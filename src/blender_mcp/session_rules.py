"""Server instructions that don't fit Claude Code's 2048-character cap.

Claude Code cuts every MCP server's instructions at 2048 characters, silently.
SERVER_INSTRUCTIONS keeps what the model needs before its first call; the rest
lives in session_rules.md and rides on the first tool reply of each client
session, where no such cap applies. The instructions tell the model to expect it.
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache
from importlib import resources
from typing import Any

from mcp.types import CallToolResult, TextContent

logger = logging.getLogger("BlenderMCPServer")

_delivered: set[int] = set()
_lock = threading.Lock()


@lru_cache(maxsize=1)
def text() -> str:
    return resources.files("blender_mcp").joinpath("session_rules.md").read_text(encoding="utf-8").strip()


def session_key(ctx: Any) -> int | None:
    try:
        return id(ctx.request_context.session)
    except Exception:
        return None


def attach(result: Any, key: int | None) -> Any:
    """Append the rules to the first tool reply of a session; return other replies unchanged.

    A reply the rules can't be added to (structured-only) leaves them for the
    next call instead of marking them delivered.
    """
    if key is None:
        return result
    with _lock:
        # Claimed before building the reply, so two concurrent first calls can't both carry it.
        if key in _delivered:
            return result
        _delivered.add(key)
    note = TextContent(type="text", text="\n\n---\n" + text())
    if isinstance(result, CallToolResult):
        return result.model_copy(update={"content": [*result.content, note]})
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], (list, tuple)):
        return ([*result[0], note], result[1])
    if isinstance(result, (list, tuple)):
        return [*result, note]
    with _lock:
        _delivered.discard(key)
    return result


def reset_for_tests() -> None:
    with _lock:
        _delivered.clear()
