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

def degraded_dem(seed, post_m=None, noise_m=0.0, shift_m=0.0, rng_seed=0,
                 prefilter_m=0.0):
    """The degradation itself now lives in the node (`trn.degrade_dem`).

    It was duplicated here while this script was the only consumer. It no longer
    is: `terrain_relative_node.py` takes the same three defects as ROS parameters
    so the live stack can be run on a degraded map, and the whole value of that
    live run is that it tests the prediction THIS script makes. Two copies of the
    model would let the prediction and the test drift apart without either
    changing visibly, so there is one copy and this calls it.
    """
    m = json.load(open(Path.home() / ".cache/regolith/worlds" / f"seed_{seed}" / "manifest.json"))
    gx, gy, W, res, _ = trn.terrain_gradients(
        m, post_m=post_m or 0.0, noise_m=noise_m, shift_m=shift_m, noise_seed=rng_seed,
        prefilter_m=prefilter_m)
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

# DETAIL LOSS alone. Survivable, and in the safe direction.
for post in (1.0, 2.0, 5.0):
    run_case(f"posts coarsened to {post:.0f} m", post_m=post)

# VERTICAL ERROR alone, at the native post spacing. This is the arm whose earlier
# version was mislabelled: the drawn field was smoothed and never renormalised, so
# "0.1 m rms" applied about 0.005 m and scored identically to coarsening-only. With
# the amplitude it claims, vertical error is the WORST of the three defects.
for noise in (0.02, 0.05, 0.10, 0.30):
    run_case(f"elevation noise {noise:.2f} m rms", noise_m=noise)

# VERTICAL ERROR at a realistic correlation length. A DTM's height error is
# correlated over the DTM's OWN posts, not over the finer grid it is resampled
# onto, and that length is what converts metres of height error into degrees of
# slope error. Coarser posts therefore PROTECT against the same vertical error -
# the one genuinely counter-intuitive result here.
for post, noise in ((2.0, 0.02), (2.0, 0.05), (2.0, 0.10),
                    (5.0, 0.10), (5.0, 0.30)):
    run_case(f"{post:.0f} m posts + {noise:.2f} m noise", post_m=post, noise_m=noise)

# THE MITIGATION. Same corrupted maps, but the rover smooths what it was given
# before differentiating it. Nothing about the map improves; only what the matcher
# does with it. If sigma/L is really the quantity that matters, lengthening L here
# should buy back most of what the noise arms lost.
for pre in (0.5, 1.0, 2.0):
    run_case(f"0.10 m noise, prefilter {pre:.1f} m", noise_m=0.10, prefilter_m=pre)
for pre in (1.0, 2.0):
    run_case(f"2 m posts + 0.10 m noise, prefilter {pre:.1f} m",
             post_m=2.0, noise_m=0.10, prefilter_m=pre)
run_case("perfect map, prefilter 1.0 m", prefilter_m=1.0)

# REGISTRATION. A pure bias, invisible to any confidence measure.
for shift in (1.0, 3.0):
    run_case(f"registration shift {shift:.0f} m (both axes)", shift_m=shift)
