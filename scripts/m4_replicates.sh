#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Repeat acceptance cells, because one run per cell turned out not to be a
# measurement.
#
# The first goal_tolerance experiment produced, on seed 42, an EKF divergence of
# 5.20 m in one arm and 7.47 m in the other, against the 0.40 m banked in
# PROGRESS.md for that same seed. Pulling seed 42's unaided history together:
# 6.80 m, then 0.40 m, then 5.20 and 7.47 m. The seed fixes the terrain and the
# goal; it does not fix the outcome. Run-to-run spread on that seed is an order
# of magnitude larger than the ~0.65 m the stopping tolerance is worth, so a
# single run per cell cannot see the effect being tested - and the banked table
# is one sample per cell.
#
# So: replicate. Seed 7 gets the replicates because it is the seed where the
# tolerance is actually decisive - its drift is small (0.56-0.62 m) and its
# arrival error sits right on the 1.5 m bar, which is exactly where 0.65 m of
# stopping distance decides pass from fail. Seeds 42 and 123 fail by margins no
# stopping tolerance can close, so spending hours replicating them would buy
# less.
#
# Each cell is skipped if it already has a summary.json, so this is safe to
# re-run after an interruption.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:?usage: m4_replicates.sh <output-dir>}"
REPS="${2:-3}"

mkdir -p "${OUT}"
echo "=== replicates -> ${OUT} (${REPS} per cell) ==="
date

run_cell() {
  local seed="$1" tol="$2" rep="$3"
  local run_dir="${OUT}/seed${seed}_tol${tol}_rep${rep}"
  if [[ -f "${run_dir}/summary.json" ]]; then
    echo "--- seed ${seed} tol ${tol} rep ${rep}: done, skipping ---"
    return
  fi
  echo ""
  echo "=== seed ${seed}, tol ${tol}, rep ${rep} - $(date +%H:%M:%S) ==="
  python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
    --seeds "${seed}" --goal-tolerance-m "${tol}" --out "${run_dir}"
  echo "=== finished $(date +%H:%M:%S) ==="
  # A surviving server shares gz's partition with the next run whatever
  # ROS_DOMAIN_ID says - see PROGRESS.md.
  pkill -KILL -f "gz[ ]sim.*regolith_moon" 2>/dev/null
  pkill -KILL -f "gz[ ]sim.*worlds/seed_" 2>/dev/null
  sleep 10
}

# The cell lost to a dead simulator in the first experiment, so the 3x2 grid is
# complete rather than having a hole in it.
run_cell 123 1.00 1

# Seed 7, both arms, interleaved so an interruption leaves matched pairs.
for rep in $(seq 2 $((REPS + 1))); do
  run_cell 7 1.00 "${rep}"
  run_cell 7 0.35 "${rep}"
done

echo ""
echo "=== replicates finished - $(date) ==="
