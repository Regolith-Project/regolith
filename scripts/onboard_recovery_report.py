#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Score the onboard-vs-oracle recovery campaign.

The question is not "how many escapes fired" but **how many the rover could tell
had worked**. In the `oracle` arm those are the same number by construction: the
verdict is read from /ground_truth/pose, so it is right every time. In the
`onboard` arm the verdict comes from the rover's own EKF, and the escape's own
wheel-slip ZUPT can zero out the very motion it needs to see.

So this reports three things per arm:

  fired            escape maneuvers started
  believed freed   what the ROVER concluded - the number a real mission acts on
  actually freed   what ground truth says happened - scoring only

and, for the onboard arm, how often those last two disagree.

  onboard_recovery_report.py [campaign_dir]
"""
import json
import re
import sys
from pathlib import Path

FIRED = re.compile(r"STUCK RECOVERY #(\d+) \(escalation level (\d+)")
RESULT = re.compile(
    r"STUCK RECOVERY #(\d+) result: (.+?) moved ([\d.]+) m during the maneuver - "
    r"(FREED|STILL WEDGED)")
TRUTH = re.compile(r"\[scoring only: ground truth moved ([\d.]+) m")
FREED_BAR = 0.3   # escape_freed_threshold_m


def scan(run_dir: Path) -> dict:
    logs = list(run_dir.glob("*.log")) + list(run_dir.glob("**/*.log"))
    fired = believed = actually = disagree = 0
    levels = []
    for log in logs:
        for line in log.read_text(errors="replace").splitlines():
            m = FIRED.search(line)
            if m:
                fired += 1
                levels.append(int(m.group(2)))
                continue
            m = RESULT.search(line)
            if not m:
                continue
            rover_freed = m.group(4) == "FREED"
            believed += rover_freed
            t = TRUTH.search(line)
            if t:                                   # onboard arm: truth logged beside
                truth_freed = float(t.group(1)) >= FREED_BAR
                actually += truth_freed
                disagree += (truth_freed != rover_freed)
            else:
                # ORACLE ARM: the verdict was READ FROM ground truth, so "actually"
                # here is the same number by construction and is NOT an independent
                # confirmation. Counted for shape only; the report says so.
                actually += rover_freed
    summary = {}
    sj = run_dir / "summary.json"
    if sj.exists():
        try:
            loaded = json.loads(sj.read_text())
            # the harness writes a LIST of per-seed results; these cells run one seed
            summary = loaded[0] if isinstance(loaded, list) and loaded else loaded
        except Exception:
            pass
    return dict(fired=fired, believed=believed, actually=actually,
                disagree=disagree, levels=levels, summary=summary)


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "onboard_recovery_campaign")
    cells = sorted(d for d in root.iterdir() if d.is_dir() and d.name.startswith("seed"))
    if not cells:
        print(f"no run directories under {root}"); return

    print(f"{'cell':28s} {'fired':>6} {'believed':>9} {'actually':>9} {'wrong':>6}  verdict")
    totals = {}
    for c in cells:
        r = scan(c)
        arm = "onboard" if "_onboard_" in c.name else "oracle"
        t = totals.setdefault(arm, dict(fired=0, believed=0, actually=0, disagree=0, runs=0))
        for k in ("fired", "believed", "actually", "disagree"):
            t[k] += r[k]
        t["runs"] += 1
        v = r["summary"].get("verdict", "-") if r["summary"] else "(running)"
        print(f"{c.name:28s} {r['fired']:6d} {r['believed']:9d} {r['actually']:9d} "
              f"{r['disagree']:6d}  {v}")

    print()
    for arm, t in sorted(totals.items()):
        if not t["fired"]:
            print(f"{arm:8s}: no escape events yet ({t['runs']} run(s))"); continue
        print(f"{arm:8s} ({t['runs']} run(s)): {t['fired']} fired, "
              f"rover believed {t['believed']}/{t['fired']} freed "
              f"({100*t['believed']/t['fired']:.0f}%), "
              f"ground truth says {t['actually']}/{t['fired']} "
              f"({100*t['actually']/t['fired']:.0f}%)"
              + ("  [by construction - this arm READS the verdict from ground truth]"
                 if arm == "oracle" else ""))
        if t["disagree"]:
            print(f"{'':8s}  -> the rover was WRONG about {t['disagree']} of "
                  f"{t['fired']} escapes ({100*t['disagree']/t['fired']:.0f}%)")

    if {"oracle", "onboard"} <= totals.keys():
        o, n = totals["oracle"], totals["onboard"]
        if o["fired"] and n["fired"]:
            print(f"\nHEADLINE: with the oracle the rover knows it escaped "
                  f"{100*o['believed']/o['fired']:.0f}% of the time; "
                  f"onboard-only it knows {100*n['believed']/n['fired']:.0f}% "
                  f"- while actually escaping {100*n['actually']/n['fired']:.0f}%.")


if __name__ == "__main__":
    main()
