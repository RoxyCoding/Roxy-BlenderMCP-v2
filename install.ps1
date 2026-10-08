# Roxy Blender MCP installer for Windows. Run it from the Roxy-BlenderMCP checkout:
#
#   powershell -ExecutionPolicy ByPass -File install.ps1
#
# Installs uv (with its official installer) if it's missing, then runs
# `uv run --directory <this checkout> roxy-blender-mcp setup`, which configures
# your MCP clients and the Blender addon. The fork isn't on PyPI: the server
# always runs from this checkout.

# Wrapped in a function so errors return instead of closing the user's
# PowerShell window.
function Install-RoxyBlenderMcp {
    $ErrorActionPreference = 'Stop'

    function Find-Uv {
        $cmd = Get-Command uv -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        # Where uv's installer puts it, before a new shell has it on PATH.
        foreach ($dir in @($env:UV_INSTALL_DIR, $env:XDG_BIN_HOME, "$env:USERPROFILE\.local\bin", "$env:USERPROFILE\.cargo\bin")) {
            if ($dir -and (Test-Path (Join-Path $dir 'uv.exe'))) { return (Join-Path $dir 'uv.exe') }
        }
        return $null
    }

    $root = $PSScriptRoot
    if (-not $root -or -not (Test-Path (Join-Path $root 'pyproject.toml'))) {
        Write-Host 'Run this from the Roxy-BlenderMCP checkout: powershell -ExecutionPolicy ByPass -File install.ps1' -ForegroundColor Red
        return
    }

    Write-Host 'Roxy Blender MCP installer'

    $uv = Find-Uv
    if (-not $uv) {
        Write-Host 'Installing uv, which runs Roxy Blender MCP (https://docs.astral.sh/uv/)...'
        powershell -ExecutionPolicy ByPass -c 'irm https://astral.sh/uv/install.ps1 | iex'
        $uv = Find-Uv
        if (-not $uv) {
            Write-Host "uv installed, but was not found. Open a new terminal and run: uv run --directory `"$root`" roxy-blender-mcp setup" -ForegroundColor Red
            return
        }
    }

    # Keep uv's folder on PATH for setup, which records uv's absolute path.
    $env:Path = "$(Split-Path $uv);$env:Path"
    # uv shows little while it builds the environment, which can take a while.
    Write-Host 'Preparing Roxy Blender MCP. The first run can take a minute...'
    & $uv run --directory $root roxy-blender-mcp setup @args
}

Install-RoxyBlenderMcp @args
