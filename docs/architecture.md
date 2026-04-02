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
