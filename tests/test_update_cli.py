"""Tests for `roxy-blender-mcp update` (no network, uv or Blender touched)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from blender_mcp import update_cli
from blender_mcp.addon_manager import (
    AddonUpdate,
    addon_release_key,
    get_bundled_addon_path,
    update_installed_addons,
)
from blender_mcp.update_cli import run_update

BUNDLED = get_bundled_addon_path().read_text(encoding="utf-8")
BUNDLED_KEY = addon_release_key(BUNDLED)


def _with_version(version, protocol) -> str:
    text = re.sub(r'"version": \(\d+, \d+(?:, \d+)?\)', f'"version": {version}', BUNDLED, count=1)
    return re.sub(r"^ADDON_PROTOCOL_VERSION = \d+", f"ADDON_PROTOCOL_VERSION = {protocol}", text, count=1, flags=re.M)


def _install(addons: Path, name: str, text: str) -> Path:
    addons.mkdir(parents=True, exist_ok=True)
    path = addons / name
    path.write_text(text, encoding="utf-8")
    return path


# --- addon -------------------------------------------------------------------

def test_release_key_reads_bundled_addon():
    assert BUNDLED_KEY is not None
    assert addon_release_key(_with_version((2, 0, 3), 40)) == (2, 0, 3, 40)
    assert addon_release_key("print('hello')") is None


def test_updates_older_addon_in_place_with_backup(tmp_path):
    old = _with_version((1, 0), 1)
    path = _install(tmp_path, "addon.py", old)
    [result] = update_installed_addons([tmp_path])
    assert result.action == "updated" and result.installed == (1, 0, 0, 1)
    assert path.read_text(encoding="utf-8") == BUNDLED
    assert path.with_suffix(".py.bak").read_text(encoding="utf-8") == old
    # Writes over the existing file only; no second copy under another name.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["addon.py", "addon.py.bak"]


def test_updates_addon_from_before_the_rename(tmp_path):
    old = 'bl_info = {\n    "name": "Blender MCP",\n    "version": (1, 2),\n}\n'
    path = _install(tmp_path, "blender_mcp.py", old)
    [result] = update_installed_addons([tmp_path])
    assert result.action == "updated"
    assert path.read_text(encoding="utf-8") == BUNDLED


def test_never_downgrades_addon_from_main(tmp_path):
    major, minor, patch, protocol = BUNDLED_KEY
    newer = _with_version((major, minor + 1), protocol)
    path = _install(tmp_path, "blender_mcp.py", newer)
    [result] = update_installed_addons([tmp_path])
    assert result.action == "newer"
    assert path.read_text(encoding="utf-8") == newer


def test_same_release_with_local_edits_is_left_alone(tmp_path):
    edited = BUNDLED + "\n# my tweak\n"
    path = _install(tmp_path, "blender_mcp.py", edited)
    [result] = update_installed_addons([tmp_path])
    assert result.action == "current"
    assert path.read_text(encoding="utf-8") == edited


def test_dry_run_writes_nothing(tmp_path):
    old = _with_version((1, 0), 1)
    path = _install(tmp_path, "blender_mcp.py", old)
    [result] = update_installed_addons([tmp_path], dry_run=True)
    assert result.action == "updated"
    assert path.read_text(encoding="utf-8") == old
    assert not path.with_suffix(".py.bak").exists()


# --- run_update --------------------------------------------------------------

@pytest.fixture
def quiet(monkeypatch):
    """No clients, Blender or addon installs on the test machine leak in, and
    nothing may reach the network or start a process."""
    monkeypatch.setattr(update_cli, "detect_clients", lambda: [])
    monkeypatch.setattr(update_cli, "blender_is_running", lambda: False)
    monkeypatch.setattr(update_cli, "update_installed_addons", lambda dry_run=False: [])
    import httpx
    import subprocess
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: pytest.fail("must not check PyPI"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("must not re-run itself"))


def test_never_updates_the_server_itself(quiet, capsys):
    assert run_update() == 0
    out = capsys.readouterr().out
    assert "never updates itself" in out
    assert "roxy-blender-mcp setup" in out  # addon not installed -> points at setup


def test_updated_addon_says_how_to_load_it(quiet, monkeypatch, capsys):
    monkeypatch.setattr(update_cli, "update_installed_addons",
                        lambda dry_run=False: [AddonUpdate(Path("/a/blender_mcp.py"), "updated", (1, 8, 0, 13))])
    assert run_update() == 0
    out = capsys.readouterr().out
    assert "updated" in out and "Open Blender" in out


def test_points_out_clients_still_on_upstream(quiet, monkeypatch, capsys):
    monkeypatch.setattr(update_cli, "detect_clients", lambda: [type("C", (), {"name": "Cursor"})()])
    monkeypatch.setattr(update_cli, "client_state", lambda c: type("S", (), {"status": update_cli.OUTDATED})())
    assert run_update(dry_run=True) == 0
    out = capsys.readouterr().out
    assert "Still running upstream's package: Cursor." in out
