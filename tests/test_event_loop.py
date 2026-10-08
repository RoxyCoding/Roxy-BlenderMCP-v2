"""A slow Blender must not stall the MCP event loop.

Tools wait on Blender for as long as it takes, up to minutes. If they wait on
the event loop itself, pings, cancellations and the Viewport app's polls all
stop answering until Blender does.
"""
import asyncio
import time
from unittest.mock import Mock

import pytest

from blender_mcp import server

BLENDER_DELAY_S = 0.5


@pytest.fixture
def slow_blender(monkeypatch):
    def send_command(command_type, params=None, **kwargs):
        time.sleep(BLENDER_DELAY_S)
        return {"result": "ok", "version": 1, "scene": "Scene"}

    connection = Mock()
    connection.send_command.side_effect = send_command
    monkeypatch.setattr(server, "get_blender_connection", lambda **kwargs: connection)
    return connection


async def _ticks_while(coro) -> int:
    """How often the loop got a turn while `coro` ran."""
    ticks = 0
    done = asyncio.Event()

    async def ticker():
        nonlocal ticks
        while not done.is_set():
            ticks += 1
            await asyncio.sleep(0.01)

    task = asyncio.create_task(ticker())
    try:
        await coro
    finally:
        done.set()
        await task
    return ticks


@pytest.mark.parametrize("call", [
    lambda: server.execute_blender_code(None, code="print(1)"),
    lambda: server.scene_state(),
    lambda: server.checkpoint(None, action="save"),
])
def test_tools_wait_for_blender_off_the_event_loop(slow_blender, call):
    ticks = asyncio.run(_ticks_while(call()))
    # A blocked loop gets one turn at most; a free one about delay / 10ms.
    assert ticks >= 10
    assert slow_blender.send_command.called


def test_tools_no_longer_ask_for_user_prompt():
    tools = asyncio.run(server.mcp.list_tools())
    assert not [t.name for t in tools if "user_prompt" in t.inputSchema.get("properties", {})]
