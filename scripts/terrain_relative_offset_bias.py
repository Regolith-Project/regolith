#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Is a noisy map's error zero-mean, and a shifted map's a bias? Measured directly.

The live noisy arm survived where the replay said it would not, and the proposed
reason is that the EKF averages down zero-mean fix error while the replay
integrates each fix at full weight. That explanation stands or falls on a
distribution, not on a run: for the SAME windows, compare the offset matched
against a degraded DEM with the offset matched against the perfect one.

  zero-mean  -> mean error ~0, spread > 0. The filter can average it away.
  bias       -> mean error ~ the map's own displacement. Nothing averages it away.
"""
import glob, importlib.util, json
from pathlib import Path
import numpy as np

R = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "trn", R / "src/regolith.universe/planetary/regolith_bringup/scripts/terrain_relative_node.py")
trn = importlib.util.module_from_spec(spec); spec.loader.exec_module(trn)

W_M, STRIDE, SEARCH, STEP, MIN_SAMP = 15.0, 0.2, 6.0, 0.25, 30

def windows(path):
    d = np.genfromtxt(path, delimiter=",", names=True)
    if "ekf_x" in d.dtype.names:
        ex, ey = d["ekf_x"], d["ekf_y"]
    else:
        t = np.genfromtxt(str(path).replace("_signals.csv", "_trace.csv"),
                          delimiter=",", names=True)
        t = t[np.isfinite(t["ekf_x"]) & np.isfinite(t["t_s"])]
        ex = np.interp(d["t_s"], t["t_s"], t["ekf_x"], left=np.nan, right=np.nan)
        ey = np.interp(d["t_s"], t["t_s"], t["ekf_y"], left=np.nan, right=np.nan)
    k = np.isfinite(ex) & np.isfinite(d["roll"]) & (d["gt_speed"] >= 0.03)
    d, ex, ey = d[k], ex[k], ey[k]
    s = np.cumsum(np.hypot(np.diff(ex, prepend=ex[0]), np.diff(ey, prepend=ey[0])))
    keep, last = [], -1e9
    for i in range(len(s)):
        if s[i] - last >= STRIDE: keep.append(i); last = s[i]
    keep = np.array(keep)
    out, nxt = [], W_M
    for i in keep:
        if s[i] < nxt: continue
        w = keep[(s[keep] >= s[i]-W_M) & (s[keep] <= s[i])]
        nxt = s[i] + 6.0
        if len(w) >= MIN_SAMP:
            out.append((ex[w], ey[w], d["yaw"][w], d["roll"][w], d["pitch"][w]))
    return out

CASES = {"0.10 m vertical noise": dict(post_m=2.0, noise_m=0.10),
         "1 m registration shift": dict(shift_m=1.0),
         "3 m registration shift": dict(shift_m=3.0)}

for seed, pattern in ((123, "wheel_slip_generalization_campaign/seed123_*/seed_123_signals.csv"),
                      (7, "planned_path_campaign/seed7_paths_rep*/seed_7_signals.csv")):
    man = json.load(open(Path.home()/".cache/regolith/worlds"/f"seed_{seed}"/"manifest.json"))
    clean = trn.terrain_gradients(man)[:4]
    wins = [w for f in sorted(glob.glob(pattern))[:4] for w in windows(f)]
    print(f"\nseed {seed}: {len(wins)} windows")
    for label, kw in CASES.items():
        bad = trn.terrain_gradients(man, **kw)[:4]
        errs = []
        for xs, ys, yaw, roll, pitch in wins:
            a = trn.match_offset(*clean, xs, ys, yaw, roll, pitch, SEARCH, STEP)
            b = trn.match_offset(*bad, xs, ys, yaw, roll, pitch, SEARCH, STEP)
            errs.append((b[0]-a[0], b[1]-a[1]))
        e = np.array(errs)
        mean = np.hypot(*e.mean(axis=0))
        spread = np.hypot(e[:,0].std(), e[:,1].std())
        print(f"  {label:24s} mean error ({e[:,0].mean():+5.2f}, {e[:,1].mean():+5.2f}) "
              f"|mean| {mean:4.2f} m, spread {spread:4.2f} m, |mean|/spread {mean/max(spread,1e-9):5.2f}")
