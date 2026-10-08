---
title: Materials and texturing
summary: Node-based materials that survive version and language changes, believable values, normal maps, transparency, displacement, emission, subsurface, Poly Haven textures, tiling, procedural looks and packing.
---

# Materials and texturing

## Creating materials

```python
mat = bpy.data.materials.new("Brushed Steel")
mat.use_nodes = True   # no-op in 5.0+, where it's always on
bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
bsdf.inputs["Base Color"].default_value = (0.6, 0.6, 0.62, 1)
bsdf.inputs["Metallic"].default_value = 1.0
bsdf.inputs["Roughness"].default_value = 0.35
obj.data.materials.clear(); obj.data.materials.append(mat)
```

Sockets renamed in 4.0; resolve them defensively (`inputs.get("Emission Color") or inputs.get("Emission")`).

## Believable values

| Material | Base colour (linear) | Metallic | Roughness |
|---|---|---|---|
| Painted wall | 0.5–0.7 grey | 0 | 0.8–0.9 |
| Wood (varnished) | textured | 0 | 0.3–0.5 |
| Plastic | any | 0 | 0.3–0.6 |
| Polished metal | 0.9 | 1 | 0.05–0.2 |
| Rubber | 0.02–0.05 | 0 | 0.8 |
| Glass | white | 0 | 0; Transmission Weight 1, IOR 1.5 |
| Water | white | 0 | 0; Transmission Weight 1, IOR 1.33 |
| Skin | textured | 0 | 0.4-0.5; Subsurface Weight 0.1-0.3 |
| Tatami (new / aged) | 0.45 0.5 0.25 / 0.5 0.42 0.25 | 0 | 0.6-0.7 |
| Shoji paper | 0.85 0.83 0.78 | 0 | 0.9; light behind it: Transmission Weight 0.2-0.4 |
| Hinoki / light wood | 0.6 0.45 0.3 | 0 | 0.4-0.6 |

Nothing in nature is pure black (0) or pure white (1) as a base colour. Keep it between ~0.02 and 0.9.

Values are linear. A colour picked as sRGB or hex must be converted: linear = (srgb / 255) ** 2.2
per channel, roughly (`#808080` is about 0.22 linear, not 0.5).

## Normal, bump and displacement

- A normal map image is Non-Color and goes through a Normal Map node into the BSDF's `Normal`:

```python
nt = mat.node_tree
img_node = nt.nodes.new("ShaderNodeTexImage"); img_node.image = img
img.colorspace_settings.name = "Non-Color"
nmap = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(img_node.outputs["Color"], nmap.inputs["Color"])
nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
```

  Plugging the image straight into `Normal` gives wrong shading.
- Bump (`ShaderNodeBump`) fakes small detail from a height or noise texture, also into `Normal`.
- Real displacement moves geometry: Cycles only, with enough subdivision on the mesh, and
  `mat.displacement_method = "DISPLACEMENT"` (or `"BOTH"`). A Displacement node feeds the Material
  Output's `Displacement` socket.

## Transparency, emission, subsurface

- Alpha (leaves, decals, fences): wire the texture's alpha into the BSDF's `Alpha`. In EEVEE set
  `mat.surface_render_method = "DITHERED"` (cheap, sorts correctly) or `"BLENDED"` (soft edges,
  can sort wrongly); this replaced `blend_method` in 4.2.
- Glass and water use Transmission Weight 1, not Alpha. Thin glass panes look better with
  roughness near 0 and no thickness tricks; thick glass needs real geometry.
- Emission: `Emission Color` plus `Emission Strength`. Screens and signs 1-5, neon and LEDs 5-20,
  a lamp's bulb 10-50. Emission adds light in Cycles; in EEVEE it lights only through raytracing
  or bloom, so add a real light next to a glowing lamp.
- Subsurface (skin, wax, marble, leaves, milk): `Subsurface Weight` 0.05-0.3, `Subsurface Radius`
  reddish for skin (1.0, 0.2, 0.1), `Subsurface Scale` in metres about the depth light travels
  (a few mm for skin: 0.005).

## Textures

- Poly Haven textures come as full PBR sets. `import_asset(source="polyhaven", id=...,
  apply_to=["Floor"])` builds the material and applies it in one call.
- Tiling: the import result gives the texture's real-world size. For 0–1 UVs across a surface,
  Mapping node Scale = surface size in metres / texture size in metres. Prefer large-coverage
  textures (`min_size_m` in search) for walls and floors; small ones repeat visibly.
- Objects need UVs. Primitives have them; scripted meshes need `smart_project` or box-projection
  (`Texture Coordinate > Object` into Mapping, and the Image Texture node's projection `BOX`).
- Image textures for roughness, metallic and normal maps must be Non-Color
  (`img.colorspace_settings.name = "Non-Color"`).

## Several materials on one object

Add each to `obj.data.materials`, then set `polygon.material_index` per face (bmesh:
`face.material_index`). Imported models often bring many duplicate materials (`Wood.001`,
`Wood.002`); point slots at one material instead of editing each copy.

## Procedural

Noise, Voronoi and Wave textures through a Color Ramp make variation without images: grunge for
roughness, stains, wood rings. Mixing a little noise into roughness makes any flat material look
less CG. Look each node up before indexing its sockets (see `get_guide("bpy")`).

## Keeping textures with the file

Image textures are linked by path. Before handing the .blend to someone else or another machine,
`bpy.ops.file.pack_all()` embeds them (larger file), or make the paths relative with
`bpy.ops.file.make_paths_relative()` and keep the textures beside the .blend.

## Check it

Material colours only show in Material Preview or Rendered shading:
`look(mode="camera", shading="material")` or `shading="rendered"`. Solid shading shows only the
viewport display colour.
