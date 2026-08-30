#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""How good does the a-priori DEM have to be? Closed-loop replay against degraded maps.

terrain_relative_node.py matches against the generator's own heightmap, read
exactly - a perfect map, which no mission has. This answers what happens when it
is not perfect, by replaying the same 25 recorded runs against deliberately
degraded copies. No simulation time; run it from the repo root with the workspace
sourced.

Three degradations, applied separately because they fail differently:

  COARSENING   posts resampled to 1/2/5 m and back. Removes fine relief, which is
               most of what the matcher reads.
  NOISE        elevation error added at the post scale. Corrupts relief rather
               than removing it.
  REGISTRATION the map is correct but sits in the wrong place. This one is a pure
               BIAS, not a loss of information, and it is the one that bites: the
               matcher faithfully reports where the rover is on a map that is
               itself displaced, and hands that displacement straight to the EKF.

Note on the registration case: goals here are world-frame points, so a shifted
map shifts the estimate against a goal that did not move. A mission whose targets
are picked FROM the same orbital map would see part of that offset cancel, so
treat this arm as the pessimistic bound rather than the expected behaviour.
"""
import glob
import importlib.util
import json
from pathlib import Path

import numpy as np
from regolith_costmap.costmap_node import load_heightmap
from scipy import ndimage

REPO_ROOT = Path(__file__).resolve().parents[1]
_NODE = (REPO_ROOT / "src/regolith.universe/planetary/regolith_bringup/scripts"
         / "terrain_relative_node.py")
_spec = importlib.util.spec_from_file_location("terrain_relative_node", _NODE)
trn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(trn)


def load_signals(path):
    """Signals at 10 Hz, with the EKF pose joined in from the trace where absent.

    Runs recorded before the ekf_x/ekf_y columns were added still carry the EKF
    pose in their trace file at a lower rate, so they are usable here rather than
    being dropped - which is most of the seed 55 and 123 sample.
    """
    d = np.genfromtxt(path, delimiter=",", names=True)
    if "ekf_x" in d.dtype.names:
        return d, d["ekf_x"], d["ekf_y"]
    t = np.genfromtxt(str(path).replace("_signals.csv", "_trace.csv"),
                      delimiter=",", names=True)
    t = t[np.isfinite(t["ekf_x"]) & np.isfinite(t["t_s"])]
    ex = np.interp(d["t_s"], t["t_s"], t["ekf_x"], left=np.nan, right=np.nan)
    ey = np.interp(d["t_s"], t["t_s"], t["ekf_y"], left=np.nan, right=np.nan)
    return d, ex, ey

WINDOW_M, UPDATE_M, STRIDE_M, SEARCH_M, STEP_M = 15.0, 6.0, 0.2, 6.0, 0.25
MIN_MARGIN, CONSISTENCY_M, MIN_SAMPLES = 2.0, 1.5, 30

def degraded_dem(seed, post_m=None, noise_m=0.0, shift_m=0.0, rng_seed=0):
    m = json.load(open(Path.home() / ".cache/regolith/worlds" / f"seed_{seed}" / "manifest.json"))
    dem = load_heightmap(m)
    W = float(m["world_size_m"]); res = W/(dem.shape[0]-1)
    if post_m:            # coarser posts, then back to the same grid: information lost
        factor = post_m/res
        small = ndimage.zoom(dem, 1.0/factor, order=1)
        dem = ndimage.zoom(small, np.array(dem.shape)/np.array(small.shape), order=1)
    if noise_m:
        rng = np.random.default_rng(rng_seed)
        dem = dem + ndimage.gaussian_filter(
            rng.normal(0, noise_m, dem.shape), sigma=max(post_m or res, res)/res)
    if shift_m:           # registration error: the map is right, but not where it says
        dem = ndimage.shift(dem, (shift_m/res, shift_m/res), order=1, mode="nearest")
    gy, gx = np.gradient(dem, res)
    return gx, gy, W, res

def replay(path, dem):
    gx, gy, W, res = dem
    d, ex, ey = load_signals(path)
    mv = np.hypot(np.diff(d["gt_x"],prepend=d["gt_x"][0]), np.diff(d["gt_y"],prepend=d["gt_y"][0]))>0
    k0 = mv & np.isfinite(ex) & np.isfinite(d["roll"]); d=d[k0]; ex=ex[k0]; ey=ey[k0]
    s = np.cumsum(np.hypot(np.diff(ex, prepend=ex[0]), np.diff(ey, prepend=ey[0])))
    fast = d["gt_speed"] >= 0.03
    keep, last = [], -1e9
    for i in range(len(s)):
        if fast[i] and s[i]-last >= STRIDE_M: keep.append(i); last=s[i]
    keep = np.array(keep)
    if len(keep) < MIN_SAMPLES: return None
    cx=cy=0.0; prev=None; pub=0; next_fix=WINDOW_M; raw=corr=None
    for i in keep:
        raw = np.hypot(d["gt_x"][i]-ex[i], d["gt_y"][i]-ey[i])
        corr = np.hypot(d["gt_x"][i]-(ex[i]+cx), d["gt_y"][i]-(ey[i]+cy))
        if s[i] < next_fix: continue
        win = keep[(s[keep] >= s[i]-WINDOW_M) & (s[keep] <= s[i])]
        next_fix = s[i] + UPDATE_M
        if len(win) < MIN_SAMPLES: continue
        dx, dy, mg = trn.match_offset(gx, gy, W, res, ex[win]+cx, ey[win]+cy,
                                      d["yaw"][win], d["roll"][win], d["pitch"][win],
                                      SEARCH_M, STEP_M)
        if mg < MIN_MARGIN: prev=(dx,dy); continue
        if prev is None: prev=(dx,dy); continue
        if np.hypot(dx-prev[0], dy-prev[1]) > CONSISTENCY_M: prev=(dx,dy); continue
        prev=(dx,dy); cx+=dx; cy+=dy; pub+=1
    return raw, corr, pub

SPECS = (("planned_path_campaign/seed7_paths_rep*/seed_7_signals.csv", 7),
         ("wheel_slip_generalization_campaign/seed123_*/seed_123_signals.csv", 123),
         ("wheel_slip_generalization_campaign/seed55_fixed_rep*/seed_55_signals.csv", 55),
         ("wheel_slip_generalization_campaign/seed7_fixed_rep*/seed_7_signals.csv", 7))

def run_case(label, **kw):
    out = []
    for pattern, seed in SPECS:
        dem = degraded_dem(seed, **kw)
        for f in sorted(glob.glob(pattern)):
            r = replay(f, dem)
            if r: out.append(r)
    a = np.array(out)
    print(f"{label:38s} n={len(a):2d}  final err median {np.median(a[:,0]):5.2f} -> "
          f"{np.median(a[:,1]):5.2f} m | over 1.5 m: {(a[:,0]>1.5).sum():2d} -> {(a[:,1]>1.5).sum():2d} "
          f"| fixes {int(a[:,2].sum()):3d}", flush=True)

print("=== a-priori DEM quality vs closed-loop replay (25 runs, seeds 7/55/123) ===")
run_case("perfect map (as shipped)")
for post in (1.0, 2.0, 5.0):
    run_case(f"posts coarsened to {post:.0f} m", post_m=post)
for noise in (0.1, 0.3):
    run_case(f"elevation noise {noise:.1f} m rms", noise_m=noise, post_m=2.0)
for shift in (1.0, 3.0):
    run_case(f"registration shift {shift:.0f} m (both axes)", shift_m=shift)
