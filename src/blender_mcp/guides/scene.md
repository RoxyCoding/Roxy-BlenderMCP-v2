---
title: Scene design
summary: Building a believable scene - real-world (by default Japanese) scale and details, grounding, composition, generated vs library assets, lighting values, camera and depth of field, colour management and render settings.
---

# Scene design

## Workflow

1. `get_scene_info` — know what's there and the scene's scale before adding anything. Decide the
   setting's country: Japanese unless the user names or implies another (`get_guide("japanese-design")`).
2. Block out with primitives at real-world size: the layout, the big shapes, the camera.
   `look(mode="camera")` or `look(mode="angles")` to check proportions before spending on assets.
3. Replace blockout pieces with real assets, biggest and most visible first.
4. Light, then set materials, then dress with small props.
5. Judge the image, not your intentions: is anything
   floating, clipping, the wrong size, or hidden from camera?

## Getting assets

- **Poly Haven** (`search_assets(source="polyhaven")`): HDRIs, PBR textures for large surfaces
  (floors, walls, terrain), and generic realistic props. CC0.
- **ambientCG** (`source="ambientcg"`): CC0 PBR materials Poly Haven lacks, including Japanese
  surfaces such as tatami.
- **Sketchfab**: specific real-world things (a named car model, a landmark), and realistic props.
  Check the licence and face count in results.
- **Script it** for simple or procedural geometry: walls, floors, shelves, stairs, fences,
  arrays, scattering (`get_guide("geometry-nodes")`). Import once and duplicate (`obj.copy()`) for
  repeats.

Match the style. Don't mix stylised low-poly props with photoreal scans in one frame.

Library assets are mostly American or European. In a Japanese setting, check each one for what
gives the wrong country away (sockets, signs, text, number plates, steering side, door and
furniture sizes) and replace or edit it, or model the Japanese version yourself.

## After every import

Imported and generated models arrive at arbitrary scale, rotation and origin. The import result
gives `world_bounding_box`; use it:

- Scale to real size from the bounding box, not by eye.
- Put it on the ground: `obj.location.z -= min_z` (with the bounding box min z).
- Rotate it to face the right way; generators usually face -Y or +Y. Check with
  `look(mode="angles", target=[name])`.
- Check it doesn't intersect its neighbours.

## Composition

- Decide the camera early and compose for it; set `scene.camera`, focal length 35–50 mm for
  natural views, 85 mm+ for product shots, 24 mm or wider for interiors.
- Foreground, midground, background. Leave negative space. Rule of thirds for the subject.
- Vary scale and rotation of repeated props slightly; perfect grids read as fake.
- Ground contact sells realism: props sit on surfaces, small things cluster against larger ones.

## Lighting

- Start with an HDRI from Poly Haven for ambient light and reflections; set its strength
  (0.5–1.5), then add a key light (sun or area) for shape and shadows.
- Three-point for products: key, fill at lower power, rim behind.
- Interiors: area lights in windows (portals in Cycles) plus practicals (lamps with emission).
- Check with `look(mode="camera", shading="rendered")`. Blown-out white or pure black areas mean
  exposure or light power is off; fix light power before touching exposure.

Starting values with exposure 0 and AgX, then judge by eye:

| Light | Setting |
|---|---|
| Sun, clear day | Sun `energy` 3-5 (W/m²); `angle` (radians: `math.radians(0.5-1)`) crisp, 5-10° soft |
| Overcast | HDRI only, or sun 0.5-1 with a large angle |
| Room ceiling light | Area light 100-300 W, about 1 m² |
| Desk or bedside lamp | Point or spot 20-60 W, warm (blackbody about 2700-3000 K) |
| Window fill (interior) | Area light the window's size, 50-300 W, pointing in |
| Product key / fill / rim | Area 50-200 W / a third of the key / about the key, behind |

Light colour from temperature: daylight about 5500-6500 K, office fluorescent and LED about
4000-5000 K, Japanese homes often use both warm (電球色, 2700-3000 K) and daylight (昼光色,
6500 K) fittings.

## Camera

- Set `scene.camera`, the focal length (above) and the resolution's aspect before composing.
- Depth of field draws the eye: `cam.data.dof.use_dof = True`, `focus_object` = the subject (or
  `focus_distance`), `aperture_fstop` 1.4-2.8 for a shallow product or portrait look, 5.6-11 for
  landscapes and interiors where everything should be sharp.
- Keep verticals vertical in architecture: camera level (rotation X = 90°), raise it with
  `cam.data.shift_y` instead of tilting.

## Render settings

Read the current engine rather than setting one blindly (see `get_guide("bpy")`).

- **Colour management.** Use AgX (the default since 4.0) for realistic light; Standard only for
  flat graphics, UI-like or toon looks where colours must match exactly. `view_transform` is an
  enum RNA under-reports: read the current value, and assign inside `try/except TypeError`, whose
  message lists the valid names ('Standard', 'AgX', 'Filmic', 'Khronos PBR Neutral', ... in 5.1).
  Adjust brightness with `scene.view_settings.exposure`, not by overdriving lights.
- **Cycles.** `scene.cycles.samples` 64-256 for previews, 512-2048 final; keep
  `use_adaptive_sampling` on and `use_denoising` on. Noise left after denoising usually means too
  few samples in dark or glossy areas, or a light that is too small.
- **EEVEE.** `scene.eevee.taa_render_samples` 64-256; `scene.eevee.use_raytracing = True` for
  reflections and bounced light.
- **Resolution.** `render.resolution_x/y` with `resolution_percentage` 25-50 for tests, 100 final.
  1920x1080 for video, 1080x1920 for vertical (shorts), 3840x2160 for 4K.
- **Output.** PNG for stills, `render.film_transparent = True` for a transparent background;
  OpenEXR Multilayer (`OPEN_EXR_MULTILAYER`) when the image goes on to compositing (After
  Effects, Nuke) with render passes.
- Do quick checks at low samples and resolution with `look(mode="camera", shading="rendered")`;
  render the final only when the user is happy with the preview.
