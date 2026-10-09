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
   (`roxy.add_layer` below with a large-scale noise texture as the mask, scale 1-3).
3. Add grime and dust masks; their variation hides the repeat.

## Displacement

Imported Poly Haven materials come with a Displacement node set to Scale 0.1 (10 cm), which is
far too strong for most surfaces and does nothing without geometry to move. For real height
(cobbles, bricks, bark) in Cycles: subdivide the mesh enough (Subdivision modifier, or adaptive
subdivision), set the Displacement node's Scale to the texture's real height range (1-5 cm for
bricks and stones, 2-5 mm for wood grain and plaster), and keep `mat.displacement_method = "BOTH"`.
For small detail, or in EEVEE, the normal map is enough: unlink the displacement.

## Not new: weather everything by default

Real things are rarely new. Unless the subject is meant to be new (a showroom, a product shot),
every surface gets a light history on top of its material: `roxy.weather(obj, age="used")` after
the materials are on. It keeps whatever the material already is - Poly Haven and ambientCG image
textures included - and layers over it: uneven colour and roughness in large soft patches, dirt
in corners and seams, dirt and kick marks near the floor, lighter scuffs on edges and corners,
and dust on top. Ages:

| age | For |
|---|---|
| `"new"` | only slight unevenness: showrooms, packaging, things just installed |
| `"used"` (default) | anything in daily life: homes, schools, offices, shops, streets |
| `"old"` | years of use: old houses, public buildings, worn-in tools |
| `"neglected"` | abandoned, derelict, outdoors without care |

Each material is aged once (shared materials too); the strengths follow the object's size. Then
add what is specific to the object with the layers below - handles polished by hands, rust where
paint chipped, water streaks under a sill - which is what makes it this object's history rather
than a filter. Look close up in rendered mode: it should read as used, not dirty. Game export
needs the result baked to textures: `uv_bake` (below).

## Substance 3D Painter: painted wear for hero and game assets

When the Roxy Substance 3D Painter MCP is connected, texture the hero asset and anything a game
shows up close there: its wear follows baked curvature and AO, can be placed where this object is
really touched, hit and rained on, and exports straight to Unreal's textures. `roxy.weather` stays
the quick way for background and set dressing, and for Blender-only renders.

1. Finish the model and its materials' split: one material per texture set (body, metal fittings,
   glass...), named for what they are.
2. `painter_handoff(action="export", name=..., target="unreal" or "blender")` unwraps each
   material's objects into an "Unwrap" UV map and writes the FBX; its reply lists the Painter MCP
   steps: create_project, bake_mesh_maps, a base material and the wear layers per texture set,
   export_textures, save_project.
3. In Painter, age it as the story needs (the table under "How much" below): used by default.
   Look with frame_camera and screenshot from several sides.
4. `painter_handoff(action="import", name=..., textures_dir=...)` rebuilds the Blender materials
   from the exported textures. For Unreal, import the same textures there (sRGB off for normal and
   ORM) - they replace the Blender materials, which don't transfer.

Don't `roxy.weather` an asset that went through Painter: its wear is in the textures.

## Layering wear, rust, dirt and dust

These helpers work on any material built of Principled BSDFs, including the ones `import_asset`
creates from Poly Haven and ambientCG textures:

- `roxy.add_layer(base, other, mask)` blends a second material (a Poly Haven rust, a dirty version of
  the same surface, bare metal under paint) over the base where the mask is 1. Import the second
  texture without `apply_to`, use it as `other`, then delete it from `bpy.data.materials` if you
  don't need it on its own.
- `roxy.grime(base, mask)` darkens and roughens without a second texture: dirt, soot, water stains.
  Pass a light colour (0.4, 0.38, 0.35) and roughness 1.0 for dust.
- Masks: `roxy.edge_wear_mask` (convex edges and corners), `roxy.crevice_dirt_mask` (corners, seams,
  contact areas), `roxy.top_dust_mask` (upward faces). Each is broken up by noise so wear comes in
  patches, not lines. Tune `width` / `distance` to the object's size and `scale` to the size of
  the patches.

The addon provides these as `roxy.<name>` inside execute_blender_code (addon protocol 18+), so call them directly - don't paste or redefine them. If `roxy` is undefined, the Blender addon is outdated: get_addon_status says how to update it. `roxy.weather` needs protocol 23.

- `roxy.weather(obj, age="used", seed=0)` - Age every material on obj over what it already is (textures included): uneven colour and roughness, dirt in corners and near the floor, scuffed edges, dust on top. Returns the materials changed.
- `roxy.edge_wear_mask(mat, width=0.01, breakup=0.7, scale=40)` - Convex edges and corners: rays cast inside the mesh hit nearby walls there.
- `roxy.crevice_dirt_mask(mat, distance=0.1, breakup=0.5, scale=15)` - Corners, seams and contact areas, where dirt collects.
- `roxy.top_dust_mask(mat, breakup=0.4, scale=8)` - Upward-facing surfaces, where dust settles.
- `roxy.add_layer(dst, src, fac, scale=1.0)` - Blend material src (a Poly Haven rust, say) over dst where fac is 1; stacks when repeated.
- `roxy.grime(mat, fac, color=(0.05, 0.04, 0.03, 1.0), roughness=0.9, blend="MIX")` - Darken and roughen the base material where fac is 1, without a second texture; its textures stay underneath, and blend="MULTIPLY" tints them instead of covering them.

Typical stacks:

| Object | Layers |
|---|---|
| Painted metal (machinery, lockers, railings) | base paint; `roxy.add_layer` bare or rusty metal on `roxy.edge_wear_mask`; `roxy.grime` on `roxy.crevice_dirt_mask` |
| Wooden furniture | base wood; `roxy.grime` (darker, lower roughness = polished by hands) on edges of handles and tops; `roxy.top_dust_mask` dust if unused |
| Concrete, plaster, stone walls | base; second texture of the same material with large-scale noise; `roxy.grime` streaks near the ground on `roxy.crevice_dirt_mask` |
| Floors | base; `roxy.grime` in corners and along walls; worn, smoother paths where people walk (lower roughness) |

The AO-based masks are exact in Cycles. EEVEE approximates ambient occlusion from the screen,
so masks shift as the camera moves; for EEVEE renders or game export, bake the finished material
to textures: `uv_bake(action="unwrap")`, then `uv_bake(action="bake", target="unreal" or
"blender")` writes BaseColor, Normal and Roughness/Metallic (or packed ORM) per texture set.

## Decals

Labels, warning signs, stickers, posters, cracks, stains and graffiti make a surface specific.
A decal is a plane just in front of the surface (1 mm off, or a Shrinkwrap with a small offset)
with an image texture whose alpha drives the BSDF's `Alpha`, `mat.surface_render_method =
"DITHERED"` for EEVEE, and no shadow casting. Text on decals is Japanese in a Japanese setting.

## How much

Age the surface for the story and keep it consistent across the frame:

| State | Wear | Dirt | Dust |
|---|---|---|---|
| New, showroom (`"new"`) | none; bevels only | none | none |
| In use - the default (`"used"`) | handles, edges, floor paths | corners, around switches and handles | tops of high shelves |
| Old, well kept | edges softened everywhere | light, in seams | light |
| Neglected, abandoned | heavy, bare material showing | heavy, streaks from water | thick on every top |

Stop before it looks dirty everywhere at the same strength: real wear concentrates where things
are touched, hit and rained on.
