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
  matching the node's `data_type` is enabled. Pick by name and `enabled` (the `sock` helper below).
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

Tested on Blender 5.1. Paste them into a script, then call them:

```python
def gn_modifier(obj, name):
    """A Geometry Nodes modifier on obj with an empty group: Geometry in, Geometry out."""
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi = ng.nodes.new("NodeGroupInput"); go = ng.nodes.new("NodeGroupOutput")
    mod = obj.modifiers.new(name, "NODES"); mod.node_group = ng
    return mod, ng, gi, go

def sock(node, name, output=False):
    """The enabled socket called name; several sockets can share a name, one per data type."""
    return next(s for s in (node.outputs if output else node.inputs) if s.name == name and s.enabled)

def expose(mod, name, socket_type, default):
    """Add a group input the user can change on the modifier, and return the group input socket."""
    ng = mod.node_group
    item = ng.interface.new_socket(name, in_out="INPUT", socket_type=socket_type)
    item.default_value = default
    mod[item.identifier] = default          # modifier inputs are keyed by identifier ("Socket_2"), not name
    gi = next(n for n in ng.nodes if n.type == "GROUP_INPUT")
    return gi.outputs[name]

def instances_along_curve(curve_obj, source_obj, spacing=10.0, name="AlongCurve"):
    """Copies of source_obj every `spacing` metres along a curve object (poles, posts, lamps)."""
    mod, ng, gi, go = gn_modifier(curve_obj, name)
    n, l = ng.nodes, ng.links
    pts = n.new("GeometryNodeCurveToPoints"); pts.mode = "LENGTH"
    sock(pts, "Length").default_value = spacing
    info = n.new("GeometryNodeObjectInfo"); info.inputs["Object"].default_value = source_obj
    info.inputs["As Instance"].default_value = True
    inst = n.new("GeometryNodeInstanceOnPoints")
    l.new(gi.outputs["Geometry"], pts.inputs["Curve"])
    l.new(pts.outputs["Points"], inst.inputs["Points"])
    l.new(info.outputs["Geometry"], inst.inputs["Instance"])
    l.new(pts.outputs["Rotation"], inst.inputs["Rotation"])   # follows the curve's direction
    l.new(inst.outputs["Instances"], go.inputs["Geometry"])
    return mod

def tube_from_curve(curve_obj, radius=0.01, material=None, name="Tube"):
    """Turn a curve object into a round tube: cables, wires, pipes, hoses, rails."""
    mod, ng, gi, go = gn_modifier(curve_obj, name)
    n, l = ng.nodes, ng.links
    circle = n.new("GeometryNodeCurvePrimitiveCircle")
    circle.inputs["Resolution"].default_value = 8
    circle.inputs["Radius"].default_value = radius
    to_mesh = n.new("GeometryNodeCurveToMesh"); to_mesh.inputs["Fill Caps"].default_value = True
    l.new(gi.outputs["Geometry"], to_mesh.inputs["Curve"])
    l.new(circle.outputs["Curve"], to_mesh.inputs["Profile Curve"])
    last = to_mesh.outputs["Mesh"]
    if material:
        setm = n.new("GeometryNodeSetMaterial"); setm.inputs["Material"].default_value = material
        l.new(last, setm.inputs["Geometry"]); last = setm.outputs["Geometry"]
    l.new(last, go.inputs["Geometry"])
    return mod

def density_from_vertex_group(dist_node, ng, group_name, density):
    """Make a Distribute Points on Faces node's density follow a painted vertex group (0-1)."""
    attr = ng.nodes.new("GeometryNodeInputNamedAttribute"); attr.data_type = "FLOAT"
    attr.inputs["Name"].default_value = group_name
    mul = ng.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = density
    ng.links.new(sock(attr, "Attribute", output=True), mul.inputs[0])
    ng.links.new(mul.outputs["Value"], dist_node.inputs["Density"])

def realize(mod):
    """Insert Realize Instances before the output, so exporters and later modifiers see real mesh."""
    ng = mod.node_group
    go = next(n for n in ng.nodes if n.type == "GROUP_OUTPUT")
    link = go.inputs["Geometry"].links[0]
    real = ng.nodes.new("GeometryNodeRealizeInstances")
    ng.links.new(link.from_socket, real.inputs["Geometry"])
    ng.links.new(real.outputs["Geometry"], go.inputs["Geometry"])
```

Examples:

```python
# Utility poles every 25 m along a road curve, with an editable spacing.
mod = instances_along_curve(road_curve, pole, spacing=25)
spacing = expose(mod, "Spacing", "NodeSocketFloat", 25.0)
pts = next(n for n in mod.node_group.nodes if n.type == "CURVE_TO_POINTS")
mod.node_group.links.new(spacing, sock(pts, "Length"))

# Overhead wires between them: a Bezier curve per span, sagging in the middle, turned into tubes.
tube_from_curve(wire_curve, radius=0.008, material=bpy.data.materials["Cable"])

# Grass only where a vertex group called "grass" was painted.
density_from_vertex_group(dist_node, ng, "grass", density=40)
```

For general scattering (random rotation and scale, several source objects) use the `scatter`
helper in `get_guide("environment-art")`.

## Instances and realizing

Instances are cheap: thousands of copies share one mesh. Keep them as instances while you work.
Realize them (the `realize` helper, or Realize Instances in the tree) only when something needs
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
  `realize`, then export with `use_mesh_modifiers=True` (`get_guide("unreal-engine")`), or apply
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
