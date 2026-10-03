#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Paired A/B: what does the escape record look like when the recovery node is not
# allowed a simulation oracle?
#
# `flip_recovery_node` decided everything from /ground_truth/pose - flip attitude,
# the "not moving" test, and whether an escape had worked. The 61/61 figure was
# measured that way, so it is a statement about a rover with a sensor no real
# rover has. `onboard_only` restricts the detectors to IMU attitude and the EKF
# estimate (see PROGRESS.md, "Sim-to-real, step 1").
#
# Both arms are the SAME BUILD, same seeds, same goals; the only difference is
# which pose source the detectors may read. That is the discipline PROGRESS.md's
# visual-odometry lesson exists to enforce - a component measured against an older
# baseline takes credit for every other change made since.
#
# The metric of interest accumulates WITHIN a run (2-9 escape events each), so
# even one rep per cell yields dozens of events to compare. Pass/fail per seed
# needs replicates and does not get them here; that is stated, not smuggled.
#
# Arms are interleaved per seed so an interrupted campaign still leaves matched
# pairs rather than a complete arm and nothing to compare it against.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

OUT="${OUT:-${REPO_ROOT}/onboard_recovery_campaign}"
SEEDS="${SEEDS:-42 7 123}"
REPS="${REPS:-1}"
ARMS="${ARMS:-oracle onboard}"

mkdir -p "${OUT}"
exec 9>"${OUT}/.campaign.lock"
if ! flock -n 9; then
  echo "REFUSING TO START: another campaign holds ${OUT}/.campaign.lock." >&2
  exit 1
fi

for seed in ${SEEDS}; do
  for rep in ${REPS}; do
    for arm in ${ARMS}; do
      run_dir="${OUT}/seed${seed}_${arm}_rep${rep}"
      if [[ -f "${run_dir}/summary.json" ]]; then
        echo "--- seed ${seed} ${arm} rep ${rep}: done, skipping ---"
        continue
      fi
      flag=""
      [[ "${arm}" == "onboard" ]] && flag="--onboard-only-recovery"
      echo ""
      echo "=== seed ${seed}, recovery=${arm}, rep ${rep} - $(date +%H:%M:%S) ==="
      python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
        --seeds "${seed}" --goal-tolerance-m 0.35 \
        ${flag} --out "${run_dir}"
      echo "=== finished $(date +%H:%M:%S) ==="
      # A survivor from one cell poisons the next one's RTF and its DDS graph.
      # Both patterns are kept: the world NAME never appears in the server's
      # command line (it carries the world PATH), so the first matches nothing
      # on this build - see PROGRESS.md, "demo.sh's leftover-process check has a
      # hole". The second is the one that actually fires.
      pkill -KILL -f "gz[ ]sim.*regolith_moon" 2>/dev/null
      pkill -KILL -f "gz[ ]sim.*worlds/seed_" 2>/dev/null
      sleep 10
    done
  done
done
echo "campaign complete - $(date +%H:%M:%S)"
