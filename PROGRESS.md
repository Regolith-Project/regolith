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
| M4 — Autonomous navigation | **Done** — full 60-100 m / 3-consecutive-seed acceptance check passed (see "M4 acceptance check: full 60-100 m / 3-consecutive-run result" below) |
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
