"""The session rules ride on the first model-facing tool reply of each client session."""

import asyncio
import types

import pytest
from mcp.types import CallToolResult, TextContent

from blender_mcp import server, session_rules

RULES = session_rules.text()


@pytest.fixture(autouse=True)
def fresh():
    session_rules.reset_for_tests()
    yield
    session_rules.reset_for_tests()


def _as_session(monkeypatch, session):
    ctx = types.SimpleNamespace(request_context=types.SimpleNamespace(session=session))
    monkeypatch.setattr(server.mcp, "get_context", lambda: ctx)


def _texts(result):
    content = result.content if isinstance(result, CallToolResult) else (
        result[0] if isinstance(result, tuple) else result)
    return [c.text for c in content if isinstance(c, TextContent)]


def _call(name, args):
    return asyncio.run(server.mcp.call_tool(name, args))


def test_first_reply_of_a_session_carries_the_rules_once(monkeypatch):
    _as_session(monkeypatch, object())
    first = _texts(_call("get_guide", {"topic": "rigging"}))
    second = _texts(_call("get_guide", {"topic": "rigging"}))
    assert any(RULES in t for t in first)
    assert not any(RULES in t for t in second)


def test_each_session_gets_them(monkeypatch):
    _as_session(monkeypatch, object())
    _call("get_guide", {"topic": "bpy"})
    _as_session(monkeypatch, object())
    assert any(RULES in t for t in _texts(_call("get_guide", {"topic": "bpy"})))


def test_app_only_tools_dont_use_up_the_delivery(monkeypatch):
    _as_session(monkeypatch, object())
    app_only = next(t.name for t in server.mcp._tool_manager.list_tools() if server.is_app_only(t))
    monkeypatch.setattr(server.mcp._tool_manager, "call_tool",
                        lambda *a, **k: asyncio.sleep(0, result=[TextContent(type="text", text="app")]))
    assert _texts(_call(app_only, {})) == ["app"]
    assert any(RULES in t for t in _texts(_call("get_guide", {"topic": "bpy"})))


@pytest.mark.parametrize("result", [
    [TextContent(type="text", text="plain")],
    CallToolResult(content=[TextContent(type="text", text="image tool")]),
    ([TextContent(type="text", text="structured")], {"x": 1}),
])
def test_every_reply_shape_takes_the_rules(result):
    out = session_rules.attach(result, key=1)
    assert any(RULES in t for t in _texts(out))
    if isinstance(result, tuple):
        assert out[1] == {"x": 1}


def test_a_reply_without_text_content_leaves_them_for_the_next_call():
    assert session_rules.attach({"only": "structured"}, key=2) == {"only": "structured"}
    assert any(RULES in t for t in _texts(session_rules.attach([], key=2)))


def test_unknown_session_gets_nothing():
    assert session_rules.attach([], key=None) == []
