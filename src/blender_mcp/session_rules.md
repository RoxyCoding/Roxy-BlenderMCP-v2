# Roxy Blender MCP session rules

These continue the server instructions. Follow them for the whole conversation.

## Guides

Before rigging, animation, materials, retopology, Geometry Nodes, scene building and lighting,
level design, exporting to Unreal or bpy work you are unsure of, read the matching guide with
get_guide(topic); an unknown topic lists them all.

## Quality

Aim for AAA quality. Before calling a scene or asset done, review it with
get_guide("quality-review"), and report what is still weak rather than claiming it is perfect.

## Region: Japanese by default

Unless the user names another country or region (or the setting clearly implies one), every
real-world building, product, piece of equipment and everyday item follows Japanese
specifications, design and standards - anything at all, not only what the guide lists. Library
and generated assets are mostly American or European: check them. get_guide("japanese-design")
says how to work out the Japanese version. A region the user names always wins.

## Game engine: Unreal Engine 5 by default

Game assets target Unreal Engine 5 unless the user names another engine: naming, scale, pivots,
Nanite, collision and FBX export follow get_guide("unreal-engine").

## Assets

Objects and materials can also come from existing libraries (search_assets, then import_asset:
Poly Haven, ambientCG, Sketchfab). For a material, search Poly Haven first and
ambientCG when Poly Haven lacks it or for Japanese surfaces (tatami and more); both are CC0.
What no library has, model with execute_blender_code. Imported models arrive at arbitrary
scale: use the reported world_bounding_box to size them and put them on the ground.
