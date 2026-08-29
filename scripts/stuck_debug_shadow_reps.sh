#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Follow-up to stuck_debug_chokepoint_rep.sh. That script's one rep (15)
# landed in the SHORT cluster and was resolved by the wheel-slip detector
# before the ground-truth debounce could complete, which - because
# _check_stuck returns on a slip hit before touching _stuck_since - left the
# actual question unobserved (PROGRESS.md, "Internal debug logging built...").
# flip_recovery_node's stuck_debug now also logs the slip path and a shadow
# streak that survives slip/cooldown/escape gaps, so every rep says how close
# the ground-truth condition came regardless of what resolved it.
#
# This runs a sequential batch of fixed-arm seed-7 reps with that fuller
# instrumentation. The open question needs at least one LONG-cluster rep
# (divergence ~3 m; 6 of the first 15 were long), and cluster membership is
# not selectable - hence a batch rather than a single rep.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${REPO_ROOT}/escape_timing_fix_campaign"

first="${1:-16}"
last="${2:-19}"

for rep in $(seq "${first}" "${last}"); do
  run_dir="${OUT}/seed7_fixed_rep${rep}"
  if [[ -f "${run_dir}/summary.json" ]]; then
    echo "--- fixed rep ${rep}: done, skipping ---"
    continue
  fi
  echo "=== seed 7, fixed, rep ${rep} (stuck_debug + shadow) - $(date +%H:%M:%S) ==="
  python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
    --seeds 7 --goal-tolerance-m 0.35 --record-signals --stuck-debug --out "${run_dir}"
  echo "=== rep ${rep} finished $(date +%H:%M:%S) ==="
  pkill -KILL -f "gz[ ]sim.*regolith_moon" 2>/dev/null
  pkill -KILL -f "gz[ ]sim.*worlds/seed_" 2>/dev/null
  sleep 5
done
echo "=== batch done $(date +%H:%M:%S) ==="
