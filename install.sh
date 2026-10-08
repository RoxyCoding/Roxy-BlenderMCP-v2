#!/bin/sh
# Roxy Blender MCP installer for macOS and Linux. Run it from the
# Roxy-BlenderMCP checkout:
#
#   sh install.sh
#
# Installs uv (with its official installer) if it's missing, then runs
# `uv run --directory <this checkout> roxy-blender-mcp setup`, which configures
# your MCP clients and the Blender addon. The fork isn't on PyPI: the server
# always runs from this checkout. Arguments are passed to setup:
#
#   sh install.sh --dry-run
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ ! -f "$ROOT/pyproject.toml" ]; then
    echo "Run this from the Roxy-BlenderMCP checkout: sh install.sh" >&2
    exit 1
fi

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return 0
    fi
    # Where uv's installer puts it, before a new shell has it on PATH.
    for dir in "${UV_INSTALL_DIR:-}" "${XDG_BIN_HOME:-}" "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        if [ -n "$dir" ] && [ -x "$dir/uv" ]; then
            echo "$dir/uv"
            return 0
        fi
    done
    return 1
}

echo "Roxy Blender MCP installer"

if ! UV=$(find_uv); then
    echo "Installing uv, which runs Roxy Blender MCP (https://docs.astral.sh/uv/)..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        echo "Neither curl nor wget is available; install uv by hand: https://docs.astral.sh/uv/getting-started/installation/" >&2
        exit 1
    fi
    if ! UV=$(find_uv); then
        echo "uv installed, but wasn't found. Open a new terminal and run: uv run --directory \"$ROOT\" roxy-blender-mcp setup" >&2
        exit 1
    fi
fi

# Keep uv's folder on PATH for setup, which records uv's absolute path.
PATH="$(dirname "$UV"):$PATH"
export PATH

# uv shows little while it builds the environment, which can take a while.
echo "Preparing Roxy Blender MCP. The first run can take a minute..."
exec "$UV" run --directory "$ROOT" roxy-blender-mcp setup "$@"
