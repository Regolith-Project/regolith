#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Does tightening pure pursuit's stopping distance buy M4 the arrival error it
# is missing?
#
# At the shipped goal_tolerance_m = 1.0 m the rover stops a metre short of where
# it believes the goal is, which spends two thirds of M4's 1.5 m bar before it
# has drifted at all - seed 7 failed by 0.20 m with only 0.70 m of drift. See
# PROGRESS.md, "Where M4 actually stands now, and what is blocking it".
#
# Both arms run from THIS build, back to back, on the same deterministic goals.
# That is the whole point: the last comparison this project ran against banked
# numbers credited visual odometry with gains that belonged to two unrelated
# fixes, and the controlled arm reversed the conclusion outright. Nothing here
# is compared against a number from a previous session.
#
# Interleaved by seed (control, then tight, then the next seed) so that stopping
# early leaves complete matched pairs rather than a finished control arm and no
# treatment.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-${REPO_ROOT}/m4_tolerance_$(date +%Y%m%d_%H%M%S)}"
SEEDS=(42 7 123)
TOLERANCES=(1.00 0.35)   # control (shipped), treatment

mkdir -p "${OUT}"
echo "=== goal_tolerance_m experiment -> ${OUT} ==="
echo "seeds: ${SEEDS[*]}   tolerances: ${TOLERANCES[*]}"
date

for seed in "${SEEDS[@]}"; do
  for tol in "${TOLERANCES[@]}"; do
    run_dir="${OUT}/seed${seed}_tol${tol}"
    if [[ -f "${run_dir}/summary.json" ]]; then
      echo "--- seed ${seed}, tolerance ${tol}: already done, skipping ---"
      continue
    fi
    echo ""
    echo "=== seed ${seed}, goal_tolerance_m=${tol} - $(date +%H:%M:%S) ==="
    python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
      --seeds "${seed}" \
      --goal-tolerance-m "${tol}" \
      --out "${run_dir}"
    echo "=== seed ${seed}, tolerance ${tol} finished ($(date +%H:%M:%S)) ==="
    # A survivor shares gz's partition with the next run's server whatever
    # ROS_DOMAIN_ID says, which has previously starved /clock and made a healthy
    # rover look like a navigation failure. Between arms of a comparison that
    # would be worse than a lost run - it would be a wrong number.
    pkill -KILL -f "gz[ ]sim.*regolith_moon" 2>/dev/null
    pkill -KILL -f "gz[ ]sim.*worlds/seed_" 2>/dev/null
    sleep 10
  done
done

echo ""
echo "=== all runs finished - $(date) ==="
grep -h '"verdict"\|"gt_error_m"\|"divergence_m"' "${OUT}"/*/summary.json 2>/dev/null
