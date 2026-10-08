---
title: Environment art
summary: Building believable places at a AAA bar - planning a scene in layers, density and clustering, environmental storytelling, set dressing with Poly Haven and other libraries, scattering with Geometry Nodes (tested helper), ground and terrain, vegetation, and backgrounds that give depth.
---

# Environment art

A AAA environment feels like a real place someone lives in, works in or abandoned, seen at one
moment in time. It is built in layers, densely, with every area telling a small story. Assets come
from the libraries (Poly Haven first for realistic textures, HDRIs and props; Sketchfab for
specific objects; modelling for what no library has); the craft is in choosing, placing and
connecting them.

## Plan in layers

1. **Purpose and story.** One sentence: who uses this place, when, and what just happened ("a
   Tokyo apartment the morning after a party", "a rural station platform in winter, last train
   gone"). Every later choice should support it.
2. **Blockout** the architecture and big shapes at real size, with the camera
   (`get_guide("scene")`). Japanese dimensions unless the user names another region
   (`get_guide("japanese-design")`).
3. **Primary** objects: the furniture, vehicles, machines and structures that define the place.
4. **Secondary** objects: what sits on and around them - books, dishes, boxes, tools, bags.
5. **Tertiary** detail: clutter, cables, papers, litter, leaves, decals, small debris.
6. **Surfaces and light**: `get_guide("surface-realism")`, `get_guide("lighting-and-rendering")`.
7. **Review** with `get_guide("quality-review")`, then go back to whichever layer is weak.

Save a checkpoint after each layer that works.

## Density and clustering

- Real places are dense where people live and work and sparse where they don't: a desk is
  covered, a corridor is clear. Avoid the even spread of a showroom unless that is the story.
- Group things: objects gather into clusters (a stack of books with a mug on top, boxes against a
  wall, plant pots in a group of three), clusters gather near walls, corners and furniture, and
  open space separates the clusters.
- Vary within a cluster: different sizes, slight rotations (2-10°), a few things fallen or tilted,
  nothing aligned to a perfect grid unless it would be in reality (shop shelves, parking spaces).
- Big, medium, small: each area needs all three scales. A room of only large furniture looks
  empty; a room of only small props looks noisy.
- Ground contact: things rest on surfaces, lean against walls, sit in shadow under shelves. Check
  low angles for floating objects.

## Environmental storytelling

Details that imply people and time make a place real:

- Use: worn paths on floors, a chair pushed out, a half-drunk drink, a jacket on a chair, shoes
  at the genkan, an umbrella stand by the door.
- Time: dust on unused things, faded posters, sun-bleached curtains, leaves blown into corners,
  wet ground after rain with puddles reflecting lights.
- Region and culture: signs, packaging, vending machines, bicycles, plants and architecture of the
  place (japanese-design for Japanese defaults).
- Personality: what is on the walls, the shelves, the fridge says who lives there.

## Set dressing from the libraries

- Materials: Poly Haven textures, then ambientCG for what it lacks (`get_guide("surface-realism")`).
- Search Poly Haven models first for realistic props (`search_assets(source="polyhaven",
  asset_type="models", query=...)`), then Sketchfab for specific or culturally specific objects
  (check licence and face count), and model the few hero objects nothing else covers.
- Import once and duplicate with `obj.copy()` (shared mesh data) for repeats; vary each copy's
  rotation, scale (±10%) and sometimes material colour so repeats don't read as copies.
- Size every import from its bounding box to real dimensions and put it on the ground
  (`get_guide("scene")`, After every import).
- Keep the style and level of detail consistent; replace the asset that doesn't match rather
  than placing it anyway.
- Check every imported asset for details that give away the wrong country in a Japanese setting.

## Scattering

For many small things over a surface - grass clumps, stones, leaves, litter, gravel, debris -
use Geometry Nodes instead of placing thousands of objects. Put the source objects (a few
variations) in their own collection, hidden from view, and scatter them over the ground:

```python
def scatter(target, collection, density=5.0, scale=(0.6, 1.4), seed=0, name="Scatter"):
    """Scatter random copies of the objects in `collection` over `target`'s faces.

    density is copies per square metre. The originals in the collection are the
    sources: keep them out of view (exclude or hide that collection).
    """
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n, l = ng.nodes, ng.links
    gi = n.new("NodeGroupInput"); go = n.new("NodeGroupOutput")
    dist = n.new("GeometryNodeDistributePointsOnFaces")
    dist.inputs["Density"].default_value = density
    dist.inputs["Seed"].default_value = seed
    info = n.new("GeometryNodeCollectionInfo")
    info.inputs["Collection"].default_value = collection
    info.inputs["Separate Children"].default_value = True
    info.inputs["Reset Children"].default_value = True
    inst = n.new("GeometryNodeInstanceOnPoints")
    inst.inputs["Pick Instance"].default_value = True
    rot = n.new("FunctionNodeRandomValue"); rot.data_type = "FLOAT_VECTOR"
    rot.inputs["Max"].default_value = (0.0, 0.0, 6.2832)      # any heading, stays upright
    size = n.new("FunctionNodeRandomValue"); size.data_type = "FLOAT"
    size.inputs["Min"].default_value, size.inputs["Max"].default_value = scale
    join = n.new("GeometryNodeJoinGeometry")
    l.new(gi.outputs["Geometry"], dist.inputs["Mesh"])
    l.new(dist.outputs["Points"], inst.inputs["Points"])
    l.new(info.outputs["Instances"], inst.inputs["Instance"])
    l.new(rot.outputs["Value"], inst.inputs["Rotation"])
    l.new(size.outputs["Value"], inst.inputs["Scale"])
    l.new(gi.outputs["Geometry"], join.inputs["Geometry"])
    l.new(inst.outputs["Instances"], join.inputs["Geometry"])
    l.new(join.outputs["Geometry"], go.inputs["Geometry"])
    mod = target.modifiers.new(name, "NODES"); mod.node_group = ng
    return mod
```

- Density per square metre: grass clumps 20-100, pebbles 5-30, fallen leaves 10-50, litter 0.5-3,
  rocks 0.1-1.
- Several scatters at different densities and scales (big rocks sparse, small stones dense, leaves
  densest in corners) look more natural than one.
- Keep scatter away from paths and under furniture where nothing would collect, or limit it to a
  separate mesh covering only the areas it belongs (a strip along a wall, the edge of a road).
- Several hundred thousand instances render fine but slow the viewport; preview with lower
  density, then raise it.

## Ground and terrain

- The ground is often the largest surface in frame; give it the best texture (Poly Haven,
  `min_size_m` 4+, 2k-4k near the camera) and break up tiling (surface-realism).
- Terrain: a subdivided plane with a Displace modifier driven by a Clouds or Noise texture at
  large scale for rolling ground, a second at small scale for unevenness. Flatten where buildings
  and roads sit.
- Blend between ground materials (grass to dirt to gravel) with a noise mask or by painting a
  vertex colour mask, and scatter along the transitions.
- Roads and pavements: kerbs, drains, manholes, road markings and patches of repaired asphalt;
  Japanese markings and street furniture by default.

## Vegetation

- Poly Haven has scanned plants, trees and ground cover; use several species and sizes together,
  never one plant repeated.
- Nature clusters: undergrowth at the base of trees, plants along walls and paths, gaps where
  people walk. Vary scale and rotation strongly (±30%).
- Leaves need translucency to look alive when backlit: Transmission or a small Subsurface weight
  with a green tint, and alpha for leaf cards (`get_guide("materials")`).
- Japanese settings: potted plants outside houses, trimmed hedges, pines and cherry trees in
  parks, rice fields and cedar forests in the countryside.

## Depth and backgrounds

- Foreground elements partly in frame (a branch, a railing, a doorway) give scale and depth.
- The background needs content, not a void: buildings, hills, trees, or an HDRI whose content
  matches the scene and sits behind real geometry. Match its horizon to the camera height.
- Simplify with distance: detailed geometry near the camera, simple shapes and cards further
  away, the HDRI at the horizon. Haze and fog tie the layers together
  (`get_guide("lighting-and-rendering")`, Atmosphere).
- Check the frame in values only (desaturated): foreground, midground and background should read
  as separate tones.
