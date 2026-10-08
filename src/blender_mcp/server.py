# blender_mcp_server.py
from mcp.server.fastmcp import FastMCP, Context
import argparse
import socket
import json
import logging
import tempfile
import threading
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any
import os
import sys
import time
import asyncio
import base64
import re

from .addon_manager import (
    handshake_addon,
    format_handshake_log,
    run_cli as run_addon_cli,
    EXPECTED_ADDON_PROTOCOL_VERSION,
    ADDON_DISPLAY_NAME,
    INSTALL_ADDON_COMMAND,
    check_addon_status_on_startup,
)
from . import ambientcg, blender_scripts, context_log, guides, session_rules
from . import model_plan as model_plans
from . import unreal_export
from .safe_mode import safe_mode_enabled, validate_code, SandboxViolation, SAFE_MODE_ENV
from .openai_apps import (
    APP_MIME_TYPE,
    VIEWPORT_STATE_META,
    VIEWPORT_TITLE,
    VIEWPORT_URI,
    PickerOption,
    client_extensions,
    is_app_only,
    pick_asset,
    picked_reply,
    supports_apps,
    supports_openai_forms,
    viewport_html,
    viewport_icon,
    viewport_store,
)
from mcp.types import CallToolResult, ImageContent, ResourceLink, TextContent, ToolAnnotations
from urllib.parse import quote, unquote

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BlenderMCPServer")

_READ_ONLY = ToolAnnotations(readOnlyHint=True)

# Default configuration
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876


def parse_connection_args(argv):
    """Parse --host/--port out of argv, ignoring anything else.

    parse_known_args is deliberate: MCP clients sometimes append their own
    arguments to the server command, and an unrecognised one must not abort
    startup. Unknown args are logged rather than dropped silently, so a typo
    like --prot does not masquerade as "connected to the default port".
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        logger.warning(f"Ignoring unrecognized command-line arguments: {unknown}")
    return args.host, args.port


def resolve_connection(cli_host=None, cli_port=None):
    """Resolve the Blender address: CLI flags > environment > defaults."""
    host = cli_host or os.getenv("BLENDER_HOST", DEFAULT_HOST)

    if cli_port is not None:
        return host, cli_port

    raw_port = os.getenv("BLENDER_PORT")
    if raw_port is None or raw_port == "":
        return host, DEFAULT_PORT
    try:
        return host, int(raw_port)
    except ValueError:
        logger.warning(
            f"BLENDER_PORT={raw_port!r} is not a valid port number; "
            f"falling back to {DEFAULT_PORT}"
        )
        return host, DEFAULT_PORT


# Set from --host/--port in main(); these take precedence over the
# BLENDER_HOST/BLENDER_PORT environment variables.
CLI_HOST = None
CLI_PORT = None

_addon_handshake = None
_addon_handshake_checked = False
_addon_handshake_lock = threading.Lock()

@dataclass
class BlenderConnection:
    host: str
    port: int
    sock: socket.socket = None  # Changed from 'socket' to 'sock' to avoid naming conflict
    # Serializes send+receive so two commands can never interleave on one socket.
    # Without this, a second command's response can be read as the first's, and
    # the stream stays desynced until the 180s timeout fires.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def connect(self, timeout: float = 180.0) -> bool:
        """Connect to the Blender addon socket server"""
        if self.sock:
            return True
            
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to Blender at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Blender: {str(e)}")
            self.disconnect()
            return False
    
    def disconnect(self):
        """Disconnect from the Blender addon"""
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting from Blender: {str(e)}")
            finally:
                self.sock = None

    def receive_full_response(self, sock, buffer_size=8192, timeout: float = 180.0):
        """Receive the complete response, potentially in multiple chunks"""
        chunks = []
        deadline = time.monotonic() + timeout
        
        try:
            while True:
                try:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise socket.timeout("Timeout waiting for Blender response")
                    sock.settimeout(remaining)
                    chunk = sock.recv(buffer_size)
                    if not chunk:
                        # If we get an empty chunk, the connection might be closed
                        if not chunks:  # If we haven't received anything yet, this is an error
                            raise Exception("Connection closed before receiving any data")
                        break
                    
                    chunks.append(chunk)
                    
                    # Check if we've received a complete JSON object
                    try:
                        data = b''.join(chunks)
                        json.loads(data.decode('utf-8'))
                        # If we get here, it parsed successfully
                        logger.info(f"Received complete response ({len(data)} bytes)")
                        return data
                    except json.JSONDecodeError:
                        # Incomplete JSON, continue receiving
                        continue
                except socket.timeout:
                    logger.warning("Socket timeout during chunked receive")
                    raise
                except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
                    logger.error(f"Socket connection error during receive: {str(e)}")
                    raise  # Re-raise to be handled by the caller
        except socket.timeout:
            logger.warning("Socket timeout during chunked receive")
            raise
        except Exception as e:
            logger.error(f"Error during receive: {str(e)}")
            raise
            
        # If we get here, we either timed out or broke out of the loop
        # Try to use what we have
        if chunks:
            data = b''.join(chunks)
            logger.info(f"Returning data after receive completion ({len(data)} bytes)")
            try:
                # Try to parse what we have
                json.loads(data.decode('utf-8'))
                return data
            except json.JSONDecodeError:
                # If we can't parse it, it's incomplete
                raise Exception("Incomplete JSON response received")
        else:
            raise Exception("No data received")

    def send_command(self, command_type: str, params: Dict[str, Any] = None, read_only: bool = False, timeout: float = 180.0) -> Dict[str, Any]:
        """Send a command to Blender and return the response.

        `read_only` marks an execute_code the server runs only to observe the
        scene, so the Viewport app doesn't treat it as an edit and recapture.
        `timeout` bounds lock waiting and socket communication (default 180 seconds).
        """
        # Hold the lock across send+receive: the response is matched to the
        # command purely by ordering on the stream, so overlapping calls would
        # hand each other's responses back.
        deadline = time.monotonic() + timeout
        if not self._lock.acquire(timeout=timeout):
            raise TimeoutError("Timeout waiting for Blender command lock")
        try:
            # The Viewport app watches these to recapture once Blender goes quiet.
            viewport_store.command_started()
            try:
                return self._send_command_locked(command_type, params, deadline - time.monotonic())
            finally:
                viewport_store.command_finished("observe" if read_only else command_type)
        finally:
            self._lock.release()

    def _send_command_locked(self, command_type: str, params: Dict[str, Any] = None, timeout: float = 180.0) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        if timeout <= 0:
            raise TimeoutError("Timeout waiting for Blender command lock")
        if not self.sock and not self.connect(timeout=timeout):
            raise ConnectionError("Not connected to Blender")

        command = {
            "type": command_type,
            "params": params or {}
        }

        try:
            # Log the command being sent
            logger.info(f"Sending command: {command_type} with params: {params}")
            
            # Send the command
            self.sock.settimeout(max(0.001, deadline - time.monotonic()))
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            logger.info(f"Command sent, waiting for response...")
            
            # Receive the response using the improved receive_full_response method
            response_data = self.receive_full_response(self.sock, timeout=deadline - time.monotonic())
            logger.info(f"Received {len(response_data)} bytes of data")
            
            response = json.loads(response_data.decode('utf-8'))
            logger.info(f"Response parsed, status: {response.get('status', 'unknown')}")
            
            if response.get("status") == "error":
                logger.error(f"Blender error: {response.get('message')}")
                raise Exception(response.get("message", "Unknown error from Blender"))
            
            return response.get("result", {})
        except socket.timeout:
            logger.error("Socket timeout while waiting for response from Blender")
            # Don't try to reconnect here - let the get_blender_connection handle reconnection
            # Just invalidate the current socket so it will be recreated next time
            self.disconnect()
            raise TimeoutError("Timeout waiting for Blender response - try simplifying your request. If Blender is running headless (blender -b), commands never execute; run Blender with a GUI or via 'xvfb-run -a blender' instead")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Socket connection error: {str(e)}")
            self.disconnect()
            raise Exception(f"Connection to Blender lost: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Blender: {str(e)}")
            # Try to log what was received
            if 'response_data' in locals() and response_data:
                logger.error(f"Raw response (first 200 bytes): {response_data[:200]}")
            raise Exception(f"Invalid response from Blender: {str(e)}")
        except Exception as e:
            logger.error(f"Error communicating with Blender: {str(e)}")
            # Don't try to reconnect here - let the get_blender_connection handle reconnection
            self.disconnect()
            raise Exception(f"Communication error with Blender: {str(e)}")

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    # We don't need to create a connection here since we're using the global connection
    # for resources and tools

    try:
        # Just log that we're starting up
        logger.info("BlenderMCP server starting up")

        try:
            status = check_addon_status_on_startup()
            if status.needs_action:
                logger.warning(status.message)
            elif status.message:
                logger.info(status.message)
        except Exception as e:
            logger.debug(f"Addon status check skipped: {e}")

        # Blender may be busy in a modal operation; connect only when a tool needs it.

        # Return an empty context - we're using the global connection
        yield {}
    finally:
        # Clean up the global connection on shutdown
        global _blender_connection
        if _blender_connection:
            logger.info("Disconnecting from Blender on shutdown")
            _blender_connection.disconnect()
            _blender_connection = None
        logger.info("BlenderMCP server shut down")

# Guidance delivered to clients in the `initialize` response. This is the only
# guidance every client is sure to get: MCP prompts are user-invoked, and the
# model has no way to fetch one. Per-tool details belong in tool descriptions.
# Claude Code cuts it at 2048 characters, so it holds only what the model needs
# before its first call; the rest is session_rules.md, attached to the first
# tool reply of each session (see RoxyMCP below and #347 on context cost).
SERVER_INSTRUCTIONS = """Roxy Blender MCP drives the user's live Blender. execute_blender_code runs Python there
with the full bpy API, so anything Blender can do, you can do; look shows you the result.

Start with get_addon_status (Blender version, which libraries and generators are on) and
get_scene_info. The first tool reply in a conversation ends with this server's session rules
(guides, quality bar, assets): follow them for the whole conversation.

Scripts run in someone else's Blender:
- Look shader nodes up by type, never by name (names are localized):
  `next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")`.
- Never hardcode enum identifiers; read them, e.g.
  `[i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["file_format"].enum_items]`.
  scene.render.engine under-reports: read the current value, and assign a new one inside
  try/except TypeError, whose message lists the valid engines.
- Material colors go on shader node inputs; material.diffuse_color only affects the viewport.

look is how you see your work; use it as much as you need. Images stay in the conversation, so
a smaller max_size keeps long sessions cheap.

Before a risky or sweeping change, checkpoint(action="save"); restore it if the result is worse.

Never model anything with more than one part before model_plan(action="check") passes its
structure; build from the plan and verify against it.

Real-world buildings, products and everyday items follow Japanese specifications and design
unless the user names another region; game assets target Unreal Engine 5 unless the user names
another engine, and go there through export_to_unreal. Imported models arrive at arbitrary scale: size them from the reported
world_bounding_box and put them on the ground."""


class RoxyMCP(FastMCP):
    """FastMCP that attaches the session rules to the first model-facing tool reply."""

    async def call_tool(self, name, arguments):
        result = await super().call_tool(name, arguments)
        tool = self._tool_manager.get_tool(name)
        if tool is None or is_app_only(tool):
            return result
        try:
            return session_rules.attach(result, session_rules.session_key(self.get_context()))
        except Exception as e:
            logger.debug(f"Session rules not attached: {e}")
            return result


# Create the MCP server with lifespan support
mcp = RoxyMCP(
    ADDON_DISPLAY_NAME,
    lifespan=server_lifespan,
    instructions=SERVER_INSTRUCTIONS,
)

# Resource endpoints

# Global connection for resources (since resources can't access context)
_blender_connection = None

def _maybe_handshake_addon(blender: BlenderConnection, force: bool = False) -> None:
    """Run addon version handshake once per process after a live connection."""
    global _addon_handshake, _addon_handshake_checked
    deadline = time.monotonic() + 5.0
    if not _addon_handshake_lock.acquire(timeout=5.0):
        raise TimeoutError("Timeout waiting for addon handshake")
    try:
        if _addon_handshake_checked and not force:
            return
        _addon_handshake = handshake_addon(blender, timeout=max(0.001, deadline - time.monotonic()))
        _addon_handshake_checked = _addon_handshake.source != "error"
        log_line = format_handshake_log(_addon_handshake)
        if _addon_handshake.up_to_date:
            logger.info(log_line)
        else:
            logger.warning(log_line)
    except TimeoutError:
        _addon_handshake = None
        _addon_handshake_checked = False
        logger.warning("Addon handshake timed out; will retry on the next call")
        raise
    finally:
        _addon_handshake_lock.release()


def _addon_protocol() -> int | None:
    """Protocol the connected addon reported at handshake, or None if unknown."""
    return _addon_handshake.protocol_version if _addon_handshake else None


_connection_lock = threading.Lock()


def get_blender_connection(handshake: bool = True, timeout: float = 180.0):
    """Get or create a persistent Blender connection"""
    global _blender_connection

    # Reuse the connection without a liveness probe. Only a failed handshake retries.
    # Create a new connection if needed. Tools call this from worker threads, so
    # the lock keeps two of them from each opening a connection.
    if not _connection_lock.acquire(timeout=timeout):
        raise TimeoutError("Timeout waiting for the Blender connection")
    try:
        if _blender_connection is None:
            host, port = resolve_connection(CLI_HOST, CLI_PORT)
            connection = BlenderConnection(host=host, port=port)
            if not connection.connect(timeout=timeout):
                logger.error("Failed to connect to Blender")
                raise Exception("Could not connect to Blender. Make sure the Blender addon is running.")
            _blender_connection = connection
            logger.info("Created new persistent connection to Blender")
    finally:
        _connection_lock.release()
    if handshake:
        try:
            _maybe_handshake_addon(_blender_connection)
        except TimeoutError:
            pass

    return _blender_connection


# Talking to Blender blocks for as long as Blender takes, up to minutes. Async
# tools do it on a worker thread so the event loop keeps answering pings,
# cancellations and the Viewport app's polls meanwhile; BlenderConnection's
# lock still keeps commands in order.
async def _send(command_type: str, params: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
    return await asyncio.to_thread(
        lambda: get_blender_connection().send_command(command_type, params, **kwargs))


def _integrations(blender: BlenderConnection, deadline: float) -> dict:
    """Which asset libraries (search_assets) are on. ambientCG needs no switch."""
    status = {}
    for name in ("polyhaven", "sketchfab"):
        try:
            reply = blender.send_command(f"get_{name}_status", timeout=max(0.001, deadline - time.monotonic()))
            status[name] = "on" if reply.get("enabled") else "off"
        except TimeoutError:
            raise
        except Exception as e:
            status[name] = "not in this addon version" if _addon_lacks(e) else "unknown"
    status["ambientcg"] = "on"
    return {"libraries": status}


@mcp.tool(annotations=_READ_ONLY)
async def get_addon_status(ctx: Context) -> str:
    """
    Check the connected Blender: its version, whether the addon matches this server, and which
    asset libraries are switched on. Call it once at the start.

    `libraries` are the search_assets sources, each on or off for this user.

    If outdated, `update_command` is how the user updates it (then restart or re-enable the
    addon in Blender).

    No usage data, prompts, code or screenshots are ever sent anywhere.
    """
    return await asyncio.to_thread(_addon_status)


def _addon_status() -> str:
    try:
        deadline = time.monotonic() + 10.0
        blender = get_blender_connection(handshake=False, timeout=5.0)
        _maybe_handshake_addon(blender, force=True)
        result = _addon_handshake
        if result is None:
            return "Could not determine addon status."
        payload = {
            "up_to_date": result.up_to_date,
            "protocol_version": result.protocol_version,
            "expected_protocol_version": EXPECTED_ADDON_PROTOCOL_VERSION,
            "addon_version": result.addon_version,
            "capabilities": result.capabilities,
            "blender_version": result.blender_version,
            **_integrations(blender, deadline),
            "source": result.source,
            "warning": result.warning,
            "update_command": INSTALL_ADDON_COMMAND,
            "after_install": (
                "If the addon file was updated: in Blender, Preferences → Add-ons → "
                f"disable/enable 'Interface: {ADDON_DISPLAY_NAME}', or restart Blender, then Start MCP Server."
            ),
        }
        return json.dumps(payload, indent=2)
    except TimeoutError:
        return "Blenderは接続を受け付けていますが応答しません。Blenderでダイアログやモーダル操作が開いていないか確認してください。"
    except Exception as e:
        return f"Error checking addon status: {e}"


# Backwards compatibility. The server runs from the checkout, but the addon
# only changes when the user reinstalls it, so any server must work with any
# addon. Two rules keep that true:
# - Never assume a command or argument exists. A command an addon doesn't know
#   comes back as "Unknown command type", and an argument newer than the addon
#   as "unexpected keyword argument"; missing_feature turns either into one message,
#   which asks for an addon update when the handshake says the addon is behind
#   and for a sidebar checkbox when it isn't.
# - Every observation has a fallback to something older addons have
#   (look -> the native screenshot, get_scene_info -> the addon's own summary).
# tests/test_compat_matrix.py runs the tools against real past addons.

ADDON_UPDATE_HINT = f"Update the Blender addon: run `{INSTALL_ADDON_COMMAND}`, then restart Blender."


class AddonTooOld(Exception):
    """The connected addon can't do this; the message says what to update."""


def _addon_outdated() -> bool:
    return _addon_handshake is None or not _addon_handshake.up_to_date


_ADDON_LACKS = ("Unknown command type", "unexpected keyword argument")


def _addon_lacks(e: Exception | str) -> bool:
    """Whether a failure means the addon predates the command or an argument."""
    return any(marker in str(e) for marker in _ADDON_LACKS)


def missing_feature(what: str, sidebar_label: str | None = None) -> str:
    """What to tell the user when the addon doesn't handle a command.

    Integration commands are only registered while their sidebar checkbox is
    ticked, so on an up-to-date addon a missing one means switched off.
    """
    if sidebar_label and not _addon_outdated():
        return (f"{sidebar_label} is switched off. Ask the user to tick it in the {ADDON_DISPLAY_NAME} sidebar "
                "in Blender (press N in the 3D Viewport).")
    reply = f"The Blender addon is too old for {what}. {ADDON_UPDATE_HINT}"
    if sidebar_label:
        reply += f" If it is already up to date, tick {sidebar_label} in the {ADDON_DISPLAY_NAME} sidebar."
    return reply


def _run_script(script: str, args: dict) -> dict:
    """Run one of blender_scripts' observation scripts and return its result."""
    result = get_blender_connection().send_command(
        "execute_code", {"code": blender_scripts.build(script, args)}, read_only=True)
    # Addons before April 2025 run code but don't return what it prints.
    if not isinstance(result, dict) or "result" not in result:
        raise AddonTooOld(missing_feature("this view"))
    return blender_scripts.parse_result(result["result"])


def _format_scene_summary(data: dict, fields) -> str:
    h = data["header"]
    counts = ", ".join(f"{n} {kind}" for kind, n in sorted(h["object_counts"].items())) or "empty"
    selected = ", ".join(h["selected"]) or "none"
    extra = h.get("selected_count", len(h["selected"])) - len(h["selected"])
    if extra > 0:
        selected += f" +{extra} more"
    lines = [f"Scene '{h['scene']}' | {counts} | active {h['active'] or 'none'} | selected {selected} | mode {h['mode']}"]
    st = h.get("settings")
    if st:
        lines.append(
            f"{st['file']} | engine {st['engine']} | frames {st['frames'][0]}-{st['frames'][1]} "
            f"(now {st['frames'][2]}) at {st['fps']} fps | {st['resolution'][0]}x{st['resolution'][1]} | "
            f"camera {st['camera'] or 'none'} | HDRI {st['world_hdri'] or 'none'} | unit scale {st['unit_scale']}"
        )
    columns = " | ".join(["name", "type", *(f for f in blender_scripts.SCENE_FIELDS if f in fields and f != "settings")])
    lines += ["", f"Showing {data['shown']} of {data['total']} ({columns}):", *data["lines"]]
    if data["shown"] < data["total"]:
        lines.append(f"... {data['total'] - data['shown']} more. Narrow with query= or root=, or raise limit.")
    return "\n".join(lines)


@mcp.tool(annotations=_READ_ONLY)
async def get_scene_info(
    ctx: Context,
    query: str | None = None,
    root: str | None = None,
    fields: list[str] | None = None,
    limit: int = 20,
) -> Any:
    """
    Facts about the scene as text: what's there, where, how big, and how healthy meshes and rigs
    are. No image; to see the scene, use look.

    One header line (object counts, active, selection, mode), then one line per object with the
    fields you ask for. Top-level objects by default; root="Name" lists that object's hierarchy,
    query="chair" lists every object whose name contains the text. For anything else about an
    object, read it with execute_blender_code.

    Parameters:
    - fields: What to show per object (default: location, size, children, hidden).
      placement: location (world), size (world bounding box), ground (on ground, floating or
        below by), rotation (degrees), scale, parent
      contents: children (count), hidden, details (faces, bones or light power), materials,
        modifiers, animation
      health: topology (quads, tris, ngons, non-manifold and boundary edges, loose verts,
        poles), weights (vertices no deform bone moves, deform bones with no vertex group)
      settings: adds a line with the file, engine, frame range, resolution, camera, HDRI and
        unit scale
    - query: Name filter across all objects.
    - root: Object whose hierarchy to list.
    - limit: Maximum object lines (default 20).
    """
    fields = list(blender_scripts.SCENE_DEFAULT_FIELDS) if fields is None else list(dict.fromkeys(fields))
    unknown = [f for f in fields if f not in blender_scripts.SCENE_FIELDS]
    if unknown:
        return f"Error: unknown fields {', '.join(unknown)}. Pick from: {', '.join(blender_scripts.SCENE_FIELDS)}"
    return await asyncio.to_thread(_scene_info, query, root, fields, limit)


def _scene_info(query: str | None, root: str | None, fields: list[str], limit: int) -> Any:
    try:
        try:
            data = _run_script(blender_scripts.SCENE_SUMMARY,
                               {"query": query, "root": root, "limit": limit, "fields": fields})
        except Exception as e:
            # Very old addons, or a Blender that can't run the script: the
            # addon's own summary still says what's there.
            logger.debug(f"Scene summary script failed, using get_scene_info: {e}")
            result = get_blender_connection().send_command("get_scene_info")
            return json.dumps(result, indent=2)
        if data.get("error"):
            return f"Error: {data['error']}"
        structured = {
            **data["header"],
            "selected_count": data["header"].get("selected_count", len(data["header"]["selected"])),
            "columns": ["name", "type", *(f for f in blender_scripts.SCENE_FIELDS if f in fields and f != "settings")],
            "objects": data.get("objects", []),
            "shown": data["shown"],
            "total": data["total"],
        }
        if "settings" not in fields:
            structured.pop("settings", None)
        return CallToolResult(
            content=[TextContent(type="text", text=_format_scene_summary(data, fields))],
            structuredContent=structured,
        )
    except Exception as e:
        logger.error(f"Error getting scene info from Blender: {str(e)}")
        return f"Error getting scene info: {str(e)}"


def _capture_viewport(max_size: int) -> tuple[bytes, dict]:
    """Have the addon render the viewport to a temp file.

    Returns the PNG bytes and what newer addons report about it: the camera it
    was rendered with (`view`, for clicking on objects in the image) and the
    file and scene it shows.
    """
    blender = get_blender_connection()
    temp_path = os.path.join(tempfile.gettempdir(), f"blender_screenshot_{os.getpid()}.png")

    result = blender.send_command("get_viewport_screenshot", {
        "max_size": max_size,
        "filepath": temp_path,
        "format": "png"
    })

    if "error" in result:
        raise Exception(result["error"])

    if not os.path.exists(temp_path):
        raise Exception("Screenshot file was not created")

    with open(temp_path, 'rb') as f:
        image_bytes = f.read()
    os.remove(temp_path)
    return image_bytes, result


def _store_capture(max_size: int, source: str) -> None:
    # Read the version first: an edit that lands mid-capture isn't in the image.
    scene_version = viewport_store.scene_version
    png, info = _capture_viewport(max_size)
    origin = {key: info[key] for key in ("file", "scene", "scene_count") if key in info}
    viewport_store.put(png, source, view=info.get("view"), scene_version=scene_version, origin=origin)


# In MCP Apps hosts the result also shows in the fullscreen Viewport app.
def _viewport_screenshot(max_size: int = 1000) -> CallToolResult:
    """look(mode="viewport"): the user's viewport, also shown in the Viewport app."""
    try:
        _store_capture(max_size, "model")
        state, image_bytes = _viewport_snapshot()
        # The state rides in _meta, which only the Viewport app reads, so the
        # model sees exactly the image it always did.
        return CallToolResult(
            content=[_png_content(image_bytes)],
            _meta={VIEWPORT_STATE_META: state},
        )
    except Exception as e:
        logger.error(f"Error capturing screenshot: {str(e)}")
        raise Exception(f"Screenshot failed: {str(e)}")


@mcp.tool()
async def execute_blender_code(ctx: Context, code: str) -> str:
    """
    Run Python in the user's live Blender (bpy, bmesh, mathutils). Whatever it prints is returned.

    Work in small steps and print what you need to know.

    Parameters:
    - code: The Python code to execute
    """
    if safe_mode_enabled():
        try:
            validate_code(code)
        except SandboxViolation as exc:
            logger.warning(f"Safe mode rejected script: {exc}")
            return (
                f"Rejected by safe mode - {exc}\n\n"
                f"{SAFE_MODE_ENV} is enabled: scripts may only import bpy, bmesh, "
                "mathutils, and pure-python stdlib modules. No eval/exec/open, no "
                "os/subprocess/network access, no handlers/timers/drivers, no class "
                "or property registration, and no loading of external .blend "
                "datablocks. Blender operators for rendering, saving, and "
                "import/export ARE allowed. Rewrite the script within these limits; "
                "only the user can disable safe mode."
            )
    try:
        result = await _send("execute_code", {"code": code})
        return f"Code executed successfully: {result.get('result', '')}"
    except Exception as e:
        logger.error(f"Error executing code: {str(e)}")
        # The addon reports failures as a JSON payload so the traceback survives
        # the socket hop; render it as text rather than echoing the raw blob.
        try:
            detail = json.loads(str(e))
            traceback_text = detail["traceback"]
        except (ValueError, KeyError, TypeError):
            return f"Error executing code: {str(e)}"
        return f"Error executing code: {detail.get('exception_type', 'Error')}: {detail.get('message', '')}\n\n{traceback_text}"


UE_ACTIONS = ("export", "verify")
# What each export predicted Unreal would report, by Blender object name.
_unreal_expected: dict[str, dict] = {}


@mcp.tool()
async def export_to_unreal(
    ctx: Context,
    name: str,
    action: str = "export",
    kind: str | None = None,
    asset_name: str | None = None,
    ue_folder: str = "/Game/Roxy",
    output_dir: str | None = None,
    animation: bool = False,
    unreal_bounds: dict | None = None,
) -> str:
    """
    Send one asset from Blender to Unreal Engine 5 and check it arrived at the right size, pivot
    and facing. Use it for every Unreal export instead of calling the FBX exporter yourself: the
    settings are tested against UE5 (other scale options import 100x too small).

    - action="export": write an Unreal-ready FBX of the object `name` and everything parented
      under it (an assembly empty, a mesh, or a character's root/armature). It names the asset
      SM_/SK_, exports from the asset's own origin, renames the armature to "Armature" for the
      export, includes UCX_/UBX_/USP_/UCP_ collision and SOCKET_ empties, and puts everything back.
      The reply gives the file, the bounds Unreal should report, and the Unreal MCP steps.
    - action="verify": pass what the Unreal MCP's get_bounds returned as unreal_bounds; it is
      compared with the export's prediction.

    Parameters:
    - kind: "static" or "skeletal"; default: skeletal when an armature drives the meshes.
    - asset_name: Name in Unreal without prefix; default the object's name.
    - ue_folder: Content folder for the import steps (default /Game/Roxy).
    - output_dir: Where the FBX goes; default an UnrealExport folder beside the .blend.
    - animation: Include the active animation (skeletal), baked.

    Build the asset to get_guide("unreal-engine") first: real size, front facing Blender -Y,
    origin where the pivot belongs.
    """
    if action not in UE_ACTIONS:
        return f"Error: action must be one of {', '.join(UE_ACTIONS)}."
    try:
        if action == "verify":
            expected = _unreal_expected.get(name)
            if expected is None:
                return f'Error: nothing exported as {name!r} this session; run export_to_unreal(name="{name}") first.'
            ok, findings = unreal_export.compare(expected, unreal_bounds or {})
            return unreal_export.format_verify(name, ok, findings)
        if kind not in (None, "static", "skeletal"):
            return 'Error: kind must be "static" or "skeletal".'
        result = await asyncio.to_thread(_run_script, blender_scripts.UE_EXPORT, {
            "name": name, "kind": kind, "asset_name": asset_name, "output_dir": output_dir,
            "animation": animation})
        if result.get("error"):
            return f"Error: {result['error']}"
        lo, hi = result["bounds_m"]
        result["expected_bounds_cm"] = unreal_export.blender_to_unreal_cm(lo, hi)
        _unreal_expected[name] = result["expected_bounds_cm"]
        return unreal_export.format_export(result, ue_folder.rstrip("/"))
    except Exception as e:
        return f"Error exporting to Unreal: {e}"


PLAN_ACTIONS = ("check", "build", "verify")
# Plans that passed check this session, by name: build only accepts these.
_checked_plans: dict[str, dict] = {}


@mcp.tool()
async def model_plan(
    ctx: Context,
    action: str = "check",
    plan: dict | None = None,
    name: str | None = None,
) -> str:
    """
    Write down the structure of anything with more than one part before modeling it, check it,
    build it, and verify the result. Don't model a multi-part subject without a plan that passed
    check: it is how you show you understand what holds it together.

    - action="check", plan={...}: validate the plan; fix every error and check again.
    - action="build", name=...: build a checked plan's box and cylinder parts under an empty
      called name (each part <Name>_<Part>); then add custom parts and detail yourself.
    - action="verify", name=...: compare what is in the scene with the plan stored on it.

    Plan (metres, relative to the subject's bottom centre):
    {"name": "Table", "purpose": "dining table for four", "size": [1.35, 0.8, 0.7],
     "location": [0, 0, 0],
     "parts": [
       {"name": "Top", "shape": "box", "size": [1.35, 0.8, 0.03], "at": [0, 0, 0.67],
        "rests_on": ["Leg_FL", "Leg_FR", "Leg_BL", "Leg_BR"]},
       {"name": "Leg_FL", "shape": "box", "size": [0.04, 0.04, 0.67], "at": [0.625, -0.35, 0],
        "rests_on": ["ground"]}, ...]}
    - shape: box, cylinder (size [diameter, diameter, height]) or custom (add "how": the roxy
      helper or technique you will use; you build it, named <Name>_<Part>, parented to the empty).
    - at: bottom centre of the part's box. rests_on: what holds it up - parts it sits on, hangs
      from or is fixed to, or "ground". Every part must touch its supports and reach the ground.
    - size: the whole subject; the parts must span it. Work the sizes out first
      (get_guide("modeling")).
    """
    if action not in PLAN_ACTIONS:
        return f"Error: action must be one of {', '.join(PLAN_ACTIONS)}."
    try:
        if action == "check":
            report = model_plans.check(plan)
            if report.ok:
                _checked_plans[plan["name"]] = plan
                return report.text("Plan") + f'\nBuild it with model_plan(action="build", name="{plan["name"]}").'
            return report.text("Plan")

        if not name:
            return f"Error: {action} needs name."
        if action == "build":
            checked = _checked_plans.get(name)
            if checked is None:
                return (f"Error: no checked plan called {name!r} in this session. "
                        'Run model_plan(action="check", plan=...) first and fix its errors.')
            code = ("import json\n"
                    f"root = roxy.build(json.loads({json.dumps(json.dumps(checked))}))\n"
                    "print(root.name, len(root.children))\n")
            result = await _send("execute_code", {"code": code})
            out = (result.get("result") or "").strip() if isinstance(result, dict) else ""
            custom = [p["name"] for p in checked["parts"] if p.get("shape") == "custom"]
            reply = f"Built {name} ({out.split()[-1] if out else '?'} parts so far)."
            if custom:
                reply += (f" Now make the custom parts {', '.join(custom)} as {name}_<Part> with "
                          f"parent=bpy.data.objects[{name!r}] and location = the part's 'at'.")
            return reply + f' Then look at it and run model_plan(action="verify", name="{name}").'

        state = await asyncio.to_thread(_run_script, blender_scripts.PLAN_STATE, {"name": name})
        if state.get("error"):
            return f"Error: {state['error']}"
        stored = state.get("plan")
        checked = json.loads(stored) if stored else _checked_plans.get(name)
        if not checked:
            return f"Error: {name} has no plan. Build it with model_plan(action=\"build\") first."
        return model_plans.verify(checked, state.get("parts") or {}).text(f"{name} against its plan")
    except Exception as e:
        if "name 'roxy' is not defined" in str(e) or _addon_lacks(e):
            return missing_feature("model plans")
        return f"Error with model_plan: {e}"


CHECKPOINT_ACTIONS = ("save", "list", "restore")
# A restore reloads the whole file; give a big one time to load.
CHECKPOINT_RESTORE_WAIT_S = 60.0


@mcp.tool()
async def checkpoint(
    ctx: Context,
    action: str = "save",
    label: str = "",
    id: str | None = None,
    limit: int = 10,
) -> str:
    """
    Save the whole Blender file as a checkpoint, list checkpoints, or roll back to one.

    Save one before a risky or sweeping change (deleting or rebuilding many objects, applying
    modifiers, a long script), and when the user is happy with a state. Restore when a change made
    things worse or the user asks to go back; Blender's own undo doesn't reach changes made here.

    Parameters:
    - action: save (default), list, or restore.
    - label: For save: what this state is ("blockout done", "before relighting").
    - id: For restore: a checkpoint id from save or list.
    - limit: For list: how many, newest first (default 10).

    Restoring reloads the file: undo history is cleared, the state just before restoring is saved
    as a checkpoint first, and the restored scene is saved back to the user's .blend (Blender keeps
    the version it replaces as .blend1). Up to 30 checkpoints are kept; older ones are deleted.
    """
    if action not in CHECKPOINT_ACTIONS:
        return f"Error: action must be one of {', '.join(CHECKPOINT_ACTIONS)}."
    try:
        if action == "save":
            result = await _send("save_checkpoint", {"label": label})
            if result.get("error"):
                return f"Error: {result['error']}"
            reply = (f"Saved checkpoint {result['id']} ({result['objects']} objects, {result['size_mb']} MB). "
                     f'Roll back with checkpoint(action="restore", id="{result["id"]}").')
            if result.get("pruned"):
                reply += f" Deleted the oldest: {', '.join(result['pruned'])}."
            return reply

        if action == "list":
            result = await _send("list_checkpoints", {"limit": max(1, min(int(limit or 10), 30))})
            items = result.get("checkpoints") or []
            if not items:
                return "No checkpoints yet."
            lines = [f"{c.get('id')}  {c.get('created', '')}  {c.get('objects', '?')} objects"
                     + (f"  \"{c['label']}\"" if c.get("label") else "")
                     + ("" if c.get("this_file") else f"  (from {c.get('source_file') or 'an unsaved file'})")
                     for c in items]
            return "Newest first:\n" + "\n".join(lines)

        if not id:
            return 'Error: restore needs id, from checkpoint(action="list").'
        result = await _send("restore_checkpoint", {"checkpoint_id": id})
        if result.get("error"):
            return f"Error: {result['error']}"
        deadline = time.monotonic() + CHECKPOINT_RESTORE_WAIT_S
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            try:
                status = (await _send("list_checkpoints", {"limit": 1})).get("last_restore") or {}
            except Exception:
                continue  # Blender is busy loading the file
            if status.get("id") != id or status.get("state") == "pending":
                continue
            if status.get("state") == "error":
                return f"Error restoring {id}: {status.get('error')}"
            reply = (f"Restored checkpoint {id}. The state before it is checkpoint {result['before_restore']}, "
                     "if the user wants that back.")
            if not result.get("file"):
                reply += (f" The file was never saved, so it is now open as {status.get('file')}: "
                          "ask the user to Save As where they want it.")
            return reply
        return (f"Restoring {id} is taking a while; check with get_scene_info. The state before it is "
                f"checkpoint {result['before_restore']}.")
    except Exception as e:
        if _addon_lacks(e):
            return missing_feature("checkpoints")
        return f"Error with checkpoint: {e}"


def _polyhaven_credit(result):
    """A source line for an imported asset.

    Poly Haven's assets are CC0 and need no attribution, ever. Its API asks that
    software built on the live API makes clear to its users where the content
    comes from, and in an MCP client the chat is the surface they actually see.
    """
    authors = ", ".join(result.get("authors") or [])
    by = f" by {authors}" if authors else ""
    url = result.get("url") or "https://polyhaven.com"
    return f"From Poly Haven{by} - {url} (CC0, free to use for anything)."


def _polyhaven_scale_note(result):
    """How to tile the material that was just built, in the units it was authored in.

    Poly Haven publishes a real-world size for every texture, but until now it
    appeared once in a search result and never again - so a material was applied
    with whatever tiling the object's UVs happened to give it, which for a 0.5m
    plank texture on a 6m beam is twelve visible repeats. Saying it here, beside
    the node that consumes it, is the difference between the size being a fact
    and it being a decision.
    """
    size = result.get("scale_mm")
    node = result.get("mapping_node")
    if not size or len(size) != 2 or not node:
        return ""

    width, height = (value / 1000 for value in size)
    return (
        f" The texture covers {width:g}m x {height:g}m in the real world. Its "
        f"'{node}' node is in POINT mode, where Scale multiplies the UV "
        f"coordinates: the pattern repeats Scale times across whatever span the "
        f"UVs cover. For UVs that run 0-1 across a surface, life-sized tiling is "
        f"Scale = surface size in metres / {width:g}."
    )


POLYHAVEN_UNUSED_NOTE = (
    "Nothing is using it yet: assign the material to objects (import_asset's apply_to does it in "
    "the same call). Saving the file before then discards it, as Blender does with any unused "
    "datablock, and it would have to be downloaded again."
)


def _polyhaven_thumbnail(asset: dict) -> str:
    # Addons before protocol 12 don't pass thumbnail_url on. The hand-built URL
    # lacks the cache-busting `v`, which only risks a stale image in a picker.
    return asset.get("thumbnail_url") or (
        f"https://cdn.polyhaven.com/asset_img/thumbs/{asset['id']}.png?width=256&height=256"
    )


async def _search_polyhaven(
    ctx: Context,
    query: str | None = None,
    asset_type: str = "all",
    category: str | None = None,
    attributes: dict | None = None,
    min_size_m: float | None = None,
    limit: int = 20,
) -> str:
    """search_assets(source="polyhaven"): ranked Poly Haven results, with real-world sizes and the picker."""
    try:
        result = await _send("search_polyhaven_assets", {
            "asset_type": asset_type,
            "category": category,
            "attributes": attributes,
            "query": query,
            "limit": limit,
            "min_size_m": min_size_m,
        })

        if "error" in result:
            return f"Error: {result['error']}"

        assets = result["assets"]
        total_count = result["total_count"]

        if result.get("query"):
            header = f"{total_count} assets on Poly Haven match '{result['query']}'"
        else:
            header = f"{total_count} assets on Poly Haven"
            if category:
                header += f" in {category}"
            if attributes:
                header += " (" + ", ".join(f"{k}={v}" for k, v in attributes.items()) + ")"
            header += ", most downloaded first"

        if min_size_m:
            header += f" (at least {min_size_m:g}m across)"

        lines = [header, f"Showing {result['returned_count']}:", ""]
        if result.get("note"):
            lines.insert(1, result["note"])

        credit = "Assets from Poly Haven (https://polyhaven.com), free and CC0."
        blocks = {}
        options = []
        for asset in assets:
            block = [f"- {asset['name']} (ID: {asset['id']})"]
            block.append(f"  Type: {asset['type']}  |  {asset['url']}")
            if asset.get("authors"):
                block.append(f"  By: {', '.join(asset['authors'])}")
            if asset.get("category"):
                block.append(f"  Category: {asset['category']}")
            if asset.get("tags"):
                block.append(f"  Tags: {', '.join(asset['tags'])}")
            if asset.get("attributes"):
                attributes = ", ".join(
                    f"{k}={v if not isinstance(v, list) else '/'.join(v)}"
                    for k, v in asset["attributes"].items()
                )
                block.append(f"  Attributes: {attributes}")
            size = asset.get("dimensions_mm")
            if size:
                metres = " x ".join(f"{v / 1000:g}m" for v in size)
                axes = " (W x D x H)" if len(size) == 3 else ""
                block.append(f"  Real-world size: {metres}{axes}")
            if asset.get("max_resolution"):
                block.append(f"  Up to: {'x'.join(str(v) for v in asset['max_resolution'])}")
            if asset.get("downloads") is not None:
                block.append(f"  Downloads: {asset['downloads']}")
            if asset.get("description"):
                block.append(f"  {asset['description']}")
            lines.extend(block)
            lines.append("")
            blocks[asset["id"]] = "\n".join(block) + f"\n\n{credit}"
            options.append(PickerOption(
                id=asset["id"],
                title=asset["name"],
                description=" · ".join(filter(None, [asset.get("type"), asset.get("category")])) or None,
                thumbnail=_polyhaven_thumbnail(asset),
            ))

        lines.append(credit)
        listing = "\n".join(lines)
        picked = await pick_asset(ctx, f"Pick a Poly Haven asset for: {query or 'your scene'}", "Asset", options)
        return picked_reply("Poly Haven", picked, blocks, listing) if picked else listing
    except Exception as e:
        logger.error(f"Error searching Polyhaven assets: {str(e)}")
        return f"Error searching Polyhaven assets: {str(e)}"

async def _download_polyhaven(
    ctx: Context,
    asset_id: str,
    asset_type: str,
    resolution: str = "1k",
    file_format: str | None = None,
) -> str:
    """import_asset(source="polyhaven"): download an HDRI, texture or model and say where it came from."""
    try:
        result = await _send("download_polyhaven_asset", {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "resolution": resolution,
            "file_format": file_format
        })
        
        if "error" in result:
            return f"Error: {result['error']}"
        
        if result.get("success"):
            message = result.get("message", "Asset downloaded and imported successfully")

            # Add additional information based on asset type
            if asset_type == "hdris":
                message = f"{message}. The HDRI has been set as the world environment."
            elif asset_type == "textures":
                material_name = result.get("material", "")
                maps = ", ".join(result.get("maps", []))
                message = (
                    f"{message}. Created material '{material_name}' with maps: {maps}. "
                    f"{POLYHAVEN_UNUSED_NOTE}"
                    f"{_polyhaven_scale_note(result)}"
                )
            elif asset_type == "models":
                message = f"{message}. The model has been imported into the current scene."

            # Where it came from. The sidebar checkbox names Poly Haven, but in
            # an agentic session nobody opens the sidebar - the chat is the only
            # place the person receiving the asset can see whose it is.
            return f"{message}\n\n{_polyhaven_credit(result)}"
        else:
            return f"Failed to download asset: {result.get('message', 'Unknown error')}"
    except Exception as e:
        logger.error(f"Error downloading Polyhaven asset: {str(e)}")
        return f"Error downloading Polyhaven asset: {str(e)}"

async def _set_texture(
    ctx: Context,
    object_name: str,
    texture_id: str) -> str:
    """Apply a downloaded Poly Haven texture to an object, replacing its materials (import_asset's apply_to)."""
    try:
        result = await _send("set_texture", {
            "object_name": object_name,
            "texture_id": texture_id
        })
        
        if "error" in result:
            return f"Error: {result['error']}"
        
        if result.get("success"):
            material_name = result.get("material", "")
            maps = ", ".join(result.get("maps", []))
            
            # Add detailed material info
            material_info = result.get("material_info", {})
            node_count = material_info.get("node_count", 0)
            has_nodes = material_info.get("has_nodes", False)
            texture_nodes = material_info.get("texture_nodes", [])
            
            output = f"Successfully applied texture '{texture_id}' to {object_name}.\n"
            output += f"Using material '{material_name}' with maps: {maps}.\n\n"
            output += f"Material has nodes: {has_nodes}\n"
            output += f"Total node count: {node_count}\n\n"
            
            if texture_nodes:
                output += "Texture nodes:\n"
                for node in texture_nodes:
                    output += f"- {node['name']} using image: {node['image']}\n"
                    if node['connections']:
                        output += "  Connections:\n"
                        for conn in node['connections']:
                            output += f"    {conn}\n"
            else:
                output += "No texture nodes found in the material.\n"

            return f"{output}\n{_polyhaven_credit(result)}"
        else:
            return f"Failed to apply texture: {result.get('message', 'Unknown error')}"
    except Exception as e:
        logger.error(f"Error applying texture: {str(e)}")
        return f"Error applying texture: {str(e)}"


def _sketchfab_thumbnail(model: dict) -> str | None:
    """The smallest thumbnail at least 256px wide, else the largest there is."""
    images = [
        i for i in ((model.get("thumbnails") or {}).get("images") or [])
        if isinstance(i, dict) and str(i.get("url", "")).startswith("https://")
    ]
    if not images:
        return None
    width = lambda i: i.get("width") or 0
    big_enough = [i for i in images if width(i) >= 256]
    return (min(big_enough, key=width) if big_enough else max(images, key=width))["url"]


async def _search_sketchfab(
    ctx: Context,
    query: str,
    categories: str | None = None,
    count: int = 20,
    downloadable: bool = True) -> str:
    """search_assets(source="sketchfab"): matching models with author, licence and face count."""
    try:
        logger.info(f"Searching Sketchfab models with query: {query}, categories: {categories}, count: {count}, downloadable: {downloadable}")
        result = await _send("search_sketchfab_models", {
            "query": query,
            "categories": categories,
            "count": count,
            "downloadable": downloadable
        })
        
        if "error" in result:
            logger.error(f"Error from Sketchfab search: {result['error']}")
            return f"Error: {result['error']}"
        
        # Safely get results with fallbacks for None
        if result is None:
            logger.error("Received None result from Sketchfab search")
            return "Error: Received no response from Sketchfab search"
            
        # Format the results
        models = result.get("results", []) or []
        if not models:
            return f"No models found matching '{query}'"
            
        formatted_output = f"Found {len(models)} models matching '{query}':\n\n"
        blocks = {}
        options = []

        for model in models:
            if model is None:
                continue

            model_name = model.get("name", "Unnamed model")
            model_uid = model.get("uid", "Unknown ID")
            block = f"- {model_name} (UID: {model_uid})\n"

            # Get user info with safety checks
            user = model.get("user") or {}
            username = user.get("username", "Unknown author") if isinstance(user, dict) else "Unknown author"
            block += f"  Author: {username}\n"

            # Get license info with safety checks
            license_data = model.get("license") or {}
            license_label = license_data.get("label", "Unknown") if isinstance(license_data, dict) else "Unknown"
            block += f"  License: {license_label}\n"

            # Add face count and downloadable status
            face_count = model.get("faceCount", "Unknown")
            is_downloadable = "Yes" if model.get("isDownloadable") else "No"
            block += f"  Face count: {face_count}\n"
            block += f"  Downloadable: {is_downloadable}\n"
            formatted_output += block + "\n"
            blocks[model_uid] = block
            options.append(PickerOption(
                id=model_uid,
                title=model_name,
                description=f"{username} · {license_label} · {face_count} faces",
                thumbnail=_sketchfab_thumbnail(model),
            ))

        picked = await pick_asset(ctx, f"Pick a Sketchfab model for: {query}", "Model", options)
        return picked_reply("Sketchfab", picked, blocks, formatted_output) if picked else formatted_output
    except Exception as e:
        logger.error(f"Error searching Sketchfab models: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Error searching Sketchfab models: {str(e)}"


async def _download_sketchfab(
    ctx: Context,
    uid: str,
    target_size: float) -> str:
    """import_asset(source="sketchfab"): import a model scaled so its largest side is target_size."""
    try:
        logger.info(f"Downloading Sketchfab model: {uid}, target_size={target_size}")

        result = await _send("download_sketchfab_model", {
            "uid": uid,
            "normalize_size": True,  # Always normalize
            "target_size": target_size
        })
        
        if result is None:
            logger.error("Received None result from Sketchfab download")
            return "Error: Received no response from Sketchfab download request"
            
        if "error" in result:
            logger.error(f"Error from Sketchfab download: {result['error']}")
            return f"Error: {result['error']}"
        
        if result.get("success"):
            imported_objects = result.get("imported_objects", [])
            object_names = ", ".join(imported_objects) if imported_objects else "none"
            
            output = f"Successfully imported model.\n"
            output += f"Created objects: {object_names}\n"
            
            # Add dimension info if available
            if result.get("dimensions"):
                dims = result["dimensions"]
                output += f"Dimensions (X, Y, Z): {dims[0]:.3f} x {dims[1]:.3f} x {dims[2]:.3f} meters\n"
            
            # Add bounding box info if available
            if result.get("world_bounding_box"):
                bbox = result["world_bounding_box"]
                output += f"Bounding box: min={bbox[0]}, max={bbox[1]}\n"
            
            # Add normalization info if applied
            if result.get("normalized"):
                scale = result.get("scale_applied", 1.0)
                output += f"Size normalized: scale factor {scale:.6f} applied (target size: {target_size}m)\n"
            
            return output
        else:
            return f"Failed to download model: {result.get('message', 'Unknown error')}"
    except Exception as e:
        logger.error(f"Error downloading Sketchfab model: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Error downloading Sketchfab model: {str(e)}"


# The model-facing tool surface. Each tool covers a job the model can't do
# with execute_blender_code alone: seeing the scene (look), asset libraries
# (search_assets, import_asset), and craft knowledge it
# loads only when needed (get_guide). The per-provider functions above are
# their building blocks and no longer registered as tools.

LOOK_MODES = ("viewport", "camera", "angles", "frames")
LOOK_ANGLES = ("front", "back", "left", "right", "top", "three_quarter")
LOOK_SHADING = ("solid", "material", "rendered", "wireframe", "xray")
# Modes before the shading/stats split, so a model trained on them gets pointed the right way.
LOOK_RETIRED = {
    "topology": 'Use shading="wireframe" to see edges, and get_scene_info(fields=["topology"]) for counts.',
    "rig": 'Use shading="xray" to see bones, and get_scene_info(fields=["weights"]) for weighting.',
    "image": 'Pass image= on its own, e.g. look(image="Render Result").',
}


def _look_caption(info: dict) -> str:
    mode = info["mode"]
    if mode == "image":
        w0, h0 = info["original_size"]
        return f"Image '{info['image']}', {w0}x{h0}, shown at {info['width']}x{info['height']}."
    parts = []
    if mode == "angles":
        parts.append("Tiles left to right, top to bottom: " + ", ".join(info.get("views", [])) + ".")
    if mode == "frames":
        parts.append("Frames left to right, top to bottom: " + ", ".join(map(str, info.get("frames", []))) + ".")
    if mode == "camera":
        parts.append(f"Through camera '{info.get('camera')}'.")
    if mode != "viewport":
        size = " x ".join(f"{v:g}" for v in info.get("size", []))
        parts.append(f"Framed {info.get('targets', 0)} objects, {size} m across, centred at {info.get('center')}.")
    return " ".join(parts)


@mcp.tool(annotations=_READ_ONLY, meta={"ui": {"resourceUri": VIEWPORT_URI}})
async def look(
    ctx: Context,
    mode: str | None = None,
    target: list[str] | None = None,
    views: list[str | list[float]] | None = None,
    distance: float | None = None,
    shading: str | None = None,
    frames: list[int] | None = None,
    frame_count: int = 6,
    view: str | list[float] | None = None,
    image: str | None = None,
    max_size: int = 768,
) -> CallToolResult:
    """
    See the scene as one image. For counts, sizes and positions, use get_scene_info.

    Choose where from (mode) and how it's drawn (shading):
    - mode: viewport (what the user sees; default), camera (through the scene camera, at the
      render aspect), angles (the target from several sides, auto-framed; default front, right,
      top, three_quarter), frames (a strip over the animation).
    - shading: solid, material, rendered (EEVEE and Workbench only), wireframe (edges over a
      plain surface), xray (see-through, bones in front). Default: the viewport's.
    - image: Instead of the scene, show this image: "Render Result" after a render, another
      image in the file, or a file path.

    Parameters:
    - target: Object names to frame (children included). Default: every visible object.
    - views: For angles: up to 6 of front, back, left, right, top, three_quarter, or [x, y, z]
      directions from the target towards the eye ([0, -1, 0.2] is front, slightly above).
    - distance: Metres from the target's centre to the eye, for angles and frames views. Default:
      far enough to fit it; closer for detail or to stand inside a room.
    - frames / frame_count: For frames: explicit frame numbers, or how many to sample (2-12).
    - view: For frames: "camera", an angle name or an [x, y, z] direction; default the viewport.
    - max_size: Longest side in pixels (default 768). Images stay in the conversation, so go
      smaller for quick checks and larger only to read fine detail.

    Every setting changed to take the picture is restored afterwards.
    """
    if mode in LOOK_RETIRED:
        return _app_error(f"There is no {mode} mode. {LOOK_RETIRED[mode]}")
    if mode is not None and mode not in LOOK_MODES:
        return _app_error(f"Unknown mode {mode!r}. Use one of: {', '.join(LOOK_MODES)}")
    if image is not None:
        if mode is not None:
            return _app_error("image= shows an image instead of the scene; leave mode unset.")
        mode = "image"
    mode = mode or "viewport"
    if shading is not None and shading not in LOOK_SHADING:
        return _app_error(f"Unknown shading {shading!r}. Use one of: {', '.join(LOOK_SHADING)}")
    for v in (views or []) + ([view] if view is not None and view != "camera" else []):
        if isinstance(v, str) and v not in LOOK_ANGLES:
            return _app_error(f"Unknown view {v!r}. Use one of {', '.join(LOOK_ANGLES)} or an [x, y, z] direction.")
        if not isinstance(v, str) and (len(v) != 3 or not any(v)):
            return _app_error(f"A view direction is three numbers, not all zero; got {v!r}.")
    args = {"mode": mode, "target": target, "views": views, "distance": distance, "shading": shading,
            "frames": frames, "frame_count": frame_count, "view": view, "image": image,
            "max_size": max(200, min(int(max_size or 768), 2000))}
    return await asyncio.to_thread(_look, mode, shading, max_size, args)


def _look(mode: str, shading: str | None, max_size: int, args: dict) -> CallToolResult:
    def native():
        return _viewport_screenshot(max_size=max_size)

    def scripted():
        return _look_via_script(args)

    # The plain viewport has a native command; everything else is a script.
    # Each falls back to the other, since old addons may have only one of them.
    first, second = (native, scripted) if mode == "viewport" and not shading else (scripted, native)
    try:
        return first()
    except _LookRefused as e:
        return _app_error(str(e))
    except Exception as e:
        reason = str(e)
    if mode == "image":
        # The viewport is no stand-in for the image that was asked for.
        hint = f" {ADDON_UPDATE_HINT}" if _addon_outdated() and ADDON_UPDATE_HINT not in reason else ""
        return _app_error(f"Couldn't show the image: {reason}{hint}")
    try:
        result = second()
    except Exception as e:
        hint = f" {ADDON_UPDATE_HINT}" if _addon_outdated() and ADDON_UPDATE_HINT not in reason else ""
        return _app_error(f"Couldn't capture the view: {reason}{hint}")
    if second is native:
        note = f"look(mode=\"{mode}\") isn't available here ({reason}), so this is the plain viewport."
        result.content.append(TextContent(type="text", text=note))
    return result


class _LookRefused(Exception):
    """A mistake in the request (a missing object, no camera): report it, don't fall back."""


def _look_via_script(args: dict) -> CallToolResult:
    path = os.path.join(tempfile.gettempdir(), f"blender_look_{os.getpid()}.png")
    info = _run_script(blender_scripts.LOOK, {**args, "filepath": path})
    if info.get("error"):
        raise _LookRefused(info["error"])
    with open(path, "rb") as f:
        png = f.read()
    os.remove(path)
    return CallToolResult(content=[_png_content(png), TextContent(type="text", text=_look_caption(info))])


ASSET_SOURCES = ("polyhaven", "ambientcg", "sketchfab")


def _unavailable(source: str, e: Exception, action: str) -> str:
    if _addon_lacks(e):
        label = {"polyhaven": "Poly Haven", "ambientcg": "ambientCG", "sketchfab": "Sketchfab"}[source]
        return missing_feature(f"{label} {action}", label)
    return f"Error: {e}"


def _preview_images(source: str, listing: str, count: int) -> list[ImageContent]:
    """Thumbnails of the first `count` results, read off the listing's ids."""
    if source == "ambientcg" and count > 0:
        ids = re.findall(r"\(ID: ([^)]+)\)", listing)[:count]
        return [ImageContent(type="image", data=data, mimeType=mime) for data, mime in ambientcg.thumbnails(ids)]
    pattern = {"polyhaven": r"\(ID: ([^)]+)\)", "sketchfab": r"\(UID: ([^)]+)\)"}.get(source)
    if not pattern or count <= 0:
        return []
    command = {"polyhaven": "get_polyhaven_asset_preview", "sketchfab": "get_sketchfab_model_preview"}[source]
    key = {"polyhaven": "asset_id", "sketchfab": "uid"}[source]
    images = []
    for ident in re.findall(pattern, listing)[:count]:
        try:
            result = get_blender_connection().send_command(command, {key: ident}, read_only=True)
            images.append(ImageContent(type="image", data=result["image_data"],
                                       mimeType=f"image/{result.get('format', 'png').replace('jpg', 'jpeg')}"))
        except Exception as e:
            logger.debug(f"Preview of {ident} failed: {e}")
    return images


@mcp.tool()
async def search_assets(
    ctx: Context,
    source: str,
    query: str = "",
    asset_type: str = "all",
    category: str | None = None,
    attributes: dict | None = None,
    min_size_m: float | None = None,
    limit: int = 20,
    previews: int = 0,
):
    """
    Search a library of existing assets. The sources:
    - polyhaven: HDRIs, PBR textures and realistic models, all CC0. Search understands intent and
      synonyms ("couch" finds sofas).
    - ambientcg: CC0 PBR materials (about 2000), including surfaces Poly Haven lacks, Japanese
      ones such as tatami among them. Every word of the query must match; keep it to 1-2 words.
    - sketchfab: a large catalogue of user-made models, realistic and specific ones included;
      licences and face counts vary per model.

    Parameters:
    - source: polyhaven, ambientcg or sketchfab.
    - query: What you're looking for, in plain words.
    - asset_type: polyhaven only: hdris, textures, models or all.
    - category: Optional. polyhaven: a category path ("Metal/Sheet & Corrugated"). sketchfab:
      comma-separated categories.
    - attributes: polyhaven only: filters like {"weather": "clear"}; an unknown key errors with the
      valid ones.
    - min_size_m: polyhaven only: minimum real-world size in metres. Use 2+ for walls, floors and
      ground so textures don't visibly repeat.
    - limit: Number of results.
    - previews: Attach thumbnails of the first N results (max 6; polyhaven, ambientcg, sketchfab). Cheaper
      than importing the wrong asset.

    Results include each asset's id; pass it to import_asset.
    """
    source = (source or "").lower()
    if source not in ASSET_SOURCES:
        return f"Error: source must be one of {', '.join(ASSET_SOURCES)}"
    limit = max(1, min(int(limit or 20), 50))
    try:
        if source == "polyhaven":
            listing = await _search_polyhaven(
                ctx, query=query or None, asset_type=asset_type, category=category, attributes=attributes,
                min_size_m=min_size_m, limit=limit)
        elif source == "ambientcg":
            listing = await ambientcg.search(query, asset_type=asset_type, limit=limit)
        else:
            if not query:
                return "Error: sketchfab needs a query."
            listing = await _search_sketchfab(
                ctx, query=query, categories=category, count=limit)
    except Exception as e:
        return _unavailable(source, e, "search")
    if listing.lower().startswith("error") and _addon_lacks(listing):
        return _unavailable(source, Exception(listing), "search")
    images = await asyncio.to_thread(_preview_images, source, listing, max(0, min(int(previews or 0), 6)))
    if not images:
        return listing
    return CallToolResult(content=[TextContent(type="text", text=listing), *images])


@mcp.tool()
async def import_asset(
    ctx: Context,
    source: str,
    id: str,
    asset_type: str | None = None,
    target_size: float | None = None,
    apply_to: list[str] | None = None,
    resolution: str = "1k",
    file_format: str | None = None,
) -> str:
    """
    Download an asset found with search_assets and bring it into the scene.

    Parameters:
    - source: polyhaven, ambientcg or sketchfab.
    - id: The asset's id (UID for sketchfab) from search_assets.
    - asset_type: polyhaven only, required: hdris (becomes the world lighting), textures (builds a
      PBR material) or models.
    - target_size: Size in metres of the model's largest dimension (chair 1.0, car 4.5, cup 0.12).
      Required for sketchfab; library models come at arbitrary scale.
    - apply_to: polyhaven textures and ambientcg: object names to put the material on (replaces
      their materials). Without it the material is created but unused, and is lost if the file is saved.
    - resolution: polyhaven and ambientcg: 1k, 2k, 4k or 8k. 1k-2k for background, 4k for close-ups.
    - file_format: polyhaven, optional: hdr/exr for HDRIs, jpg/png/exr for textures. ambientcg:
      jpg (default) or png.

    Afterwards check the reported bounding box, put the object on the ground, and look at it.
    """
    source = (source or "").lower()
    if source not in ASSET_SOURCES:
        return f"Error: source must be one of {', '.join(ASSET_SOURCES)}"
    reply = await _import_asset(ctx, source, id, asset_type, target_size, apply_to, resolution, file_format)
    # The download helpers report failures as text, so an unknown command arrives inside it.
    if reply.lower().startswith("error") and _addon_lacks(reply):
        return _unavailable(source, Exception(reply), "import")
    # Old addons can fail on a newer Blender (removed node types and the like).
    if "error" in reply.lower() and _addon_outdated() and ADDON_UPDATE_HINT not in reply:
        reply += f"\n\nThe Blender addon is out of date, which may be the cause. {ADDON_UPDATE_HINT}"
    return reply


def _download_ambientcg(asset_id, resolution, file_format, apply_to) -> str:
    """import_asset(source="ambientcg"): the addon downloads the zip and builds the material."""
    result = get_blender_connection().send_command("download_ambientcg_material", {
        "asset_id": asset_id,
        "resolution": (resolution or "2k").upper(),
        "file_format": (file_format or "jpg").upper(),
        "apply_to": list(apply_to or []),
    })
    if result.get("error"):
        return f"Error: {result['error']}"
    lines = [f"Imported ambientCG material {asset_id} ({result.get('resolution')}) as material "
             f"'{result.get('material')}' with maps: {', '.join(result.get('maps') or [])}."]
    size = result.get("size_m")
    if size:
        lines.append(f"One texture tile covers {size[0]:g} x {size[1]:g} m: for real-world scale set the "
                     "Mapping node's Scale to surface size / tile size.")
    else:
        lines.append("ambientCG gives no real-world size for this material: judge the tiling with look.")
    if result.get("applied"):
        lines.append(f"Applied to: {', '.join(result['applied'])} (their previous materials were replaced).")
    else:
        lines.append("Not applied to anything: pass apply_to, or assign it yourself; an unused material is "
                     "dropped when the file is saved.")
    if result.get("not_found"):
        lines.append(f"Not found, so not applied: {', '.join(result['not_found'])}.")
    lines.append(f"{ambientcg.CREDIT} {result.get('url', '')}")
    return "\n".join(lines)


async def _import_asset(ctx, source, id, asset_type, target_size, apply_to, resolution, file_format) -> str:
    try:
        if source == "polyhaven":
            if asset_type not in ("hdris", "textures", "models"):
                return "Error: polyhaven needs asset_type: hdris, textures or models."
            reply = await _download_polyhaven(
                ctx, asset_id=id, asset_type=asset_type, resolution=resolution, file_format=file_format)
            if asset_type == "textures" and apply_to and not reply.lower().startswith(("error", "failed")):
                applied = []
                for object_name in apply_to:
                    result = await _set_texture(ctx, object_name=object_name, texture_id=id)
                    applied.append(result.splitlines()[0] if result else f"{object_name}: no reply")
                applied_note = "Applied:\n" + "\n".join(applied) + "\n"
                reply = reply.replace(" " + POLYHAVEN_UNUSED_NOTE + " ", "\n" + applied_note)
                reply = reply.replace(" " + POLYHAVEN_UNUSED_NOTE, "\n" + applied_note)
            return reply
        if source == "ambientcg":
            return await asyncio.to_thread(_download_ambientcg, id, resolution, file_format, apply_to)
        if not target_size:
            return "Error: sketchfab needs target_size (metres, largest dimension)."
        return await _download_sketchfab(ctx, uid=id, target_size=target_size)
    except Exception as e:
        return _unavailable(source, e, "import")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_guide(topic: str) -> str:
    """Read a workflow guide: bpy, scene, level-design, animation, rigging,
    retopology, materials, japanese-design, quality-review, surface-realism,
    lighting-and-rendering, environment-art, geometry-nodes, modeling or unreal-engine. An unknown topic returns the available guide index.
    """
    return guides.get(topic)


def _register_guide_resource(guide: guides.Guide) -> None:
    @mcp.resource(f"guide://{guide.topic}", name=guide.title,
                  description=guide.summary, mime_type="text/markdown")
    def read_guide() -> str:
        return guide.body


for _guide in guides.all_guides().values():
    _register_guide_resource(_guide)


# MCP Apps and OpenAI extensions. Tools marked visibility ["app"] are called by
# the host UI, never by the model, and are hidden from clients without MCP Apps.

_APP_ONLY = {"ui": {"visibility": ["app"]}}


@mcp.tool(annotations=_READ_ONLY, meta=_APP_ONLY)
async def scene_state(since: int = 0) -> CallToolResult:
    """Poll Blender's shared scene version; changed means version > since.

    Versions last for this Blender/addon process and also advance on file loads.
    """
    return await asyncio.to_thread(_scene_state, since)


def _scene_state(since: int) -> CallToolResult:
    try:
        deadline = time.monotonic() + 5.0
        blender = get_blender_connection(handshake=False, timeout=5.0)
        state = blender.send_command("get_scene_state", read_only=True,
                                     timeout=max(0.001, deadline - time.monotonic()))
        state = {**state, "changed": state["version"] > since}
        return CallToolResult(
            content=[TextContent(type="text", text=f"Scene '{state['scene']}' | version {state['version']} | changed {state['changed']}")],
            structuredContent=state,
        )
    except Exception as e:
        return _app_error(missing_feature("scene state") if _addon_lacks(e) else f"Could not read scene state: {e}")
_SCENE_ITEM_KINDS = ("object", "material", "collection")


def _scene_items(query: str, limit: int = 30) -> list[dict]:
    blender = get_blender_connection()
    if (_addon_protocol() or 0) >= 12:
        result = blender.send_command("list_scene_items", {"query": query, "limit": limit})
        return result.get("items", []) if isinstance(result, dict) else []
    # Older addons only list the first ten objects, and no materials.
    result = blender.send_command("get_scene_info")
    needle = query.strip().lower()
    return [
        {"kind": "object", "name": o["name"], "detail": f"{o.get('type', '').title()} object"}
        for o in (result.get("objects") or [])
        if needle in o["name"].lower()
    ]


def _scene_item_uri(kind: str, name: str) -> str:
    return f"blender://{kind}/{quote(name, safe='')}"


@mcp.tool(
    title="Mention Blender items",
    annotations=_READ_ONLY,
    meta={"openai/extensions": {"mentions/search": {}}, **_APP_ONLY},
)
async def search_mentions(query: str = "") -> CallToolResult:
    """Search scene objects, materials and collections to @-mention in the composer."""
    try:
        items = await asyncio.to_thread(_scene_items, query)
    except Exception as e:
        logger.debug(f"Mention search failed: {e}")
        items = []
    links = [
        ResourceLink(
            type="resource_link",
            uri=_scene_item_uri(item["kind"], item["name"]),
            name=item["name"],
            title=item["name"],
            description=item.get("detail"),
            mimeType="application/json",
        ).model_dump(by_alias=True, exclude_none=True, mode="json")
        for item in items
        if item.get("kind") in _SCENE_ITEM_KINDS
    ]
    return CallToolResult(content=[], structuredContent={"items": links})


@mcp.resource("blender://object/{name}", mime_type="application/json")
async def object_resource(name: str) -> str:
    """A Blender object's transform, materials and mesh stats."""
    return json.dumps(await _send("get_object_info", {"name": unquote(name)}))


def _scene_item_resource(kind: str, name: str) -> str:
    name = unquote(name)
    for item in _scene_items(name, limit=100):
        if item.get("kind") == kind and item.get("name") == name:
            return json.dumps(item)
    raise ValueError(f"No {kind} named {name!r} in the open Blender file")


@mcp.resource("blender://material/{name}", mime_type="application/json")
async def material_resource(name: str) -> str:
    """A Blender material and the objects that use it."""
    return await asyncio.to_thread(_scene_item_resource, "material", name)


@mcp.resource("blender://collection/{name}", mime_type="application/json")
async def collection_resource(name: str) -> str:
    """A Blender collection and how many objects it holds."""
    return await asyncio.to_thread(_scene_item_resource, "collection", name)


@mcp.resource(
    VIEWPORT_URI,
    name="viewport",
    title=VIEWPORT_TITLE,
    mime_type=APP_MIME_TYPE,
    meta={
        "ui": {"prefersBorder": False},
        # Fullscreen only: every screenshot updates the one live view rather
        # than leaving a card in the thread.
        "openai/ui": {"preferredDisplayMode": "fullscreen", "availableDisplayModes": ["fullscreen"]},
    },
)
def viewport_app() -> str:
    return viewport_html()


def _png_content(png: bytes) -> ImageContent:
    return ImageContent(type="image", data=base64.b64encode(png).decode("ascii"), mimeType="image/png")


def _viewport_snapshot() -> tuple[dict, bytes | None]:
    state, png = viewport_store.snapshot()
    # An addon older than this server can't pick objects, so the app says to
    # update it instead of quietly attaching only the image.
    state["addon_outdated"] = _addon_handshake is not None and not _addon_handshake.up_to_date
    return state, png


def _viewport_result(since: int) -> CallToolResult:
    """The viewport state, with the image only when it is newer than `since`."""
    state, png = _viewport_snapshot()
    content = []
    if png is not None and state["seq"] > since:
        content.append(_png_content(png))
    return CallToolResult(content=content, structuredContent=state)


@mcp.tool(
    title=VIEWPORT_TITLE,
    annotations=_READ_ONLY,
    icons=[viewport_icon()],
    meta={
        "ui": {"resourceUri": VIEWPORT_URI, "visibility": ["app"]},
        "openai/ui": {"entrypoints": [{"type": "thread"}]},
    },
)
def open_viewport() -> CallToolResult:
    """Show the latest Blender viewport screenshot beside the conversation."""
    return _viewport_result(since=0)


@mcp.tool(annotations=_READ_ONLY, meta=_APP_ONLY)
def viewport_latest(since: int = 0) -> CallToolResult:
    """The latest viewport screenshot, if newer than `since`. Never touches Blender."""
    return _viewport_result(since)


@mcp.tool(annotations=_READ_ONLY, meta=_APP_ONLY)
async def viewport_capture(max_size: int = 1000, auto: bool = False) -> CallToolResult:
    """Capture a fresh viewport screenshot for the Viewport app.

    `auto` marks a capture the app took on its own after the scene changed,
    rather than one the user asked for with Refresh.
    """
    try:
        await asyncio.to_thread(_store_capture, max_size, "auto" if auto else "user")
    except Exception as e:
        return _app_error(f"Couldn't capture the viewport: {e}")
    return _viewport_result(since=0)


def _app_error(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], isError=True)


@mcp.tool(annotations=_READ_ONLY, meta=_APP_ONLY)
async def viewport_pick(seq: int, x: float, y: float) -> CallToolResult:
    """The object under a click on viewport capture `seq`.

    `x` and `y` run 0..1 from the image's top-left corner. The ray uses the
    camera that capture was rendered with, so it works after the user has
    orbited the view, against the scene as it is now.
    """
    view = viewport_store.view(seq)
    if view is None:
        return _app_error("This screenshot can't be clicked on. Press Refresh for a new one.")
    try:
        hit = await _send("pick_viewport_object", {**view, "x": x, "y": y})
    except Exception as e:
        return _app_error(f"Couldn't reach Blender: {e}")
    hit = hit if isinstance(hit, dict) else {}
    if hit.get("mismatch") == "file":
        name = os.path.basename(view.get("file") or "") or "an unsaved file"
        return _app_error(f"This screenshot is of {name}, which isn't open in Blender now. Press Refresh for a new one.")
    if hit.get("mismatch") == "scene":
        return _app_error(
            f"This screenshot is of the scene '{view.get('scene')}', but Blender is showing "
            f"'{hit.get('current')}'. Switch back to it, or press Refresh."
        )
    obj = hit.get("object")
    if not obj:
        return CallToolResult(content=[], structuredContent={"object": None})
    link = ResourceLink(
        type="resource_link",
        uri=_scene_item_uri("object", obj["name"]),
        name=obj["name"],
        title=obj["name"],
        description=obj.get("detail"),
        mimeType="application/json",
    ).model_dump(by_alias=True, exclude_none=True, mode="json")
    return CallToolResult(content=[], structuredContent={"object": {**obj, "link": link}})


_client_features_logged = False


def _log_client_features(session) -> None:
    """Log once what the client advertised, since that decides which UI features it gets."""
    global _client_features_logged
    if _client_features_logged:
        return
    _client_features_logged = True
    params = getattr(session, "client_params", None)
    info = getattr(params, "clientInfo", None)
    logger.info(
        f"MCP client {getattr(info, 'name', '?')} {getattr(info, 'version', '')}: "
        f"extensions={sorted(client_extensions(session))}, apps={supports_apps(session)}, "
        f"openai_forms={supports_openai_forms(session)}"
    )


async def _list_tools_for_client():
    tools = await mcp.list_tools()
    try:
        session = mcp.get_context().session
    except Exception:
        return tools
    _log_client_features(session)
    if supports_apps(session):
        return tools
    return [t for t in tools if not is_app_only(t)]


mcp._mcp_server.list_tools()(_list_tools_for_client)


# Main execution

def main():
    """Run the MCP server, or addon install CLI subcommands."""
    global CLI_HOST, CLI_PORT

    if len(sys.argv) > 1 and sys.argv[1] in {"install-addon", "addon-paths", "setup", "update", "-h", "--help"}:
        code = run_addon_cli(sys.argv[1:])
        if code >= 0:
            raise SystemExit(code)

    CLI_HOST, CLI_PORT = parse_connection_args(sys.argv[1:])

    # When run by hand (stdin is a TTY) the server appears to "hang" while it
    # silently waits for an MCP client; log a hint so that state is obvious.
    # Launched by a client, stdin is a pipe so this is skipped, and logging goes
    # to stderr, never to the stdio protocol on stdout.
    try:
        interactive = sys.stdin.isatty()
    except (AttributeError, OSError):
        interactive = False
    if interactive:
        logger.info(
            "BlenderMCP is an MCP server and is meant to be launched by your MCP "
            "client (Claude Desktop, Cursor, VS Code, ...), not run by hand. "
            "It will now wait silently for a client on stdin -- that is normal, "
            "not a hang. Press Ctrl-C to exit. "
            "Setup guide: README.md in the Roxy-BlenderMCP checkout "
            f"(if the addon is outdated this logs how to update it: {INSTALL_ADDON_COMMAND})"
        )
    context_log.install(mcp, SERVER_INSTRUCTIONS)
    mcp.run()

if __name__ == "__main__":
    main()
