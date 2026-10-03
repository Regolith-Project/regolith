#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# LIVE validation of the a-priori-map-quality result. The offline replay
# (scripts/terrain_relative_dem_quality.py, table in PROGRESS.md) already
# answered this on 25 recorded runs, and its answer is specific:
#
#     detail loss is survivable    2 m / 5 m posts still roughly halve the error,
#                                  and degrade in the SAFE direction because the
#                                  margin gate rejects more windows
#     vertical error is the worst   0.05 m rms of height error is already worse
#                                  than a 3 m map offset, because the matcher
#                                  consumes SLOPE: error of sigma correlated over
#                                  length L arrives as slope error ~sigma/L, and
#                                  at native 0.39 m posts 0.1 m of height error is
#                                  9.8 deg of spurious slope against 2-3 deg of
#                                  real relief
#     misregistration is fatal     a 3 m map offset is worse than dead reckoning
#                                  while publishing as many fixes at full
#                                  confidence, because nothing about the cost
#                                  surface is wrong
#
# A replay is not a run. It applies each accepted fix to a running correction;
# the real EKF weights it against its own covariance, keeps drifting between
# fixes, and feeds a controller that then drives somewhere else. Every number in
# that table is a prediction about this campaign, and predictions that are never
# tested are opinions.
#
# THREE ARMS, all with terrain_relative ON - the variable is the MAP, not the
# algorithm. The arms bracket the claim rather than sampling near one end:
#
#   perfect     the generator's own heightmap, read exactly. Not reused from the
#               existing seed-123 cells even though two PASSes at 0.18-0.19 m
#               exist: those ran at regolith.universe d643e915c and this tree is
#               two commits and several working-tree edits past it. Same-build or
#               it is not a comparison - the visual-odometry lesson.
#   degraded    2 m posts, 0.02 m vertical error, 0.5 m registration shift. The
#               best a real orbital DEM plausibly gets, and inside every bound the
#               replay derived (slope error ~26% of this site's own relief,
#               registration inside the < 1 m requirement). Replay: 1.79 m median.
#               This is the SHIP/NO-SHIP arm.
#   noisy       2 m posts, 0.10 m vertical error. A NAC-stereo DTM's actual
#               vertical precision is 0.3-1 m, so this is already generous to the
#               real artefact, and the replay says it fails outright (5.99 m).
#               Run deliberately: a predicted failure never observed is not a
#               finding, and if the live stack does NOT break here the derived
#               requirement is wrong.
#
# Seed 123 first and only, deliberately: it is the drift-limited seed, where the
# perfect-map fix does the most work (FAIL at 12-18 m -> PASS at 0.18 m). A map
# defect that does not show up here will not show up anywhere, and a fix that
# survives here has survived its hardest case.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

OUT="${OUT:-${REPO_ROOT}/dem_quality_campaign}"
SEEDS="${SEEDS:-123}"
REPS="${REPS:-1 2}"
# Arm order within a rep is interleaved rather than blocked, so that if the
# campaign is interrupted - and at ~45 min a cell, over six cells, it may be -
# what is on disk is one of each arm rather than two of the first one.
ARMS="${ARMS:-degraded perfect noisy}"

mkdir -p "${OUT}"
exec 9>"${OUT}/.campaign.lock"
if ! flock -n 9; then
  echo "REFUSING TO START: another campaign holds ${OUT}/.campaign.lock." >&2
  exit 1
fi

for rep in ${REPS}; do
  for seed in ${SEEDS}; do
    for arm in ${ARMS}; do
      run_dir="${OUT}/seed${seed}_${arm}_rep${rep}"
      if [[ -f "${run_dir}/summary.json" ]]; then
        echo "--- seed ${seed} ${arm} rep ${rep}: done, skipping ---"
        continue
      fi
      case "${arm}" in
        perfect)  dem="--dem-post-m 0 --dem-noise-m 0 --dem-shift-m 0" ;;
        degraded) dem="--dem-post-m 2.0 --dem-noise-m 0.02 --dem-shift-m 0.5" ;;
        noisy)    dem="--dem-post-m 2.0 --dem-noise-m 0.10 --dem-shift-m 0" ;;
        # REGISTRATION, added after the first six cells. The offline replay called
        # vertical error the worst defect and the live `noisy` arm passed anyway,
        # so the surviving hypothesis is about the KIND of error rather than its
        # size: the EKF's covariance weighting averages down zero-mean fix error
        # and cannot touch a bias. Matched on the same recorded windows,
        # |mean|/spread is 0.28 for 0.1 m of vertical noise and 3.03 for a 3 m
        # shift on seed 7 - scatter versus bias, which is the whole claim.
        #
        # Run on SEED 7, not 123. Seed 123's recorded windows already saturate the
        # +-6 m search range on a perfect map (42% at the bound, because they come
        # from unaided runs carrying 10 m of drift), so a shift is unrecoverable
        # there for a reason that has nothing to do with registration. Seed 7 sits
        # at 0% and shows the bias cleanly.
        shift1)   dem="--dem-post-m 0 --dem-noise-m 0 --dem-shift-m 1.0" ;;
        shift3)   dem="--dem-post-m 0 --dem-noise-m 0 --dem-shift-m 3.0" ;;
        *) echo "unknown arm ${arm}" >&2; exit 2 ;;
      esac
      # The noise seed is tied to the rep, not fixed: two reps of `realistic`
      # that share a noise field are one map tested twice, and the question is
      # about maps of that quality, not about one draw of one.
      echo ""
      echo "=== seed ${seed}, map=${arm} (${dem}), rep ${rep} - $(date +%H:%M:%S) ==="
      python3 "${REPO_ROOT}/scripts/m4_acceptance.py" \
        --seeds "${seed}" --goal-tolerance-m 0.35 --record-signals \
        --terrain-relative ${dem} --dem-noise-seed "${rep}" --out "${run_dir}"
      echo "=== finished $(date +%H:%M:%S) ==="
      pkill -KILL -f "gz[ ]sim.*regolith_moon" 2>/dev/null
      pkill -KILL -f "gz[ ]sim.*worlds/seed_" 2>/dev/null
      sleep 10
    done
  done
done
echo "campaign complete - $(date +%H:%M:%S)"
