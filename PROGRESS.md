# Progress Log

Tracks milestone status, decisions, issues, and exact commands that worked.
See `docs/architecture.md` for the pipeline description and the Autoware
component reuse log.

## Status

| Milestone | Status |
|---|---|
| M0 — Environment verified | Done |
| M1 — Procedural lunar terrain | Not started |
| M2 — Rover spawns and drives (teleop) | Not started |
| M3 — Localization | Not started |
| M4 — Autonomous navigation | Not started |
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

## Issues encountered

- This Claude Code session runs as a background job with no attached TTY, so
  neither `sudo` nor `gh auth login`'s interactive prompts could be driven
  from here directly. Resolved by having the user configure passwordless
  `sudo` for their own account and complete GitHub's device-code auth flow
  (`gh auth login --web`) from their side.
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
