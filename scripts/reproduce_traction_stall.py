#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Reproduces the "benign-ground traction stall" (PROGRESS.md: wheels claim 2.76 m,
body 0.00 m) on a FRESH, wedge-free, tour-free run - no escape-maneuver history, no
rocks, no seam - to answer the question that section left open: is the rover actually
losing traction, or is something else going on.

Usage (after `ros2 launch regolith_bringup hello_moon.launch.py seed:=42 mission:=none
rviz:=false headless:=true` is up and its ROS_DOMAIN_ID exported into this shell):

    python3 scripts/reproduce_traction_stall.py out.csv 12.0 12.0 150.0

Drives a straight point-to-point goal whose line happens to cross the recorded wedge
cell (seed 42, cell (22,22), centred near (6.2, 6.2)), and logs ground-truth pose
(position AND attitude) plus wheel odom at 5 Hz for the whole drive. This answers the
open question directly: if the rover is really losing traction, ground-truth XY stalls
while wheel odom keeps claiming distance; if it isn't, ground-truth XY keeps advancing
right through the moment the detector declares slip.

RESULT (2026-08-20, one run, seed 42, goal (12, 12) from spawn): it is the second case.
See PROGRESS.md, "Root-caused: the benign-ground traction stall was never a stall" -
`SlipDetector`'s rigid-body signature cannot tell "stationary" from "translating without
rotating," and a dead-straight drive across this seed's unusually flat, uniform patch
near (6.2, 6.2) does the latter for long enough to satisfy the former.
"""
import csv
import math
import sys
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock

OUT_CSV = sys.argv[1] if len(sys.argv) > 1 else "/tmp/traction_repro.csv"
GOAL_X = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
GOAL_Y = float(sys.argv[3]) if len(sys.argv) > 3 else 12.0
SIM_BUDGET_S = float(sys.argv[4]) if len(sys.argv) > 4 else 150.0
WALL_CAP_S = 900.0  # hard stop regardless of sim time, in case /clock ever wedges itself


def rpy_from_quat(q) -> tuple:
    roll = math.atan2(2.0 * (q.w * q.x + q.y * q.z), 1.0 - 2.0 * (q.x * q.x + q.y * q.y))
    pitch = math.asin(max(-1.0, min(1.0, 2.0 * (q.w * q.y - q.z * q.x))))
    yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
    return roll, pitch, yaw


class Repro(Node):
    def __init__(self):
        super().__init__("traction_repro")
        self.sim_t = None
        self.gt = None
        self.odom_vx = None
        self.rows = []
        self.create_subscription(Clock, "/clock", self._on_clock, 10)
        self.create_subscription(PoseStamped, "/ground_truth/pose", self._on_gt, 20)
        self.create_subscription(Odometry, "/odom", self._on_odom, 20)
        self.goal_pub = self.create_publisher(PoseStamped, "/goal_pose", 10)
        self._goal_accepted = False
        # Keep re-publishing the goal every 2s for the WHOLE run, not just an initial
        # burst: planner_node refuses a goal until it has both a costmap and a current
        # EKF pose ("No costmap or current pose yet - ignoring goal"), which on a fresh
        # launch can take longer than a short burst covers - an early version of this
        # script published for 6s, the planner was ready at ~8s, and the rover never
        # moved for the entire budget.
        self.create_timer(2.0, self._maybe_pub_goal)
        self.create_timer(0.2, self._sample)  # 5 Hz - fine enough to catch a transition
        self.start_wall = time.monotonic()

    def _on_clock(self, msg):
        self.sim_t = msg.clock.sec + msg.clock.nanosec * 1e-9

    def _on_gt(self, msg):
        self.gt = msg

    def _on_odom(self, msg):
        self.odom_vx = msg.twist.twist.linear.x

    def _maybe_pub_goal(self):
        if self.odom_vx is not None and abs(self.odom_vx) > 0.02:
            self._goal_accepted = True
        if self._goal_accepted:
            return
        g = PoseStamped()
        g.header.frame_id = "map"
        g.header.stamp = self.get_clock().now().to_msg()
        g.pose.position.x = GOAL_X
        g.pose.position.y = GOAL_Y
        g.pose.orientation.w = 1.0
        self.goal_pub.publish(g)

    def _sample(self):
        if self.gt is None or self.sim_t is None:
            return
        r, p, y = rpy_from_quat(self.gt.pose.orientation)
        self.rows.append(
            {
                "sim_t": self.sim_t,
                "wall_t": time.monotonic() - self.start_wall,
                "gt_x": self.gt.pose.position.x,
                "gt_y": self.gt.pose.position.y,
                "gt_z": self.gt.pose.position.z,
                "roll": r,
                "pitch": p,
                "yaw": y,
                "odom_vx": self.odom_vx,
            }
        )

    def done(self) -> bool:
        return self.sim_t is not None and self.sim_t > SIM_BUDGET_S


def main() -> None:
    rclpy.init()
    node = Repro()
    try:
        while rclpy.ok() and not node.done():
            rclpy.spin_once(node, timeout_sec=0.5)
            if time.monotonic() - node.start_wall > WALL_CAP_S:
                node.get_logger().warn("wall-clock cap hit, stopping")
                break
    except KeyboardInterrupt:
        pass
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["sim_t", "wall_t", "gt_x", "gt_y", "gt_z", "roll", "pitch", "yaw", "odom_vx"],
        )
        writer.writeheader()
        writer.writerows(node.rows)
    node.get_logger().info(f"wrote {len(node.rows)} rows to {OUT_CSV}")
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
