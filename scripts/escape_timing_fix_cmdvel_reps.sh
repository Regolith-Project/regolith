#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Follow-up to escape_timing_fix_campaign, fixed arm only, seed 7, reps 11-14 -
# now with /cmd_vel recorded (m4_acceptance.py, --record-signals), to test the
# open hypothesis from PROGRESS.md ("the split traced to a second shared
# chokepoint"): whether pure_pursuit's commanded_speed is what differs between
# the "long" and "short" outcome groups at the shared t=800-1300s dwell, since
# GT speed and wheel odometry alone don't distinguish them.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${REPO_ROOT}/escape_timing_fix_campaign"

for rep in 11 12 13 14; do
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
echo "=== all cmd_vel-instrumented reps done $(date +%H:%M:%S) ==="
