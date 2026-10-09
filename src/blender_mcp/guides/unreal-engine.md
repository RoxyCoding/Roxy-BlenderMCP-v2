---
title: Unreal Engine 5
summary: Getting assets from Blender into Unreal Engine 5, the default game engine - naming, scale and pivots, Nanite vs LODs, Lumen and lightmaps, collision and sockets, FBX export settings for static and skeletal meshes, the Mannequin and retargeting, animation and root motion, and textures (DirectX normals, ORM packing).
---

# Unreal Engine 5

Unreal Engine 5 is the game engine to target unless the user names another. Build every game
asset so it imports into UE5 cleanly, and still follow `get_guide("japanese-design")` for what
the world looks like.

## Naming

Unreal projects sort assets by prefix. Name the Blender objects and the exported files the same:

| Asset | Prefix | Example |
|---|---|---|
| Static mesh | `SM_` | `SM_VendingMachine` |
| Skeletal mesh | `SK_` | `SK_Schoolgirl` |
| Animation | `A_` | `A_Schoolgirl_Walk` |
| Material / instance | `M_` / `MI_` | `MI_Painted_Metal_Worn` |
| Texture | `T_` + suffix `_D` (colour), `_N` (normal), `_ORM` | `T_Crate_ORM` |
| Collision | `UCX_` / `UBX_` / `USP_` / `UCP_` + mesh name + `_NN` | `UCX_SM_Crate_01` |
| Socket (attach point) | `SOCKET_` on an empty | `SOCKET_Handle` |

Unique names, no spaces, ASCII only (Japanese names break some tools and paths).

## Scale, axes and pivots

- Model in metres at real size in Blender (scene Unit Scale 1.0); Unreal works in centimetres.
  Keep the FBX exporter's default `apply_scale_options="FBX_SCALE_NONE"`: it writes the unit
  conversion into the file and Unreal imports at the right size. `FBX_SCALE_ALL` and
  `FBX_SCALE_UNITS` import 100x too small (tested on UE5 with Blender 5.1). Check the result
  with the static mesh's bounds, which read in centimetres.
- Apply scale and rotation on everything before export (`transform_apply`), or Unreal inherits
  odd scales and rotations.
- The pivot in Unreal is the FBX origin. Export each asset sitting at the world origin with its
  pivot where it should be: bottom centre for props and furniture, the hinge for doors (see
  Moving parts), the
  corner for modular kit pieces (`get_guide("level-design")`).
- Keep Blender's default FBX axes (forward -Z, up Y); Unreal converts them. Blender +X stays +X
  and up stays up, but Y flips: Blender's -Y (an object's front) becomes Unreal's +Y. If an asset
  imports facing the wrong way, rotate it in Blender and apply, rather than fixing it in Unreal.

## Nanite, LODs and polygon budgets

- **Nanite** (static meshes; opaque and masked materials) streams detail automatically, so
  high-poly static meshes are fine and need no LODs: scanned props, sculpted rocks, detailed
  architecture. Enable Nanite on import. Still remove hidden interior faces and fix non-manifold
  geometry (`get_guide("retopology")`).
- **Not Nanite:** skeletal meshes (characters), translucent materials (glass, water), and
  anything the project disables Nanite for. These need sane triangle counts and LODs.
- **LODs in Unreal:** Unreal only reads LODs from an FBX LOD group, which Blender's exporter
  doesn't write. Either let Unreal generate them (Static Mesh Editor, LOD settings, number of
  LODs) or export each LOD as its own FBX (`SM_Crate_LOD1.fbx`...) and import it into the
  Static Mesh Editor's LOD slots. Skeletal meshes: Unreal's skeletal LOD generation.

## Lighting: Lumen and lightmaps

UE5 projects use Lumen (dynamic global illumination) by default, which needs no lightmap UVs.
Add a second, non-overlapping lightmap UV channel (`get_guide("level-design")`) only when the
project bakes static lighting. Lighting set up in Blender does not transfer; Blender renders are
for look development and previews.

## Collision and sockets

- Simple collision as separate meshes named after the render mesh: boxes (`UBX_`), spheres
  (`USP_`), capsules (`UCP_`) or convex hulls (`UCX_`, each part convex, a few hundred
  triangles at most). Export them together with the mesh, at the same transform.
- Sockets: an empty named `SOCKET_<Name>` parented to the mesh, at the attach point and
  orientation (a lamp's bulb, a weapon's grip, a sign's mount). Include empties in the export.

## Moving parts: doors, lids, drawers

A static mesh can't move part of itself. Anything the player opens is its own mesh with its pivot
on its hinge (or its runner for a drawer), placed as a child component and turned in a Blueprint:

- Model the moving parts with `"moves"` in their `model_plan` (`get_guide("modeling")`, Parts that
  move) and run `verify` until they clear everything across their range.
- `export_to_unreal` then writes the fixed parts as `SM_<Name>` and each moving part, with what
  it carries, as `SM_<Name>_<Part>` whose origin is the hinge. Its reply gives each part's
  location relative to `SM_<Name>` in centimetres and the rotation to animate: a hinge about
  Blender's z is Yaw (sign reversed by the Y flip: Blender -100 degrees is Yaw +100), about x
  Roll, about y Pitch (sign reversed); a slide is a relative location.
- In Unreal: an Actor Blueprint with `SM_<Name>` as the root, each moving part as a child Static
  Mesh Component at that location, a Timeline (0 to 1) driving its relative rotation or location
  from closed to open, and an interaction (overlap or input) that plays and reverses it.
- Give moving parts their own simple collision so an open door blocks the player and a closed
  one doesn't leave a gap; keep collision off the 2-3 mm clearance so it doesn't stick.
- For a skeletal approach instead (many moving parts, or animation authored in Blender), parent
  each rigid part to a bone at its hinge (`get_guide("rigging")`) and export as skeletal.

## Exporting: use export_to_unreal

`export_to_unreal(name=...)` does the export for both static and skeletal meshes: SM_/SK_ naming,
the asset's own origin as the pivot, the tested FBX settings, "Armature" as the armature's name,
collision and sockets included, and the scene left as it was. It returns the file, the bounds
Unreal should report and the Unreal MCP steps: `import_file`, `get_bounds`, then
`export_to_unreal(action="verify", name=..., unreal_bounds=...)`, which names the cause when the
size, pivot or facing is off. The settings it uses, for reference:

## Exporting static meshes

Select the mesh with its collision and sockets, at the origin, then:

```python
bpy.ops.export_scene.fbx(filepath=path, use_selection=True,
    object_types={"MESH", "EMPTY"},
    apply_scale_options="FBX_SCALE_NONE",   # the default; the others import 100x too small
    mesh_smooth_type="FACE",       # writes smoothing groups; avoids Unreal's missing-smoothing warning
    use_tspace=True,               # tangents; fails on n-gons, so triangulate or set use_triangles=True
    use_mesh_modifiers=True,       # applies modifiers (bevels, weighted normals) in the exported mesh
    add_leaf_bones=False, bake_anim=False)
```

One asset per FBX file, named like the asset (`SM_Crate.fbx`). Material slots export by name;
Blender shader nodes do not. Rebuild the look in Unreal as material instances of a master
material, fed by exported textures.

## Textures

- Export image textures as PNG or TGA, power-of-two sizes (1024, 2048, 4096).
- **Normal maps:** Unreal uses the DirectX convention, Blender OpenGL. Poly Haven offers both;
  for Unreal take the DirectX one (`nor_dx`), or flip the green channel in Unreal's texture
  settings when importing an OpenGL map. ambientCG materials are built from their OpenGL map
  (`NormalGL`), and baked normal maps from Blender are OpenGL too: flip green in Unreal.
- **ORM:** Unreal packs ambient occlusion, roughness and metallic into one texture, R/G/B. Poly
  Haven's `arm` map is already in that order. Import ORM and normal maps with sRGB off.
- Layered wear and dirt built in Blender with node masks (`get_guide("surface-realism")`) must be
  baked to textures to reach Unreal, or rebuilt with Unreal's material layering. For hero and
  close-up assets, texture in Substance 3D Painter instead: `painter_handoff(action="export",
  target="unreal")` and the Roxy Painter MCP give BaseColor, DirectX Normal and packed ORM ready
  for Unreal (surface-realism guide, Substance 3D Painter).

## Skeletal meshes and the Mannequin

- Follow `get_guide("rigging")` for the rig, then export only the deform skeleton and meshes
  (FBX settings there: `add_leaf_bones=False`, `use_armature_deform_only=True`,
  `primary_bone_axis="Y"`, `secondary_bone_axis="X"`, `apply_scale_options="FBX_SCALE_NONE"`).
- One root bone at the origin that everything hangs from, and name the armature object
  `Armature`: any other name becomes an extra root bone above it (tested: an armature called
  `Rig` imported as Rig > root > ...). A non-deforming root bone is still exported as the
  parent of the deform bones.
- Characters meant to use Unreal animations: model in the Mannequin's proportions and A-pose,
  keep its bone structure if possible, and retarget in Unreal with an IK Rig and IK Retargeter
  (UE5 Manny/Quinn), rather than renaming bones in Blender.
- Up to 4 bone influences per vertex for most platforms (weight cleanup in the rigging guide);
  more needs Unreal's skin weight settings.

## Animation

- Bake constraints and IK to keys before export (`get_guide("animation")`, Baking and exporting),
  then export with `bake_anim=True`, one action per FBX or all actions as separate clips.
- Frame rate: match the Unreal project (commonly 30 fps); set `scene.render.fps` before keying.
- Root motion: if the character should move by its animation (walks that cover ground, attacks
  that lunge), animate the root bone's translation and enable root motion on the animation in
  Unreal; otherwise keep the root at the origin and move the character in gameplay.
- Import animations onto the existing skeleton asset (`SK_..._Skeleton`) so they share it.

## Checking in Unreal

If an Unreal MCP server is connected, import and check there; otherwise tell the user what to
check: size against the Mannequin, facing, pivot, smoothing, collision (show Simple Collision),
Nanite enabled where intended, normal map direction (dents look like bumps when green is wrong),
and for characters the skeleton hierarchy and a test animation.
