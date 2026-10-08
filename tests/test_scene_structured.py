import asyncio
import copy
import io
import json
import sys
from contextlib import redirect_stdout
from types import SimpleNamespace

import pytest

from blender_mcp import blender_scripts, server, session_rules


HEADER = {"scene": "Scene", "object_counts": {"mesh": 2}, "active": "Cube",
          "selected": ["Cube"], "selected_count": 1, "mode": "OBJECT"}
SETTINGS = {"file": "example.blend", "engine": "CYCLES", "frames": [1, 250, 1],
            "fps": 24, "resolution": [1920, 1080], "camera": None,
            "world_hdri": None, "unit_scale": 1.0}
OBJECT = {"name": "Cube", "type": "MESH",
          "fields": {"location": "at (0.0, 0.0, 0.0)", "size": "size 2.0x2.0x2.0"}}
DATA = {"header": HEADER, "objects": [OBJECT],
        "lines": ["Cube | mesh | at (0.0, 0.0, 0.0) | size 2.0x2.0x2.0"], "shown": 1, "total": 2}


@pytest.mark.parametrize("settings", [False, True])
def test_scene_text_is_unchanged_and_structure_matches_addon(monkeypatch, settings):
    data = copy.deepcopy(DATA)
    fields = ["size", "location"]
    if settings:
        fields.append("settings")
        data["header"]["settings"] = SETTINGS
    connection = SimpleNamespace(send_command=lambda *args, **kwargs: {
        "result": blender_scripts.RESULT_MARKER + json.dumps(data)})
    monkeypatch.setattr(server, "get_blender_connection", lambda: connection)
    result = asyncio.run(server.get_scene_info(None, fields=fields))
    assert result.content[0].text == server._format_scene_summary(data, fields)
    assert result.structuredContent == {
        **data["header"], "columns": ["name", "type", "location", "size"],
        "objects": [OBJECT], "shown": 1, "total": 2,
    }
    assert ("settings" in result.structuredContent) is settings


def test_session_rules_preserve_scene_structure(monkeypatch):
    monkeypatch.setattr(server, "_run_script", lambda *args: copy.deepcopy(DATA))
    monkeypatch.setattr(session_rules, "session_key", lambda ctx: 123)
    monkeypatch.setattr(session_rules, "_delivered", set())
    result = asyncio.run(server.mcp.call_tool("get_scene_info", {"fields": ["location", "size"]}))
    assert result.content[0].text == server._format_scene_summary(DATA, ["location", "size"])
    assert result.content[1].text.endswith(session_rules.text())
    assert result.structuredContent["objects"] == [OBJECT]


def test_scene_errors_still_return_text_only(monkeypatch):
    monkeypatch.setattr(server, "_run_script", lambda *args: {"error": "No object named 'missing'"})
    result = asyncio.run(server.mcp.call_tool("get_scene_info", {"root": "missing"}))
    assert result[0].text == "Error: No object named 'missing'"


def test_script_keeps_names_and_omitted_fields_unambiguous(monkeypatch):
    obj = SimpleNamespace(name="  Empty | marker", type="EMPTY", parent=None, children=[],
                          hide_get=lambda: False, hide_render=True,
                          matrix_world=SimpleNamespace(translation=SimpleNamespace(x=0, y=1, z=2)))
    scene = SimpleNamespace(name="Scene", objects=[obj])
    context = SimpleNamespace(scene=scene, mode="OBJECT", selected_objects=[obj],
                              view_layer=SimpleNamespace(objects=SimpleNamespace(active=obj)),
                              evaluated_depsgraph_get=lambda: None)
    monkeypatch.setitem(sys.modules, "bpy", SimpleNamespace(context=context))
    monkeypatch.setitem(sys.modules, "mathutils", SimpleNamespace(Vector=lambda v: v))
    output = io.StringIO()
    with redirect_stdout(output):
        exec(blender_scripts.build(blender_scripts.SCENE_SUMMARY,
                                   {"fields": ["location", "size", "hidden", "children"]}), {})
    data = blender_scripts.parse_result(output.getvalue())
    assert data["lines"] == ["  Empty | marker | empty | at (0.0, 1.0, 2.0) | hidden"]
    assert data["objects"] == [{"name": obj.name, "type": "EMPTY",
                                "fields": {"location": "at (0.0, 1.0, 2.0)", "hidden": "hidden"}}]
