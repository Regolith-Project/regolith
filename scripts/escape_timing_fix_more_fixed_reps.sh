#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Extends escape_timing_fix_campaign's FIXED-arm sample only (seed 7, reps 6-10),
# to answer PROGRESS.md's open question ("the natural fix, attempted") about
# whether the fixed arm's post-fix divergence regression (1.64m -> 2.42m mean at
# n=5) is real or n=5 noise. Legacy arm is already conclusively resolved (5/5
# identical escalation sequences) and is not re-run here - only fixed needs more
# statistical power. Same skip-if-done discipline as wheel_slip_generalization_
# campaign.sh, which this deliberately does not reuse wholesale (it always runs
# both arms per rep; this needs fixed only).
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${REPO_ROOT}/escape_timing_fix_campaign"

for rep in 6 7 8 9 10; do
  run_dir="${OUT}/seed7_fixed_rep${rep}"
  if [[ -f "${run_dir}/summary.json" ]]; then
    echo "--- fixed rep ${rep}: done, skipping ---"
    continue
  fi
  echo ""
  echo "=== seed 7, fixed, rep ${rep} - $(date +%H:%M:%S) ==="
  python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
    --seeds 7 --goal-tolerance-m 0.35 --record-signals --out "${run_dir}"
  echo "=== finished $(date +%H:%M:%S) ==="
  pkill -KILL -f "gz[ ]sim.*regolith_moon" 2>/dev/null
  pkill -KILL -f "gz[ ]sim.*worlds/seed_" 2>/dev/null
  sleep 10
done
echo "=== all fixed-arm extension reps done $(date +%H:%M:%S) ==="
