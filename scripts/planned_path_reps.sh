#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# The fixed-arm split is resolved down to one unanswered input: at the 4 cm
# step around (-15.2,-50.65), the follower steers at its 0.30 rad/s angular
# limit in the long reps and never above 0.24 in the short ones - from the
# same position, the same heading and the same 0.13-0.20 m of EKF divergence
# (PROGRESS.md). The only remaining candidate is the path it is following,
# which no campaign here has ever recorded.
#
# This runs fixed-arm seed-7 reps with --record-paths as well as
# --record-signals and --stuck-debug, so scripts/reconstruct_follower_target.py
# can recompute the follower's heading error offline - the quantity /cmd_vel
# cannot show, because it saturates.
#
# Cluster membership is not selectable (10 short / 9 long at n=19), so this
# needs both kinds to compare; a batch, not a single rep.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${REPO_ROOT}/planned_path_campaign"
mkdir -p "${OUT}"

first="${1:-1}"
last="${2:-4}"

for rep in $(seq "${first}" "${last}"); do
  run_dir="${OUT}/seed7_paths_rep${rep}"
  if [[ -f "${run_dir}/summary.json" ]]; then
    echo "--- paths rep ${rep}: done, skipping ---"
    continue
  fi
  echo "=== seed 7, fixed, paths rep ${rep} - $(date +%H:%M:%S) ==="
  python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
    --seeds 7 --goal-tolerance-m 0.35 --record-signals --record-paths --stuck-debug \
    --out "${run_dir}"
  echo "=== paths rep ${rep} finished $(date +%H:%M:%S) ==="
  pkill -KILL -f "gz[ ]sim.*regolith_moon" 2>/dev/null
  pkill -KILL -f "gz[ ]sim.*worlds/seed_" 2>/dev/null
  sleep 5
done
echo "=== batch done $(date +%H:%M:%S) ==="
