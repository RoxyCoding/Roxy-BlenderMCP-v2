"""painter_handoff: Blender -> Substance 3D Painter (through the Roxy Painter MCP) -> back.

Painter wants one UV map with every face in its own place (roxy.unwrap), makes a texture set per material,
and exports textures named <mesh>_<TextureSet>_<Channel>. The Blender side writes that mesh
and reads those textures back; the replies say what to run on the Painter MCP in between.
"""

from __future__ import annotations


def format_export(result: dict, target: str) -> str:
    sets = result["texture_sets"]
    normal = "DirectX" if target == "unreal" else "OpenGL"
    tex_dir = result["dir"].rstrip("/\\") + "/textures"
    lines = [
        f"Exported {result['name']} for Painter: {result['file']}",
        "Texture sets (one per material): " + "; ".join(f"{m} ({', '.join(objs)})" for m, objs in sets.items()),
        "Each object has a UV map \"Unwrap\" (seams on hard edges, every face in its own place in 0-1, one "
        "texel density across the asset); the FBX carries only that map, triangulated, at the asset's origin.",
    ]
    res = result.get("resolutions") or {}
    if res:
        lines.append(f"Texel density {result.get('density')} px/m; resolution per texture set: "
                     + ", ".join(f"{m} {r}" for m, r in res.items()) + ".")
    for w in result.get("warnings") or []:
        lines.append(f"Warning: {w}")
    lines += [
        "",
        "Next, with the Substance 3D Painter MCP:",
        f"1. create_project(mesh_path=\"{result['file']}\", normal_map_format=\"{normal}\", "
        f"resolution={max(res.values(), default=2048)}, close_current=true), then wait_until_idle"
        + "".join(f"; set_texture_set_resolution(size={r}, texture_sets=[\"{m}\"])"
                  for m, r in res.items() if r != max(res.values())),
        "2. bake_mesh_maps() - AO, curvature and the rest drive the wear generators",
        "3. Per texture set: a base material (search_resources / add_layer smart_material or a fill), then "
        "the object's history - dirt in crevices, edge wear, dust - as masks with generators (\"Dirt\", "
        "\"Edge Wear\"...). Default to used, not new; frame_camera + screenshot to judge it.",
    ]
    if target == "unreal":
        lines.append(f"4. export_textures(export_path=\"{tex_dir}\", preset=<the Unreal packed preset from "
                     "list_export_presets>) - BaseColor, Normal (DirectX) and OcclusionRoughnessMetallic, which "
                     "import into Unreal directly (sRGB off for ORM and Normal).")
        lines.append(f"5. For Blender previews too: painter_handoff(action=\"import\", name=\"{result['name']}\", "
                     f"textures_dir=\"{tex_dir}\", normal_format=\"DirectX\").")
    else:
        lines.append(f"4. export_textures(export_path=\"{tex_dir}\", preset=\"PBR Metallic Roughness\")")
        lines.append(f"5. painter_handoff(action=\"import\", name=\"{result['name']}\", textures_dir=\"{tex_dir}\")")
    lines.append("6. save_project(path=...) so the layers can be changed later.")
    return "\n".join(lines)


def format_import(result: dict) -> str:
    done = result.get("materials") or {}
    lines = [f"Painter textures on {result['name']}:" if done else
             f"No Painter textures matched the materials of {result['name']}."]
    for mat, channels in done.items():
        lines.append(f"- {mat}: {', '.join(channels)} (through the \"Unwrap\" UV map)")
    if result.get("without_textures"):
        lines.append("No files for: " + ", ".join(result["without_textures"]) + " - export those texture sets "
                     "too, or check the file names end in _<TextureSet>_<Channel>.")
    if result.get("unmatched"):
        lines.append("Ignored files: " + ", ".join(result["unmatched"][:12]))
    if done:
        lines.append("The materials were rebuilt from the textures (the wear is in them now, so don't "
                     "roxy.weather these). look(shading=\"rendered\") to check.")
    return "\n".join(lines)
