---
title: Lighting and rendering
summary: Cinematic lighting at a AAA bar - designing light with key, fill and rim, contrast and colour temperature, time-of-day recipes with Poly Haven HDRIs, atmosphere (volumetrics, fog, light shafts), light linking, compositor finishing (bloom, lens, grade, vignette) in Blender 5.x, and final render settings.
---

# Lighting and rendering

Lighting is where a scene goes from assembled to photographed. Design it like a cinematographer:
decide where the light comes from and what it should say before placing any lamp. Basic values,
colour management and render settings are in `get_guide("scene")`; this guide is the craft on top.

## Design the light

- **One motivated key.** Every main light has a source the viewer would believe: the sun, a
  window, a lamp, a screen. Place the key first, alone, and get the shapes and shadows right.
- **Contrast ratio.** Key against fill sets the mood: 2:1 bright and friendly (products, daytime
  interiors), 4:1 dramatic, 8:1 or more for night and suspense. Start with no fill at all and add
  only as much as the shadows need.
- **Rim / back light** separates the subject from the background: behind and above, often as
  strong as the key, narrow.
- **Colour temperature contrast.** Warm key against cool fill, or the reverse: sunlight against
  blue sky, tungsten lamps against a blue dusk window, neon against a dark street. One temperature
  should dominate.
- **Shape the darkness.** Leave parts of the frame in shadow. Light the subject, not the room.
- **Practicals.** Lamps, screens, signs and windows visible in frame should actually emit light
  (emission plus a real light near them) and be the motivation for the lights you add.

## Time-of-day recipes

Start from a Poly Haven HDRI that matches (`search_assets(source="polyhaven", asset_type="hdris",
query=...)`, e.g. "sunset", "overcast", "night city", "indoor"; `previews` to check), then add the
key light the HDRI implies, aligned with the sun or window in it. Rotate the HDRI (the Mapping
node's Z rotation in the world's node tree) so its sun sits where the key comes from.

| Time | HDRI strength | Key | Notes |
|---|---|---|---|
| Midday, clear | 0.8-1.2 | Sun 4-5, high, small angle | Hard shadows; can look flat - prefer a lower sun for beauty shots |
| Golden hour | 0.5-1.0 | Sun 2-4, low (5-15° up), warm 3000-4000 K | Long shadows, rim light on everything facing the sun |
| Blue hour, dusk | 0.3-0.6 | Practicals as key: windows, street lamps 2700-3000 K | Cool ambient against warm lamps; the classic city look |
| Overcast | 0.8-1.5 | None, or sun 0.5 with angle 10-20° | Soft, low contrast; add contrast with grading and darker surroundings |
| Night, urban | 0.05-0.2 | Street lights, signs, shop fronts, vending machines | Pools of light with darkness between; wet surfaces double the light |
| Interior, day | 0.5-1.0 (outside) | Area lights in the windows, the size of the window | Exposure for the interior; windows may blow out a little, as in photos |
| Interior, night | 0.05 | Ceiling and lamp practicals | Warm, high contrast, light falls off across the room |

## Atmosphere

Air between the camera and the background is what gives depth.

- **Light shafts and haze (Cycles and EEVEE):** a box enclosing the scene with a material that has
  only a Principled Volume (`ShaderNodeVolumePrincipled`) on the Material Output's `Volume`, no
  surface, `Density` 0.005-0.05 (interiors with dust in sunbeams 0.02-0.1). Light shafts appear
  where a strong, small light (the sun, a spot) passes through gaps.
- **Distance fog:** a lower density over a large box, or the world's `Volume` socket for open
  landscapes. Fog colour close to the sky colour.
- **EEVEE volumetrics** are controlled by `scene.eevee.volumetric_start` / `volumetric_end` (set
  them to the scene's depth) and `volumetric_tile_size` (smaller = sharper shafts, slower).
- Volumes are expensive: preview at low samples, and keep density low; a little goes a long way.

## Light linking

Light linking (Cycles, and EEVEE in recent versions) lets a light affect only some objects: a rim
light on the character but not the wall behind, an eye light, a product highlight.

```python
coll = bpy.data.collections.new("RimReceivers"); coll.objects.link(character)
rim_light.light_linking.receiver_collection = coll      # only these objects receive it
# rim_light.light_linking.blocker_collection = ...      # only these cast its shadow
```

## Finishing in the compositor (Blender 5.x)

Blender 5.0 moved compositing to a node group: `scene.node_tree` and the Composite node are gone.
Build a Compositor node tree, give it an `Image` output, and assign it to the scene. All settings
(even the Glare type) are input sockets:

```python
scene = bpy.context.scene
ng = bpy.data.node_groups.new("Finish", "CompositorNodeTree")
ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
n, l = ng.nodes, ng.links
rl = n.new("CompositorNodeRLayers"); out = n.new("NodeGroupOutput")
glare = n.new("CompositorNodeGlare")
glare.inputs["Type"].default_value = "Bloom"      # also Fog Glow, Streaks, Ghosts, Simple Star...
glare.inputs["Strength"].default_value = 0.2
lens = n.new("CompositorNodeLensdist")
lens.inputs["Dispersion"].default_value = 0.005   # faint chromatic aberration at the edges
grade = n.new("CompositorNodeColorBalance")       # lift / gamma / gain; print its inputs to find them
l.new(rl.outputs["Image"], glare.inputs["Image"]); l.new(glare.outputs["Image"], lens.inputs["Image"])
l.new(lens.outputs["Image"], grade.inputs["Image"]); l.new(grade.outputs["Image"], out.inputs["Image"])
scene.compositing_node_group = ng
```

On Blender before 5.0 the same nodes go in `scene.node_tree` after `scene.use_nodes = True`, ending
in a `CompositorNodeComposite`. Check `hasattr(scene, "compositing_node_group")` to choose.

Keep every effect subtle: bloom only on genuinely bright sources, aberration you notice only at
the edges, a vignette (Ellipse Mask, blurred, multiplied over the image) that darkens corners by
10-20%. A grade should unify the frame (slightly warm highlights and cool shadows is a safe,
filmic choice), not restyle it. The Color Balance node has same-named float and colour inputs;
pick the colour one: `next(s for s in grade.inputs if s.name == "Gain" and s.type == "RGBA")`.

The compositor runs on the final render, not in `look`'s viewport shading: render, then check
with `look(image="Render Result")`.

## Final render

1. `checkpoint(action="save", label="before final render")`.
2. Settings from `get_guide("scene")` (AgX, samples, denoising, resolution 100%).
3. Motion: `scene.render.use_motion_blur = True` for animation and fast objects;
   `motion_blur_shutter` 0.5 (a 180° shutter) looks like film.
4. Depth of field on close and product shots (`get_guide("scene")`, Camera).
5. Render (`bpy.ops.render.render(write_still=True)` with `scene.render.filepath` set) and look at
   the result with `look(image="Render Result")`. Review it with `get_guide("quality-review")`
   before showing it as final.
6. For compositing elsewhere (After Effects), output OpenEXR Multilayer with the passes you need
   (`view_layer.use_pass_z`, `use_pass_mist`, `use_pass_normal`, and `use_pass_cryptomatte_object`
   / `use_pass_cryptomatte_material` for masks).
