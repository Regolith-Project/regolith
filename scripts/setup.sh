#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Pulls in regolith.universe (per regolith.repos) and builds the workspace.
# Mirrors autoware's meta-repo pattern: this repo holds no package source of
# its own, only the .repos pin, launch/demo scripts, and top-level docs.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -f /opt/ros/humble/setup.bash ]; then
  echo "ERROR: ROS 2 Humble not found at /opt/ros/humble." >&2
  echo "Install ros-humble-desktop first - see the Quick Start prerequisites in README.md." >&2
  exit 1
fi
for tool in vcs rosdep colcon; do
  if ! command -v "$tool" >/dev/null; then
    echo "ERROR: '$tool' not found on PATH." >&2
    echo "Install python3-vcstool, python3-rosdep, and python3-colcon-common-extensions - see README.md." >&2
    exit 1
  fi
done

if [ ! -d src/regolith.universe ]; then
  mkdir -p src
  vcs import src < regolith.repos
fi

# ROS 2's setup.bash isn't safe under `set -u` (references unbound vars like
# AMENT_TRACE_SETUP_FILES on first source) - relax it for this line only.
set +u
source /opt/ros/humble/setup.bash
set -u

# Builds only the regolith_* packages (under src/regolith.universe/planetary/),
# not the full autoware.universe tree: none of them depend on any autoware_*
# package, and the untouched car-specific tree has rosdep keys
# (tier4_*/CUDA-only packages) that don't resolve on a stock install - see
# PROGRESS.md M1. The stripping/COLCON_IGNORE pass from the plan's section 4
# is deferred to whichever milestone first needs a full-workspace build.
rosdep install --from-paths src/regolith.universe/planetary --ignore-src -y

colcon build --symlink-install --parallel-workers "${COLCON_PARALLEL_WORKERS:-2}" \
  --packages-up-to regolith_bringup

echo "Done. Source install/setup.bash and run: ros2 launch regolith_bringup hello_moon.launch.py"
