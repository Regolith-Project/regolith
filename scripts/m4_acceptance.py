#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""M4 acceptance runner - judged on ground truth, never on /goal_reached.

    ./scripts/m4_acceptance.py --seeds 42 7 123

M4's bar is "the rover reaches a 60-100 m goal within 1.5 m, without
intervention, on 3 consecutive runs". The res40 re-run recorded in PROGRESS.md
showed why that has to be measured against `/ground_truth/pose` and nothing
else: all three runs published "Goal reached (within 1.50 m)" while ground
truth put the rover 17-36 m away. `pure_pursuit_node` measures arrival as
`norm(path[-1] - position)` with `position` coming from `/odometry/filtered`,
so once a wedged rover's wheel odometry has integrated distance it never
travelled, the arrival check is wrong in exactly the same direction and by
exactly the same amount as the estimate. A harness that trusted the system's
own success topic would have recorded 3/3 pass on a 0/3 run.

So this harness:

  * publishes the goal and then does nothing else - "without intervention"
    is only true if the harness stays out of it;
  * subscribes to `/ground_truth/pose` (bridged straight from gz, never fused
    into the EKF) and decides pass/fail on that distance alone;
  * treats a `/goal_reached` that fires further than the tolerance from the
    goal as a FALSE ARRIVAL - a failure that is *worse* than a timeout,
    recorded as such rather than quietly accepted;
  * records the EKF's own estimate alongside, so localization divergence is a
    measured column of every run rather than something inferred afterwards;
  * validates the goal against the SAME costmap the running system builds,
    with the same parameters hello_moon.launch.py passes to costmap_node. A
    goal on a lethal cell makes the planner refuse it forever and looks
    exactly like a navigation failure (this happened - see PROGRESS.md's
    "harness corrections").

Every launch claims a private ROS_DOMAIN_ID via the lock-file registry, so the
watcher reads the domain back off the launch's stdout and joins it. A watcher
left on the default domain sees an empty graph and waits out the whole timeout.
"""

import argparse
import json
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The parameters hello_moon.launch.py passes to costmap_node. Goal validation is
# only meaningful against the costmap the running system actually builds.
COSTMAP_RESOLUTION_M = 1.0
ROVER_RADIUS_M = 0.3
SLOPE_LETHAL_DEG = 20.0

SPAWN_XY = (0.0, 0.0)  # hello_moon.launch.py bakes the rover in at world origin

DOMAIN_RE = re.compile(r"ROS_DOMAIN_ID=(\d+)")
# Anchored on the maneuver announcement specifically. `STUCK RECOVERY #N` alone
# matches twice per event - once when the maneuver runs and once when its result
# ("FREED" / "STILL WEDGED") is reported - which silently doubled the stuck-event
# column of the first verification run.
STUCK_RE = re.compile(r"STUCK RECOVERY #(\d+) \(escalation")
STUCK_FREED_RE = re.compile(r"STUCK RECOVERY #(\d+) result: .* - FREED")
FLIP_RE = re.compile(r"SIMULATED RECOVERY #(\d+)")
SLIP_RE = re.compile(r"WHEEL SLIP #(\d+): over the last")


# --------------------------------------------------------------------------
# Goal selection and validation (driver side, no ROS needed)
# --------------------------------------------------------------------------


def _load_manifest(seed: int) -> dict:
    from regolith_terrain_gen.cli import default_output_dir
    from regolith_terrain_gen.config import TerrainConfig
    from regolith_terrain_gen.generate import generate_world

    output_dir = default_output_dir(seed)
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        generate_world(TerrainConfig(seed=seed), output_dir, start_paused=False)
    return json.loads(manifest_path.read_text())


def _costmap_for(seed: int):
    """(lethal_bool_grid, resolution_m, origin_x, origin_y) as costmap_node builds it."""
    import numpy as np
    from regolith_costmap.costmap_node import build_costmap, load_heightmap

    manifest = _load_manifest(seed)
    heightmap = load_heightmap(manifest)
    cost_grid, resolution_m, origin_x, origin_y = build_costmap(
        manifest, heightmap, COSTMAP_RESOLUTION_M, ROVER_RADIUS_M, SLOPE_LETHAL_DEG
    )
    return np.asarray(cost_grid) >= 100, resolution_m, origin_x, origin_y


def _to_cell(x_m: float, y_m: float, resolution_m: float, origin_x: float, origin_y: float):
    return int((y_m - origin_y) / resolution_m), int((x_m - origin_x) / resolution_m)


def validate_goal(seed: int, goal_xy: tuple) -> dict:
    """Goal cell and its 8 neighbours must be non-lethal (the planner snaps to a
    cell centre, so a goal whose neighbourhood is lethal is not reliably
    plannable), and the cell must be connected to spawn through non-lethal cells."""
    from collections import deque

    lethal, resolution_m, origin_x, origin_y = _costmap_for(seed)
    rows, cols = lethal.shape
    grow, gcol = _to_cell(goal_xy[0], goal_xy[1], resolution_m, origin_x, origin_y)
    srow, scol = _to_cell(*SPAWN_XY, resolution_m, origin_x, origin_y)

    result = {
        "goal": list(goal_xy),
        "cell": [grow, gcol],
        "in_bounds": 0 <= grow < rows and 0 <= gcol < cols,
        "neighbourhood_clear": False,
        "connected_to_spawn": False,
        "straight_line_m": math.dist(SPAWN_XY, goal_xy),
    }
    if not result["in_bounds"]:
        return result

    block = lethal[max(0, grow - 1):grow + 2, max(0, gcol - 1):gcol + 2]
    result["neighbourhood_clear"] = not bool(block.any())
    if not result["neighbourhood_clear"]:
        return result

    # Flood fill from spawn through non-lethal cells (4-connected, matching the
    # planner's own step set closely enough for a reachability verdict).
    seen = {(srow, scol)}
    queue = deque([(srow, scol)])
    while queue:
        r, c = queue.popleft()
        if (r, c) == (grow, gcol):
            result["connected_to_spawn"] = True
            break
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in seen and not lethal[nr, nc]:
                seen.add((nr, nc))
                queue.append((nr, nc))
    return result


def pick_goal(seed: int, min_m: float, max_m: float) -> dict:
    """Deterministic goal draw in the [min_m, max_m] annulus around spawn, kept
    only if it survives validate_goal. Used when no goal is given explicitly."""
    import random

    rng = random.Random(seed)
    for _ in range(500):
        distance = rng.uniform(min_m, max_m)
        bearing = rng.uniform(-math.pi, math.pi)
        goal = (
            round(SPAWN_XY[0] + distance * math.cos(bearing), 2),
            round(SPAWN_XY[1] + distance * math.sin(bearing), 2),
        )
        report = validate_goal(seed, goal)
        if report["neighbourhood_clear"] and report["connected_to_spawn"]:
            return report
    raise RuntimeError(f"seed {seed}: no valid goal found in {min_m}-{max_m} m after 500 draws")


# --------------------------------------------------------------------------
# Watcher (runs as a subprocess inside the launch's ROS_DOMAIN_ID)
# --------------------------------------------------------------------------


def run_watcher(args) -> int:
    import rclpy
    from geometry_msgs.msg import PoseStamped
    # Aliased: nav_msgs' Path would otherwise shadow pathlib.Path inside this
    # function, which is used for every output file below.
    from nav_msgs.msg import Odometry
    from nav_msgs.msg import Path as PathMsg
    from rclpy.node import Node
    from rclpy.qos import QoSDurabilityPolicy, QoSProfile
    from sensor_msgs.msg import Imu
    from std_msgs.msg import Bool

    goal_xy = tuple(float(v) for v in args.goal.split(","))
    trace_path = Path(args.trace_csv)
    result_path = Path(args.result_json)

    def rpy(q):
        roll = math.atan2(2.0 * (q.w * q.x + q.y * q.z), 1.0 - 2.0 * (q.x * q.x + q.y * q.y))
        pitch = math.asin(max(-1.0, min(1.0, 2.0 * (q.w * q.y - q.z * q.x))))
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        return roll, pitch, yaw

    class Watcher(Node):
        def __init__(self):
            super().__init__("m4_acceptance_watcher")
            self.gt = None
            self.ekf = None
            self.gt_travelled = 0.0
            self.ekf_travelled = 0.0
            self._last_gt = None
            self._last_ekf = None
            self.max_roll = 0.0
            self.max_pitch = 0.0
            self.goal_reached_at = None      # (gt_error, t) when /goal_reached fired
            self.first_gt_at = None
            self.path_seen = False
            self.verdict = None
            self.started = time.monotonic()
            self._goal_publishes = 0
            self._trace = trace_path.open("w", buffering=1)
            self._trace.write("t_s,gt_x,gt_y,ekf_x,ekf_y,gt_error_m,divergence_m,gt_travelled_m\n")

            # Raw signal log, for judging slip detectors offline: what the wheels
            # claim (/odom twist) against what the IMU and ground truth say the
            # body actually did. A slip detector may only use the first two -
            # the ground-truth columns are the answer key, not an input.
            self._signals = None
            if args.signals_csv:
                self._signals = Path(args.signals_csv).open("w", buffering=1)
                # sim_t comes from the /odom header stamp, not the wall clock:
                # every velocity here is per second of SIMULATED time, and this
                # world runs well below real time, so integrating vx against
                # wall-clock dt overstates distance by 1/RTF. Anything replaying
                # this file as if it were the live signal must use sim_t.
                self._signals.write(
                    "t_s,sim_t,odom_vx,odom_wz,imu_wz,imu_ax,imu_ay,roll,pitch,yaw,"
                    "gt_x,gt_y,gt_speed\n"
                )
            self._gt_speed = 0.0
            self._gt_prev = None
            self._imu = None
            self._odom = None
            self._rpy = (0.0, 0.0, 0.0)

            self.create_subscription(PoseStamped, "/ground_truth/pose", self._on_gt, 10)
            self.create_subscription(Odometry, "/odometry/filtered", self._on_ekf, 10)
            self.create_subscription(Odometry, "/odom", self._on_odom, 10)
            self.create_subscription(Imu, "/imu", self._on_imu, 10)
            self.create_subscription(Bool, "/goal_reached", self._on_reached, 10)
            # The goal is re-sent until a path comes back, not a fixed number of
            # times: the planner drops any goal that arrives before it has both a
            # costmap and a pose, and a run whose goals all landed in that window
            # sits motionless for the whole timeout looking like a navigation
            # failure. Seen for real - see PROGRESS.md.
            path_qos = QoSProfile(depth=1)
            path_qos.durability = QoSDurabilityPolicy.TRANSIENT_LOCAL
            self.create_subscription(PathMsg, "/planned_path", self._on_path, path_qos)
            self._goal_pub = self.create_publisher(PoseStamped, "/goal_pose", 10)
            self.create_timer(1.0, self._tick)
            self.create_timer(5.0, self._log_trace)
            if self._signals is not None:
                self.create_timer(0.1, self._log_signals)

        # -- callbacks ---------------------------------------------------
        def _on_gt(self, msg):
            p = msg.pose.position
            if self.first_gt_at is None:
                self.first_gt_at = time.monotonic()
            if self._last_gt is not None:
                step = math.dist((p.x, p.y), self._last_gt)
                if step > 0.01:  # ignore jitter below a centimetre
                    self.gt_travelled += step
                    self._last_gt = (p.x, p.y)
            else:
                self._last_gt = (p.x, p.y)
            now = time.monotonic()
            if self._gt_prev is not None and now > self._gt_prev[0]:
                self._gt_speed = math.dist((p.x, p.y), self._gt_prev[1:]) / (now - self._gt_prev[0])
            self._gt_prev = (now, p.x, p.y)
            self.gt = (p.x, p.y)
            roll, pitch, yaw = rpy(msg.pose.orientation)
            self._rpy = (roll, pitch, yaw)
            self.max_roll = max(self.max_roll, abs(roll))
            self.max_pitch = max(self.max_pitch, abs(pitch))

        def _on_odom(self, msg):
            self._odom = (
                msg.twist.twist.linear.x,
                msg.twist.twist.angular.z,
                msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            )

        def _on_imu(self, msg):
            self._imu = (
                msg.angular_velocity.z,
                msg.linear_acceleration.x,
                msg.linear_acceleration.y,
            )

        def _log_signals(self):
            if self.gt is None or self._odom is None or self._imu is None:
                return
            roll, pitch, yaw = self._rpy
            self._signals.write(
                f"{time.monotonic() - self.started:.2f},{self._odom[2]:.3f},"
                f"{self._odom[0]:.4f},{self._odom[1]:.4f},"
                f"{self._imu[0]:.4f},{self._imu[1]:.4f},{self._imu[2]:.4f},"
                f"{roll:.4f},{pitch:.4f},{yaw:.4f},"
                f"{self.gt[0]:.3f},{self.gt[1]:.3f},{self._gt_speed:.4f}\n"
            )

        def _on_ekf(self, msg):
            p = msg.pose.pose.position
            if self._last_ekf is not None:
                step = math.dist((p.x, p.y), self._last_ekf)
                if step > 0.01:
                    self.ekf_travelled += step
                    self._last_ekf = (p.x, p.y)
            else:
                self._last_ekf = (p.x, p.y)
            self.ekf = (p.x, p.y)

        def _on_path(self, msg):
            if msg.poses:
                self.path_seen = True

        def _on_reached(self, msg):
            if msg.data and self.goal_reached_at is None and self.gt is not None:
                self.goal_reached_at = (self.gt_error(), time.monotonic() - self.started)

        # -- helpers -----------------------------------------------------
        def gt_error(self):
            return math.dist(self.gt, goal_xy) if self.gt else float("nan")

        def divergence(self):
            return math.dist(self.gt, self.ekf) if self.gt and self.ekf else float("nan")

        def _log_trace(self):
            if self.gt is None:
                return
            ekf = self.ekf or (float("nan"), float("nan"))
            self._trace.write(
                f"{time.monotonic() - self.started:.1f},{self.gt[0]:.3f},{self.gt[1]:.3f},"
                f"{ekf[0]:.3f},{ekf[1]:.3f},{self.gt_error():.3f},{self.divergence():.3f},"
                f"{self.gt_travelled:.2f}\n"
            )

        def _tick(self):
            elapsed = time.monotonic() - self.started
            if self.gt is None:
                # A watcher on the wrong ROS_DOMAIN_ID sees an empty graph and
                # would otherwise burn the whole timeout looking like a
                # navigation failure. Fail fast and say which it was.
                if elapsed > args.graph_timeout_s:
                    self.verdict = "ABORT_NO_GROUND_TRUTH"
                return

            if not self.path_seen:
                if self._goal_publishes >= args.max_goal_publishes:
                    self.verdict = "ABORT_NO_PATH"
                    return
                if elapsed > 5.0 + 10.0 * self._goal_publishes:
                    goal = PoseStamped()
                    goal.header.frame_id = "odom"
                    goal.header.stamp = self.get_clock().now().to_msg()
                    goal.pose.position.x, goal.pose.position.y = goal_xy
                    goal.pose.orientation.w = 1.0
                    self._goal_pub.publish(goal)
                    self._goal_publishes += 1
                return

            error = self.gt_error()
            if error <= args.tolerance_m:
                self.verdict = "PASS"
            elif self.goal_reached_at is not None:
                # The system says it arrived and has stopped driving. Ground
                # truth says otherwise, and nothing will move the rover again.
                self.verdict = "FAIL_FALSE_ARRIVAL"
            elif elapsed > args.timeout_s:
                self.verdict = "FAIL_TIMEOUT"

    rclpy.init()
    node = Watcher()
    try:
        while rclpy.ok() and node.verdict is None:
            rclpy.spin_once(node, timeout_sec=0.5)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        # Ctrl-C, or the driver tearing the run down. Still write the result
        # file below: a partial record of where the rover actually got to is
        # worth more than a stack trace and no data.
        node.verdict = node.verdict or "ABORT_INTERRUPTED"

    result = {
        "verdict": node.verdict,
        "goal": list(goal_xy),
        "gt_final": list(node.gt) if node.gt else None,
        "ekf_final": list(node.ekf) if node.ekf else None,
        "gt_error_m": node.gt_error(),
        "divergence_m": node.divergence(),
        "gt_travelled_m": node.gt_travelled,
        "ekf_travelled_m": node.ekf_travelled,
        "max_roll_deg": math.degrees(node.max_roll),
        "max_pitch_deg": math.degrees(node.max_pitch),
        "path_planned": node.path_seen,
        "goal_publishes": node._goal_publishes,
        "goal_reached_published": node.goal_reached_at is not None,
        "goal_reached_gt_error_m": node.goal_reached_at[0] if node.goal_reached_at else None,
        "wall_time_s": time.monotonic() - node.started,
    }
    result_path.write_text(json.dumps(result, indent=2))
    node.destroy_node()
    try:
        rclpy.shutdown()
    except Exception:  # noqa: BLE001 - already shut down externally
        pass
    return 0


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def _launch(seed: int, log_path: Path, counters: dict):
    """Starts hello_moon headless in its own process group; returns (proc, get_domain)."""
    command = (
        "source /opt/ros/humble/setup.bash && "
        f"source {REPO_ROOT}/install/setup.bash && "
        "exec ros2 launch regolith_bringup hello_moon.launch.py "
        f"seed:={seed} headless:=true rviz:=false"
    )
    proc = subprocess.Popen(
        ["bash", "-c", command],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,  # own process group, so the whole tree can be killed
    )
    domain = {"id": None}
    log_file = log_path.open("w", buffering=1)

    def pump():
        for line in proc.stdout:
            log_file.write(line)
            if domain["id"] is None:
                match = DOMAIN_RE.search(line)
                if match:
                    domain["id"] = match.group(1)
            if STUCK_RE.search(line):
                counters["stuck"] += 1
            if FLIP_RE.search(line):
                counters["flips"] += 1
        log_file.close()

    threading.Thread(target=pump, daemon=True).start()
    return proc, domain


def _kill_tree(proc) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(30):
        if proc.poll() is not None:
            break
        time.sleep(1.0)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    # gz sim outlives its launch parent often enough to matter, and a survivor is
    # not harmless: ROS_DOMAIN_ID does not isolate gz-transport, so a leftover
    # server shares the gz partition with the next run's server. Observed exactly
    # once that happened - /clock stopped reaching the ROS side, every sim-time
    # timer in the graph stalled, and the run looked like a navigation failure
    # with a silent EKF and no costmap.
    #
    # Match the process by its real command line. `pkill -f "ruby .*gz sim"` (used
    # here and in demo.sh) matches nothing on this gz build, where the server runs
    # as `gz sim -r -s <world>` with no ruby wrapper in the visible command - which
    # is why a leftover survived a cleanup that reported success. The bracket in
    # "gz[ ]sim" keeps the pattern from matching this very process's own command
    # line (see PROGRESS.md's notes on pkill self-matching).
    subprocess.run(["pkill", "-KILL", "-f", "gz[ ]sim.*regolith_moon"], check=False)
    subprocess.run(["pkill", "-KILL", "-f", "gz[ ]sim.*worlds/seed_"], check=False)


def run_seed(seed: int, goal_xy, args, out_dir: Path) -> dict:
    report = validate_goal(seed, goal_xy) if goal_xy else pick_goal(seed, args.min_m, args.max_m)
    goal_xy = tuple(report["goal"])
    valid = report["neighbourhood_clear"] and report["connected_to_spawn"]
    print(
        f"[seed {seed}] goal ({goal_xy[0]:.2f}, {goal_xy[1]:.2f}), "
        f"{report['straight_line_m']:.1f} m straight line, "
        f"valid={valid} (clear={report['neighbourhood_clear']}, "
        f"connected={report['connected_to_spawn']})",
        flush=True,
    )
    if not valid:
        return {"seed": seed, "verdict": "ABORT_INVALID_GOAL", "goal_validation": report}

    log_path = out_dir / f"seed_{seed}_launch.log"
    trace_path = out_dir / f"seed_{seed}_trace.csv"
    signals_path = out_dir / f"seed_{seed}_signals.csv"
    result_path = out_dir / f"seed_{seed}_result.json"
    counters = {"stuck": 0, "flips": 0}

    proc, domain = _launch(seed, log_path, counters)
    try:
        deadline = time.monotonic() + 120.0
        while domain["id"] is None and time.monotonic() < deadline:
            if proc.poll() is not None:
                return {"seed": seed, "verdict": "ABORT_LAUNCH_DIED", "log": str(log_path)}
            time.sleep(0.5)
        if domain["id"] is None:
            return {"seed": seed, "verdict": "ABORT_NO_DOMAIN_ID", "log": str(log_path)}
        print(f"[seed {seed}] launch is on ROS_DOMAIN_ID={domain['id']}", flush=True)

        env = dict(os.environ, ROS_DOMAIN_ID=domain["id"])
        watch_cmd = (
            "source /opt/ros/humble/setup.bash && "
            f"source {REPO_ROOT}/install/setup.bash && "
            f"exec python3 {Path(__file__).resolve()} --watch "
            # `--goal=` and not `--goal `: a goal with a negative x reads as an
            # option flag in the space-separated form, and argparse rejects it
            # ("expected one argument"). Seeds whose goal happened to have a
            # positive x ran fine, so this only surfaced on seed 7 - one of the
            # three acceptance seeds - which aborted instantly.
            f"--goal={goal_xy[0]},{goal_xy[1]} --trace-csv {trace_path} "
            f"--result-json {result_path} --timeout-s {args.timeout_s} "
            f"--tolerance-m {args.tolerance_m} --graph-timeout-s {args.graph_timeout_s}"
            + (f" --signals-csv {signals_path}" if args.record_signals else "")
        )
        watcher = subprocess.run(["bash", "-c", watch_cmd], cwd=REPO_ROOT, env=env)
        if watcher.returncode != 0 or not result_path.exists():
            return {"seed": seed, "verdict": "ABORT_WATCHER_FAILED", "log": str(log_path)}
    finally:
        _kill_tree(proc)
        time.sleep(3.0)  # let the pump thread flush the tail of the log

    result = json.loads(result_path.read_text())
    result.update(
        seed=seed,
        goal_validation=report,
        straight_line_m=report["straight_line_m"],
        stuck_events=counters["stuck"],
        flip_events=counters["flips"],
        log=str(log_path),
        trace=str(trace_path),
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 123])
    parser.add_argument(
        "--goals", default=None,
        help="semicolon-separated 'x,y' goals, one per seed, in the same order as "
             "--seeds. One string rather than a list because a bare negative "
             "coordinate reads as an option flag. For the same reason, pass it with "
             "an equals sign whenever the FIRST goal's x is negative: "
             "--goals=-45.0,77.94;52.33,-66.98 (the space-separated form fails with "
             "'expected one argument'). "
             "Omit to draw goals deterministically from the seed - either way the "
             "goal is validated against the costmap the running system builds."
    )
    parser.add_argument("--tolerance-m", type=float, default=1.5, help="M4's arrival bar")
    parser.add_argument("--timeout-s", type=float, default=3600.0)
    parser.add_argument("--graph-timeout-s", type=float, default=150.0,
                        help="abort if no /ground_truth/pose arrives within this")
    parser.add_argument("--max-goal-publishes", type=int, default=20,
                        help="give up (ABORT_NO_PATH) after this many goals with no plan back")
    parser.add_argument("--min-m", type=float, default=60.0)
    parser.add_argument("--max-m", type=float, default=100.0)
    parser.add_argument("--out", default=None, help="results directory (default: ./m4_acceptance_<stamp>)")
    parser.add_argument(
        "--record-signals", action="store_true",
        help="also log /odom, /imu and ground truth at 10 Hz per run - the raw material "
             "for judging a slip detector offline (~5 MB/hour/run)"
    )
    parser.add_argument("--watch", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--goal", help=argparse.SUPPRESS)
    parser.add_argument("--trace-csv", help=argparse.SUPPRESS)
    parser.add_argument("--result-json", help=argparse.SUPPRESS)
    parser.add_argument("--signals-csv", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.watch:
        return run_watcher(args)

    goals = [None] * len(args.seeds)
    if args.goals:
        parsed = [g for g in args.goals.split(";") if g.strip()]
        if len(parsed) != len(args.seeds):
            parser.error(
                f"--goals gave {len(parsed)} goals for {len(args.seeds)} seeds - "
                "one 'x,y' per seed, semicolon-separated"
            )
        goals = [tuple(float(v) for v in g.split(",")) for g in parsed]

    out_dir = Path(args.out) if args.out else REPO_ROOT / f"m4_acceptance_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Results -> {out_dir}", flush=True)

    results = []
    for seed, goal in zip(args.seeds, goals):
        print(f"\n=== seed {seed} ===", flush=True)
        started = time.time()
        result = run_seed(seed, goal, args, out_dir)
        result["started"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started))
        results.append(result)
        (out_dir / "summary.json").write_text(json.dumps(results, indent=2))
        print(
            f"[seed {seed}] {result['verdict']}"
            + (
                f" - ground truth {result['gt_error_m']:.1f} m from the goal after "
                f"{result['gt_travelled_m']:.1f} m travelled, EKF divergence "
                f"{result['divergence_m']:.1f} m, {result['stuck_events']} stuck events, "
                f"{result['flip_events']} flips"
                if "gt_error_m" in result else ""
            ),
            flush=True,
        )

    passes = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"\n=== M4 acceptance: {passes}/{len(results)} (judged on ground truth) ===")
    print(f"{'seed':>6} {'verdict':>20} {'gt error':>9} {'travelled':>10} {'diverg':>8} {'stuck':>6} {'flips':>6}")
    for r in results:
        if "gt_error_m" in r:
            print(
                f"{r['seed']:>6} {r['verdict']:>20} {r['gt_error_m']:>8.1f}m "
                f"{r['gt_travelled_m']:>9.1f}m {r['divergence_m']:>7.1f}m "
                f"{r['stuck_events']:>6} {r['flip_events']:>6}"
            )
        else:
            print(f"{r['seed']:>6} {r['verdict']:>20}")
    false_arrivals = [r for r in results if r.get("goal_reached_published") and r["verdict"] != "PASS"]
    if false_arrivals:
        print(
            f"\n{len(false_arrivals)} run(s) published /goal_reached while ground truth "
            "disagreed - the reason this harness does not trust that topic:"
        )
        for r in false_arrivals:
            print(f"  seed {r['seed']}: claimed arrival at {r['goal_reached_gt_error_m']:.1f} m true error")
    return 0 if passes == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
