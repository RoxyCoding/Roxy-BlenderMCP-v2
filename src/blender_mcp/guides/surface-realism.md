---
title: Surface realism
summary: Making surfaces read as real at a AAA bar - bevels and weighted normals, choosing and scaling Poly Haven textures, breaking up tiling, displacement, layering wear, rust, dirt and dust over Poly Haven materials with tested helper code, decals, and how much ageing to apply.
---

# Surface realism

Real surfaces have a history: they were made (edges rounded, panels seamed), used (edges worn,
handles polished), and left (dust on top, dirt in corners, stains where water runs). A CG surface
has none of it. Build that history in layers, and use Poly Haven's scanned textures as the base
wherever you can: they carry real colour and roughness variation that is hard to fake.

## Edges

No manufactured or worn object has a perfectly sharp edge; the rounded edge is what catches the
highlight that makes a shape read as solid. On every hard-surface object:

```python
import math
bev = obj.modifiers.new("Bevel", "BEVEL")
bev.width = 0.003                     # metres: 2-5 mm on furniture and props, 1-2 cm on buildings
bev.segments = 3
bev.limit_method = "ANGLE"; bev.angle_limit = math.radians(30)
bev.harden_normals = True
for p in obj.data.polygons:
    p.use_smooth = True
wn = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL"); wn.keep_sharp = True
```

Raise `width` for soft or worn objects, lower it for crisp machined parts; never 0. Check the
highlights with `look(shading="rendered")` close up.

## Choosing Poly Haven and ambientCG textures

- Two CC0 sources build ready PBR materials: Poly Haven (`source="polyhaven"`, `asset_type=
  "textures"`) and ambientCG (`source="ambientcg"`, about 2000 materials, including Japanese
  surfaces such as tatami). Search Poly Haven first; ambientCG when it has nothing fitting.
  ambientCG matches every word of the query, so search with one or two words ("tatami",
  "plaster", "asphalt"), and use `previews` to compare.
- Search by what the surface is and how old it is: "painted metal worn", "concrete floor
  stained", "rusty metal", "wood planks old". Use `previews=4` to see before importing.
- Large surfaces (floors, walls, ground, roads): `min_size_m=2` or more, so a single tile covers
  metres and repetition doesn't show.
- Resolution by screen size: 4k for the hero object and anything near the camera, 2k for the
  midground, 1k for the background. Don't put 8k on everything; it slows the scene for nothing.
- Keep texel density even: neighbours seen at the same distance should show similar texture
  detail. A 4k crate next to a 1k wall reads wrong.
- Match the setting: Japanese materials for Japanese places (tatami, plaster, tiles, painted
  steel, asphalt with Japanese markings) unless the user names another region.

## Breaking up tiling

Even a large texture repeats on a long floor or wall. Fix it in one of these ways, cheapest first:

1. Vary each object's Mapping node: random rotation (`inputs["Rotation"]`) and offset
   (`inputs["Location"]`) per wall or floor piece.
2. Blend a second Poly Haven texture of the same material over it with a large-scale noise mask
   (`add_layer` below with a `_breakup`-style mask at scale 1-3).
3. Add grime and dust masks; their variation hides the repeat.

## Displacement

Imported Poly Haven materials come with a Displacement node set to Scale 0.1 (10 cm), which is
far too strong for most surfaces and does nothing without geometry to move. For real height
(cobbles, bricks, bark) in Cycles: subdivide the mesh enough (Subdivision modifier, or adaptive
subdivision), set the Displacement node's Scale to the texture's real height range (1-5 cm for
bricks and stones, 2-5 mm for wood grain and plaster), and keep `mat.displacement_method = "BOTH"`.
For small detail, or in EEVEE, the normal map is enough: unlink the displacement.

## Layering wear, rust, dirt and dust

These helpers work on any material built of Principled BSDFs, including the ones `import_asset`
creates from Poly Haven textures. Paste them into a script once, then:

- `add_layer(base, other, mask)` blends a second material (a Poly Haven rust, a dirty version of
  the same surface, bare metal under paint) over the base where the mask is 1. Import the second
  texture without `apply_to`, use it as `other`, then delete it from `bpy.data.materials` if you
  don't need it on its own.
- `grime(base, mask)` darkens and roughens without a second texture: dirt, soot, water stains.
  Pass a light colour (0.4, 0.38, 0.35) and roughness 1.0 for dust.
- Masks: `edge_wear_mask` (convex edges and corners), `crevice_dirt_mask` (corners, seams,
  contact areas), `top_dust_mask` (upward faces). Each is broken up by noise so wear comes in
  patches, not lines. Tune `width` / `distance` to the object's size and `scale` to the size of
  the patches.

```python
def _breakup(nt, mask, scale, amount):
    """mask * noise remapped to (1 - amount)..1, so the mask breaks into patches."""
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale; noise.inputs["Detail"].default_value = 8
    remap = nt.nodes.new("ShaderNodeMapRange")
    remap.inputs["From Min"].default_value = 0.4; remap.inputs["From Max"].default_value = 0.6
    remap.inputs["To Min"].default_value = 1 - amount
    nt.links.new(noise.outputs["Fac"], remap.inputs["Value"])
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.use_clamp = True
    nt.links.new(mask, mul.inputs[0]); nt.links.new(remap.outputs["Result"], mul.inputs[1])
    return mul.outputs["Value"]

def _ramp(nt, value, low, high):
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = low; ramp.color_ramp.elements[1].position = high
    nt.links.new(value, ramp.inputs["Fac"])
    return ramp.outputs["Color"]

def _invert(nt, value):
    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    nt.links.new(value, inv.inputs[1])
    return inv.outputs["Value"]

def edge_wear_mask(mat, width=0.01, breakup=0.7, scale=40):
    """Convex edges and corners: rays cast inside the mesh hit nearby walls there."""
    nt = mat.node_tree
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion"); ao.inside = True; ao.only_local = True
    ao.inputs["Distance"].default_value = width
    return _breakup(nt, _ramp(nt, _invert(nt, ao.outputs["AO"]), 0.3, 0.6), scale, breakup)

def crevice_dirt_mask(mat, distance=0.1, breakup=0.5, scale=15):
    """Corners, seams and contact areas, where dirt collects."""
    nt = mat.node_tree
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion"); ao.inputs["Distance"].default_value = distance
    return _breakup(nt, _ramp(nt, _invert(nt, ao.outputs["AO"]), 0.2, 0.7), scale, breakup)

def top_dust_mask(mat, breakup=0.4, scale=8):
    """Upward-facing surfaces, where dust settles."""
    nt = mat.node_tree
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    xyz = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], xyz.inputs["Vector"])
    return _breakup(nt, _ramp(nt, xyz.outputs["Z"], 0.6, 0.95), scale, breakup)

def _surface(nt):
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output)
    return out, out.inputs["Surface"].links[0].from_socket

def add_layer(dst, src, fac, scale=1.0):
    """Blend material src (e.g. a Poly Haven rust) over dst where fac is 1. Stacks when repeated."""
    nt = dst.node_tree
    out, below = _surface(nt)
    src_bsdf = next(n for n in src.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (scale, scale, scale)
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])

    def image(img):
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img
        nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        return t.outputs["Color"]

    for i, inp in enumerate(src_bsdf.inputs):
        if not inp.is_linked:
            try:
                bsdf.inputs[i].default_value = inp.default_value
            except (AttributeError, TypeError, ValueError):
                pass
            continue
        node = inp.links[0].from_node
        if node.type == "TEX_IMAGE":
            nt.links.new(image(node.image), bsdf.inputs[i])
        elif node.type == "NORMAL_MAP" and node.inputs["Color"].is_linked:
            nm = nt.nodes.new("ShaderNodeNormalMap")
            nt.links.new(image(node.inputs["Color"].links[0].from_node.image), nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], bsdf.inputs[i])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fac, mix.inputs[0]); nt.links.new(below, mix.inputs[1]); nt.links.new(bsdf.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mix

def grime(mat, fac, color=(0.05, 0.04, 0.03, 1.0), roughness=0.9):
    """Darken and roughen the base material where fac is 1, without a second texture."""
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    for name, value, kind in (("Base Color", color, "RGBA"), ("Roughness", roughness, "FLOAT")):
        target = bsdf.inputs[name]
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = kind
        ins = [s for s in mix.inputs if s.enabled]          # Factor, A, B for this data type
        nt.links.new(fac, ins[0])
        if target.is_linked:
            nt.links.new(target.links[0].from_socket, ins[1])
        else:
            ins[1].default_value = target.default_value
        ins[2].default_value = value
        nt.links.new(next(s for s in mix.outputs if s.enabled), target)
```

Typical stacks:

| Object | Layers |
|---|---|
| Painted metal (machinery, lockers, railings) | base paint; `add_layer` bare or rusty metal on `edge_wear_mask`; `grime` on `crevice_dirt_mask` |
| Wooden furniture | base wood; `grime` (darker, lower roughness = polished by hands) on edges of handles and tops; `top_dust_mask` dust if unused |
| Concrete, plaster, stone walls | base; second texture of the same material with large-scale noise; `grime` streaks near the ground on `crevice_dirt_mask` |
| Floors | base; `grime` in corners and along walls; worn, smoother paths where people walk (lower roughness) |

The AO-based masks are exact in Cycles. EEVEE approximates ambient occlusion from
the screen, so masks shift as the camera moves; for EEVEE renders or game export, bake the
finished material to textures (`get_guide("retopology")`, Bake detail back, with `type="DIFFUSE"`
and `type="ROUGHNESS"`).

## Decals

Labels, warning signs, stickers, posters, cracks, stains and graffiti make a surface specific.
A decal is a plane just in front of the surface (1 mm off, or a Shrinkwrap with a small offset)
with an image texture whose alpha drives the BSDF's `Alpha`, `mat.surface_render_method =
"DITHERED"` for EEVEE, and no shadow casting. Text on decals is Japanese in a Japanese setting.

## How much

Age the surface for the story and keep it consistent across the frame:

| State | Wear | Dirt | Dust |
|---|---|---|---|
| New, showroom | none; bevels only | none | none |
| In use (homes, offices, shops) | handles, edges, floor paths | corners, around switches and handles | tops of high shelves |
| Old, well kept | edges softened everywhere | light, in seams | light |
| Neglected, abandoned | heavy, bare material showing | heavy, streaks from water | thick on every top |

Stop before it looks dirty everywhere at the same strength: real wear concentrates where things
are touched, hit and rained on.
