#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Summarise a terrain_relative_campaign run: both arms, plus what the matcher actually did.

The per-run verdict is only half the story. A run where the fix never published
(all windows rejected as ambiguous) and a run where it published twenty fixes and
they were wrong are both "FAIL", and they need entirely different follow-ups - so
this pulls the node's own accounting out of the launch log alongside the verdict.

Also checks the IMU's roll/pitch against the ground-truth columns. Every offline
validation of the matcher was scored against ground-truth attitude because the
IMU's own attitude was not recorded at the time; this simulator's IMU declares no
noise model so they should agree, and this is where that stops being an
assumption.
"""

import argparse
import json
from pathlib import Path
import re

import numpy as np

# Matches BOTH wordings the node has used. The line was reworded from "Terrain fix
# #N ... : correction (dx, dy)" to "Terrain correction #N ... : (dx, dy)", and this
# pattern was not updated - so from that rewording until 2026-09-14 this script
# silently reported "fixes published 0" for every run, including runs that had
# published fourteen. Nothing failed; a count simply came back empty, which reads
# exactly like a matcher that rejected everything. Both forms are kept because
# both appear in campaign logs already on disk. test_report_parsers.py pins them.
FIX_RE = re.compile(
    r"Terrain (?:fix|correction) #(\d+) at ([\d.]+) m travelled: (?:correction )?"
    r"\(([-+][\d.]+), ([-+][\d.]+)\) m, margin ([\d.]+)"
)
REJECT_MARGIN_RE = re.compile(r"Terrain fix rejected: margin")
REJECT_CONSISTENCY_RE = re.compile(r"Terrain fix rejected: disagrees")
# The authoritative running totals, carried inside the correction line itself.
TOTALS_RE = re.compile(
    r"Terrain correction #(\d+) at [\d.]+ m travelled: .*?(\d+) poses published "
    r"\(rejected so far: (\d+) ambiguous, (\d+) inconsistent\)"
)


def node_activity(run_dir: Path) -> dict:
    """What the matcher actually did, from the node's own accounting.

    COUNT THE COUNTERS, NOT THE LINES. Every one of these log calls is throttled -
    the correction line to one per `report_every_m` of travel, both rejection lines
    to one per 30 s - so the number of lines in the log is a sample of the activity
    and not a measure of it. An earlier version of this function counted lines, and
    on a real run that reported 14 corrections where the node had applied 61 and 28
    ambiguous rejections where it had counted 226. The node carries the true
    running totals inside the correction line; those are what this reads, and line
    counting survives only as a fallback for a log with no correction line at all
    (a run where nothing was ever published, where the line count IS the total).

    `sampled_fixes` is the per-line detail - offsets and margins - and is a
    throttled SAMPLE by construction. Its offsets are also post-clamp, so they say
    what the filter was asked to do, not what the matcher measured.
    """
    logs = list(run_dir.glob("*_launch.log"))
    if not logs:
        return {}
    text = logs[0].read_text(errors="replace")
    fixes = [
        {"n": int(m[0]), "travelled_m": float(m[1]), "dx": float(m[2]), "dy": float(m[3]),
         "margin": float(m[4])}
        for m in FIX_RE.findall(text)
    ]
    totals = TOTALS_RE.findall(text)
    if totals:
        n, poses, ambiguous, inconsistent = (int(v) for v in totals[-1])
    else:
        n, poses = len(fixes), 0
        ambiguous = len(REJECT_MARGIN_RE.findall(text))
        inconsistent = len(REJECT_CONSISTENCY_RE.findall(text))
    return {
        "fixes": fixes,                  # kept for callers that want the sample
        "sampled_fixes": fixes,
        "corrections_applied": n,
        "poses_published": poses,
        "rejected_ambiguous": ambiguous,
        "rejected_inconsistent": inconsistent,
        "counts_are_sampled": not totals,
    }


def imu_vs_truth(run_dir: Path) -> str:
    signals = list(run_dir.glob("*_signals.csv"))
    if not signals:
        return "no signals recorded"
    header = signals[0].open().readline()
    if "imu_roll" not in header:
        return "predates the imu_roll/imu_pitch columns"
    d = np.genfromtxt(signals[0], delimiter=",", names=True)
    ok = np.isfinite(d["imu_roll"]) & np.isfinite(d["roll"])
    if ok.sum() < 100:
        return "too few samples"
    dr = np.degrees(d["imu_roll"][ok] - d["roll"][ok])
    dp = np.degrees(d["imu_pitch"][ok] - d["pitch"][ok])
    return (f"roll {dr.mean():+.3f} +- {dr.std():.3f} deg, "
            f"pitch {dp.mean():+.3f} +- {dp.std():.3f} deg (n={ok.sum()})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign_dir", nargs="?", default="terrain_relative_campaign")
    args = parser.parse_args()

    root = Path(args.campaign_dir)
    rows = []
    for run_dir in sorted(root.glob("seed*_trn_*_rep*")):
        results = list(run_dir.glob("*_result.json"))
        if not results:
            print(f"{run_dir.name}: no result yet")
            continue
        r = json.loads(results[0].read_text())
        arm = "ON " if "_on_" in run_dir.name else "OFF"
        activity = node_activity(run_dir)
        rows.append((run_dir.name, arm, r))
        print(f"{run_dir.name:34s} {arm}  {r['verdict']:20s} "
              f"gt_err {r.get('gt_error_m', float('nan')):6.2f}  "
              f"diverg {r.get('divergence_m', float('nan')):6.2f}  "
              f"travelled {r.get('gt_travelled_m', float('nan')):6.1f}")
        if activity:
            fixes = activity["sampled_fixes"]
            print(f"{'':34s}     corrections applied {activity['corrections_applied']}, "
                  f"{activity['poses_published']} poses published, rejected "
                  f"{activity['rejected_ambiguous']} ambiguous / "
                  f"{activity['rejected_inconsistent']} inconsistent")
            if fixes:
                mags = [np.hypot(f["dx"], f["dy"]) for f in fixes]
                print(f"{'':34s}     (throttled sample of {len(fixes)}, post-clamp) "
                      f"correction median {np.median(mags):.2f} m, max {max(mags):.2f} m, "
                      f"margins {min(f['margin'] for f in fixes):.1f}-"
                      f"{max(f['margin'] for f in fixes):.1f}")
        print(f"{'':34s}     IMU vs ground-truth attitude: {imu_vs_truth(run_dir)}")

    for arm in ("ON ", "OFF"):
        div = [r.get("divergence_m") for _, a, r in rows
               if a == arm and isinstance(r.get("divergence_m"), (int, float))]
        err = [r.get("gt_error_m") for _, a, r in rows
               if a == arm and isinstance(r.get("gt_error_m"), (int, float))]
        if div:
            print(f"\narm {arm}: n={len(div)}  divergence median {np.median(div):.2f} m "
                  f"(range {min(div):.2f}-{max(div):.2f})  arrival error median {np.median(err):.2f} m")


if __name__ == "__main__":
    main()
