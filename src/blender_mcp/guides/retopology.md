---
title: Retopology and mesh cleanup
summary: Turning generated or scanned meshes into clean, lighter geometry - cleanup, remeshing, decimation, smooth shading, UVs, baking detail back, game LODs and 3D printing.
---

# Retopology and mesh cleanup

Generated and scanned models are dense, triangulated, and often non-manifold. What to do depends
on where the mesh is going:

| Goal | Approach |
|---|---|
| Still render, background prop | Leave it; maybe Decimate |
| Game prop | Decimate or remesh, then bake normals from the original |
| Deforming character | Quad remesh (QuadriFlow), clean loops at joints, then rig |
| 3D print | Voxel remesh for a watertight solid |

Always work on a copy and keep the original as the bake source: `low = src.copy(); low.data = src.data.copy()`.
Remeshing and decimation can't be undone from here: `checkpoint(action="save")` before them.

## Diagnose

`get_scene_info(fields=["topology"], query=name)` reports quads, tris, ngons, non-manifold edges,
boundary edges, loose vertices and poles; `look(mode="angles", shading="wireframe", target=[name])`
shows the edges.

## Clean up

```python
import bmesh
bm = bmesh.new(); bm.from_mesh(obj.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=0.0001)
loose = [v for v in bm.verts if not v.link_edges]
bmesh.ops.delete(bm, geom=loose, context="VERTS")
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(obj.data); bm.free()
```

## Reduce

- **Decimate** keeps the shape and UVs, gives triangles. Fast, fine for static props:
  `m = obj.modifiers.new("Decimate", "DECIMATE"); m.ratio = 0.1`. Planar mode (`decimate_type="DISSOLVE"`)
  is good for hard-surface.
- **Voxel remesh** makes a watertight, even mesh but loses UVs and sharp edges:
  `obj.data.remesh_voxel_size = 0.01; bpy.ops.object.voxel_remesh()` (active object needed).
  Size relative to the object: ~1/200 of its largest dimension is a sane start.
- **QuadriFlow** gives quads for deformation:
  `bpy.ops.object.quadriflow_remesh(target_faces=4000)`. It is slow on dense input and can fail on
  non-manifold meshes — voxel remesh first, then QuadriFlow the result.
- **Shrinkwrap** a low mesh onto the high one (`modifiers.new("Shrinkwrap", "SHRINKWRAP")`,
  `target = high`) to recover the silhouette after remeshing.

Face budgets: hero game character 15–50k tris, prop 500–5k, background 50–500.

## Smooth shading

Auto Smooth (`mesh.use_auto_smooth`) was removed in 4.1. Now shade smooth, then mark sharp edges
by angle with the data API (no context needed):

```python
import math
for p in obj.data.polygons:
    p.use_smooth = True
obj.data.set_sharp_from_angle(angle=math.radians(30))
```

`bpy.ops.object.shade_auto_smooth()` instead adds a "Smooth by Angle" modifier, which stays live
but must be applied (or exported with modifiers) for engines. Hard-surface models also benefit
from a Weighted Normal modifier after any Bevel.

## Game LODs

In Unreal Engine 5 (the default engine) static meshes with opaque or masked materials use
Nanite and need no LODs: keep them detailed and clean instead. LODs matter for skeletal meshes,
translucent meshes and other engines.

Make each LOD from the finished LOD0 with Decimate (collapse) and keep UVs: about 50%, 25% and
10% of LOD0's triangles. Unreal reads LODs only from an FBX LOD group, which Blender doesn't
write: export each LOD as its own FBX (`SM_Crate_LOD1.fbx`) for the Static Mesh Editor's LOD
slots, or let Unreal generate them (`get_guide("unreal-engine")`). Unity picks up `_LOD0`,
`_LOD1`... names in one FBX. Check each with `get_scene_info(fields=["topology"])` and from the
distance it will be seen at.

## UVs

Hard-surface props, furniture, buildings and anything modelled with the roxy helpers:
`uv_bake(action="unwrap", name=...)` (or `roxy.unwrap` in a script). It puts seams on hard edges,
splits smooth and ring-shaped regions so they open flat, packs each material's objects as one
texture set, and gives every island one texel density across the asset - the largest set fills
the resolution, smaller sets get the power of two that holds the same density. Then
`uv_bake(action="check")` until it reports no problems: nothing outside 0-1, nothing flipped,
under 5% stretch, no overlap, islands at least the margin apart (8 px; 16 px for 4k textures).

Texel density to aim for, for a first-person game: about 512 px/m for props and buildings seen
up close, 1024 px/m for hero props and what the player holds, 256 px/m for distant scenery.
Keep it the same across neighbours (`density=`), or the sharper one gives the other away.

Characters and organic shapes need seams placed by hand along hidden lines (inside the arms and
legs, under the hair line, round the soles): mark them in bmesh (`edge.seam = True`), then
`bpy.ops.uv.unwrap(method="ANGLE_BASED")` in edit mode, and check with `roxy.check_uvs(obj)`.

`roxy.uv_world_box` is a different thing: tiling UVs in metres for materials that repeat
(plaster, flooring, wood), rendered in Blender. Keep it for that; textures painted or baked for
the object need the unique "Unwrap" map.

## Bake detail back

Bake normals (and colour) from the original high mesh to the low one's UVs, in Cycles:

1. Create an image (`bpy.data.images.new("Low_Normal", 2048, 2048, is_data=True)`) and an Image
   Texture node using it in the low mesh's material, set as the active node.
2. Select high, make low active; `scene.render.bake.use_selected_to_active = True`,
   `cage_extrusion` ~1–2% of the object size.
3. `scene.render.bake.margin = 16` (pixels at 2048, so mip-mapping doesn't bleed seams), then
   `bpy.ops.object.bake(type="NORMAL")`; for colour use `type="DIFFUSE"` with only the colour pass.
4. Save the image or the bake is lost when Blender closes:
   `img.filepath_raw = "//textures/Low_Normal.png"; img.file_format = "PNG"; img.save()`.
5. Wire it into a Normal Map node (see `get_guide("materials")`) and compare with `look(mode="angles")`.

Switching the engine to Cycles for the bake: read the current engine first and restore it after
(see `get_guide("bpy")`).

## 3D printing

- Work in real units and check them: `scene.unit_settings.scale_length` 0.001 with
  `length_unit = "MILLIMETERS"` makes 1 unit = 1 mm, as slicers expect; or keep metres and export
  with a scale of 1000.
- The mesh must be one closed, manifold solid: voxel remesh fixes holes and self-intersections.
  `get_scene_info(fields=["topology"])` should report no non-manifold or boundary edges.
- Walls at least 1-2 mm thick for FDM printers (0.5-1 mm for resin); thin details break.
  Solidify (`modifiers.new("Solidify", "SOLIDIFY")`) open shells before remeshing.
- Flat base on the build plate; split tall or overhanging models into parts.
- Export STL (or OBJ) with the built-in exporters: `bpy.ops.wm.stl_export(filepath=...)`
  (the old `export_mesh.stl` was removed in 4.2) or `bpy.ops.wm.obj_export(...)`; read their
  arguments first.
