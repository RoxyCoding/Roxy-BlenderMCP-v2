"""Server instructions carry the rules that keep generated Blender code working.

The guidance used to live in an asset_creation_strategy prompt, but MCP prompts
are user-invoked and the model can't fetch one, so clients effectively got none.
That is how generated scripts ended up looking shader nodes up by localized name
(#26) and hardcoding render engine identifiers from a different Blender version
(#110).

These tests deliberately assert on API identifiers rather than prose, so the wording
stays free to change.
"""

from blender_mcp import session_rules
from blender_mcp.server import SERVER_INSTRUCTIONS, mcp


def test_instructions_are_advertised_to_clients():
    assert mcp.instructions
    assert mcp.instructions == SERVER_INSTRUCTIONS


def test_instructions_name_the_apis_that_keep_scripts_portable():
    # Node type lookup instead of localized names (#26); reading enum values
    # instead of hardcoding identifiers (#110).
    assert "BSDF_PRINCIPLED" in SERVER_INSTRUCTIONS
    assert "bl_rna" in SERVER_INSTRUCTIONS
    assert "get_addon_status" in SERVER_INSTRUCTIONS


def test_instructions_fit_claude_codes_cap():
    # Claude Code silently cuts server instructions at 2048 characters; anything
    # longer belongs in session_rules.md. #347 tracks context cost.
    assert len(SERVER_INSTRUCTIONS) < 2048


def test_instructions_carry_the_asset_workflow():
    for name in ("get_addon_status", "world_bounding_box"):
        assert name in SERVER_INSTRUCTIONS
    for name in ("search_assets", "import_asset", "ambientCG", "world_bounding_box"):
        assert name in session_rules.text()


def test_instructions_announce_the_session_rules():
    assert "session rules" in SERVER_INSTRUCTIONS


def test_instructions_do_not_point_at_an_unreachable_prompt():
    assert "asset_creation_strategy" not in SERVER_INSTRUCTIONS


def test_instructions_send_the_model_to_look():
    assert "look" in SERVER_INSTRUCTIONS
