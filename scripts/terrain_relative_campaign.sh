#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Live validation of terrain-relative navigation (terrain_relative_node.py), as a
# matched A/B on ONE build - the discipline PROGRESS.md's visual-odometry lesson
# exists to enforce: a new component measured against an older baseline takes
# credit for every other change made since.
#
# Both arms run the same binary, the same seed and the same goal; the only
# difference is whether the EKF is fused with the terrain-matched absolute fix.
# The `off` arm is NOT taken from the existing seed-123 campaign data, even
# though six runs of it exist: those predate the escape-timing fix and several
# other changes, and the whole point here is that the comparison is same-build.
#
# Seed 123 first, deliberately. It is the drift-limited seed - 9.98-11.25 m of
# EKF divergence across six recorded runs, a margin no stopping tolerance can
# close - and it is where the offline replay predicts the largest effect
# (11.18 m -> 1.64 m median). If terrain matching does nothing here it does
# nothing anywhere, so this is the cheapest way to be wrong early.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${REPO_ROOT}/terrain_relative_campaign"
SEEDS="${SEEDS:-123}"
REPS="${REPS:-1 2}"

for seed in ${SEEDS}; do
  for rep in ${REPS}; do
    for arm in on off; do
      run_dir="${OUT}/seed${seed}_trn_${arm}_rep${rep}"
      if [[ -f "${run_dir}/summary.json" ]]; then
        echo "--- seed ${seed} ${arm} rep ${rep}: done, skipping ---"
        continue
      fi
      flag=""
      [[ "${arm}" == "on" ]] && flag="--terrain-relative"
      echo ""
      echo "=== seed ${seed}, terrain_relative=${arm}, rep ${rep} - $(date +%H:%M:%S) ==="
      python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
        --seeds "${seed}" --goal-tolerance-m 0.35 --record-signals \
        ${flag} --out "${run_dir}"
      echo "=== finished $(date +%H:%M:%S) ==="
      # Same teardown as every other campaign runner here: a survivor from one
      # cell poisons the next one's RTF and its DDS graph. See PROGRESS.md.
      pkill -KILL -f "gz[ ]sim.*regolith_moon" 2>/dev/null
      pkill -KILL -f "gz[ ]sim.*worlds/seed_" 2>/dev/null
      sleep 10
    done
  done
done
echo "campaign complete - $(date +%H:%M:%S)"
