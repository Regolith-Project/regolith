#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Record a cinematic clip from an ALREADY-RUNNING hello_moon.launch.py (with
cine_camera and/or cine_rig enabled) and assemble it into a finished, honestly
re-timed mp4.

Why this is a separate script from the launch itself: recording is something you
choose to do to a run that's already happening (a tour, a hand-driven session, a
scripted drive), not a property of the launch. This script drives none of the
navigation stack - it only calls the CameraVideoRecorder gz service and (optionally)
a short /cmd_vel burst so a throwaway smoke-test clip has something to look at
without waiting for a full autonomous tour.

Mechanism (see docs/media/README.md's "camera rig" section and
regolith_bringup/scripts/camera_rig_node.py for the full writeup):
  - Recording: gz-sim's server-side CameraVideoRecorder plugin, started/stopped via
    `gz service -s <service> --reqtype gz.msgs.VideoRecord`. Writes the mp4 moov
    atom on STOP - a crash mid-recording loses the whole take - so this script
    ALWAYS records in bounded segments (default 150 s, override with
    --segment-s) and verifies each segment file with ffprobe before trusting it,
    exactly like the existing manually-run workflow this replaces.
  - Re-timing: the true fix, not a guess. This world runs at roughly 0.05-0.10x
    real time with a 720p+ camera attached, so raw footage crawls. This script
    measures the REAL-TIME FACTOR over the actual capture window (world stats'
    sim_time delta / wall-clock delta of the recording), and applies exactly
    `setpts=1/RTF` per segment so one second of finished clip is one simulated
    second - a correction to true speed, never an exaggeration of it. It also
    NEVER lies about a segment whose stats read-back failed: such a segment is
    left at 1x and flagged, rather than guessing a factor.

Usage (against an already-running cine_rig or cine_camera launch):
    scripts/record_cine.py --world regolith_moon --service rover/rig/record_video \\
        --out docs/media/dev/chase_smoketest.mp4 --duration-s 12

    # throwaway smoke test that also drives the rover for the duration:
    scripts/record_cine.py --service rover/rig/record_video \\
        --out /tmp/chase_test.mp4 --duration-s 15 --drive 0.3 0.15
"""

import argparse
from dataclasses import dataclass
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _gz_service(service, reqtype, reptype, req, timeout_ms=8000, env=None):
    cmd = [
        "gz", "service", "-s", service,
        "--reqtype", reqtype, "--reptype", reptype,
        "--timeout", str(timeout_ms), "--req", req,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_ms / 1000.0 + 5)
    ok = out.returncode == 0 and "true" in out.stdout.lower()
    return ok, out.stdout.strip(), out.stderr.strip()


def _world_stats(world, env=None, timeout_s=8.0):
    """Returns (sim_time_s, real_time_s) or None if the read failed. Uses the
    world-scoped stats topic, not generic /stats - see the repo's WSL gotchas note
    on why a generic /stats can hold a stale latched message from a dead server."""
    try:
        out = subprocess.run(
            ["gz", "topic", "-e", "-n", "1", "-t", f"/world/{world}/stats"],
            env=env, capture_output=True, text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    sim_sec = sim_nsec = real_sec = real_nsec = 0
    section = None
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("sim_time"):
            section = "sim"
        elif line.startswith("real_time"):
            section = "real"
        elif line.startswith("sec:"):
            v = int(line.split(":")[1].strip())
            if section == "sim":
                sim_sec = v
            elif section == "real":
                real_sec = v
        elif line.startswith("nsec:"):
            v = int(line.split(":")[1].strip())
            if section == "sim":
                sim_nsec = v
            elif section == "real":
                real_nsec = v
    return (sim_sec + sim_nsec * 1e-9, real_sec + real_nsec * 1e-9)


def _ffprobe_duration(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        return float(out.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None


def _distinct_frame_count(path, timeout_s=60):
    """How many of the container's frames are actually DISTINCT renders, not the
    container frame rate. A clip whose camera sensor update_rate (sim time) is
    lower than the container fps repeats the same rendered frame across several
    output frames - invisible in `ffprobe`'s frame count, very visible as stutter
    on a full-screen watch. This is exactly the gap that caught the first cine_rig
    take at 15 Hz (a 1.04s/~31-frame clip that was actually only 26 distinct
    renders) - see docs/media/README.md's "frame count, not container fps" note.

    Uses ffmpeg's mpdecimate filter, which drops frames that are near-duplicates of
    the previous one; the count of frames that SURVIVE decimation is the distinct-
    frame count. Returns (total_frames, distinct_frames, distinct_fps) or None on
    failure.
    """
    total = None
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
             "-show_entries", "stream=nb_read_frames,duration",
             "-of", "default=noprint_wrappers=1", str(path)],
            capture_output=True, text=True, timeout=timeout_s,
        )
        duration = None
        for line in probe.stdout.splitlines():
            if line.startswith("nb_read_frames="):
                total = int(line.split("=", 1)[1])
            elif line.startswith("duration="):
                try:
                    duration = float(line.split("=", 1)[1])
                except ValueError:
                    duration = None
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None
    if total is None:
        return None

    try:
        out = subprocess.run(
            ["ffmpeg", "-i", str(path), "-vf", "mpdecimate", "-loglevel", "debug",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return None
    # ffmpeg -loglevel debug prints one "Parsed_mpdecimate..." line per surviving
    # frame is not reliable across builds; instead read the final encoder summary
    # ("frame=  N ") from stderr, which counts frames actually sent downstream
    # (i.e. survivors of the decimate filter).
    distinct = None
    for line in reversed(out.stderr.splitlines()):
        line = line.strip()
        if line.startswith("frame="):
            try:
                distinct = int(line.split("frame=")[1].split()[0])
            except (IndexError, ValueError):
                continue
            break
    if distinct is None:
        return None
    distinct_fps = (distinct / duration) if duration else None
    return total, distinct, distinct_fps


@dataclass
class SegmentResult:
    path: Path
    ok: bool
    rtf: float | None
    sim_elapsed_s: float | None
    wall_elapsed_s: float | None
    note: str


def record_segment(service, world, out_path, duration_s, env, drive=None, poll_s=2.0):
    """Start the recorder, optionally stream /cmd_vel for the duration, wait, stop.
    Returns a SegmentResult with the MEASURED (not assumed) real-time factor."""
    drive_proc = None
    if drive is not None:
        lin, ang = drive
        drive_proc = subprocess.Popen(
            ["ros2", "topic", "pub", "-r", "5", "/cmd_vel", "geometry_msgs/msg/Twist",
             f"{{linear: {{x: {lin}}}, angular: {{z: {ang}}}}}"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    try:
        stats_before = _world_stats(world, env=env)
        ok_start, out, err = _gz_service(
            service, "gz.msgs.VideoRecord", "gz.msgs.Boolean",
            f'start: true, format:"mp4", save_filename:"{out_path.name}"',
            env=env,
        )
        wall_start = time.monotonic()
        if not ok_start:
            return SegmentResult(out_path, False, None, None, None,
                                  f"start call failed: {err or out}")
        waited = 0.0
        while waited < duration_s:
            step = min(poll_s, duration_s - waited)
            time.sleep(step)
            waited += step
        ok_stop, out, err = _gz_service(
            service, "gz.msgs.VideoRecord", "gz.msgs.Boolean", "stop: true", env=env,
        )
        wall_elapsed = time.monotonic() - wall_start
        stats_after = _world_stats(world, env=env)
        if not ok_stop:
            return SegmentResult(out_path, False, None, None, wall_elapsed,
                                  f"stop call failed: {err or out}")
    finally:
        if drive_proc is not None:
            try:
                os.killpg(os.getpgid(drive_proc.pid), 15)
            except (ProcessLookupError, PermissionError):
                pass

    if stats_before is None or stats_after is None:
        return SegmentResult(out_path, out_path.exists(), None, None, wall_elapsed,
                              "world stats read failed - RTF NOT measured, "
                              "segment left at 1x rather than guessed")

    sim_elapsed = stats_after[0] - stats_before[0]
    wall_stats_elapsed = stats_after[1] - stats_before[1]
    if wall_stats_elapsed <= 0 or sim_elapsed <= 0:
        return SegmentResult(out_path, out_path.exists(), None, sim_elapsed,
                              wall_elapsed, "non-positive elapsed time - RTF NOT measured")

    rtf = sim_elapsed / wall_stats_elapsed
    note = "ok"
    gz_recorded_by = out_path  # gz writes into the launch's cwd, see below
    return SegmentResult(out_path, out_path.exists(), rtf, sim_elapsed, wall_elapsed, note)


def retime_segment(src, dst, rtf, note=""):
    """setpts=1/RTF so one clip-second is one simulated second - see module docstring.
    If RTF is unknown, copies the file unchanged rather than guessing a factor."""
    if rtf is None:
        shutil.copy(src, dst)
        return f"NOT re-timed (RTF unmeasured: {note}) - ships at raw 1x recorder output"
    speed = 1.0 / rtf
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-vf", f"setpts={rtf:.6f}*PTS",
         "-an", str(dst)],
        capture_output=True, text=True, timeout=120, check=True,
    )
    return f"re-timed by {speed:.2f}x (measured RTF {rtf:.4f} over this capture window)"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--world", default="regolith_moon")
    ap.add_argument("--service", required=True, help="e.g. rover/rig/record_video")
    ap.add_argument("--out", required=True, help="final, re-timed mp4 path")
    ap.add_argument("--duration-s", type=float, default=12.0, help="TOTAL wall-clock recording time")
    ap.add_argument("--segment-s", type=float, default=150.0,
                     help="max wall-clock time per recorder segment - the mp4 moov atom is "
                          "only written on STOP, so a crash mid-segment loses the whole "
                          "segment, never more (default matches the existing workflow)")
    ap.add_argument("--drive", nargs=2, type=float, metavar=("LINEAR", "ANGULAR"), default=None,
                     help="also stream this /cmd_vel for the duration - for throwaway smoke "
                          "tests that need motion without a full autonomous mission running")
    ap.add_argument("--gz-partition", default=None,
                     help="GZ_PARTITION to target - must match the launch you are recording "
                          "against. hello_moon.launch.py does not set one itself (a known "
                          "gap - see docs/media/README.md), so pass whatever you exported "
                          "before launching, or omit to use the default partition")
    ap.add_argument("--ros-domain-id", type=int, default=None)
    ap.add_argument("--recorder-cwd", default=".",
                     help="gz-sim writes the mp4 into the directory IT was launched from, "
                          "not this script's cwd - point this at that directory")
    args = ap.parse_args()

    env = dict(os.environ)
    if args.gz_partition:
        env["GZ_PARTITION"] = args.gz_partition
    if args.ros_domain_id is not None:
        env["ROS_DOMAIN_ID"] = str(args.ros_domain_id)

    out_final = Path(args.out)
    out_final.parent.mkdir(parents=True, exist_ok=True)
    recorder_cwd = Path(args.recorder_cwd)

    n_segments = max(1, int(-(-args.duration_s // args.segment_s)))  # ceil
    per_segment_s = args.duration_s / n_segments
    print(f"[record_cine] {n_segments} segment(s) of ~{per_segment_s:.1f}s each "
          f"(total {args.duration_s:.1f}s wall-clock)", flush=True)

    segment_results = []
    for i in range(n_segments):
        seg_name = f"{out_final.stem}_seg{i:02d}.mp4"
        seg_path_recorder = recorder_cwd / seg_name  # where gz actually writes it
        if seg_path_recorder.exists():
            seg_path_recorder.unlink()
        print(f"[record_cine] segment {i+1}/{n_segments}: recording {per_segment_s:.1f}s "
              f"-> {seg_path_recorder}", flush=True)
        result = record_segment(
            args.service, args.world, seg_path_recorder, per_segment_s, env,
            drive=args.drive,
        )
        if not seg_path_recorder.exists():
            print(f"[record_cine] segment {i+1} produced NO FILE ({result.note}) - "
                  f"skipping it, continuing with what we have", flush=True)
            continue
        dur = _ffprobe_duration(seg_path_recorder)
        if dur is None:
            print(f"[record_cine] segment {i+1} file exists but ffprobe could not read it "
                  f"(likely a truncated/crash-lost moov atom) - DROPPING this segment", flush=True)
            continue
        print(f"[record_cine] segment {i+1}: {dur:.2f}s recorded, "
              f"RTF={'%.4f' % result.rtf if result.rtf else 'UNKNOWN'} "
              f"(sim {result.sim_elapsed_s and round(result.sim_elapsed_s,3)}s / "
              f"wall {result.wall_elapsed_s and round(result.wall_elapsed_s,3)}s), "
              f"note={result.note}", flush=True)
        segment_results.append((seg_path_recorder, result, dur))

    if not segment_results:
        print("[record_cine] FAILED: no valid segments recorded", flush=True)
        return 1

    retimed_paths = []
    provenance_lines = []
    for idx, (seg_path, result, dur) in enumerate(segment_results):
        retimed_path = seg_path.with_name(seg_path.stem + "_retimed.mp4")
        msg = retime_segment(seg_path, retimed_path, result.rtf, result.note)
        print(f"[record_cine] segment {idx}: {msg}", flush=True)
        retimed_paths.append(retimed_path)
        provenance_lines.append(
            f"  segment {idx}: {dur:.2f}s raw, RTF={result.rtf}, {msg}"
        )

    if len(retimed_paths) == 1:
        shutil.copy(retimed_paths[0], out_final)
    else:
        concat_list = out_final.with_suffix(".concat.txt")
        concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in retimed_paths))
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-c", "copy", str(out_final)],
            capture_output=True, text=True, timeout=120, check=True,
        )
        concat_list.unlink()

    print("[record_cine] counting DISTINCT rendered frames in the final clip "
          "(container frame count is not this - see docs/media/README.md)", flush=True)
    frame_check = _distinct_frame_count(out_final)
    if frame_check is None:
        print("[record_cine] WARNING: distinct-frame check failed to run - "
              "cannot confirm this clip isn't stuttery duplicate frames", flush=True)
        frame_summary = None
    else:
        total, distinct, distinct_fps = frame_check
        frame_summary = {"total_frames": total, "distinct_frames": distinct,
                          "distinct_fps": distinct_fps}
        fps_str = f"{distinct_fps:.1f}" if distinct_fps else "?"
        print(f"[record_cine] {distinct}/{total} frames are distinct renders "
              f"(effective {fps_str} fps of real motion)", flush=True)
        if distinct < total * 0.9:
            print(f"[record_cine] WARNING: {total - distinct} of {total} output frames "
                  f"are duplicates of the previous frame - this WILL read as stutter. "
                  f"Raise the rig camera sensor's update_rate to match the output "
                  f"frame rate (see _cine_rig_sdf in hello_moon.launch.py).", flush=True)

    provenance = {
        "service": args.service,
        "world": args.world,
        "requested_duration_s": args.duration_s,
        "segments": [
            {"raw_duration_s": dur, "rtf": result.rtf, "note": result.note}
            for _, result, dur in segment_results
        ],
        "output": str(out_final),
        "distinct_frames": frame_summary,
    }
    provenance_path = out_final.with_suffix(".provenance.json")
    provenance_path.write_text(json.dumps(provenance, indent=2))
    print(f"[record_cine] wrote {out_final}", flush=True)
    print(f"[record_cine] wrote {provenance_path}", flush=True)
    print("[record_cine] provenance summary:", flush=True)
    for line in provenance_lines:
        print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
