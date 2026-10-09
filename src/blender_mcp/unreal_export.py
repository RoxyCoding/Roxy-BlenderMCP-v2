"""export_to_unreal: Blender -> Unreal Engine 5, and checking the import landed right.

The FBX settings here were tested against UE5 with Blender 5.1: the exporter's
default unit handling (FBX_SCALE_NONE) imports at real size, while
FBX_SCALE_ALL / FBX_SCALE_UNITS import 100x too small; Blender +X stays +X and
up stays up, but Y flips (Blender -Y becomes Unreal +Y); an armature object
not called "Armature" becomes an extra root bone.
"""

from __future__ import annotations

# Bounds may differ by bevels and float noise; anything beyond this is a real mismatch.
BOUNDS_TOL_CM = 1.0
BOUNDS_TOL_FRACTION = 0.01


def blender_to_unreal_cm(lo: list[float], hi: list[float]) -> dict:
    """Blender world-space box (metres) to the box Unreal reports (centimetres, Y flipped)."""
    return {
        "min": {"x": lo[0] * 100, "y": -hi[1] * 100, "z": lo[2] * 100},
        "max": {"x": hi[0] * 100, "y": -lo[1] * 100, "z": hi[2] * 100},
    }


def _as_min_max(bounds: dict) -> dict | None:
    """Accept StaticMeshTools.get_bounds ({min, max}) or SkeletalMeshTools.get_bounds
    ({origin, boxExtent}), with or without a returnValue wrapper."""
    if not isinstance(bounds, dict):
        return None
    bounds = bounds.get("returnValue", bounds)
    if "min" in bounds and "max" in bounds:
        return {"min": bounds["min"], "max": bounds["max"]}
    if "origin" in bounds and "boxExtent" in bounds:
        o, e = bounds["origin"], bounds["boxExtent"]
        return {"min": {a: o[a] - e[a] for a in "xyz"}, "max": {a: o[a] + e[a] for a in "xyz"}}
    return None


def compare(expected: dict, unreal_bounds: dict) -> tuple[bool, list[str]]:
    """(ok, findings) comparing the bounds Unreal reports with the ones the export predicted."""
    got = _as_min_max(unreal_bounds)
    if got is None:
        return False, ["Pass the bounds as Unreal returned them: {min, max} from StaticMeshTools.get_bounds "
                       "or {origin, boxExtent} from SkeletalMeshTools.get_bounds."]
    findings = []
    for axis in "xyz":
        size_e = expected["max"][axis] - expected["min"][axis]
        size_g = got["max"][axis] - got["min"][axis]
        tol = max(BOUNDS_TOL_CM, BOUNDS_TOL_FRACTION * size_e)
        if size_e > 0 and abs(size_g / size_e - 0.01) < 0.002:
            findings.append(f"{axis}: {size_g:.2f} cm instead of {size_e:.2f} - 100x too small, the FBX was "
                            "exported with FBX_SCALE_ALL or FBX_SCALE_UNITS; export again with this tool.")
        elif size_e > 0 and abs(size_g / size_e - 100) < 20:
            findings.append(f"{axis}: {size_g:.0f} cm instead of {size_e:.2f} - 100x too big; check the scene's "
                            "Unit Scale is 1.0 and the objects' scale is applied.")
        elif abs(size_g - size_e) > tol:
            findings.append(f"{axis}: size {size_g:.2f} cm, expected {size_e:.2f} cm.")
        for end in ("min", "max"):
            if abs(got[end][axis] - expected[end][axis]) > tol and abs(size_g - size_e) <= tol:
                findings.append(f"{axis} {end}: {got[end][axis]:.2f} cm, expected {expected[end][axis]:.2f} cm "
                                "- the pivot or facing differs (export from the asset's own origin, front "
                                "towards Blender -Y).")
    return not findings, findings


# A rotation of +a about Blender's x, y or z axis, seen in Unreal (Y flipped, left-handed
# rotators): (rotator field, sign). Yaw turns X towards Y, Roll turns Y towards -Z, Pitch turns
# X towards Z; mirroring Y reverses the sense of every rotation.
UNREAL_ROTATION = {"x": ("Roll", 1), "y": ("Pitch", -1), "z": ("Yaw", -1)}


def unreal_motion(moving: dict) -> str:
    """How a moving part exported on its own moves in Unreal, relative to the main asset."""
    mv = moving["moves"]
    p = moving["pivot_m"]
    place = "({:.1f}, {:.1f}, {:.1f}) cm".format(*(round(c * 100, 1) + 0.0 for c in (p[0], -p[1], p[2])))
    lo, hi = mv["range"]
    axis = mv["axis"]
    if mv["type"] == "slide":
        if isinstance(axis, str):
            sign = -1 if axis.startswith("-") else 1
            vec = [float(axis.lower().lstrip("+-") == a) * sign for a in "xyz"]
        else:
            n = sum(v * v for v in axis) ** 0.5
            vec = [v / n for v in axis]
        cm = lambda t: "({:.1f}, {:.1f}, {:.1f}) cm".format(
            *(round(c * t * 100, 1) + 0.0 for c in (vec[0], -vec[1], vec[2])))
        return (f"place at {place}; it slides from relative location {cm(lo)} to {cm(hi)} "
                "(0 is closed, as modelled).")
    if isinstance(axis, str) and axis.lower().lstrip("+-") in UNREAL_ROTATION:
        field, sign = UNREAL_ROTATION[axis.lower().lstrip("+-")]
        sign *= -1 if axis.startswith("-") else 1
        ends = sorted((sign * lo, sign * hi))
        return (f"place at {place}; animate relative rotation {field} from {ends[0]:g} to {ends[1]:g} degrees "
                "(0 is closed, as modelled).")
    v = [axis[0], -axis[1], axis[2]]
    return (f"place at {place}; it turns about the Unreal axis ({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f}) through "
            f"{lo:g} to {hi:g} degrees in Blender's sense - check the direction once in the editor.")


def format_export(result: dict, ue_folder: str) -> str:
    """The reply for action="export": what was written, and the Unreal steps that follow."""
    kind, asset, path = result["kind"], result["asset"], result["file"]
    b = result["expected_bounds_cm"]
    lines = [
        f"Exported {kind} mesh {asset} to {path}" if path else
        f"{asset} has only moving parts; nothing static was exported.",
        f"Expected in Unreal (cm): min ({b['min']['x']:.1f}, {b['min']['y']:.1f}, {b['min']['z']:.1f}), "
        f"max ({b['max']['x']:.1f}, {b['max']['y']:.1f}, {b['max']['z']:.1f}); {result['triangles']} triangles.",
    ]
    if result.get("materials"):
        lines.append(f"Material slots: {', '.join(result['materials'])} (rebuild them in Unreal as material "
                     "instances; Blender shader nodes don't transfer).")
    if result.get("sockets"):
        lines.append(f"Sockets: {', '.join(result['sockets'])}.")
    if result.get("collisions"):
        lines.append(f"Collision meshes: {', '.join(result['collisions'])}.")
    for w in result.get("warnings") or []:
        lines.append(f"Warning: {w}")
    moving = result.get("moving") or []
    if moving:
        lines.append("")
        lines.append("Moving parts, each its own mesh with its pivot on its hinge or runner (so the "
                     f"game can open it): build a Blueprint with {asset} as the root component and each of these "
                     "as a child Static Mesh Component, moved by a Timeline:")
        for m in moving:
            lines.append(f"- {m['asset']} ({m['file']}): {unreal_motion(m)}")
    toolset = "SkeletalMeshTools" if kind == "skeletal" else "StaticMeshTools"
    lines += [
        "",
        "Next, with the Unreal MCP (toolset editor_toolset.toolsets.<x>):",
        f"1. {toolset}.import_file(folder_path=\"{ue_folder}\", asset_name=\"{asset}\", source_file=<the path above>"
        + (", combine_meshes=true)" if kind == "static" else ")"),
        f"2. {toolset}.get_bounds(mesh={{\"refPath\": \"{ue_folder}/{asset}.{asset}\"}})",
        f"3. export_to_unreal(action=\"verify\", name=\"{result['name']}\", unreal_bounds=<what get_bounds returned>)",
    ]
    if kind == "static":
        lines.append("4. Opaque static meshes: StaticMeshTools.set_nanite_enabled(enabled=true). "
                     + ("No collision was exported: generate_convex_collisions, or model UCX_ meshes."
                        if not result.get("collisions") else ""))
    else:
        lines.append("4. Check the skeleton: SkeletalMeshTools.get_bone_names - one root, no extra "
                     "bone named after the armature.")
    if moving:
        lines.append("Import the moving parts the same way (asset_name each one's name above); add their "
                     "collision so the player can't walk through an open door.")
    lines.append("Save the new assets with AssetTools.save_assets once they check out.")
    return "\n".join(lines)


def format_verify(name: str, ok: bool, findings: list[str]) -> str:
    if ok:
        return f"{name} in Unreal: OK - size, pivot and facing match the Blender export."
    return f"{name} in Unreal: NOT OK\n" + "\n".join(f"- {f}" for f in findings)

