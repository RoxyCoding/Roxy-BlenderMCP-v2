"""
`roxy-blender-mcp update`: bring the installed Blender addon up to this checkout.

Roxy-BlenderMCP isn't on PyPI and never updates itself: MCP clients run the
server from this checkout (`uv run --directory <checkout> roxy-blender-mcp`),
so updating the server means updating the checkout. This copies the
checkout's addon over every installed copy, and points out MCP clients still
configured to run upstream's package.
"""

from __future__ import annotations

from .addon_manager import ADDON_DISPLAY_NAME, addon_version_label, cli_command, update_installed_addons
from .setup_cli import OUTDATED, blender_is_running, client_state, detect_clients


def _update_addon(dry_run: bool) -> tuple[bool, bool]:
    """Print what happened to each installed addon. Returns (any updated, any failed)."""
    print("Blender addon:")
    try:
        results = update_installed_addons(dry_run=dry_run)
    except FileNotFoundError as e:
        print(f"  {e}")
        return False, True
    if not results:
        print(f"  Not installed. Run `{cli_command('setup')}` to install and enable it.")
        return False, False

    verb = "would update" if dry_run else "updated"
    for r in results:
        if r.action == "updated":
            print(f"  ✓ {verb} {r.path} (was {addon_version_label(r.installed)})")
        elif r.action == "current":
            print(f"  {r.path}: already up to date")
        elif r.action == "newer":
            print(f"  {r.path}: {addon_version_label(r.installed)} is newer than this checkout's, left alone")
        else:
            print(f"  ✗ {r.path}: {r.detail}")
    updated = any(r.action == "updated" for r in results)
    if updated and not dry_run:
        print("  (the previous file is kept beside each one as .bak)")
    return updated, any(r.action == "failed" for r in results)


def _upstream_clients() -> list[str]:
    """Clients still configured to run upstream's mcp-for-blender (or blender-mcp) package."""
    names: list[str] = []
    for client in detect_clients():
        try:
            if client_state(client).status == OUTDATED:
                names.append(client.name)
        except Exception:
            continue
    return names


def run_update(dry_run: bool = False) -> int:
    print(f"{ADDON_DISPLAY_NAME} update" + (" (dry run: nothing will be changed)" if dry_run else ""))
    print()
    print("Server: runs from this checkout and never updates itself; update the checkout to update it.")
    print()

    addon_updated, addon_failed = _update_addon(dry_run)
    print()

    upstream = _upstream_clients()
    if upstream:
        print(f"Still running upstream's package: {', '.join(upstream)}.")
        print(f"  Run `{cli_command('setup')}` to switch them to this fork.")
        print()

    if dry_run:
        return 0

    print("Next:")
    if addon_updated:
        if blender_is_running():
            print("  • Blender is open: restart it, or Preferences → Add-ons → disable and re-enable")
            print(f"    'Interface: {ADDON_DISPLAY_NAME}', to load the new addon.")
        else:
            print("  • Open Blender. The new addon loads on launch.")
    else:
        print("  • Nothing to do: the addon is up to date.")
    return 1 if addon_failed else 0
