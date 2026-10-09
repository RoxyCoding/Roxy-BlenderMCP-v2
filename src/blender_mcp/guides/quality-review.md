---
title: Quality review
summary: Reviewing your own work against a AAA bar - a scored checklist, the review loop with look and checkpoints, the usual tells of a CG-looking scene and how to fix each, and comparing against reference.
---

# Quality review

Run this before calling any scene, asset or shot done, and whenever the user says it looks
"cheap", "fake", "flat" or "CG". The bar is a AAA game or film frame: every surface has a
history, every light has a reason, and nothing gives away that it was assembled from primitives.

## The loop

1. `checkpoint(action="save", label="before review pass N")`.
2. Look properly: `look(mode="camera", shading="rendered")` for the shot, plus
   `look(mode="angles", shading="rendered")` on the hero object(s). A solid-shaded viewport hides
   every material and lighting problem.
3. Score each item below 0-2 (0 missing, 1 present but weak, 2 convincing). Write the scores
   down in your reply so the user can follow.
4. Fix the lowest-scoring item that is cheapest to fix, one change at a time, and look again.
   Don't fix several things blind and look once.
5. If a fix made it worse, `checkpoint(action="restore", ...)`.
6. Stop when nothing scores 0 and the hero items score 2, or when the user is happy. Report what
   is still weak rather than claiming it is perfect.

## The checklist

**Form**
- Silhouette: the main shapes read clearly against the background; the subject is recognisable
  as a black shape.
- Scale: every object is real-world size relative to its neighbours (doors, chairs, people);
  check against known sizes, by default Japanese ones (`get_guide("japanese-design")`).
- Identity: it reads as the specific real thing, not something like it; every identifying
  feature in its plan is visible and right close up.
- Form: no part is a bare primitive (box, cylinder, sphere, cone) unless the real thing is
  exactly that shape; parts taper, curve, crown and round where the real thing does, round
  things have their side profile, organic things their real silhouette, and one-piece parts are
  one body. `model_plan(action="verify")` lists the bare primitives left.
- Edges: no perfectly sharp corners on manufactured or worn objects; bevels catch highlights
  (`get_guide("surface-realism")`).
- Contact: everything rests on something; no floating, no intersecting; contact shadows visible.
  `model_plan(action="verify")` passes with no near-miss warnings left unexplained.
- Joints: every part is fixed the way the real thing is (hinge, bracket, bolt into its plate,
  pipe into a fitting); faces meant to be flush are flush. Check each joint close up.

**Surface**
- Material variation: no large area of one flat colour or uniform roughness.
- Wear and history: edges worn, crevices dirty, horizontal surfaces dusty, wet areas stained,
  appropriate to the object's age and use.
- Texture scale: texel density consistent between neighbours; no visibly repeating tiles on large
  surfaces; no stretched UVs.
- Physically plausible values: albedo between ~0.02 and 0.9 linear, metallic 0 or 1, glass with
  transmission not alpha (`get_guide("materials")`).

**Light**
- Direction: a clear key light shapes the objects; shadows tell you where it comes from.
- Contrast: the frame has real darks and real brights, not mid-grey everywhere, without clipped
  whites or crushed blacks over large areas.
- Colour: warm against cool (sunlight and sky, lamp and window); one dominant temperature.
- Atmosphere: depth through haze, fog or light shafts where the setting has air in it
  (`get_guide("lighting-and-rendering")`).

**Composition and storytelling**
- Focal point: the eye lands on the subject first (light, contrast, sharpness, framing).
- Density: big, medium and small objects in clusters, not evenly spaced; no empty floors or
  shelves unless emptiness is the point (`get_guide("environment-art")`).
- Story: the place looks used - something left out, something out of place, signs of who is there.
- Consistency: one art style, one era, one region, one level of detail across the frame.

**Finish**
- Camera: a deliberate focal length and height; verticals straight in architecture.
- Lens and grade: subtle bloom on bright sources, depth of field where it helps, a colour grade
  that unifies the frame, a slight vignette. All subtle.

## The usual tells, and their fixes

| Tell | Fix |
|---|---|
| Razor-sharp edges, no highlights on corners | Bevel modifier (2-3 segments) + Weighted Normal |
| Only "something like it" - a generic version of the subject | Name the specific kind and its identifying features (modeling guide, step 1), model each, check each close up |
| A cylinder bottle, sphere head, cone tree, cube rock | Draw the real side profile (`roxy.lathe`), shape the real silhouette, or use a library asset |
| Looks like boxes stuck together | Give each part its real form: taper (`roxy.rounded_box(top=/bottom=)`), real edge radius, crown or curve (`roxy.loft`), profiles (`roxy.extrude_profile`, `roxy.sweep`); `roxy.fuse` what is one piece in reality (modeling guide, step 4) |
| Plastic look everywhere | Vary roughness with a texture or noise; real materials from Poly Haven |
| One flat colour per object | Poly Haven texture, or noise/AO-driven colour variation |
| Spotless surfaces | Edge wear, crevice dirt, dust layers (surface-realism) |
| Flat, shadowless light | One strong key with real shadows; reduce the ambient/HDRI strength |
| Everything the same brightness | Lower fill, add darks; let parts of the frame fall into shadow |
| Clean empty void behind the subject | Background geometry, fog, an HDRI with matching content |
| Grid-perfect placement | Random small rotation and offset; clusters instead of rows |
| Tiled texture repeating on a floor | Larger texture (`min_size_m`), rotate/offset per object, blend a second texture with noise |
| Everything perfectly sharp | Depth of field on close shots |
| Objects floating 1 cm above the floor | Snap to the ground from the bounding box; check a low side view |
| A lid, shelf or fitting hovering beside what should hold it | Add the hinge, bracket or fixing; sink bolts into their plate; verify again |
| Panels a few mm proud of or short of their frame | Line the faces up exactly, or make the step a clear 10 mm+ |
| Mixed styles (low-poly next to photoscan) | Replace the odd ones out |
| Foreign details in a Japanese setting | Sockets, signs, plates, text, steering side (japanese-design) |

## Reference

When the user gives a reference image, compare side by side: show it with `look(image=path)`,
then the render, and list differences in light direction, contrast, colour, density and scale
before changing anything. Without a reference, describe the target in one sentence first ("a
lived-in Tokyo apartment at dusk, warm lamps against a blue window") and judge against that.

## Honesty

Say what you could not reach. Organic sculpted detail and hand-painted textures depend on the
source assets; if the best library or generated asset is the limit, say so and suggest what would
improve it (a better asset, a reference, a texture the user supplies).
