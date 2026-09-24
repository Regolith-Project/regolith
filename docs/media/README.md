# docs/media

Where each asset came from, and what it does and does not show. Everything here is a
recording of a real run - no asset is composed, re-timed to flatter the rover, or
captioned in a way the run does not support.

## Video

| file | size | length | what it is |
|---|---|---|---|
| `hero_chase.mp4` | 1280x720 | 29.1 s | Free-flying chase rig, **autonomous goal-seeking** (planner_node + pure_pursuit_node, not teleop), rover driving through a real boulder field - see "Cinematic camera rig" below for full provenance, RTF and driven-by details |
| `hero_orbit.mp4` | 1280x720 | 35.4 s | Free-flying orbit rig circling the rover close, **autonomous goal-seeking**, same drive as the chase clip - see "Cinematic camera rig" below |
| `m5_onboard_drive.mp4` | 1280x720 | 47.6 s | Onboard mast camera, autonomous drive past a boulder cluster |
| `m4_immobilisation_and_escape.mp4` | 1280x720 | ~20 s | Chase camera: the rover caught under a leaning boulder's overhang, and the escape that frees it |
| `m4_rviz_autonomous_run.mp4` | 1920x1080 | 13.9 s | RViz during a live autonomous run - robot model, TF, costmap, planned path advancing |
| `m5_demo_tour.mp4` | 640x480 | 80 s | The original M5 tour clip. Superseded by `m5_onboard_drive.mp4`; kept because PROGRESS.md M5 refers to it |
| `m5_demo_hero.gif` | 480x360 | 8 s | README hero excerpt of the above |

## Stills

| file | size | what it is |
|---|---|---|
| `m4_costmap_and_planned_path_2048.png` | 2048x2048 | Traversability costmap + planned path, nearest-neighbour upsampled so every cell is exactly the value the planner read |
| `m4_costmap_and_planned_path.png` | 256x256 | The original 1:1 grid dump. Kept: PROGRESS.md M4 cites it |
| `m0`-`m3`, `mission_flags`, `floating_rocks_*` | various | Milestone screenshots, see PROGRESS.md |

## Cinematic camera rig - mechanism verified, hero clips shot (chase, orbit)

Status as of this entry: the visual overhaul (rover body/wheels, terrain surface, sky/
Earth/far-field) is frozen and the box was made exclusive for the shoot (no other
gz-sim process running). Two hero clips are delivered below - `hero_chase.mp4` and
`hero_orbit.mp4` - both genuinely AUTONOMOUS (planner_node + pure_pursuit_node driving
against the live costmap, not teleop - see "How the rover was driven" below for why that
distinction matters and is stated for every clip). Crane and track are not yet shot
(droppable per the brief; chase and orbit carried the priority). What follows is the rig
mechanism verified for real, the hero clips with full provenance, and the throwaway dev
clips in `docs/media/dev/` that proved the chain before the hero shoot.

### The problem with the existing `cine_camera` (onboard/chase)

Both existing cine cameras (`regolith_rover.urdf.xacro`'s `cine_camera` arg) are rigidly
bolted to the chassis, so the horizon pitches and rolls with every bump and the framing
never changes - it reads as a bodycam, not cinematography. Fixing that needs a camera
that is NOT attached to the rover at all.

### Mechanism: gz-sim's `/world/<world>/set_pose` service, driven every tick

A new `cine_rig` launch arg (`none|chase|orbit|crane|track`, default `none`, opt-in)
adds a free-flying, camera-only `<static>true</static>` model (`cine_rig`, see
`hello_moon.launch.py`'s `_cine_rig_sdf`) with its own 1280x720 camera and
`CameraVideoRecorder` plugin on `rover/rig/record_video` - same pattern as the existing
cine cameras, just not attached to anything. `regolith_bringup/scripts/camera_rig_node.py`
moves it every tick by calling `gz service -s /world/<world>/set_pose`, the EXACT same
mechanism `flip_recovery_node.py` already uses in production to teleport a flipped rover
upright - reused rather than invented, and its own history in this repo is independent
evidence the mechanism is real and reliable on this gz-sim 8.14 (Harmonic) install.

This was verified three ways before anything was built on top of it, because it was the
piece most likely to be a silent no-op:

1. **ECM readback**: a `PosePublisher` plugin + ROS bridge on a throwaway test rig
   confirmed 15/15 requested teleports landed exactly on the requested pose.
2. **The rendered image, not just the pose**: three distinct coloured boxes were placed
   in a scene and a static camera-only model was teleported+re-aimed at each in turn -
   the three saved frames were visually inspected (not just pixel-diffed) and each shows
   a genuinely different, correctly-perspective viewpoint of the right box.
3. Confirmed working for both `<static>true</static>` and non-static (gravity-disabled)
   models - a plausible silent no-op either way, checked rather than assumed.

**Rate cost, measured**: a `gz service` CLI call (this is a subprocess call, like
`flip_recovery_node.py`'s, not the faster gz-transport Python bindings - chosen for the
same partition-safety reasons) costs ~300-330 ms wall-clock, almost all process startup.
At this world's measured 0.05-0.10x real-time factor, a 30 Hz SIMULATED control rate
(see "frame count, not container fps" just below for why 30, not 15) needs 1.5-3.0 real
calls per second - the 300 ms cost still fits, but with noticeably less margin than 15 Hz
had; a real capture measured 100 calls at an actual 2.57 Hz wall-clock rate with 0
failures, so it held up, but this is worth re-checking on a longer take rather than
assumed permanent.

### Lit, not silhouetted - computing the sun's bearing rather than guessing it

Early framing attempts put the rover backlit - a dark silhouette against its own shadow,
the same failure this project's own history already documents for the
`m4_immobilisation_and_escape.mp4` boulder shot ("check where the sun is before choosing
what to drive at"). Rather than trial-and-error rotating a camera or a rover, the sun's
true world bearing was computed directly from the generator's own math
(`regolith_terrain_gen/worldgen.py`'s `_sun_direction`: `dx = cos(elev)*cos(az)`,
`dy = cos(elev)*sin(az)`, with the world's `sun_azimuth_deg` at 235 and `sun_elevation_deg`
at 18 under `cine_light`) - the direction the LIGHT TRAVELS, so the sun itself sits at the
opposite bearing, `atan2(-dy, -dx) ~= 55 deg`. This matches the ~55 deg figure the
project's boulder-shot investigation found by hand.

This number drives every framing choice in the hero shoot: the chase/crane camera sits
behind the rover, so the rover's direction of travel needs to be roughly 235 deg
(bearing 55 + 180) for the camera - and the sun - to end up on the same side, lighting
the face the lens sees rather than its shadow. For the autonomous hero clips this means
choosing a GOAL roughly along bearing 235 from spawn (see "How the rover was driven"
below) rather than steering by hand. Verified, not assumed: a still render at the
computed geometry (`scripts/render_still.py --view`) confirmed the rover reads as lit
hardware - white deck panels, gold trim, dark wheels - well before any live capture was
attempted.

### Crane height and the far-field seam

A separate, documented residual from the visual overhaul: a thin seam between the near
terrain and the far-field horizon mesh, visible only from elevated cameras (empirically:
invisible below ~15 m above local terrain, a few-pixel sliver at ~15 m, a clear ~100 px
band by ~32 m - gradual, not a hard cutoff, and not proven azimuth-independent). The
crane shot's whole premise is rising to reveal the landscape, so it is the one shot type
that can fly into this. `camera_rig_node.py`'s crane parameters were set with both
constraints at once - `crane_end_up` capped at 10 m (comfortable margin under 15 m,
allowing for local terrain height variation away from spawn) and `crane_start_back`/
`crane_start_side`/`crane_end_back`/`crane_end_side` positioned along the ~55 deg sun
bearing above rather than the original pure-(-X) placement, so the reveal is lit as well
as seam-safe. Checked with two still renders at the exact computed end-of-crane eye
position (one aimed down at the rover, one aimed level toward the horizon - the harder
case for the seam) before this was ever queued for a live capture: clean horizon in both,
no visible seam band, rover materials correctly coloured. Not yet exercised in an actual
recording - see "Still rough" below.

### Frame count, not container fps - the mistake this caught

The first working take was captured with both the rig sensor and the control node at
15 Hz sim-time. It played back fine as a container (25 fps, 26 frames in a 1.04 s clip)
but a frame-by-frame check (`ffmpeg`'s `mpdecimate` filter, now wired into
`scripts/record_cine.py` as an automatic post-capture check - see `_distinct_frame_count`)
showed only **15 of those 26 frames were actually distinct renders** (57.7%, an
effective ~14.4 fps of real motion) - the rest were the same rendered frame repeated,
because the SENSOR only produced a new frame 15 times per simulated second while the
recorder/retiming pipeline was producing more container frames than that. Invisible from
a duration/frame-count check; very visible as stutter on a full-screen watch, which is
exactly the failure mode this footage exists to avoid.

**Fix**: raised both the rig camera sensor's `update_rate` (`_cine_rig_sdf` in
`hello_moon.launch.py`) and `camera_rig_node.py`'s own default `update_rate_hz` to 30 -
they must match, not just be close, or every other frame still repeats a stale pose.
Re-measured on a fresh capture: **24 of 26 frames distinct (92.3%, effective 23.1 fps)**
- a real, large improvement, not assumed. Still short of a clean 26/26 (some ticks fell
behind the ~330 ms call cost during faster-RTF moments in that capture), so this number,
not an assumption that "30 Hz means 30 fps," is what should gate the hero shoot.

**Smoothing**: chassis bumps and turns never reach the frame directly. The rover's
tracked position/heading, and separately the camera's own pursuit of its computed
target, each go through a closed-form critically-damped 2nd-order filter (Juckett's
"Damped Springs" formulation, exact for any `dt` - needed because this world's per-tick
`dt` is large and irregular, not the small fixed step a naive `lerp` assumes). Shot
library: `chase` (fixed standoff behind/above, smoothed), `orbit` (slow circle, angular
rate independent of framerate), `crane` (scripted low-close-to-high-far reveal, eased
with smoothstep), `track` (fixed lockoff, aim pans to follow the rover).

### A real, repeated environmental hazard found along the way: gz-sim segfaults/SIGKILLs under concurrent load

Across this work's test launches, gz-sim's server process died outright (`Segmentation
fault (core dumped)`, or `SIGKILL`/exit 137) in roughly half of all attempts, always
while at least one OTHER gz-sim instance (another agent's `render_still.py` run or its
own hello_moon test) was rendering concurrently on this box, and never during the fully
isolated lightweight probes used to verify the mechanism above. This is very likely
GPU/Ogre2 render-context contention between concurrent headless gz-sim processes, not a
bug in the rig - the project's own history already has one independent instance of this
exact failure mode (see "A render artefact..." section below / PROGRESS.md's M5 notes:
"One Ogre2/Sensors segfault... cost a complete 68 MB take"). **Practical consequence**:
this is exactly why segmented recording (mp4 moov atom written only on STOP) is not
optional here - `scripts/record_cine.py` always records in bounded segments and verifies
each one with `ffprobe` before trusting it, dropping (never silently shipping) any
segment whose file is unreadable.

**Also found and worth recording**: `hello_moon.launch.py` isolates `ROS_DOMAIN_ID` per
launch (see its `_allocate_domain_id`) but never sets `GZ_PARTITION`, so by default every
launch's gz-transport traffic - including `set_pose` calls and the recorder service -
rides the SAME default partition and can cross-talk with any other concurrent gz-sim
instance using the same world name (`regolith_moon`). One test session read back a world
`stats` message showing `sim_time` in the thousands of seconds from a *different*,
long-orphaned gz-sim process on the same partition before this was diagnosed. Not fixed
in the shared launch file here (out of this work's scope and risk to touch mid-flight
while other agents edit the same file); `scripts/record_cine.py` and the test wrapper
used for this work set `GZ_PARTITION` explicitly as a workaround. Worth fixing in
`hello_moon.launch.py` itself the same way `ROS_DOMAIN_ID` already is.

### Recording/assembly pipeline and honest re-timing

`scripts/record_cine.py` starts/stops the `CameraVideoRecorder` service in bounded
segments (default 150 s, matching the existing workflow), measures the REAL-TIME FACTOR
over each capture window from `/world/<world>/stats` (`sim_time` delta / wall-clock
delta - not assumed, not a constant), and re-times each valid segment with
`ffmpeg setpts=<measured RTF>*PTS` so one second of finished clip is one simulated
second - a correction to true speed, never an exaggeration of it, same convention as the
existing clips below. A segment whose stats read-back fails is left at 1x and flagged
rather than guessed. Multiple segments are concatenated after re-timing.

### How the rover was driven, and why it matters for every clip below

**Every clip's provenance states plainly whether the rover was under autonomous
goal-seeking, a scripted tour mission, or direct teleoperation** - never left implicit,
because this project's claim is autonomous navigation, and footage of a hand-driven
chassis does not support that claim no matter how well it is lit or framed.

The hero clips (`hero_chase.mp4`, `hero_orbit.mp4`) are **autonomous goal-seeking**:
`regolith_planner`'s `planner_node` and `regolith_vehicle_interface`'s `pure_pursuit_node`
do the actual planning and driving, exactly as they do in every acceptance run. The only
thing chosen by hand is WHERE to send the goal - picked for lighting (a bearing from
spawn roughly opposite the sun, so a rig trailing the rover sits near the sun and the
vehicle is front-lit rather than a silhouette - see the sun-bearing section above), not
for a route. That goal is never just picked and hoped for: a throwaway script
(`send_goal.py` in this work's scratch directory) validates each candidate against the
SAME live `/costmap` and the same `regolith_planner.astar.plan_path` A* the planner node
itself runs before publishing anything - the identical reachability check
`regolith_planner/tour.py` already uses to build the `mission:=tour` waypoints, not a
separate approximation of it. `planner_node` and `pure_pursuit_node` then do the only
work that would happen in a real run.

An earlier chase take used direct `/cmd_vel` teleop with a hand-turned starting heading
to get the same lighting. It was rejected for the hero slot on exactly this reasoning and
is kept only as labelled B-roll - see `broll_chase_teleop.mp4` below.

### Hero clips

Shipped at `docs/media/hero_chase.mp4` / `docs/media/hero_orbit.mp4` (also listed in the
Video table at the top of this file). The un-retimed raw segment and the full
`.provenance.json` for each live in `docs/media/dev/` alongside the same filename, kept
as supporting detail rather than duplicated at the top level.

Seed 42 (the canonical demo seed), `cine_light:=true`, 30 Hz rig sensor matched to the
control node's tick rate, multi-segment capture (150 s per segment - the mp4 moov atom
is written only on STOP, so a crash or a dropped `gz service` call costs at most one
segment, never the whole take), each segment's real-time factor measured independently
from `/world/regolith_moon/stats` and used to re-time that segment
(`setpts=<measured RTF>*PTS`) so one second of finished clip is one simulated second.
Distinct-frame count (not container frame count - see "frame count, not container fps"
above) checked on every clip with `scripts/record_cine.py`'s `mpdecimate`-based check.

| file | driven by | requested / actual | segments | RTF range measured | retimed length | distinct frames |
|---|---|---|---|---|---|---|
| `hero_chase.mp4` | **autonomous goal-seeking** - goal at (-14.34, -20.48), 25 m along bearing 235 deg, A*-validated, 28-cell path | 550 s requested, 3 of 4 segments captured (see below) | 3 | 0.0678-0.0718 | 29.08 s | 652/727 (89.7%, ~22.4 fps effective) |
| `hero_orbit.mp4` | **autonomous goal-seeking** - same goal as chase (rover drives the same route; the camera does the orbiting) | 550 s requested, 4 of 4 segments captured | 4 | 0.0437-0.0717 | 35.36 s | 873/884 (98.8%, ~24.7 fps effective) |

**`hero_chase.mp4` is 3 segments, not 4 - said plainly rather than shipped quietly.**
The 4th segment's `CameraVideoRecorder` `start` service call timed out (a transient gz
service hiccup, not a crash - gz-sim was confirmed still alive and healthy afterward, and
the launch tore down cleanly). `record_cine.py`'s segment handling did exactly its job:
it dropped the one bad segment and kept the three good ones rather than losing or
corrupting the whole take. Net effect: ~29 s of finished clip instead of the ~37 s the
full 4 segments would have given - a real, stated shortfall, not a defect worth
reshooting for (the coordinator's call: reshoot for defects - stutter, black rover, a
seam, a broken segment file - not for a clip that came out a bit shorter than planned).

**What `hero_chase.mp4` shows**: the rover driving autonomously through a real boulder
field toward its goal, well-lit (sun-side framing working as designed - white ribbed
deck, gold band, dark grousered wheels, a crisp long cast shadow), the ground's fine
ripple texture and sunlit boulders with their own dark cast shadows all reading clearly.
Confirmed NOT a repeat of the urdf2sdf black-tint bug (checked in a live frame pulled
from the rig's own topic before any recording started, and again in the finished clip).

**What `hero_orbit.mp4` shows, and the reshoot that got it there**: the first orbit take
(radius 9 m, height 4 m, the rig's shared 1.3 rad hfov) was technically clean - 4/4
segments, 815/942 distinct frames - but put the rover at roughly 3% of frame width, a
speck lost in the landscape. As a hero beauty shot its only job is showing the vehicle,
so it failed despite being a valid capture; this is the one case in this work where
re-shooting for composition (not a defect) was the right call. Fix: the orbit shot now
gets its own narrower camera hfov (0.7 rad vs the shared 1.3 - see `_cine_rig_sdf` in
`hello_moon.launch.py`) AND a tightened orbit radius/height (4 m / 2 m, down from 9 m /
4 m - see `camera_rig_node.py`'s `orbit_radius`/`orbit_height` defaults), checked with a
still render at the exact new geometry before committing a long take (rover measured at
~19% of frame width in that still, matching the reshoot's actual frames). The reshoot
puts the rover at roughly 20-25% of frame width through the sweep - the clear subject of
the shot, landscape as context rather than the reverse - with visible orbital motion
across the ~35 s capture (the camera visibly circles the vehicle between the sampled
frames, not just a fixed three-quarter view).

**Real distinct-frame numbers, not rounded to "30 Hz"**, per the standing instruction:
`hero_chase.mp4` is 652/727 frames distinct (10.3% duplicates, ~22.4 fps effective) -
just above `record_cine.py`'s 10%-duplicate warning threshold, from the ~330 ms `gz
service` CLI call occasionally falling behind the 30 Hz tick target during faster-RTF
moments (see the rate-cost note above). `hero_orbit.mp4`'s reshoot came out tighter:
873/884 distinct (1.2% duplicates, ~24.7 fps effective), comfortably under the
threshold - likely the narrower hfov and reduced radius mean less scene detail to
render per frame, leaving the control loop more headroom to keep up. Neither is a clean
30/30 fps, but at 22-25 fps effective both read as smooth motion on inspection.

### `broll_chase_teleop.mp4` - labelled B-roll, not a hero clip

**Driven by: teleoperation** - direct `/cmd_vel`, turned in place to a staged starting
heading (235 deg, for the same sun-bearing lighting reasoning as the autonomous chase
goal) then driven straight, via a throwaway heading-aware driver script. This is the
take that was running BEFORE the plan changed to autonomous goal-seeking; let it finish
rather than killed (a segfault or a wasted capture window would have cost more than
letting it complete), then demoted rather than shipped as the hero chase clip. Same
lighting design, same 30 Hz/multi-segment/re-timing pipeline, same honesty convention
the existing `m4_immobilisation_and_escape.mp4` uses for a staged heading - but a
chassis under hand-published velocity commands is not evidence of the autonomy stack
working, so it does not belong in the hero slot. 40.48 s retimed, 4/4 segments
(RTF 0.0710-0.0740), 862/1012 distinct frames (85.2%, ~21.3 fps effective). Kept as
rig-validation B-roll only.

### The dev clips in `docs/media/dev/`

All throwaway smoke tests proving the chain (rig moves -> records -> valid mp4 ->
honestly re-timed), NOT hero footage - seed 42, `cine_light:=true`, ~10-15 s wall-clock
captures, `/cmd_vel` driven directly rather than through a full autonomous mission (to
get something moving on camera without waiting on the planner). Provenance for each is
its `.provenance.json` sibling; the un-retimed source is kept alongside as `*_raw.mp4`.

| file | rig rate | RTF measured (720p rig camera attached) | retimed length | distinct frames | what it shows |
|---|---|---|---|---|---|
| `pipeline_chase30.mp4` | 30 Hz (current) | 0.061 (sim 0.98 s / wall 15.3 s) | 1.04 s | **24/26 (92.3%, ~23.1 fps)** | Chase shot at the fixed rate - see "frame count" above. The framing itself: rig behind and above, whole rover in frame, boulders raking long shadows across the ground - reads as a documentary shot, not a screen capture. |
| `pipeline_chase.mp4` | 15 Hz (superseded) | 0.093 (sim 1.02 s / wall 10.3 s) | 1.04 s | 15/26 (57.7%, ~14.4 fps) | Kept as the before-case for the frame-count fix above - visibly stuttery, do not use for anything but that comparison. |
| `pipeline_orbit.mp4` | 15 Hz (not yet redone at 30) | 0.078 (sim 0.78 s / wall 10.2 s) | 0.88 s | not re-checked | Orbit shot: radius and height land exactly on their configured values (verified by construction). Too short in sim-time (~4.7 degrees of arc) to visibly show the orbit motion, AND still at the superseded 15 Hz rate - needs redoing at 30 Hz with a longer capture before it means anything as footage. |

An earlier chase capture in the same session measured RTF=0.057 (sim 0.61 s / wall
10.7 s) - every RTF figure above is a genuine measurement from its own capture window,
not one number repeated; the spread (0.057-0.093) across otherwise similar short takes
is consistent with the concurrent-load contention noted above and is itself useful
context for sizing segments.

**These are render-side RTF numbers, WITH the 720p `cine_rig` camera attached** (on top
of the rover's own always-on RGB+depth pair) - not the headless, no-sensors RTF that
acceptance runs are measured against. They should not be confused with each other:
physics-only headless RTF (measured elsewhere, before/after the visual overhaul, terrain
mesh 2.8 MB -> 50.5 MB) showed no confirmed slowdown, but that number says nothing about
the cost of actually filming, which is what these figures are.

### Still rough / not done

- **Crane and track hero shots are implemented (`camera_rig_node.py`'s `shot_crane` /
  `shot_track`) but not yet filmed** - chase and orbit carried the stated priority
  (they "carry most of the weight": chase shows the vehicle working in its environment,
  orbit is the beauty shot); crane and track are explicitly droppable if time runs out,
  and time ran out before them this pass. The crane's lit, seam-safe geometry (10 m end
  height, sun-bearing-aligned start/end positions - see `camera_rig_node.py`'s
  `crane_start_side`/`crane_end_*` parameters) was computed and verified with still
  renders (see "Crane height and the far-field seam" above) but never exercised in a
  live capture.
- **`pipeline_chase.mp4`/`pipeline_chase30.mp4`/`pipeline_orbit.mp4` in `docs/media/dev/`
  are superseded by the hero clips above** - kept only as the dated record of the
  frame-rate fix (15 Hz -> 30 Hz) and the original pipeline proof, not as current
  reference footage.
- The gz-sim segfault/SIGKILL and transient-service-timeout hazards above are
  unresolved - real risk for any long recording session on this box, mitigated but not
  eliminated by segmenting (see `hero_chase.mp4`'s dropped 4th segment for a live
  instance: a `gz service` timeout, not a crash, cost one segment out of four).
- `hello_moon.launch.py`'s missing `GZ_PARTITION` isolation (above) is flagged, not
  fixed in the shared launch file - the coordinator has taken this one directly.

## How the three new clips were recorded

All three come from `hello_moon.launch.py` with two media-only launch arguments added
for this purpose (documented in `regolith_bringup`'s README):

- `cine_camera:=onboard|chase|both` adds a **separate** 1280x720 camera whose only job
  is filming. The navigation cameras are not moved: their pose and intrinsics are what
  the costmap, VO and every M3/M4 number depend on, so framing requirements are met with
  a new sensor rather than by disturbing the measured one.
- `cine_light:=true` raises the sun and lifts the scene ambient off the floor. This is
  render-only - the heightmap, rocks, collision boxes and costmap are all generated
  before the light is written - so a clip recorded with it is driving the same world as
  a normal run. It exists because the shipped lighting, which is what a low lunar sun
  actually looks like and what every measurement here was taken under, renders most of
  the surface as unreadable shadow on video.
  **Values changed since the clips below were recorded**: `m5_onboard_drive.mp4` /
  `m4_immobilisation_and_escape.mp4` / `m4_rviz_autonomous_run.mp4` were shot at the
  original `cine_light` (sun 12 -> 25 deg, ambient 0.06 -> 0.12), which - discovered
  while adding the sky/Earth/far-field pass below - blew real lunar regolith's ~0.08-0.14
  albedo out to near-white. `cine_light` is now sun 12 -> 18 deg, ambient 0.06 -> 0.07;
  the shipped clips are unaffected (already-recorded video, not regenerated) but a new
  capture with the same flag will read as visibly darker/more contrasty than these.

Recording goes through gz-sim's server-side `CameraVideoRecorder`, in ~150 s segments.
Segments are not cosmetic: the recorder writes the mp4 moov atom on STOP, so a server
crash mid-recording leaves a large file with no header and nothing recoverable. One
Ogre2/Sensors segfault during this work cost a complete 68 MB take that way.

### Playback speed

The recorder writes frames as they render, and this world runs at 0.05-0.10x real time
with a 720p camera attached, so raw footage shows the rover crawling.

- `m5_onboard_drive.mp4` and `m4_rviz_autonomous_run.mp4` are **re-timed to sim-time
  speed** (`setpts` by the real-time factor measured over each capture window: 0.0717
  and 0.0792 respectively). One second of clip is one simulated second. That is a
  correction to true speed, not an exaggeration of it.
- `m4_immobilisation_and_escape.mp4` is **unmodified 1x recorder output**, deliberately.
  The measured RTF disagreed with how long the escape visibly took on film, so rather
  than impose a speed factor that might misrepresent the event, the clip ships raw and
  can be re-timed downstream.

No clip has a burned-in caption.

## What `m4_immobilisation_and_escape.mp4` shows, exactly

The rover is driven at seed 42's 2.24 m boulder at `(-18.90, -9.99)` until it is
immobilised. **The heading was staged; the immobilisation and the escape are the
system's own** - `flip_recovery_node` detected it from its own signals and ran its own
maneuver:

```
STUCK RECOVERY #2 (escalation level 1, triggered by ground truth)
  reversed 0.20 m/s for 6.0 s, then turned right at 0.50 rad/s for 3.5 s
STUCK RECOVERY #2 result: ground truth moved 1.19 m during the maneuver - FREED
```

Both escapes in this run freed the rover (2/2). The capture harness releases `/cmd_vel`
as soon as the recovery starts (see point 2 below); the earliest takes needed multiple
attempts only because the harness was fighting the maneuver.

### The mechanism, because it is not what it looks like

The boulder is tilted (`pitch_rad 0.246`) and **leans out over the ground**. The rover
drives under the overhang until the **top front-left corner of its chassis** jams
against the rock's underside - `ahead 0.29 m, lateral -0.23 m, z 0.265 m` on the rover,
the only point of its whole front face that intersects the rock's collision ellipsoid in
3-D. All four wheels stay on flat, open ground and keep turning. That is exactly what
the onboard detector reports: *"the wheels claim 1.84 m and 0.55 rad of turning; the
gyro saw 0.08 rad (14% of it)"*.

Two things it is **not**, both checked rather than assumed:

- not a terrain step - all 1764 collision boxes were reconstructed from the world and
  the collision surface tracks the visual mesh to within +/-10 mm along the rover's
  path, with 2 mm per-step changes;
- not contact at the wheels - at wheel height the rock's collision surface is 0.24 m
  away.

### Why this took three takes, which is the useful part

**Take 1** put the `chase` boom at `1.6 m back, pitch 0.5, hfov 1.05`. That placed the
boulder's top **7.6 degrees above the frame's top edge**: only its dark underside was in
shot. The first person to watch it said the rover looked "immobilised on a shadow",
which was the correct reading of what was on screen.

**Take 2** fixed the framing - boom to `2.6 m back, 1.1 m up, pitch 0.24, hfov 1.3`, so
the whole boulder is in frame - and it was still wrong, for a different reason. The
viewer said the same thing again. Framing was never the whole cause:

    sunlight arrives from bearing 55 deg   (from the world's own <direction> tag)
    the rover approached that rock from bearing 205 deg
    -> 150 deg apart, cos = -0.87: the camera was looking at the rock's SHADOWED side

An unlit boulder renders as a flat black silhouette, and it sits directly against its
own cast shadow, so rock and shadow merge into one dark mass. No amount of framing fixes
that - the object has to be **lit**.

**Take 3** (this clip) picks a boulder the rover can reach in a straight line from spawn
whose camera-facing side is sunlit: `(-18.90, -9.99)`, scale 2.24 m, its near face 27 deg
off the sun (`cos +0.89`), with 3.4 m of clearance past every other rock on the way. The
sun is now behind the camera, the boulder is an obviously solid lit object, and its cast
shadow falls away to the left instead of toward the lens.

The general rule, since it will apply to any future shot here: **check where the sun is
before choosing what to drive at.** The world writes its own light vector into
`world.sdf`; the face the chase camera sees is the one pointing back along the rover's
approach.

### Still worth knowing before captioning

1. **It is a staged wedge, not a natural one.** ~40 minutes of autonomous tour driving
   on seed 7, plus a full 23 m autonomous run on seed 42, produced no immobilisation at
   all. They are real but sparse; waiting for one on camera was not converging, so the
   rover was aimed at a boulder instead.
2. **The harness must let go of the wheels.** Holding a forward `/cmd_vel` through the
   escape leaves this script's commands interleaved with the maneuver's reverse commands
   at the DiffDrive plugin - the rover is pushed back under the overhang it is reversing
   out of. Measured: three escalating escapes moved it 0.01, 0.01 and 0.03 m, "STILL
   WEDGED" every time. That is the harness, not the recovery. `pure_pursuit_node` does
   the right thing autonomously ("Recovery node has taken over /cmd_vel - pausing path
   following"); the capture script now releases `/cmd_vel` the moment a reverse command
   from the recovery appears on the topic.
3. **Ships at unmodified 1x.** The measured real-time factor disagreed with how long the
   escape visibly took on film, so rather than impose a speed factor that might
   misrepresent the event, the clip is raw recorder output and can be re-timed
   downstream.

## Two things the costmap image does not show

- **Boulders have no graded inflation halo.** They are flat lethal cells; the rover
  radius is already folded into the lethal footprint. The ring structures visible in the
  map are **crater rims** - graded slope cost - and those are what a highlight pass over
  "rings" would be highlighting.
- The grid is 256x256 at 0.78 m/cell and has no more detail than that. The 2048 px
  export is a nearest-neighbour upsample: every cell stays a hard-edged square of
  exactly the value the planner read, just large enough to annotate.

## A caveat that applies to any "immobilisations" figure

`flip_recovery_node`'s `commanded_speed` includes `|ang_z| * half_track` while its
`gt_speed` measures translation only. A rover pivoting in place to face a new leg
therefore produces the signature `commanded=0.0690, gt_speed~0` and fires an escape
after 3 s of sim time without ever having been stuck. This asymmetry is deliberate and a
symmetric fix was measured and rejected (PROGRESS.md - it would break detection of the
real wedges), but it means a raw count of fired escapes is not a count of
immobilisations. The clip here was selected by requiring `commanded=0.3000` against
`gt_speed=0.0014` - commanded forward, not translating - which is a genuine wedge.

## A render artefact present in all Gazebo footage

A soft vertical band, roughly the width of the near field, sweeps with the camera. It is
a shadow-cascade boundary in the Ogre2 render path and is **not** caused by
`cine_light`: it is visible in the original `m5_demo_tour.mp4` too.

## Sky, Earth, and the far-field horizon ("the world beyond the world")

Three purely visual additions, all generated by `regolith_terrain_gen` alongside the
terrain and none of them read by the costmap or planner (no collision geometry, none of
it written to `manifest.json` - see `sky.py`/`earth.py`/`farfield.py` and
`test_farfield_and_sky_visual_only.py` in that package):

- **Sky**: a large (`sky_radius_m`, default 4800 m) custom mesh sphere carrying a
  procedurally generated starfield + Milky Way band (magnitude-distributed stars, a few
  bright and many faint, with small per-star colour variation, plus a size/brightness
  spread on the brightest few so they don't all read as identical dots). Its texture is
  applied through the PBR `emissive_map` channel with `ambient`/`diffuse` zeroed, not
  `lighting=false` - that combination renders as flat white on this gz-rendering/Ogre2
  build regardless of the texture, a real bug root-caused and documented in
  `sky.py`/`sky_model_sdf`'s docstrings; emissive is unaffected by scene light either
  way, so the practical effect (a sky that looks the same regardless of sun position) is
  the same. Regenerated fresh per seed on its own independent rng stream.
- **Earth**: an ordinary *lit* sphere textured with real NASA imagery (see below),
  placed at a fixed sky position (does not rise or set - correct behaviour for a
  tidally-locked Moon). Its day/night phase comes from the scene's own directional sun
  light, not a baked texture, so it always matches `sun_elevation_deg`/`sun_azimuth_deg`.
  Its default position (azimuth 200 deg) is nowhere near the `hero`/`horizon`/`orbit`/
  `terrain` presets' own ~13-80 deg forward azimuth - deliberately: with the shipped sun
  at azimuth 235 deg, any Earth position within the presets' forward view shows Earth's
  night side at every elevation (checked algebraically - see config.py's `earth_azimuth_deg`
  comment). Use the `earthlight` preset (`scripts/render_still.py --preset earthlight`) to
  see it - a continent-and-ocean-visible gibbous Earth with a clear terminator, confirmed
  on seeds 42 and 7.
- **Far-field horizon**: a visual-only mesh extending the ground from the 200 m physics
  edge out to `farfield_outer_radius_m` (default 3000 m half-width), built from the same
  kind of fBm noise as the near terrain, height-matched exactly to the actual drawn
  terrain surface at the boundary (see `test_farfield_boundary_matches_physics_terrain`)
  and silhouette-floored so it cannot dip below its own recent local peak by more than a
  small, distance-scaled amount (see `test_farfield_silhouette_has_no_sky_gap_from_elevated_camera`
  - the fix for a real "black band of stars between the near terrain and the far field"
  defect, visible only from elevated cameras). Material is a flat, near-terrain-toned
  grey (`diffuse 0.42 0.40 0.38`) rather than a reused texture: an earlier pass tiled the
  near terrain's own albedo/normal maps across the far field, which read as a
  high-contrast, marbled "crumpled foil" once actually seen at that scale (fine detail
  authored for close-range viewing aliases badly when minified over a multi-km horizon).
  Real per-vertex shading off the hill/crater-rim geometry, not a texture, is what gives
  the far field its "broad tonal variation and crater-scale structure" now.

### Earth texture: source and licence

`src/regolith.universe/planetary/regolith_terrain_gen/regolith_terrain_gen/assets/earth_albedo.png`
is a downsampled (1024x512, from the original 5400x2700) copy of NASA's **Blue Marble
Next Generation**, December 2004 composite:

- Source: NASA Earth Observatory / Visible Earth, image record 73909
  (`https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73909/world.topo.bathy.200412.3x5400x2700.jpg`)
- Credit: Reto Stöckli, NASA Earth Observatory, using data from the NASA/NOAA/DoD Suomi
  National Polar-orbiting Partnership / and MODIS instrument teams.
- Licence: NASA imagery is not copyrighted and is released as public domain under NASA's
  media usage guidelines (https://www.nasa.gov/nasa-brand-center/images-and-media/); no
  attribution is legally required, but it is credited here anyway as good practice.
- Modified: Lanczos-downsampled to 1024x512 and re-encoded as PNG rather than the JPEG
  NASA ships, purely as a precaution (every other texture in this codebase is a PNG) -
  not something that turned out to matter: an early render with the default `earth_azimuth_deg`
  showed Earth as a flat black disc, which looked like a texture-loading failure but
  measured out to be correct physics for a badly-chosen position (that azimuth put Earth
  almost exactly opposite the sun as seen from the camera - a "new" phase, genuinely dark
  side facing the viewer at every elevation). Fixed by moving `earth_azimuth_deg`, not by
  the JPEG/PNG swap. No colour grading or cropping either way.

Earth's night side is not a separate "city lights" texture - it relies entirely on real
lighting (near-black `scene_ambient` by default, brighter under `cine_light`), which is
what keeps it genuinely dark rather than an unlit flat disc.
