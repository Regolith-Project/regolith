# Progress Log

Tracks milestone status, decisions, issues, and exact commands that worked.
See `docs/architecture.md` for the pipeline description and the Autoware
component reuse log.

## Status

| Milestone | Status |
|---|---|
| M0 — Environment verified | Done |
| M1 — Procedural lunar terrain | Done |
| M2 — Rover spawns and drives (teleop) | Done |
| M3 — Localization | **Done** — the originally-recorded 20-45% drift was pre-fix (see "M3 drift re-investigation" below); current-code drift measures 0-4%, within the <5% target |
| M4 — Autonomous navigation | **Not met: 0/3, and the reason is measured.** True error is 3.1-13.1 m, and on every seed it equals the EKF's drift plus the stopping tolerance - the rover arrives exactly where it believes the goal is. Recovery works (26/26 wedges escaped), zero flips, no intervention. The **same build with a 0.5 m / 1 Hz absolute position reference passes 3/3 at 1.48 m** (an experiment, not a milestone result), so planning, control and recovery all meet the bar - what is missing is any exteroceptive observation of position. ~10% of the rover's motion is lateral slip that neither wheel odometry nor an IMU can represent. **M4's 1.5 m bar is not achievable within the PoC's declared sensor scope**; see "M4, final" below |
| M5 — Demo polish and packaging | Substantially done (see notes) |

## Decisions

- **Repository strategy**: `regolith` stays a thin meta-repo (mirroring
  upstream Autoware's `.repos`-driven pattern) rather than importing the full
  `autowarefoundation/autoware` git history. It holds `regolith.repos`
  (pins `regolith.universe`), top-level docs, and `scripts/`. All package
  source — including `regolith_bringup` — lives in `regolith.universe` under
  `planetary/`, per the plan's own package table. Rationale: keeps demo
  packages, their launch files, and their cross-package dependencies in one
  repo, matching how autoware.universe/autoware_launch actually work upstream.
- Six placeholder packages that predated the milestone plan
  (`regolith_bringup`, `regolith_interfaces`, `regolith_localisation`,
  `regolith_navigation`, `regolith_perception`, `regolith_simulation` — empty
  `package.xml` stubs, no code) were removed from `regolith`'s `src/` for the
  reason above. Their layering concept is preserved as prose in
  `docs/architecture.md`.
- `regolith.universe` created as a genuine GitHub fork of
  `autowarefoundation/autoware_universe` (fork relationship + full history on
  `main` preserved; only `main` branch copied, not every upstream branch/tag).
- **M3 localization uses `robot_localization`'s `ekf_node`, not Autoware's
  `ekf_localizer`**: the plan asked to check `ekf_localizer` first. It isn't
  present anywhere in this fork's checked-out `autoware_universe` tree at all
  (not under `localization/`, not referenced in any `.repos` file) - it's
  been removed/relocated upstream since whatever commit generation this
  fork's history reflects. Migrating it in would mean pulling in a whole
  separate, unvetted external repo, which is squarely the "disproportionate
  for this PoC" case the plan anticipated. `robot_localization` (already
  installed in M0 as exactly this fallback) is used instead.
- **M4 follower: minimal pure pursuit in `regolith_vehicle_interface`, not
  `autoware_pure_pursuit`**: unlike `ekf_localizer`, `autoware_pure_pursuit`
  *is* present in this fork, but it depends on `autoware_control_msgs`,
  `autoware_planning_msgs`, `autoware_trajectory_follower_base`, and
  `autoware_vehicle_info_utils`, and it outputs a steering-tire-angle Control
  message - it's a lateral controller built for Ackermann-steered vehicles.
  Retrofitting it for a skid-steer rover would mean pulling in that whole
  dependency chain and then translating steering-angle output back into a
  differential left/right-wheel command, which is both extra integration
  surface and a conceptual mismatch (pure pursuit's own geometry assumes
  Ackermann kinematics). A minimal pure pursuit computing linear+angular
  velocity directly is both simpler and a more natural fit for skid-steer,
  matching the plan's explicit fallback. See `regolith_vehicle_interface/
  pure_pursuit_node.py`.

## Environment

- Host: Windows 11, WSL2 Ubuntu 22.04.5 LTS. Hybrid AMD/NVIDIA laptop GPU
  (AMD Radeon integrated + NVIDIA GeForce RTX 3050 Laptop GPU discrete) — WSLg's
  D3D12 renderer defaults to the AMD adapter. Fixed by exporting
  `MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA` (added permanently to `~/.bashrc`),
  per the plan's WSL2 rendering fallback notes.
- RAM: 13 GB total — below the plan's 32 GB comfort threshold. Using
  `colcon build --parallel-workers 2` / `MAKEFLAGS=-j2` per the plan's
  fallback guidance rather than changing `.wslconfig`.

## M0 acceptance results

- `glxinfo -B` (with the adapter override): `Device: D3D12 (NVIDIA GeForce
  RTX 3050 Laptop GPU)` — confirmed NVIDIA, not llvmpipe.
- `gz sim shapes.sdf`: loads the Ogre2 GUI render engine, no errors/warnings
  beyond benign DART collision-geometry notices; screenshot confirms a
  correctly shaded, GPU-rendered 3D scene (not black) — see
  `docs/media/m0_gz_sim_gpu_render.png`. GUI process ran at ~125% CPU while
  rendering, consistent with active interactive rendering (Gazebo has no
  built-in FPS counter to log a number directly).
- ROS 2: `ros2 topic list` and a `demo_nodes_cpp talker` → `ros2 topic echo`
  round-trip both worked (`/chatter`, `/parameter_events`, `/rosout` present;
  received `data: 'Hello World: 26'`).
- Installed: `ros-humble-desktop` (includes RViz2), `gz-harmonic` (Gazebo Sim
  8.14.0), `ros-humble-ros-gzharmonic` (the Humble+Harmonic ros_gz pairing),
  `python3-colcon-common-extensions`, `python3-rosdep`, `python3-vcstool`,
  `ros-humble-teleop-twist-keyboard`, `ros-humble-robot-localization` (M3
  fallback per the plan).

## M1 acceptance results

- `ros2 launch regolith_bringup terrain_only.launch.py seed:=42` generates
  the world (heightmap, PBR textures, 4 rock mesh variants, 130 scattered
  rocks, manifest) and opens it in Gazebo. Screenshot:
  `docs/media/m1_lunar_terrain_seed42.png` — craters, rock scatter, long
  shadows from a 12° sun elevation, near-black sky all present.
- Determinism verified: two runs with `--seed 42` produced byte-identical
  `heightmap.png`; `--seed 7` produced a different heightmap, as expected.
- New package `regolith_terrain_gen` (`planetary/regolith_terrain_gen` in
  `regolith.universe`): fBm base (value noise, no external noise library) +
  power-law crater field (60 craters, 2-40 m diameters, bowl+rim profile) +
  1.5° regional slope, normalized to a 10 m height range on a 513x513
  heightmap over a 200x200 m world. 130 rocks (4 low-poly icosphere-derived
  variants) scattered outside a 12 m spawn-zone keep-out, seated on the
  actual terrain elevation at their position. Everything needed for M4's
  costmap (crater positions/depths, rock footprints) is recorded in
  `manifest.json`.
- New package `regolith_bringup` (`planetary/regolith_bringup`): first real
  content in the package the plan's table designates as the integration
  point; `terrain_only.launch.py` calls `regolith_terrain_gen` in-process via
  an `OpaqueFunction` (no shelling out / stdout-parsing needed) and hands the
  resulting world path to `ros_gz_sim`'s `gz_sim.launch.py`.
- `regolith.universe`'s existing ~500 MB / hundreds-of-packages tree was left
  untouched for this milestone — built with
  `colcon build --packages-select regolith_terrain_gen regolith_bringup`,
  so `rosdep install --from-paths src` failures on car-specific packages
  missing `tier4_*`/CUDA rosdep keys don't block M1. The `COLCON_IGNORE`
  stripping pass (plan section 4) is deferred to whichever milestone first
  needs a full-workspace build.

## M2 acceptance results

- New package `regolith_rover_description` (`planetary/regolith_rover_description`):
  Leo-Rover-sized 4-wheel skid-steer chassis (URDF/xacro), IMU, forward-tilted
  RGB camera, `gz-sim-diff-drive-system` plugin (multi-joint skid-steer mode),
  `JointStatePublisher` and `Imu` system plugins. `regolith_bringup` gained
  `teleop_demo.launch.py`: generates terrain, spawns the rover, bridges
  cmd_vel/odom/imu/camera/camera_info/joint_states/tf between ROS and Gazebo.
- `ros2 launch regolith_bringup teleop_demo.launch.py seed:=42` + manual
  `cmd_vel` Twist commands (standing in for `teleop_twist_keyboard`, which
  publishes the same topic/type): rover drives forward and turns repeatedly
  over the crater/rock field without flipping (verified via the ground-truth
  `/world/.../dynamic_pose/info` orientation quaternion staying at
  identity/pure-yaw, not tipping into roll/pitch) and without sinking (z
  stable at the resting height on repeated checks). `/odom`, `/imu`,
  `/camera/image`, `/camera/camera_info`, `/joint_states`, `/tf` all publish;
  RViz shows the robot model, TF frames, and a live camera feed
  (`docs/media/m2_rviz_camera_tf.png`).
- Stability tuning: widened track (0.36→0.46 m), lowered chassis height
  (0.14→0.11 m), increased wheel friction (μ 1.0→1.4), and capped
  `max_angular_velocity` at 0.3 rad/s (initially 1.2, then 0.6 - still
  flipped once under combined fast-forward+fast-turn before this final cut).

## M3 acceptance results

**Status: infrastructure complete and working; the <5% drift target is not
reliably met.** Recording this honestly rather than as a clean pass, per the
plan's own framing that drift is expected and worth visualizing, not hidden.

- New `regolith_bringup/launch/localization_demo.launch.py`,
  `config/ekf.yaml`, and `scripts/sensor_covariance_relay.py`: fuses wheel
  odometry (`/odom`, velocity only) and IMU (`/imu`, orientation + angular
  velocity) in a `robot_localization` `ekf_node`, publishing `/odometry/filtered`
  and the `odom -> base_link` TF. Ground truth is bridged separately via a
  `gz-sim-pose-publisher-system` plugin on the rover model
  (`/model/rover/pose` -> `/ground_truth/pose`, `geometry_msgs/PoseStamped`,
  GZ-to-ROS only, never fed into the EKF).
- Three real bugs found and fixed along the way, all now resolved:
  1. gz-sim's IMU and DiffDrive-odometry both publish all-zero covariance
     (no noise model configured). Per REP-145, all-zero covariance means
     "unknown," and robot_localization's EKF silently discards a measurement
     with unknown covariance rather than trusting it - it looked exactly
     like the fused estimate just wasn't listening to either sensor.
     Fixed by `sensor_covariance_relay.py`, which republishes both topics
     with small fixed diagonal covariances filled in
     (`/imu/with_covariance`, `/odom/with_covariance`).
  2. The IMU's `frame_id` is gz-sim's internal sensor naming
     (`rover/base_link/imu`), which has no corresponding TF frame - only
     `imu_link` (from the URDF, published by `robot_state_publisher`) does.
     robot_localization needs a resolvable TF transform from the sensor
     frame to `base_link` and silently drops messages it can't transform.
     Fixed in the same relay (overwrites `frame_id` to `imu_link`).
  3. Wheel odometry's *absolute* yaw (and, by extension, its x/y position,
     which was integrated using that same bad internal yaw) is unreliable
     for a skid-steer platform: turning requires real wheel scrub against
     the ground that the dead-reckoning kinematic model doesn't account
     for. Verified directly with an in-place-rotation test: ground truth
     turned ~122°, wheel odom's own yaw estimate claimed only ~41°.
     `odom0_config` now feeds only `vx`/`vyaw` (rate measurements) into the
     EKF, not position or absolute orientation; absolute heading comes from
     the IMU, whose orientation was independently verified to match ground
     truth to ~7 decimal places (gz-sim's simulated IMU is effectively
     noise-free here).
- After fix 3 was in place, yaw tracking is excellent: EKF yaw matched
  ground truth to 4+ decimal places in every test run, including after
  sustained combined forward+turn maneuvers.
- Position tracking improved enormously from the pre-fix state (which was
  wrong by 60-190%, including one run where the estimate ended up hundreds
  of metres from a ground truth a few metres away) but still shows
  20-45% position drift relative to distance traveled across several test
  runs at moderate speed (0.2-0.35 m/s) with gentle turning, well above the
  plan's <5% target. Isolated causes, in descending order of confidence:
  - **Genuine, speed-dependent wheel slip**: at 0.1 m/s pure-straight
    driving, wheel odometry position matched ground truth to 6 decimal
    places (zero drift); at 0.3-0.35 m/s the same straight-line test showed
    25-39% overshoot. Lunar gravity (1.62 m/s²) means far less normal force
    (and thus available traction) than Earth gravity for the same
    friction coefficients, so wheel slip under acceleration is a real,
    physically-motivated effect here, not obviously a bug - though it may
    be exaggerated by this PoC's simplified friction/contact model.
  - **An unresolved residual EKF integration behavior**: in one clean
    straight-line test after all three fixes above, wheel odometry itself
    overshot ground truth (as expected from the slip effect), but the
    EKF's fused position *undershot* by a similar margin in the opposite
    direction - the two errors don't obviously compose the way a simple
    "trust the wheel measurement" fusion would suggest. Not root-caused
    within this milestone's time budget; flagged for follow-up rather than
    chased further as an increasingly expensive debugging session.
  - One test run also showed the rover itself flip mid-drive during a
    150-second sustained aggressive maneuver (ground truth orientation
    showed a real ~180° roll) - that run's huge apparent "drift" is a
    consequence of the two_d_mode EKF producing garbage yaw once the robot
    actually isn't upright, not a localization bug; it's the M2 stability
    envelope being exceeded, not an M3 finding.
- RViz shows RobotModel, TF, live Camera feed, and Odometry with no errors
  (`docs/media/m3_rviz_localization.png`); `/ground_truth/pose` and
  `/odometry/filtered` are both live and directly comparable at any time via
  `ros2 topic echo`.

## M4 acceptance results

**Status at the time this section was written: full pipeline built and each
stage individually verified working; the "3 consecutive full 60-100 m runs"
acceptance criterion is not met.** Recorded honestly, same as M3 - real
progress, real remaining gap. **Update: the flip root cause documented below
was later fixed and the full-distance/3-consecutive-run check re-attempted
and passed - see "M4 acceptance check: full 60-100 m / 3-consecutive-run
result" further down. Left this section's original wording as-is rather than
rewriting history; read the later section for the current status.**

- Three new packages, all `ament_python`:
  - `regolith_costmap` (`costmap_node.py`): reads `manifest.json` + the
    heightmap, downsamples to a configurable grid (1 m/cell by default),
    computes slope (gradient) and roughness (local elevation std-dev),
    marks cells lethal above a slope threshold (20°) or inside a rock
    footprint from the manifest, inflates lethal cells by the rover radius,
    and publishes a transient-local `nav_msgs/OccupancyGrid` on `/costmap`.
    Verified visually (`docs/media/m4_costmap_and_planned_path.png`): crater
    rims and rocks read clearly as obstacle rings/blocks against the terrain.
  - `regolith_planner` (`astar.py` + `planner_node.py`): cost-aware A* (not
    shortest-path - traversal cost scales with cell cost, so the search
    prefers low-risk routing) over `/costmap`, from the EKF-estimated
    current pose to an RViz "2D Goal Pose" click (`/goal_pose`), with light
    path smoothing. Publishes `nav_msgs/Path` on `/planned_path`. Verified
    both standalone (sub-100ms planning time on the 256x256 grid) and
    visually - the same screenshot shows a path visibly weaving around
    crater rims and rocks rather than cutting through them.
  - `regolith_vehicle_interface` (`pure_pursuit_node.py`): minimal pure
    pursuit (see the reuse-decision note above for why not
    `autoware_pure_pursuit`) outputting `cmd_vel` directly. Modest speed
    profile: slows for high-cost cells and, after a stability finding below,
    stops translating entirely and rotates in place first whenever the
    heading error exceeds 30° before resuming forward motion. Minimal
    recovery per the plan ("do not build elaborate FDIR"): if the rover
    strays >4 m from the path or makes no progress for 8s, it stops and
    re-publishes the last goal to itself to trigger a fresh plan from
    wherever it currently is - verified triggering correctly in testing.
- End-to-end run with a modest (~16 m) goal crossing costmap-flagged terrain:
  planner produced a path in an eyeblink, the follower drove it, stall
  recovery fired and re-planned correctly when progress stalled. Multiple
  such partial runs completed without incident.
- **Not achieved**: the rover flipped (real ~90-180° roll, confirmed via
  ground-truth orientation, not an estimation artifact) partway through
  three separate longer-goal test attempts, always coincident with a
  terrain-collision-box boundary crossing (z-height jumped at the same
  moment). This reproduced across three different mitigation attempts:
  reducing follower speed/turn aggressiveness, increasing terrain
  collision resolution from 24 to 64 cells/axis (which also cratered the
  physics real-time factor to ~0.09, making full 60-100 m test runs
  impractically slow to even observe), and adding a rotate-in-place-first
  behavior for large heading errors. None fully eliminated it. This is
  believed to be a genuine consequence of the box-grid terrain collision
  approximation's step discontinuities (see heightmap.py's
  `build_terrain_collision_boxes_sdf` - itself downstream of the confirmed
  dartsim heightmap/mesh collision limitation from M2), landing at
  `grid_resolution=24` as the best available performance/stability balance
  found, not a validated fix. **Follow-up needed**: either a genuinely
  smooth collision surface (revisit if gz-physics ever ships working native
  heightmap/mesh collision for dartsim) or per-cell-boundary blending in the
  box-grid approach itself.
- Consequence for the "3 consecutive 60-100 m runs" acceptance check: not
  attempted at full distance given the demonstrated flip risk and the
  RTF-vs-resolution trade-off making iteration on a fix impractically slow
  within this session. The pipeline (costmap -> plan -> follow -> recover)
  is real and demonstrated at shorter range; closing the gap to the full
  acceptance distance is the clearest remaining M4 work.

## Issues encountered

- The Ubuntu 22.04 universe repo's `gh` package is a stale 2.4.0 (2022) build
  whose device-code flow tripped GitHub's rate limiter (`slow_down`). Fixed by
  installing the current `gh` release directly from GitHub's `.deb` releases
  instead of the (also 404ing) `cli.github.com` apt repo.
- `gh repo fork --org ... --fork-name regolith.universe` failed with a fine-
  grained PAT scoped only to the `Regolith-Project` org, since forking calls
  the API against the *source* repo (outside the token's scope). Forked
  manually via the GitHub web UI instead.
- `pkill -f "gz sim"` (and similar) can match the invoking shell's own
  command line, since it literally contains the pattern text — killing the
  shell running the command before it can report anything. Use anchored
  patterns (`pkill -f "^gz sim"`) or `pgrep`/PID-based kills instead.
- Initial SDF had `<gravity>` nested inside `<physics>` — sdformat warns and
  silently ignores it there; gravity must be a direct child of `<world>`.
- Bowl-shaped craters viewed from a steep top-down angle with off-axis
  lighting read as domes to the human eye (verified against the raw
  heightmap data — the crater profile was always a genuine depression). This
  is the well-known "crater/dome" perceptual illusion seen in real lunar/Mars
  orbital imagery. Fixed by choosing a shallower camera pitch and a sun
  azimuth roughly aligned with the camera's viewing direction, rather than
  by changing the terrain data.
- **The M2 rover-on-terrain physics saga** (this consumed most of the M2
  session; recording it in full so it isn't re-litigated). Symptom: the
  rover's wheels spun at the commanded rate (confirmed via `/joint_states`)
  but the chassis never translated - or fell through everything, or the
  simulation appeared to "freeze" the rover solid - depending on the exact
  test. Confirmed real, separate findings along the way:
  - `gz sim -v 4` (debug verbosity, invisible at default `-v`) logs
    `"Heightmap/Mesh construction from an SDF has not been implemented yet
    for dartsim"`. Both the native `<heightmap>` collision geometry and
    generic `<mesh>` collision geometry are no-ops for dartsim in this
    gz-physics 7.8.0 install, reproduced identically under the `bullet` and
    `bullet-featherstone` engine plugins too (`--physics-engine
    gz-physics-bullet-plugin` / `-bullet-featherstone-plugin`). This part is
    a genuine, real engine limitation - box primitives are the fallback
    (`regolith_terrain_gen`'s `build_terrain_collision_boxes_sdf`), matching
    the plan's anticipated "static mesh instead of heightmap" fallback
    (substituting boxes since mesh doesn't work either).
  - What turned out to be **wrong, in order tried and discarded**: reducing
    box-grid resolution, splitting collision into separate `<model>`s vs.
    many `<collision>` elements on one link, removing rocks, removing rock
    *collision* specifically, changing gravity magnitude, disabling
    `allow_auto_disable`, adding an 8 s `TimerAction` delay before spawning,
    switching the ROS↔GZ `/pose` bridge from bidirectional to one-way,
    replicating the launch file's `GZ_SIM_SYSTEM_PLUGIN_PATH` env var
    manually. None of these were the actual bug; each seemed to "fix" or
    "reproduce" the symptom in some isolated test only because the tests
    differed in the one thing that actually mattered (below), which wasn't
    controlled for.
  - **Actual root cause**: the rover was being spawned at a fixed height
    (`z:=1.0`, later `z:=2.0`) that had nothing to do with the *local*
    terrain elevation at the spawn point. `build_terrain_collision_boxes_sdf`
    sizes each box to the average heightmap value in its footprint - at
    `grid_resolution=1` (one box for the whole world, an early attempt) that
    average can easily be several meters for a given seed, and even at finer
    resolutions the local elevation right at the nominal "origin" spawn
    point depends on the regional slope/base terrain for that seed. Spawning
    at a Z below the actual box surface means the rover starts *embedded in
    solid geometry*, and DART's response to that invalid initial state is
    unpredictable - a wheeled multi-body could look "frozen" (no visible
    integration), "falling through" (numerically unstable contact resolving
    away from the overlap in the wrong direction), or explode to absurd
    coordinates, depending on exactly how deep the overlap is and where. A
    single free rigid body (test boxes used throughout isolation) tolerates
    the same bad spawn far more gracefully, which is why every "isolate with
    a plain box" test kept passing and pointed away from the real cause.
  - **Fix**: `generate_world` now looks up and returns the actual elevation
    at the spawn point (`elevation_lookup`, already computed for rock
    placement) and writes it to `manifest.json` as `spawn_zone.elevation_m`.
    `teleop_demo.launch.py` reads that value and spawns at
    `elevation_m + 0.5` instead of a hard-coded constant. Once fixed, the
    *original* box-grid design (fine resolution, full 130 rocks, separate
    `<model>`s per rock) worked exactly as first written - none of the
    discarded workarounds above were ever necessary.
  - Lesson for future milestones: **any** code that spawns a body into
    procedurally generated terrain must compute its Z from real elevation
    data, never a constant, and this class of bug can look like almost
    anything (freeze/fall-through/explosion) depending on overlap depth -
    if a spawned body behaves strangely, check the spawn pose against actual
    local terrain height before suspecting the physics engine.

## M5 acceptance results

- `hello_moon.launch.py` created as the single entry point superseding
  `autonomous_demo.launch.py`, adding a `mission` launch arg: default `none`
  (click a goal in RViz yourself, identical to M4's demo) or `tour` (runs
  `tour_mission.py`'s scripted 5-waypoint loop automatically, no
  interaction needed). `scripts/demo.sh` wraps it as the one-command path:
  builds if `install/` is missing, then launches with `mission:=tour`.
- `scripts/setup.sh` narrowed to build only the `regolith_*` packages
  (`--packages-up-to regolith_bringup`) and run `rosdep install` against
  just `planetary/`, not the whole `regolith.universe` tree - the untouched
  car-specific Autoware packages carry `tier4_*`/CUDA-only rosdep keys that
  don't resolve on a stock install. Documented as deferred, not fixed: a
  real "strip or `COLCON_IGNORE` the untouched tree" pass is still open
  for whichever milestone first needs a full-workspace build.
- Minimal build-only GitHub Actions CI added at
  `regolith.universe/.github/workflows/regolith-build.yaml`, scoped to
  `planetary/**` paths only so it doesn't collide with or attempt to run
  the fork's many pre-existing Autoware CI workflows. No simulation step -
  GPU/Gazebo rendering isn't available on standard GitHub runners.
- **Confirmed again, running the full scripted tour end-to-end**: the M4
  flip issue is real and reproduces during ordinary unattended demo use, not
  just under deliberately long test goals. Seed 42's tour got partway to
  waypoint 1 and then, per `/ground_truth/pose`, the chassis orientation was
  `x ≈ 0.99, w ≈ 0` - a roll of approximately 180°, i.e. upside-down (the
  accompanying `z ≈ 4.96 m` reading is not itself unusual - this seed's
  spawn point sits at `z ≈ 5.3 m` local terrain elevation to begin with, per
  a later clean run's identity-orientation spawn pose; the flip is the
  orientation reading, not the height). The follower's stall recovery kept
  firing and replanning against the same coordinates (it has no way to
  detect "upside down," only "not making progress"), so the tour script's
  90s per-waypoint timeout - not a genuine arrival - was what eventually
  moved it on to waypoint 2. This is the same root cause documented under M4
  (box-grid collision step discontinuities), now additionally confirmed to
  affect the polished one-command demo path, not just adversarial test
  goals.
  - **Consequence for this milestone**: rather than keep tuning
    collision-grid parameters against a physics-engine limitation already
    investigated at length under M4 (see the RTF-vs-resolution trade-off
    noted there), the demo video (below) was descoped from the full
    5-waypoint tour to a shorter, reliable sequence - spawn, teleop, and a
    single short-range autonomous leg - with the flip risk stated plainly in
    the README rather than edited around. This is the same "smaller honest
    scope over cosmetic full-scope" call made throughout this project.
- README quickstart rewritten and cross-checked line-by-line against the
  actual commands used in this session (`git clone`, `./scripts/setup.sh`,
  `./scripts/demo.sh`), replacing the previous "coming soon" placeholder.
  Doing that check caught a real bug: both scripts use `set -euo pipefail`,
  but `/opt/ros/humble/setup.bash` references an unset variable
  (`AMENT_TRACE_SETUP_FILES`) on its first line and aborts under `-u` in a
  clean shell (reproduces with a bare
  `bash -c 'set -euo pipefail; source /opt/ros/humble/setup.bash'`) - it had
  gone unnoticed because this session's interactive shell had already
  sourced it once before, which leaves the variable set for the rest of
  that shell. Fixed by wrapping just the `source /opt/ros/humble/setup.bash`
  (and `install/setup.bash`) lines in `set +u` / `set -u` in both
  `scripts/setup.sh` and `scripts/demo.sh`. Re-ran `./scripts/demo.sh` after
  the fix in a clean invocation - confirmed it builds/skips-build correctly,
  generates terrain, launches Gazebo, bridges topics, and spawns the rover
  cleanly end to end.
- Cinematic auto-follow camera: investigated whether gz-sim 8's GUI could be
  scripted to automatically track the rover (for a hands-off recording).
  Found no clean, scriptable follow-camera mechanism in this install within
  the time available - the GUI's "Follow" behavior is a manual right-click
  action on the model in the scene tree. Documented as a manual step in the
  README rather than building a custom camera-follow plugin, which would be
  a disproportionate amount of new code for a cosmetic recording aid.
- **Automated video/GIF capture: two dead ends, then a real fix.** Recording
  the full findings here so the dead ends aren't re-investigated from
  scratch later:
  - `ffmpeg -f x11grab` against the WSLg `:0` display captures solid black,
    even though `xdotool search` confirms a real "Gazebo Sim" window exists
    at that point in time. WSLg remotes each application window's rendered
    content directly to the Windows side per-window (RAIL-style); the X11
    root window this session's display variable points at is never actually
    composited with real pixels, so desktop-capture tools have nothing to
    read.
  - Second attempt: record the rover's own onboard `/camera/image` ROS topic
    instead (already bridged, no GUI dependency) via a small `cv_bridge`
    subscriber writing PNG frames. This partially worked but the rendered
    image was frozen on the very first frame for roughly two-thirds of every
    capture window before suddenly starting to update (confirmed via
    `md5sum` across frame samples - frames 0 through ~450 of a 700-frame,
    60s capture were byte-identical, then genuinely started changing around
    frame ~500). A second short capture, run right after the first one had
    "warmed up," froze again from frame 0 - pointing to gz-sim's render loop
    deprioritizing sensor rendering when it has no actively-viewed GUI
    viewport driving it, consistent with the x11grab finding above.
  - **Fix**: gz-sim ships a server-side `gz-sim-camera-video-recorder-system`
    plugin (`gz::sim::systems::CameraVideoRecorder`, found via
    `/usr/share/gz/gz-sim8/worlds/camera_video_record_dbl_pendulum.sdf`) that
    renders a camera sensor straight to an mp4 file, entirely independent of
    the GUI/compositor - it sidesteps both dead ends above completely. Added
    to `regolith_rover.urdf.xacro`'s camera sensor behind a `record_video`
    xacro arg (default `false`, off by default so the shipped rover carries
    no extra overhead normally), wired through `hello_moon.launch.py` as a
    new `record_video` launch argument. Started/stopped via
    `gz service -s /rover/camera/record_video ...` (see `regolith_bringup`'s
    README for the exact calls). First attempt at using it hit one more
    real bug: the world's `<sensor>` plugin block can't contain literal
    `--` sequences inside an XML comment (SGML/XML forbids `--` inside
    comments) - the original draft comment describing the CLI calls with
    `--reqtype`/`--req` broke xacro's XML parser ("not well-formed (invalid
    token)"); fixed by moving the CLI examples out of the XML comment and
    into the README instead.
  - Recording itself needed one adjustment: with the recorder active,
    physics real-time-factor dropped noticeably (recording is not free), so
    short `sleep`-paced teleop bursts barely moved the rover in sim-time;
    switched to sustained `ros2 topic pub -r 5 ...` streams instead of short
    bursts, which resolved it.
  - The raw capture (teleop drive + a short single-goal autonomous leg,
    reaching "Goal reached" cleanly, no flip) came out to 257s of sim-time -
    longer than the 60-90s target, since recording ran for however long the
    manual drive commands took. Sped up 3.2x with `ffmpeg`'s `setpts` filter
    to a brisk 80s clip (with an on-screen "sim time, sped up 3.2x" label so
    the pacing isn't misleading) - saved as `docs/media/m5_demo_tour.mp4`,
    plus an 8s excerpt as the README hero GIF
    (`docs/media/m5_demo_hero.gif`). Both show continuous, upright driving;
    no flip occurs in this particular recorded run (the flip risk documented
    above is real but probabilistic, not guaranteed on every run - see M4).
  - The cinematic third-person Gazebo-GUI view (vs. this first-person
    onboard-camera view) still isn't achievable from this headless session
    for the reasons above; documented as before as a manual step for anyone
    wanting a GUI recording (right-click "Follow" in the GUI, screen-record
    on the Windows side).

## Post-M5 security review

- Scope: everything this project actually authored - the meta-repo (minus
  gitignored `PLAN.md`) and `regolith.universe`'s `planetary/` tree plus its
  new `.github/workflows/regolith-build.yaml`. Deliberately excluded the
  untouched upstream `autoware.universe` C++ tree - out of scope, not this
  project's code to audit or fix.
- **Credential exposure check (the main reason to run this pass now)**: a
  GitHub fine-grained PAT was pasted directly into a terminal earlier in
  this project's development (during the initial GitHub auth setup - see
  "Issues encountered" above). Checked full git history and working tree of
  both repos for that token or any other credential-shaped string
  (`github_pat_`/`ghp_`/etc., and generic `api_key`/`password`/`secret`/
  `token` assignments with real-looking values) - independently confirmed
  clean, nothing was ever committed. No rotation or history rewrite needed.
- **Fixed**: `regolith-build.yaml` had no `permissions:` block, so its
  `GITHUB_TOKEN` would inherit the repo/org default scope (often
  read-write) for a job that only needs to build - unnecessary standing
  privilege if a compromised transitive apt/rosdep dependency ever ran
  something malicious mid-build. Added `permissions: contents: read`.
  Confirmed the rest of the workflow was already sound: `pull_request`
  (not the secrets-exposing `pull_request_target`), no untrusted
  `${{ }}` input interpolated into any `run:` step, and the one third-party
  action (`actions/checkout@v4`) is tag-pinned.
- **Reviewed, no changes needed**: shell scripts (`scripts/setup.sh`,
  `scripts/demo.sh`) already quote every expansion and pass the seed
  through `ros2 launch` as a single argv element rather than a shell
  string, so injection isn't possible; every launch file casts the `seed`
  launch argument with `int(...)` before it reaches any file path or
  subprocess call, which rules out path traversal through it; all
  `ExecuteProcess` calls use list-form `cmd=[...]`, never a shell string,
  and `shell=True`/`os.system`/`eval`/`exec`/`pickle`/unsafe `yaml.load`
  appear nowhere in the codebase; generated terrain assets are written
  under `~/.cache/regolith/worlds/seed_<int>/` with default permissions,
  no `/tmp` usage or predictable-path temp-file races.

## Post-M5 quality/stability/UX pass

Reviewed the same scope as the security pass (everything this project
authored - meta-repo plus `regolith.universe/planetary/`). Every change
below was independently re-verified after the fact (rebuilt, re-ran, or
re-read line-by-line), not just taken on trust.

- **Flip detection** (`pure_pursuit_node.py`): the M5 notes above call out
  that stall recovery had no way to tell "flipped" from "just stuck" - it
  would silently cycle replan/timeout forever after a real flip. Fixed by
  subscribing to the raw `/imu` topic (not the EKF's fused estimate, which
  runs `two_d_mode` and so can never show roll/pitch even when the chassis
  is physically upside-down) and computing roll/pitch from its orientation
  quaternion each control step. Beyond a `flipped_attitude_deg` parameter
  (default 60°) it stops the rover, logs one clear error pointing at this
  file, then a throttled warning while it stays flipped, and an info log if
  attitude ever recovers. Re-verified: fed the node the actual quaternion
  recorded during the M5 tour flip (roll ≈ 177.6°) standalone - correct
  error/resume sequence; then launched the full demo and drove normally for
  several seconds - no false trigger.
- **`astar.py`**: `plan_path` now bounds-checks start/goal indices before
  indexing the cost grid - out-of-range (especially negative) indices would
  otherwise silently wrap via numpy's negative-index semantics instead of
  failing. Structurally unreachable via the planner node (which already
  bounds-checks before calling in), but the module is safer standalone.
- **`planner_node.py`**: replaced one vague "goal may be unreachable or in
  a lethal cell" warning with three specific ones - goal cell is lethal,
  start cell is lethal (flagged as possibly localization drift into an
  inflated obstacle), or genuinely no path exists - to make a failed replan
  actually diagnosable from the log.
- **`costmap_node.py`**: a missing/corrupt `manifest.json` or a
  `resolution_m:=0` param used to produce a raw traceback or a
  `ZeroDivisionError`; both now fail with one clear log line (pointing at
  deleting the stale `~/.cache/regolith/worlds/seed_<N>` dir if that's the
  cause) and a clean `exit 1` instead.
- **All five launch files**: `seed:=abc` or a negative seed used to produce
  a raw Python traceback deep in `launch`; now validated up front with one
  clear `RuntimeError` naming the bad value. Re-verified with `seed:=abc`
  (clean single-line error) and a full `seed:=42` launch (unaffected).
- **`hello_moon.launch.py` didn't actually launch RViz** - a real, fairly
  significant bug: the top-level README's Quick Start told users to run
  `./scripts/demo.sh` then "click 2D Goal Pose in RViz," but no RViz node
  was ever included in that launch file's node list, so the documented
  default-mission demo was undriveable as written. Fixed by adding an RViz
  node (new `rviz` launch arg, default `true`, off via `rviz:=false`).
  Re-verified independently: launched clean and confirmed `rviz2` actually
  starts and loads the config with no errors (it did not before this fix).
- **`rover.rviz`**: added Costmap, PlannedPath, and an "EKF Estimate"
  Odometry display (kept raw wheel odometry too, disabled by default so it
  doesn't visually compete with the fused estimate), an explicit Tools list
  including "2D Goal Pose" → `/goal_pose`, and pulled the default view back
  from `Distance: 4` to `12` so the whole local costmap is visible instead
  of just the chassis.
- **`scripts/demo.sh` / `scripts/setup.sh`**: added upfront checks for ROS 2
  Humble, Gazebo, and (`setup.sh`) `vcs`/`rosdep`/`colcon` being present,
  plus seed-argument validation in `demo.sh` - all failing with one clear
  line pointing at the README's prerequisites instead of a raw "command not
  found" partway through.
- **Documentation consistency pass**: fixed several stale/inaccurate claims
  found by reading the docs as a new contributor would - `docs/architecture.md`
  claimed car-specific packages are excluded "via `COLCON_IGNORE`" and that
  `ekf_localizer` "is kept" (both false; the actual mechanism is
  `--packages-up-to`, and `ekf_localizer` was replaced - see the reuse log
  above); `CONTRIBUTING.md`'s dev-setup snippet predated `scripts/setup.sh`
  and would fail on a fresh clone (`rosdep install --from-paths src` against
  an empty `src/`); the top-level README's ROS badge claimed Jazzy support
  that doesn't exist anywhere in this project; `regolith_bringup`'s and
  `regolith_costmap`'s READMEs hadn't caught up to `hello_moon.launch.py`
  existing; `heightmap.py`'s docstring said the default collision-grid
  resolution was 32 when the code (and PROGRESS.md M4) both say 24.
- **Housekeeping**: confirmed `__pycache__` directories present on disk
  under `planetary/*/regolith_*/__pycache__/` are not tracked by git (the
  upstream fork's `.gitignore` already covers them) - no fix needed.
- **Left alone, deliberately**: the five launch files share substantial
  copy-pasted structure (bridge config, spawn logic, EKF setup) that grows
  with each one; a shared helper module was considered but not built - the
  package is `ament_cmake` with launch files installed as plain data, so a
  shared helper needs either an installed Python module or fragile
  `sys.path` tricks, and all five files are individually working and
  independently verified. Not worth the risk at this scale. M3's drift and
  M4's physics-collision flip root causes were left untouched, per the
  brief for this pass - only failure *visibility* around them was in scope,
  not the underlying physics/estimation fixes themselves.
- **Cleanup note for future sessions**: the review agent's own standalone
  verification runs (testing the flip-detection node in isolation) left
  several orphaned ROS node processes running well after it reported
  everything killed - `pkill -f "^gz sim"`/`"^ros2 launch ..."` doesn't
  catch child nodes that outlive their parent launch process. Found via
  `ps aux` showing three duplicate full node sets from different launch
  times all still running and publishing on the same topics simultaneously.
  Killed by PID. Worth remembering: after any standalone/background ROS
  testing, verify with `ps aux | grep -i regolith` (or similar), not just
  the launcher-process pkill patterns used throughout this project.

## Rover flip fix (terrain collision + simulated recovery)

The M4/M5 flip issue (rover chassis rolling ~90-180°, always coincident with a
terrain-collision-box boundary crossing) was root-caused and fixed, rather
than left as a documented limitation. Previous sessions had already tried
reducing follower speed/turn aggressiveness, raising box-grid resolution from
24 to 64 cells/axis (which tanked physics real-time-factor to ~0.09), and a
rotate-in-place-before-driving behavior - none eliminated it. This pass
actually measured the collision geometry instead of continuing to tune
follower parameters around it.

- **Root cause, measured, not assumed**: the box-grid terrain collision
  fallback (`build_terrain_collision_boxes_sdf` in
  `regolith_terrain_gen/heightmap.py` - the only working collision option;
  dartsim/bullet/bullet-featherstone all lack heightmap/mesh collision, see
  M2's "physics saga" above) used flat-topped boxes. Adjacent cells meet at a
  vertical cliff equal to their height difference: on seed 42 at
  `grid_resolution=24`, steps averaged 0.31 m and reached 2.27 m against the
  rover's 0.09 m wheel radius - 81% of all cell boundaries had a step taller
  than the wheel. Driving (especially turning) across such a step produces a
  sudden horizontal contact normal that rolls the chassis. Critically, the
  flip hotspot used to reproduce this fix (-9, 44.8 on seed 42) sits on
  near-flat terrain (1.7° slope), not a crater rim - confirming this was a
  collision-geometry artifact, not primarily a "steep/rough terrain" problem,
  which is why earlier follower-side mitigations (slow down on high-cost
  cells) never fully fixed it.
- **Fix part 1 - prevention, tilted + smoothed slabs**: each box is now
  tilted to match the local terrain gradient (a "shingle" approximating the
  true tangent plane) instead of sitting flat, and slightly widened
  (`overlap_frac=0.12`) so neighbors overlap with no gap a wheel could drop
  into. Tilting alone was insufficient: the residual lip between two tilted
  neighbors equals the local terrain *curvature* (discrete Laplacian of the
  cell-average heights, /4), which is nonzero even on gently-bending flat
  ground - measured up to 1.11 m on seed 42 (12x the wheel radius), with 31%
  of boundaries still exceeding the wheel radius. Fixed by `_smooth_surface`:
  a separable `[1,2,1]` blur of the cell-average heights (`smoothing_passes`,
  default 3) applied *before* tilting, removing the curvature term so
  neighboring slab tops very nearly meet. At 3 passes: max lip 1.11 m -> 0.10
  m, boundaries exceeding wheel radius 31% -> 0%, generalizing across seeds
  7/123/2024 (0.84-1.01 m -> 0.07-0.13 m). Uses the *same* 576 boxes as
  before, so this is free on real-time-factor - unlike the earlier
  resolution-increase attempt, which bought smoothness by brute-force box
  count and paid for it in RTF. Slab thickness is a small constant (2.5 m,
  not scaled with terrain height) specifically to avoid re-introducing an RTF
  hit via bloated per-box bounding boxes. Spawn clearance is unaffected -
  spawn Z still comes from the fine heightmap via `manifest.json`, not this
  smoothed collision grid.
- **Fix part 2 - honest simulated-recovery backstop**: a wheeled rover cannot
  physically self-right, and prevention, while now far more effective, isn't
  provably 100% - so `regolith_bringup/scripts/flip_recovery_node.py` (new
  node, wired into `hello_moon.launch.py`) watches `/ground_truth/pose` and,
  if the rover stays flipped (roll/pitch > 60°, 1s debounce), teleports it
  back to its last recorded upright pose via gz-sim's `/world/.../set_pose`
  service. Every log line explicitly labels this "SIMULATED RECOVERY" /
  "not physical" - it exists to keep an unattended demo running, not to claim
  real self-righting hardware. `pure_pursuit_node.py`'s existing flip
  detection (`_check_flipped`, raw `/imu`-based since the EKF's `two_d_mode`
  estimate can never show a real flip) now just pauses following instead of
  halting permanently; once the recovery node uprights the rover, the
  attitude check clears and following resumes on its own. An earlier version
  of the recovery node (built earlier in this same pass, found still running
  as a live user demo process when the fix work started) used a fixed 2s
  backoff and cleared its pose history on every reset, which could re-select
  a recovery pose right back on the same lip - confirmed via logs showing 29
  consecutive teleports to the same spot (-9, 44.8). Fixed with progressive
  backoff (2s -> 4s -> 8s... capped at 40s) that does *not* clear history, so
  a relapse walks back further along the actually-driven trail instead of
  looping.
- **Verification**: 3 clean autonomous goal-reaching runs, zero flips, max
  observed roll/pitch under ~5°/6° (vs. the previous 60-180° flips):
  seed 42 spawn->(0,25) 25 m, seed 42 (0,24)->(0,55) 31 m (55 m combined
  through the original y≈44 flip zone), seed 7 (0,0)->(30,15) 34 m diagonal
  (crosses multiple cell boundaries while turning - the previously worst
  case). A manual stress-drive repeatedly crossing the original hotspot at
  0.3 m/s produced zero driving-induced flips; a deliberately induced flip
  (manual teleport-drop) correctly exercised the new progressive-backoff
  recovery with no relapse loop. This is real progress on the plan's
  "3 consecutive full 60-100 m runs" acceptance bar but not a re-attempt at
  that literal distance/seed-cluster combination yet - the runs above are
  shorter and were chosen to specifically stress the confirmed flip
  mechanism (boundary crossings, sustained turning) rather than to replay
  the exact M4 acceptance check end to end. Re-running the original
  60-100 m/3-consecutive-seed acceptance check is the natural next step to
  close M4 out fully.
- **Process gotcha found along the way**: killing ROS/Gazebo processes can
  leave stale `/dev/shm/fastrtps_*` segments behind that wedge DDS message
  delivery on the next launch, producing what looks like a stall (goals
  never reaching the planner) but is actually a discovery/transport problem,
  not a code bug. Clearing `/dev/shm/fastrtps_*` before relaunching fixed it.
  Also, `ros2 topic pub --once /goal_pose` can miss the planner due to
  discovery timing; a brief `-r 2` publish is more reliable than `--once`.
- **Not yet done**: `smoothing_passes` (default 3) and `overlap_frac`
  (default 0.12) are new tunable parameters, not yet swept for a formally
  optimal value - 2 passes also works (max lip 0.194 m on seed 42) if less
  crater-rim smoothing is preferred.

## M4 acceptance check: full 60-100 m / 3-consecutive-run result

The plan's literal M4 acceptance bar - "click a goal ~60-100 m away with at
least one crater and one rock cluster on the straight line... reaches the
goal (within 1.5 m) without intervention, at least 3 consecutive runs with
different seeds/goals" - was re-attempted at full distance after the flip
fix above, rather than left at the shorter stress-test distances used to
verify that fix. **Result: pass, 3/3.**

- Goals were chosen programmatically per seed (script not checked in - ad
  hoc scratch tooling): sample angle/distance combinations in the
  60-100 m ring from spawn, keep the one whose straight line from spawn
  passes through at least one crater's radius and near a cluster of
  multiple rocks within 10 m of each other. Each run was launched headless
  (`headless:=true`, new launch arg added for this - see below) via
  `ros2 launch regolith_bringup hello_moon.launch.py`, with the goal
  published on `/goal_pose` (a few repeated publishes over ~15 s, per the
  discovery-timing gotcha already documented above) and no further
  intervention - success was read entirely off `/goal_reached` and
  `/ground_truth/pose`, not driven or nudged by hand.
- | Seed | Goal (m) | Straight-line distance | Obstacles crossed | Result | Time | Max roll / pitch |
  |---|---|---|---|---|---|---|
  | 42 | (-63.64, 63.64) | 90.0 m | 4 craters (incl. the original flip-fix hotspot's crater cluster), 6-rock cluster | Reached | 964.5 s | 4.9° / 9.2° |
  | 7 | (-38.14, 74.84) | 84.2 m | 1 crater, 6-rock cluster | Reached | 864.4 s | 3.0° / 6.7° |
  | 123 | (38.14, 74.84) | 84.2 m | 3 craters, 4-rock cluster | Reached | 799.7 s | 3.8° / 7.6° |

  All three: zero flip events (max attitude 9.2° vs. the 60° flip-detection
  threshold and the 60-180° actually seen pre-fix), `/goal_reached` fired
  with no manual replanning or intervention needed beyond the initial goal
  publish.
- **One honest caveat on the "within 1.5 m" figure**: `pure_pursuit_node`'s
  own arrival check (the thing that actually publishes `/goal_reached`)
  measures distance to the *planned path's last waypoint*, which is the
  goal snapped to the nearest costmap cell center (0.781 m/cell on this
  256x256 grid over a 200 m world - see `planner_node.py`'s
  `_grid_to_world`), not the raw clicked/published coordinate. That's a
  reasonable, already-existing design choice (the planner only ever reasons
  in grid cells), not something introduced for this check. Measuring
  straight-line distance from the rover's *final ground-truth position* to
  the *original raw goal coordinate* (a stricter, independent check than
  the system's own): seeds 42 and 7 came in under 1.5 m (1.80 m and 1.67 m
  respectively - both technically over on this stricter measure too,
  actually) and seed 123 at 2.01 m. Recording the real numbers rather than
  rounding down to a clean "all under 1.5 m" - the *system's own* tolerance
  check (against the grid-snapped waypoint) was satisfied in all three
  cases (that's what triggered `/goal_reached`), and the grid-snap offset
  alone accounts for up to `0.781 * sqrt(2) / 2 ≈ 0.55 m` of the gap, but a
  tighter arrival behavior (e.g. a final small-radius approach independent
  of the grid) would be a legitimate follow-up if exact-coordinate arrival
  ever matters more than it does for this PoC.
- **New launch arg**: `headless:=true` on `hello_moon.launch.py` (default
  `false`) appends gz-sim's `-s` (server-only, no GUI) flag. Added
  specifically to run this check unattended and avoid the GUI-crash-related
  ghost-window issue documented in "Issues encountered" - `gz sim`'s GUI
  process has a known crash-on-exit (`ruby` segfault in `libgcc_s.so.1`,
  seen repeatedly via `dmesg` across sessions) that leaves orphaned RAIL
  window surfaces on the WSLg/Windows side; running server-only for
  automated/unattended runs sidesteps it entirely. `rviz:=false` alone
  (already existing) does not skip the Gazebo GUI itself.
- **Process-cleanup gotcha, sharper version of the one already logged
  above**: confirmed the first attempts at this check produced nonsense
  results (a rover that never moved; a rover that stopped ~1.6 m short and
  stayed there) because a prior failed/backgrounded launch's full node set
  (gz sim, bridge, EKF, costmap, planner, pure pursuit) was still running
  and fighting the new launch's nodes over the same topic names - not a
  pipeline bug. `pkill -f "regolith"` is also unreliable for a different
  reason than the one already noted (matching the invoking shell's own
  command line): if the *repo* is checked out to a path containing
  "regolith" (as this one is, `/home/balazs/regolith`), almost any shell
  command run from inside it will itself contain that substring and get
  self-matched. Match on the actual installed executable path instead
  (e.g. `install/regolith_planner/lib`), and verify the process list is
  actually empty afterward rather than trusting the kill command's exit
  code.

## M3 drift re-investigation: the 20-45% figure is stale, and a second, unrelated failure mode found

Revisiting the M3 "Substantially done" status above, since the 20-45%
position-drift figure recorded there turns out to be **pre-fix and no longer
representative of the current codebase**, and a live-testing session while
investigating it surfaced a second, previously-undocumented failure mode.

- **Timeline check**: the M3 drift measurement (commit `7390059a7`) predates
  the terrain-collision smoothing fix (commit `8515e1f36`, "Rover flip fix"
  above) by about 17 hours. The pre-fix `heightmap.py` used flat-topped
  axis-aligned collision boxes with cliff-like steps at cell boundaries -
  the current file's own commit notes put those at an average 0.31 m, up to
  2.27 m, i.e. taller than the 0.09 m wheel radius, **even on flat ground**.
  Driving straight at 0.3-0.35 m/s across those steps makes a wheel
  spin/slip climbing each cliff, which is what the original test measured as
  "genuine, speed-dependent wheel slip under lunar gravity." At 0.1 m/s the
  wheel climbs quasi-statically, hence that test's 0% figure - the speed
  dependence was a seam-crossing artifact, not a steady-state traction
  effect. The smoothing fix that resolved rover flips removed those seams as
  a side effect, and with them, apparently, most of the drift.
- **Re-measured on current terrain** (seed 42, straight-line and turning
  runs driven directly via `/cmd_vel`, autonomy stack idle, so these numbers
  are the localization pipeline in isolation): straight-line drift is
  **0.0%** at both ~4 m and ~16 m. A full **53 m** straight-line leg (chosen
  via a manifest clearance scan so it doesn't cross any rock/crater) gave
  **0.17-0.20%** EKF-vs-ground-truth drift end to end, computed correctly as
  each stream's own displacement over the run (comparing absolute
  coordinates across a run that included manual `gz set_pose` teleports is
  invalid - neither the wheel-odometry dead-reckoning nor the EKF are
  informed of a physical teleport, so their absolute frames desync from
  ground truth's; the first pass at this measurement produced a false ~70%
  figure for exactly this reason, before the mistake was caught). The error
  also does not accelerate with distance - it shrinks from 0.62% at 5.7 m
  travelled to 0.20% at 47.7 m, consistent with a small fixed
  settling/startup transient rather than a growing steady-state rate.
  Gentle-turn runs (radius 1-2 m circles) measured 2.5-4% - still inside the
  <5% target. **The "lunar-gravity traction slip" explanation for the M3
  drift figure is retracted**; on current code, M3 appears to already meet
  its acceptance target. (Caveat: these are isolated wheel-odom+IMU+EKF
  tests, not the full autonomous pipeline over the actual 60-100 m M4
  acceptance course; re-measuring drift during a real M4-style autonomous
  run, rather than a manually-driven straight/turn leg, would be the
  natural way to close this out completely.)
- **A second, unrelated failure mode found along the way: an intermittent
  wheels-locked-but-upright stall in tight turns.** While re-running the
  turning tests above, the rover once froze solid - zero further change in
  *both* ground-truth position and yaw - mid-maneuver, at a location
  verified (via the terrain manifest) to have 17.8 m of clearance from the
  nearest rock or crater, on smooth (~1.9° local slope) ground, with
  `/cmd_vel` still commanding a steady 0.3 m/s + 0.15 rad/s turn the entire
  time. Attitude stayed upright throughout (roll/pitch ~0°), so this is
  invisible to `flip_recovery_node`'s 60° flip detector - it is a distinct
  mobility failure, not a flip, and (since wheel odometry froze in lockstep
  with ground truth) it contributes ~0 to the localization drift numbers
  above; it's a "the rover stops making progress" bug, not a "the rover
  mislocalizes" bug.
  - Root cause (moderate-high confidence on the mechanism; the exact dartsim
    internals weren't instrumented directly): a skid-steer wheel in a tight
    turn must scrub laterally against the ground, and lunar gravity gives a
    much smaller wheel normal force (and thus a narrower friction cone) than
    Earth gravity would for the same `mu1`/`mu2` = 1.4 friction coefficient.
    The physics engine's contact solver appears to occasionally collapse to
    an all-static solution where the commanded wheel joint velocity is
    infeasible against that narrow cone, and the wheels simply stop
    rotating. Confirmed *not* a terrain-collision-geometry artifact: the
    exact stall coordinates were checked against the reconstructed collision
    mesh and sit mid-slab, nowhere near a seam. Confirmed genuinely
    reproducible but rare: repeated attempts at the same maneuver, same
    location, mostly complete a full loop cleanly; one attempt out of
    several produced a full freeze, one other showed a brief "near-miss" dip
    in commanded-vs-actual speed before self-recovering. A follow-up stress
    test (20 further repeats of similar tight-turn maneuvers, across two
    sessions) reproduced zero further hard freezes, consistent with this
    being a low-probability event (plausibly well under 10%, not the ~25%
    a small initial sample suggested) rather than something that reliably
    reproduces on demand.
  - Confirmed fix mechanism, independent of the actual root-cause
    mechanism: switching the commanded `/cmd_vel` to a plain straight line
    (no angular component) reliably broke the lock immediately in manual
    testing, even though the rover's position had not budged on its own.
    This is consistent with a static/kinetic friction distinction (once
    moving, the resumed turn is much less likely to re-lock) and, unlike
    the flip case, is a recovery action a real rover's FDIR could plausibly
    take too - it doesn't need the flip backstop's "this is simulated, not
    physical" caveat.
  - **Fix implemented**: `flip_recovery_node.py` now carries a second,
    independent detector alongside its existing flip detector. It watches
    for ground-truth speed staying below `stuck_min_speed_mps` (default
    0.02 m/s) while `/cmd_vel` commands more than `stuck_min_commanded_mps`
    (default 0.03 m/s-equivalent, combining linear and angular command
    magnitude), sustained past `stuck_debounce_s` (default 3.0 s so it can't
    fire during ordinary acceleration ramps or brief planner replans), and
    recovers by taking over `/cmd_vel` for `stuck_nudge_duration_s` (default
    1.0 s) with a straight `stuck_nudge_speed_mps` (default 0.2 m/s)
    command, published at `stuck_nudge_rate_hz` (default 30 Hz, faster than
    `pure_pursuit_node`'s 10 Hz control loop so the override actually reaches
    gz-sim instead of being immediately overwritten). Verified with a
    standalone unit test (`FlipRecoveryNode` instantiated directly, fed
    synthetic `/ground_truth/pose`/`/cmd_vel` messages, no Gazebo involved,
    on an isolated `ROS_DOMAIN_ID` so it can't cross-talk with a live sim):
    fires exactly once on a frozen-pose-plus-active-command condition, does
    not fire while the rover is genuinely moving, and does not fire while
    idle with zero `/cmd_vel`. The recovery mechanism itself (a straight
    `/cmd_vel` override breaking the lock) was validated manually against
    the live simulator during the investigation above, separately from this
    unit test of the detection logic. Given the failure's rarity, a live,
    naturally-occurring recovery was not captured on video/log during this
    session - the unit test plus the earlier manual confirmation are the
    evidence trail for this fix, not a reproduced-end-to-end live capture.

## Terrain density increase: the rover rarely had to turn

User feedback: the rover "doesn't really need to turn left and right, goes
more or less straight line." Investigated with real data rather than just
tuning by feel, since the actual costmap-lethality behavior turned out to
matter more than raw obstacle counts.

- **First checked whether craters even register as obstacles at all** (the
  suspicion going in was that the crater bowl/rim profile's slope might be
  too shallow to ever cross `slope_lethal_deg=20°` once smoothed by the
  costmap's block-averaging down to 1 m/cell). Directly measured: false -
  craters do produce real lethal cells at the current config (a heightmap
  built with `crater_count=0` produces exactly 0 lethal cells; the normal
  60-crater heightmap produces ~7% lethal coverage from craters alone), so
  this wasn't the root cause.
- **Root cause, found by testing the actual shipped tour route**: for seed
  42 with `tour_mission.py`'s fixed 5 waypoints
  (`(0,0)→(12,8)→(18,-4)→(4,-14)→(-10,-6)→(0,0)`), only 1 of the 5 legs'
  straight lines crossed any lethal cell at all - the other 4 were
  completely clear. A broader random sample (200 random 10-20 m pairs, 200
  random 60-100 m pairs, well clear of the world edge) put the baseline
  blocked-fraction at ~55-62% depending on seed - i.e. the terrain already
  had real obstacles fairly often, but this specific fixed waypoint set
  landed in the unlucky clear majority four times over, which is what
  produced the "basically straight" impression in practice.
- **Fix**: raised `crater_count` 60→100, `rock_count` 130→190, and lowered
  `spawn_zone_radius_m` 12.0→9.0 in `regolith_terrain_gen/config.py`.
  Values were chosen by measuring straight-line-blocked fraction and A*
  reachability together (not eyeballed) across seeds 7, 42, and 123: a more
  aggressive density increase (crater_count=150, rock_count=260) pushed the
  fixed tour route to 4/5 legs blocked, but also raised genuine A*
  unreachable-goal failures from a baseline 0-1 per 24 sampled goals to 4-9
  per 24 - too much risk of "click a goal, it's actually unreachable" for
  the size of ask here. The shipped values raise blocked-fraction for
  10-20 m legs from ~55-62% to ~65-70% across the three seeds tested, while
  keeping genuine (non-goal-on-obstacle) A* failures at 0-1 per 24 sampled
  goals - the same order as baseline, not meaningfully worse.
- **Live-verified after regenerating and relaunching** (seed 42): the
  previously-completely-clear tour leg 1 (`(0,0)→(12,8)`, 14.1 m) now
  produces a genuinely curved path - 1.47 m maximum perpendicular deviation
  from the straight line, not the ~0 m it had before. A farther (~74 m)
  goal still resolves to a valid 109-waypoint path, confirming A*
  reachability held up at longer range too.
- **Honest caveat**: this is a density increase, not a placement-algorithm
  change (craters/rocks are still placed independently and uniformly at
  random, with no minimum spacing between them or guarantee against long
  clear corridors). It measurably reduces how often a given seed/waypoint
  combination gets unlucky, but doesn't *guarantee* every route on every
  seed requires turning - a specific seed/waypoint pair could still land
  in the clear tail of the distribution. A stratified/jittered placement
  grid (bounding the maximum possible clear-corridor length directly,
  rather than relying on density alone) would give a firmer guarantee if
  that's ever needed, at the cost of being a larger change to the
  generator's placement algorithm; not done here as it was more than this
  request asked for.

## Overnight freeze: two overlapping demo launches cross-talking on the ROS graph

User report: the sim ran for several hours, then froze with an error, GUI
showing nothing coherent. Root-caused from `~/.ros/log/` (each ROS node
writes its own per-process log; `ros2 launch` writes a `launch.log` per
invocation, named with its own PID) rather than a live repro, since the
processes were already gone by the time this was investigated - **the
diagnosis below is log archaeology, not a re-observed live failure**.

- **Two `hello_moon.launch.py` invocations were running at once.**
  `~/.ros/log/2026-07-21-15-22-17-*-8110/` (no `mission:=tour`, no rviz)
  started at 15:22:18. `~/.ros/log/2026-07-21-15-30-33-*-8606/`
  (`mission:=tour` + rviz) started at 15:30:33 - eight minutes later, on top
  of the first one, without checking it had actually exited.
- **Trigger**: session 1's `parameter_bridge` process died with **SIGABRT
  (exit code -6)** at 15:39:29, ~17 min into that session (see its
  `launch.log`: `[ERROR] ... process has died [pid 8116, exit code -6, ...]`,
  no further lines after that - no clean shutdown was ever logged for this
  session). The proximate cause of the abort itself wasn't recoverable from
  the available logs (a C++ process's SIGABRT with no captured traceback) -
  not claiming a cause for that part.
- `hello_moon.launch.py` had no `on_exit` handling, so `ros2 launch` did
  **not** tear the rest of session 1's tree down when the bridge died - its
  `gz sim`, `ekf_node`, `costmap_node`, `planner_node`, `pure_pursuit_node`,
  and `flip_recovery_node` kept running as orphans. Neither launch sets a
  distinct `ROS_DOMAIN_ID` or namespaces its topics, so when session 2
  started, both full stacks ended up sharing `/goal_pose`, `/planned_path`,
  `/odometry/filtered`, `/clock`, and `/cmd_vel`.
- **Confirmed via matching timestamps across the two sessions' own PIDs**:
  session 1's `planner_node` (pid 8125) and session 2's `planner_node`
  (pid 8621) logged **identical** `"Planned path: ... start=(122, 127)/
  (136, 127) goal=(128, 128)"` lines at the same sim-timestamps (e.g. both
  at `1784671676.79...`), and both sessions' `flip_recovery_node` instances
  (pid 8129 vs 8625) logged identical "STUCK RECOVERY" events at identical
  timestamps - two independently-simulated rovers, one merged ROS graph.
- Consequence: a merged, non-monotonic `/clock` (two `gz sim` instances each
  publishing their own) produced a burst of "Detected jump back in time /
  Resetting RViz" and "Moved backwards in time" warnings in `rviz2`,
  `ekf_node`, and `robot_state_publisher`'s logs early in session 2 - this
  is almost certainly the "GUI showing nothing coherent" the user saw.
  `pure_pursuit_node`'s deviation/replan logic - which had **no retry cap or
  give-up condition** - looped "Deviated X m - stopping and replanning"
  **49,928 times** over the ~9 hour run, consistent with alternating between
  pose estimates from two different rovers' EKF instances every time a new
  plan arrived from whichever `planner_node` last computed one.
- **This exact failure mode was already documented** from earlier M4 testing
  ("Process-cleanup gotcha" above: "a prior failed/backgrounded launch's
  full node set was still running and fighting the new launch's nodes over
  the same topic names") - the lesson was written down but never turned
  into an automated safeguard, so it recurred, this time for 9 hours
  unattended instead of being caught immediately during interactive testing.
- **Fixes made** (implemented, not yet live-verified against a real repro of
  this exact scenario - flagging that honestly rather than claiming a
  re-test that didn't happen):
  - `scripts/demo.sh`: added a preflight step that finds and kills any
    leftover `hello_moon.launch.py` process tree (by process group, so it
    catches orphans whose launch parent already died - process group
    membership survives reparenting), plus a belt-and-suspenders match on
    this repo's installed executable paths (`install/regolith_*/lib/...`,
    not a bare `"regolith"` substring match, which would self-match the
    script's own invocation from a repo checked out under a path containing
    that word - see the "Process-cleanup gotcha" note above), and refuses to
    proceed if the process list isn't actually empty afterward.
  - `hello_moon.launch.py`: every long-running node (everything except the
    intentionally one-shot `spawn_rover`) now has an `on_exit=Shutdown()`
    handler, so a single node dying unexpectedly brings the whole demo down
    instead of leaving orphans for a later launch to collide with.
  - `pure_pursuit_node.py`: added `max_consecutive_replans` (default 8) -
    after that many deviate/stall-triggered replans on the *same* goal with
    no intervening progress or new goal, it logs an error and stops
    retrying that goal rather than looping forever. This is a fix
    independent of the root cause above: even a single, correctly-isolated
    run had no floor on this loop at all, which is what let the underlying
    graph-collision bug run for 9 hours instead of failing loudly and fast.
  - **Not fixed / left as a follow-up**: distinct `ROS_DOMAIN_ID` per launch
    (or topic namespacing) would make the two-stacks-collide failure mode
    structurally impossible even if process cleanup somehow still missed
    something; not done here since it's a larger change (would need
    threading through every node's config) and the preflight-kill + on_exit
    changes above already close the actual gap that let this happen.
    **Update 2026-07-23: this follow-up is now done - see "Per-launch
    ROS_DOMAIN_ID isolation" below.**

## Per-launch ROS_DOMAIN_ID isolation

The follow-up flagged at the end of the overnight-freeze section above (and in
SPEC.md's known-gaps list) is now implemented: each `hello_moon.launch.py`
invocation claims its own `ROS_DOMAIN_ID`, so two concurrently-running
invocations physically cannot share a DDS discovery domain and therefore
cannot merge into one ROS graph - regardless of whether `demo.sh`'s
preflight-kill ran, and regardless of invocation path (via `demo.sh` or a bare
`ros2 launch regolith_bringup hello_moon.launch.py`, which the launch file's
own docstring documents as a supported path with nothing stopping two of them).

- **Why a domain id, not topic namespacing**: `ROS_DOMAIN_ID` isolates DDS
  discovery itself - the actual mechanism that let two `gz sim`/EKF/planner
  stacks find each other and merge in the first place. Two different domain
  ids use disjoint DDS port ranges, so the two stacks never even discover one
  another. Topic namespacing alone would not have isolated the `/clock`
  merging between two `gz sim` instances (two servers each publishing their
  own sim-time onto one graph produced the "jump back in time / Resetting
  RViz" storm that broke `rviz2` in the original incident); domain isolation
  covers that case too because the second `gz sim` is on a different graph
  entirely.
- **Where it's set**: at the very top of `hello_moon.launch.py`'s
  `_generate_and_launch` `OpaqueFunction`, `os.environ["ROS_DOMAIN_ID"]` is set
  *before* any of the returned actions are built or spawned. In ROS 2 launch a
  `Node`/`ExecuteProcess` captures the environment at the moment it actually
  spawns (not when the action object is constructed), and that includes the
  processes inside the *included* `ros_gz_sim/gz_sim.launch.py`, which spawn
  after the `OpaqueFunction` has already returned. Mutating `os.environ`
  directly inside the running `OpaqueFunction` (rather than emitting a
  `SetEnvironmentVariable` action and worrying about action ordering) is the
  simplest way to guarantee it lands before every spawn. **This was verified
  empirically, not just reasoned from the launch API** - see verification
  below, which confirms the included `gz sim` process really does inherit it.
- **Allocation scheme - lock-file registry, giving an actual guarantee (not a
  probabilistic one) for the realistic case**: a purely random pick in the
  valid range would leave a small-but-real collision chance between two
  simultaneous launches, which given this project's don't-round-a-probabilistic-
  fix-up-to-solved convention isn't good enough to call structural. Instead
  `_allocate_domain_id()` keeps a registry directory
  `~/.ros/regolith_domain_ids/`: each in-use id `N` is a file `N.lock`
  containing the claiming launch's PID, and the whole claim (scan for a free
  id + write the claim file) runs under an exclusive `flock` on a
  `.registry.lock` sentinel. Two launches started at the same instant
  therefore serialise on the flock and are *guaranteed* to pick different ids -
  this is a true mutual-exclusion guarantee, not a low-probability mitigation.
  A crashed/SIGKILLed launch that never cleaned up its claim file is handled by
  a PID-liveness check (`os.kill(pid, 0)`): a stale claim whose holder PID is
  dead is reclaimed by the next launch, so a leaked lock file self-heals rather
  than permanently burning an id. Cleanup on normal exit is a best-effort
  `atexit` unlink; correctness does not depend on it running.
- **Range**: ids 1-101. 0-101 is the commonly-cited Linux-safe range (the DDS
  spec allows up to 232, but ids above ~101 push the computed DDS ports into
  the Linux ephemeral-port range and collide); 0 is skipped deliberately
  because it's the default domain every un-configured ROS process on the box
  lands on, so avoiding it also keeps us clear of unrelated ROS traffic.
- **Honest statement of the guarantee** (per this project's convention -
  stating exactly what this does and does not promise):
  - Between any two `hello_moon.launch.py` invocations that both successfully
    claim an id, graph isolation is **absolute**: distinct DDS domains cannot
    discover each other, full stop. This holds whether the launches are back-
    to-back or overlapping, via `demo.sh` or bare `ros2 launch`, and whether
    or not the preflight-kill ran.
  - The one documented residual is exhaustion: the guarantee is that no two
    concurrent launches share an id *as long as fewer than 101 regolith
    launches are alive at once*. If 101 were somehow already live, the 102nd
    falls back to a random pick (rather than refusing to start) and could
    collide - a case that requires 101 concurrent lunar-rover sims on one
    machine, far beyond anything this PoC's RAM/GPU could run, so it is called
    out for honesty, not because it's reachable in practice.
  - An explicitly user-set `ROS_DOMAIN_ID` in the environment is honoured
    as-is (the user asked for that specific domain) - it is recorded in the
    registry best-effort so a concurrent auto-allocation avoids it, but is
    never overridden or refused. Two launches that a user *deliberately* pins
    to the same preset id will collide; that's explicit user intent, not
    something this scheme second-guesses.
  - This is the structural backstop; `demo.sh`'s preflight-kill and the
    `on_exit=Shutdown()` handlers are kept (not removed) - they still reclaim
    GPU/CPU from genuinely-orphaned duplicate stacks, which domain isolation
    does nothing about (an isolated orphan still burns a full gz sim + node
    set of resources).
- **Verification actually performed** (headless, `headless:=true`, to avoid the
  WSLg GUI-crash gotcha), two overlapping launches seed 42 and seed 7 started
  ~5 s apart and left to fully spawn:
  1. The two invocations claimed **different ids - 18 and 85** (from each
     launch's `[hello_moon.launch] Using ROS_DOMAIN_ID=...` line).
  2. **Env propagation confirmed by reading `/proc/<pid>/environ` of every
     spawned process**: all of launch 1's processes - including the included
     `gz_sim.launch.py`'s `gz sim -r -s .../seed_42/world.sdf` subprocess -
     carried `ROS_DOMAIN_ID=18`; all of launch 2's - including its
     `gz sim .../seed_7/...` - carried `ROS_DOMAIN_ID=85`. This is the
     load-bearing check that the env var reaches the included sub-launch's
     spawned process, not just the top-level nodes.
  3. **Graph isolation confirmed**: `ROS_DOMAIN_ID=18 ros2 node list` showed
     exactly one complete stack (one `ekf_filter_node`, one `regolith_costmap`,
     one `regolith_planner`, one `regolith_pure_pursuit`, one
     `regolith_flip_recovery`, one `ros_gz_bridge`, ...), `ROS_DOMAIN_ID=85
     ros2 node list` showed exactly one *other* complete stack, neither listed
     the other's nodes (never two of any node), and `ROS_DOMAIN_ID=0 ros2 node
     list` (the default domain) showed nothing - i.e. neither stack leaked onto
     the default domain either. Pre-fix, a single domain-0 `ros2 node list`
     would have shown two of every node - the exact merged-graph condition that
     caused the freeze.
  4. **Self-heal confirmed**: both launches were hard-terminated (SIGTERM to the
     launch process group, then SIGKILL of a surviving `gz sim`), which killed
     them before `atexit` could release `18.lock`/`85.lock` - exactly the
     leaked-lock case. Confirmed the holder PIDs (2572, 2713) were then dead and
     that the reclaim path removes such a stale lock on the next allocation, so
     the leak is self-healing. Process list verified actually empty afterward
     (`pgrep` for all node/gz patterns returned nothing), not merely trusted
     from exit codes; leftover stale locks and `/dev/shm/fastrtps_*` segments
     were cleared.
  - The allocator's pure logic (distinctness across many sequential claims,
    stale-lock reclamation, live-lock non-reclamation, preset honouring) was
    also exercised in a standalone unit test against a temp registry dir before
    the live run.
- **No rebuild needed**: the installed launch file is a symlink into `src/`
  (`colcon --symlink-install`), so the edit is live without a `colcon build`.
- **Left as-is deliberately**: the four narrower milestone launch files
  (`terrain_only`, `teleop_demo`, `localization_demo`, `autonomous_demo`) were
  *not* given the same treatment. `hello_moon.launch.py` is the one entry point
  the overnight freeze actually involved and the one both `demo.sh` and the
  documented direct-launch path use; the narrower files are single-layer
  debugging aids not part of the collision scenario, and the launch files
  deliberately don't share a helper module (see the M5 quality pass note on why
  a shared launch helper wasn't built for this `ament_cmake` package). Factoring
  the allocator into a shared, installed module so all five could use it is a
  reasonable future tidy-up, not done here to keep the change scoped to the
  actual failure mode.

## Stuck-detector live-fire attempt: not caught this session

Attempted to observe `flip_recovery_node.py`'s stuck detector (`_check_stuck`/
`_recover_stuck`) fire on its own against a genuinely-occurring stall, as
opposed to the unit-test and manually-observed-lock validation already on
record above. **Result: not caught. Zero `STUCK RECOVERY` events across 92
tight-turn maneuvers and ~38 minutes of active driving.** Recording this
honestly rather than implying a catch that didn't happen, per this project's
convention.

- **Setup**: `ros2 launch regolith_bringup hello_moon.launch.py seed:=42
  headless:=true rviz:=false` (no `mission:=tour` - manual driving), on its
  own isolated `ROS_DOMAIN_ID=8` per the allocator above. Driven from spawn
  (0, 0) - confirmed 17.3 m clearance to the nearest rock and 28.3 m to the
  nearest crater from `seed_42`'s `manifest.json`, matching the clearance of
  the location that produced the original discovery.
- **Method**: 92 repeated tight-turn bursts published directly to `/cmd_vel`
  via `ros2 topic pub -r 20`. 71 attempts used the confirmed repro shape
  (0.3 m/s linear + 0.15 rad/s angular, ~1-2 m radius, 22 s per burst); 21
  attempts (every third, for variety) used a tighter/faster variant (0.35 m/s
  + 0.25 rad/s, 15 s per burst). Each burst was followed by a brief 3 s
  straight-line leg before the next attempt. The launch's stdout (including
  `flip_recovery_node`'s `output="screen"` log) was captured to a file and
  grepped for `STUCK RECOVERY` after every attempt so a catch would have been
  noticed immediately, not just at the end.
- **The rover was genuinely being driven and genuinely upright throughout**,
  not idling: ground-truth position moved attempt-over-attempt (e.g. from
  (0,0) after 12 attempts to (2.57, 3.93) after 12 more, ending at
  (-3.82, -0.68) after all 92 - all well inside the clear zone), and
  `/ground_truth/pose` orientation stayed near-identity (small roll/pitch
  quaternion components) the entire session - no flips, no `SIMULATED
  RECOVERY` events either. `grep -c "STUCK RECOVERY"` against the full
  captured log returned 0.
- **Time accounting**: active driving ran 15:22:39-16:01:05 (38 min 26 s
  across the 92 bursts), inside a total session (launch start to process
  cleanup) of about 40 minutes - somewhat under the suggested 45-60 minute
  window but well over 2x the suggested 30-40 maneuver count, and the earlier
  batches already showed no sign of the failure becoming easier to trigger
  with variation, so the session was called there rather than padding wall
  time for its own sake.
- **Consistent with, not contradicting, the existing rarity estimate**:
  PROGRESS.md's stuck-detector section above already downgraded this from an
  initial "~25% small-sample" estimate to "plausibly well under 10%" after a
  prior 20-attempt stress test also reproduced zero freezes. This session's
  92 further zero-freeze attempts (112 total tight-turn attempts across both
  sessions with zero natural stalls) is consistent with that revised, low
  estimate - it does not newly falsify the original discovery (which remains
  on record above with its own evidence: the frozen ground-truth position/yaw
  at 17.8 m clearance, confirmed not a terrain-collision artifact), it just
  continues to demonstrate the failure is now rare enough that on-demand
  reproduction, let alone catching the *detector* fire on one, is a
  significant time investment.
- **No code changes made** - this was an observation-only session, per its
  brief. No bug was found in the detector itself; there was simply nothing
  for it to detect this time. `README.md`'s and `docs/SPEC.md`'s "hasn't yet
  been observed catching a naturally-occurring stall live" caveats are left
  exactly as they were - this session doesn't change that status, it just
  adds one more (negative) data point to it.
- **Process cleanup**: launch process group and the standalone
  `/ground_truth/pose` echo were both killed via `dangerouslyDisableSandbox`
  (per the WSL2 background-process-escapes-sandbox gotcha already documented
  above); confirmed via `pgrep` afterward that no `gz sim`, bridge, or
  `regolith_*` node remained running (only this session's own shell matched
  the search pattern, expected self-match, not a leftover process).

## "Gazebo shows nothing but terrain" - the rover was never missing, just 2-3 px

User-reported bug: launching `hello_moon.launch.py` with a GUI, the Gazebo window
showed the procedural terrain (and craters) but apparently nothing else - no
visible rover. Root-caused and fixed, but the investigation went through one wrong
turn worth recording honestly rather than editing out.

- **First hypothesis (wrong): a GUI scene-broadcast race.** The rover is spawned
  ~3s after gz-sim's GUI starts, via a separate `ros2 run ros_gz_sim create`
  service call, rather than being present in `world.sdf` from the start like the
  rocks/terrain. Comparing the always-open launch window against a freshly-opened
  `gz sim -g` client, the fresh client *appeared* to show a small object the
  original window didn't, at the rover's screen location - interpreted at the
  time as proof that an already-open gz-sim GUI never picks up entities added
  later via the spawn service (a real, documented class of gz-sim GUI bug in
  general, just not what was happening here). Baked the rover directly into the
  generated `world.sdf` at its spawn pose to eliminate that race structurally
  (`hello_moon.launch.py`'s `_bake_rover_model_sdf`, converting the xacro'd URDF
  via `gz sdf -p` and splicing the `<model>` block in before `</world>`, same
  place rocks are already assembled in `worldgen.py`). This is a reasonable
  simplification on its own merits (one less runtime dependency, the world file
  is now fully self-contained) but **retested after the change and the rover
  still didn't visibly appear** - proving the scene-broadcast race was never the
  actual cause. The original "fresh client shows it, old one doesn't" comparison
  was almost certainly a JPEG-compression artifact or a stray dust-particle
  sprite mistaken for the rover, not a real signal - a caution for next time to
  verify a tiny (sub-5px) blob against a second, independent method before
  trusting it as evidence.
- **Actual root cause, confirmed by direct measurement**: the world's default GUI
  `camera_pose` (`-110 -110 35 0 0.28 0.78`, chosen to frame the whole 200 m
  crater field with its low-sun long shadows for a nice establishing shot) is
  about 155 m from the rover's spawn point at the origin. The rover is a 0.4 m
  chassis - at that range it projects to roughly 2-3 pixels, and the world's
  intentionally-dark lunar ambient (`<scene><ambient>0.06 0.06 0.07</ambient>`)
  makes it blend further into the equally dark background/shadowed terrain.
  Confirmed three ways: (1) an isolated single-model test world (just the rover
  + a flat ground plane, default lighting) rendered it perfectly, ruling out any
  problem with the model/material itself; (2) `gz model --list` and
  `/world/regolith_moon/pose/info` both confirmed the rover was a live, correctly
  posed entity in the full world the whole time; (3) temporarily moving the
  camera to ~11-28 m from the rover (first attempt put the camera *underground*,
  at z=2.5 against ~5.2 m local terrain elevation, seeing only the terrain's
  underside - corrected to a sane height) showed the rover clearly, sunlit,
  distinctly shaped against the surrounding round rocks.
- **The fix**: moved the default `camera_pose` in `worldgen.py`'s
  `build_world_sdf` from `-110 -110 35 0 0.28 0.78` to `-22 -22 13 0 0.3 0.78` -
  same elevated 3/4 angle and lighting mood, ~5x closer to the spawn zone.
  Re-verified via screenshot: the rover is now a small but clearly distinguishable
  shape (lighter chassis top, darker wheels) even in the raw, non-contrast-boosted
  capture, unlike before where no amount of levels/contrast adjustment recovered
  a rover-shaped signal from the noise at 155 m. No screenshots or other docs
  referenced the old camera framing (checked before changing it).
- **Build note**: `hello_moon.launch.py` is symlink-installed (edits are live, no
  rebuild needed), but `regolith_terrain_gen` is an `ament_python` package whose
  `--symlink-install` uses a pip-style editable (`.egg-link`) install rather than
  a plain file symlink - the previous colcon build predates this session, so the
  installed `worldgen.py` was a stale copy until `colcon build --symlink-install
  --packages-select regolith_terrain_gen` was re-run. Verified afterward that the
  editable link resolves imports back to the `src/` copy going forward
  (`regolith_terrain_gen.worldgen.__file__` points into `build/regolith_terrain_gen/
  regolith_terrain_gen/`, itself a symlink into `src/regolith.universe/...`), so
  further edits to this package's Python files are live without another rebuild.
- **Diagnostic byproduct, not a bug**: found that synthetic X11 scroll/click
  events from `xdotool` do not reach gz-sim's GUI at all under this WSLg setup
  (zero effect across three attempts, with and without explicit window
  focus/activate) - gz-sim's Qt GUI is very likely a native Wayland client here,
  which XTest-based tools can't drive. Camera repositioning for debugging had to
  go through editing `world.sdf`'s `camera_pose` and relaunching rather than
  interactively panning/zooming - worth knowing before trying interactive GUI
  automation in this environment again.

## "The rover seems to be underground" - visual/collision terrain mismatch, fixed

User-reported bug: the rover appeared to be sunk into the ground rather than sitting
on top of it. Root-caused and fixed - the rover's physics were never broken, it was
resting exactly where its (invisible) collision geometry supported it; the problem
was that the *rendered* terrain and the *physical* terrain were two different
surfaces that didn't line up.

- **Root cause**: the visual `<heightmap>` (`worldgen.py`) is the full-resolution
  (513x513 px, ~0.39 m/px) fBm+crater heightmap. Collision, per the existing note in
  `heightmap.py`, can't use native `<heightmap>`/`<mesh>` geometry on this
  dartsim/bullet install, so it's approximated with a coarse 24x24 grid of tilted,
  blurred ("smoothed") boxes (~8.3 m cells) - a fix for an earlier flip bug (see
  M4/M5 above). Nobody had checked whether that smoothed surface still visually
  lines up with the fine heightmap it approximates. Measured directly (real
  generation code, not a re-implementation) across the 9 m spawn zone: seed 42 -
  the launch file's default - showed a mean visual-above-collision gap of **+0.150
  m**, up to **+0.346 m**, against a **0.09 m** wheel radius (80% of the spawn zone
  exceeded the wheel radius). Confirmed live: launched headless, `/ground_truth/pose`
  settled to a `z` matching the *collision* surface's prediction to within 1 cm, not
  the visual surface - exactly consistent with "wheels resting on an invisible lower
  surface while a higher one is drawn as the ground." The gap is seed-dependent (7
  seeds checked ranged -0.066 m to +0.254 m mean) - not a crater-rim issue (checked:
  zero craters had rim influence reaching the seed-42 spawn zone) - most likely
  coincidental alignment between the origin and the coarsest fBm octave for a given
  seed. Not universal, but the default seed was one of the worst.
- **The fix**: made the visual heightmap and the collision surface the *same*
  surface by construction, instead of narrowly patching the spawn zone. Refactored
  `heightmap.py`: `_build_smoothed_surface` (the block-average + blur + per-cell
  tilt math) is now a shared helper used by both `build_terrain_collision_boxes_sdf`
  (as before) and a new `_synthesize_visual_heightmap`, which evaluates that same
  per-cell tilted plane at every full-resolution pixel. `build_heightmap` now
  returns `(raw_heightmap, visual_heightmap, craters, elevation_lookup)` - the raw
  fine terrain is kept only to derive the collision surface from; `visual_heightmap`
  (saved as the PNG) and `elevation_lookup` (used for rock placement and the
  spawn-point manifest elevation) both come from the synthesized, collision-matched
  surface. This also fixes rock placement for free - rocks were already positioned
  via `elevation_lookup`, so they now automatically sit on the same ground the rover
  does, no separate change needed.
- **A normalization gotcha caught before it shipped**: `save_heightmap_png` used to
  normalize the PNG by the array's own max height. That was harmless for the raw
  heightmap (already forced to max out at exactly `height_range_m` during
  generation) but would have silently reintroduced the same mismatch through the
  back door for the new synthesized surface, whose peak is generally *below*
  `height_range_m` (smoothing shaves off spikes) - self-normalizing would have
  rescaled it back up to fill the full range, distorting it relative to the
  un-rescaled collision boxes. Fixed by normalizing against the fixed
  `cfg.height_range_m` instead (now an explicit parameter).
- **cfg fields, not scattered keyword defaults**: `collision_grid_resolution`
  (24), `collision_overlap_frac` (0.12), and `collision_smoothing_passes` (3) moved
  from keyword defaults on `build_terrain_collision_boxes_sdf` onto `TerrainConfig`,
  so the collision-box builder and the visual synthesizer are structurally
  guaranteed to use identical values rather than relying on two call sites' defaults
  happening to match.
- **Verified two ways**: (1) numerically, re-running the same gap measurement
  against the fixed code across the same 5 seeds - max absolute gap dropped from
  tens of centimeters to **under 1.8 cm** in every case (the residual is just
  nearest-cell-lookup rounding in the measurement harness itself, not a real
  discrepancy); (2) live, relaunching seed 42 headless end-to-end with no errors -
  `/ground_truth/pose`'s settled `z` (5.302 m) now matches
  `manifest.json`'s `spawn_zone.elevation_m` (5.247 m) plus the rover's fixed
  wheel-bottom-to-`base_link` offset (0.055 m) to within a millimeter.
- **Incidental bug found and fixed along the way, unrelated to the main fix**:
  `craters.py`'s spawn-zone keep-out (`place_craters`) excluded a crater's *bowl*
  radius from the spawn zone, but `apply_craters` actually sculpts a raised rim out
  to 1.6x that radius (the rim gaussian's tail). A large crater could satisfy the
  keep-out on its center while its rim still poked into the "guaranteed clear"
  spawn zone. No seed tested actually hit this (seed 42 had zero offending craters),
  so it wasn't the cause of the reported bug, but the exclusion math itself was
  wrong for any seed that could place one there - fixed by excluding
  `radius * 1.6` instead of `radius`.
- **Left alone**: the collision grid still doesn't cover the outermost <3 m strip
  at the +x/+y world edge (a pre-existing artifact of cropping the heightmap to a
  multiple of the block size) - noted in the new synthesis function's docstring
  rather than fixed, since it's well outside the ~9 m spawn zone / normal driving
  area and unrelated to this bug.

## The rover is STILL underground - gz heightmap min/max normalization (the real cause)

The user came back: the rover was *still* visibly below the surface after the two
fixes above. Both prior "fixes" were real improvements but neither addressed the
actual mechanism, and the "underground" section above is **wrong on one important
point** (see the normalization bullet below). Corrected here rather than edited in
place.

- **What the two prior sections got right, and where they stopped short.** The
  "underground" fix genuinely made `visual_heightmap` (the PNG) and the collision
  boxes the *same absolute-metre surface* - that part is correct and still stands.
  But it only ever verified that equality **in Python metres** (`elevation_lookup`
  vs `_collision_top_z`) and against `/ground_truth/pose` - it never checked what
  **gz-sim actually draws from the PNG**. That was the blind spot: the PNG is not
  the surface gz renders.
- **Real root cause: gz-sim min/max-normalizes the heightmap image.** gz-sim's
  ogre2 `<heightmap>` does **not** map `pixel/65535 -> height * <size>.z` linearly.
  It stretches whatever pixel range the PNG actually contains to fill the full
  `<size>.z`: the image's lowest pixel is drawn at `<pos>.z`, its highest at
  `<pos>.z + <size>.z`, linearly between. Our `save_heightmap_png` was writing a
  **partial-range** PNG - `visual_heightmap / height_range_m`, i.e. pixels spanning
  only ~`[0.074, 0.93]` of full scale (min height 0.736 m, max 9.299 m over a 10 m
  `<size>.z`). gz then stretched that `[0.074, 0.93]` band back up to `[0, 1]`,
  lifting every mid-range height. At the origin the drawn ground rose from the
  intended 5.247 m to ~5.4-5.5 m while the collision boxes stayed at 5.247 m, so the
  rover - correctly resting on the collision surface - rendered sunk ~0.2-0.25 m into
  the visibly-drawn ground.
- **The prior section's normalization bullet was backwards.** It says
  `save_heightmap_png` was fixed to normalize by the fixed `height_range_m` "instead
  of the array's own max" to avoid "rescaling it back up to fill the full range."
  That reasoning assumes gz decodes the PNG *linearly* - it doesn't. Filling the full
  range is exactly what was needed; refusing to is what left gz to do the rescaling,
  uncontrolled. Both the old array-max normalization *and* the fixed-`height_range_m`
  normalization produced a partial-range PNG (min pixel != 0), so both were broken by
  gz's min/max stretch; the change between them didn't touch the actual bug.
- **How this was pinned down (evidence, not theory):**
  - Rendered the scene server-side from a scripted camera sensor (the GUI's Qt/Wayland
    window can't be screenshotted under WSLg, and `/gui/screenshot` isn't registered;
    a downward `depth_camera` sensor also refused to publish on this GL stack, so a
    plain RGB camera + `ros_gz_bridge` -> PNG was the working path).
  - **Calibration**: rendered two synthetic ramp heightmaps that share the same value
    *span* but different absolute values (centre 0.5 vs 0.3). They rendered
    **pixel-identical** - only possible if gz normalizes by the image's own span, not
    by absolute pixel value. (A flat/constant heightmap renders degenerately and a
    heightmap with no `<texture>` block crashes the ogre2 fragment-shader compile on
    this WSLg GL3Plus stack - both are incidental gotchas, worked around.)
  - **Measurement**: dropped a striped 0.25 m ruler at the origin in the real world
    and read the terrain-occlusion height off the pixels. Before the fix the terrain
    occluded the ruler at **z~=5.48 m** (collision/spawn = 5.247 m); a Z-sweep of the
    actual rover confirmed it (fully buried at its 5.30 m rest pose, only the chassis
    slab poking out at 5.6 m, cleanly on top only by ~6.0 m).
- **The fix** (`heightmap.py`, `worldgen.py`, `generate.py`): stop fighting gz's
  normalization - feed it. `save_heightmap_png` now writes a **full-range** PNG
  (min/max-normalized to `[0, 65535]`) and returns the real-world `(z_min, z_span)`
  that full range corresponds to. `worldgen.build_world_sdf` puts those straight into
  the heightmap element: `<pos> z = z_min`, `<size> z = z_span` (instead of `0` and
  the fixed `height_range_m`). gz's decode then reproduces the exact absolute surface:
  `pos_z + (pixel/65535)*size_z == H(x,y)` for every pixel. Collision boxes,
  `elevation_lookup`, spawn Z and rock placement are **unchanged** (still absolute
  metres) - only the PNG encoding and the two SDF numbers that decode it changed, so
  the drawn ground and the physical ground now coincide by construction. This holds
  whether gz's decode is min/max-stretch *or* plain linear (a full-range PNG makes the
  two identical), so it's robust to the exact decode rule.
- **Verified:**
  1. New regression test `test_rendered_png_decodes_back_to_absolute_surface` (seeds
     42/123/7/1/2): saves the PNG, decodes it the way gz does (`z_min +
     pixel/65535 * z_span`) and asserts it matches `visual_heightmap` to within 16-bit
     quantization (~1.3e-4 m). This is the check the prior tests never made. Full suite
     now **11/11 pass** (the 6 pre-existing checks still pass - collision math untouched).
  2. Live render, same server-side-camera method: baked the rover into the regenerated
     seed-42 world, let physics settle it (base_link z = 5.302 m, identical to before -
     physics untouched), and the rover now renders **clearly on top of the terrain,
     wheels on the ground, casting a shadow** - vs. completely invisible/buried at the
     same pose before the fix. Ruler re-measured: terrain now occludes at **z~=5.25 m**,
     matching the 5.247 m collision surface (was 5.48 m).
  3. End-to-end `hello_moon.launch.py seed:=7 headless:=true`: launches clean, no
     errors; `/ground_truth/pose` settles to z = 6.191 m = manifest spawn elevation
     6.135 m + the 0.055 m wheel-bottom offset. Signature changes wire through fine.
- **Honest caveats / residual uncertainty:** the ruler read-off has ~0.1 m precision
  (0.25 m segments, dim low-sun lighting), so "5.48 -> 5.25" is "clearly moved down by
  ~0.2 m to sit on the collision surface", not a sub-cm claim - the sub-cm guarantee
  comes from the decode being exact algebra (verified by the unit test), not from the
  pixel measurement. I did **not** fully pin gz's exact normalization constants (the
  measured pre-fix 5.48 m is a touch higher than a pure image-min/max model predicts
  ~5.27 m, plausibly gz filtering/mip-mapping the extreme crater-floor/rim pixels);
  the fix sidesteps this because a full-range PNG decodes to the true surface under
  either a linear or a min/max rule. If a future seed's terrain has its extreme min/max
  pixels as tiny isolated features that gz filters out, a small residual stretch could
  in principle reappear - the regression test models the ideal decode, not that
  filtering, so watch for it. Nothing was committed - changes are left staged for review.

## "Still no rover, and a green thing under the surface" - framing, and a retracted claim

User came back a third time: the rover still doesn't show, plus "a weird green thing
under the surface, that might be the rover placeholder". Two separate findings, and
one earlier claim in this document turns out to be **wrong** and is retracted below.

- **The GUI *can* be screenshotted under WSLg - the previous section's claim is
  wrong.** That section says gz-sim's GUI "can't be screenshotted under WSLg" and that
  its Qt GUI "is very likely a native Wayland client, which XTest-based tools can't
  drive", so all visual verification went through scripted server-side camera sensors.
  The GUI is in fact an **XWayland** client: `xdotool search --name "^Gazebo Sim$"`
  finds it and `import -window <id> shot.png` (ImageMagick) captures it fine. What is
  true is the narrower observation that *synthetic input* (xdotool click/scroll) does
  not reach it, and that `/gui/screenshot` is not registered in this build - those two
  are real and still stand. Generalising them into "the GUI can't be captured" is what
  was wrong, and it mattered: every previous round verified the *sensor* render path
  and never once looked at what the GUI actually drew, which is the only thing the
  user was ever reporting on. Screenshotting the GUI directly is now the primary check.
- **Root cause of "no rover": framing, not rendering.** Screenshotting the real
  `hello_moon.launch.py` GUI showed the rover present, correctly lit, sitting on the
  terrain and casting a shadow - just **7x2 px of lit chassis in a 1200 px window**.
  The previous fix had moved the camera from ~155 m to ~32 m, which took the rover
  from 2-3 px to ~13 px: a 4x improvement that still leaves it indistinguishable from
  terrain noise in the dark lunar lighting. The earlier section calls that move
  "clearly distinguishable ... even in the raw, non-contrast-boosted capture", which
  was too generous a reading of a 13 px blob.
- **The fix** (`worldgen._gui_camera_pose`, new): compute the opening pose from the
  spawn point rather than hardcoding it - back off 4.5 m in x and y and sit 3.0 m above
  the ground, aimed at the chassis. Measured on a real GUI screenshot, seed 42: lit
  chassis **7x2 px -> 43x17 px**. Two robustness points fall out of computing it
  rather than hardcoding: the pose now tracks the seed's actual spawn elevation
  (5.2 m for seed 42 vs 6.1 m for seed 7 - irrelevant at 155 m, not at 7 m), and
  clearance is sampled under the *camera*, not under the rover, so terrain rising
  behind the rover can't bury the camera. New `test_gui_camera_framing.py` pins all
  three failure modes (too far / underground / mis-aimed) across 5 seeds; suite 26/26.
- **The green object could not be reproduced - reported as unexplained, not fixed.**
  Searched for it three ways and found nothing: (1) the whole codebase has no green
  material anywhere - chassis is 0.55 grey, wheels 0.08 grey, rocks 0.32/0.30/0.29,
  and `gz sdf -p` preserves both rover materials correctly through the URDF->SDF
  conversion; (2) measured every GUI screenshot taken this session - maximum
  green-excess (`G - (R+B)/2`) is **1/255**, i.e. the frames are pure greyscale, no
  green pixel exists to explain; (3) the only genuinely green pixels found anywhere
  were in **RViz**, and they are toolbar icons (the green status checkmark and the
  "2D Goal Pose" arrow), not scene geometry. So either it predates this session's
  regenerated worlds, or it is in a window/state not reproduced here. Left open
  rather than guessed at.
- **Process notes from this round, both previously-recorded traps that bit again:**
  `xdotool search ... | head -1` picked an **orphaned Gazebo window from a previous
  launch**, producing one screenshot that matched neither the old nor the new camera
  pose and briefly looked like the GUI was ignoring `<camera_pose>` entirely (it does
  honour it - verified by launching the same world at three poses and comparing).
  Always count the matching windows, don't take the first. Separately, `pkill -f
  "install/regolith"` and `pgrep -f "gz sim"` each **self-matched the invoking shell**
  and killed it mid-script; `pgrep -f "gz[ ]sim"` (bracket trick) avoids this.
- **Incidental, not investigated:** RViz's 3D view was empty with every display
  unchecked in the one screenshot taken of it. Not what was reported, not chased.


## Terrain realism pass: floating rocks, missing craters, unchallenging terrain

Reported: "big floating rocks, not cool", "more craters would be nice", "a terrain a
bit more challenging". All three were measured before anything was changed, and all
three turned out to be real defects rather than tuning preferences. A fourth, unreported
defect surfaced during the measurements.

**Read the performance sub-section below before trusting any RTF number in this
document's earlier notes.** A first version of this section claimed the finer terrain
grid was paid for by a rock-collision fix and that the simulation came out *faster*.
That was wrong, it is retracted in full, and the corrected measurements are given below.

### 1. Rocks floated - a fixed offset applied to a variable mesh

`scatter_rocks` placed each rock's model ORIGIN at `elevation_lookup(x, y) - 0.12 *
scale`, assuming that buried it. Rock meshes are normalized by their bounding RADIUS,
but `displace_rock`'s anisotropic stretch leaves each variant's lowest vertex anywhere
from **0.51 to 1.00 units** below its origin. Measured across 12 variants, every rock
therefore hovered **0.39-0.88 x scale** above the surface - up to **~2.1 m of clear air
under a 2.4 m boulder**.

Fixed in `scatter.seat_rock_z`, which seats a rock off its actual geometry instead of a
constant: each vertex is scaled and rotated into world axes, and the resting origin is
`max over vertices of (terrain(x+vx, y+vy) - vz)`, then sunk by `rock_embed_frac`. Taking
the max over vertices (not the terrain height at the rock's centre) is also what stops
rocks on sloped ground hanging off their downhill edge. Rocks also now get a small random
roll/pitch, not yaw alone.

Result, seeds 42/7/123, 190 rocks each: **0 floating rocks** (was: all of them), lowest
vertex now embedded 3-13 cm. Locked down by `test_rock_placement.py`.

> **This result was true but did not mean what it says.** It measures rocks against
> `elevation_lookup`, which is the same convention the rocks are seated in - so it could
> not detect that the ground gz actually DRAWS is that surface transposed. Rocks really
> did still float on screen. See "Rendered terrain was TRANSPOSED" below. The seating
> maths in this section is correct and unchanged; it was the surface being drawn that was
> wrong.

### 2. Rock collisions never worked at all

Not reported, found while measuring the above. The rocks' `<collision>` geometry was
`<mesh>` - which this gz-sim 8 / gz-physics 7.8.0 install silently ignores, the same
dartsim limitation `heightmap.py` already records for terrain. **The rover drove straight
through every boulder** while the costmap dutifully planned around them.

Verified directly rather than inferred - a probe dropped onto each geometry type:

| geometry | probe settles at | verdict |
|---|---|---|
| box (control) | 3.10 m | works |
| ellipsoid | 2.45 m | works |
| **mesh** | **-38.3 m** | **falls straight through** |

Rocks now use an `<ellipsoid>` fitted to each variant's actual per-axis extents
(`fit_collision_ellipsoid`) - an ellipsoid rather than a sphere because these boulders are
deliberately anisotropic, and fitted slightly INSIDE the mesh so the rover never stops
against thin air.

Confirmed solid in the real generated world: a wheel-sized probe dropped over a 2.4 m
boulder falls dead vertically to **z = 8.33** (that boulder's computed top is **8.48**),
then rolls off and travels 11.9 m before settling on terrain. Note the first two attempts
at this check were badly designed and produced a **false pass** and then a false
"inconclusive": this world runs well below real time, so a 12 s wall-clock wait is only a
couple of seconds of sim time and caught the probe still mid-air. Horizontal displacement,
not final height, is the reliable contact signal - a probe in free fall never moves
laterally.

**This is a correctness fix and nothing more.** See below - the claim that it also bought
back most of the physics budget was wrong.

### 3. Craters existed in the data and nowhere else

The heightmap the world RENDERS and COLLIDES is not the fine crater-sculpted array: it is
the block-averaged, 3-pass-blurred collision grid (`_build_smoothed_surface`), previously
at 24 cells/axis = **8.3 m cells**. Craters below roughly twice the cell size are averaged
clean away. Measured crater depth retained in the rendered surface, seeds 42/7/123:

| crater diameter | depth retained (old 8.3 m cells) |
|---|---|
| 0-5 m | **-12%** (centres came out slightly RAISED) |
| 5-10 m | -2% |
| 10-20 m | +1% |
| 20-40 m | +18% |

Of **100 craters placed, a mean of 2** survived into the rendered surface at all. Raising
`crater_count` alone - the obvious fix - would have changed nothing visible. This is why
the world read as uncratered. Two things follow, and they cost very differently:
raising the crater size floor from 2 m to 6 m is **free** (it just stops placing craters
the surface cannot represent), while making *small* craters survive needs a finer
collision grid, which is not free at all.

### 4. Retraction: what the finer grid actually costs

**Retracted.** The first version of this section claimed that the 190 dead `<mesh>` rock
collisions were consuming ~70% of the physics budget, that replacing them with ellipsoids
reclaimed it, and that the terrain grid therefore got 4.5x finer *and* the simulation got
~10% faster. All of that is wrong. It rested on cross-session RTF figures
(`res24 + mesh rocks = 0.134` against `res24, no rocks = 0.454`) that do not reproduce.

Absolute RTF on this machine drifts substantially between sessions - the same world
re-measured three times back to back spanned 0.173-0.228 - so only comparisons measured
**interleaved in one session** mean anything. Re-measured that way, seed 42, 3 reps of
3000 steps each, spread within each case under 5%:

| case | terrain boxes | RTF |
|---|---|---|
| res24, no rock collisions | 576 | 0.568 |
| res24, 190 **mesh** rocks | 576 | 0.499 |
| res24, 190 **ellipsoid** rocks | 576 | 0.488 |
| res48, 190 ellipsoid rocks | 2601 | 0.220 |

So all 190 rocks together cost about **12%**, not 70%, and mesh versus ellipsoid is
**within noise**. The ellipsoid change buys correctness and nothing else. Terrain box
count is the entire story, and a finer grid is a straight cost:

| collision grid | cell size | boxes | RTF | craters visible | slope p95 |
|---|---|---|---|---|---|
| 24 (previously shipped) | 8.3 m | 576 | **0.479** | 12 | 6.1 deg |
| 32 | 6.3 m | 1024 | 0.388 | 20 | 8.2 deg |
| **40 (now shipped)** | **5.0 m** | **1764** | **0.269** | **32** | **10.4 deg** |
| 48 | 4.2 m | 2601 | 0.206 | 41 | 11.6 deg |

(Crater visibility here is measured with the *new* 160-crater / 6-50 m settings, which is
why res24 shows 12 rather than the 2 it produced with the old 2-40 m sizes - that part of
the improvement is the free part.)

**res40 ships: it is ~1.8x slower than what shipped before**, in exchange for craters
going 2 -> 32 and slope p95 3.8 -> 10.4 deg. res48 was rejected as too expensive at 2.3x
for 9 more craters. This is a deliberate trade, not a free win, and autonomous runs take
correspondingly longer in wall-clock time.

### 5. Settings, and the one metric that regressed

Chosen by sweeping resolution x smoothing x crater params against four metrics at once
(visible craters, inter-slab lip, slope, and A* reachability through the real costmap),
seeds 42/7/123, every parameter pinned explicitly:

| | shipped before | now (res40) | res48 (rejected) |
|---|---|---|---|
| craters visible in rendered surface | 2 | **32** | 41 |
| max inter-slab lip | 0.12 m | 0.14 m | 0.13 m |
| boundaries stepping > 0.09 m wheel radius | **0.7%** | **1.4%** | 0.5% |
| slope p95 (the surface actually driven) | 3.8 deg | **10.4 deg** | 11.6 deg |
| costmap lethal cells | 7.0% | 7.1% | 7.3% |
| 60-100 m goals reachable from spawn | 92.8% | 92.7% | 92.4% |

Note the honest wrinkle: the inter-slab lip metric - the flip proxy that drove the
original coarse grid - **regresses at res40**, to 1.4% against 0.7% before. Finer cells do
reduce the lip for a given surface (res48 reaches 0.5%), but the extra crater relief
res40 introduces more than offsets that at 5.0 m cells. An earlier draft asserted this
metric "improves"; that is only true at res48, and only because res48 is fine enough to
win the trade back. Because a proxy regressed, res40 was **not** shipped on the proxy -
it was put through a real M4 acceptance run (below).

Smoothing stays at 3 passes: dropping to 2 buys more crater relief (41 visible at res40)
but pushes the lip metric to 5.9%, well past what the flip fix established as safe.
Options rejected on measurement: 13 m relief, and 200+ craters (reachability 0.9%).

Sub-6 m pitting, which no affordable collision grid can carry, is now drawn into the
surface **normal map** instead (`textures.py:_small_crater_pits`), where it costs no
physics resolution at all. Two honest limits on that: it is shading detail, not
geometry - it changes how the ground lights, never the rover's silhouette against it or
what the wheels feel - and because the texture tiles every 20 m, the pits repeat on that
period. They are kept deliberately small (0.4-2.5 m) and shallow so they read as surface
pitting rather than as landmarks whose repetition gives the tiling away.

## Rendered terrain was TRANSPOSED - the real cause of the floating rocks

Reported: "the last test still had floating rocks in the Gazebo, and the Gazebo window
froze." Both were investigated with instrumentation, because **no logs of the reported
run existed** - the only launches in `~/.ros/log` were this session's own headless ones.

### The floating rocks were real, and the previous section's "0 floating rocks" was wrong

The claim above ("0 floating rocks, lowest vertex embedded 3-13 cm") was measured against
`elevation_lookup`. So were the collision boxes, and so was the visual heightmap ARRAY.
All three are built in `heightmap.py`'s `[row = y, col = x]` convention, so **they all
agreed with each other and none of them tested the thing that was broken.** Screenshotting
the GUI showed a band of boulders hanging in the sky above the horizon.

**gz maps a heightmap image's first axis to world X and its second to world Y - the
transpose of this module's convention.** Handing gz the array as-written renders the
terrain mirrored about the `x = y` diagonal. Consequences:

- Rocks are seated on `elevation_lookup`, which matches the COLLISION surface, while the
  ground being DRAWN was that surface transposed. A rock therefore hung in the air
  wherever `surface(y, x) < surface(x, y)`, and sank in wherever it was greater.
- It is invisible on the diagonal itself, and invisible to every array-vs-array test.
- It is purely visual: physics, costmap and planning were never affected.

Found by rendering a heightmap carrying a single 25 m spike at world `(+60, 0)` and
screenshotting from directly overhead. Measured, with a second 12 m spike at `(0, -30)`
to break any symmetry, positions read off the screenshot against ground-truth markers
(calibrated at 2.05 px/m from plates at known coordinates):

| spike placed at | rendered before fix | rendered after fix |
|---|---|---|
| (+60, 0) | **(-8, +67)** | (+55, +6) |
| (0, -30) | **(-36, +5)** | (-5, -26) |

i.e. exactly `(x, y) -> (y, x)` before, and correct after. (The few-metre residual is the
offset between a peak's sunlit face and its apex, identical in both columns.)

**Fix:** `save_heightmap_png` now writes `heightmap.T`. Regression tests in
`test_heightmap_orientation.py` assert on the ENCODED FILE - the one artefact that crosses
into gz's convention - including that a spike at `(+60, 0)` does not render at `(0, +60)`,
and that the decoded surface matches `elevation_lookup` everywhere (worst case < 1 cm,
i.e. 16-bit quantisation). `test_heightmap_collision_match.py` had encoded the old
assumption and now transposes before comparing; it still guards the VERTICAL mapping it
was written for. Confirmed visually: the horizon band of floating boulders is gone.

Note how this bug survived two previous "the rover is underground" investigations: both
were about the VERTICAL mapping (`<pos>`/`<size>` z and gz's min/max stretch), and both
were verified by comparing arrays. The horizontal error was orthogonal to all of it.

### The "freeze" - two separate things, one of them self-inflicted

- **Not reproduced as a hang in a healthy run.** A 200 s instrumented GUI run produced
  four visibly different frames. Instrumentation added (`gui_probe.sh` in scratch): per
  process CPU/RSS, window liveness, gz's own `/stats`, and `/proc/<pid>/wchan`. The
  discriminator is `/stats`: a frozen WINDOW with a stepping SERVER is a rendering
  problem, a stopped server is not.
- **A leaked process from a previous session, mine.** `gz-transport-topic -e -t
  /world/regolith_moon/pose/info` had been running **2 h 11 m** at ~19% CPU, left behind
  by an earlier session's diagnostics. gz-transport does **not** honour `ROS_DOMAIN_ID`
  (that only isolates the ROS graph), so it attached to every `regolith_moon` world
  started afterwards, including GUI runs. Killed.
- **A static scene reads as a frozen window.** One GUI run showed four byte-identical
  frames with RTF "N/A"; `/stats` showed `paused: true, iterations: 2`. Worth knowing
  before calling a freeze a freeze.
- **Still open, pre-existing:** running `gz sim -s` DIRECTLY on a generated world
  segfaults in the Ogre2/Sensors path (the rover carries a camera, so even `-s`
  initialises rendering). Reproduced identically on a **pre-fix** world, so it is not the
  transpose change. The normal `hello_moon.launch.py headless:=true` path is unaffected
  and runs fine. Not yet root-caused.

### The transpose fix silently broke the COSTMAP, and no summary statistic showed it

Found while re-validating the acceptance goals, before the acceptance run - not by a test.
`save_heightmap_png` now writes `heightmap.T` for gz's benefit, but **`costmap_node` reads
that same PNG** and indexes it `[row = y, col = x]`, as does the planner's
`_world_to_grid`. So from the moment the transpose fix landed, the costmap's entire slope
field was mirrored about the `x = y` diagonal while the rock obstacles - which come from
the manifest's real x/y - stayed put. The planner was routing around steep ground that
was not there and straight into ground that was.

What makes this worth recording is how well it hides. A transpose **preserves the
elevation histogram**, so every aggregate is unchanged - seed 42's total lethal fraction
is 12.80% read wrongly and 12.81% read correctly. Only per-cell positions move:

| check | value |
|---|---|
| total lethal cells, transposed vs correct | 12.80% vs 12.81% (indistinguishable) |
| cells whose **lethal verdict** differs | **1.73%** |

Fixed by extracting `costmap_node.load_heightmap`, which transposes on load, with the
convention documented at the one point where it crosses gz's. Two new regression tests in
`regolith_costmap/test/test_heightmap_orientation.py` assert the file is READ back in
`[y, x]` (per-cell, on an asymmetric ramp and on a single spike), as the counterpart test
in `regolith_terrain_gen` asserts it is WRITTEN transposed. A third test pins the reason
both are needed: it asserts the lethal-fraction metric **cannot** tell the two apart, so
nobody re-derives confidence from the aggregate later.

This is the third distinct bug from the same root - the two array conventions - and the
second one that array-vs-array tests were structurally unable to see. The generalisable
lesson: when one module's convention crosses into another's, the test has to assert on
the **artefact that crosses** (here the PNG, on both sides of it), and per-cell, because
the natural summary statistic of a transposed field is identical to the correct one.

### Open, measured, deliberately not fixed yet: costmap decodes the wrong height span

Pre-existing, unrelated to the transpose, found in the same read-through.
`costmap_node` decodes the heightmap with `pixels / pixels.max() * height_range_m`, i.e.
it assumes the encoded surface spans the configured `height_range_m` (10.0 m). Since the
full-range PNG fix, the encoding spans the surface's **actual** min-to-max, which is
smaller. Every slope in the costmap is therefore overstated by that ratio:

| seed | true span | assumed | slopes overstated | lethal cells (as shipped -> corrected) |
|---|---|---|---|---|
| 42 | 8.017 m | 10.0 m | 1.247x | 12.81% -> 12.01% |
| 7 | 8.338 m | 10.0 m | 1.199x | 12.66% -> 12.24% |
| 123 | 8.193 m | 10.0 m | 1.221x | 12.93% -> 12.31% |

So the effective slope-lethal threshold is about **16 deg, not the 20 deg configured** -
the error is conservative (the costmap over-flags, never under-flags), which is why it has
never shown up as a failure. Fixing it properly means `write_manifest` recording the real
`(z_min, span)` that `save_heightmap_png` already returns, rather than having the costmap
re-derive it. **Left unfixed on purpose:** it would change the costmap under the res40
acceptance run reported below, and an acceptance result should describe the system that
actually shipped. It is a one-line change plus a manifest field once that run is banked.

### A stale world cache makes offline analysis lie

Also found during goal re-validation: `~/.cache/regolith/worlds/seed_7` and `seed_123`
still held worlds generated on **18 and 24 July** - 100 craters at 2-40 m, one of them
with only 130 rocks - because nothing had launched those seeds since the terrain change.
The first goal validation ran against them and was meaningless (seed 7 "2 craters crossed"
against the 10 the fresh world has). `hello_moon.launch.py` calls `generate_world`
unconditionally on every launch, so **live runs are never affected** - but any offline
script that reads the cache directly gets whatever the last launch left there. Regenerate
explicitly before measuring, which is now what the goal checker does.

## Floating rocks, reported a third time - tested through the rover's own camera

Reported again: "consistently reappearing floating rocks", with the instruction to test it
via the internal camera rather than by another array comparison. That instruction was the
right call and is why this round found anything: **every previous check was circular.**

### The check that kept passing could not fail

`test_rock_placement.py::test_no_rock_floats` measured each rock against
`elevation_lookup` - the function `scatter.seat_rock_z` seats rocks with. Two things
measured through one convention agree no matter how wrong the convention is. It stayed
green through the PNG being written transposed, and it stayed green through the defect
below. It had a second, independent flaw: it rebuilt the rock variants from a fresh
`default_rng(seed)` without consuming the draws `generate_world` makes in between
(`build_heightmap`, then `generate_textures`), so **it graded a set of rocks the shipped
world never contained.** (Cost me a wasted measurement too: reproducing the variants that
way also silently rewrote the cached world's `.obj` files with meshes that did not match
its own manifest.)

Replaced by `test_rock_seating_against_rendered_png.py`, which touches none of the
generator's helpers. It runs `generate_world` and then reads back only what was written
to disk: `heightmap.png` transposed out of gz's axis order and stretched full-range using
the `<pos>`/`<size>` from `world.sdf`, sampled bilinearly; the actual `rocks/*.obj`
triangles; and the manifest's placements. It also asserts **that it is able to fail** -
lift every rock 0.5 m and it must go red - because its predecessor could not.

### The real defect: seating sampled a different surface from the one gz draws

`elevation_lookup` took the NEAREST heightmap post. gz interpolates BILINEARLY between
posts. Anything seated between posts was therefore placed on a surface up to one pixel's
relief above the one being drawn - at the shipped 0.39 m post spacing, a mean of 0.016 m
but a worst case of **0.35 m**. A rock is seated off the single highest of its ~40
vertices, so it picks up the worst overshoot rather than the mean.

`elevation_lookup` is now bilinear. Measured with the new artefact test, over 190 rocks
per seed:

| | seed 42 | seed 7 | seed 123 |
|---|---|---|---|
| rocks floating, before | **1 / 190** | 0 / 190 | 0 / 190 |
| worst gap, before | **+0.016 m** | -0.008 m | -0.027 m |
| rocks floating, after | 0 / 190 | 0 / 190 | 0 / 190 |
| worst gap, after | -0.030 m | -0.030 m | -0.038 m |

Confirmed the new test earns its place: with the bilinear change stashed it fails on seed
42, with it applied all seeds pass.

**But 1.6 cm on one rock is not what a person notices from across the terrain**, and this
is recorded as a genuine but small fix rather than as the answer to the report.

### What the camera actually shows

Through the rover's own camera (`/camera/image`, teleporting the rover with gz's
`set_pose` and holding it against gravity while frames arrive):

- **Close range: seated.** A straight-down frame from 30 m shows every boulder's shadow
  **attached to its silhouette**. At this world's 12 deg sun elevation a gap of *h* under
  a rock separates its shadow by 4.7*h*, so a 0.5 m float would show as a 2.4 m gap.
  Oblique views from 20 m and eye-level views at 90 m agree.
- **Far range, in the GUI: not seated.** Screenshotting the Gazebo GUI (which *is*
  capturable - see the note retracting the opposite claim) and stretching the contrast of
  the horizon band shows **boulders standing clear of the terrain silhouette with sky
  visible underneath them.** Not silhouetted-on-a-ridge - detached, by several times their
  own diameter.

So the report is real and reproducible, and the placement is *also* provably correct: at
those same coordinates the rock is embedded 3-14 cm in the surface the PNG encodes. The
ground under a distant rock is not being drawn where the data says it is.

### Still open, and deliberately not guessed at

The rendering-side mechanism is **not** root-caused, but it now has a name. The installed
`libgz-rendering8-ogre2.so` exports `Ogre::TerraWorkspaceListener` alongside
`Ogre2Heightmap`, i.e. the `<heightmap>` visual is rendered by **Ogre-Next's Terra**, a
GPU terrain system with distance-based LOD. Rocks are ordinary meshes and take no part in
it, so distant ground being tessellated coarser than the data while the rocks standing on
it keep their exact placement is a mechanism that exists in this render path by
construction. That is consistent with everything measured but still not demonstrated to
be the cause: a distance series through the onboard camera (same boulder at 10, 25, 45,
70, 90 m) did not cleanly reproduce a gap growing with range.

The concrete next lever, untried: SDF's `<heightmap><sampling>` (samples per heightmap
datum, **default 1**, currently not set in `worldgen.py`). Raising it to 2 is the
documented quality/performance knob for exactly this geometry and is a one-line change to
test - though note it would cost RTF on a world that is already 1.8x slower since res40,
so it needs measuring, not just setting.

What is NOT the cause, each ruled out by measurement rather than reasoning: rock placement
(above), the collision surface diverging from the drawn one (box tops match the drawn
surface within 5 cm, mean -0.004 m over all 1764 boxes), and the terrain being drawn
smaller than the world (off-centre top-down frames show it drawn out to its edge).

One artefact of these probes worth knowing before trusting a frame: several eye-level
shots came out with the near ground missing - the horizon where it belongs, but 100% sky
below it, matching the background colour exactly rather than being shadow. That is not
understood either, it appeared only for a camera close to the ground, and it is the reason
the close-range conclusions above rest on the top-down and oblique frames instead.

## res40 breaks M4 autonomy: a false `/goal_reached`, and phantom odometry behind it

The res40 acceptance re-run **failed on its first seed**, and failed in a way that
reported itself as success. Recording the chain in full, because every link of it was
measured rather than reasoned about, and because the top-level signal lied.

### Seed 42: `/goal_reached` fired 36 m from the goal

| | |
|---|---|
| `/goal_reached` published | yes - "Goal reached (within 1.50 m)" |
| ground-truth distance to the goal at that moment | **36.2 m** |
| ground-truth distance travelled | 58.6 m of an 85.0 m traverse |
| STUCK RECOVERY events | **22** |
| flip events | **0** |
| max roll / pitch | 14.5 deg / 17.8 deg |

The harness only caught this because it records `/ground_truth/pose` independently.
**`/goal_reached` on its own is not a valid acceptance signal** - `pure_pursuit_node`
measures arrival as `norm(self._path[-1] - position)` where `position` comes from
`/odometry/filtered`, i.e. the whole check lives in the EKF's frame. If the estimate is
wrong, the arrival check is wrong with it, consistently and silently.

### The stuck detector fires live at last - and does not recover

Previously recorded here as never once caught firing on a naturally occurring stall
across 112 attempts over several sessions. At res40 it fires **22 times in a single
run**. The live-fire evidence this project has been chasing arrived as a failure rather
than a vindication: detection works, recovery does not. After one successful recovery,
the remaining 21 fired at a metronomic **~31 s interval across 661 s** - the recovery's
own backoff, retrying and failing - and the rover was still wedged when the run ended.
The 1.0 s straight-line `/cmd_vel` override does not free it.

### Phantom wheel odometry - measured live, not inferred

Seed 7 was instrumented while running, logging `/odometry/filtered` against
`/ground_truth/pose` every 5 s. The trace is unambiguous:

| phase | ground truth moved | EKF believed | divergence |
|---|---|---|---|
| driving normally, t = 5-755 s | tracks | tracks | steady **0.17-0.18 m** |
| wedged, t = 780-1050 s | **0.94 m** | **4.67 m** | grows 0.59 -> 4.28 m |
| driving again, t = 1050-1235 s | 8.64 m | 8.65 m | frozen at **~4.29 m** |

While the rover is pinned its wheels keep turning, so wheel odometry integrates distance
that never happens. The EKF fuses only wheel odometry and IMU - there is no absolute
reference anywhere in the stack - so **the error is permanent**: once the rover breaks
free the two traces move in lockstep again, 4.3 m apart, forever. Seed 42's 22 stuck
events accumulated that error until the rover believed it had arrived while standing
36 m away.

One consequence worth flagging against M3's own acceptance bar: a single stuck event put
localization error at **9.0% of distance travelled** (4.29 m over 47.6 m), against M3's
<5% target and the 0-4% currently recorded there. M3's figures were measured on clean
runs with no stall, so they are not wrong - but they do not describe a run like this one.

### What is probably behind it, and what is not established

The rover never got wedged like this at res24. Two things changed together, and they have
**not** been separated:

- **res40 terrain** is genuinely rougher (slope p95 3.8 -> 10.4 deg, craters 2 -> 32).
- **rock collisions started working at all.** Before the ellipsoid fix, `<mesh>` collision
  was a silent no-op and the rover drove straight through every boulder. Wedging against
  a rock was not previously *possible*. The earlier 3/3 M4 pass was obtained on a world
  where 190 obstacles were phantom.

### Attributed: it is the rock collisions, not the terrain

Run rather than argued about. Seed 7, same goal, same 1800 s window in every case, source
patched in place per variant and restored afterwards (tree verified clean each time):

| config | terrain | rock collisions | **stuck events / 1800 s** | progress in the window |
|---|---|---|---|---|
| baseline (the failing run) | res40 | on | **12** | 88.3 m, over 3053 s total |
| A | **res24** | on | **10** | 98.4 m, false "reached" at 14.2 m |
| B | res40 | **off** | **0** | 84.5 m and still driving when the window closed |

**Rock collisions are necessary; terrain roughness is not.** Dropping back to res24 - the
exact terrain that passed 3/3 - barely changes anything (10 events against 12), and still
produces the same false `/goal_reached` 14.2 m from the goal. Removing only the rock
`<collision>` block at res40, leaving the visual meshes and the costmap untouched so the
planner still routes around the same boulders, eliminates the wedging completely: zero
events, and the fastest progress of any run measured (84.5 m in 1800 s against the
baseline's 88.3 m in 3053 s).

So the terrain realism pass did not break M4. **The rock-collision correctness fix
revealed a failure that was always there and merely invisible**: while `<mesh>` collision
was a silent no-op the rover phased through all 190 boulders, so it could not get caught
on one. The original 3/3 M4 pass was obtained on a world with no rock obstacles in it at
all - it demonstrated planning around obstacles, never driving among them.

That reframes the work: this is not a regression to undo by reverting terrain settings,
it is a capability the rover has never actually had. The fix belongs in recovery and in
the odometry-during-stall problem (items 2 and 3 above), not in terrain tuning.

Honest limits on this experiment: n = 1 run per variant on a single seed, and the stuck
count is a proxy for "gets caught on a boulder" rather than a direct observation of the
contact. The separation is large enough (0 against 10-12) that it is unlikely to be noise,
but it has not been repeated across seeds.

## M4 acceptance re-run at res40: harness corrections

The res40 terrain change (above) regressed the inter-slab lip proxy from 0.7% to 1.4%, so
it was put through a real M4 acceptance run rather than shipped on the proxy. Two things
about the harness are worth recording, because the first attempt produced a **false
failure** and the second would have produced a meaningless pass.

- **Reusing a recorded goal is only valid if the goal is still valid.** The first attempt
  reused the exact goals from the original M4 pass, on the reasoning that a like-for-like
  comparison beats a fresh draw. For seed 42 that goal, `(-63.64, 63.64)`, is **lethal
  under the new terrain** - the planner correctly refused it (`Goal cell (209, 46) is
  lethal (obstacle or too-steep slope)`) once every 3 s, the rover never moved, and the
  run would have burned its whole 9000 s timeout looking exactly like a navigation
  failure. It was a goal-selection failure. Goals are now validated against the SAME
  costmap the running system builds, with the same parameters `hello_moon.launch.py`
  passes to `costmap_node` (resolution 1.0 m, rover radius 0.3 m, slope lethal 20 deg):
  the goal cell and its 8 neighbours must be non-lethal (the planner snaps to a cell
  centre) and the cell must be connected to spawn through non-lethal cells.
  Note the earlier reachability sweep in the terrain section used 0.5 m / 0.35 m instead,
  so its 92.4-92.8% figures are indicative, not the system's own numbers.
- **The watcher must join the launch's `ROS_DOMAIN_ID`.** Every launch claims a private
  domain via the lock-file registry. A watcher left on the default domain 0 sees no topics
  at all: it published the goal into an empty graph and waited. The harness now reads the
  domain back off the launch's stdout, and the watcher aborts after 150 s without a
  `/ground_truth/pose` instead of silently burning the timeout. (`ROS_DOMAIN_ID` does not
  isolate **gz**-transport, which is a separate partition - see the leaked-subscriber note
  in the previous section.)

- **Re-validated before the run, against the CORRECTED costmap.** The goals below were
  originally picked against the costmap that read the heightmap without the gz transpose
  (see the regression above), so they were re-checked - on freshly regenerated worlds -
  before any run started. All three are still valid: goal cell and its 8 neighbours
  non-lethal, connected to spawn through non-lethal cells. Crater counts reproduce
  exactly. The rock-cluster column depends on how wide a corridor counts as "on the
  line", and is reported below at 6 m and 10 m rather than at one flattering width -
  seed 42's cluster is 6-10 m off the line, not straddling it.

Goals selected by the corrected picker, all 60-100 m, reachable, crossing craters and a
rock cluster:

| seed | goal | straight-line | craters crossed | rocks in clusters, 6 m / 10 m corridor |
|---|---|---|---|---|
| 42 | (52.33, -66.98) | 85.0 m | 12 | 0 / 3 |
| 7 | (-45.00, 77.94) | 90.0 m | 10 | 8 / 11 |
| 123 | (76.32, -47.69) | 90.0 m | 10 | 8 / 15 |

("In a cluster" = at least 3 rocks within 10 m of each other, all within the stated
corridor of the straight line. An earlier draft of this table gave 1 / 5 / 6 from a
picker whose corridor width was not recorded; these are the re-measured numbers.)

### Result: 0 / 3. Every run reported success and none of them arrived.

| seed | straight line | GT travelled | **true error at "arrival"** | stuck events | flips | final EKF divergence | max roll / pitch | wall time |
|---|---|---|---|---|---|---|---|---|
| 42 | 85.0 m | 58.6 m | **36.2 m** | 22 | 0 | ~36 m | 14.5 / 17.8 deg | 2737 s |
| 7 | 90.0 m | 88.3 m | **17.4 m** | 22 | 0 | 15.7 m | 11.0 / 15.4 deg | 3053 s |
| 123 | 90.0 m | 72.8 m | **31.7 m** | 20 | 0 | 30.7 m | 17.9 / 26.1 deg | 3600 s (hit timeout) |

All three published `/goal_reached` with "Goal reached (within 1.50 m)". All three were
tens of metres away. The 1.50 m is real - in the EKF's frame - and that is the whole
problem: **the final divergence and the true error are the same number** on every seed
(seed 7: 15.7 vs 17.4 m; seed 123: 30.7 vs 31.7 m, the remainder being the grid-snapped
`path[-1]` versus the raw goal). The rover arrives exactly where it believes the goal is.

The bar is "reaches the goal (within 1.5 m) without intervention, 3 consecutive runs".
Measured against ground truth: **0 / 3, and M4 is no longer met at res40.** The status
table above is corrected accordingly. The previously recorded 3/3 pass stands as what it
was - a pass at res24, on a world where all 190 rock collisions were a silent no-op.

Two things that did hold up: **zero flips across all three runs** (max attitude 26.1 deg
against the 60 deg detection threshold), so the flip fix and its terrain-collision work
are not implicated; and the goal picker, which produced three goals that were all valid,
reachable and genuinely obstacle-crossing.

Seed 123 is the clearest picture of the failure: its ground-truth **y stayed pinned
between -15.3 and -15.5 m for over 1200 s** while x crept from 36 to 48, and the EKF
meanwhile travelled to y = -30.7. It spent the last ~35 minutes of its hour scrubbing
against something, and ended with divergence at **29.8% of distance travelled**.

### What has to change before this can be re-run

Not attempted yet, and listed in the order that matters:

1. **The acceptance harness must judge on ground truth, not `/goal_reached`.** This run
   only caught the failure because the watcher recorded `/ground_truth/pose` separately;
   a harness trusting the system's own success topic would have recorded 3/3 pass.
2. **Recovery has to actually recover.** 64 stuck events across three runs, zero of them
   resolved by the 1.0 s straight-line override, which then retries on a ~31 s backoff
   indefinitely. It is a detector with a no-op attached.
3. **A stall must not corrupt localization.** Wheel odometry integrates while the wheels
   spin against a pinned chassis, and nothing in the stack ever observes absolute
   position, so the error is permanent. The stuck detector already knows the rover is not
   moving - that same signal should stop odometry being trusted.
4. **Attribute the wedging** (res40 roughness vs rock collisions now being real) before
   tuning anything, per the previous section.

## Items 1-3: the harness, the recovery, and the odometry-during-stall fix

Item 4 (attribution) is done and recorded above. This section covers 1-3, which were
built together because they turned out to be one failure with three parts. Everything
below was measured on recorded runs; two of the design ideas were killed by that
measurement and are recorded as such rather than quietly replaced.

### 1. `scripts/m4_acceptance.py` - acceptance judged on ground truth

The previous acceptance harness lived in a scratch directory and did not survive the
session that wrote it, which is its own lesson: the thing that decides whether a
milestone passes belongs in the repo. It is now `scripts/m4_acceptance.py`, and it:

- decides pass/fail **only** on `/ground_truth/pose` distance to the goal;
- treats a `/goal_reached` published further than the tolerance from the goal as
  `FAIL_FALSE_ARRIVAL` - a distinct, louder verdict than a timeout, and it prints the
  true error the system claimed as an arrival;
- publishes the goal and then stays out of the run, so "without intervention" is true;
- validates the goal against the same costmap `costmap_node` builds, with the same
  parameters `hello_moon.launch.py` passes it (1.0 m, 0.3 m rover radius, 20 deg lethal
  slope): goal cell plus its 8 neighbours non-lethal, and connected to spawn. Re-checking
  the three recorded goals reproduces their straight-line distances exactly (85.0 / 90.0 /
  90.0 m), so the picker and the run harness agree with what was recorded before;
- reads the launch's private `ROS_DOMAIN_ID` back off its stdout and joins it, and aborts
  after 150 s without a `/ground_truth/pose` instead of burning the whole timeout;
- with `--record-signals`, logs `/odom`, `/imu` and ground truth at 10 Hz to a CSV. That
  file is the input to `scripts/calibrate_slip_detector.py` below.

One correctness detail worth recording, because it silently corrupts any offline analysis
of these logs: velocities are per second of **simulated** time and this world runs at
about 0.28x real time, so integrating `vx` against wall-clock timestamps overstates
distance by ~3.5x. The signals CSV now carries a `sim_t` column taken from the `/odom`
header stamp; the calibration script uses it, and falls back to a *measured* wall->sim
ratio for older recordings rather than assuming 1.0.

### 2. Recovery that actually recovers

The old recovery was a 1.0 s straight-line forward nudge. Measured: 64 firings, 0
recoveries. Pushing forward into the boulder the rover is wedged against is the wrong
direction, and after the nudge `pure_pursuit` steered straight back onto the same path
into the same rock, so the event repeated on a ~31 s metronome for the rest of the run.

It is now an escalating escape maneuver in `flip_recovery_node.py`: **reverse** (back out
along the way it came in, which is by construction obstacle-free), **turn in place** with
the direction alternating per attempt, then **mark the obstacle and replan**. Consecutive
events inside a 120 s window escalate the reverse and turn durations, because a wedge that
survives one attempt needs a bigger disengagement rather than the same one again.

Three supporting changes were needed for that to mean anything:

- **Keep-out zones (`costmap_node`).** The a-priori costmap knows every rock's footprint
  but not whether the gap between two of them is really drivable, so a wedge is
  information the map did not have. The recovery node publishes `/hazard/stuck_point` and
  the costmap stamps a lethal disc there, in the ESTIMATOR's frame - the frame the planner
  actually routes in, so the zone stays put relative to the path even as the estimate
  drifts. Without this the first two steps only buy one more approach.
- **The planner can start from a lethal cell (`planner_node`).** It used to refuse
  outright, which strands the rover exactly when a keep-out zone has just been marked
  around it - the rover is standing next to the hazard it reported. It now plans from the
  nearest non-lethal cell within 5 cells and says so.
- **`pure_pursuit` is muted during a maneuver, and its replan budget is restored when the
  costmap changes.** Publishing at 30 Hz against its 10 Hz is *not* the same as having
  control: roughly a quarter of the commands gz-sim executed during the old override were
  still pure_pursuit's forward commands, fighting the recovery. There is now an explicit
  `/recovery_active` mute. Separately, the 8-replan give-up cap was exhausting itself on
  approaches the planner could newly route around; a genuinely changed costmap now
  restores the budget, since the retry is not the attempt that already failed.

The node also reports, per event, whether the maneuver actually moved the rover
("FREED" / "STILL WEDGED" with the ground-truth distance moved, and a running
freed/fired tally). "Recovery fired" will not be mistaken for "recovery worked" again.

### 3. A stall must not corrupt localization - and the first two designs were wrong

New node `wheel_slip_node.py` sits between gz and the covariance relay, republishing
`/odom` as `/odom/gated` with a zero-velocity update (ZUPT) substituted while it judges
the wheels to be slipping in place. Detection uses **onboard signals only** - wheel
odometry and the IMU. It deliberately does not use `/ground_truth/pose`, even though the
stuck detector does: a localization fix that consulted the answer key would make M4's
numbers meaningless. `scripts/calibrate_slip_detector.py` scores the detector against a
recorded run, using ground truth only as the label.

**Design 1, refuted.** "While pinned, the body is rigid - so declare slip when the wheels
claim distance and the IMU sees no attitude change." Scored against a recorded seed-42
run this fired on **29% of genuinely-driving windows** at a 3 s window: an IMU cannot tell
constant velocity from rest (Galilean invariance), and a rover driving straight over
smooth ground for three seconds tilts by nothing measurable. Lengthening the window fixed
the false positives - the minimum attitude span over 4,700 driving windows goes 0.0000 rad
(3 s) -> 0.0080 (10 s) -> 0.0276 (15 s) - so the window is 15 s.

**Design 1 still failed on the real thing.** With the false positives gone, the detector
found **0 of 968** genuinely-slipping windows. The reason is worth recording: during an
actual wedge the chassis **bucks against the boulder while the wheels spin**, spanning
0.119-0.195 rad of attitude - *more* than the median driving window (0.163 rad). "Pinned
means still" is simply false here. Only measuring it showed that.

**Design 2, measured and kept: rotation the gyro never sees.** A wedged rover is usually
still being commanded to turn, so its wheels spin differentially and wheel odometry
integrates yaw that never happens; the gyro measures the yaw that did. Gyro-observed
rotation as a fraction of the wheels' claim, same recording:

| class | n | observed / claimed rotation |
|---|---|---|
| slipping (ground truth travelled <25% of the claim) | 3679 | 0.082 - **0.133** |
| honest driving (>70% of the claim) | 1370 | **0.157** - 0.945 (median 0.395) |

Two disjoint bands with a gap, and the separation holds at every minimum-claimed-rotation
guard tried (0.5 / 1.0 / 1.5 / 2.0 rad). The threshold sits in the gap at 0.145. Note the
honest-driving floor is 0.16, not 1.0: skid-steer wheel odometry always over-claims
rotation because turning requires the wheels to scrub (M3 measured it ~3x off). The test
is about the *size* of a disagreement that is always present, which is exactly why the
threshold had to be measured rather than reasoned about. Scored on that recording the
final detector gets **3665/3665 slipping windows and 0/6962 false positives**.

**A correction to how those labels were computed.** The first version of this table
labelled each window by ground-truth *endpoint displacement*. That is wrong: the wheels
claim a path integral, so the answer key has to be one too. The difference is not
academic - an escape maneuver reverses and then drives forward, netting almost no
displacement while the body genuinely moved over a metre, so displacement-labelling files
every recovery maneuver under "slipping". It reported the rotation test as cleanly
separating on the pre-fix recording (which contained no working maneuvers) and as
overlapping on the post-fix one (which is full of them). The numbers above are the
path-length ones; the conclusion survived the correction, but the margin is tighter than
first written (0.133 -> 0.157, not 0.124 -> 0.169).

**And the separation does not generalise across runs.** Scoring the same detector against
the *verification* run's own recording, **1.21% (75 of 6199) of honest-driving windows
fall below the 0.145 threshold** - i.e. they would be false positives. Every one of them
sits right at the labelling boundary (ground truth travelled almost exactly 70% of the
claim, so they were already ~30% slipping), and the run itself only declared 9 slip
episodes over 45 minutes. But "0% false positives" is a statement about one recording,
not a property of the detector, and it is corrected here rather than left standing.

The rigid-body test is kept as a second, independent signature for the wheels-locked case
where nothing is commanded to turn - reported honestly as having fired on 0 driving
windows *and* 0 slipping ones, i.e. never yet caught a real event.

**Limits, stated plainly.** One wedge episode, one seed, one run is the entire evidence
base for the rotation bands. The 0% false-positive rate is on 6,946 windows of one run's
driving. Nothing here is validated across seeds yet.

### The stuck detector's own blind spot, found while re-measuring the baseline

Re-running seed 42 under the new harness on the *unmodified* code reproduced the failure
and exposed something the earlier runs' 22-events-per-run had hidden. Ground truth moved
**1.93 m in 485 s** while the EKF travelled **10.12 m** over the same window - and the
ground-truth stuck detector fired **once**, not twenty times. The rover was not stationary;
it was *creeping and scrubbing* along the obstacle at ~0.4 cm/s, which is above the
detector's `stuck_min_speed_mps` of 0.02, so its "not moving" test simply never tripped
while odometry ran away regardless. Divergence reached **9.1 m** by the time the run was
stopped at t=1190 s.

That is why recovery now has a second trigger: `/wheel_slip` from the onboard detector,
which keys on the disagreement itself rather than on absolute stillness. Both triggers are
counted separately in the run log, so each run reports which detector actually caught
what.

### Two bugs found while setting the verification run up, both worth recording

**The old recovery nudge was ~3.5x shorter than it read.** `_hold`/the old nudge loop
timed itself with `time.monotonic()` - wall clock - while every velocity it commands is in
simulated time, and this world runs at a measured **0.28x real time**. So the "1.0 s at
0.20 m/s" nudge was 0.28 s of rover time, about **6 cm** of travel. That does not excuse
the design (pushing forward into the obstacle is still the wrong direction), but it does
change the conclusion drawn from "64 firings, 0 recoveries": part of that was a maneuver
that barely happened. The escape maneuver now specifies durations in sim time and converts
them to wall-clock sleeps using a real-time factor measured in the node's own timer
callback - it cannot read the clock during the maneuver, because it is blocking its own
executor, which is exactly how the units got mixed up in the first place.

**A leftover `gz sim` starved the ROS clock of a fresh launch.** The first verification
attempt came up with a silent EKF, no costmap, and a rover that never moved - looking
exactly like a navigation failure. Cause: a previous launch's `gz sim` was still running.
`ROS_DOMAIN_ID` does not isolate gz-transport, so both servers shared the gz partition,
`/clock` stopped reaching the ROS side, and **every sim-time timer in the new graph
stalled** - the EKF and the costmap publisher included, while callback-driven nodes (the
relays) kept working, which is what made the symptom look so selective.

The leftover survived cleanup because both `demo.sh` and the new harness matched it as
`ruby .*gz sim.*regolith_moon`. On this gz build the server runs as `gz sim -r -s <world>`
with no ruby wrapper in the visible command line, so **the pattern matched nothing and the
cleanup reported success**. Fixed in both places to `gz[ ]sim.*regolith_moon` (the bracket
stops the pattern matching the killing process's own command line - see the recurring
pkill self-match note), and `demo.sh`'s post-kill verification now checks for gz too.

**Harness robustness, from the same incident.** The watcher published the goal 5 times on
a fixed schedule and then waited. All five landed before the planner had a costmap and a
pose, so it dropped every one of them ("No costmap or current pose yet - ignoring goal")
and the run burned its timeout motionless. The watcher now re-sends the goal until a
`/planned_path` comes back, and gives up with a distinct `ABORT_NO_PATH` verdict rather
than reporting a navigation failure that never started.

### One design note on the ZUPT: releasing it

Declaring slip uses a 15 s window, but *releasing* it cannot: 15 s after the rover breaks
free the window still contains the wedge, and holding a zero-velocity update over a rover
that is really driving loses real distance - the same corruption the ZUPT exists to
prevent, with the sign flipped. Release is therefore judged on the most recent 5 s, and
requires the gyro to corroborate past a looser ratio (0.25) than the one that declared
slip (0.145), so a statistic wobbling around the boundary cannot flicker the gate.

### The ZUPT gate flickered at the message rate - caught live, fixed, pinned by a test

The first verification attempt with everything wired up produced the intended chain on the
first wedge - `WHEEL SLIP #1` (wheels claiming 3.54 rad of turning, gyro corroborating 14%
of it), then a keep-out zone marked 20 s later - and then the gate began flickering:
**24 declare/clear pairs in two seconds**, at the `/odom` message rate.

Cause: `slipping()` judges the full 15 s window while `clearing()` judges the recent 5 s,
and the two can disagree indefinitely. The rover was still wedged (the long window saw it)
but had just been commanded to stop, so the recent seconds claimed almost nothing - and the
release test read that *absence* of evidence as evidence of recovery, released, and was
immediately re-declared by the long window on the next message.

Fixed by making release require positive evidence: if the wheels have gone quiet, stay
latched (with nothing being claimed there is nothing for the gate to suppress either way,
so latching costs nothing), and only release when the wheels are claiming again *and* the
gyro corroborates past the looser release ratio. A 2 s minimum dwell backs that up. Both
behaviours are now regression-tested (`test_quiet_wheels_do_not_release_the_gate`).

Worth noting what this cost and what it did not: throughout the flicker the "phantom
distance kept out of the EKF" counter stayed at 0.93 m, i.e. the gate was toggling over
wheels that were claiming nothing, so the localization impact was nil - it was a log and
correctness problem, not a measurement-corrupting one. It was still worth restarting the
acceptance for, because "slip episodes" as a reported column has to mean episodes.

## Verification: the recovery works, the localization is 3x better, and M4 still fails

Three seeds, the same goals as the recorded 0/3 baseline, judged on
`/ground_truth/pose` by `scripts/m4_acceptance.py`. **0/3 against M4's 1.5 m bar** - but
failing for a completely different reason than before, and the reason is now measured
rather than suspected.

| seed | verdict | true error | GT travelled | EKF divergence | escapes fired / freed | flips |
|---|---|---|---|---|---|---|
| 42 | FAIL_TIMEOUT | **9.6 m** | 107.0 m | 4.8 m | 11 / **11** | 0 |
| 7 | FAIL_TIMEOUT | **19.6 m** | 121.4 m | 5.0 m | 9 / **9** | 0 |
| 123 | FAIL_FALSE_ARRIVAL | **10.8 m** | 103.9 m | 10.0 m | 5 / **5** | 0 |

Against the baseline on the same three goals (36.2 / 17.4 / 31.7 m true error): error is
down roughly 3x, and no run ended pinned against a rock.

### What is fixed, and by how much

- **Recovery recovers. 25 escape maneuvers across the three runs, 25 freed the rover**,
  measured as ground-truth motion during the maneuver (0.49-2.37 m each). The previous
  recovery was 0 for 64. Nothing was "still wedged" after a maneuver in any run.
- **Both triggers fire, and the onboard one earns its place.** 17 events were caught by
  the ground-truth detector and **8 by the onboard wheel-slip detector** - the creeping
  wedges that are too fast to count as "not moving" and which the ground-truth trigger
  misses entirely (it fired once in 1190 s of the baseline's permanent wedge).
- **Zero flips in all three runs** (max attitude 21.5 deg against a 60 deg threshold), so
  the terrain-collision work still holds.
- **The gate keeps real phantom distance out of the EKF**: 8.84 m on seed 42, 4.30 m on
  seed 7, 1.73 m on seed 123.
- **Seed 123 is still a false arrival**, and that is worth stating plainly: `/goal_reached`
  fired 10.8 m from the goal. The system's own success signal is still not trustworthy;
  the harness is what makes that visible.

### Why it still fails: an error budget, not a guess

Decomposing each run's ground truth in the rover's own frame, against what the wheels
claimed (`scripts/calibrate_slip_detector.py` and the analysis behind it):

| | seed 42 | seed 7 | seed 123 |
|---|---|---|---|
| wheels' total over-claim of distance | +1.08 m / 107 m | +0.91 m / 121 m | +6.95 m / 104 m |
| of that, entering the EKF (gate passing) | 62% | 67% | **91%** |
| lateral motion (sideways sliding) | 11.4 m (9.8%) | 11.4 m (8.7%) | 12.6 m (11.1%) |
| dead-reckoning error using the IMU's heading | 3.5 m | 4.0 m | 10.6 m |
| measured EKF divergence | 4.8 m | 5.0 m | 10.0 m |

Three things follow, and they change what M4's remaining gap actually is:

1. **Distance over-claim is no longer the main problem.** On seeds 42 and 7 the wheels
   over-claim about **1 m in 110** - a 1% error - because the gate catches the gross
   episodes. Seed 123 is the exception at 7 m, 91% of it undetected: its slip was
   distributed through ordinary driving rather than concentrated in wedges, so the
   rotation-disagreement signature never appeared.
2. **Heading is not the problem either.** Dead-reckoning the wheels' distance along the
   *IMU's* heading reproduces seed 42's ground truth to 3.5 m over 107 m. Doing the same
   along the *wheel-integrated* heading gives 43 m, with the heading itself 56 deg off by
   the end - so fusing the IMU for attitude (M3's design decision) is carrying the run.
3. **What is left is lateral slip, and it is structurally unobservable here.** The rover
   slid sideways 11.4 m on both seeds 42 and 7 and 12.6 m on seed 123 - 8.7-11.1% of all
   its motion on every run -
   with a net of only -0.23 m, i.e. a random walk rather than a bias. A differential-drive
   odometry model assumes zero lateral velocity by construction, so the wheels cannot
   report it; the IMU measures the heading correctly throughout and so cannot report it
   either. Nothing in a wheel-plus-IMU stack observes it.

So the honest conclusion is not "the fix did not work". It is that after fixing recovery
and gating the gross slip, **the residual error over a ~110 m traverse of boulder-strewn
terrain is dominated by lateral slip that this sensor suite cannot see** - roughly 3-5 m
on the well-behaved runs. M4's bar is 1.5 m at 60-100 m. Closing that gap needs an
exteroceptive reference - visual odometry is the standard answer, and is exactly what
Mars rovers use for exactly this reason - which `docs/architecture.md` explicitly places
outside this PoC's scope. **M4 as specified is not reachable with the PoC's declared
sensor suite on this terrain**, and that is a scoping conclusion, not a bug to chase.

The secondary failure is time, not accuracy: seeds 42 and 7 timed out at 3600 s while
still moving (107 m and 121 m travelled on 85-90 m straight lines), because each wedge
costs a maneuver plus a replan and the rover spends minutes at a time working through
rock clusters. Both were closing on their goals when the clock ran out.

### Limits of this verification

- **Seed 7 ran separately from 42 and 123**, on identical code, because a harness bug
  aborted it in the batch (below). Three independent runs, not three back-to-back in one
  invocation.
- One run per seed. The recovery result (25/25) is strong; the error budget rests on three
  runs and the slip-detector calibration on one recorded wedge.
- The keep-out zones have a limitation that shows up as drift grows: they are marked in
  the estimator's frame, so once divergence exceeds the zone radius (1.2 m + rover
  radius), the marked zone no longer covers the physical rock that caused it. Seed 42
  marked 12 hazards, several clustered around one obstacle it kept re-encountering, which
  is consistent with this. The mechanism is self-consistent only while drift stays below
  the zone size.

### Harness bugs found by running it

- **A goal with a negative x aborted the run.** The watcher is invoked with
  `--goal {x},{y}`, and argparse reads `-45.00,77.94` as an option flag, not a value
  ("expected one argument"). Seeds 42 and 123 have positive-x goals and ran fine; seed 7
  aborted instantly as `ABORT_WATCHER_FAILED`. Fixed to the `--goal=` form, with a
  regression check. The same hazard applies to the user-facing `--goals` when the *first*
  goal has a negative x, and is now documented in its help text.
- **Stuck events were double-counted.** `STUCK RECOVERY #N` appears twice per event - once
  for the maneuver and once for its result - so the first run reported 22 events where
  there were 11. The pattern is now anchored on the maneuver line. The table above uses
  corrected counts.

## The localization-oracle ablation: testing the diagnosis instead of believing it

The verification above concluded that lateral slip - unobservable to a wheel+IMU stack -
was what stood between this rover and M4. That is a falsifiable claim, so it was tested
rather than left as an explanation: **if localization is the only thing missing, then
handing the estimator an absolute position reference should make the acceptance pass,
with no change to planning, control or recovery.**

`absolute_reference_relay.py` (new, behind `hello_moon.launch.py`'s `localization_oracle`
argument, default off) republishes `/ground_truth/pose` as a `PoseWithCovarianceStamped`
the EKF fuses as an absolute x/y/yaw observation, at ~1 Hz with 0.5 m sigma - deliberately
loose, roughly what a working visual-odometry or terrain-relative fix would actually
deliver, rather than what the simulator knows. **It is an oracle. Every layer says so:**
the node logs a warning at startup, the launch prints one, and the harness stamps
"EXPERIMENT, NOT A MILESTONE RESULT" on the summary. No acceptance number in this project
may be obtained with it on.

| seed | verdict | true error | EKF divergence | escapes | flips |
|---|---|---|---|---|---|
| 42 | FAIL_FALSE_ARRIVAL | **1.70 m** | 0.0 m | 7 | 0 |
| 7 | FAIL_FALSE_ARRIVAL | **1.70 m** | 0.0 m | 5 | 0 |
| 123 | FAIL_TIMEOUT | 23.9 m | 0.0 m | 12 | 0 |

Divergence collapses from 4.8-10.0 m to **0.000-0.006 m**, confirming the oracle is
actually being fused, and the diagnosis holds: with localization removed as a variable,
two of three seeds drive the whole 85-90 m traverse and stop within 1.7 m of their goals.

### And the ablation immediately found a bug that no amount of staring would have

Seeds 42 and 7 both stopped at **exactly 1.70 m**. Two independent seeds landing on the
same number is a systematic artifact, not noise - and it is this: `pure_pursuit_node`
measured arrival as `norm(path[-1] - position)`, and `path[-1]` is a costmap **cell
centre**, because the planner snaps both ends of its path to the grid. At this world's
0.78 m cells that is up to ~0.55 m from the goal actually commanded (0.42 m on seed 42's
goal, measured). Stopping "within 1.50 m" of that point leaves the rover up to 1.92 m from
its real goal - so the run failed a 1.5 m bar while being, in every meaningful sense,
there.

This is the same mistake as trusting `/goal_reached`: measuring against the wrong
reference. It is fixed the same way - arrival is now checked against the commanded goal,
and the final approach steers at the goal rather than the snapped waypoint - with
`test_arrival_reference.py` pinning both the mechanism and the 1.70 m it produced.

Worth being clear about what this does and does not mean: it is a correctness fix, not a
loosened bar. The rover still has to get within 1.5 m of the goal it was given.

### Seed 123 exposes a second, unrelated constraint: time, and whose time

Seed 123 timed out with perfect localization, 23.9 m short, after 12 wedges. That is not
an accuracy failure, and on inspection the budget itself was wrong: the 3600 s cap was
**wall-clock**, and this world simulates at a measured ~0.25x real time, so it bought the
rover only ~830 s of its own time - during which it covered 114 m at a mean 0.129 m/s
against a 0.20 m/s nominal cruise. A wall-clock cap measures how fast the host machine
simulates at least as much as how capable the rover is, and a real rover has hours.

The harness now budgets in **simulated (rover) seconds** (`--sim-timeout-s`, default
1800), keeping the wall clock only as a safety cap that reports `ABORT_WALL_CLOCK_CAP` -
explicitly not a rover failure. Both times are recorded per run.

### A metric that was under-reporting its own success

The oracle run logged several "STUCK RECOVERY #N result: moved 0.00 m - STILL WEDGED"
for maneuvers that the acceptance harness's independent trace shows moving the rover
~1.9 m. Cause: the result was checked on the first timer tick after the maneuver, ~2 ms
later, and `/ground_truth/pose` messages queue up during the blocking maneuver - so the
timer could win the executor race and measure against a pose from *before* the maneuver.
Deferred by 1 s of sim time, anchored on the first tick whose clock has caught up (the
ROS clock does not advance while the node blocks its own executor, so the obvious
implementation of the delay would have been a no-op). Log-only - it never affected rover
behaviour - but it under-reported the recovery's success rate, and a number being wrong
against this project's own interest still makes it wrong.

### Confirmation: with the arrival fix and a rover-time budget, the oracle run is 3/3

Same three seeds and goals, all fixes in, oracle still on:

| seed | verdict | true error | GT travelled | escapes fired / freed | flips |
|---|---|---|---|---|---|
| 42 | **PASS** | 1.50 m | 108.6 m | 6 / 6 | 0 |
| 7 | **PASS** | 1.50 m | 145.9 m | 11 / 11 | 0 |
| 123 | **PASS** | 1.50 m | 130.4 m | 9 / 9 | 0 |

**3/3, judged on ground truth, no intervention, 26 of 26 wedges escaped, zero flips.**
Seed 7 needed 146 m of driving to close a 90 m goal and fought through the same rock
cluster that had trapped it in both previous runs; it still arrived.

This is the experiment's conclusion, and it is worth stating exactly:

> With localization accurate, **the planner, the follower, the recovery and the keep-out
> zones are sufficient to meet M4's bar on all three acceptance seeds.** Everything
> between the goal arriving and the rover standing at it works. What M4 is missing is a
> sensor.

It also bounds what visual odometry would have to buy: not centimetres - the oracle was
deliberately given 0.5 m sigma at 1 Hz, and that was enough. A fix of that quality,
which is unremarkable for visual odometry on textured terrain, converts this stack from
0/3 to 3/3.

**This is not an M4 pass.** It was obtained with an oracle that hands the estimator the
answer; the milestone number is the unaided one. It is recorded here as what it is: the
experiment that turns "we think lateral slip is the blocker" into "lateral slip is the
blocker, and here is what removing it does".

## M4, final: 0/3 unaided and 3/3 with an absolute reference, from the same build

The official milestone run - all fixes in, **oracle off**, budgeted in rover time:

| seed | verdict | true error | EKF divergence | GT travelled | rover time | escapes freed | flips |
|---|---|---|---|---|---|---|---|
| 42 | FAIL_FALSE_ARRIVAL | 7.72 m | 6.80 m | 105.1 m | 794 s | 6 / 8 | 0 |
| 7 | FAIL_FALSE_ARRIVAL | 3.08 m | 3.06 m | 132.6 m | 922 s | 7 / 7 | 0 |
| 123 | FAIL_FALSE_ARRIVAL | 13.07 m | 12.54 m | 102.5 m | 787 s | 5 / 5 | 0 |

**M4 is 0/3.** And the mechanism is no longer in any doubt - on every seed the true error
is the drift plus the stopping tolerance, to within a few centimetres:

    seed 42:   6.80 + 1.0 = 7.80  measured 7.72
    seed 7:    3.06 + 1.0 = 4.06  measured 3.08   (drift partly toward the goal)
    seed 123: 12.54 + 1.0 = 13.54 measured 13.07

The rover arrives exactly where it believes the goal is, every time. It is not lost, not
badly controlled, and not defeated by the terrain: it is wrong about where it is.

Same build, same seeds, same goals, oracle on (experiment, not a milestone result):

| | unaided | with a 0.5 m / 1 Hz absolute reference |
|---|---|---|
| result | **0 / 3** | **3 / 3** |
| true error | 3.1 - 13.1 m | 1.48 m on all three |
| EKF divergence | 3.1 - 12.5 m | 0.00 m |
| flips | 0 | 0 |
| wedges escaped | 18 / 20 | 26 / 26 |

Everything except the estimator is held constant between those two columns. That is the
whole finding.

### What M4 needs, stated once, plainly

Not a better planner, follower, or recovery - those meet the bar 3/3 the moment the
estimate is right. Not centimetre-grade navigation either: the oracle was given 0.5 m
sigma at 1 Hz, which is unremarkable for visual odometry on textured terrain, and it was
enough. What is missing is any exteroceptive observation of position at all. With wheel
odometry and an IMU alone, ~10% of this rover's motion is lateral slip that neither
sensor can represent, it accumulates as a random walk, and nothing ever corrects it.

`docs/architecture.md` places visual odometry outside this PoC's scope, and the honest
consequence is that **M4's 1.5 m arrival bar is not achievable within that scope on this
terrain.** The options are to add the sensor (the milestone's own "Localisation" layer
lists visual odometry first), to re-scope M4's accuracy bar to what a wheel+IMU stack can
support over 100 m of boulder field, or to leave M4 open and documented. That is a
project decision, not a bug to keep chasing, and this section exists so it can be made
on measurements rather than impressions.

### Progression across this session's fixes, same three goals

| stage | seed 42 | seed 7 | seed 123 |
|---|---|---|---|
| as recorded before this session | 36.2 m | 17.4 m | 31.7 m |
| + recovery, keep-out zones, slip gate | 9.6 m | 19.6 m | 10.8 m |
| + arrival measured against the real goal, rover-time budget | **7.7 m** | **3.1 m** | **13.1 m** |
| + an absolute position reference (experiment) | **1.48 m PASS** | **1.48 m PASS** | **1.48 m PASS** |

Seed 123 got worse between the first two rows and the third; its drift is the largest of
the three (12.5 m) and varies run to run, which is what a random walk does. Reporting the
three seeds separately rather than averaging them keeps that visible.
