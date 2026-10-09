---
title: Modeling
summary: Modeling anything yourself with Python - one method for any subject (objects, buildings, vehicles, machines, plants, terrain), working out real dimensions from use, people, standards and materials, decomposing by how things are made, choosing techniques, tested helpers (boxes, cylinders, profiles, lathes, sweeps, panels with openings, steps, cuts, real-scale UVs, assembling), and checking.
---

# Modeling

You model whatever no library has. The same method works for a cup, a chair, a vending machine,
a car, a staircase, a school, a tree or a hillside; what changes is only the facts you feed it.
Build every subject as the real thing it is: made for a purpose, at real size, from parts,
with no razor-sharp edges. Japanese facts unless the user names another region
(`get_guide("japanese-design")`).

## The method

### 1. Understand the subject

Before any geometry, answer in one or two sentences: what is it, who uses it and how, what is it
made of, how was it made (cast, bent, cut from boards, welded, grown, poured, woven), and where
does it stand. Purpose explains form: a chair's seat height comes from legs, a handle's diameter
from hands, a roof's slope from rain, a branch's taper from growth. If unsure what it looks like,
say what you will assume, or ask the user for a reference image.

With a reference image, take an inventory before any geometry: every visible element (body,
fittings, ornaments, soft goods, gems, text), its outline, how it is made, its size measured
against the whole in the image, and its material. That list is the job: each item is modelled
to match, or reported to the user as left out or simplified - never silently dropped.

### 2. Work out the dimensions

Size the whole first, then each part, in metres. Derive sizes rather than guess them:

- **People.** Adult (Japan): height 1.6-1.7 m, eye level 1.5-1.6 m, seat height 0.40-0.43 m,
  table and desk 0.70-0.72 m, counter 0.85-0.90 m, handrail 0.80-0.90 m, comfortable reach up to
  about 1.8-1.9 m, shoulder width 0.45 m, grip 25-40 mm across, a fingertip button about 10-15 mm,
  doorway clear width 0.75-0.80 m.
- **Standards and law.** Many sizes are fixed (`get_guide("japanese-design")`: JIS, the Building
  Standards Act, road rules): stair risers and treads, ceiling heights, road widths, sign sizes,
  paper sizes, plug shapes, vehicle classes. Use the rule for the region.
- **Materials.** Thickness and spans come from what the part is made of: sheet steel 0.8-2 mm,
  plywood and boards 12-30 mm, glass 3-12 mm, interior walls 100-150 mm, exterior walls
  150-250 mm, concrete slabs 150-250 mm, timber posts 105-120 mm square, steel tubes 20-60 mm.
- **Function and fit.** Parts that work together set each other's size: a drawer fits its
  carcass with 2-3 mm gaps, a lid its box, a wheel its arch, a door its frame.
- **Known products.** When the subject is a common product (a fridge, a bicycle, a kei car),
  use its typical real dimensions; state that they are approximate.

Write the dimensions down in your reply before modelling; they are the plan.

### 3. Decompose the way it was made

Break the subject into the parts it is built from, from large to small:

| Level | Examples |
|---|---|
| Structure / body | building frame and floors, car body, appliance casing, furniture carcass, trunk |
| Major parts | walls and roof, doors and windows, wheels and seats, shelves and drawers, branches |
| Fittings | handles, hinges, lights, switches, vents, mirrors, signs, fasteners, leaves |
| Surface detail | seams, panel gaps, labels, grilles, stitching, bark ridges (geometry or texture) |

Each part is its own object named `<Subject>_<Part>`, so it can be checked, textured and changed
separately, and the subject is assembled from them (`roxy.assemble`).

### 4. Choose a technique per part

| Shape | Technique |
|---|---|
| Boards, slabs, casings, boxes | `roxy.box` |
| Boards and walls with holes (doors, windows, vents, displays) | `roxy.panel_with_openings`, or `roxy.cut` |
| Legs, poles, posts, pipes, knobs | `roxy.cylinder` |
| Round things turned on an axis (bottles, cups, vases, lamps, columns, wheels) | `roxy.lathe` from a side profile |
| Anything with a custom outline (mouldings, brackets, frames, roofs, signs, rail sections) | `roxy.extrude_profile` |
| Members along a path (handrails, pipes, frames, cables, bent tubes) | `roxy.sweep` |
| Stairs, bleachers, stepped bases | `roxy.steps` |
| Repeats (slats, shelves, tiles, lattices, window rows, fence posts) | Array modifier, or `get_guide("geometry-nodes")` |
| Symmetric subjects (vehicles, furniture, faces) | model one half, Mirror modifier |
| Soft and organic shapes (cushions, bodies, rocks, car body panels) | a low box or profile with Subdivision Surface and a few supporting edge loops |
| Many small scattered things (stones, leaves, debris, grass) | scatter (`get_guide("environment-art")`) |
| Ground and terrain | subdivided plane with Displace (environment-art) |

### 5. Write the plan and check it

Steps 1-4 become a plan: the subject's name, purpose and overall size, and every structural part
with its shape, size, position (`at`, the bottom centre of its box) and what holds it up
(`rests_on`: the parts it sits on, hangs from or is fixed to, or "ground"). Submit it with
`model_plan(action="check", plan=...)` and fix every error until it passes. The check catches
what a misunderstood structure looks like: parts that float, supports that don't touch, chains
that never reach the ground, parts outside the whole, two parts in one place.

Plan the structure and major parts, not every screw: detail comes after and doesn't need a plan.
Parts no box or cylinder describes (a lathe-turned leg, a curved backrest) are `"shape": "custom"`
with `"how"` naming the helper you will use; give them the box they occupy.

For a subject the user will judge closely (the hero object, a whole building), show the plan's
parts and sizes to the user before building.

### 6. Build from the plan, then add detail

`model_plan(action="build", name=...)` builds every box and cylinder part under one empty called
the subject's name, each named `<Name>_<Part>`, and stores the plan on it. Make the custom parts
yourself with the same naming, `parent=` the empty and `location=` their `at`. Then add fittings
and detail. `look(mode="angles", target=["<Subject>"])` after each level - fixing proportions
early is cheap, fixing them after detail is not. Save a checkpoint before anything hard to undo
(cuts, applying modifiers, joining).

When the build is done, `model_plan(action="verify", name=...)` compares it with the plan: every
part present, at its planned size and place, touching its supports and grounded. Fix what it
reports, or change the plan and build again if the plan was wrong. Move or turn the whole subject
only through its empty.

### 7. Surface, light, review

UVs (`roxy.uv_world_box` for hard-surface and architecture), materials (`get_guide("materials")`,
`get_guide("surface-realism")`), then `get_guide("quality-review")`.

## Helpers

Tested on Blender 5.1. They build mesh data directly (no viewport or mode switching), keep object
scale at 1, and put the origin at the bottom centre so `location` is where the part stands.
Most parts get `roxy.finish()`: a small angle-limited bevel and weighted normals.

The addon provides these as `roxy.<name>` inside execute_blender_code (addon protocol 18+), so call them directly - don't paste or redefine them. If `roxy` is undefined, the Blender addon is outdated: get_addon_status says how to update it.

- `roxy.finish(obj, bevel=0.002, segments=2)` - Rounded edges that catch highlights, with clean shading.
- `roxy.box(name, size, location=(0, 0, 0), bevel=0.002, parent=None, collection=None, origin='bottom')` - A box of real size (x, y, z metres) with scale 1.
- `roxy.cylinder(name, radius, depth, location=(0, 0, 0), segments=32, bevel=0.001, parent=None, collection=None, origin='bottom')` - An upright cylinder (legs, poles, pipes, knobs).
- `roxy.extrude_profile(name, points, depth, location=(0, 0, 0), bevel=0.001, parent=None, collection=None)` - Extrude a closed 2D outline [(x, z), ...] in metres along +Y by depth: mouldings, brackets, frames, signs, anything with a custom silhouette.
- `roxy.cut(obj, cutter)` - Subtract cutter from obj (holes, slots, recesses) and delete the cutter.
- `roxy.uv_world_box(obj, space='world')` - UVs in metres, projected per face along its main axis: a texture with Mapping Scale 1/size tiles at real size on every object built this way, whatever its dimensions.
- `roxy.assemble(name, parts, location=(0, 0, 0), collection=None)` - Group parts under an empty, so the whole object moves, rotates and exports as one.
- `roxy.panel_with_openings(name, size, openings, location=(0, 0, 0), bevel=0.002, parent=None, collection=None)` - A board or wall (width x, thickness y, height z) with rectangular openings, each (x_centre, z_bottom, width, height) in metres from the panel's bottom centre: walls with doors and windows, doors with glazing, appliance fronts, furniture sides, signs.
- `roxy.steps(name, rise, run, width, max_step_rise=0.2, location=(0, 0, 0), bevel=0.002, parent=None, collection=None)` - A flight of steps climbing `rise` over `run` along +Y from `location`, centred across X: stairs, bleachers, stepped plinths.
- `roxy.sweep(name, points, radius=0.02, location=(0, 0, 0), resolution=4, parent=None, collection=None)` - A round member following a path of 3D points in metres: handrails, pipes, frames, cables, bent tubes.
- `roxy.lathe(name, profile, segments=48, location=(0, 0, 0), parent=None, collection=None)` - Spin a side profile [(radius, z), ...] in metres around the Z axis: bottles, cups, bowls, vases, lamps, columns, knobs, wheels (rotate afterwards).

## Examples

These show the method applied; they are not the limit of what it covers.

- **Dining table** (furniture): top 1350 x 800 x 30 mm at 700 mm, four 40 mm legs inset 50 mm,
  aprons under the top.

```python
W, D, H, T, L, IN = 1.35, 0.80, 0.70, 0.03, 0.04, 0.05
top = roxy.box("Table_Top", (W, D, T), (0, 0, H - T), bevel=0.003)
legs = [roxy.box(f"Table_Leg_{i}", (L, L, H - T), (sx * (W / 2 - IN), sy * (D / 2 - IN), 0))
        for i, (sx, sy) in enumerate([(1, 1), (1, -1), (-1, 1), (-1, -1)])]
aprons = [roxy.box("Table_Apron_F", (W - 2 * IN, 0.02, 0.08), (0, -(D / 2 - IN), H - T - 0.08)),
          roxy.box("Table_Apron_B", (W - 2 * IN, 0.02, 0.08), (0, D / 2 - IN, H - T - 0.08))]
for part in (top, *legs, *aprons):
    roxy.uv_world_box(part, space="local")
table = roxy.assemble("Table", [top, *legs, *aprons])
```

- **A room** (architecture): floor slab (`roxy.box`), walls 120 mm thick to the ceiling height
  (2.4 m in homes) with `roxy.panel_with_openings` for a 780 x 2000 mm door and windows with sills at
  900 mm, ceiling slab, skirting (`roxy.extrude_profile`), switches at 1200 mm, sockets at 250 mm.
  `roxy.uv_world_box(space="world")` so plaster and flooring run continuously across pieces.
- **A vending machine** (appliance): casing `roxy.box` about 1000 x 700 x 1830 mm with a
  `roxy.panel_with_openings` front (display window, coin slot, outlet), product dummies arrayed
  behind the window, buttons as small `roxy.cylinder`s, emission for the lit panel.
- **A bicycle** (vehicle/machine): wheels by `roxy.lathe` (tyre profile) rotated upright, frame tubes
  by `roxy.sweep` between the head tube, bottom bracket and axles, seat and handlebar by
  `roxy.extrude_profile` and `roxy.sweep`, mirrored parts where it is symmetric.
- **A stair with handrail** (building element): `roxy.steps` for the rise and run (it chooses the step
  count from the maximum riser), `roxy.sweep` for the handrail at 850 mm above the step nosings.
- **A potted plant** (nature): pot by `roxy.lathe`, soil disc, stems by `roxy.sweep` with small radii, leaves
  as subdivided `roxy.extrude_profile` outlines with a slight bend; or a Poly Haven plant in a modelled pot.

## Detail and geometry

- **Detail where it is seen.** Hero subjects close to the camera get bevels with more segments,
  real gaps between parts (2-3 mm), visible fasteners and seams. Background subjects can be
  simple shapes with good materials.
- **No hairline gaps, no floating.** Parts that touch in reality meet exactly; at most a few
  tenths of a millimetre of overlap where two faces rest on each other.
- **Every joint is a real joint.** Ask of each part how it is fixed, and model that: a lid sits
  on its rim or turns on a hinge the model shows; a shelf hangs from a bracket or sleeve; a bolt
  head sits on its plate with the shank in a hole cut for it; a pipe enters a hole, a flange or a
  fitting; a trim strip lies flush against the face it covers. Something "near" its support is
  floating - fixings are where a model looks careless first.
- **Nothing passes through anything.** Pushing one solid into another and letting the overlap
  stand for the joint is never a joint, even where a third part hides it. Each overlap is a
  question - how is this really made? - with an answer you can model:
  - **Inserted** (pin, shank, stem, tenon, ribbon end): `roxy.cut` the hole or socket first, then
    seat the part in it.
  - **One piece** (an eye pin's shank and loop, a cast setting and its petals, a bent bracket):
    build it as one mesh - `roxy.sweep` one wire, one lathe or profile - not two parts butted
    together. A cylinder end stuck into the side of a ring is the classic fake.
  - **Linked** (chain links, jump rings, a ring through an eye or lug): each ring passes through
    the other's opening with clearance; they never share volume.
  - **Set** (a gem in a bezel or cup, a cap over a gem): the holder is a hollow shell shaped to the
    stone with a small clearance; the stone does not run through the holder or what is under it.
  - **Inlaid or seated** (metal lines in leather, a badge in a panel): cut the groove or recess, or
    rest the part on the surface - don't sink it into the panel.
  - **Resting / layered** (straps over trim, ribbon over a cover, flowers side by side, bow loops
    over the knot): route it over what lies beneath with clearance; neighbours touch, they don't
    interpenetrate. Things that gather (a ribbon in a knot) get narrower, not overlapped.
  `model_plan(action="verify")` and `get_scene_info(root=..., fields=["intersections"])` measure
  how far parts pass into each other; every pair deeper than 0.5 mm is a joint still to be made.
- **Flush or clearly stepped.** Faces that line up in reality line up exactly; a deliberate
  step (a reveal, a lip) is 10 mm or more. A side panel 2-3 mm proud of its post, or a frame a
  few mm short of the casing, reads as a mistake.
- **Polygon budget.** Static subjects for rendering can be dense; for Unreal Engine 5 they can
  stay detailed with Nanite (`get_guide("unreal-engine")`). Deforming subjects need evenly spaced
  quads (`get_guide("retopology")`, `get_guide("rigging")`).
- **Normals.** The helpers recalculate them; after your own bmesh work call
  `bmesh.ops.recalc_face_normals`. Inside-out faces render black or vanish.
- **UVs.** Every part needs UVs before texturing. `roxy.uv_world_box` suits hard-surface subjects and
  architecture; organic shapes need seams and unwrapping (`get_guide("retopology")`, UVs).

## No shortcuts

A shortcut looks finished in a wide shot and wrong to anyone who looks. Each of these is
unfinished work, not a simplification:

- **A primitive standing in for a designed part.** A squashed sphere for a petal, one spiral
  strip for a rose, a flat strip on a polyline for a ribbon, a plain cylinder for a cast
  medallion, a torus for a chain. Build each element from what it is made of: a rose from
  separate cupped petals in layers, a ribbon as fabric (width, thickness, gathered where it is
  tied, cut ends, hanging under gravity), a chain from links, filigree as raised relief with a
  real cross-section, a cast setting as one piece.
- **An outline that only roughly matches.** A pointed arch is not an ellipse; a teardrop is not
  a sphere. Match the silhouette of the reference or the real object before adding detail, and
  compare again after.
- **Sizes and spacing by guess.** Measure every element against the whole (in the reference, or
  from real dimensions) and compute positions from the measured sizes, so neighbours touch or
  clear as intended instead of piling into each other.
- **Soft and loose things that ignore physics.** Fabric, cords, chains, leaves and charms rest on
  what is under them and hang under gravity; no stiff straight runs, no hovering ends.
- **Copies and edits that leave the rest behind.** After deleting, moving, mirroring or
  duplicating a part, deal with what depended on it: leaves of a deleted flower, a strap that
  ended on a moved cover, ornaments a mirror now drives into something.
- **Flat surfaces where the real one has structure.** One colour per part where the reference
  shows inlay, enamel, stitching, page edges, grain or wear (`get_guide("surface-realism")`).
- **"Done" from a distance.** Look at every element close up, at the largest size the viewer
  will see it, and side by side with the reference (`look(image=<reference path>)`, then the
  model from the same angle). Fix what differs, and tell the user what is still simplified.

## Checking

- **Structure:** `model_plan(action="verify", name=...)` after building, after adding detail and
  after any change to the parts. It measures the real surfaces, not bounding boxes: every part,
  detail included, must touch what holds it and connect to the structure. Fix its errors; read
  every near miss and almost-flush warning and either close it or say why it is intended.
- **Joints:** `look(target=[...], distance=...)` close up on every joint - hinges, brackets,
  bolts, pipe ends, where trims meet the body - from two angles. A gap that is invisible from the
  default distance is obvious in a close shot, and so is a part that runs into another one.
- **Size:** read `obj.dimensions` or `get_scene_info(query=...)` against your planned dimensions.
  A 1.65 m tall cylinder named `_ScaleRef` beside the subject makes scale errors obvious in `look`;
  delete it afterwards.
- **Shape:** `look(mode="angles", target=[...])` from front, side, top and three-quarter; close up
  (`distance`) for edges and joints. Compare with the reference image if there is one.
- **Shading:** `look(shading="rendered")` shows bevels catching light and inverted faces.
- **Topology:** `get_scene_info(fields=["topology"], query=...)` for n-gons, non-manifold edges and
  face counts when the subject will be exported or deformed.
