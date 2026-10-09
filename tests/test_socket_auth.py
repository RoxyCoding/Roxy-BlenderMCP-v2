"""The addon socket runs arbitrary Python, so only the MCP server may use it.

The addon publishes a fresh token on start; the server reads it and sends it
with every command. Also covers the framing fixes: malformed input gets an
error instead of stalling the connection, and back-to-back commands in one
chunk are all handled.
"""
from __future__ import annotations

import json
import os
import socket
import threading

import pytest

from blender_mcp import server as mcp_server
from test_server_threading import BlenderMCPServer, _make_server, _pump
from test_socket_unicode import _ScriptedSocket


def _roundtrip(server, payload: dict) -> dict:
    with socket.create_connection(("localhost", server.port), timeout=5) as client:
        client.sendall(json.dumps(payload).encode())
        threading.Thread(target=_pump, args=(server,), daemon=True).start()
        client.settimeout(5)
        return json.loads(client.recv(8192).decode())


@pytest.fixture
def running():
    server = _make_server()
    server.start()
    yield server
    server.stop()


def test_start_publishes_a_token_and_stop_removes_it():
    server = _make_server()
    server.start()
    path = server._token_path()
    try:
        with open(path, encoding="utf-8") as f:
            assert f.read() == server.token
        assert mcp_server.read_blender_token(server.port) == server.token
    finally:
        server.stop()
    assert not os.path.exists(path)
    assert mcp_server.read_blender_token(server.port) is None


def test_commands_without_the_token_are_refused(running):
    for payload in ({"type": "ping"}, {"type": "ping", "auth": "guess"}):
        response = _roundtrip(running, payload)
        assert response["status"] == "error"
        assert "Unauthorized" in response["message"]
    assert running.command_queue.empty()


def test_commands_with_the_token_run(running):
    response = _roundtrip(running, {"type": "ping", "auth": running.token})
    assert response == {"status": "success", "result": {"echo": "ping"}}


def test_the_token_is_not_passed_on_to_the_command(running):
    seen = []
    running.execute_command = lambda command: seen.append(command) or {"status": "success", "result": {}}
    _roundtrip(running, {"type": "ping", "auth": running.token})
    assert seen == [{"type": "ping"}]


def test_auth_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("BLENDERMCP_ALLOW_UNAUTHENTICATED", "1")
    server = _make_server()
    server.start()
    try:
        assert server.token is None
        assert _roundtrip(server, {"type": "ping"})["status"] == "success"
    finally:
        server.stop()


def test_the_server_picks_up_the_published_token_on_connect(running):
    connection = mcp_server.BlenderConnection("localhost", running.port)
    try:
        assert connection.connect(timeout=5)
        assert connection.token == running.token
    finally:
        connection.disconnect()


def test_the_env_token_wins_over_the_file(monkeypatch, running):
    monkeypatch.setenv("BLENDER_MCP_TOKEN", "from-env")
    assert mcp_server.read_blender_token(running.port) == "from-env"


def test_server_and_addon_agree_end_to_end(running):
    connection = mcp_server.BlenderConnection("localhost", running.port)
    pump = threading.Thread(target=_pump, args=(running,), daemon=True)
    pump.start()
    try:
        assert connection.send_command("ping", timeout=5) == {"echo": "ping"}
    finally:
        connection.disconnect()


# ---------------------------------------------------------------- framing

def _queued(chunks):
    server = BlenderMCPServer(port=0)
    server.running = True
    sock = _ScriptedSocket(chunks)
    server._handle_client(sock)
    out = []
    while not server.command_queue.empty():
        out.append(server.command_queue.get_nowait()[0])
    return out


def test_back_to_back_commands_in_one_chunk_are_all_queued():
    chunk = json.dumps({"type": "a"}).encode() + json.dumps({"type": "b"}).encode()
    assert [c["type"] for c in _queued([chunk])] == ["a", "b"]


@pytest.mark.parametrize("payload", [
    {"type": "x", "params": {"flag": True, "off": False, "none": None}},
    {"type": "x", "params": {"n": -12.5e-3}},
])
def test_a_value_cut_at_any_byte_waits_for_the_rest(payload):
    data = json.dumps(payload).encode()
    for i in range(1, len(data)):
        assert _queued([data[:i], data[i:]]) == [payload], f"split at {i}: {data[:i]!r}"


@pytest.mark.parametrize("garbage", [b"hello", b'{"type": x}', b"[1, 2]", b'{"type": "a"} junk', b"\xff\xfe{}"])
def test_malformed_input_is_answered_not_left_hanging(garbage):
    queued = _queued([garbage, json.dumps({"type": "after"}).encode()])
    assert queued[-1] == {"type": "after"}, "the connection stalled after bad input"
    assert any(c["type"] == "__invalid__" for c in queued)


def test_invalid_input_gets_an_error_reply():
    server = BlenderMCPServer(port=0)
    server.running = True
    sock = _ScriptedSocket([b"hello"])
    server._handle_client(sock)
    server.running = True
    server._drain_command_queue()
    reply = json.loads(sock.sent[0])
    assert reply["status"] == "error" and reply["message"].startswith("Invalid command")
