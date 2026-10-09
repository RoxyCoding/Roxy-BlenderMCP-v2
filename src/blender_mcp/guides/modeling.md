---
title: Modeling
summary: Modeling anything yourself with Python - one method for any subject (objects, buildings, vehicles, machines, plants, terrain), working out real dimensions from use, people, standards and materials, naming the features that make it the real thing rather than something like it, decomposing by how things are made, giving every part its real form instead of a primitive, choosing techniques, tested helpers (boxes, rounded and tapered boxes and cylinders, lofts, fusing one-piece parts, cylinders, profiles, lathes, sweeps, panels with openings, steps, cuts, real-scale UVs, assembling), and checking.
---

# Modeling

You model whatever no library has. The same method works for a cup, a chair, a vending machine,
a car, a staircase, a school, a tree or a hillside; what changes is only the facts you feed it.
Build every subject as the real thing it is: made for a purpose, at real size, from parts,
each in its real form, with no razor-sharp edges. Never settle for something that only looks
like it - a generic chair-ish chair, boxes stuck together, a cylinder for a bottle, a sphere for
a head, a cone for a tree. Japanese facts unless the user names another region
(`get_guide("japanese-design")`).

## The method

### 1. Understand the subject

Before any geometry, answer in one or two sentences: what is it, who uses it and how, what is it
made of, how was it made (cast, bent, cut from boards, welded, grown, poured, woven), and where
does it stand. Purpose explains form: a chair's seat height comes from legs, a handle's diameter
from hands, a roof's slope from rain, a branch's taper from growth.

Then pin down **which** one it is. "A chair" is a category; "a Japanese school chair: 22 mm
steel tube frame bent in one piece, plywood seat and back screwed on from below, plastic feet"
is a thing you can build. Choose the specific kind (type, era, maker style, region) that fits
the scene and say it.

Then write its **identifying features**: the details someone who knows the real thing looks
for first, and whose absence makes a model read as "something like it". Make each one concrete
and measurable - proportions, angles, radii, sections, how parts join, what is one piece:

- School chair: back legs splay back about 6 degrees; the seat tilts back 3-5 degrees; the
  tube bends at R40-60 with no welds at the bends.
- Kei car: 3.4 m long, 1.48 m wide; tall cabin with an almost vertical tailgate; wheels pushed
  to the corners; 145/80R12 or 155/65R14 tyres filling round wheel arches.
- Wine bottle: shoulder at about two thirds of the height, neck 30 mm across with a lip, a
  punt pushed up into the base.

Model every feature, and check each one at the end. If you can't name at least three, you
don't know the subject well enough yet: say what you will assume, or ask for a reference image.

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

Mark what **moves**: doors, lids, drawers, flaps, windows, wheels, levers, anything a player or
an animation will open, turn or slide. Each is its own part with everything fixed to it, and how
it moves is part of the plan (see "Parts that move" below).

### 4. Give every part its real form

A box, cylinder, sphere or cone is where a part starts, not what it is. Before choosing a
technique, say for each part what makes it more than a primitive - this is what separates the
real thing from something like it:

- **Section and taper.** Legs narrow to the foot, posts and plinths step or chamfer, casings
  have draft, a handle is thicker where the hand grips. Few real parts keep one section from
  end to end.
- **Edge radius from how it was made.** Moulded plastic 1-5 mm, die-cast and machined metal
  0.5-2 mm, sawn and planed timber 1-3 mm, worn or sanded edges more, upholstery and cushions
  20-60 mm, appliance and car body corners 10-100 mm, concrete and stone chamfers 5-20 mm.
  A 2 mm bevel on everything is not a form.
- **Crown, curve and silhouette.** Seat pans dish, cushions bulge, tops and lids crown, backrests
  curve and lean, roofs overhang with a fascia, vehicles and appliances are rounded at every
  corner seen from above. Check the subject as a black shape: if its outline is all right
  angles and the real one isn't, the form is wrong.
- **One piece where it is one piece.** A casting, a moulding, a welded frame, a carved or turned
  block, a bent sheet is one continuous body with a radius where its pieces meet
  (`roxy.fuse`, `roxy.loft`, `roxy.sweep`), not separate boxes touching. Separate parts are
  separate where the real thing is assembled, and the joint shows how (seam, gap, fastener).
- **Profiles, not stacks.** A moulding, a frame, a counter edge, a step nosing, a rail is one
  `roxy.extrude_profile` or `roxy.sweep` with its real section, never a pile of thin boxes.
- **Round things have a side profile.** A bottle has a shoulder, neck and lip; a cup a foot and
  a rim; a table leg turned on a lathe has beads and a taper; a tyre has a bulging sidewall and
  tread; a lamp shade flares. Draw that profile (`roxy.lathe`) instead of a cylinder.
- **Organic things are not geometric.** A head is not a sphere, a tree not a cone on a cylinder,
  a rock not a cube, a cushion not a box. Start from the real proportions and silhouette and
  shape them (Subdivision Surface over a shaped cage, `roxy.loft`, sculpted Displace), or use a
  library asset.
- **Nothing perfectly regular that isn't.** Hand-made, grown and worn things vary: planks differ
  in width, stones in size, leaves in angle, a cushion sags where it is sat on. Machine-made
  things are regular - keep those exact.

Some parts really are that plain shape: a wall, a floor slab, a shelf board, a brick, a sheet
of glass, a rod, a straight tube. Say so (`"plain": true` in the plan); everything else gets its
form.

### 5. Choose a technique per part

| Shape | Technique |
|---|---|
| Plain boards, slabs, walls, bricks (truly box-shaped) | `roxy.box` |
| Casings, worktops, cushions, moulded and cast blocks (rounded edges) | `roxy.rounded_box` with the real radius |
| Legs, posts, plinths and casings that taper | `roxy.rounded_box(top=..., bottom=...)` |
| Bodies whose section changes along their height (appliances, car bodies, seats, handles, non-round bottles) | `roxy.loft` through rounded-rectangle sections |
| One-piece parts made from several shapes (castings, mouldings, welded frames, carved blocks) | build the pieces, then `roxy.fuse` them with a fillet |
| Boards and walls with holes (doors, windows, vents, displays) | `roxy.panel_with_openings`, or `roxy.cut` |
| Straight rods, tubes and pipes | `roxy.cylinder` |
| Round legs, feet, knobs, caps, columns (rounded ends, tapers) | `roxy.rounded_cylinder` |
| Round things turned on an axis (bottles, cups, vases, lamps, columns, wheels) | `roxy.lathe` from a side profile |
| Anything with a custom outline (mouldings, brackets, frames, roofs, signs, rail sections) | `roxy.extrude_profile` |
| Members along a path (handrails, pipes, frames, cables, bent tubes) | `roxy.sweep` |
| Stairs, bleachers, stepped bases | `roxy.steps` |
| Repeats (slats, shelves, tiles, lattices, window rows, fence posts) | Array modifier, or `get_guide("geometry-nodes")` |
| Symmetric subjects (vehicles, furniture, faces) | model one half, Mirror modifier |
| Soft and organic shapes (cushions, bodies, rocks, car body panels) | a low box or profile with Subdivision Surface and a few supporting edge loops |
| Many small scattered things (stones, leaves, debris, grass) | scatter (`get_guide("environment-art")`) |
| Ground and terrain | subdivided plane with Displace (environment-art) |

### 6. Write the plan and check it

Steps 1-4 become a plan: the subject's name, purpose and overall size, its identifying
`features` (at least three, from step 1), and every structural part
with its shape, size, position (`at`, the bottom centre of its box) and what holds it up
(`rests_on`: the parts it sits on, hangs from or is fixed to, or "ground"). Submit it with
`model_plan(action="check", plan=...)` and fix every error until it passes. The check catches
what a misunderstood structure looks like: parts that float, supports that don't touch, chains
that never reach the ground, parts outside the whole, two parts in one place.

Plan the structure and major parts, not every screw: detail comes after and doesn't need a plan.
A box or cylinder part carries its form: `"radius"` for its edge radius, `"top"` or `"bottom"`
[width, depth] (a cylinder's [diameter, diameter]) where an end narrows (`size` is the part at its
widest), and `build` makes it with `roxy.rounded_box` or `roxy.rounded_cylinder`; `"plain": true`
where the real thing is exactly that shape. The check warns about every bare primitive. Parts no box or cylinder describes (a lathe-turned leg,
a curved backrest, a lofted body) are `"shape": "custom"` with `"how"` naming the helper you will
use; give them the box they occupy.

For a subject the user will judge closely (the hero object, a whole building), show the plan's
parts and sizes to the user before building.

### 7. Build from the plan, then add detail

`model_plan(action="build", name=...)` builds every box and cylinder part under one empty called
the subject's name, each named `<Name>_<Part>`, and stores the plan on it. Make the custom parts
yourself with the same naming, `parent=` the empty and `location=` their `at`. Then add fittings
and detail. `look(mode="angles", target=["<Subject>"])` after each level - fixing proportions
early is cheap, fixing them after detail is not. Save a checkpoint before anything hard to undo
(cuts, applying modifiers, joining).

When the build is done, `model_plan(action="verify", name=...)` compares it with the plan: every
part present, at its planned size and place, touching its supports and grounded. Fix what it
reports, or change the plan and build again if the plan was wrong. It also lists every part
that is still a bare primitive (box, straight prism or cylinder, cone, sphere) and not marked
plain, and lists the identifying features to confirm close up. Move or turn the whole subject
only through its empty.

### 8. Surface, light, review

UVs (`roxy.uv_world_box` for hard-surface and architecture), materials (`get_guide("materials")`,
`get_guide("surface-realism")`), then `get_guide("quality-review")`.

## Helpers

Tested on Blender 5.1. They build mesh data directly (no viewport or mode switching), keep object
scale at 1, and put the origin at the bottom centre so `location` is where the part stands.
Most parts get `roxy.finish()`: a small angle-limited bevel and weighted normals.

The addon provides these as `roxy.<name>` inside execute_blender_code (addon protocol 18+), so call them directly - don't paste or redefine them. If `roxy` is undefined, the Blender addon is outdated: get_addon_status says how to update it. `roxy.rounded_box`, `roxy.rounded_cylinder`, `roxy.loft` and `roxy.fuse` need protocol 22.

- `roxy.finish(obj, bevel=0.002, segments=2)` - Rounded edges that catch highlights, with clean shading.
- `roxy.box(name, size, location=(0, 0, 0), bevel=0.002, parent=None, collection=None, origin='bottom')` - A box of real size (x, y, z metres) with scale 1.
- `roxy.rounded_box(name, size, radius, location=(0, 0, 0), top=None, bottom=None, bottom_radius=None, segments=6, parent=None, collection=None)` - A box with real rounded edges (radius in metres): size is the part at its widest, top/bottom=(width, depth) narrow that end into a taper, bottom_radius=0 keeps the bottom edges square where it sits flush.
- `roxy.rounded_cylinder(name, radius, depth, edge, location=(0, 0, 0), top=None, bottom=None, segments=48, parent=None, collection=None)` - A turned round part with rounded end edges (edge in metres): radius is the part at its widest, top/bottom (a radius) narrow that end into a taper.
- `roxy.loft(name, sections, location=(0, 0, 0), segments=6, bevel=0.002, parent=None, collection=None)` - One surface through rounded-rectangle sections from bottom to top, each (z, width, depth, corner_radius) or (z, width, depth, corner_radius, x, y): bodies whose section changes along their height. Both ends are capped flat.
- `roxy.fuse(obj, parts, fillet=None)` - Merge parts into obj as one continuous body (boolean union) and delete them; fillet (metres) rounds the seams where they meet, as on a casting or weld.
- `roxy.cylinder(name, radius, depth, location=(0, 0, 0), segments=32, bevel=0.001, parent=None, collection=None, origin='bottom')` - An upright cylinder (legs, poles, pipes, knobs).
- `roxy.extrude_profile(name, points, depth, location=(0, 0, 0), bevel=0.001, parent=None, collection=None)` - Extrude a closed 2D outline [(x, z), ...] in metres along +Y by depth: mouldings, brackets, frames, signs, anything with a custom silhouette.
- `roxy.cut(obj, cutter)` - Subtract cutter from obj (holes, slots, recesses) and delete the cutter.
- `roxy.set_pivot(obj, pivot)` - Move obj's origin to pivot (metres, in its parent's space) without moving its mesh: the hinge a door, lid or flap turns on.
- `roxy.carry(holder, obj)` - Parent obj to holder where it stands, so it moves with it: a handle on its door, a knob on its drawer.
- `roxy.limit_motion(obj, moves)` - Limit Rotation or Location constraints that keep a moving part in its plan range while you animate it.
- `roxy.uv_world_box(obj, space='world')` - UVs in metres, projected per face along its main axis: a texture with Mapping Scale 1/size tiles at real size on every object built this way, whatever its dimensions.
- `roxy.assemble(name, parts, location=(0, 0, 0), collection=None)` - Group parts under an empty, so the whole object moves, rotates and exports as one.
- `roxy.panel_with_openings(name, size, openings, location=(0, 0, 0), bevel=0.002, parent=None, collection=None)` - A board or wall (width x, thickness y, height z) with rectangular openings, each (x_centre, z_bottom, width, height) in metres from the panel's bottom centre: walls with doors and windows, doors with glazing, appliance fronts, furniture sides, signs.
- `roxy.steps(name, rise, run, width, max_step_rise=0.2, location=(0, 0, 0), bevel=0.002, parent=None, collection=None)` - A flight of steps climbing `rise` over `run` along +Y from `location`, centred across X: stairs, bleachers, stepped plinths.
- `roxy.sweep(name, points, radius=0.02, location=(0, 0, 0), resolution=4, parent=None, collection=None)` - A round member following a path of 3D points in metres: handrails, pipes, frames, cables, bent tubes.
- `roxy.lathe(name, profile, segments=48, location=(0, 0, 0), parent=None, collection=None)` - Spin a side profile [(radius, z), ...] in metres around the Z axis: bottles, cups, bowls, vases, lamps, columns, knobs, wheels (rotate afterwards).

## Examples

These show the method applied; they are not the limit of what it covers.

- **Dining table** (furniture): top 1350 x 800 x 30 mm at 700 mm with 6 mm rounded edges, four
  legs 40 mm square tapering to 28 mm at the foot, inset 50 mm, aprons under the top.

```python
W, D, H, T, L, IN = 1.35, 0.80, 0.70, 0.03, 0.04, 0.05
top = roxy.rounded_box("Table_Top", (W, D, T), 0.006, (0, 0, H - T))
legs = [roxy.rounded_box(f"Table_Leg_{i}", (L, L, H - T), 0.003, (sx * (W / 2 - IN), sy * (D / 2 - IN), 0),
                         bottom=(0.028, 0.028))
        for i, (sx, sy) in enumerate([(1, 1), (1, -1), (-1, 1), (-1, -1)])]
aprons = [roxy.rounded_box("Table_Apron_F", (W - 2 * IN, 0.02, 0.08), 0.002, (0, -(D / 2 - IN), H - T - 0.08)),
          roxy.rounded_box("Table_Apron_B", (W - 2 * IN, 0.02, 0.08), 0.002, (0, D / 2 - IN, H - T - 0.08))]
for part in (top, *legs, *aprons):
    roxy.uv_world_box(part, space="local")
table = roxy.assemble("Table", [top, *legs, *aprons])
```

- **A room** (architecture): floor slab (`roxy.box`), walls 120 mm thick to the ceiling height
  (2.4 m in homes) with `roxy.panel_with_openings` for a 780 x 2000 mm door and windows with sills at
  900 mm, ceiling slab, skirting (`roxy.extrude_profile`), switches at 1200 mm, sockets at 250 mm.
  `roxy.uv_world_box(space="world")` so plaster and flooring run continuously across pieces.
- **A vending machine** (appliance): casing `roxy.rounded_box` about 1000 x 700 x 1830 mm (20 mm
  corners) with a
  `roxy.panel_with_openings` front (display window, coin slot, outlet), product dummies arrayed
  behind the window, buttons as small `roxy.cylinder`s, emission for the lit panel.
- **A bicycle** (vehicle/machine): wheels by `roxy.lathe` (tyre profile) rotated upright, frame tubes
  by `roxy.sweep` between the head tube, bottom bracket and axles, seat and handlebar by
  `roxy.extrude_profile` and `roxy.sweep`, mirrored parts where it is symmetric.
- **A stair with handrail** (building element): `roxy.steps` for the rise and run (it chooses the step
  count from the maximum riser), `roxy.sweep` for the handrail at 850 mm above the step nosings.
- **A potted plant** (nature): pot by `roxy.lathe`, soil disc, stems by `roxy.sweep` with small radii, leaves
  as subdivided `roxy.extrude_profile` outlines with a slight bend; or a Poly Haven plant in a modelled pot.

## Parts that move

Anything that will be animated - in a game above all - must move like the real thing without
breaking: turn about its real hinge, carry what is fixed to it, and pass everything else with
the clearance the real one has. Get this wrong and the door swings about its middle, the handle
stays hanging in the air, or the leaf cuts through the frame.

- **Plan the motion.** Give the part `"moves"`: `{"type": "hinge", "axis": "z", "pivot": [x, y, z],
  "range": [-100, 0]}` (degrees) or `{"type": "slide", "axis": "y", "range": [-0.4, 0]}` (metres).
  Build it at rest, closed, so the range includes 0; the sign says which way it goes (about +z,
  positive turns counter-clockwise seen from above). The check sweeps it through the range and
  reports anything it runs into, so a wrong pivot or direction shows before you build.
- **The pivot is where the real hinge is.** Hinges sit on the edge where the knuckles are: a
  door on the face it opens towards, a lid on the back edge of its top, a flap on its bottom
  edge - not in the middle of the thickness, which swings the far corner through the frame.
  Drawers and sliding doors slide along their runners or track.
- **Clearance like the real thing.** A door leaf 2-3 mm from its frame all round, a drawer front
  2-3 mm from its neighbours, a lid 1-2 mm. Faces that are this close by design are clearance,
  and the flush check ignores them between a moving part and its surround.
- **What is fixed to it moves with it.** `rests_on` the moving part - a handle, a knob, glass,
  a hinge leaf on the door side - and `build` parents it to the moving part. Detail you add
  later: `roxy.carry(door, handle)`. The frame-side hinge leaf rests on the frame.
- **The origin is the pivot.** `build` puts each moving part's origin on its hinge
  (`roxy.set_pivot` for parts you make yourself) and adds a Limit Rotation/Location constraint
  (`roxy.limit_motion`) so posing it in Blender stays in range. A game engine turns a mesh about
  its origin and nowhere else.
- **Check it moving.** `model_plan(action="verify")` moves each moving part through its range
  with its real meshes and children, as the game will, and reports collisions, an origin off
  the hinge, and detail that would stay behind. Also pose it open in Blender and `look` at it.
- **Export it to move.** `export_to_unreal` exports each moving part as its own mesh with its
  pivot on the hinge and says where to place it and how to rotate it (`get_guide("unreal-engine")`,
  Moving parts). A moving part merged into the rest of the mesh can never open.

## Detail and geometry

- **Detail where it is seen.** Hero subjects close to the camera get bevels with more segments,
  real gaps between parts (2-3 mm), visible fasteners and seams. Background subjects can be
  simple shapes with good materials.
- **No hairline gaps, no floating.** Parts that touch in reality meet exactly or overlap slightly
  out of sight.
- **Every joint is a real joint.** Ask of each part how it is fixed, and model that: a lid sits
  on its rim or turns on a hinge the model shows; a shelf hangs from a bracket or sleeve; a bolt
  head sits on its plate with the shank sunk into it; a pipe enters a hole, a flange or a
  fitting; a trim strip lies flush against the face it covers. Something "near" its support is
  floating - fixings are where a model looks careless first.
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

## Checking

- **Is it the real thing?** `look(mode="angles")` and go through the identifying features one by
  one, close up: each must be visible and right. Then ask whether someone who owns one would
  recognise it as that kind, or only as "a chair" / "a car". If parts are still bare primitives,
  give them their taper, radius, profile or organic shape (step 4) before adding any detail.
- **Structure:** `model_plan(action="verify", name=...)` after building, after adding detail and
  after any change to the parts. It measures the real surfaces, not bounding boxes: every part,
  detail included, must touch what holds it and connect to the structure. Fix its errors; read
  every near miss and almost-flush warning and either close it or say why it is intended.
- **Joints:** `look(target=[...], distance=...)` close up on every joint - hinges, brackets,
  bolts, pipe ends, where trims meet the body - from two angles. A gap that is invisible from the
  default distance is obvious in a close shot.
- **Size:** read `obj.dimensions` or `get_scene_info(query=...)` against your planned dimensions.
  A 1.65 m tall cylinder named `_ScaleRef` beside the subject makes scale errors obvious in `look`;
  delete it afterwards.
- **Shape:** `look(mode="angles", target=[...])` from front, side, top and three-quarter; close up
  (`distance`) for edges and joints. Compare with the reference image if there is one.
- **Shading:** `look(shading="rendered")` shows bevels catching light and inverted faces.
- **Topology:** `get_scene_info(fields=["topology"], query=...)` for n-gons, non-manifold edges and
  face counts when the subject will be exported or deformed.
