# Roxy-BlenderMCP

RoxyBlenderMCP is based on MCP for Blender by Siddharth Ahuja, licensed under the MIT License. This project is independently modified and maintained.

It connects an MCP client (Claude Desktop, Claude Code, Cursor, VS Code, Codex, ...) to a running Blender, so the assistant can build and edit scenes through Blender's Python API.

## How it differs from upstream

- **Its own name.** The package and command are `roxy-blender-mcp`, and the Blender addon shows up as "Roxy Blender MCP". It isn't published on PyPI: MCP clients run it from this checkout.
- **No data collection.** Telemetry, trajectory recording and the consent prompt are switched off in code, and the `disable_telemetry` and `record_trajectory_feedback` tools are gone. Nothing is sent anywhere.
- **No self-update.** The addon no longer downloads itself from upstream's GitHub, and `update` no longer checks PyPI, so nothing replaces this fork with upstream's code.
- **No Premium.** Upstream's paid generation service is removed, along with Tripo, which only ran through it. Hyper3D Rodin and Hunyuan3D still work with your own API keys.

## Setup

You need [uv](https://docs.astral.sh/uv/) and Blender 3.0 or newer. From this checkout:

```sh
# Windows
powershell -ExecutionPolicy ByPass -File install.ps1

# macOS / Linux
sh install.sh
```

Both run `uv run --directory <this checkout> roxy-blender-mcp setup`, which finds your MCP clients, adds a `blender` server to each, and installs and enables the Blender addon. Add `--dry-run` to see what would change first.

To configure a client by hand, add:

```json
{
  "mcpServers": {
    "blender": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\path\\to\\Roxy-BlenderMCP-v2", "roxy-blender-mcp"]
    }
  }
}
```

Then in Blender, press N in the 3D Viewport, open the **Roxy Blender MCP** tab and connect.

## Updating

Update the checkout; clients pick up the new server the next time they start it. If the addon changed, copy it into Blender and restart Blender:

```sh
uv run --directory <this checkout> roxy-blender-mcp update
```

## Codex plugin

`integrations/codex` holds a Codex plugin. A plugin can't know where this checkout is, so it runs `roxy-blender-mcp` from your PATH: install that first with `uv tool install --editable <this checkout>`. Alternatively, skip the plugin and let `setup` configure Codex directly.

## More

Upstream's original documentation, including tool details and troubleshooting, is in [README_Old.md](README_Old.md). Some of it (PyPI install, Premium, telemetry, self-update) no longer applies to this fork.

## License

MIT. See [LICENSE](LICENSE).
