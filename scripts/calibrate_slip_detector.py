#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Scores wheel_slip_node.py's detector against a recorded run.

    ./scripts/m4_acceptance.py --seeds 42 --record-signals   # produces the CSV
    ./scripts/calibrate_slip_detector.py m4_acceptance_*/seed_42_signals.csv

The detector may only look at wheel odometry and the IMU (see
wheel_slip_node.py for why ground truth is off-limits to it). The recorded
ground-truth columns are used here purely as the answer key: they label which
samples were genuinely wedged and which were genuinely driving, so the
detector's hit rate and - the number that actually matters - its FALSE
POSITIVE rate on a moving rover can both be measured instead of asserted.

A false positive is not a harmless miss: it feeds a zero-velocity update to a
rover that is really moving, which corrupts localization in the same way the
wedge does, only in the opposite direction. The thresholds are therefore
picked for separation, not sensitivity, and this script reports the margin.

WALL CLOCK vs SIM TIME: velocities are per second of simulated time and this
world runs below real time, so replaying against wall-clock timestamps
overstates every integrated distance. Recordings made after 2026-08-01 carry a
`sim_t` column and are replayed against it. Older ones are replayed against
wall time with a measured scale factor (odometry-claimed distance against
ground-truth distance over clean driving), reported so it is visible.
"""

import argparse
import csv
import importlib.util
import math
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SLIP_NODE = (
    REPO_ROOT / "src/regolith.universe/planetary/regolith_bringup/scripts/wheel_slip_node.py"
)


def _load_detector_class():
    spec = importlib.util.spec_from_file_location("wheel_slip_node", SLIP_NODE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["wheel_slip_node"] = module
    spec.loader.exec_module(module)
    return module.SlipDetector


def load_rows(path: Path) -> list:
    with path.open() as handle:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(handle)]


def time_scale(rows: list) -> tuple:
    """(scale, basis) mapping recorded timestamps to seconds of simulated time.

    With a sim_t column this is exact. Without one, it is estimated as the ratio
    of wheel-claimed distance to ground-truth distance over samples where the
    rover was clearly driving - i.e. where the wheels are known to be honest.
    """
    if "sim_t" in rows[0]:
        return 1.0, "sim_t"
    claimed = 0.0
    actual = 0.0
    for prev, row in zip(rows, rows[1:]):
        dt = row["t_s"] - prev["t_s"]
        if dt <= 0 or dt > 1.0 or prev["gt_speed"] < 0.05:
            continue
        claimed += abs(prev["odom_vx"]) * dt
        actual += math.dist((prev["gt_x"], prev["gt_y"]), (row["gt_x"], row["gt_y"]))
    scale = actual / claimed if claimed > 0 else 1.0
    return scale, f"t_s x {scale:.3f} (measured wall->sim ratio)"


def gt_path_length(rows: list, index: int, window_s: float, tkey: str) -> float:
    """Ground-truth distance TRAVELLED over the window ending at `index`.

    Path length, not endpoint displacement. The comparison is against what the
    wheels claim, which is itself a path integral, and the difference is not
    academic: an escape maneuver reverses and then drives forward, so its
    endpoint displacement is near zero while the body moved a metre. Labelling
    by displacement therefore files every recovery maneuver under "slipping" -
    which is how an earlier version of this script reported the rotation test
    as overlapping on a run that contained maneuvers, and cleanly separating on
    one that did not.
    """
    start = index
    while start > 0 and rows[index][tkey] - rows[start][tkey] < window_s:
        start -= 1
    total = 0.0
    for a, b in zip(rows[start:index], rows[start + 1:index + 1]):
        step = math.dist((a["gt_x"], a["gt_y"]), (b["gt_x"], b["gt_y"]))
        if step > 0.001:  # below this is sampling jitter, not motion
            total += step
    return total


def percentiles(values: list, points=(0, 5, 50, 95, 100)) -> str:
    if not values:
        return "n/a"
    ordered = sorted(values)
    return "  ".join(
        f"p{p}={ordered[min(len(ordered) - 1, int(p / 100 * (len(ordered) - 1)))]:.5f}"
        for p in points
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", nargs="+", type=Path)
    parser.add_argument("--window-s", type=float, default=15.0)
    parser.add_argument("--min-claimed-distance-m", type=float, default=0.25)
    parser.add_argument("--max-attitude-span-rad", type=float, default=0.010)
    parser.add_argument("--max-gyro-rms-rps", type=float, default=0.005)
    # Labels are ratios, not absolute distances. A rover scrubbing along a
    # boulder at half a centimetre per second while its wheels claim 0.19 m/s
    # is slipping by any useful definition, but it moves far enough over a
    # 15 s window to pass an absolute "is it moving" test - an earlier version
    # of this script labelled exactly that episode as honest driving, which
    # would have calibrated the detector to ignore the failure it exists for.
    parser.add_argument("--slip-ratio", type=float, default=0.25,
                        help="GT distance travelled below this fraction of the wheels' claim = slipping")
    parser.add_argument("--honest-ratio", type=float, default=0.70,
                        help="GT distance travelled above this fraction of the claim = honest driving")
    args = parser.parse_args()

    SlipDetector = _load_detector_class()
    wedged, moving = [], []
    total = 0

    for path in args.csv:
        rows = load_rows(path)
        if len(rows) < 20:
            print(f"{path}: too few samples ({len(rows)})")
            continue
        scale, basis = time_scale(rows)
        tkey = "sim_t" if "sim_t" in rows[0] else "t_s"
        print(f"{path.name}: {len(rows)} samples, time basis {basis}")

        detector = SlipDetector(
            window_s=args.window_s,
            min_claimed_distance_m=args.min_claimed_distance_m,
            max_attitude_span_rad=args.max_attitude_span_rad,
            max_gyro_rms_rps=args.max_gyro_rms_rps,
        )
        for index, row in enumerate(rows):
            t = row[tkey] * (scale if tkey == "t_s" else 1.0)
            detector.add(
                t, row["odom_vx"], row["odom_wz"], row["imu_wz"],
                (row["roll"], row["pitch"], row["yaw"]),
            )
            features = detector.features()
            if features is None:
                continue
            total += 1
            displacement = gt_path_length(rows, index, args.window_s / (scale if tkey == "t_s" else 1.0), tkey)
            claimed = features["claimed_distance_m"]
            if claimed < args.min_claimed_distance_m:
                continue  # the wheels aren't claiming anything to disagree with
            record = (features, detector.slipping(), displacement / claimed)
            if displacement <= args.slip_ratio * claimed:
                wedged.append(record)
            elif displacement >= args.honest_ratio * claimed:
                moving.append(record)

    print(f"\n{total} windows scored: {len(wedged)} slipping (ground truth moved under "
          f"{args.slip_ratio:.0%} of what the wheels claimed), {len(moving)} honest driving "
          f"(over {args.honest_ratio:.0%})")
    if not wedged:
        print("No slipping windows in this recording - nothing to calibrate against. "
              "Record a run that actually gets stuck.")
        if moving:
            # Still worth reporting: these are the windows a false positive would
            # have to come from, so they bound how tight the thresholds can be.
            print("\nDRIVING windows (the false-positive risk surface):")
            for key in ("attitude_span_rad", "gyro_rms_rps", "claimed_distance_m"):
                print(f"  {key:22} {percentiles([f[key] for f, _, _ in moving])}")
            fired = sum(1 for _, verdict, _ in moving if verdict)
            print(f"  detector fired on {fired}/{len(moving)} of them")
        return 1

    for name, group in (("SLIPPING", wedged), ("HONEST DRIVING", moving)):
        print(f"\n{name} windows:")
        for key in ("attitude_span_rad", "gyro_rms_rps", "claimed_distance_m"):
            print(f"  {key:22} {percentiles([f[key] for f, _, _ in group])}")
        print(f"  {'gt/claimed ratio':22} {percentiles([r for _, _, r in group])}")

    hits = sum(1 for _, verdict, _ in wedged if verdict)
    false_positives = sum(1 for _, verdict, _ in moving if verdict)
    print(
        f"\nAt the configured thresholds (attitude span <= {args.max_attitude_span_rad} rad, "
        f"gyro rms <= {args.max_gyro_rms_rps} rad/s, claimed >= {args.min_claimed_distance_m} m):"
    )
    print(f"  detected {hits}/{len(wedged)} slipping windows ({100.0 * hits / len(wedged):.1f}%)")
    if moving:
        print(
            f"  fired on {false_positives}/{len(moving)} driving windows "
            f"({100.0 * false_positives / len(moving):.2f}% false positive)"
        )

    driving_spans = [f["attitude_span_rad"] for f, _, _ in moving]
    wedged_spans = [f["attitude_span_rad"] for f, _, _ in wedged]
    if driving_spans and wedged_spans:
        print(
            f"\nSeparation on attitude span: slipping max {max(wedged_spans):.5f} rad, "
            f"driving min {min(driving_spans):.5f} rad, driving median "
            f"{statistics.median(driving_spans):.5f} rad"
        )
        if max(wedged_spans) < min(driving_spans):
            print("  -> the two classes do not overlap on this recording")
        else:
            print("  -> the classes OVERLAP; no threshold on this feature alone separates them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
