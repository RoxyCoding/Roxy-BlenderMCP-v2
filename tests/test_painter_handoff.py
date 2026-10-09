"""painter_handoff: an asset goes to Substance 3D Painter and its textures come back."""

import asyncio

import pytest

from blender_mcp import painter_handoff, server

EXPORTED = {"name": "Cabinet", "file": "/x/PainterExport/Cabinet.fbx", "dir": "/x/PainterExport",
            "texture_sets": {"Cab Paint": ["Cab_Body", "Cab_Door"], "Steel": ["Cab_Knob"]}, "warnings": []}


def _tool(**kw):
    return asyncio.run(server.painter_handoff(None, **kw))


@pytest.fixture
def blender(monkeypatch):
    calls = []

    def run(script, args, changes=False):
        calls.append((script, args, changes))
        if script is server.blender_scripts.PAINTER_EXPORT:
            return dict(EXPORTED)
        return {"name": "Cabinet", "materials": {"Cab Paint": ["color", "normal", "roughness"]},
                "without_textures": ["Steel"], "unmatched": ["notes.png"]}

    monkeypatch.setattr(server, "_run_script", run)
    return calls


def test_export_for_blender_names_the_painter_steps(blender):
    reply = _tool(name="Cabinet")
    assert reply.startswith("Exported Cabinet for Painter: /x/PainterExport/Cabinet.fbx")
    assert "Cab Paint (Cab_Body, Cab_Door); Steel (Cab_Knob)" in reply
    assert 'create_project(mesh_path="/x/PainterExport/Cabinet.fbx", normal_map_format="OpenGL"' in reply
    assert 'preset="PBR Metallic Roughness"' in reply
    assert 'painter_handoff(action="import", name="Cabinet", textures_dir="/x/PainterExport/textures")' in reply
    (script, args, changes), = blender
    assert args == {"name": "Cabinet", "output_dir": None, "unwrap": True} and changes


def test_export_for_unreal_uses_directx_and_the_packed_preset(blender):
    reply = _tool(name="Cabinet", target="unreal")
    assert 'normal_map_format="DirectX"' in reply
    assert "Unreal packed preset" in reply and 'normal_format="DirectX"' in reply


def test_import_reports_what_was_rebuilt_and_what_is_missing(blender):
    reply = _tool(name="Cabinet", action="import", textures_dir="/x/tex", normal_format="DirectX")
    assert "- Cab Paint: color, normal, roughness" in reply
    assert "No files for: Steel" in reply and "Ignored files: notes.png" in reply
    assert blender[0][1] == {"name": "Cabinet", "textures_dir": "/x/tex", "normal_format": "DirectX"}


@pytest.mark.parametrize("kw, expected", [
    ({"action": "paint"}, "action must be one of"),
    ({"target": "unity"}, 'target must be "blender" or "unreal"'),
    ({"action": "import"}, "import needs textures_dir"),
    ({"action": "import", "textures_dir": "/x", "normal_format": "Vulkan"}, "normal_format must be"),
])
def test_bad_input_never_reaches_blender(blender, kw, expected):
    assert expected in _tool(name="Cabinet", **kw)
    assert blender == []


def test_format_import_with_nothing_matched():
    text = painter_handoff.format_import({"name": "Cabinet", "materials": {}, "without_textures": ["Steel"],
                                          "unmatched": []})
    assert text.startswith("No Painter textures matched the materials of Cabinet.")
