# Regolith Architecture Overview

## Design Philosophy

Regolith is not a clean-room rewrite of rover autonomy. It is a **fork of Autoware**, which means it inherits a battle-tested ROS 2 architecture, a proven perception–planning–control pipeline, and an active upstream community. The development effort focuses on **planetary-specific adaptations** — replacing road assumptions with terrain assumptions — rather than rebuilding middleware from scratch.

## System Layers

### 1. Hardware Abstraction Layer (HAL)

The HAL provides standardised ROS 2 interfaces for:

- **Sensors**: cameras (mono/stereo/thermal), IMU, lidar, radar, wheel encoders
- **Actuators**: drive motors, steering, braking
- **Rover kinematics**: Ackermann, skid-steer, differential drive, and custom configurations

This means you can swap rover platforms by implementing a thin driver — Regolith's autonomy stack doesn't change.

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
  own — only `regolith.repos` (pins the packages repo), top-level docs, and the
  demo/launch scripts under `scripts/`. Run `scripts/setup.sh` to pull in
  `regolith.universe` and build.
- **[`regolith.universe`](https://github.com/Regolith-Project/regolith.universe)**
  is a genuine GitHub fork of
  [`autoware.universe`](https://github.com/autowarefoundation/autoware_universe),
  preserving fork relationship and history. Car-specific packages (lane/HD-map
  planning, traffic-light logic, NDT map localisation, etc.) are excluded from
  the build via `COLCON_IGNORE`; reusable packages (common utilities, Autoware
  message definitions, `ekf_localizer`, trajectory/control components) are kept.
  New planetary packages live under `planetary/` in that repo, namespaced
  `regolith_*`.

## Hello-World PoC Scope

The sections above describe Regolith's long-term architectural vision. The
first working demo (an NLnet NGI Zero Commons Fund milestone) deliberately
narrows this to prove the pipeline end-to-end before broadening it:

- **Localisation** fuses wheel odometry + IMU only — no visual odometry yet.
  Bounded drift over a short traverse is acceptable and is visualized
  (estimated vs. ground-truth pose), not hidden.
- **The costmap comes from the generated terrain heightmap** (the world is
  known a priori), not from onboard perception. Sensor-derived costmaps are
  the explicit next milestone after this PoC — the rover still genuinely
  plans and navigates, it just starts from a map instead of building one.
- Lunar gravity (1.62 m/s²) is modeled; wheel friction/damping is tuned for
  controllability rather than strict physical accuracy.

Out of scope for this milestone: visual odometry/SLAM, sensor-derived
costmaps, additional rover models, ML terrain classification, adaptive speed
governors, FDIR beyond stop-and-replan, real hardware.

### Autoware Component Reuse Log

Every reuse-vs-replace decision made while building the PoC is logged here as
it happens, with a one-line rationale.

| Autoware component | Decision | Rationale |
|---|---|---|
| _(none — M1 is a greenfield package)_ | N/A | `regolith_terrain_gen` has no car-driving analogue in Autoware; procedural terrain/world generation for simulation is a planetary-specific addition, not a fork of an existing component. |
| _(none — M2 is a greenfield package)_ | N/A | `regolith_rover_description`/vehicle simulation has no Autoware analogue either: Autoware assumes a car-shaped vehicle interface, not a skid-steer rover description or a `gz-sim` DiffDrive-based simulated drivetrain. The vehicle *interface* layer (translating stack trajectory commands to skid-steer `cmd_vel`) is still planned as a genuine reuse point in `regolith_vehicle_interface` (M4). |
| `ekf_localizer` → **replaced** with `robot_localization`'s `ekf_node` | Replaced | `ekf_localizer` is entirely absent from this fork's checked-out `autoware_universe` tree (not under `localization/`, not in any `.repos` file) - it isn't a case of "hard to integrate," there's nothing here to integrate. Migrating it in would mean pulling in and vetting a whole separate external repo, matching the plan's own "disproportionate for this PoC" escape hatch. `robot_localization` (ROS ecosystem standard, already installed as this exact fallback) fuses wheel odometry + IMU into `odom -> base_link` instead. **To migrate to `ekf_localizer` later**: locate wherever upstream Autoware now ships it (likely a separate `autoware_localization` or similarly-named repo added via `.repos`), confirm its input topic conventions (it expects `nav_msgs/Odometry` inputs with specific covariance/twist conventions, similar to what we already produce), and swap the `ekf_node` launch/config in `localization_demo.launch.py` for `ekf_localizer`'s node + its own YAML schema - the surrounding topic wiring (odom, imu, ground-truth comparison) shouldn't need to change. |

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
