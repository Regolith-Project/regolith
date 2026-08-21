#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Follow-up to the wheel-slip A/B campaign's "what this does not establish": phantom
# distance suppressed explains only ~half of seed 42's divergence variance (r=0.70,
# r^2~0.49), and two path-complexity proxies (replan count, jump-shape) point away from
# isolated stuck incidents and toward something that accumulates during ordinary
# driving - consistent with M3's already-measured mechanism (skid-steer wheel odometry
# over-claims rotation ~3x during turning). This campaign gets the direct measurement
# the earlier proxies couldn't: --record-signals logs /odom wz and /imu wz continuously,
# so accumulated turning can be correlated against divergence growth directly instead of
# through a replan-count proxy.
#
# Fixed arm only (signature 2 already retired - this is not an A/B test, it's a
# same-build replicate campaign to get enough (turning, divergence) pairs to correlate).
# Seed 42, same goal as the A/B campaign, for direct comparability.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:?usage: turning_vs_divergence_campaign.sh <output-dir> [reps]}"
REPS="${2:-3}"

mkdir -p "${OUT}"
echo "=== turning-vs-divergence campaign -> ${OUT} (${REPS} reps, seed 42, fixed arm, signals recorded) ==="
date

for rep in $(seq 1 "${REPS}"); do
  run_dir="${OUT}/seed42_rep${rep}"
  if [[ -f "${run_dir}/summary.json" ]]; then
    echo "--- rep ${rep}: done, skipping ---"
    continue
  fi
  echo ""
  echo "=== seed 42, rep ${rep} - $(date +%H:%M:%S) ==="
  python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
    --seeds 42 --goal-tolerance-m 0.35 --record-signals --out "${run_dir}"
  echo "=== finished $(date +%H:%M:%S) ==="
  pkill -KILL -f "gz[ ]sim.*regolith_moon" 2>/dev/null
  pkill -KILL -f "gz[ ]sim.*worlds/seed_" 2>/dev/null
  sleep 10
done

echo ""
echo "=== turning-vs-divergence campaign finished - $(date) ==="
