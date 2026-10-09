"""uv_bake: unwrap an asset, check its UVs and bake its textures."""

import asyncio

import pytest

from blender_mcp import server, uv_bake

CHECK_OK = {"Cab Paint": {"resolution": 1024, "density": 436, "used": 55.0, "stretched": 0.0, "overlap": 0.0,
                          "too_close": 0.0, "problems": []}}
CHECK_BAD = {"Cab Paint": dict(CHECK_OK["Cab Paint"], overlap=12.0,
                               problems=["12.0% of the used area overlaps another island"])}


@pytest.fixture
def blender(monkeypatch):
    calls, replies = [], {}

    def run(script, args, changes=False):
        calls.append((args, changes))
        return replies[args["action"]]

    monkeypatch.setattr(server, "_run_script", run)
    return calls, replies


def _tool(**kw):
    return asyncio.run(server.uv_bake(None, **kw))


def test_unwrap_reports_density_resolutions_and_the_check(blender):
    calls, replies = blender
    replies["unwrap"] = {"density": 436, "sets": {"Cab Paint": 1024, "Steel": 256},
                         "objects": {"Cab Paint": ["Cab_Body"], "Steel": ["Cab_Knob"]}, "not_flat": 0,
                         "frozen": ["Cab_Shelf"], "checks": CHECK_OK}
    reply = _tool(name="Cabinet", resolution=1024)
    assert reply.startswith('Unwrapped Cabinet into the "Unwrap" UV map: 436 px/m everywhere; resolution per '
                            "texture set: Cab Paint 1024, Steel 256.")
    assert "Geometry Nodes output made real mesh (originals hidden as <name>_GN): Cab_Shelf" in reply
    assert "- Cab Paint: 1024 px, 436 px/m, 55.0% used" in reply and reply.endswith('uv_bake(action="bake").')
    assert calls[0][0]["resolution"] == 1024 and calls[0][1]


def test_check_lists_problems(blender):
    _, replies = blender
    replies["check"] = {"checks": CHECK_BAD}
    reply = _tool(name="Cabinet", action="check")
    assert reply.startswith("UVs of Cabinet: NOT OK")
    assert "problem: 12.0% of the used area overlaps another island" in reply


def test_bake_for_unreal_says_how_to_import(blender):
    _, replies = blender
    replies["bake"] = {"dir": "/x/Baked", "files": {"Cab Paint": {"BaseColor": "a", "Normal": "b",
                                                                  "OcclusionRoughnessMetallic": "c"}}}
    reply = _tool(name="Cabinet", action="bake", target="unreal")
    assert "- Cab Paint: BaseColor, Normal, OcclusionRoughnessMetallic" in reply
    assert "sRGB off" in reply and 'normal_format="DirectX")' in reply


def test_an_old_addon_is_named(blender):
    _, replies = blender
    replies["unwrap"] = {"error": "old addon", "old": True}
    assert "too old" in _tool(name="Cabinet")


@pytest.mark.parametrize("kw, expected", [
    ({"action": "smart"}, "action must be one of"),
    ({"target": "unity"}, 'target must be "blender" or "unreal"'),
    ({"resolution": 1000}, "resolution must be a power of two"),
])
def test_bad_input_never_reaches_blender(blender, kw, expected):
    assert expected in _tool(name="Cabinet", **kw)
    assert blender[0] == []


def test_format_unwrap_asks_for_seams_where_it_could_not_open():
    text = uv_bake.format_unwrap("Rock", {"density": 300, "sets": {"Rock": 2048}, "not_flat": 2,
                                          "checks": CHECK_BAD})
    assert "2 regions could not be opened flat" in text and text.endswith("Fix the problems above before texturing.")
