<p align="center">
  <img src="docs/assets/regolith_logo_slogan.png" alt="Regolith — Open-Source Rover Autonomy" width="400">
</p>

<p align="center">
  <strong>Open-source autonomous navigation for planetary rovers</strong><br>
  A fork of <a href="https://github.com/autowarefoundation/autoware">Autoware</a>, adapted for GPS-denied rough-terrain autonomy
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
  <a href="https://www.ros.org/"><img src="https://img.shields.io/badge/ROS%202-Humble%20|%20Jazzy-blue?logo=ros" alt="ROS 2"></a>
  <a href="https://github.com/Regolith-Project/regolith/issues"><img src="https://img.shields.io/github/issues/Regolith-Project/regolith" alt="Issues"></a>
</p>

---

## The Problem

Every autonomous planetary rover runs proprietary navigation code. University rover teams rebuild autonomy from scratch every year. Startups face years of development before their rover can navigate a rock field. There is no open-source equivalent of what [Autoware](https://autoware.org/) did for self-driving cars — but for rovers on rough terrain.

## What Regolith Does

Regolith takes the proven Autoware ROS 2 architecture — perception, planning, control — and replaces road-driving assumptions with planetary rover requirements:

| Autoware (roads) | Regolith (rough terrain) |
|---|---|
| GPS + HD maps | Visual-inertial odometry, no GPS |
| Lane-following on pavement | Terrain-aware waypoint navigation |
| Traffic rules & signals | Hazard avoidance & traversability |
| Abundant compute (x86 server) | Resource-constrained embedded boards |

**The goal:** clone the repo, build it, launch the simulation, and watch a rover autonomously navigate between waypoints across a rocky, sloped planetary landscape — no hardware required.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Mission Manager                       │
│              (waypoints, keep-out zones)                 │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────────┐
        ▼              ▼                  ▼
┌──────────────┐ ┌───────────────┐ ┌──────────────┐
│ Localisation │ │  Navigation   │ │  Perception  │
│              │ │  & Planning   │ │              │
│ Visual odom  │ │ Global plan   │ │ Terrain map  │
│ IMU fusion   │ │ Local planner │ │ Obstacle det │
│ Wheel odom   │ │ Traj follower │ │ Traversab.   │
│ Fault detect │ │ Hazard avoid  │ │ Costmap gen  │
└──────┬───────┘ └──────┬────────┘ └──────┬───────┘
       │                │                  │
       └────────────────┼──────────────────┘
                        ▼
          ┌──────────────────────────┐
          │  Hardware Abstraction    │
          │  Layer (HAL)             │
          │                          │
          │  Sensor interfaces       │
          │  Actuator interfaces     │
          │  Rover kinematics        │
          └──────────┬───────────────┘
                     ▼
          ┌──────────────────────────┐
          │  Your Rover / Simulator  │
          │  (Gazebo, ISAAC Sim,     │
          │   Leo Rover, Husky, ...) │
          └──────────────────────────┘
```

## Project Status

> **🚧 Early development

Regolith is in active early development. The current milestone focuses on:

1. **ROS 2 Hardware Abstraction Layer** — sensor/actuator interfaces and rover kinematics
2. **Localisation & Navigation pipeline** — GPS-denied pose estimation + waypoint traversal, validated in simulation
3. **Planetary simulation environment** — Gazebo worlds with rocks, slopes, and realistic lighting for benchmarking

See the [Roadmap](#roadmap) below for details.

## Quick Start

> Coming soon — the first simulation release is targeted for mid-2026. When ready:
>
> ```bash
> # Clone
> git clone https://github.com/Regolith-Project/regolith.git
> cd regolith
>
> # Build (ROS 2 Humble/Jazzy)
> colcon build --symlink-install
>
> # Launch simulation
> ros2 launch regolith_bringup simulation.launch.py
> ```
>
> This will spawn a rover in a planetary-analogue Gazebo world and begin autonomous waypoint navigation.

## Roadmap

### Current Milestone (NLnet NGI Zero Commons Fund)

| Phase | Focus | Target |
|---|---|---|
| **WP1** | Autoware fork, architecture, HAL interfaces | Architecture doc + interface packages |
| **WP2** | GPS-denied localisation (VIO + IMU + wheel odom fusion) | <5% drift over 500 m traverse |
| **WP3** | Terrain-aware navigation + obstacle avoidance | Autonomous 5-waypoint route in simulation |
| **WP4** | Gazebo planetary simulation environment + benchmarks | Turnkey sim with rocks, slopes, shadows |
| **WP5** | Documentation + community bootstrap | Clone → build → run in under 1 hour |

### Future Vision

- 🔬 **Advanced perception** — HDR stereo vision, lidar processing for extreme lighting
- 🏔️ **Terrain classification** — ML-based surface detection (rock, sand, dust, bedrock)
- ⚡ **Adaptive speed governor** — look-ahead risk-aware speed control
- 🤖 **Hardware validation** — Leo Rover, Clearpath Husky, custom platforms
- 🏜️ **Field demos** — ESA Mars Yards, planetary analogue sites
- 🛰️ **Space-grade hardening** — ECSS alignment, FPGA offload, real-time determinism

## Built On

Regolith stands on the shoulders of excellent open-source projects:

- **[Autoware](https://autowarefoundation.github.io/autoware-documentation/)** — the autonomous driving stack we fork from
- **[ROS 2](https://docs.ros.org/)** — robotics middleware
- **[Gazebo](https://gazebosim.org/)** — simulation
- **[Nav2](https://navigation.ros.org/)** — ROS 2 navigation framework
- **[NVIDIA ISAAC Sim](https://developer.nvidia.com/isaac-sim)** — high-fidelity simulation (planned)

## Who Is This For?

- **🎓 University rover teams** — stop rewriting navigation every year. Start from a working stack.
- **🏢 Space industry** — a shared benchmark and reference implementation for ESA/Terrae Novae rover programmes.
- **🔧 ROS 2 developers** — standard packages that work with your existing tf2, sensor_msgs, Nav2 setup.
- **🔬 Researchers** — a reproducible simulation testbed for rough-terrain autonomy research.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Whether you're fixing a typo, adding a sensor driver, improving the planner, or building a new simulation world — we'd love your help.

## About

Regolith is developed by [Astro42](https://astro42.com) (Wozify Engineering Group Kft), a Budapest-based European space software consultancy with an ESA track record. Project funding is pending.

## License

Regolith is licensed under the [Apache License 2.0](LICENSE).

```
Copyright 2026 Wozify Engineering Group Kft (t/a Astro42)

Licensed under the Apache License, Version 2.0
```
