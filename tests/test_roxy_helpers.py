"""The `roxy` helpers the addon gives every execute_code script, and the guides that document them."""

import ast
import re
from pathlib import Path

import pytest

from blender_mcp import guides
from blender_mcp.safe_mode import SandboxViolation, validate_code

ROOT = Path(__file__).resolve().parents[1]


def _helper_source() -> str:
    tree = ast.parse((ROOT / "src" / "blender_mcp" / "bundled" / "addon.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "_ROXY_HELPERS_SOURCE" for t in node.targets):
            return node.value.value
    raise AssertionError("addon.py has no _ROXY_HELPERS_SOURCE")


def _public_helpers() -> set[str]:
    return {n.name for n in ast.parse(_helper_source()).body
            if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}


def test_every_helper_a_guide_mentions_exists():
    public = _public_helpers()
    for topic, guide in guides.all_guides().items():
        for name in set(re.findall(r"roxy\.(\w+)", guide.body)):
            assert name in public, f"{topic} guide mentions roxy.{name}, which the addon doesn't define"


def test_guides_no_longer_carry_the_helper_code():
    for guide in guides.all_guides().values():
        for name in _public_helpers():
            assert f"def {name}(" not in guide.body



def test_safe_mode_lets_scripts_use_roxy():
    validate_code('obj = roxy.box("Top", (1.0, 0.5, 0.03), (0, 0, 0.7))\nroxy.assemble("T", [obj])\n')


@pytest.mark.parametrize("code", ["roxy = 1\n", "def roxy():\n    pass\n", "import os as roxy\n"])
def test_safe_mode_refuses_rebinding_roxy(code):
    with pytest.raises(SandboxViolation):
        validate_code(code)
