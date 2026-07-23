#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# One-command entry point: regenerates terrain, builds if needed, and launches
# the full hello-world demo (scripted 5-waypoint tour).
#
#   ./scripts/demo.sh [--seed N]

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

SEED=42
while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed)
      [ $# -ge 2 ] || { echo "ERROR: --seed requires a value" >&2; exit 1; }
      SEED="$2"; shift 2 ;;
    *) echo "Usage: $0 [--seed N]" >&2; echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if ! [[ "$SEED" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --seed must be a non-negative integer, got '$SEED'" >&2
  exit 1
fi

if [ ! -f /opt/ros/humble/setup.bash ]; then
  echo "ERROR: ROS 2 Humble not found at /opt/ros/humble." >&2
  echo "Install ros-humble-desktop first - see the Quick Start prerequisites in README.md." >&2
  exit 1
fi
if ! command -v gz >/dev/null; then
  echo "ERROR: 'gz' (Gazebo) not found on PATH." >&2
  echo "Install gz-harmonic and ros-humble-ros-gzharmonic - see README.md." >&2
  exit 1
fi

if [ ! -f install/setup.bash ]; then
  echo "No build found - running scripts/setup.sh first..."
  ./scripts/setup.sh
fi

# A prior launch (crashed, backgrounded, or just left running in another
# terminal) leaves gz sim + every ROS node from this demo still alive. Since
# 2026-07-23 hello_moon.launch.py claims a private ROS_DOMAIN_ID per invocation
# (see PROGRESS.md's "Per-launch ROS_DOMAIN_ID isolation"), so a leftover stack
# can no longer cross-talk with a new launch on shared /goal_pose, /clock,
# /cmd_vel etc. - the graph-collision that caused the overnight freeze is now
# structurally prevented. This preflight kill is kept anyway: a genuinely
# orphaned duplicate stack still burns GPU/CPU (gz sim + a full node set) even
# when it's graph-isolated, so reclaiming those resources before starting is
# still worthwhile. Anchor on the launch process's own process group so every descendant is
# caught even if the launch parent itself already died and its children were
# reparented (pgid survives reparenting). Match installed executable paths,
# not "regolith" as a bare substring - this repo is checked out under a path
# containing that word, so a substring match self-matches this very script.
echo "Checking for leftover processes from a previous run..."
found_leftover=0
for pid in $(pgrep -f "ros2 launch.*hello_moon\.launch\.py" 2>/dev/null || true); do
  found_leftover=1
  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
  [ -n "$pgid" ] && kill -TERM -- "-$pgid" 2>/dev/null || true
done
if pgrep -f "install/regolith_[a-z_]*/lib/" >/dev/null 2>&1; then
  found_leftover=1
  pkill -TERM -f "install/regolith_[a-z_]*/lib/" 2>/dev/null || true
fi
if pgrep -f "ruby .*gz sim.*regolith_moon" >/dev/null 2>&1; then
  found_leftover=1
  pkill -TERM -f "ruby .*gz sim.*regolith_moon" 2>/dev/null || true
fi
if [ "$found_leftover" = "1" ]; then
  echo "Found leftover processes from a previous run - stopping them..."
  sleep 2
  pkill -KILL -f "ros2 launch.*hello_moon\.launch\.py" 2>/dev/null || true
  pkill -KILL -f "install/regolith_[a-z_]*/lib/" 2>/dev/null || true
  pkill -KILL -f "ruby .*gz sim.*regolith_moon" 2>/dev/null || true
  sleep 1
fi
if pgrep -f "install/regolith_[a-z_]*/lib/" >/dev/null 2>&1 \
   || pgrep -f "ros2 launch.*hello_moon\.launch\.py" >/dev/null 2>&1; then
  echo "ERROR: could not fully stop a previous run's processes." >&2
  echo "Check 'ps aux | grep regolith' and stop them manually before continuing -" >&2
  echo "starting a second launch on top of a live one silently corrupts both (see PROGRESS.md)." >&2
  exit 1
fi

# ROS 2's setup.bash isn't safe under `set -u` (references unbound vars like
# AMENT_TRACE_SETUP_FILES on first source) - relax it for these two lines only.
set +u
source /opt/ros/humble/setup.bash
source install/setup.bash
set -u

# WSL2 on a hybrid AMD/NVIDIA laptop: WSLg's D3D12 renderer otherwise defaults
# to the integrated AMD adapter instead of the discrete NVIDIA GPU - see
# PROGRESS.md M0. Harmless (unset) on other setups.
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA

echo "Launching Regolith hello-world demo (seed=${SEED})..."
ros2 launch regolith_bringup hello_moon.launch.py "seed:=${SEED}" mission:=tour
