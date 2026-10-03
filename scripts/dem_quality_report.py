#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Summarise the live a-priori-map-quality campaign, per arm.

The verdict alone cannot answer the question this campaign asks. The offline
replay's central claim is not "a bad map gives a worse number" - it is that the
three defects fail in DIFFERENT WAYS, and the difference is visible only in what
the matcher did:

  detail loss      the margin gate fires harder, the node publishes FEWER fixes,
                   and the estimate degrades toward the unaided one. Safe.
  vertical error   slope error of ~sigma/L swamps the terrain's own relief. The
                   gate fires somewhat and not nearly enough.
  registration     the node publishes AS MANY fixes as on a perfect map, at full
                   confidence, every one of them displaced by the map's own
                   error - because nothing about the cost surface is wrong.

So published-fix count and margin distribution are the diagnostic, not a detail,
and a run that fails with zero fixes published means something entirely different
from one that fails with forty. Both would read as one number in a verdict table.

`node_activity` and `imu_vs_truth` are imported from terrain_relative_report.py
rather than re-written: they parse the node's own log lines, and two parsers for
one log format drift apart the moment either log line is reworded.
"""
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "terrain_relative_report", _HERE / "terrain_relative_report.py")
_trr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_trr)

# What the offline replay predicts for each arm, written down here so the live
# number is read against a prediction made BEFORE it, not against a memory of one
# formed after. Median final EKF error over the 25 replayed runs.
REPLAY_PREDICTION = {"perfect": 0.71, "degraded": 1.79, "noisy": 5.99}


def describe_map(cfg: dict) -> str:
    if cfg.get("perfect", True):
        return "perfect map"
    bits = []
    if cfg.get("post_m"):
        bits.append(f"{cfg['post_m']:.1f} m posts")
    if cfg.get("noise_m"):
        bits.append(f"{cfg['noise_m']:.2f} m vertical")
    if cfg.get("shift_m"):
        bits.append(f"{cfg['shift_m']:.1f} m shift")
    if cfg.get("prefilter_m"):
        bits.append(f"prefilter {cfg['prefilter_m']:.1f} m")
    return ", ".join(bits)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign_dir", nargs="?", default="dem_quality_campaign")
    args = parser.parse_args()

    root = Path(args.campaign_dir)
    arms = {}
    for run_dir in sorted(root.glob("seed*_*_rep*")):
        results = list(run_dir.glob("*_result.json"))
        if not results:
            print(f"{run_dir.name:30s} (running or aborted - no result)")
            continue
        r = json.loads(results[0].read_text())
        cfg = json.loads((run_dir / "run.json").read_text()).get("dem_quality", {})
        arm = run_dir.name.split("_")[1]
        act = _trr.node_activity(run_dir)
        sample = act.get("sampled_fixes", [])
        applied = act.get("corrections_applied", 0)
        margins = [f["margin"] for f in sample]
        arms.setdefault(arm, []).append((r, applied, margins))

        print(f"\n{run_dir.name}  [{describe_map(cfg)}]")
        print(f"    {r['verdict']:20s} divergence {r.get('divergence_m', float('nan')):6.3f} m, "
              f"travelled {r.get('gt_travelled_m', float('nan')):6.1f} m")
        # Accepted vs rejected is the diagnostic the whole campaign turns on: which
        # way a bad map fails is visible here and nowhere else in the run.
        rej = act.get("rejected_ambiguous", 0) + act.get("rejected_inconsistent", 0)
        rate = 100.0 * applied / max(applied + rej, 1)
        print(f"    corrections applied {applied} ({rate:.0f}% of attempts), "
              f"{act.get('poses_published', 0)} poses published, rejected "
              f"{act.get('rejected_ambiguous', 0)} ambiguous / "
              f"{act.get('rejected_inconsistent', 0)} inconsistent")
        if margins:
            print(f"    margin {min(margins):.1f}-{max(margins):.1f} "
                  f"(median {np.median(margins):.1f}, from a throttled sample of {len(margins)})")

    print("\n=== per arm ===")
    for arm, runs in sorted(arms.items()):
        div = [r.get("divergence_m") for r, *_ in runs
               if isinstance(r.get("divergence_m"), (int, float))]
        npass = sum(1 for r, *_ in runs if r["verdict"] == "PASS")
        pub = [n for _, n, _ in runs]
        if not div:
            continue
        pred = REPLAY_PREDICTION.get(arm)
        # The replay's number is a median FINAL EKF ERROR over 25 runs and this is
        # a live divergence over n<=2, so they are the same quantity measured two
        # ways, not the same statistic. Printed side by side to be read as an
        # order-of-magnitude check - which is all the replay ever claimed to be.
        pred_s = f"  [replay predicted ~{pred:.2f} m]" if pred else ""
        print(f"{arm:10s} n={len(div)}  PASS {npass}/{len(div)}  "
              f"divergence median {np.median(div):5.3f} m "
              f"(range {min(div):.3f}-{max(div):.3f})  "
              f"corrections applied {min(pub)}-{max(pub)}{pred_s}")


if __name__ == "__main__":
    main()
