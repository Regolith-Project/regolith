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
