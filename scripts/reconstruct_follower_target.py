#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Reconstructs pure_pursuit_node's heading error from recorded data, offline.

PROGRESS.md's open question on the fixed-arm split is why the follower steers
at its 0.30 rad/s angular limit at one spot in some reps and not in others,
from the same position, heading and pose estimate. `|cmd angular_z|` alone
cannot answer it: it saturates, so every rep at the limit looks identical and
the heading error behind it is unrecoverable.

The follower's control law is small and deterministic, so given the path it
was following (`--record-paths`) and the pose trace (`--record-signals`) the
heading error is recomputable exactly. This does that, and - because a
reconstruction nobody checked is just a second opinion - it can score itself
against the `/cmd_vel` the run actually recorded.

One caveat this cannot escape: the follower steers on the EKF estimate, while
the signals CSV records ground-truth pose and yaw. Over the fork window the
two differ by 0.13-0.20 m (PROGRESS.md), so reconstructed alpha carries that
error. --validate reports it rather than hiding it.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

# pure_pursuit_node.py's defaults - see that file; changing them there without
# changing them here makes every number this prints quietly wrong.
LOOKAHEAD_M = 1.5
MAX_ANGULAR = 0.30
BASE_SPEED = 0.2
ANGULAR_GAIN = 1.5
ROTATE_IN_PLACE_ALPHA = math.pi / 6


def normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def follower_target(path: list, position: tuple, lookahead_m: float = LOOKAHEAD_M) -> tuple:
    """The waypoint pure_pursuit would steer at, and the index it came from.

    Mirrors _control_step: nearest waypoint, then walk forward accumulating
    segment lengths until lookahead_m is covered.
    """
    if not path:
        raise ValueError("empty path")
    distances = [math.dist(p, position) for p in path]
    nearest_idx = min(range(len(path)), key=distances.__getitem__)
    target_idx = nearest_idx
    accumulated = 0.0
    while target_idx < len(path) - 1 and accumulated < lookahead_m:
        accumulated += math.dist(path[target_idx + 1], path[target_idx])
        target_idx += 1
    return path[target_idx], target_idx, distances[nearest_idx]


def follower_command(path: list, position: tuple, yaw: float, goal_xy: tuple = None,
                     lookahead_m: float = LOOKAHEAD_M, cost_factor: float = 1.0) -> dict:
    """What pure_pursuit would publish from this pose against this path.

    cost_factor is the one input not recoverable from a pose trace (it needs
    the live costmap), so it is a parameter: linear_x scales with it, alpha and
    angular_z do not.
    """
    target_xy, target_idx, deviation = follower_target(path, position, lookahead_m)
    if target_idx == len(path) - 1 and goal_xy is not None:
        target_xy = goal_xy
    heading = math.atan2(target_xy[1] - position[1], target_xy[0] - position[0])
    alpha = normalize_angle(heading - yaw)
    angular_z = max(-MAX_ANGULAR, min(MAX_ANGULAR, ANGULAR_GAIN * alpha))
    if abs(alpha) > ROTATE_IN_PLACE_ALPHA:
        linear_x = 0.0
    else:
        turn_factor = max(0.15, 1.0 - abs(alpha) / (math.pi / 3))
        linear_x = BASE_SPEED * turn_factor * cost_factor
    return {
        "alpha_deg": math.degrees(alpha),
        "angular_z": angular_z,
        "linear_x": linear_x,
        "target_xy": list(target_xy),
        "target_idx": target_idx,
        "deviation_m": deviation,
        "saturated": abs(angular_z) >= MAX_ANGULAR - 1e-9,
        "rotate_in_place": abs(alpha) > ROTATE_IN_PLACE_ALPHA,
    }


def recovery_owns_cmd(linear_x: float, angular_z: float) -> bool:
    """True when /cmd_vel was published by flip_recovery_node, not the follower.

    During an escape maneuver `_control_step` returns immediately and the
    recovery node drives - so those samples are not the follower's output and
    scoring a reconstruction against them measures nothing. The signals CSV has
    no /recovery_active column (recording one would be cleaner; this campaign's
    schema was already fixed when the need showed up), but the two writers are
    separable by their own limits: the follower never commands a negative
    linear velocity and never exceeds max_angular_velocity, while the escape
    reverses at -0.2 m/s and turns at 0.5 rad/s.
    """
    if math.isnan(linear_x) or math.isnan(angular_z):
        return False
    return linear_x < -1e-6 or abs(angular_z) > MAX_ANGULAR + 1e-3


def load_paths(rep_dir: Path, seed: int) -> list:
    f = rep_dir / f"seed_{seed}_paths.jsonl"
    if not f.exists():
        raise SystemExit(f"{f} not found - the run needs --record-paths")
    return [json.loads(line) for line in f.read_text().splitlines() if line.strip()]


def load_signals(rep_dir: Path, seed: int) -> list:
    f = rep_dir / f"seed_{seed}_signals.csv"
    if not f.exists():
        raise SystemExit(f"{f} not found - the run needs --record-signals")
    with f.open() as fh:
        return list(csv.DictReader(fh))


def path_in_force(paths: list, sim_t: float):
    """The most recent path published at or before sim_t."""
    active = None
    for p in paths:
        if p["sim_t"] <= sim_t:
            active = p
        else:
            break
    return active


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rep_dir", type=Path)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--from-t", type=float, default=365.0, help="sim time window start")
    ap.add_argument("--to-t", type=float, default=385.0)
    ap.add_argument("--step", type=float, default=1.0, help="print every N sim seconds")
    ap.add_argument("--validate", action="store_true",
                    help="score reconstructed angular_z against the recorded /cmd_vel")
    args = ap.parse_args()

    paths = load_paths(args.rep_dir, args.seed)
    rows = load_signals(args.rep_dir, args.seed)
    print(f"{len(paths)} planned paths, {len(rows)} signal rows")
    for p in paths:
        print(f"  path #{p['seq']}: sim_t={p['sim_t']:8.2f}  {p['n_poses']:3d} waypoints"
              f"  published while the rover was at {p['gt_at_publish']}")

    errors = []
    skipped = 0
    print(f"\n sim_t   gt_x    gt_y    yaw     alpha   recon_w  recorded_w  sat  rot-in-place")
    nxt = args.from_t
    for r in rows:
        t = float(r["sim_t"])
        if not (args.from_t <= t <= args.to_t):
            continue
        active = path_in_force(paths, t)
        if active is None:
            continue
        pos = (float(r["gt_x"]), float(r["gt_y"]))
        yaw = float(r["yaw"])
        cmd = follower_command([tuple(p) for p in active["poses"]], pos, yaw)
        recorded_w = float(r["cmd_ang_z"]) if "cmd_ang_z" in r else float("nan")
        recorded_v = float(r["cmd_lin_x"]) if "cmd_lin_x" in r else float("nan")
        owned_by_recovery = recovery_owns_cmd(recorded_v, recorded_w)
        if not math.isnan(recorded_w) and not owned_by_recovery:
            errors.append(abs(cmd["angular_z"] - recorded_w))
        else:
            skipped += 1
        if t >= nxt:
            nxt = t + args.step
            print(f"{t:7.1f} {pos[0]:7.2f} {pos[1]:7.2f} {math.degrees(yaw):7.1f} "
                  f"{cmd['alpha_deg']:7.1f} {cmd['angular_z']:8.3f} {recorded_w:10.3f}   "
                  f"{'Y' if cmd['saturated'] else '.'}    {'Y' if cmd['rotate_in_place'] else '.'}"
                  f"{'   [escape owns /cmd_vel]' if owned_by_recovery else ''}")

    if args.validate and errors:
        errors.sort()
        n = len(errors)
        print(f"\nreconstruction vs recorded /cmd_vel over {n} samples "
              f"({skipped} skipped as escape-owned):")
        print(f"  median |error| {errors[n // 2]:.4f} rad/s   90th pct {errors[int(n * 0.9)]:.4f}"
              f"   max {errors[-1]:.4f}")
        print("  (a floor of ~0.02-0.05 is expected: the follower steers on the EKF estimate, "
              "this reconstructs from ground truth, and the two differ by 0.13-0.20 m here)")


if __name__ == "__main__":
    main()
