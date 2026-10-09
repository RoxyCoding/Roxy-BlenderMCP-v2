"""Shared paths for the test suite.

These tests read the addon as a source file (it cannot be imported without
bpy). src/blender_mcp/bundled/addon.py is its only copy.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT_ADDON = REPO_ROOT / "src" / "blender_mcp" / "bundled" / "addon.py"


import pytest


@pytest.fixture(autouse=True)
def _isolated_token_dir(tmp_path, monkeypatch):
    """Keep addon auth tokens out of the real ~/.roxy-blender-mcp."""
    monkeypatch.setenv("ROXY_BLENDER_MCP_DIR", str(tmp_path / "roxy-blender-mcp"))
    monkeypatch.delenv("BLENDER_MCP_TOKEN", raising=False)
    monkeypatch.delenv("BLENDERMCP_ALLOW_UNAUTHENTICATED", raising=False)
