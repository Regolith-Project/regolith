#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Does the signature-2 retirement (PROGRESS.md, "Root-caused: the benign-ground
# traction stall was never a stall" / "Fixed: signature 2 retired") generalize beyond
# seed 42, the one seed the A/B campaign (scripts/wheel_slip_ab_campaign.sh) actually
# measured? This is the same same-build A/B discipline generalized to any seed: a
# single legacy_rigid_body_signature launch argument toggles the retired behaviour back
# on for the "legacy" arm, so both arms come from one build - no build-vs-build
# comparison, which is what produced the visual-odometry confound earlier in this
# project. --record-signals is on for both arms so scripts/escape_window_divergence.py
# can be run against these runs too, as a cross-seed check of the escape-vs-ordinary
# per-radian-divergence-rate question that script was built to answer on seed 42.
#
# Each cell is skipped if it already has a summary.json, so this is safe to re-run
# after an interruption. Unlike wheel_slip_ab_campaign.sh this takes the seed as an
# argument - it is not hardcoded to 42.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:?usage: wheel_slip_generalization_campaign.sh <output-dir> <seed> [reps]}"
SEED="${2:?usage: wheel_slip_generalization_campaign.sh <output-dir> <seed> [reps]}"
REPS="${3:-1}"

mkdir -p "${OUT}"
echo "=== wheel-slip generalization campaign -> ${OUT} (seed ${SEED}, ${REPS} rep(s)/arm) ==="
date

run_cell() {
  local arm="$1" legacy_flag="$2" rep="$3"
  local run_dir="${OUT}/seed${SEED}_${arm}_rep${rep}"
  if [[ -f "${run_dir}/summary.json" ]]; then
    echo "--- ${arm} rep ${rep}: done, skipping ---"
    return
  fi
  echo ""
  echo "=== seed ${SEED}, ${arm}, rep ${rep} - $(date +%H:%M:%S) ==="
  python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
    --seeds "${SEED}" --goal-tolerance-m 0.35 --record-signals ${legacy_flag} --out "${run_dir}"
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
echo "=== wheel-slip generalization campaign finished (seed ${SEED}) - $(date) ==="
