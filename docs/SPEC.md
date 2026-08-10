# Regolith — Project Specification (as of 2026-07-21)

This is a snapshot brief for a developer team picking up the project cold. It
describes the system **as it is actually built right now**, not the
long-term vision (that lives in `PLAN.md` and the top half of
`docs/architecture.md`). Where the two diverge, this document wins — this is
the current, working "hello world" PoC.

For narrative/history, `PROGRESS.md` is the day-by-day log; this document is
the synthesized state.

---

## 1. What this is

A ROS 2 + Gazebo simulation in which a procedurally generated lunar terrain
is loaded, a 4-wheel skid-steer rover spawns on it, and the rover
autonomously plans and drives to a clicked (or scripted) goal, avoiding
craters and rocks — entirely from a costmap derived from the world's own
heightmap, with pose estimated from fused wheel odometry + IMU (no GPS, no
visual odometry yet).

It is a **seed demo** for an NLnet-funded open-source project ("Regolith"),
positioned as a genuine fork of [Autoware](https://autoware.org/) adapted
for GPS-denied, rough-terrain rover autonomy rather than road-driving cars.
All milestones M0–M5 defined in `PLAN.md` are done or substantially done;
see §7 for exactly what's still open.

One command reproduces it: `./scripts/demo.sh [--seed N]`.

---

## 2. Repository layout

Two repos, mirroring upstream Autoware's own meta-repo/universe split:

- **`regolith`** (this repo) — thin meta-repo. No package source of its
  own. Holds `regolith.repos` (pins the packages repo), `scripts/`
  (`setup.sh`, `demo.sh`), and top-level docs (`PLAN.md`, `PROGRESS.md`,
  `README.md`, `docs/architecture.md`, this file).
- **`regolith.universe`** (checked out under `src/regolith.universe/`) — a
  genuine GitHub fork of `autowarefoundation/autoware_universe` (fork
  relationship + history preserved on `main`). All actual package code
  lives under `planetary/` inside it, in six new packages, namespaced
  `regolith_*`. The rest of the upstream tree (`control/`, `perception/`,
  `planning/`, etc.) is present but **unbuilt** — the build only compiles
  up to `regolith_bringup` (`colcon build --packages-up-to
  regolith_bringup`), so upstream car-specific code sits inert rather than
  being deleted. A proper `COLCON_IGNORE`/stripping pass is deferred (noted
  in `docs/architecture.md`).

### The six planetary packages (`src/regolith.universe/planetary/`)

| Package | Type | Role |
|---|---|---|
| `regolith_terrain_gen` | Python (ament_python) | Procedural lunar terrain generator: heightmap PNG, rock/crater manifest, Gazebo SDF world |
| `regolith_rover_description` | ament_cmake (URDF/xacro only) | Rover model: chassis, 4 wheels, IMU, camera, DiffDrive plugin |
| `regolith_vehicle_interface` | Python (ament_python) | Pure-pursuit trajectory follower — path → `cmd_vel`, goal arrival, stall/deviation detection |
| `regolith_costmap` | Python (ament_python) | Heightmap → `OccupancyGrid` traversability costmap |
| `regolith_planner` | Python (ament_python) | Cost-aware A* global planner, costmap → `Path` |
| `regolith_bringup` | ament_cmake (launch/config only) | All launch files, EKF config, mission scripts, flip-recovery node, start/goal markers |

No C++ in the new code — everything planetary is Python, deliberately kept
boring and readable (per `PLAN.md` §8's working agreements).

---

## 3. Runtime pipeline

```
seed --> regolith_terrain_gen (offline, at launch time)
           |  writes heightmap PNG + world SDF + manifest JSON to
           |  ~/.cache/regolith/worlds/seed_<N>/
           v
        Gazebo (gz-sim, DiffDrive plugin, IMU/camera sensors)
           |  ros_gz bridge: /cmd_vel, /odom, /imu, /camera, /clock, TF,
           |  plus a gz-sim-pose-publisher-system --> /ground_truth/pose
           v
sensor_covariance_relay.py  -->  /odom/with_covariance, /imu/with_covariance
           |  (fills in covariance gz-sim leaves at zero; fixes IMU frame_id)
           v
robot_localization ekf_node (config/ekf.yaml)
           |  fuses odom vx/vyaw + IMU orientation/angular velocity only
           v
        /odometry/filtered  (+ odom -> base_link TF)
           |
           v
regolith_costmap  --(/costmap, OccupancyGrid, latched)-->  regolith_planner
                                                               |
                                    /goal_pose (RViz click or tour_mission.py)
                                                               v
                                                          /planned_path (Path)
                                                               v
                                              regolith_vehicle_interface
                                              (pure_pursuit_node.py)
                                                               |
                                              /cmd_vel  +  /goal_reached
                                                               v
                                                         Gazebo DiffDrive
```

`flip_recovery_node.py` runs alongside, watching `/ground_truth/pose` and
issuing a Gazebo pose-reset + brief `/cmd_vel` override if the rover's
attitude exceeds a flip threshold (see §6).

### Key topics

| Topic | Type | Publisher | Consumer(s) |
|---|---|---|---|
| `/costmap` | `nav_msgs/OccupancyGrid` | `regolith_costmap` (latched, republished 1 Hz) | `regolith_planner`, `pure_pursuit_node` |
| `/goal_pose` | `geometry_msgs/PoseStamped` | RViz "2D Goal Pose" or `tour_mission.py` | `regolith_planner`, `mission_markers_node.py` |
| `/planned_path` | `nav_msgs/Path` | `regolith_planner` | `pure_pursuit_node`, RViz |
| `/odometry/filtered` | `nav_msgs/Odometry` | `ekf_node` | `regolith_planner`, `pure_pursuit_node`, RViz |
| `/ground_truth/pose` | `geometry_msgs/PoseStamped` | Gazebo pose-publisher plugin | `flip_recovery_node`, RViz (comparison only, never fed into EKF) |
| `/cmd_vel` | `geometry_msgs/Twist` | `pure_pursuit_node` (normal) / `flip_recovery_node` (during recovery) | Gazebo DiffDrive plugin |
| `/goal_reached` | `std_msgs/Bool` | `pure_pursuit_node` | `tour_mission.py`, `mission_markers_node.py` |
| `/mission_waypoints` | `nav_msgs/Path` | `tour_mission.py` (latched, once) | `mission_markers_node.py` |
| `/mission_markers` | `visualization_msgs/MarkerArray` | `mission_markers_node.py` (latched) | RViz |
| `/odom`, `/imu` | raw, zero-covariance | Gazebo bridge | `sensor_covariance_relay.py` only |
| `/odom/with_covariance`, `/imu/with_covariance` | covariance-filled | `sensor_covariance_relay.py` | `ekf_node` |

---

## 4. Package details

### `regolith_terrain_gen`

Deterministic from `--seed`. Composes: fractal Brownian motion base
roughness + a power-law crater field (bowl + raised rim) + a gentle regional
slope (`config.py`: `TerrainConfig` dataclass holds every tunable —
`world_size_m=200`, `heightmap_resolution_px=513`, `height_range_m=10`,
`crater_count=60`, sizes 2–40 m, `rock_count=130` across 4 low-poly
variants, sun at 12° elevation / 235° azimuth). Outputs, per seed, to
`~/.cache/regolith/worlds/seed_<N>/`:
- 16-bit heightmap PNG — the elevation source `regolith_costmap` plans
  against. Note it is *not* what Gazebo draws: see below.
- `terrain.obj` — the ground as an explicit triangle mesh in world
  coordinates, which is the visual Gazebo renders. A `<heightmap>` visual
  goes through Ogre-Next's Terra and is point-sampled coarser with distance,
  so distant ground is drawn below where the data puts it and the rocks
  standing on it visibly hang in the air. A `<mesh>` has no level of detail.
  See `terrain_mesh.py` and PROGRESS.md's "Floating rocks, round four".
- Gazebo SDF world (generated from a template)
- A JSON **manifest**: crater positions/radii, rock positions/scale, spawn
  zone — the same manifest both the Gazebo world and `regolith_costmap`
  read, so what the rover physically encounters and what the costmap
  "knows about" are guaranteed consistent.
- A guaranteed-clear circular spawn zone (`spawn_zone_radius_m=12`, default
  centered at origin) kept free of craters/rocks.

CLI entry point: `cli.py`. Invoked by the launch files, not run standalone
in the normal demo flow.

### `regolith_rover_description`

URDF/xacro only (no Python/C++ nodes). ~Leo-Rover-sized: `chassis_mass=6.0
kg`, `wheel_radius=0.09 m`, `wheel_separation=0.46 m`, 4 independently
Xacro-macro'd wheels (`front_left/right`, `rear_left/right`), each with
correct cylinder inertia. Sensors: an `imu_link` (Gazebo IMU sensor,
topic `imu`) and a forward-tilted `camera_link` (Gazebo camera sensor,
topic `camera`) with an optional `gz-sim-camera-video-recorder-system`
plugin (off by default). Drivetrain is Gazebo's built-in DiffDrive plugin,
bridged to ROS via `ros_gz_bridge`.

### `regolith_vehicle_interface` — `pure_pursuit_node.py`

The trajectory follower. Subscribes to `/planned_path`, `/odometry/filtered`,
`/imu`, `/costmap`, `/goal_pose`; publishes `/cmd_vel` and `/goal_reached`.
Parameters (all `declare_parameter`, overridable via launch):

| Param | Default | Purpose |
|---|---|---|
| `lookahead_distance_m` | 1.5 | pure-pursuit lookahead |
| `base_speed_mps` | 0.2 | nominal forward speed |
| `max_angular_velocity` | 0.3 | rad/s cap |
| `goal_tolerance_m` | 1.5 | arrival radius (measured to the path's last waypoint — see §7 caveat) |
| `path_deviation_limit_m` | 4.0 | triggers a stop when off-path this far |
| `stall_timeout_s` | 8.0 | triggers a stop if not making progress |
| `control_period_s` | 0.1 | 10 Hz control loop |
| `flipped_attitude_deg` | 60.0 | own attitude guard (independent of `flip_recovery_node`'s) |

Recovery behavior per `PLAN.md`: stop-and-flag on deviation/stall, no
elaborate FDIR.

### `regolith_costmap` — `costmap_node.py`

Single-shot: reads the terrain manifest JSON + heightmap PNG once at
startup (path via `manifest_path` param, produced by `regolith_terrain_gen`
during launch), computes a cost grid (slope via gradient, lethal above
`slope_lethal_deg=20°`, plus rock footprints from the manifest, inflated by
`rover_radius_m=0.3`), converts to an `OccupancyGrid` at `resolution_m=1.0
m/cell`, and republishes the same latched message every second (transient
local + `depth=1` QoS, so late subscribers still get it). It does not
re-read sensors — this is the PoC's explicit "map is known a priori"
simplification (§6 of `PLAN.md`; sensor-derived costmaps are out of scope).

### `regolith_planner` — `planner_node.py` / `astar.py`

Subscribes `/costmap`, `/odometry/filtered`, `/goal_pose`; publishes
`/planned_path`. `astar.py` is cost-aware A* (8-connected grid, diagonal
cost `√2`), not shortest-path: `_cost_multiplier = 1.0 + cost/20.0` biases
the search away from expensive-but-not-lethal cells (cost 100 = impassable,
explicit bounds/lethality check before search starts, returns `[]` if
start/goal is out of bounds or itself lethal). Grid cell size follows the
costmap's `resolution_m` (256×256 cells over the 200 m world → 0.781 m/cell
at the values actually used in the M4 acceptance run — see §7's arrival
caveat, this is where the "snapped to grid" behavior comes from).

### `regolith_bringup`

All the glue:
- `launch/hello_moon.launch.py` — the main entry point. Args: `seed`,
  `headless` (server-only Gazebo, default `false`; added specifically for
  unattended/CI-adjacent runs — sidesteps a known `gz sim` GUI
  crash-on-exit under WSLg, see `PROGRESS.md`), `mission` (`tour` runs
  `tour_mission.py` automatically; omit for manual goal-clicking in RViz),
  `rviz` (default `true`).
- `launch/terrain_only.launch.py`, `teleop_demo.launch.py`,
  `localization_demo.launch.py`, `autonomous_demo.launch.py` — narrower
  launches for each milestone, still usable standalone for debugging one
  layer at a time.
- `config/ekf.yaml` — see §5.
- `scripts/sensor_covariance_relay.py` — see §5, bug #1/#2 fixes.
- `scripts/flip_recovery_node.py` — see §6.
- `scripts/tour_mission.py` — 5-waypoint loop, advancing on `/goal_reached`,
  90 s per-waypoint timeout, 10 s start delay. Deliberately short legs
  (~10–20 m), **not** the full 60–100 m single-goal distance used in the M4
  acceptance check — chosen so the unattended demo doesn't gamble on the
  terrain-collision flip risk documented in §7.

  The waypoints are **derived from the live `/costmap`**, not hardcoded
  (`regolith_planner/tour.py`): each one has a clear cell neighbourhood, each
  leg is confirmed with the same `plan_path` A* the planner node runs, and
  legs are preferred whose straight line is blocked so the rover has to route
  around something. Deterministic from `seed`. The previous hardcoded list
  was fine when chosen and stopped being drivable when the terrain changed —
  on seeds 42/7/123 it left 2–3 of 5 legs unplannable. See `PROGRESS.md`,
  "The tour picks its own waypoints".

---

## 5. Localization design (M3)

`robot_localization`'s `ekf_node`, not Autoware's `ekf_localizer` (absent
from this fork's checked-out tree entirely — see the reuse-log rationale in
`docs/architecture.md`). Fuses:
- **Wheel odometry**: `vx`/`vyaw` only, **not** position or absolute yaw.
  Skid-steer dead-reckoning yaw was measured ~3x off from ground truth
  under an in-place-rotation test; since its own x/y integration used that
  same bad yaw internally, position is equally unreliable and feeding it in
  wouldn't help even with yaw fusion disabled.
- **IMU**: orientation + angular velocity only, not linear acceleration
  (double-integrating accelerometer noise is a known drift trap; wheel
  `vx` is the better velocity source).

`two_d_mode: true` — roll/pitch on slopes is real but not fused in this
PoC, kept out to keep the estimator small with only two sensor sources.

`sensor_covariance_relay.py` exists because gz-sim publishes all-zero
covariance on both `/odom` and `/imu` (REP-145: zero covariance = "unknown",
silently discarded by the EKF) and the IMU's `frame_id` is gz-sim's internal
sensor name with no matching TF frame — the relay fixes both by
republishing with small fixed diagonal covariances and the correct
`imu_link` frame_id.

**Result (corrected 2026-07-21 — see `PROGRESS.md`'s "M3 drift
re-investigation" for the full trail)**: yaw tracks ground truth to 4+
decimal places. The 20–45% position-drift figure originally recorded here
turned out to be **measured before** the terrain-collision smoothing fix
(§6) and is not representative of the current codebase — it was driven by
wheels slipping on the pre-fix collision boxes' cliff-like seams, which the
smoothing fix removed as a side effect. Re-measured on current terrain:
0.0% over short (~4–16 m) straight-line legs, 0.17–0.20% over a full 53 m
straight-line leg with no sign of growing with distance, and 2.5–4% on
gentle-turn (1–2 m radius) legs — all within the <5% target. These are
isolated localization-pipeline measurements (manual `/cmd_vel`, autonomy
idle), not a re-run of the full M4 autonomous course; that would be the
natural way to close this out completely.

---

## 6. Flip and stuck recovery (`flip_recovery_node.py`)

This node carries two independent detectors — both watch `/ground_truth/pose`,
both log clearly labeled recovery actions, but they catch different failure
modes and use different recovery mechanisms. (Terminology note: the flip
detector's own progressive-backoff-on-relapse behavior is informally called
"stuck" in its own parameter names/comments — a rover repeatedly re-flipping
at the same spot — which is a different thing from the second detector
below, also called "stuck," meaning upright-but-not-moving. Both live in
this file; check which one a log line is about before assuming.)

**Flip detector**: if attitude exceeds `flip_threshold_deg=60°` for
`debounce_s=1.0`, teleports the rover back to a recorded earlier pose
(progressive backoff: starts at `backoff_s=2.0` sim-seconds back, grows up
to `max_backoff_s=40.0` if a re-flip happens within `relapse_window_s=20.0`
of the last reset), lifted `clearance_m=0.3` above recorded ground height,
with a `cooldown_s=5.0` re-arm delay. This exists because of a real physics
limitation: gz-physics/dartsim has no native heightmap/mesh collision, so
terrain collision is approximated as a grid of boxes, and the rover can flip
when crossing a box-boundary seam at the wrong angle/speed. Explicitly
labeled a *simulated* recovery in every log line — a wheeled rover cannot
physically self-right, so this would not exist on real hardware.

**Stuck detector** (added 2026-07-21, see `PROGRESS.md`'s "M3 drift
re-investigation"): catches a different, unrelated failure — an
intermittent dartsim static-friction lock during tight skid-steer turns
(low lunar-gravity wheel normal force → narrow friction cone → the contact
solver occasionally collapses to all-static and the wheels stop rotating
entirely, while the rover stays upright and so is invisible to the flip
detector above). Watches for ground-truth speed below
`stuck_min_speed_mps=0.02` while `/cmd_vel` commands more than
`stuck_min_commanded_mps` (0.03 m/s-equivalent, linear + angular combined),
sustained past `stuck_debounce_s=3.0`. Recovers by taking over `/cmd_vel`
for `stuck_nudge_duration_s=1.0` with a straight `stuck_nudge_speed_mps=0.2`
command at `stuck_nudge_rate_hz=30` (faster than `pure_pursuit_node`'s
10 Hz control loop, so the override actually reaches gz-sim). Unlike the
flip case, this is *not* labeled simulated — a real rover's FDIR could
plausibly attempt the same straight-line nudge to break a traction lock.
Confirmed rare (roughly 1-in-4 to well under 1-in-20 depending on the
sample, not reliably reproducible on demand) and confirmed not caused by
terrain-collision geometry (checked the collision mesh at an actual stall
location — flat, no nearby seam). Detection logic is covered by a
standalone unit test (no Gazebo involved); the recovery mechanism itself
was validated by manually confirming a straight-line command broke a live
lock during the investigation. This is the current single biggest open
stability item — see §7.

---

## 7. Known gaps and open items (be honest about these)

1. ~~M3 position drift (20–45%, target <5%)~~ **Retracted 2026-07-21**: this
   figure was measured before the terrain-collision smoothing fix and isn't
   reproducible on current code — see §5's corrected result (0–4% measured,
   within target) and `PROGRESS.md`'s "M3 drift re-investigation" for the
   full trail, including why the original straight-line "genuine wheel
   slip" explanation doesn't hold up either (it was the same pre-fix
   collision-seam artifact). Re-measuring drift during a full M4-style
   autonomous run (rather than the isolated manual legs used so far) would
   close this out completely.
2. **A rare, intermittent wheels-locked-but-upright stall in tight turns**
   (found while re-investigating #1 above, unrelated to it) — see §6's
   stuck detector. Root cause: a dartsim static-friction lock under
   lunar-gravity-reduced wheel normal force during lateral scrub, not a
   terrain-geometry defect (checked directly) and not caught by the flip
   detector (no tip-over involved). A detector + recovery now exists;
   its detection logic is unit-tested, but the fix has not yet been
   observed catching a *naturally re-occurring* stall live (the failure is
   rare enough that none recurred across ~20 stress-test attempts during
   this work) — so treat it as validated-in-isolation, not
   validated-end-to-end, until one is caught in the wild.
3. **Terrain-collision flip risk on long autonomous runs** — root cause is
   the box-grid collision approximation (§6), not the planner/controller.
   `flip_recovery_node.py` mitigates it (verified: zero relapse loop on a
   deliberately induced flip). The **full 60–100 m / 3-consecutive-seed M4
   acceptance check has since been re-run and passed 3/3** with zero flips
   after a terrain-collision fix (see `PROGRESS.md`, "Rover flip fix" and
   the most recent "M4 acceptance check" sections) — but `tour_mission.py`
   still deliberately uses short legs rather than the full distance, so the
   unattended one-command demo itself doesn't carry that risk.
4. **Goal arrival tolerance is grid-snapped, not exact**: `/goal_reached`
   fires based on distance to the *planned path's last waypoint*, which is
   the goal snapped to the nearest costmap cell center (0.781 m/cell at
   256×256 over the 200 m world) — not the raw published goal coordinate.
   A stricter check (rover's final ground-truth position vs. the original
   raw goal) measured 1.67–2.01 m across the three M4 acceptance runs,
   nominally over the plan's 1.5 m bar, though the grid-snap alone accounts
   for up to ~0.55 m of that gap. The system's own tolerance check passed
   in all three cases. A tighter final-approach behavior independent of the
   grid would be the legitimate fix if exact-coordinate arrival matters more
   than it does for this PoC.
5. **`smoothing_passes` / `overlap_frac`** (terrain-collision box-grid
   tunables) are not swept for a formally optimal value; current defaults
   work (verified) but 2 passes vs. the default 3 is also an option with a
   documented trade-off (max lip height) in `PROGRESS.md`.
6. **Cinematic GUI-follow-camera recording** isn't achievable from this
   headless WSLg dev session — documented as a manual step for whoever next
   has a GUI-attached session.
7. **Upstream stripping**: the untouched upstream `autoware.universe` tree
   is excluded from the build via `--packages-up-to`, not via
   `COLCON_IGNORE`/deletion as the plan's stripping policy eventually calls
   for — deferred, not done.
8. **Concurrent-launch graph collision** — *addressed 2026-07-23, not an open
   gap anymore, recorded here for continuity*: an overnight freeze was
   root-caused to two overlapping `hello_moon.launch.py` invocations sharing
   one DDS domain and merging into a single ROS graph over identical topic
   names (`/goal_pose`, `/clock`, `/cmd_vel`, ...). Three layers now guard
   this: `demo.sh`'s preflight process-kill, `on_exit=Shutdown()` on every
   long-running node so one dying node tears the whole tree down, and — the
   structural backstop — each `hello_moon.launch.py` invocation now claims a
   **private `ROS_DOMAIN_ID`** (lock-file registry under
   `~/.ros/regolith_domain_ids/`, flock-serialised so two simultaneous
   launches are *guaranteed* distinct ids, stale claims self-healed via a
   PID-liveness check). Between any two launches that both claim an id, graph
   isolation is absolute regardless of invocation path; the only residual is
   id exhaustion beyond 101 concurrent sims (falls back to a random pick),
   unreachable on this PoC's hardware. See `PROGRESS.md`'s "Overnight freeze"
   and "Per-launch ROS_DOMAIN_ID isolation" sections.
9. Local `main` is ahead of `origin/main`, unpushed, as of this writing
   (commit count has grown since this figure was last checked — see
   `git status` for the current count).

---

## 8. Build & run (for reference — see README.md for the full copy-pasteable version)

```bash
git clone https://github.com/Regolith-Project/regolith.git
cd regolith
./scripts/setup.sh        # pulls in regolith.universe, rosdep install, colcon build --packages-up-to regolith_bringup
./scripts/demo.sh          # builds if needed, launches hello_moon.launch.py with mission:=tour
```

Manual goal-clicking instead of the scripted tour:
```bash
source install/setup.bash
ros2 launch regolith_bringup hello_moon.launch.py seed:=42
# then use RViz's "2D Goal Pose" tool
```

Environment: ROS 2 Humble, Gazebo Harmonic (gz-sim 8) via `ros_gz`,
Ubuntu 22.04 or WSL2 with WSLg (NVIDIA GPU via D3D12 passthrough — no Linux
NVIDIA driver installed inside WSL). `MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA`
needed on hybrid AMD/NVIDIA laptops.

CI: `.github/workflows/regolith-build.yaml` in `regolith.universe` —
build-only (`colcon build --packages-up-to regolith_bringup` in a
`ros:humble-ros-base` container), triggered on changes under `planetary/`.
No simulation/GPU rendering in CI.

---

## 9. Explicitly out of scope (do not build without a deliberate decision to expand scope)

Per `PLAN.md` §9: visual odometry/SLAM, sensor-derived costmaps (the
costmap is heightmap-derived, not perception-derived), additional rover
models/kinematics, ML terrain classification, adaptive speed governors,
FDIR beyond stop-and-replan, real hardware, ROS 1 bridges, web UI/telemetry
dashboards. These are the natural "next milestone" items, not omissions.
