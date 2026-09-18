#!/usr/bin/env python3
# Copyright 2026 Regolith Project contributors
# SPDX-License-Identifier: Apache-2.0
"""Render still frames of a generated world from arbitrary viewpoints, headless.

Why this exists
---------------
Every visual change in this repo - terrain material, rover geometry, lighting, sky -
is a claim about what gz DRAWS, and this project's convention is that such a claim is
verified by a render, not by comparing arrays or inspecting the SDF. Until now the only
render paths were the GUI (needs a human at a window) and the CameraVideoRecorder (an
mp4 of a whole run). Neither gives a tight "change one line, look at the result" loop.

This does: it generates the real shipped world for a seed, splices in one or more
camera-only rigs at poses you choose, runs the server headless for a few seconds, and
writes a PNG per rig.

How it renders
--------------
The rigs are ordinary `<sensor type="camera">` blocks in camera-only static models, and
the frames come back over `ros_gz_bridge` - the same path the rover's own cameras use,
so what lands in the PNG is what the sensor pipeline produces. The server is started
through `ros2 launch ros_gz_sim gz_sim.launch.py`, NOT by invoking `gz sim -s` directly:
a direct `gz sim -s` on a generated world segfaults in the Ogre2/Sensors path on this
install (see PROGRESS.md / the WSL notes), while this route is the one that works.

Each invocation claims a private ROS_DOMAIN_ID and kills its own process group on the
way out, so concurrent renders (and any live demo run) cannot collide.

Usage
-----
    # three preset views of seed 42, rover included
    scripts/render_still.py --seed 42 --preset hero,orbit,onboard -o docs/media/dev

    # an explicit camera: position, look-at target, field of view
    scripts/render_still.py --seed 42 --view 5,-6,3.2:0,0,0.2:1.0 -o /tmp/shots

    # what the rover's own mast sees, and no rover in frame
    scripts/render_still.py --seed 42 --preset orbit --no-rover
"""

import argparse
import json
import math
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
WORLD_NAME = "regolith_moon"


def _look_at_rpy(eye, target):
    """roll/pitch/yaw for a gz camera at `eye` aimed at `target` (camera looks along +x)."""
    dx, dy, dz = (target[0] - eye[0], target[1] - eye[1], target[2] - eye[2])
    yaw = math.atan2(dy, dx)
    pitch = -math.atan2(dz, math.hypot(dx, dy))
    return 0.0, pitch, yaw


def _rig_sdf(index, pose, width, height, hfov, far=3000.0):
    x, y, z, roll, pitch, yaw = pose
    return f"""    <model name="render_rig_{index}">
      <static>true</static>
      <pose>{x:.4f} {y:.4f} {z:.4f} {roll:.4f} {pitch:.4f} {yaw:.4f}</pose>
      <link name="link">
        <sensor name="rig_{index}" type="camera">
          <always_on>1</always_on>
          <update_rate>5</update_rate>
          <topic>render/cam{index}</topic>
          <camera>
            <horizontal_fov>{hfov:.4f}</horizontal_fov>
            <image><width>{width}</width><height>{height}</height></image>
            <clip><near>0.05</near><far>{far:.1f}</far></clip>
          </camera>
        </sensor>
      </link>
    </model>
"""


def _presets(spawn_xy, spawn_z):
    """Named viewpoints, all expressed relative to the spawn point and its elevation.

    Absolute poses do not survive a seed change: spawn elevation is seed-dependent
    (5.2 m on seed 42, 6.1 m on seed 7), so a fixed z is a different height above the
    ground for every seed - and a camera can end up underground.
    """
    sx, sy = spawn_xy
    return {
        # Rover three-quarter view, low and close - the "product shot".
        "hero": ((sx - 2.6, sy - 2.2, spawn_z + 1.1), (sx, sy, spawn_z + 0.18), 1.0),
        # Chest-height view down the drive direction; shows terrain, not the rover.
        "terrain": ((sx - 1.0, sy - 1.0, spawn_z + 1.6), (sx + 40.0, sy + 34.0, spawn_z), 1.2),
        # High orbital-ish look-down over the landscape.
        "orbit": ((sx - 45.0, sy - 45.0, spawn_z + 32.0), (sx + 10.0, sy + 10.0, spawn_z), 1.1),
        # Ground-grazing shot into the sun-lit horizon: the shot that shows sky,
        # far-field terrain and the low-sun shadow rake.
        "horizon": ((sx - 3.0, sy - 3.0, spawn_z + 0.35), (sx + 60.0, sy + 55.0, spawn_z + 2.0), 1.3),
        # Close on the wheels/ground contact - the detail shot for the rover build.
        "detail": ((sx - 0.85, sy - 0.75, spawn_z + 0.35), (sx, sy, spawn_z + 0.14), 1.0),
    }


def _bake_rover(world_sdf_path, output_dir, spawn_z, cine_camera="none"):
    """Splice the rover model into the world exactly as hello_moon.launch.py does."""
    import xacro

    xacro_path = (
        REPO_ROOT
        / "src/regolith.universe/planetary/regolith_rover_description/urdf/regolith_rover.urdf.xacro"
    )
    urdf_xml = xacro.process_file(
        str(xacro_path), mappings={"record_video": "false", "cine_camera": cine_camera}
    ).toxml()
    rover_urdf = output_dir / "rover.urdf"
    rover_urdf.write_text(urdf_xml)
    converted = subprocess.run(
        ["gz", "sdf", "-p", str(rover_urdf)], capture_output=True, text=True, check=True
    ).stdout
    model_sdf = converted[converted.index("<model ") : converted.rindex("</model>") + len("</model>")]
    marker = "<model name='regolith_rover'>"
    if not model_sdf.startswith(marker):
        raise RuntimeError("gz sdf -p output did not start with the expected model tag")
    return f"<model name='rover'>\n    <pose>0 0 {spawn_z} 0 0 0</pose>" + model_sdf[len(marker) :]


def build_world(seed, views, width, height, with_rover, cine_light, out_world_dir):
    """Generate the world for `seed`, splice in the rover and the camera rigs."""
    sys.path.insert(
        0, str(REPO_ROOT / "src/regolith.universe/planetary/regolith_terrain_gen")
    )
    import dataclasses

    from regolith_terrain_gen.config import TerrainConfig
    from regolith_terrain_gen.generate import generate_world

    cfg = TerrainConfig(seed=seed)
    if cine_light:
        cfg = dataclasses.replace(cfg, sun_elevation_deg=25.0, scene_ambient=(0.12, 0.12, 0.13))
    world_sdf_path = generate_world(cfg, out_world_dir, start_paused=False)
    manifest = json.loads((out_world_dir / "manifest.json").read_text())
    spawn = manifest["spawn_zone"]
    spawn_xy = (spawn["x_m"], spawn["y_m"])
    ground = spawn["elevation_m"]

    resolved = []
    for name, spec in views:
        if spec is None:
            preset = _presets(spawn_xy, ground)
            if name not in preset:
                raise SystemExit(
                    f"unknown preset '{name}' - choose from {', '.join(sorted(preset))}"
                )
            eye, target, hfov = preset[name]
        else:
            eye, target, hfov = spec
        roll, pitch, yaw = _look_at_rpy(eye, target)
        resolved.append((name, (*eye, roll, pitch, yaw), hfov))

    extra = "".join(
        _rig_sdf(i, pose, width, height, hfov) for i, (_, pose, hfov) in enumerate(resolved)
    )
    if with_rover:
        extra += _bake_rover(world_sdf_path, out_world_dir, ground + 0.5) + "\n"
    world_sdf_path.write_text(
        world_sdf_path.read_text().replace("</world>", f"{extra}  </world>", 1)
    )
    return world_sdf_path, resolved, manifest


def _save_frames(topics, out_paths, timeout_s, settle_s):
    """Subscribe to each bridged image topic and write one PNG each."""
    import numpy as np
    from PIL import Image
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image as ImageMsg

    rclpy.init()
    node = Node("regolith_render_still")
    got = {}
    counts = {t: 0 for t in topics}
    # Skip the first few frames per camera: the first render of a scene routinely
    # lands before textures/shadows have finished loading, and a half-loaded frame
    # looks exactly like a material bug.
    skip = max(1, int(settle_s))

    def make_cb(topic):
        def cb(msg):
            counts[topic] += 1
            if counts[topic] <= skip or topic in got:
                return
            arr = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, -1)
            if msg.encoding in ("bgr8", "bgra8"):
                arr = arr[:, :, ::-1] if arr.shape[2] == 3 else arr[:, :, [2, 1, 0, 3]]
            got[topic] = Image.fromarray(arr[:, :, :3].copy(), mode="RGB")
        return cb

    for topic in topics:
        node.create_subscription(ImageMsg, topic, make_cb(topic), 1)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and len(got) < len(topics):
        rclpy.spin_once(node, timeout_sec=0.5)

    for topic, path in zip(topics, out_paths):
        if topic in got:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            got[topic].save(path)
    node.destroy_node()
    rclpy.shutdown()
    return {t: (t in got) for t in topics}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--preset", default="hero", help="comma-separated preset names, or 'all'")
    ap.add_argument(
        "--view",
        action="append",
        default=[],
        metavar="EX,EY,EZ:TX,TY,TZ:HFOV",
        help="explicit camera: eye : look-at target : horizontal fov (radians)",
    )
    ap.add_argument("-o", "--outdir", default=str(REPO_ROOT / "docs/media/dev"))
    ap.add_argument("--tag", default="", help="suffix for the output filenames, e.g. 'after'")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--no-rover", action="store_true")
    ap.add_argument("--cine-light", action="store_true", help="raise the sun to 25 deg, as media runs do")
    ap.add_argument("--settle", type=float, default=6.0, help="frames to discard per camera before saving")
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--keep-world", action="store_true", help="leave the generated world dir in place")
    args = ap.parse_args()

    views = []
    if args.preset:
        names = sorted(_presets((0, 0), 0).keys()) if args.preset == "all" else args.preset.split(",")
        views += [(n.strip(), None) for n in names if n.strip()]
    for raw in args.view:
        try:
            eye_s, target_s, fov_s = raw.split(":")
            eye = tuple(float(v) for v in eye_s.split(","))
            target = tuple(float(v) for v in target_s.split(","))
            views.append((f"view{len(views)}", (eye, target, float(fov_s))))
        except ValueError:
            raise SystemExit(f"could not parse --view '{raw}' (want EX,EY,EZ:TX,TY,TZ:HFOV)")
    if not views:
        raise SystemExit("nothing to render - pass --preset and/or --view")

    work = Path(tempfile.mkdtemp(prefix="regolith_render_"))
    world_dir = work / "world"
    print(f"[render] generating seed {args.seed} world in {world_dir}", flush=True)
    world_sdf, resolved, manifest = build_world(
        args.seed, views, args.width, args.height, not args.no_rover, args.cine_light, world_dir
    )

    # Private DDS domain, so a render never joins a live demo's graph - and a private
    # GZ_PARTITION as well, which is the half people forget: ROS_DOMAIN_ID isolates the
    # ROS graph only. gz-sim and gz-transport traffic live on gz's own partition, so two
    # concurrent renders (or a render alongside a live demo) would otherwise share one
    # partition under the same world name and cross-talk - a stray server can starve
    # /clock and stall every sim-time timer in the other run.
    env = dict(os.environ)
    env["ROS_DOMAIN_ID"] = str(random.randint(1, 101))
    env["GZ_PARTITION"] = f"regolith_render_{os.getpid()}_{random.randint(0, 1 << 20)}"
    topics = [f"/render/cam{i}" for i in range(len(resolved))]
    tag = f"_{args.tag}" if args.tag else ""
    out_paths = [
        str(Path(args.outdir) / f"seed{args.seed}_{name}{tag}.png") for name, _, _ in resolved
    ]

    procs = []
    try:
        print(f"[render] starting headless server: {world_sdf}", flush=True)
        procs.append(
            subprocess.Popen(
                ["ros2", "launch", "ros_gz_sim", "gz_sim.launch.py", f"gz_args:=-r -s {world_sdf}"],
                env=env, start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        )
        bridge_args = [f"{t}@sensor_msgs/msg/Image[gz.msgs.Image" for t in topics]
        procs.append(
            subprocess.Popen(
                ["ros2", "run", "ros_gz_bridge", "parameter_bridge", *bridge_args],
                env=env, start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        )
        os.environ["ROS_DOMAIN_ID"] = env["ROS_DOMAIN_ID"]
        print(f"[render] waiting for {len(topics)} frame(s) (timeout {args.timeout:.0f}s)", flush=True)
        results = _save_frames(topics, out_paths, args.timeout, args.settle)
    finally:
        for p in procs:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(2.0)
        for p in procs:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        if args.keep_world:
            print(f"[render] world kept at {world_dir}", flush=True)
        else:
            shutil.rmtree(work, ignore_errors=True)

    ok = 0
    for (name, _, _), topic, path in zip(resolved, topics, out_paths):
        if results.get(topic):
            ok += 1
            print(f"[render] {name:10s} -> {path}", flush=True)
        else:
            print(f"[render] {name:10s} -> NO FRAME (camera produced nothing)", flush=True)
    print(f"[render] {ok}/{len(resolved)} frames written", flush=True)
    return 0 if ok == len(resolved) else 1


if __name__ == "__main__":
    sys.exit(main())
