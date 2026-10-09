"""uv_bake: replies for unwrapping an asset, checking its UVs and baking its textures."""

from __future__ import annotations


def _checks(checks: dict) -> list[str]:
    lines = []
    for tset, c in checks.items():
        head = (f"- {tset}: {c.get('resolution')} px, {c.get('density', '?')} px/m, {c.get('used', 0)}% used, "
                f"stretch {c.get('stretched', 0)}%, overlap {c.get('overlap', 0)}%, "
                f"closer than the margin {c.get('too_close', 0)}%")
        lines.append(head + (" - OK" if not c.get("problems") else ""))
        for p in c.get("problems") or []:
            lines.append(f"    problem: {p}")
    return lines


def format_unwrap(name: str, info: dict) -> str:
    lines = [f"Unwrapped {name} into the \"Unwrap\" UV map: {info['density']} px/m everywhere; resolution per "
             "texture set: " + ", ".join(f"{m} {r}" for m, r in info["sets"].items()) + "."]
    for m, objs in info.get("objects", {}).items():
        lines.append(f"  {m}: {', '.join(objs)}")
    if info.get("frozen"):
        lines.append("Geometry Nodes output made real mesh (originals hidden as <name>_GN): " + ", ".join(info["frozen"]))
    if info.get("not_flat"):
        lines.append(f"{info['not_flat']} regions could not be opened flat; mark a seam across them (edge.seam) "
                     "and unwrap again.")
    lines.append("UV check:")
    lines += _checks(info.get("checks") or {})
    bad = any(c.get("problems") for c in (info.get("checks") or {}).values())
    lines.append("Fix the problems above before texturing." if bad else
                 "Ready for painter_handoff(action=\"export\", unwrap=False) or uv_bake(action=\"bake\").")
    return "\n".join(lines)


def format_check(name: str, checks: dict) -> str:
    bad = any(c.get("problems") for c in checks.values())
    return "\n".join([f"UVs of {name}: {'NOT OK' if bad else 'OK'}"] + _checks(checks))


def format_bake(name: str, result: dict, target: str) -> str:
    lines = [f"Baked {name} into {result['dir']}:"]
    for tset, files in result["files"].items():
        lines.append(f"- {tset}: " + ", ".join(sorted(files)))
    if target == "unreal":
        lines.append("Import them into Unreal with sRGB off for Normal and OcclusionRoughnessMetallic; "
                     "the normals are DirectX already.")
    lines.append(f"To see them in Blender: painter_handoff(action=\"import\", name=\"{name}\", "
                 f"textures_dir=\"{result['dir']}\""
                 + (", normal_format=\"DirectX\")" if target == "unreal" else ")")
                 + " - it rebuilds the materials from the files.")
    return "\n".join(lines)
