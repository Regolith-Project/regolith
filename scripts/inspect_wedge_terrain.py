#!/usr/bin/env python3
"""Inspect the local collision-slab surface at the recorded seed-42 traction-stall
wedge points, without launching Gazebo. Reuses the exact same terrain generation
pipeline (config, heightmap, smoothed-surface, box-collision builder) that the real
world uses, so the numbers here are the numbers physics actually sees."""
import numpy as np
from regolith_terrain_gen.config import TerrainConfig
from regolith_terrain_gen.heightmap import build_heightmap, _build_smoothed_surface

cfg = TerrainConfig(seed=42)
rng = np.random.default_rng(cfg.seed)
raw_heightmap, heightmap, craters, elevation_lookup = build_heightmap(cfg, rng)
grid = _build_smoothed_surface(raw_heightmap, cfg)

rows_blocks, cols_blocks = grid["rows_blocks"], grid["cols_blocks"]
cell_size_m = grid["cell_size_m"]
xs, ys = grid["xs"], grid["ys"]
surface, grad_x, grad_y = grid["surface"], grid["grad_x"], grid["grad_y"]

print(f"cell_size_m = {cell_size_m:.4f}, rows_blocks={rows_blocks}, cols_blocks={cols_blocks}")
print(f"grad_x range [{grad_x.min():.4f}, {grad_x.max():.4f}]  grad_y range [{grad_y.min():.4f}, {grad_y.max():.4f}]")

wedges = {
    "wedge1 (6.20, 6.20)": (6.20, 6.20),
    "wedge2 (6.42, 5.49)": (6.42, 5.49),
    "wedge3 (5.16, 5.57)": (5.16, 5.57),
    "spawn (0,0)": (0.0, 0.0),
}


def cell_index(x, y):
    col = int(np.argmin(np.abs(xs - x)))
    row = int(np.argmin(np.abs(ys - y)))
    return row, col


for name, (x, y) in wedges.items():
    row, col = cell_index(x, y)
    h0 = surface[row, col]
    gx, gy = grad_x[row, col], grad_y[row, col]
    slope_deg = np.degrees(np.arctan(np.hypot(gx, gy)))
    elev = elevation_lookup(x, y)
    # distance to nearest cell centre / seam
    dx = x - xs[col]
    dy = y - ys[row]
    dist_to_centre = np.hypot(dx, dy)
    dist_to_seam = cell_size_m / 2.0 - max(abs(dx), abs(dy))
    # neighbour height jump (raw, pre-smoothing tilt-plane top-of-slab value at the
    # shared edge, both sides) - the actual quantity that produces a step a wheel feels
    neighbour_deltas = []
    for drow, dcol in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        r2, c2 = row + drow, col + dcol
        if 0 <= r2 < rows_blocks and 0 <= c2 < cols_blocks:
            # height of THIS cell's tilted plane evaluated at the shared edge midpoint,
            # vs the NEIGHBOUR's plane evaluated at the same point
            edge_x = (xs[col] + xs[c2]) / 2.0
            edge_y = (ys[row] + ys[c2]) / 2.0
            h_this = h0 + gx * (edge_x - xs[col]) + gy * (edge_y - ys[row])
            h_nbr = surface[r2, c2] + grad_x[r2, c2] * (edge_x - xs[c2]) + grad_y[r2, c2] * (
                edge_y - ys[r2]
            )
            neighbour_deltas.append(abs(h_this - h_nbr))
    print(
        f"{name}: cell({row},{col}) h0={h0:.3f} elev_lookup={elev:.3f} "
        f"slope={slope_deg:.2f}deg dist_to_centre={dist_to_centre:.2f} "
        f"dist_to_seam={dist_to_seam:.2f} max_lip={max(neighbour_deltas):.3f}"
    )
