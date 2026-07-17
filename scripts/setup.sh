#!/usr/bin/env bash
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
#
# Pulls in regolith.universe (per regolith.repos) and builds the workspace.
# Mirrors autoware's meta-repo pattern: this repo holds no package source of
# its own, only the .repos pin, launch/demo scripts, and top-level docs.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

mkdir -p src
vcs import src < regolith.repos

source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -y

colcon build --symlink-install --parallel-workers "${COLCON_PARALLEL_WORKERS:-2}"

echo "Done. Source install/setup.bash and run: ros2 launch regolith_bringup hello_moon.launch.py"
