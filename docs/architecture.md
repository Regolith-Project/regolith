# Regolith Architecture Overview

## Design Philosophy

Regolith is not a clean-room rewrite of rover autonomy. It is a **fork of Autoware**, which means it inherits a battle-tested ROS 2 architecture, a proven perception-planning-control pipeline, and an active upstream community. The development effort focuses on **planetary-specific adaptations** - replacing road assumptions with terrain assumptions - rather than rebuilding middleware from scratch.

## System Layers

### 1. Hardware Abstraction Layer (HAL)

The HAL provides standardised ROS 2 interfaces for:

- **Sensors**: cameras (mono/stereo/thermal), IMU, lidar, radar, wheel encoders
- **Actuators**: drive motors, steering, braking
- **Rover kinematics**: Ackermann, skid-steer, differential drive, and custom configurations

This means you can swap rover platforms by implementing a thin driver - Regolith's autonomy stack doesn't change.

### 2. Localisation

GPS-denied pose estimation via multi-sensor fusion:

- Visual odometry (stereo or monocular)
- Inertial measurement unit (IMU) integration
- Wheel odometry with slip compensation
- Confidence-weighted Extended Kalman Filter
- Fault detection: graceful degradation when sensors fail

**Target**: <5% position drift over 500 m traverse.

### 3. Perception

Environment mapping adapted for planetary surfaces:

- Terrain heightmap and obstacle detection
- Traversability assessment (slope, roughness, surface type)
- Costmap generation for the navigation planner
- Designed for challenging lighting: shadows, glare, low sun angle

### 4. Navigation & Planning

Autonomous waypoint traversal over unknown terrain:

- **Global planner**: waypoint sequencing with terrain-aware cost
- **Local planner**: reactive obstacle avoidance
- **Trajectory follower**: smooth path execution
- Keep-out zone enforcement and dynamic re-planning

### 5. Mission Manager

High-level mission execution:

- Waypoint sequences
- Start/stop/pause autonomy
- Mode transitions (manual → assisted → autonomous)
- Telemetry and status reporting

## Repository Structure

Regolith follows the same two-tier layout as upstream Autoware:

- **`regolith`** (this repo) is the meta-repo. It holds no package source of its
  own - only `regolith.repos` (pins the packages repo), top-level docs, and the
  demo/launch scripts under `scripts/`. Run `scripts/setup.sh` to pull in
  `regolith.universe` and build.
- **[`regolith.universe`](https://github.com/Regolith-Project/regolith.universe)**
  is a genuine GitHub fork of
  [`autoware.universe`](https://github.com/autowarefoundation/autoware_universe),
  preserving fork relationship and history. Car-specific packages (lane/HD-map
  planning, traffic-light logic, NDT map localisation, etc.) are currently
  excluded from the build by building only the planetary packages
  (`--packages-up-to regolith_bringup` in `scripts/setup.sh`); a proper
  `COLCON_IGNORE`/stripping pass over the untouched upstream tree is deferred
  (see PROGRESS.md). See the reuse log below for which Autoware components
  were reused vs. replaced. New planetary packages live under `planetary/` in
  that repo, namespaced `regolith_*`.

## Hello-World PoC Scope

The sections above describe Regolith's long-term architectural vision. The
first working demo deliberately narrows this to prove the pipeline end-to-end
before broadening it:

- **Localisation** fuses wheel odometry + IMU. `regolith_visual_odometry`
  ships alongside it and is **off by default**, because a controlled
  comparison measured it making localisation worse on every seed.
  Visual odometry was originally scoped out of this PoC, and was brought in
  because measurement said the milestone could not be met without it, not
  because the scope drifted. M4's acceptance failed 0/3 with an arrival error
  of 3.1-13.1 m, and on every seed that error equalled the EKF's own divergence
  plus the stopping tolerance to within centimetres - the rover was arriving
  exactly where it believed the goal was. Roughly 10% of its motion over this
  terrain is *lateral* slide, which a differential-drive odometry model asserts
  is zero by construction and an IMU cannot observe, so nothing in the stack
  ever corrected it. `regolith_visual_odometry` publishes body-frame velocity
  from the onboard RGB + depth cameras, and the EKF fuses its `vy` - the term
  nothing else could see. Its `vx` is measured biased ~30% low and is
  deliberately *not* fused, because gated wheel odometry measures forward
  distance to about 1%.
  **Then the same-build comparison contradicted the design argument.** With
  `vy` fused, EKF divergence went 0.4 → 1.4 m, 0.7 → 24.7 m and 6.1 → 15.2 m
  on seeds 42/7/123, taking M4 from 1/3 to 0/3, so the default is `false` and
  the reasoning above stands only as the reason the package exists. Its
  lateral channel is genuinely unbiased in isolation (+0.000 ± 0.018 m/s over
  130 real frame pairs), which is precisely why per-estimate accuracy is not
  evidence about in-run behaviour. Turn it on with `visual_odometry:=true` if
  you are working on the conditioning problem; do not turn it on expecting a
  better estimate. See `regolith_visual_odometry/README.md` for the accuracy
  measurements and the three defects that only real imagery exposed, and
  PROGRESS.md for the comparison.
  The 0/3 and 1/3 figures above are single runs from two different builds and
  should not be read as the system's success rate: repeats of one seed on one
  build have since produced both a pass at 1.50 m and failures at 5.69 and
  7.76 m. See PROGRESS.md, "The stopping tolerance, measured", for the spread.
- Visual odometry is a *relative* sensor: it slows drift rather than bounding
  it, and there is still no absolute position reference anywhere in the stack.
  So an error introduced while the rover is wedged remains costly, and wheel
  slip is still gated rather than fused blindly: `wheel_slip_node` republishes
  `/odom` as `/odom/gated` with a zero-velocity update substituted while it
  detects the wheels turning without the body moving, from onboard signals
  only. See PROGRESS.md for the measured detection thresholds and their
  false-positive rate.
- **The costmap comes from the generated terrain heightmap** (the world is
  known a priori), not from onboard perception. Sensor-derived costmaps are
  the explicit next milestone after this PoC - the rover still genuinely
  plans and navigates, it just starts from a map instead of building one.
- **The ground is drawn from a mesh, not from the heightmap.** The same
  surface ships twice: as `heightmap.png` for the costmap, and as
  `terrain.obj` for Gazebo's visual. A `<heightmap>` visual is rendered by
  Ogre-Next's Terra, whose distance LOD point-samples the terrain coarser the
  further it is from the camera - so distant ground gets drawn below where
  the data puts it, and the boulders standing on it hang visibly in the air
  while every geometry test passes. A `<mesh>` has no LOD. See
  `terrain_mesh.py`, and `test_rendered_terrain_seats_rocks.py` for the
  screenshot-based regression test that can actually see a rendering fault.
- Lunar gravity (1.62 m/s²) is modelled; wheel friction/damping is tuned for
  controllability rather than strict physical accuracy.

- **Keep-out zones are learned from stuck events, not perceived.** The a-priori
  costmap knows where the rocks are but not which gaps between them are really
  drivable. When the rover wedges, the recovery node publishes the spot and
  `costmap_node` marks it lethal, so the planner stops routing back into it.
  This is the "keep-out zone enforcement" bullet above, in its minimal form.

Out of scope for this milestone: SLAM and loop closure, sensor-derived
costmaps, additional rover models, ML terrain classification, adaptive speed
governors, real hardware. (Visual odometry *was* on this list; see the
Localisation bullet above for the measurement that moved it off.) FDIR is deliberately small but no longer just
stop-and-replan: a reverse/turn escape manoeuvre with keep-out marking, plus
the slip gate above. Everything more elaborate stays out.

### Autoware Component Reuse Log

Every reuse-vs-replace decision made while building the PoC is logged here as
it happens, with a one-line rationale.

| Autoware component | Decision | Rationale |
|---|---|---|
| _(none - M1 is a greenfield package)_ | N/A | `regolith_terrain_gen` has no car-driving analogue in Autoware; procedural terrain/world generation for simulation is a planetary-specific addition, not a fork of an existing component. |
| _(none - M2 is a greenfield package)_ | N/A | `regolith_rover_description`/vehicle simulation has no Autoware analogue either: Autoware assumes a car-shaped vehicle interface, not a skid-steer rover description or a `gz-sim` DiffDrive-based simulated drivetrain. The vehicle *interface* layer (translating stack trajectory commands to skid-steer `cmd_vel`) is still planned as a genuine reuse point in `regolith_vehicle_interface` (M4). |
| `ekf_localizer` → **replaced** with `robot_localization`'s `ekf_node` | Replaced | `ekf_localizer` is entirely absent from this fork's checked-out `autoware_universe` tree (not under `localization/`, not in any `.repos` file) - it isn't a case of "hard to integrate," there's nothing here to integrate. Migrating it in would mean pulling in and vetting a whole separate external repo, matching the plan's own "disproportionate for this PoC" escape hatch. `robot_localization` (ROS ecosystem standard, already installed as this exact fallback) fuses wheel odometry + IMU into `odom -> base_link` instead. **To migrate to `ekf_localizer` later**: locate wherever upstream Autoware now ships it (likely a separate `autoware_localization` or similarly-named repo added via `.repos`), confirm its input topic conventions (it expects `nav_msgs/Odometry` inputs with specific covariance/twist conventions, similar to what we already produce), and swap the `ekf_node` launch/config in `localization_demo.launch.py` for `ekf_localizer`'s node + its own YAML schema - the surrounding topic wiring (odom, imu, ground-truth comparison) shouldn't need to change. |
| _(none - `regolith_visual_odometry` is a greenfield package)_ | N/A | Autoware's localisation stack is built around NDT matching against a pre-built HD point-cloud map, which is exactly the assumption a planetary rover cannot make: there is no prior map of the terrain and no survey to register against. Its visual-odometry-adjacent components are likewise tied to `autoware_localization_msgs` and a map frame that does not exist here. What was needed instead is small and specific - observe body-frame lateral velocity from an RGB-D pair so the EKF can correct a slip term wheel odometry cannot represent - so it is written directly against OpenCV in ~250 lines, with the geometry ROS-free and unit-tested. **To reuse an Autoware/`ros-perception` component later**: the natural swap is any node publishing `nav_msgs/Odometry` with a body-frame twist (e.g. `rtabmap_odom`); `ekf.yaml`'s `odom1` would point at it unchanged. The reason not to now is that it would bring a mapping/SLAM stack along with it, which is still out of scope. |
| `autoware_pure_pursuit` → **replaced** with a minimal in-house follower | Replaced | Unlike `ekf_localizer`, this package genuinely exists in the fork, but it depends on `autoware_control_msgs`/`autoware_planning_msgs`/`autoware_trajectory_follower_base`/`autoware_vehicle_info_utils` and outputs a steering-tire-angle `Control` message - it's an Ackermann lateral controller. Retrofitting it for skid-steer would mean pulling in that whole dependency chain and then converting steering-angle output back into differential wheel commands, plus its own path-curvature geometry assumes Ackermann kinematics in the first place. `regolith_vehicle_interface/pure_pursuit_node.py` computes linear+angular velocity directly instead - simpler and a more natural fit for skid-steer, and it's the plan's own explicit fallback. **To migrate to `autoware_pure_pursuit` later** (e.g. if the rover became Ackermann-steered): would need the full `autoware_control_msgs`/`autoware_planning_msgs`/`autoware_trajectory_follower_base` dependency chain built, a `regolith_vehicle_interface` adapter converting its `Control` (steering angle) output to whatever the target drivetrain expects, and the planner's `nav_msgs/Path` output converted to `autoware_planning_msgs/Trajectory`. |

## Simulation Environment

Gazebo-based planetary analogue worlds with:

- Procedurally generated rocky terrain with slopes
- Configurable lighting (sun angle, shadows, HDR)
- Reference rover model with standard sensor suite
- Benchmark scenarios with quantitative KPIs
- CI-integrated test suite for regression testing

## Technology Stack

| Layer | Technology |
|---|---|
| Middleware | ROS 2 (Humble / Jazzy) |
| Communication | DDS (CycloneDDS / FastDDS) |
| Languages | C++ (performance-critical), Python (tools/scripts) |
| Simulation | Gazebo Harmonic, NVIDIA ISAAC Sim (planned) |
| Build | colcon, CMake, ament |
| CI/CD | GitHub Actions |
| License | Apache 2.0 |

## Relationship to Autoware

Regolith forks from [Autoware](https://autowarefoundation.github.io/autoware-documentation/) and adapts its architecture:

- **Kept**: modular package structure, ROS 2 lifecycle management, launch system patterns, CI/CD approach
- **Replaced**: road/lane models → terrain models; GPS dependency → visual-inertial localisation; traffic rules → hazard avoidance; HD map assumption → online mapping
- **Added**: terrain traversability assessment, resource-constrained execution profiles, planetary simulation environments

Upstream improvements that benefit both projects will be contributed back to the Autoware community.
