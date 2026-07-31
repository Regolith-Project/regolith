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
| M3 — Localization | Substantially done (see notes) |
| M4 — Autonomous navigation | Pipeline built and individually verified; full acceptance not met (see notes) |
| M5 — Demo polish and packaging | Not started |

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

**Status: full pipeline built and each stage individually verified working;
the "3 consecutive full 60-100 m runs" acceptance criterion is not met.**
Recorded honestly, same as M3 - real progress, real remaining gap.

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
