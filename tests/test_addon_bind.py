"""Regression tests for the add-on's listening socket.

On Windows SO_REUSEADDR let the add-on bind port 9876 while another server
(e.g. Blender's own "MCP" extension) was already listening there, so both
silently shared the port and commands could reach the wrong one. The add-on
must now refuse with a clear "port in use" error instead.
"""

from __future__ import annotations

import ast
import errno
import socket
import sys

import pytest

from conftest import ROOT_ADDON

_NAMES = {"_blendermcp_bind_listener", "_PORT_IN_USE_WINERRORS"}


def _load_bind_listener():
    tree = ast.parse(ROOT_ADDON.read_text(encoding="utf-8"))
    body = [
        node for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in _NAMES)
        or (isinstance(node, ast.Assign) and any(getattr(t, "id", "") in _NAMES for t in node.targets))
    ]
    assert len(body) == len(_NAMES)
    namespace = {"socket": socket, "sys": sys, "errno": errno}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(ROOT_ADDON), "exec"), namespace)
    return namespace["_blendermcp_bind_listener"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_binds_and_listens_on_a_free_port():
    bind = _load_bind_listener()
    port = _free_port()
    sock = bind("127.0.0.1", port)
    try:
        client = socket.create_connection(("127.0.0.1", port), timeout=2)
        client.close()
    finally:
        sock.close()


def test_refuses_a_port_another_server_already_listens_on():
    bind = _load_bind_listener()
    port = _free_port()
    other = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # how the other add-on binds
    other.bind(("127.0.0.1", port))
    other.listen(5)
    try:
        with pytest.raises(OSError) as info:
            bind("127.0.0.1", port)
        assert "already in use" in info.value.strerror
        assert info.value.errno == errno.EADDRINUSE
    finally:
        other.close()


@pytest.mark.skipif(sys.platform != "win32", reason="SO_EXCLUSIVEADDRUSE is Windows-only")
def test_others_cannot_hijack_the_port_afterwards():
    bind = _load_bind_listener()
    port = _free_port()
    sock = bind("127.0.0.1", port)
    intruder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    intruder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        with pytest.raises(OSError):
            intruder.bind(("127.0.0.1", port))
    finally:
        intruder.close()
        sock.close()


def test_reconnect_right_after_serving_a_client():
    """Disconnect -> Connect while the old connection is still in TIME_WAIT must work."""
    bind = _load_bind_listener()
    port = _free_port()
    sock = bind("127.0.0.1", port)
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    conn, _ = sock.accept()
    conn.sendall(b"{}")
    conn.close()  # server closes first -> the server side of the connection sits in TIME_WAIT
    client.recv(10)
    client.close()
    sock.close()
    again = bind("127.0.0.1", port)
    again.close()
