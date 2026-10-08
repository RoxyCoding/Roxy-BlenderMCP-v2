---
title: Geometry Nodes
summary: Procedural geometry from Python in Blender 4.x/5.x - building node groups and their inputs, finding nodes and sockets that differ between versions, fields, tested helpers for instances along curves, tubes and cables, density from painted vertex groups, realizing instances, and preparing results for Unreal Engine 5.
---

# Geometry Nodes

Use Geometry Nodes for geometry that is repetitive, rule-based or should stay editable: rows of
poles and fences, cables and pipes, scattered debris and plants, tiled facades, stairs and
railings that follow a path. One node group on a modifier replaces hundreds of hand-placed
objects, and its inputs let you (or the user) adjust spacing, density or size afterwards. For a
one-off shape, plain mesh scripting is simpler (`get_guide("bpy")`).

## Building node groups from Python

- Since 4.0 a node group's inputs and outputs live in `ng.interface`:
  `ng.interface.new_socket(name, in_out="INPUT"|"OUTPUT", socket_type="NodeSocketGeometry")`
  (also `NodeSocketFloat`, `NodeSocketInt`, `NodeSocketVector`, `NodeSocketObject`,
  `NodeSocketCollection`, `NodeSocketMaterial`, `NodeSocketBool`). The old `ng.inputs.new` is gone.
- The modifier's input values are keyed by the interface item's identifier (`"Socket_2"`), not
  its name: `mod[item.identifier] = value`. Find it with
  `next(i.identifier for i in ng.interface.items_tree if i.name == "Spacing" and i.in_out == "INPUT")`.
  After changing a value from Python, `obj.update_tag()` and `bpy.context.view_layer.update()`.
- Node type names start with `GeometryNode` (Instance on Points is `GeometryNodeInstanceOnPoints`),
  except shared ones: Math is `ShaderNodeMath`, Random Value `FunctionNodeRandomValue`, Map Range
  `ShaderNodeMapRange`. List them: `[t for t in dir(bpy.types) if t.startswith("GeometryNode")]`.

## Sockets and settings change between versions

Before wiring an unfamiliar node, print it - names, data types and whether each socket is enabled:

```python
n = ng.nodes.new("GeometryNodeResampleCurve")
print([(s.name, s.type, s.enabled) for s in n.inputs], [s.name for s in n.outputs])
print([p.identifier for p in n.bl_rna.properties if not p.is_readonly])
```

- Several sockets can share a name, one per data type (Random Value, Switch, Mix); only the one
  matching the node's `data_type` is enabled. Pick by name and `enabled` (the `roxy.sock` helper below).
- Some settings are node properties, others became input sockets ("menu sockets") in 4.x/5.x and
  differ per node: in 5.1 Curve to Points has a `mode` property, but Resample Curve has a `Mode`
  input. Printing both lists, as above, tells you which.
- Sockets that are hidden for the current mode (Curve to Points' `Length` in COUNT mode) are
  disabled until you set the mode.

## Fields in one paragraph

Many inputs take a field: a value computed per point, face or instance instead of one number.
Link a node's output into such an input and it is evaluated for every element - a Random Value
gives every instance its own rotation, a Named Attribute reads a painted vertex group per point,
Position gives each element's location. If an input shows a diamond in the UI it accepts fields.

## Helpers

Tested on Blender 5.1.

The addon provides these as `roxy.<name>` inside execute_blender_code (addon protocol 18+), so call them directly - don't paste or redefine them. If `roxy` is undefined, the Blender addon is outdated: get_addon_status says how to update it.

- `roxy.gn_modifier(obj, name)` - A Geometry Nodes modifier on obj with an empty group: Geometry in, Geometry out.
- `roxy.sock(node, name, output=False)` - The enabled socket called name; several sockets can share a name, one per data type.
- `roxy.expose(mod, name, socket_type, default)` - Add a group input the user can change on the modifier, and return the group input socket.
- `roxy.instances_along_curve(curve_obj, source_obj, spacing=10.0, name='AlongCurve')` - Copies of source_obj every `spacing` metres along a curve object (poles, posts, lamps).
- `roxy.tube_from_curve(curve_obj, radius=0.01, material=None, name='Tube')` - Turn a curve object into a round tube: cables, wires, pipes, hoses, rails.
- `roxy.density_from_vertex_group(dist_node, ng, group_name, density)` - Make a Distribute Points on Faces node's density follow a painted vertex group (0-1).
- `roxy.realize(mod)` - Insert Realize Instances before the output, so exporters and later modifiers see real mesh.

Examples:

```python
# Utility poles every 25 m along a road curve, with an editable spacing.
mod = roxy.instances_along_curve(road_curve, pole, spacing=25)
spacing = roxy.expose(mod, "Spacing", "NodeSocketFloat", 25.0)
pts = next(n for n in mod.node_group.nodes if n.type == "CURVE_TO_POINTS")
mod.node_group.links.new(spacing, roxy.sock(pts, "Length"))

# Overhead wires between them: a Bezier curve per span, sagging in the middle, turned into tubes.
roxy.tube_from_curve(wire_curve, radius=0.008, material=bpy.data.materials["Cable"])

# Grass only where a vertex group called "grass" was painted.
roxy.density_from_vertex_group(dist_node, ng, "grass", density=40)
```

For general scattering (random rotation and scale, several source objects) use the `roxy.scatter`
helper in `get_guide("environment-art")`.

## Instances and realizing

Instances are cheap: thousands of copies share one mesh. Keep them as instances while you work.
Realize them (the `roxy.realize` helper, or Realize Instances in the tree) only when something needs
real geometry: a later modifier, a boolean, a bake, or an export that must contain them. Realizing
very many instances makes a huge mesh; check the triangle count first
(`get_scene_info(fields=["topology"])`).

## Passing data to materials

Store values on the geometry with Store Named Attribute (`GeometryNodeStoreNamedAttribute`, a
name and a `domain`) and read them in the material with an Attribute node
(`ShaderNodeAttribute`, `attribute_name` = that name): per-instance colour variation, wetness
toward the ground, wear along an edge. Instances carry their own attributes into the shader with
the Attribute node's type set to Instancer.

## For Unreal Engine 5

Unreal does not run Geometry Nodes. Decide per result:

- Structures and one-off results (a fence along a path, a railing, cables, a tiled facade):
  `roxy.realize`, then export with `use_mesh_modifiers=True` (`get_guide("unreal-engine")`), or apply
  the modifier on a copy first.
- Scattered vegetation and debris over large areas: export the source assets (one `SM_` each) and
  scatter them in Unreal with its foliage tools or PCG instead of exporting millions of baked
  triangles; Nanite and instancing handle it there.
- Keep the Blender file with the live node groups as the source, so the layout can be changed and
  re-exported.

## Checking results

- `look` shows the evaluated result. A node group that silently outputs nothing usually has a
  missing link to the Group Output, a disabled socket used by mistake, or a field linked into an
  input that doesn't accept one.
- Count what you made: evaluated vertices with `obj.evaluated_get(depsgraph).to_mesh()`, instances
  with `sum(1 for i in depsgraph.object_instances if i.is_instance and i.parent and i.parent.original == obj)`.
- Hide the source objects used for instancing (their own collection, excluded or hidden), or they
  show up at the origin.
