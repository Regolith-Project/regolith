#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the campaign-log parsers in terrain_relative_report.py.

These exist because a stale regex here does not raise, does not warn, and does not
produce an obviously wrong number - it produces ZERO, which is indistinguishable
from a matcher that rejected every window, and that is a conclusion someone will
act on. The node's published-fix line was reworded once and this parser reported
"fixes published 0" for every run afterwards, including runs that published
fourteen corrections.

The fixtures below are copied verbatim from real launch logs. Both wordings are
pinned, because logs in both forms are on disk and a campaign report has to read
its own history.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "terrain_relative_report", Path(__file__).resolve().parent / "terrain_relative_report.py")
trr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(trr)

CURRENT = (
    "[terrain_relative_node.py-5] [INFO] [1756600000.000000000] "
    "[regolith_terrain_relative]: Terrain correction #3 at 41.7 m travelled: "
    "(+0.42, -0.18) m, margin 3.71, 75 samples, 12 poses published "
    "(rejected so far: 9 ambiguous, 1 inconsistent)"
)
LEGACY = (
    "[terrain_relative_node.py-5] [INFO] [1756500000.000000000] "
    "[regolith_terrain_relative]: Terrain fix #2 at 28.3 m travelled: "
    "correction (-0.31, +0.05) m, margin 2.64"
)
REJECTS = (
    "[regolith_terrain_relative]: Terrain fix rejected: margin 1.42 < 2.0 - this stretch "
    "of terrain does not determine position (74 samples over 15.0 m)\n"
    "[regolith_terrain_relative]: Terrain fix rejected: disagrees with the previous "
    "window by 2.90 m (> 1.5); offset now (-1.20, +0.40), was (+1.10, +0.30)"
)


def _activity(tmp_path, text):
    (tmp_path / "seed_123_launch.log").write_text(text)
    return trr.node_activity(tmp_path)


def test_parses_the_current_wording(tmp_path):
    act = _activity(tmp_path, CURRENT)
    assert len(act["fixes"]) == 1
    f = act["fixes"][0]
    assert (f["n"], f["travelled_m"], f["dx"], f["dy"], f["margin"]) == (3, 41.7, 0.42, -0.18, 3.71)


def test_still_parses_the_legacy_wording(tmp_path):
    """Campaign logs in the old form are on disk and must stay readable."""
    act = _activity(tmp_path, LEGACY)
    assert len(act["fixes"]) == 1
    assert act["fixes"][0]["dx"] == -0.31


def test_counts_both_rejection_kinds(tmp_path):
    act = _activity(tmp_path, REJECTS)
    assert act["fixes"] == []
    assert act["rejected_ambiguous"] == 1
    assert act["rejected_inconsistent"] == 1


def test_a_run_with_corrections_is_never_reported_as_zero(tmp_path):
    """The exact failure that motivated this file: real content, empty count."""
    act = _activity(tmp_path, "\n".join([CURRENT, LEGACY, REJECTS]))
    assert len(act["fixes"]) == 2, "a log containing published corrections reported none"


def test_totals_come_from_the_counters_not_the_line_count(tmp_path):
    """The bug that mattered most: every one of these log calls is throttled.

    The correction line is emitted once per `report_every_m` of travel and both
    rejection lines once per 30 s, so a log holds a SAMPLE of the activity. Counting
    lines reported 14 corrections on a run that applied 61, and 28 ambiguous
    rejections on a run that counted 195 - an accept rate of 33% where the truth was
    24%. The node carries the real running totals inside the correction line.
    """
    text = "\n".join([
        REJECTS,
        "[regolith_terrain_relative]: Terrain correction #7 at 20.0 m travelled: "
        "(+0.50, +0.10) m, margin 4.00, 74 samples, 90 poses published "
        "(rejected so far: 30 ambiguous, 1 inconsistent)",
        "[regolith_terrain_relative]: Terrain correction #61 at 94.0 m travelled: "
        "(+0.06, +0.03) m, margin 19.72, 74 samples, 692 poses published "
        "(rejected so far: 195 ambiguous, 2 inconsistent)",
    ])
    act = _activity(tmp_path, text)
    assert act["corrections_applied"] == 61, "counted log lines instead of corrections"
    assert act["poses_published"] == 692
    assert act["rejected_ambiguous"] == 195, "counted throttled rejection lines"
    assert act["rejected_inconsistent"] == 2
    assert len(act["sampled_fixes"]) == 2  # the sample stays available, labelled as one
    assert act["counts_are_sampled"] is False


def test_falls_back_to_line_counting_when_nothing_was_ever_published(tmp_path):
    """A run with no correction line has no counters - there the lines ARE the total."""
    act = _activity(tmp_path, REJECTS)
    assert act["corrections_applied"] == 0
    assert act["rejected_ambiguous"] == 1
    assert act["counts_are_sampled"] is True
