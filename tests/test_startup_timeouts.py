"""A Blender that accepts TCP but never replies must not block MCP startup."""
import asyncio
import inspect
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time

import pytest

from blender_mcp import server
from blender_mcp.addon_manager import EXPECTED_ADDON_PROTOCOL_VERSION


@pytest.fixture
def silent_blender(monkeypatch):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.1)
    stopped = threading.Event()
    clients = []
    state = {"respond": False, "commands": []}

    def handle(client):
        client.settimeout(0.1)
        while not stopped.is_set():
            try:
                data = client.recv(8192)
                if not data:
                    break
                command = json.loads(data)["type"]
                state["commands"].append(command)
                if state["respond"]:
                    result = {"protocol_version": EXPECTED_ADDON_PROTOCOL_VERSION}
                    client.sendall(json.dumps({"status": "success", "result": result}).encode())
            except socket.timeout:
                continue
            except OSError:
                break

    workers = []

    def accept():
        while not stopped.is_set():
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            clients.append(client)
            worker = threading.Thread(target=handle, args=(client,), daemon=True)
            workers.append(worker)
            worker.start()

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    port = listener.getsockname()[1]
    monkeypatch.setattr(server, "CLI_HOST", "127.0.0.1")
    monkeypatch.setattr(server, "CLI_PORT", port)
    monkeypatch.setattr(server, "_blender_connection", None)
    monkeypatch.setattr(server, "_addon_handshake", None)
    monkeypatch.setattr(server, "_addon_handshake_checked", False)
    state["port"] = port
    yield state
    if server._blender_connection:
        server._blender_connection.disconnect()
    stopped.set()
    listener.close()
    for client in clients:
        client.close()
    thread.join(1)
    for worker in workers:
        worker.join(1)


def test_initialize_and_list_tools_do_not_contact_busy_blender(silent_blender):
    env = {**os.environ, "BLENDER_HOST": "127.0.0.1", "BLENDER_PORT": str(silent_blender["port"])}
    process = subprocess.Popen(
        [sys.executable, "-c", "from blender_mcp.server import main; main()"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", env=env,
    )
    replies = queue.Queue()

    def read():
        for line in process.stdout:
            replies.put(json.loads(line))

    reader = threading.Thread(target=read, daemon=True)
    reader.start()

    def send(method, request_id=None, params=None):
        message = {"jsonrpc": "2.0", "method": method}
        if request_id is not None:
            message["id"] = request_id
        if params is not None:
            message["params"] = params
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    try:
        started = time.monotonic()
        send("initialize", 1, {"protocolVersion": "2025-11-25", "capabilities": {},
                               "clientInfo": {"name": "test", "version": "1"}})
        assert replies.get(timeout=3)["id"] == 1
        send("notifications/initialized")
        send("tools/list", 2)
        reply = replies.get(timeout=3)
        assert reply["id"] == 2 and reply["result"]["tools"]
        assert time.monotonic() - started < 6
        assert not silent_blender["commands"]
    finally:
        process.terminate()
        process.wait(timeout=5)
        process.stdin.close()
        reader.join(1)
        process.stdout.close()


def test_status_times_out_and_handshake_can_retry(silent_blender, caplog):
    started = time.monotonic()
    reply = asyncio.run(server.get_addon_status(None))
    assert 4.5 <= time.monotonic() - started < 10.5
    assert "接続を受け付けていますが応答しません" in reply
    assert "ダイアログやモーダル操作" in reply
    assert "will retry" in caplog.text
    assert server._addon_handshake_checked is False
    assert server._blender_connection.sock is None
    silent_blender["respond"] = True
    server.get_blender_connection()
    assert server._addon_handshake_checked is True
    assert server._addon_handshake.up_to_date is True


def test_command_timeout_includes_waiting_for_socket_lock(silent_blender):
    connection = server.BlenderConnection("127.0.0.1", silent_blender["port"])
    connection._lock.acquire()
    try:
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            connection.send_command("ping", timeout=0.05)
        assert time.monotonic() - started < 0.5
    finally:
        connection._lock.release()
    assert inspect.signature(connection.send_command).parameters["timeout"].default == 180.0


def test_short_command_timeout_closes_socket(silent_blender):
    connection = server.BlenderConnection("127.0.0.1", silent_blender["port"])
    with pytest.raises(TimeoutError):
        connection.send_command("ping", timeout=0.05)
    assert connection.sock is None


def test_status_integrations_share_the_ten_second_budget(monkeypatch):
    from unittest.mock import Mock

    connection = Mock()
    connection.send_command.side_effect = TimeoutError("busy")
    monkeypatch.setattr(server, "get_blender_connection", lambda **kwargs: connection)
    monkeypatch.setattr(server, "_maybe_handshake_addon", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_addon_handshake", server.handshake_addon(Mock()))
    reply = asyncio.run(server.get_addon_status(None))
    assert "応答しません" in reply
    assert 0 < connection.send_command.call_args.kwargs["timeout"] <= 10
