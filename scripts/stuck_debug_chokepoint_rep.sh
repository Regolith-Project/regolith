#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Follow-up to escape_timing_fix_cmdvel_reps.sh: /cmd_vel ruled out the
# commanded-speed hypothesis for the fixed arm's second shared chokepoint
# (PROGRESS.md, "The obvious next hypothesis - checked directly, and
# refuted"), leaving the node's own internal _stuck_since state as the last
# unobserved candidate. This runs ONE fixed-arm seed-7 rep with the new
# --stuck-debug flag (flip_recovery_node.py, stuck_debug param) so the
# launch log records every streak start/reset/fire at the node's own 5 Hz
# tick, correlated against the same --record-signals 10 Hz CSV every other
# cell in this investigation used.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${REPO_ROOT}/escape_timing_fix_campaign"

rep="${1:-15}"
run_dir="${OUT}/seed7_fixed_rep${rep}"
if [[ -f "${run_dir}/summary.json" ]]; then
  echo "--- fixed rep ${rep}: done, skipping ---"
  exit 0
fi
echo "=== seed 7, fixed, rep ${rep} (stuck_debug) - $(date +%H:%M:%S) ==="
python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
  --seeds 7 --goal-tolerance-m 0.35 --record-signals --stuck-debug --out "${run_dir}"
echo "=== finished $(date +%H:%M:%S) ==="
pkill -KILL -f "gz[ ]sim.*regolith_moon" 2>/dev/null
pkill -KILL -f "gz[ ]sim.*worlds/seed_" 2>/dev/null
echo "=== done $(date +%H:%M:%S) ==="
