#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Replay the SELF-CONTAINED track: exactly what terrain_relative_node publishes.

The node dead-reckons its own absolute position from signed wheel velocity and
IMU heading, corrects that track from terrain matches, and publishes it. It never
reads the filter's pose back. This replays that computation and scores the track
against ground truth - so it can fail the way the node can.
"""
import importlib.util, json, sys, glob, os
import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_NODE = (REPO_ROOT / "src/regolith.universe/planetary/regolith_bringup/scripts"
         / "terrain_relative_node.py")
_spec = importlib.util.spec_from_file_location("terrain_relative_node", _NODE)
trn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(trn)


def load_signals(path):
    """Signals at 10 Hz, with the EKF pose joined in from the trace where absent."""
    d = np.genfromtxt(path, delimiter=",", names=True)
    if "ekf_x" in d.dtype.names:
        return d, d["ekf_x"], d["ekf_y"]
    t = np.genfromtxt(str(path).replace("_signals.csv", "_trace.csv"),
                      delimiter=",", names=True)
    t = t[np.isfinite(t["ekf_x"]) & np.isfinite(t["t_s"])]
    ex = np.interp(d["t_s"], t["t_s"], t["ekf_x"], left=np.nan, right=np.nan)
    ey = np.interp(d["t_s"], t["t_s"], t["ekf_y"], left=np.nan, right=np.nan)
    return d, ex, ey

W_M      = float(os.environ.get("W", 15.0))
STRIDE   = float(os.environ.get("S", 0.2))
MAX_STEP = float(os.environ.get("MAXSTEP", 0.10))
SEARCH, STEP = 6.0, 0.25
MIN_MARGIN, CONS, MIN_N = 2.0, 1.5, 30

def replay(path, dem):
    gx, gy, W, res = dem
    d, ex, ey = load_signals(path)
    k = np.isfinite(ex) & np.isfinite(d["roll"]) & np.isfinite(d["sim_t"]) & np.isfinite(d["odom_vx"])
    d=d[k]; ex=ex[k]; ey=ey[k]
    dt = np.diff(d["sim_t"], prepend=d["sim_t"][0]); dt = np.clip(dt, 0, 1.0)
    step = d["odom_vx"] * dt                       # SIGNED along-heading step
    yaw  = d["yaw"]
    dxs, dys = step*np.cos(yaw), step*np.sin(yaw)  # world displacements
    trav = np.cumsum(np.abs(step))

    tx, ty = ex[0], ey[0]                          # track seeded from the filter once
    buf = []              # (dx, dy, yaw, roll, pitch, travelled)
    pend_x = pend_y = 0.0
    last_s = -1e9; prev=None; prev_s=None; pub=0; next_t = 0.0
    err_track=[]; err_raw=[]
    for i in range(len(d)):
        tx += dxs[i]; ty += dys[i]
        pend_x += dxs[i]; pend_y += dys[i]
        err_track.append(np.hypot(d["gt_x"][i]-tx, d["gt_y"][i]-ty))
        err_raw.append(np.hypot(d["gt_x"][i]-ex[i], d["gt_y"][i]-ey[i]))
        if abs(d["odom_vx"][i]) >= 0.03 and trav[i]-last_s >= STRIDE:
            buf.append((pend_x, pend_y, yaw[i], d["roll"][i], d["pitch"][i], trav[i]))
            pend_x = pend_y = 0.0; last_s = trav[i]
            while buf and trav[i]-buf[0][5] > W_M: buf.pop(0)
        # Match at the node's publish rate (1 Hz of SIM time), not at every
        # recorded sample - the node runs on a timer, and matching 10x more often
        # here models a different system as well as taking hours.
        if d["sim_t"][i] < next_t: continue
        next_t = d["sim_t"][i] + 1.0
        if len(buf) < MIN_N: continue
        if buf[-1][5]-buf[0][5] < W_M*0.5: continue
        a = np.array(buf)
        xs, ys = trn.reconstruct_window(a[:,0], a[:,1], tx, ty)
        dx, dy, mg = trn.match_offset(gx, gy, W, res, xs, ys, a[:,2], a[:,3], a[:,4], SEARCH, STEP)
        if mg < MIN_MARGIN: prev=(dx,dy); prev_s=trav[i]; continue
        if prev is None: prev=(dx,dy); prev_s=trav[i]; continue
        if prev_s is not None and trav[i]-prev_s >= W_M*0.5:
            if np.hypot(dx-prev[0], dy-prev[1]) > CONS:
                prev=(dx,dy); prev_s=trav[i]; continue
            prev=(dx,dy); prev_s=trav[i]
        dx, dy = trn.clamp_correction(dx, dy, MAX_STEP)
        tx += dx; ty += dy; pub += 1
    return err_raw[-1], err_track[-1], max(err_track), pub

SPECS = (("planned_path_campaign/seed7_paths_rep*/seed_7_signals.csv", 7),
         ("wheel_slip_generalization_campaign/seed123_*/seed_123_signals.csv", 123),
         ("wheel_slip_generalization_campaign/seed55_fixed_rep*/seed_55_signals.csv", 55),
         ("wheel_slip_generalization_campaign/seed7_fixed_rep*/seed_7_signals.csv", 7))
out=[]
for pattern, seed in SPECS:
    dem = trn.terrain_gradients(json.load(open(
        Path.home() / ".cache/regolith/worlds" / f"seed_{seed}" / "manifest.json")))
    rows=[replay(f, dem) for f in sorted(glob.glob(pattern))]
    a=np.array(rows)
    print(f"  seed {seed:3d} ({len(rows):2d} runs): raw med {np.median(a[:,0]):6.2f} -> track med "
          f"{np.median(a[:,1]):5.2f} m | worst-in-run med {np.median(a[:,2]):5.2f} max {a[:,2].max():6.2f}", flush=True)
    out += rows
a=np.array(out)
print(f"\nMAXSTEP={MAX_STEP} W={W_M}: raw median {np.median(a[:,0]):.2f} -> track median {np.median(a[:,1]):.2f} m, "
      f"improved {(a[:,1]<a[:,0]).sum()}/{len(a)}, over 1.5 m: {(a[:,0]>1.5).sum()} -> {(a[:,1]>1.5).sum()}, "
      f"worst-final {a[:,1].max():.2f}, worst-excursion {a[:,2].max():.2f} m")
