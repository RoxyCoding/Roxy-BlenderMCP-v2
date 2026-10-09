"""export_to_unreal: predicted Unreal bounds, and checking what Unreal reports against them.

The numbers come from a real round trip (Blender 5.1 -> UE5): a table 1.0 x 0.6 m with a
marker sticking out to +X 0.9 m and another to -Y 0.6 m imported with min (-50, -30, 0) and
max (90, 60, 70) cm - X kept, Y flipped, metres to centimetres.
"""

import asyncio

import pytest

from blender_mcp import server, unreal_export as ue

BLENDER_BOX = ([-0.5, -0.6, 0.0], [0.9, 0.3, 0.7])
UE_STATIC = {"min": {"x": -50, "y": -30.000001907348633, "z": -2.9e-07}, "max": {"x": 90, "y": 60, "z": 70.0000076}}


def test_blender_box_maps_to_the_box_unreal_reported():
    got = ue.blender_to_unreal_cm(*BLENDER_BOX)
    assert got["min"] == pytest.approx({"x": -50, "y": -30, "z": 0})
    assert got["max"] == pytest.approx({"x": 90, "y": 60, "z": 70})


def test_the_real_import_matches():
    assert ue.compare(ue.blender_to_unreal_cm(*BLENDER_BOX), {"returnValue": UE_STATIC}) == (True, [])


def test_skeletal_bounds_are_accepted_as_origin_and_extent():
    expected = ue.blender_to_unreal_cm([-0.2, -0.2, 0.0], [0.2, 0.2, 1.6])
    got = {"origin": {"x": 0, "y": 0, "z": 80}, "boxExtent": {"x": 20, "y": 20.00001, "z": 80}, "sphereRadius": 84.9}
    assert ue.compare(expected, got) == (True, [])


def test_a_100x_too_small_import_names_the_cause():
    tiny = {end: {a: v / 100 for a, v in UE_STATIC[end].items()} for end in ("min", "max")}
    ok, findings = ue.compare(ue.blender_to_unreal_cm(*BLENDER_BOX), tiny)
    assert not ok and all("100x too small" in f and "FBX_SCALE_ALL" in f for f in findings)


def test_a_flipped_or_shifted_import_is_a_pivot_or_facing_problem():
    flipped = {"min": {"x": -50, "y": -60, "z": 0}, "max": {"x": 90, "y": 30, "z": 70}}
    ok, findings = ue.compare(ue.blender_to_unreal_cm(*BLENDER_BOX), flipped)
    assert not ok and any("pivot or facing" in f for f in findings)


def test_unrecognised_bounds_say_what_to_pass():
    ok, findings = ue.compare(ue.blender_to_unreal_cm(*BLENDER_BOX), {"nope": 1})
    assert not ok and "get_bounds" in findings[0]


# ------------------------------------------------------------------ the tool

@pytest.fixture
def export(monkeypatch):
    monkeypatch.setattr(server, "_unreal_expected", {})
    sent = []

    def run_script(script, args):
        sent.append(args)
        return {"name": args["name"], "asset": "SM_Table", "kind": "static", "file": "C:/x/SM_Table.fbx",
                "bounds_m": [list(BLENDER_BOX[0]), list(BLENDER_BOX[1])], "triangles": 756,
                "materials": ["Wood"], "sockets": [], "collisions": [], "warnings": []}

    monkeypatch.setattr(server, "_run_script", run_script)
    return sent


def _tool(**kw):
    return asyncio.run(server.export_to_unreal(None, **kw))


def test_export_reports_the_prediction_and_the_unreal_steps(export):
    out = _tool(name="Table", ue_folder="/Game/Props/")
    assert out.startswith("Exported static mesh SM_Table to C:/x/SM_Table.fbx")
    assert "min (-50.0, -30.0, 0.0), max (90.0, 60.0, 70.0)" in out
    assert 'StaticMeshTools.import_file(folder_path="/Game/Props", asset_name="SM_Table"' in out
    assert "set_nanite_enabled" in out and "generate_convex_collisions" in out


def test_verify_after_export(export):
    _tool(name="Table")
    assert "OK" in _tool(name="Table", action="verify", unreal_bounds=UE_STATIC)
    assert "NOT OK" in _tool(name="Table", action="verify",
                             unreal_bounds={"min": {"x": 0, "y": 0, "z": 0}, "max": {"x": 1, "y": 1, "z": 1}})


def test_verify_needs_an_export_first(export):
    assert _tool(name="Chair", action="verify", unreal_bounds=UE_STATIC).startswith("Error: nothing exported")


def test_bad_kind_never_reaches_blender(export):
    assert _tool(name="Table", kind="vehicle").startswith("Error: kind must be")
    assert export == []


@pytest.mark.parametrize("moves, expected", [
    ({"type": "hinge", "axis": "z", "range": [-100, 0]}, "animate relative rotation Yaw from 0 to 100 degrees"),
    ({"type": "hinge", "axis": "-z", "range": [-100, 0]}, "Yaw from -100 to 0 degrees"),
    ({"type": "hinge", "axis": "x", "range": [0, 80]}, "Roll from 0 to 80 degrees"),
    ({"type": "hinge", "axis": "y", "range": [0, 80]}, "Pitch from -80 to 0 degrees"),
    ({"type": "slide", "axis": "y", "range": [-0.4, 0]}, "slides from relative location (0.0, 40.0, 0.0) cm to (0.0, 0.0, 0.0) cm"),
])
def test_moving_parts_are_described_in_unreal_terms(moves, expected):
    text = ue.unreal_motion({"moves": moves, "pivot_m": [-0.39, -0.058, 0.0]})
    assert text.startswith("place at (-39.0, 5.8, 0.0) cm;"), text
    assert expected in text, text


def test_export_reply_lists_the_moving_parts():
    result = {"name": "Door", "kind": "static", "asset": "SM_Door", "file": "/x/SM_Door.fbx", "triangles": 10,
              "expected_bounds_cm": ue.blender_to_unreal_cm([0, 0, 0], [1, 1, 1]),
              "moving": [{"part": "Leaf", "asset": "SM_Door_Leaf", "file": "/x/SM_Door_Leaf.fbx",
                          "moves": {"type": "hinge", "axis": "z", "range": [-100, 0]}, "pivot_m": [-0.39, -0.058, 0]}]}
    text = ue.format_export(result, "/Game/Roxy")
    assert "- SM_Door_Leaf (/x/SM_Door_Leaf.fbx): place at (-39.0, 5.8, 0.0) cm; animate relative rotation Yaw" in text
    assert "Import the moving parts the same way" in text
