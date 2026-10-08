---
title: Rigging
summary: Armatures from Python, Rigify for humans and animals, bone roll, IK, constraints and drivers, symmetry, skinning and weight cleanup, corrective shapes, checking deformation, and exporting rigs to game engines.
---

# Rigging

Rigging changes are hard to undo (applied transforms, parenting, weights): `checkpoint(action="save")`
before preparing the mesh, before skinning, and once the rig deforms well.

## Before rigging

- For a new character, use real size, applied scale and rotation, and a -Y-facing rest pose to
  match the chosen metarig. Origin and facing are workflow conventions, not automatic-weight
  requirements. Do not apply transforms to an existing animated or bound rig without testing a copy.
- Inspect duplicate vertices, loose geometry, disconnected islands and interior faces before
  cleanup. Merge only unintended duplicates (`bmesh.ops.remove_doubles`, with a size-appropriate
  distance); preserve intentional separate parts, UV seams and details. Islands alone are not a
  reason to delete geometry or remesh the original.
- Characters rig best in A-pose or T-pose with a bit of bend at elbows and knees.

Inspect models from a library for arbitrary scale and facing, triangulation,
islands and inner faces. Prepare only what needs fixing. If automatic weights fail, preserve the
textured original and try a voxel-remeshed copy for weight transfer (see Skinning). A library character in a relaxed pose
with arms down still rigs, but the shoulders deform worse than from an A-pose.

## Humans and animals: Rigify

Rigify ships with Blender and has metarigs for humans and animals (quadruped, cat, horse, wolf,
bird, shark...). The set differs between versions, so list them instead of guessing a name:

```python
import addon_utils
# Enable Rigify and create its entry in the add-on preferences.
addon_utils.enable("rigify", default_set=True)
print([op for op in dir(bpy.ops.object) if op.endswith("_metarig_add")])

# Adding one needs a 3D viewport in context.
win = bpy.context.window_manager.windows[0]
area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=win, area=area, region=region):
    bpy.ops.object.armature_human_metarig_add()   # or e.g. armature_basic_quadruped_metarig_add
metarig = bpy.context.active_object
```

Pick the metarig whose body plan matches (a dog is a quadruped, not a human on all fours); for
creatures no metarig fits, build bones by hand (next section).

1. Scale and move the metarig to fit the mesh (edit bones: `metarig.data.edit_bones["spine"].head`),
   aligning joints with the mesh's joints. Check against the mesh with `look(mode="angles", shading="xray", views=["front","right"])`.
2. Generate with the metarig active, and take the rig from the metarig rather than by name:
   ```python
   bpy.ops.pose.rigify_generate()
   rig = metarig.data.rigify_target_rig   # also the rig a later regenerate updates in place
   ```
   Generation also adds `WGT-` widget objects (control shapes) in their own collection; leave them.
3. Skin to the generated rig, not the metarig. Its deform bones are the `DEF-` ones; the rest are
   controls (`*_fk`, `*_ik`, `*_tweak`) and helpers (`ORG-`, `MCH-`). Animate the controls.

## Building bones by hand

```python
arm_data = bpy.data.armatures.new("Rig"); rig = bpy.data.objects.new("Rig", arm_data)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_data.edit_bones
root = eb.new("root"); root.head = (0, 0, 0); root.tail = (0, 0.3, 0); root.use_deform = False
up = eb.new("upper_arm.L"); up.head = (0.2, 0, 1.4); up.tail = (0.5, 0.05, 1.4); up.parent = root
lo = eb.new("forearm.L"); lo.head = up.tail; lo.tail = (0.8, 0, 1.4)
lo.parent = up; lo.use_connect = True
bpy.ops.object.mode_set(mode="OBJECT")
```

- **Deform or not.** Every new bone deforms by default, and automatic weights give each deforming
  bone a vertex group. Set `use_deform = False` on roots, IK targets, poles and other controls, or
  they pull on the mesh.
- **Roll.** A bone's roll sets which way its local X and Z point, so it decides which axis bends a
  joint. Uncontrolled roll is the usual cause of elbows bending sideways and mirrored poses not
  matching. Set it for a whole chain, with the chain's bones selected in edit mode:
  `bpy.ops.armature.calculate_roll(type="GLOBAL_POS_Z")` (options include `GLOBAL_POS_X/Y/Z`, local
  tangents and `ACTIVE`; print `bpy.ops.armature.calculate_roll.get_rna_type().properties["type"].enum_items`).
  Make limbs bend around the same local axis on every joint, and check with
  `look(shading="xray")` after posing.
- **Rotation mode.** New pose bones use quaternions. For bones you create and will drive or key by
  Euler angle, set `pb.rotation_mode = "XYZ"` once, right after creating them.
- **Bone collections** (Blender 4.0+, replacing bone layers): group bones so the user can show and
  hide them. `ctrl = arm_data.collections.new("Controls"); ctrl.assign(arm_data.bones["root"])`;
  `ctrl.is_visible = False` hides a group. Rigify rigs come with their own (`rig.data.collections_all`).

## IK

Two-bone limbs (arm, leg) get an IK constraint on the lower bone, a target bone at the wrist or
ankle, and a pole bone in front of the knee or behind the elbow. Target and pole are controls:
parent them to the root, not into the chain, and switch off their deform.

```python
import math
c = rig.pose.bones["forearm.L"].constraints.new("IK")
c.target = rig; c.subtarget = "hand_ik.L"
c.pole_target = rig; c.pole_subtarget = "elbow_pole.L"
c.chain_count = 2                    # forearm + upper arm
c.pole_angle = math.radians(-90)     # usually -90 or 90; the right one keeps the rest pose unchanged
```

After adding it, look at the rest pose: if the chain twists, change `pole_angle`. Then move the
target and confirm the joint bends the right way.

## Mechanical rigs: parenting, constraints, drivers

Mechanical things (doors, wheels, robots) usually don't need skinning: parent rigid parts to bones.
Preserve the part's world transform so changing its parent does not move it:

```python
assert "arm" in rig.pose.bones
world = part.matrix_world.copy()
part.parent = rig; part.parent_type = "BONE"; part.parent_bone = "arm"
bpy.context.view_layer.update()
part.matrix_world = world
bpy.context.view_layer.update()
assert all(abs(part.matrix_world[r][c] - world[r][c]) < 1e-5
           for r in range(4) for c in range(4))
```

For constrained or already animated parts, test on a copy: constraints and keyed local transforms
can override the assigned world transform.

- Limit Rotation (`"LIMIT_ROTATION"`) on hinges keeps doors and joints in range; Damped Track
  (`"DAMPED_TRACK"`) aims a part at a target (pistons, eyes, turrets); Copy Rotation ties parts
  that turn together.
- Drivers turn one value into another, e.g. a wheel that rolls as the body moves (distance / radius):

```python
w = rig.pose.bones["wheel"]; w.rotation_mode = "XYZ"
fc = w.driver_add("rotation_euler", 0)
var = fc.driver.variables.new(); var.name = "y"; var.type = "TRANSFORMS"
t = var.targets[0]; t.id = rig; t.bone_target = "root"
t.transform_type = "LOC_Y"; t.transform_space = "LOCAL_SPACE"
fc.driver.expression = "-y / 0.35"   # wheel radius 0.35 m; flip the sign if it rolls backwards
```

Check `fc.driver.is_valid` after building a driver.

## Tails, spines, tentacles

- Bendy bones curve a single bone smoothly: `edit_bone.bbone_segments = 6` (edit mode). Good for
  spines and soft limbs with few bones.
- Spline IK makes a chain follow a curve, for tails, tentacles, ropes and cables: add a curve with
  as many points as you want controls, put a Spline IK constraint (`"SPLINE_IK"`) on the last bone
  with `target` = the curve and `chain_count` = the bones in the chain, then hook the curve points
  to control bones (Hook modifiers) so the curve is animated through the rig.

## Symmetry

Build one side, then mirror it, so left and right can't drift apart.

- Name paired bones with `.L` / `.R` suffixes (`thigh.L`, `thigh.R`). Blender pairs bones, mirrors
  poses and flips vertex groups by these names. With the character facing -Y, its left is +X: put
  `.L` bones on +X.
- While editing bones, `arm_data.use_mirror_x = True` moves the other side's bone along with each edit.
- To create the other side, select the `.L` edit bones and symmetrize. The direction's options are
  labelled by name ("+X to -X" in Blender 5.1); print them rather than assuming:

```python
bpy.ops.object.mode_set(mode="EDIT")
for eb in arm_data.edit_bones:
    eb.select = eb.select_head = eb.select_tail = eb.name.endswith(".L")
print([(i.identifier, i.name) for i in
       bpy.ops.armature.symmetrize.get_rna_type().properties["direction"].enum_items])
bpy.ops.armature.symmetrize(direction="POSITIVE_X")  # the "+X to -X" option: .L copied to .R
bpy.ops.object.mode_set(mode="OBJECT")
```

- Weights: automatic weights on a symmetric mesh and rig come out symmetric. After fixing a `.L`
  group by hand, rebuild its `.R` twin from it (mesh active, object mode). Mirror a copy, not the
  group itself: mirroring a paired group swaps the two sides' weights.

```python
vgs = body.vertex_groups
vgs.active = vgs["thigh.L"]
bpy.ops.object.vertex_group_copy()                  # the copy becomes active
bpy.ops.object.vertex_group_mirror(flip_group_names=False, use_topology=False)
mirrored = vgs.active
if "thigh.R" in vgs:
    vgs.remove(vgs["thigh.R"])
mirrored.name = "thigh.R"
```

- Check: pose a `.L` bone and its `.R` twin by the same mirrored amount and compare both sides in
  `look(mode="angles", views=["front"])`.

## Skinning

Automatic weights overwrite existing groups with matching bone names. Save a checkpoint first;
for a rebind, test a duplicate mesh with independent mesh data. If weights should be retained,
keep the groups and set the existing Armature modifier's object to the intended rig instead of
rerunning automatic weights; verify bone names and the rest pose still match. Inspect existing
parenting and Armature modifiers before rebinding to avoid duplicate deformation.

For a new binding, automatic weights need the mesh selected and the armature selected and active,
in object mode:

```python
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
```

Inspect the modifier stack rather than moving Armature unconditionally to the top. A typical
half-mesh character uses **Mirror → Armature → Subdivision**: Mirror creates the other side and
its paired weights before the rig deforms both sides independently, then Subdivision smooths the
result. Other modifiers need ordering according to their purpose; check the posed result after
each change. Select the modifier bound to this rig, not just the first Armature modifier.

Preserve Volume can reduce twisting collapse in Blender. Compare both settings; game-engine
skinning may not reproduce this deformation, so also check the exported mesh in the target engine:

```python
mod = next(m for m in body.modifiers if m.type == "ARMATURE" and m.object == rig)
mod.use_deform_preserve_volume = True
```

If Blender reports "Bone Heat Weighting: failed to find solution for one or more bones":

- On a copy, merge unintended duplicates and remove unwanted interior faces, then retry.
- Or skin a voxel-remeshed copy, then transfer weights to the original with a Data Transfer
  modifier (vertex groups, nearest face interpolated) and apply it.
- Scale the whole thing up 10x, skin, scale back down — heat weighting struggles at tiny scales.

Clean only deform-bone groups, with the mesh selected and active in object mode. Preserve mask,
cloth, modifier and corrective groups. Drop tiny weights without removing a vertex's last
assignment, cap influences to the target engine's limit (4 in this example), and normalize deform
weights. Resolve locked deform groups deliberately before cleanup, then verify the result:

```python
if bpy.context.mode != "OBJECT":
    bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True); bpy.context.view_layer.objects.active = body
assert body.find_armature() == rig, "Cleanup must use the intended deform rig"
deform_names = {b.name for b in rig.data.bones if b.use_deform}
assert not any(g.lock_weight for g in body.vertex_groups if g.name in deform_names), "Locked deform groups"
bpy.ops.object.vertex_group_clean(group_select_mode="BONE_DEFORM", limit=0.01, keep_single=True)
bpy.ops.object.vertex_group_limit_total(group_select_mode="BONE_DEFORM", limit=4)
bpy.ops.object.vertex_group_normalize_all(group_select_mode="BONE_DEFORM", lock_active=False)
```

## Corrective shape keys

Where weights alone can't hold the shape (elbow and knee pinching, shoulders), sculpt a fix as a
shape key and drive it by how far the joint is bent:

```python
if not body.data.shape_keys:
    body.shape_key_add(name="Basis")
sk = body.shape_key_add(name="elbow_fix.L", from_mix=False)   # edit its vertices to the fixed shape
fc = sk.driver_add("value")
var = fc.driver.variables.new(); var.name = "a"; var.type = "ROTATION_DIFF"
var.targets[0].id = rig; var.targets[0].bone_target = "upper_arm.L"
var.targets[1].id = rig; var.targets[1].bone_target = "forearm.L"
fc.driver.expression = "min(a / 1.57, 1)"   # full fix at 90 degrees of bend
```

Model the fix with the joint posed at the angle where the driver reaches 1. Rigify rigs: use the
`DEF-` bones as the driver's targets.

## Faces

Keep faces simple unless asked for more: a jaw bone (rotating the lower face, weighted to the chin
and lower lip) and an eye bone per eye (the eyes parented to it, aimed with Damped Track at an eye
target), plus shape keys for blinks and mouth shapes (`blink.L`, `smile`, the A-I-U-E-O vowels for
lip sync). Shape keys need no weights and are easy to fix one at a time. Rigify's human metarig
already includes a full face rig, which is better when the face must be animated in detail.

## Verify

`get_scene_info(fields=["weights"], query="Body")` reports vertices with no positive deform-bone
weight and deform bones with no vertex group. A fully skinned mesh should have no unweighted
vertices. Missing groups are warnings to inspect, not an automatic failure: face, clothing or
other meshes may use bones that Body does not. This report checks the first bound Armature
modifier and does not check weight sums, influence limits or visible deformation.

After cleanup, check positive deform weights on the mesh explicitly (4 influences in this example):

```python
deform_names = {b.name for b in rig.data.bones if b.use_deform}
deform_indices = {g.index for g in body.vertex_groups if g.name in deform_names}
bad = []
for v in body.data.vertices:
    weights = [g.weight for g in v.groups if g.group in deform_indices and g.weight > 0]
    if not weights or len(weights) > 4 or abs(sum(weights) - 1.0) > 1e-4:
        bad.append(v.index)
assert not bad, f"Invalid deform weights on {len(bad)} vertices: {bad[:10]}"
```

For deliberately rigid or unskinned portions, validate their bone parenting separately and document
the excluded vertices rather than blindly requiring weights everywhere.

Before a temporary pose, save every bone's basis. Keep this snapshot across the `look` calls:

```python
from mathutils import Matrix
saved_pose = {pb.name: pb.matrix_basis.copy() for pb in rig.pose.bones}
pb = rig.pose.bones["upper_arm_fk.L"]          # a Rigify control; on your own rig, the bone to bend
pb.matrix_basis = saved_pose[pb.name] @ Matrix.Rotation(1.2, 4, "X")
bpy.context.view_layer.update()
```

Pose through `matrix_basis` and never change `rotation_mode` to test: Rigify controls use
quaternions, and a bone left in another mode keys and constrains differently from its neighbours.

`look(mode="angles", target=["Body"])` and check elbows, shoulders, knees and hips for collapsing
or stretching. Then restore the saved pose, including if inspection fails; do not reset all bones
to identity. Do not key this temporary pose or change the frame while inspecting it, since
animation evaluation can overwrite it:

```python
for name, basis in saved_pose.items():
    rig.pose.bones[name].matrix_basis = basis
bpy.context.view_layer.update()
```

One pose misses most problems. For a range-of-motion test, use a disposable copy of the rig and
meshes with independent armature and mesh data, remapped parents, modifiers, constraints and
driver targets. Give the copy a new test Action; detach its existing Action and NLA tracks without
deleting shared Actions or editing the original. Key a few frames that bend each major joint to
its limit (arm raised, arm forward, elbow and knee at 120°, spine twisted, a squat), then
`look(mode="frames", frames=[...], view="three_quarter")` shows them in one strip. Record the
original frame and subframe, restore them even if inspection fails, and remove only the disposable
objects and newly created test data. Never delete the original Action to clean up a test.

## Exporting rigs to game engines

The engine is Unreal Engine 5 unless the user names another; `get_guide("unreal-engine")` covers
naming (`SK_`, `A_`), the Mannequin, retargeting and root motion. Export only what the engine
should get: the deform skeleton and the meshes. Select them, then:

- **FBX (Unreal, Unity):**
  ```python
  bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"},
      add_leaf_bones=False,              # no extra _end bones
      use_armature_deform_only=True,     # drop controls; for Rigify, only the DEF- bones
      primary_bone_axis="Y", secondary_bone_axis="X",
      apply_scale_options="FBX_SCALE_NONE",  # the default; FBX_SCALE_ALL/UNITS import 100x small in UE
      bake_anim=False)                   # True when exporting animation
  ```
  Unreal: model in metres at real size. An armature object named anything but "Armature" is
  imported as an extra root bone, so either name it "Armature" or give the rig a real `root` bone
  at the origin that everything else hangs from. After import, check the size (bounds read in
  centimetres); if it is off by 100x, check `apply_scale_options` is FBX_SCALE_NONE, the scene's
  Unit Scale (`scene.unit_settings.scale_length`) is 1.0 and the rig and meshes have applied
  scale, then export again.
- **glTF (Godot, three.js, Unity with glTFast):** `bpy.ops.export_scene.gltf(filepath=path,
  use_selection=True, export_def_bones=True)` exports deform bones only.
- Rigify's `DEF-` bones are not all parented to each other in the rig itself; deform-only export
  reparents each to its nearest exported ancestor. Check the hierarchy in the engine (one root,
  a continuous spine to the head) before animating there, and retarget to engine skeletons such as
  Unreal's mannequin in the engine (IK Retargeter), not by renaming bones in Blender.
- Use the target engine's influence limit (4 in the Skinning example). Prepare export copies and
  bake only modifiers required by the export format, preserving the Armature and intended shape
  keys. Topology-changing modifiers may not be directly applicable to meshes with shape keys;
  use a workflow that preserves vertex correspondence and verify exported morph targets. Keep
  the editable originals intact.
