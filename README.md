# Roxy-BlenderMCP

RoxyBlenderMCP is based on MCP for Blender by Siddharth Ahuja, licensed under the MIT License. This project is independently modified and maintained.

It connects an MCP client (Claude Desktop, Claude Code, Cursor, VS Code, Codex, ...) to a running Blender, so the assistant can build and edit scenes through Blender's Python API.

## How it differs from upstream

- **Its own name.** The package and command are `roxy-blender-mcp`, and the Blender addon shows up as "Roxy Blender MCP". It isn't published on PyPI: MCP clients run it from this checkout.
- **No data collection.** Telemetry, trajectory recording and the consent prompt are removed from the server, along with the `disable_telemetry` and `record_trajectory_feedback` tools and the `user_prompt` argument tools used to take. Nothing is sent anywhere.
- **No self-update.** The addon no longer downloads itself from upstream's GitHub, and `update` no longer checks PyPI, so nothing replaces this fork with upstream's code.
- **No AI model generation, no Premium.** Upstream's paid Premium service, Tripo, Hyper3D Rodin and Hunyuan3D are removed, and with them the `generate_3d` tool. Poly Pizza is removed too.
- **ambientCG.** CC0 PBR materials from [ambientCG](https://ambientcg.com) alongside Poly Haven, including Japanese surfaces such as tatami.

## Setup

You need [uv](https://docs.astral.sh/uv/) and Blender 3.0 or newer. From this checkout:

```sh
# Windows
powershell -ExecutionPolicy ByPass -File install.ps1

# macOS / Linux
sh install.sh
```

Both run `uv run --directory <this checkout> roxy-blender-mcp setup`, which finds your MCP clients, adds a `blender` server to each, and installs and enables the Blender addon. Add `--dry-run` to see what would change first.

Client entries use `uv run --no-sync` after setup prepares the environment. This avoids replacing a running `roxy-blender-mcp.exe` when another MCP instance starts on Windows. Existing configured clients are kept: add `--no-sync` to their `uv run` arguments by hand. After dependency changes, close the MCP clients and run `uv sync --directory <this checkout>` before starting them again.

To configure a client by hand, add:

```json
{
  "mcpServers": {
    "blender": {
      "command": "uv",
      "args": ["run", "--no-sync", "--directory", "C:\\path\\to\\Roxy-BlenderMCP-v2", "roxy-blender-mcp"]
    }
  }
}
```

Then in Blender, press N in the 3D Viewport, open the **Roxy Blender MCP** tab and connect.

## GUI clients

MCP initialization does not contact Blender. The first Blender tool call performs the connection; the addon handshake has a five-second timeout and can retry. `get_addon_status` uses a shared ten-second communication budget and reports dialogs or modal operations when Blender accepts a connection but does not respond.

`get_scene_info`, `look`, `get_addon_status` and `viewport_capture` advertise `readOnlyHint: true`. `get_scene_info` keeps its existing text and adds `structuredContent`: the scene header (`scene`, `object_counts`, `active`, `selected`, `selected_count`, `mode`), `columns`, `objects`, `shown` and `total`. `settings` is included only when requested. Each object has its original `name`, Blender `type`, and `fields` containing the same formatted values as the text; omitted fields are absent.

The app-only `scene_state(since: int = 0)` returns `{version, file, is_dirty, scene, mode, active, selected_count, changed}` in `structuredContent`, where `changed` is `version > since`. An unsaved file has `file: null`. Calls have a five-second communication budget. The version counter belongs to Blender, so all MCP processes connected to that Blender share it; dependency graph updates and file loads advance it. Reset `since` when Blender or the addon restarts. This tool requires addon protocol 20 (`roxy-blender-mcp update`, then restart Blender). GUI clients can expose app-only tools by setting `BLENDER_MCP_APPS=1` on their MCP process, as for `viewport_capture`.

## Checkpoints

The `checkpoint` tool saves the whole .blend as a checkpoint, lists checkpoints, and rolls back to one. The assistant saves one before risky changes; you can also just ask it to ("save a checkpoint", "go back to the blockout"). Restoring first saves the current state as another checkpoint, then reloads the file and saves it back to your .blend (Blender keeps the replaced version as .blend1). Undo history is cleared by a restore. The newest 30 are kept in Blender's user `datafiles/roxy_blender_mcp/checkpoints` folder.

## Authentication

The addon's socket runs arbitrary Python, so it only accepts commands that carry a token. Each time the addon's server starts it writes a new random token to `~/.roxy-blender-mcp/token-<port>` (the folder can be moved with `ROXY_BLENDER_MCP_DIR`, set for both Blender and the MCP server), and the MCP server reads it whenever it connects. Nothing needs configuring when both run as the same user on the same machine.

When the MCP server cannot read that file (Docker, another machine), pass the token in `BLENDER_MCP_TOKEN`. Setting `BLENDERMCP_ALLOW_UNAUTHENTICATED=1` in Blender's environment turns the check off, for third-party clients that cannot send a token.

Addon protocol 21 requires the token, so update the MCP server and the addon together.

## Updating

Update the checkout; clients pick up the new server the next time they start it. If the addon changed, copy it into Blender and restart Blender:

```sh
uv run --directory <this checkout> roxy-blender-mcp update
```

## Codex plugin

`integrations/codex` holds a Codex plugin. A plugin can't know where this checkout is, so it runs `roxy-blender-mcp` from your PATH: install that first with `uv tool install --editable <this checkout>`. Alternatively, skip the plugin and let `setup` configure Codex directly.

## License

MIT. See [LICENSE](LICENSE).
