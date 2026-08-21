#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Before/after campaign for the wheel_slip_node signature-2 retirement (PROGRESS.md,
# "Root-caused: the benign-ground traction stall was never a stall" / "Fixed: signature
# 2 retired"). One live repro confirmed the specific bug is gone; this measures whether
# it actually narrows seed 42's run-to-run divergence/stuck-event variance, which was
# flagged as a plausible but unmeasured target (seed 42: 8 wedges in one banked arm, 5
# in another, same seed, same terrain, unexplained at the time).
#
# Same build both arms (a single legacy_rigid_body_signature launch argument toggles
# the behaviour - see hello_moon.launch.py), same discipline as the goal_tolerance_m
# campaign: interleaved by rep so an interruption leaves matched pairs, goal_tolerance_m
# pinned explicitly (m4_acceptance.py's own --goal-tolerance-m default, 1.0, is stale
# against the shipped 0.35 - passing it here so a comparison never silently reverts).
#
# Each cell is skipped if it already has a summary.json, so this is safe to re-run
# after an interruption.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:?usage: wheel_slip_ab_campaign.sh <output-dir> [reps]}"
REPS="${2:-3}"

mkdir -p "${OUT}"
echo "=== wheel-slip A/B campaign -> ${OUT} (${REPS} reps/arm, seed 42) ==="
date

run_cell() {
  local arm="$1" legacy_flag="$2" rep="$3"
  local run_dir="${OUT}/seed42_${arm}_rep${rep}"
  if [[ -f "${run_dir}/summary.json" ]]; then
    echo "--- ${arm} rep ${rep}: done, skipping ---"
    return
  fi
  echo ""
  echo "=== seed 42, ${arm}, rep ${rep} - $(date +%H:%M:%S) ==="
  python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
    --seeds 42 --goal-tolerance-m 0.35 ${legacy_flag} --out "${run_dir}"
  echo "=== finished $(date +%H:%M:%S) ==="
  # A surviving server shares gz's partition with the next run whatever
  # ROS_DOMAIN_ID says - see PROGRESS.md.
  pkill -KILL -f "gz[ ]sim.*regolith_moon" 2>/dev/null
  pkill -KILL -f "gz[ ]sim.*worlds/seed_" 2>/dev/null
  sleep 10
}

for rep in $(seq 1 "${REPS}"); do
  run_cell legacy "--legacy-rigid-body-signature" "${rep}"
  run_cell fixed  "" "${rep}"
done

echo ""
echo "=== wheel-slip A/B campaign finished - $(date) ==="
