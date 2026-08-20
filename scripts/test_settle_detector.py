# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""The watcher must record where the rover STOPPED, not only where it first
crossed the bar.

A seed 7 run passed acceptance at 1.47 m while still driving - it never
published /goal_reached - so the experiment that existed to measure the
stopping tolerance never observed a stop. "Passed through the bar" and "stopped
inside it" are different claims about a rover, and M4 means the second.

These run the detector directly rather than against a simulator, because the
settle phase only ever executes on a PASS: a bug in it costs exactly the runs
worth having, an hour at a time.

    python3 -m pytest scripts/test_settle_detector.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from m4_acceptance import (  # noqa: E402
    SETTLE_BUDGET_SIM_S,
    SETTLE_MOVE_M,
    SETTLE_QUIET_SIM_S,
    SettleDetector,
)

SIM_TIMEOUT_S = 1800.0
WALL_TIMEOUT_S = 10800.0
STEP_S = 1.0  # the watcher ticks at 1 Hz


def detector(verdict_sim_s=600.0, gt_xy=(0.0, 0.0)) -> SettleDetector:
    return SettleDetector(verdict_sim_s, gt_xy, SIM_TIMEOUT_S, WALL_TIMEOUT_S)


def test_a_rover_still_driving_is_not_settled():
    """The case that motivated this: crossing the bar at speed and driving on."""
    d = detector()
    sim = 600.0
    for i in range(60):
        sim += STEP_S
        # 0.2 m/s of genuine progress, well above the noise floor.
        assert d.update((0.2 * i, 0.0), sim, sim, False) is None


def test_stopping_is_detected_after_the_quiet_window():
    d = detector()
    sim = 600.0
    assert d.update((0.0, 0.0), sim, sim, False) is None
    while sim - 600.0 <= SETTLE_QUIET_SIM_S:
        sim += STEP_S
        outcome = d.update((0.0, 0.0), sim, sim, False)
    assert outcome == "rover stopped moving"


def test_jitter_below_the_noise_floor_still_counts_as_stopped():
    """A parked rover's ground-truth pose wobbles; that is not driving."""
    d = detector()
    sim, outcome = 600.0, None
    for i in range(int(SETTLE_QUIET_SIM_S) + 5):
        sim += STEP_S
        wobble = (SETTLE_MOVE_M / 2) * (1 if i % 2 else -1)
        outcome = d.update((wobble, 0.0), sim, sim, False) or outcome
    assert outcome == "rover stopped moving"


def test_creeping_faster_than_the_noise_floor_is_not_stopped():
    """The other side of that threshold: real, if slow, motion keeps it open."""
    d = detector()
    sim, x = 600.0, 0.0
    for _ in range(int(SETTLE_QUIET_SIM_S) + 5):
        sim += STEP_S
        x += SETTLE_MOVE_M * 2
        assert d.update((x, 0.0), sim, sim, False) is None


def test_the_rovers_own_arrival_claim_settles_immediately():
    d = detector()
    assert d.update((5.0, 5.0), 601.0, 601.0, True) == "rover declared arrival"


def test_an_endlessly_circling_rover_is_not_waited_on_forever():
    """If the follower orbits instead of stopping, the settle phase still ends -
    on its own budget - rather than holding the run open."""
    import math

    d = detector()
    sim, outcome = 600.0, None
    for i in range(10000):
        sim += STEP_S
        angle = i * 0.1
        outcome = d.update((math.cos(angle), math.sin(angle)), sim, sim, False)
        if outcome:
            break
    assert outcome == "settle budget spent"
    assert sim - 600.0 <= SETTLE_BUDGET_SIM_S + 2 * STEP_S


def test_a_dead_simulator_ends_the_wait_on_the_wall_clock():
    """Sim time freezes when the simulator dies, so every sim-time rule in here
    is unreachable - which is how a watcher once spent 2 h 50 min logging a
    rover that was no longer being simulated. The wall-clock branch is the one
    that has to fire, and it is checked against real seconds for that reason."""
    d = detector()
    frozen_sim = 600.0
    assert d.update((0.0, 0.0), frozen_sim, 100.0, False) is None
    # Position frozen too, but the quiet window cannot elapse in frozen sim time.
    assert d.update((0.0, 0.0), frozen_sim, WALL_TIMEOUT_S - 1, False) is None
    assert d.update((0.0, 0.0), frozen_sim, WALL_TIMEOUT_S + 1, False) == "wall clock cap"


def test_the_run_budget_ends_the_wait():
    d = detector(verdict_sim_s=SIM_TIMEOUT_S - 10.0)
    moving = 0.0
    sim = SIM_TIMEOUT_S - 10.0
    outcome = None
    while outcome is None and sim < SIM_TIMEOUT_S + 60:
        sim += STEP_S
        moving += 1.0  # keep it driving so the quiet rule cannot fire
        outcome = d.update((moving, 0.0), sim, sim, False)
    assert outcome == "run budget spent"
