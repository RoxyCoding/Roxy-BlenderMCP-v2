# Roxy Blender MCP session rules

These continue the server instructions. Follow them for the whole conversation.

## Guides

Before modeling, rigging, animation, materials, retopology, Geometry Nodes, scene building and lighting,
level design, exporting to Unreal or bpy work you are unsure of, read the matching guide with
get_guide(topic); an unknown topic lists them all.

Every execute_blender_code script also has `roxy`: tested helpers for modeling (roxy.box,
roxy.panel_with_openings, roxy.lathe, roxy.sweep, ...), material wear, scattering and Geometry
Nodes. The guides list them; call them instead of writing your own.

## Quality

Aim for AAA quality. Never settle for "something like it": model the specific real thing, name
the features that identify it and get each one right, and give every part its real form - no
boxes stuck together, no cylinder for a bottle or sphere for a head (get_guide("modeling"),
steps 1 and 4). Shape features into the part they belong to (inset, extrude, cut) instead of
stacking thin blocks on it. Whatever follows a rule - rows and grids of one piece, copies along a
path, scattering, variation - is Geometry Nodes (roxy.repeat, instances_along_curve, scatter), not
objects placed one by one (get_guide("modeling"), Geometry Nodes or by hand). Nothing is factory-new by default: after materials, roxy.weather(obj)
ages every surface over its textures ("used"; "new" only when new is the point). When the Roxy
Substance 3D Painter MCP is connected, hero and close-up game assets get their textures and wear
there instead, through painter_handoff (get_guide("surface-realism")). Anything that leaves
Blender or gets painted or baked textures is unwrapped with uv_bake(action="unwrap") and passes
uv_bake(action="check") first: seams on hard edges, one texel density, no stretch or overlap. Before calling a scene or asset done, review it with
get_guide("quality-review"), and report what is still weak rather than claiming it is perfect.

## Region: Japanese by default

Unless the user names another country or region (or the setting clearly implies one), every
real-world building, product, piece of equipment and everyday item follows Japanese
specifications, design and standards - anything at all, not only what the guide lists. Library
and generated assets are mostly American or European: check them. get_guide("japanese-design")
says how to work out the Japanese version. A region the user names always wins.

## Game engine: Unreal Engine 5 by default

Anything that will be animated - doors, lids, drawers, wheels - is planned with "moves" and must
turn about its real hinge, carry what is fixed to it and clear everything across its range
(get_guide("modeling"), Parts that move).

Game assets target Unreal Engine 5 unless the user names another engine: naming, scale, pivots,
Nanite and collision follow get_guide("unreal-engine"). Export with export_to_unreal, never the FBX
exporter directly (its other scale options import 100x too small); when an Unreal MCP is connected,
import with it and run export_to_unreal(action="verify") on the bounds Unreal reports.

## Assets

Objects and materials can also come from existing libraries (search_assets, then import_asset:
Poly Haven, ambientCG, Sketchfab). For a material, search Poly Haven first and
ambientCG when Poly Haven lacks it or for Japanese surfaces (tatami and more); both are CC0.
What no library has, model with execute_blender_code following get_guide("modeling"). Anything with more
than one part needs a plan first: model_plan(action="check"), then build from it and verify it. Imported models arrive at arbitrary
scale: use the reported world_bounding_box to size them and put them on the ground.
