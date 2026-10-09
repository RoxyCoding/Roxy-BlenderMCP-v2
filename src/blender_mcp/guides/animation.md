---
title: Animation
summary: Keyframing from Python across Blender versions, posing rigs, easing, walk cycles, shape keys, paths, cameras, NLA, baking for export, and checking motion with frame strips.
---

# Animation

## Keyframes

Keyframe properties directly; it works in every version and needs no context:

```python
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, 120
scene.render.fps = 24

obj.location = (0, 0, 0); obj.keyframe_insert("location", frame=1)
obj.location = (0, 0, 2); obj.keyframe_insert("location", frame=24)
obj.rotation_euler.z = 3.1416; obj.keyframe_insert("rotation_euler", index=2, frame=48)
```

Pose bones: key the rotation channel the bone already uses; don't change `rotation_mode` on an
existing rig (Rigify controls are quaternions, and one bone in another mode breaks blending and
constraints). Bone keys use pose-space values, not world space.

```python
pb = rig.pose.bones["hand_ik.L"]
if pb.rotation_mode == "QUATERNION":
    pb.rotation_quaternion = Euler((0, 0, 0.5)).to_quaternion()   # from mathutils import Euler
    pb.keyframe_insert("rotation_quaternion", frame=f)
else:
    pb.rotation_euler.z = 0.5
    pb.keyframe_insert("rotation_euler", frame=f)
pb.keyframe_insert("location", frame=f)
```

On Rigify rigs animate the controls (`*_ik`, `*_fk`, `torso`, `root`), never `DEF-` or `ORG-` bones.

## Reaching fcurves

Blender 4.4 added slotted actions and 5.0 removed `Action.fcurves`. Use:

```python
def fcurves(obj):
    ad = obj.animation_data
    if not ad or not ad.action:
        return []
    if hasattr(ad, "action_slot"):
        from bpy_extras import anim_utils
        cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
        return list(cb.fcurves) if cb else []
    return list(ad.action.fcurves)
```

Then set easing per key: `kp.interpolation = "BEZIER"` with `kp.easing`, or `"LINEAR"` for
mechanical motion, `"CONSTANT"` for stepped/blocking.

## Making it feel alive

- Timing and spacing matter more than poses. Ease in and out of holds; keep linear for constant
  motion (wheels, conveyors).
- Anticipation before big moves, overshoot and settle after them, follow-through on
  secondary parts (antennae, tails, cloth) offset by 2–4 frames.
- Arcs: limbs and thrown objects travel on curves, not straight lines.
- Loops: make the first and last key identical and add a Cycles modifier
  (`fc.modifiers.new("CYCLES")`), or set the frame range to exclude the duplicate last frame.
- Procedural motion: drivers (`obj.driver_add("rotation_euler", 2).driver.expression = "frame * 0.1"`)
  or noise modifiers on fcurves. Safe mode may block drivers; keyframes always work.

## Walk and run cycles

- A walk cycle has four key poses per step: contact (heel down, legs apart), down (weight on the
  front leg, body lowest), passing (free leg passes the standing one, body rising), up (body
  highest). The second step mirrors the first.
- Timing at 24 fps: a normal walk is about 12 frames per step (24 per cycle), a run 8 or fewer,
  with both feet off the ground at some point in a run.
- Stride: about 0.7 m for an adult walk. If the character moves forward while cycling, move the
  root (or the whole rig) by exactly one stride per step, or feet slide; check it in a side view.
- Arms swing opposite the legs; hips and shoulders twist against each other.

## Shape keys, paths and cameras

- Shape keys (faces, corrective shapes) animate through their value:
  `kb = obj.data.shape_keys.key_blocks["Smile"]; kb.value = 1.0; kb.keyframe_insert("value", frame=f)`.
- Moving along a path: a Follow Path constraint (`"FOLLOW_PATH"`, `target` = the curve,
  `use_curve_follow = True` to face along it, `use_fixed_location = True` and key `offset_factor`
  from 0 to 1). Good for vehicles, flying cameras and conveyors.
- Camera shake: a Noise modifier on the camera's rotation fcurves (`fc.modifiers.new("NOISE")`,
  small `strength`, `scale` 10-30 frames) after keying the main move. Keep handheld shake subtle.

- Push finished actions to NLA strips (`track = ad.nla_tracks.new(); track.strips.new(name, start, action)`)
  to layer or sequence clips (walk, then wave).
- Name actions `Character_Walk`, `Door_Open`; game engines import them by name.
- Doors, lids and drawers: key the moving part's rotation or location about the origin `build`
  put on its hinge, within its plan range, and run `model_plan(action="verify")` - it moves the
  part through the range and reports anything it would cut through (`get_guide("modeling")`,
  Parts that move).
- Cameras: animate the camera or a parent empty; use a Track To constraint on a target empty for
  smooth follow shots. Keep focal-length changes slow.

## Baking and exporting

Constraints, IK and drivers only exist in Blender. Before exporting animation to a game engine or
another app, bake the result to plain keys on the deform bones, on a copy of the action:

```python
bpy.context.view_layer.objects.active = rig; rig.select_set(True)
bpy.ops.object.mode_set(mode="POSE")
bpy.ops.pose.select_all(action="SELECT")
bpy.ops.nla.bake(frame_start=scene.frame_start, frame_end=scene.frame_end, only_selected=True,
                 visual_keying=True, clear_constraints=False, use_current_action=False,
                 bake_types={"POSE"})
bpy.ops.object.mode_set(mode="OBJECT")
```

Export with FBX `bake_anim=True` (`bake_anim_use_all_actions=False` to export only the active
action, `bake_anim_use_nla_strips=True` to export each NLA strip as its own clip), or glTF, which
exports actions as animations. See `get_guide("rigging")` for the skeleton side of the export,
and `get_guide("unreal-engine")` for Unreal Engine 5, the default engine (frame rate, root
motion, importing onto an existing skeleton).

## Checking motion

A single screenshot can't show motion. Use `look(mode="frames")` to see a strip of evenly spaced
frames (or pass `frames=[...]` for specific ones, `view="camera"` to see them through the camera).
Check for popping, interpenetration, feet sliding on the ground, and the loop seam.
