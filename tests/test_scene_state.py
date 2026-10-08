import ast
import asyncio
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conftest import ROOT_ADDON
from blender_mcp import server, session_rules
from blender_mcp.addon_manager import EXPECTED_ADDON_PROTOCOL_VERSION, get_bundled_addon_path
from test_addon_autostart import _load_autostart_helpers


def load_state_helpers():
    namespace, bpy, timers, scene = _load_autostart_helpers()
    tree = ast.parse(ROOT_ADDON.read_text(encoding="utf-8"))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {"_blendermcp_depsgraph_post", "_unregister_edit_capture_handlers"}]
    addon_server = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                        and node.name == "BlenderMCPServer")
    functions.append(next(node for node in addon_server.body if isinstance(node, ast.FunctionDef)
                          and node.name == "get_scene_state"))
    namespace["suppress"] = suppress
    bpy.app.handlers.undo_post = []
    bpy.app.handlers.redo_post = []
    namespace["_blendermcp_undo_post"] = lambda *args: None
    namespace["_blendermcp_redo_post"] = lambda *args: None
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<addon>", "exec"), namespace)
    bpy.data = SimpleNamespace(filepath="", is_dirty=True)
    scene.name = "Scene"
    bpy.context.mode = "OBJECT"
    bpy.context.view_layer = SimpleNamespace(objects=SimpleNamespace(active=None))
    bpy.context.selected_objects = []
    return namespace, bpy


def test_state_counter_tracks_depsgraph_and_file_loads_without_recording():
    namespace, bpy = load_state_helpers()
    namespace["_edit_recorder"] = Mock()
    namespace["_blendermcp_depsgraph_post"](bpy.context.scene, None)
    namespace["_blendermcp_depsgraph_post"](bpy.context.scene, None)
    namespace["_blendermcp_load_post"](None)
    assert namespace["get_scene_state"](None) == {
        "version": 3, "file": None, "is_dirty": True, "scene": "Scene",
        "mode": "OBJECT", "active": None, "selected_count": 0,
    }
    namespace["_edit_recorder"].poll_operators.assert_not_called()
    bpy.data.filepath = "C:/scenes/example.blend"
    bpy.data.is_dirty = False
    bpy.context.view_layer.objects.active = SimpleNamespace(name="Cube")
    bpy.context.selected_objects = [object(), object()]
    bpy.context.mode = "EDIT_MESH"
    state = namespace["get_scene_state"](None)
    assert state["file"] == bpy.data.filepath and state["is_dirty"] is False
    assert state["active"] == "Cube" and state["selected_count"] == 2
    assert state["mode"] == "EDIT_MESH"
    assert state["version"] == 3  # polling does not change the counter


def test_scene_handler_survives_telemetry_cleanup_and_unregisters_cleanly():
    namespace, bpy = load_state_helpers()
    namespace["_blendermcp_register_auto_start"]()
    namespace["_blendermcp_register_auto_start"]()
    namespace["_unregister_edit_capture_handlers"]()
    assert bpy.app.handlers.depsgraph_update_post == [namespace["_blendermcp_depsgraph_post"]]
    namespace["_blendermcp_unregister_auto_start"]()
    assert bpy.app.handlers.depsgraph_update_post == []
    assert bpy.app.handlers.load_post == []


STATE = {"version": 7, "file": None, "is_dirty": True, "scene": "Scene",
         "mode": "OBJECT", "active": "Cube", "selected_count": 1}


@pytest.mark.parametrize("since,changed", [(0, True), (6, True), (7, False), (8, False)])
def test_scene_state_returns_structured_data_and_short_timeout(monkeypatch, since, changed):
    connection = Mock()
    connection.send_command.return_value = STATE
    get_connection = Mock(return_value=connection)
    monkeypatch.setattr(server, "get_blender_connection", get_connection)
    result = asyncio.run(server.scene_state(since))
    assert result.structuredContent == {**STATE, "changed": changed}
    assert STATE == {k: v for k, v in result.structuredContent.items() if k != "changed"}
    get_connection.assert_called_once_with(handshake=False, timeout=5.0)
    args, kwargs = connection.send_command.call_args
    assert args == ("get_scene_state",)
    assert kwargs["read_only"] is True and 0 < kwargs["timeout"] <= 5.0


@pytest.mark.parametrize("error,expected", [
    (Exception("Unknown command type: get_scene_state"), "Update the Blender addon"),
    (TimeoutError("busy Blender"), "Could not read scene state"),
])
def test_scene_state_reports_old_addon_and_timeout(monkeypatch, error, expected):
    connection = Mock()
    connection.send_command.side_effect = error
    monkeypatch.setattr(server, "get_blender_connection", lambda **kwargs: connection)
    result = asyncio.run(server.scene_state())
    assert result.isError is True and result.structuredContent is None
    assert expected in result.content[0].text


def test_scene_state_is_app_only_and_does_not_attach_session_rules(monkeypatch):
    connection = Mock()
    connection.send_command.return_value = STATE
    monkeypatch.setattr(server, "get_blender_connection", lambda **kwargs: connection)
    monkeypatch.setattr(session_rules, "_delivered", set())
    monkeypatch.setattr(session_rules, "session_key", lambda ctx: 123)
    result = asyncio.run(server.mcp.call_tool("scene_state", {}))
    assert len(result.content) == 1 and not session_rules._delivered
    tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
    tool = tools["scene_state"]
    assert tool.annotations.readOnlyHint is True
    assert tool.meta["ui"]["visibility"] == ["app"]
    assert tool.inputSchema["properties"]["since"]["default"] == 0
    assert tool.inputSchema["properties"]["since"]["type"] == "integer"


def test_scene_state_protocol_and_command_registration_match():
    source = ROOT_ADDON.read_text(encoding="utf-8")
    assert ROOT_ADDON.read_bytes() == get_bundled_addon_path().read_bytes()
    assert f"ADDON_PROTOCOL_VERSION = {EXPECTED_ADDON_PROTOCOL_VERSION}" in source
    tree = ast.parse(source)
    handlers = next(node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                    and any(getattr(target, "id", None) == "handlers" for target in node.targets)
                    and isinstance(node.value, ast.Dict))
    commands = {key.value: value for key, value in zip(handlers.keys, handlers.values)}
    assert commands["get_scene_state"].attr == "get_scene_state"


def test_scene_state_is_filtered_for_model_only_clients(monkeypatch):
    monkeypatch.setattr(server.mcp, "get_context", lambda: SimpleNamespace(session=None))
    monkeypatch.setattr(server, "supports_apps", lambda session: False)
    names = {tool.name for tool in asyncio.run(server._list_tools_for_client())}
    assert "scene_state" not in names
    monkeypatch.setattr(server, "supports_apps", lambda session: True)
    names = {tool.name for tool in asyncio.run(server._list_tools_for_client())}
    assert "scene_state" in names
