---
title: Writing bpy that works on any Blender
summary: Version-proof scripting, API introspection, operator context, and the mistakes that break scripts on other people's machines.
---

# Writing bpy that works on any Blender

Scripts run in the user's live Blender, whose version, language and add-ons you don't know.
`get_addon_status` reports `blender_version`; check it before using anything version-specific.

## Look things up instead of guessing

Introspect with RNA before indexing sockets or setting enums:

```python
# Valid values of any enum property
[i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
# Properties of a type
[p.identifier for p in bpy.types.ShaderNodeTexSky.bl_rna.properties]
# Operator arguments
[(p.identifier, p.type) for p in bpy.ops.mesh.primitive_cube_add.get_rna_type().properties]
# A node's sockets, in the mode you intend to use
tree = bpy.data.node_groups.new("_probe", "ShaderNodeTree")
n = tree.nodes.new("ShaderNodeMix"); n.data_type = "RGBA"
print([(i, s.name, s.type) for i, s in enumerate(n.inputs) if s.enabled])
bpy.data.node_groups.remove(tree)
```

## Portability rules

- Find nodes by `type`, never by name: names are localized. `next(n for n in nodes if n.type == "BSDF_PRINCIPLED")`.
- Address sockets by name only after checking they exist in this version (Principled BSDF renamed
  many inputs in 4.0: `Emission Color`, `Subsurface Weight`, `Specular IOR Level`, `Coat Weight`,
  `Sheen Weight`, `Transmission Weight`). `sock = node.inputs.get("Emission Color") or node.inputs.get("Emission")`.
- Never hardcode enum identifiers; read them (above). `scene.render.engine` is a dynamic enum that
  RNA under-reports; read the current value, and if you must switch, assign inside
  `try/except TypeError` — the error lists every accepted value. EEVEE is `BLENDER_EEVEE_NEXT` in
  4.2–4.x and `BLENDER_EEVEE` before and after.
- Material colors live on shader node inputs. `material.diffuse_color` only drives the solid
  viewport. In 5.0+ `material.use_nodes` is always on; don't rely on toggling it.
- Animation data changed in 4.4 (slotted actions) and 5.0 removed `Action.fcurves`. Insert keys with
  `obj.keyframe_insert("location", frame=f)` (works everywhere) and reach fcurves through
  `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, obj.animation_data.action_slot)`
  on 4.4+, falling back to `action.fcurves` on older versions.

## Data API over operators

Prefer `bpy.data` and object properties over `bpy.ops`: they need no context and are faster.
`bpy.data.meshes.new` + `from_pydata`, `bmesh` for editing, `obj.modifiers.new`, `obj.matrix_world`.

When you need an operator:

- Code runs from a timer, not a UI area, so `bpy.context.screen` and `bpy.context.window` can be
  None. Operators that need a viewport need an override built from the window manager:
  ```python
  win = bpy.context.window_manager.windows[0]
  area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
  region = next(r for r in area.regions if r.type == "WINDOW")
  with bpy.context.temp_override(window=win, area=area, region=region,
                                 active_object=obj, selected_objects=[obj]):
      bpy.ops.object.shade_smooth()
  ```
- `mode_set` needs an active, visible, selectable object. Always return to OBJECT mode at the end
  of a step, even on failure (`try/finally`).
- `obj.select_set(True)` and `bpy.context.view_layer.objects.active = obj` before ops that act on
  the selection.

## Reading state correctly

- Transforms update lazily. After moving, rotating, parenting or adding constraints, call
  `bpy.context.view_layer.update()` before reading `matrix_world`, bounding boxes or world
  positions; otherwise you read the old values.
- `obj.data` is the mesh before modifiers. For the mesh as shown (subdivided, mirrored, deformed
  by an armature), evaluate it, and free it afterwards:
  ```python
  dg = bpy.context.evaluated_depsgraph_get()
  ev = obj.evaluated_get(dg); me = ev.to_mesh()
  print(len(me.vertices)); ev.to_mesh_clear()
  ```
- For many vertices, read and write in bulk instead of looping in Python:
  `co = [0.0] * (len(me.vertices) * 3); me.vertices.foreach_get("co", co)` (and `foreach_set`).
  Never call an operator inside a per-object or per-vertex loop; use the data API or one operator
  on a selection.

## Working style

- Small steps. Run a chunk and `print` what you need to know.
- Before something hard to undo (applying modifiers or transforms, joining, remeshing, deleting
  many objects, a long script), `checkpoint(action="save")`.
- Name everything you create; later steps and the user refer to it by name.
- Keep the scene organized: one collection per logical group (`bpy.data.collections.new`, link
  to `scene.collection`).
- Apply scale (`obj.data.transform(Matrix.Diagonal(...))` or `transform_apply`) before rigging,
  modifiers that depend on it, or export.
- Duplicate with `obj.copy()` (shares mesh data, cheap) for repeated props; `obj.data.copy()` only
  when the copy must differ.
- Units are metres. Size things from real-world references; unless the user names another
  region these are Japanese (`get_guide("japanese-design")`): an interior door ~2.0 m tall, a
  dining table 0.7 m, a person 1.6-1.7 m.
