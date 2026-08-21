#!/usr/bin/env python3
"""Direct escape-window vs ordinary-driving decomposition of EKF divergence.

Targeted follow-up to "Turning vs. divergence, measured directly" in
PROGRESS.md. That section found a near-perfect raw correlation between total
accumulated |wz| and final divergence (r~0.995, n=3) which did not survive an
escape-attributable-turning subtraction using *commanded* escape rates: once
subtracted, ordinary-driving turning barely differed between reps while
divergence differed ~3.5x, pointing at the escape/stuck machinery rather than
general path turning.

This script sharpens that check using data already on disk (no new sim
runs): it reads each run's actual instrumented signals (10 Hz odom_wz/imu_wz)
rather than commanded escape rates, splits each run's timeline into
escape-maneuver windows (from the launch log's "took over" / "Recovery
finished" bracket pairs, converted to the recorder's elapsed-seconds clock via
the run's recorded start time) and the ordinary-driving remainder, and asks
the sharper question directly: is divergence accumulated per radian of
turning higher during escape windows than during ordinary driving, for the
same run?

Usage: python3 scripts/escape_window_divergence.py <run_dir> [<run_dir> ...]
Each run_dir must contain seed_42_launch.log, seed_42_trace.csv,
seed_42_signals.csv, and run.json (the turning_vs_divergence_campaign.sh
layout).
"""
import csv
import datetime
import json
import re
import sys
from pathlib import Path

TAKEOVER_RE = re.compile(r"^\[.*?\]\s+\[([\d.]+)\].*Recovery node has taken over /cmd_vel")
FINISHED_RE = re.compile(r"^\[.*?\]\s+\[([\d.]+)\].*Recovery finished - resuming path following")


def load_trace(path):
    """Skips rows before the EKF has converged (divergence_m is nan for the
    first sample or two, before the filter has a fix) rather than dragging
    nan through every downstream computation."""
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            d = row["divergence_m"]
            if d == "nan":
                continue
            rows.append((float(row["t_s"]), float(d)))
    return rows


def load_signals(path):
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            rows.append((float(row["t_s"]), abs(float(row["odom_wz"])), abs(float(row["imu_wz"]))))
    return rows


def interp(rows, t):
    """Linear interpolation of a (t, value) series at time t, clamped at the ends."""
    if t <= rows[0][0]:
        return rows[0][1]
    if t >= rows[-1][0]:
        return rows[-1][1]
    for (t0, v0), (t1, v1) in zip(rows, rows[1:]):
        if t0 <= t <= t1:
            if t1 == t0:
                return v0
            frac = (t - t0) / (t1 - t0)
            return v0 + frac * (v1 - v0)
    return rows[-1][1]


def escape_windows_t_s(log_path, anchor_epoch):
    starts, ends = [], []
    with open(log_path, errors="replace") as f:
        for line in f:
            m = TAKEOVER_RE.match(line)
            if m:
                starts.append(float(m.group(1)) - anchor_epoch)
                continue
            m = FINISHED_RE.match(line)
            if m:
                ends.append(float(m.group(1)) - anchor_epoch)
    if len(starts) != len(ends):
        raise ValueError(f"{log_path}: {len(starts)} takeovers vs {len(ends)} finishes - unpaired")
    return list(zip(starts, ends))


def accumulate_turning(signals, t0, t1, idx):
    """Trapezoidal accumulation of |wz| dt over [t0, t1], clipping partial
    boundary segments to the overlap, using every consecutive sample pair in
    the full 10 Hz series (not just samples strictly inside the window).
    signals rows are (t, odom_wz, imu_wz); idx selects which of the last two."""
    total = 0.0
    for s0, s1 in zip(signals, signals[1:]):
        ta, tb = s0[0], s1[0]
        va, vb = s0[idx], s1[idx]
        lo, hi = max(ta, t0), min(tb, t1)
        if hi <= lo:
            continue
        span = tb - ta
        if span <= 0:
            continue
        v_lo = va + (vb - va) * (lo - ta) / span
        v_hi = va + (vb - va) * (hi - ta) / span
        total += 0.5 * (v_lo + v_hi) * (hi - lo)
    return total


def analyze(run_dir):
    run_dir = Path(run_dir)
    run_meta = json.loads((run_dir / "run.json").read_text())
    started = datetime.datetime.strptime(run_meta["started"], "%Y-%m-%d %H:%M:%S")
    anchor_epoch = started.timestamp()

    trace = load_trace(run_dir / "seed_42_trace.csv")
    signals = load_signals(run_dir / "seed_42_signals.csv")
    windows = escape_windows_t_s(run_dir / "seed_42_launch.log", anchor_epoch)

    run_t0, run_t1 = trace[0][0], trace[-1][0]
    escape_total_dt = 0.0
    escape_div_delta = 0.0
    escape_odom_turn = 0.0
    escape_imu_turn = 0.0

    for (t0, t1) in windows:
        t0 = max(t0, run_t0)
        t1 = min(t1, run_t1)
        if t1 <= t0:
            continue
        escape_total_dt += (t1 - t0)
        escape_div_delta += interp(trace, t1) - interp(trace, t0)
        escape_odom_turn += accumulate_turning(signals, t0, t1, 1)
        escape_imu_turn += accumulate_turning(signals, t0, t1, 2)

    total_div_delta = trace[-1][1] - trace[0][1]
    total_odom_turn = accumulate_turning(signals, run_t0, run_t1, 1)
    total_imu_turn = accumulate_turning(signals, run_t0, run_t1, 2)
    total_dt = run_t1 - run_t0

    ordinary_dt = total_dt - escape_total_dt
    ordinary_div_delta = total_div_delta - escape_div_delta
    ordinary_odom_turn = total_odom_turn - escape_odom_turn
    ordinary_imu_turn = total_imu_turn - escape_imu_turn

    def rate(div, turn):
        return div / turn if turn > 1e-9 else float("nan")

    return {
        "run_dir": str(run_dir),
        "n_escape_windows": len(windows),
        "total_dt_s": total_dt,
        "escape_dt_s": escape_total_dt,
        "ordinary_dt_s": ordinary_dt,
        "total_div_delta_m": total_div_delta,
        "escape_div_delta_m": escape_div_delta,
        "ordinary_div_delta_m": ordinary_div_delta,
        "total_odom_turn_rad": total_odom_turn,
        "escape_odom_turn_rad": escape_odom_turn,
        "ordinary_odom_turn_rad": ordinary_odom_turn,
        "total_imu_turn_rad": total_imu_turn,
        "escape_imu_turn_rad": escape_imu_turn,
        "ordinary_imu_turn_rad": ordinary_imu_turn,
        "escape_div_per_rad_odom": rate(escape_div_delta, escape_odom_turn),
        "ordinary_div_per_rad_odom": rate(ordinary_div_delta, ordinary_odom_turn),
        "escape_div_per_rad_imu": rate(escape_div_delta, escape_imu_turn),
        "ordinary_div_per_rad_imu": rate(ordinary_div_delta, ordinary_imu_turn),
        "escape_div_per_s": rate(escape_div_delta, escape_total_dt),
        "ordinary_div_per_s": rate(ordinary_div_delta, ordinary_dt),
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    results = [analyze(d) for d in sys.argv[1:]]
    for r in results:
        print(f"\n=== {r['run_dir']} ===")
        print(f"  escape windows: {r['n_escape_windows']}  "
              f"escape dt: {r['escape_dt_s']:.1f}s / {r['total_dt_s']:.1f}s total "
              f"({100*r['escape_dt_s']/r['total_dt_s']:.1f}%)")
        print(f"  divergence delta: total {r['total_div_delta_m']:.3f}m  "
              f"escape {r['escape_div_delta_m']:.3f}m  ordinary {r['ordinary_div_delta_m']:.3f}m")
        print(f"  odom turning (rad): total {r['total_odom_turn_rad']:.2f}  "
              f"escape {r['escape_odom_turn_rad']:.2f}  ordinary {r['ordinary_odom_turn_rad']:.2f}")
        print(f"  divergence per radian (odom): escape {r['escape_div_per_rad_odom']:.4f} m/rad  "
              f"ordinary {r['ordinary_div_per_rad_odom']:.4f} m/rad  "
              f"ratio {r['escape_div_per_rad_odom']/r['ordinary_div_per_rad_odom']:.2f}x")
        print(f"  divergence per radian (imu):  escape {r['escape_div_per_rad_imu']:.4f} m/rad  "
              f"ordinary {r['ordinary_div_per_rad_imu']:.4f} m/rad  "
              f"ratio {r['escape_div_per_rad_imu']/r['ordinary_div_per_rad_imu']:.2f}x")
        print(f"  divergence per second: escape {r['escape_div_per_s']:.5f} m/s  "
              f"ordinary {r['ordinary_div_per_s']:.5f} m/s  "
              f"ratio {r['escape_div_per_s']/r['ordinary_div_per_s']:.2f}x")

    print("\n=== summary across runs (escape vs ordinary, per radian of odom turning) ===")
    for r in results:
        print(f"{r['run_dir']}: escape {r['escape_div_per_rad_odom']:.4f} m/rad vs "
              f"ordinary {r['ordinary_div_per_rad_odom']:.4f} m/rad "
              f"({r['escape_div_per_rad_odom']/r['ordinary_div_per_rad_odom']:.2f}x)")

    if len(results) > 1:
        print("\n=== cross-run check: does the ORDINARY per-radian rate from the other runs "
              "predict this run's TOTAL divergence, given its TOTAL turning? ===")
        for i, r in enumerate(results):
            others = [o for j, o in enumerate(results) if j != i]
            avg_other_rate = sum(o["ordinary_div_per_rad_odom"] for o in others) / len(others)
            predicted = avg_other_rate * r["total_odom_turn_rad"]
            actual = r["total_div_delta_m"]
            print(f"{r['run_dir']}: predicted {predicted:.3f}m (at {avg_other_rate:.4f} m/rad x "
                  f"{r['total_odom_turn_rad']:.1f} rad) vs actual {actual:.3f}m "
                  f"({actual/predicted:.2f}x predicted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
