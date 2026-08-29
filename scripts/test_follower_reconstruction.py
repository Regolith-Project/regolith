#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for reconstruct_follower_target.py.

The reconstruction is only worth anything if it is the SAME control law
pure_pursuit_node runs. These tests pin the three behaviours the fixed-arm
analysis depends on - the lookahead walk, the 0.30 rad/s saturation, and the
rotate-in-place branch - and cross-check the constants against the node's own
declared defaults, so a change there fails here rather than silently making
every reconstructed alpha wrong.
"""

import importlib.util
import math
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
NODE = (HERE.parent / "src/regolith.universe/planetary/regolith_vehicle_interface"
        / "regolith_vehicle_interface/pure_pursuit_node.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


R = _load("reconstruct_follower_target", HERE / "reconstruct_follower_target.py")


def test_constants_match_the_node_they_reconstruct():
    """The reconstruction hard-codes the follower's defaults; catch them drifting."""
    src = NODE.read_text()

    def declared(name):
        m = re.search(rf'declare_parameter\("{name}",\s*([0-9.]+)\)', src)
        assert m, f"{name} not found in {NODE.name}"
        return float(m.group(1))

    assert R.LOOKAHEAD_M == declared("lookahead_distance_m")
    assert R.MAX_ANGULAR == declared("max_angular_velocity")
    assert R.BASE_SPEED == declared("base_speed_mps")
    # The gain and the rotate-in-place threshold are literals in _control_step.
    assert "np.clip(1.5 * alpha" in src
    assert "abs(alpha) > np.pi / 6" in src


def test_lookahead_walks_forward_from_the_nearest_waypoint():
    # 0.5 m spacing along +x; from the origin, 1.5 m of lookahead lands on index 3.
    path = [(i * 0.5, 0.0) for i in range(10)]
    target, idx, deviation = R.follower_target(path, (0.0, 0.0))
    assert idx == 3
    assert target == (1.5, 0.0)
    assert deviation == 0.0


def test_lookahead_starts_from_the_nearest_point_not_the_path_start():
    path = [(i * 0.5, 0.0) for i in range(10)]
    _, idx, deviation = R.follower_target(path, (2.0, 0.3))
    assert idx == 7  # nearest is index 4, plus 1.5 m of walk
    assert abs(deviation - 0.3) < 1e-9


def test_straight_ahead_gives_no_steering_and_full_speed():
    path = [(i * 0.5, 0.0) for i in range(10)]
    cmd = R.follower_command(path, (0.0, 0.0), yaw=0.0)
    assert abs(cmd["alpha_deg"]) < 1e-9
    assert abs(cmd["angular_z"]) < 1e-9
    assert abs(cmd["linear_x"] - R.BASE_SPEED) < 1e-9
    assert not cmd["saturated"] and not cmd["rotate_in_place"]


def test_angular_saturates_at_the_limit():
    """The marker the fixed-arm split turns on: |cmd_w| pinned at 0.30 rad/s."""
    path = [(i * 0.5, 0.0) for i in range(10)]
    # 15 deg of heading error: 1.5 * 0.262 = 0.393, above the 0.30 limit.
    cmd = R.follower_command(path, (0.0, 0.0), yaw=math.radians(-15.0))
    assert cmd["saturated"]
    assert abs(cmd["angular_z"] - R.MAX_ANGULAR) < 1e-9
    assert not cmd["rotate_in_place"]  # 15 deg is under the 30 deg branch
    assert cmd["linear_x"] > 0.0
    # Saturation hides the heading error in /cmd_vel but not in the reconstruction.
    harder = R.follower_command(path, (0.0, 0.0), yaw=math.radians(-25.0))
    assert harder["angular_z"] == cmd["angular_z"]
    assert harder["alpha_deg"] > cmd["alpha_deg"]


def test_rotate_in_place_past_thirty_degrees():
    path = [(i * 0.5, 0.0) for i in range(10)]
    cmd = R.follower_command(path, (0.0, 0.0), yaw=math.radians(-45.0))
    assert cmd["rotate_in_place"]
    assert cmd["linear_x"] == 0.0
    assert cmd["saturated"]


def test_last_waypoint_steers_at_the_real_goal():
    """Mirrors the node: past the path's end, steer at the commanded goal."""
    path = [(0.0, 0.0), (1.0, 0.0)]
    goal = (2.0, 2.0)
    cmd = R.follower_command(path, (0.9, 0.0), yaw=0.0, goal_xy=goal)
    assert cmd["target_xy"] == list(goal)
    assert cmd["alpha_deg"] > 40.0


def test_path_in_force_picks_the_most_recent_replan():
    paths = [{"sim_t": 10.0, "seq": 0}, {"sim_t": 100.0, "seq": 1}, {"sim_t": 200.0, "seq": 2}]
    assert R.path_in_force(paths, 5.0) is None
    assert R.path_in_force(paths, 10.0)["seq"] == 0
    assert R.path_in_force(paths, 150.0)["seq"] == 1
    assert R.path_in_force(paths, 9999.0)["seq"] == 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))


def test_recovery_owned_samples_are_separable_from_follower_output():
    """The escape's own limits put it outside anything the follower can publish."""
    # flip_recovery_node's escape: reverse at -0.2 m/s, turn at 0.5 rad/s.
    assert R.recovery_owns_cmd(-0.2, 0.0)
    assert R.recovery_owns_cmd(0.0, 0.5)
    assert R.recovery_owns_cmd(0.0, -0.5)
    # Ordinary follower output, including a saturated turn, is not.
    assert not R.recovery_owns_cmd(0.2, 0.0)
    assert not R.recovery_owns_cmd(0.0, R.MAX_ANGULAR)
    assert not R.recovery_owns_cmd(0.0, -R.MAX_ANGULAR)
    assert not R.recovery_owns_cmd(0.06, 0.29)
    # A run without /cmd_vel recorded must not be silently treated as escape.
    assert not R.recovery_owns_cmd(float("nan"), float("nan"))
