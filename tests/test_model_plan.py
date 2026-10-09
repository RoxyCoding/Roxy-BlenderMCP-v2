"""model_plan: a multi-part subject's structure is checked before building and verified after."""

import asyncio
import copy
import json

import pytest

from blender_mcp import model_plan, server

LEGS = [("Leg_FL", 0.625, -0.35), ("Leg_FR", -0.625, -0.35), ("Leg_BL", 0.625, 0.35), ("Leg_BR", -0.625, 0.35)]
TABLE = {
    "name": "Table", "purpose": "dining table for four", "size": [1.29, 0.74, 0.7],
    "parts": [{"name": "Top", "shape": "box", "size": [1.29, 0.74, 0.03], "at": [0, 0, 0.67],
               "rests_on": [n for n, _, _ in LEGS]}]
    + [{"name": n, "shape": "box", "size": [0.04, 0.04, 0.67], "at": [x, y, 0], "rests_on": ["ground"]}
       for n, x, y in LEGS],
}


def _plan(**changes):
    plan = copy.deepcopy(TABLE)
    for path, value in changes.items():
        part, key = path.split("__")
        next(p for p in plan["parts"] if p["name"] == part)[key] = value
    return plan


def test_a_sound_plan_passes():
    report = model_plan.check(TABLE)
    assert report.ok, report.text("plan")
    assert not report.warnings


@pytest.mark.parametrize("changes, expected", [
    ({"Top__at": [0, 0, 0.75]}, "Top: rests on Leg_FL but does not touch it"),
    ({"Leg_FL__at": [0.625, -0.35, 0.1]}, "Leg_FL: rests on the ground but its bottom would be at 0.100"),
    ({"Top__rests_on": []}, "Top: nothing holds it up"),
    ({"Top__rests_on": ["Shelf"]}, "rests_on 'Shelf', which is not a part"),
    ({"Leg_FL__size": [0.04, 0.0, 0.67]}, "Leg_FL: size must be"),
    ({"Top__shape": "sphere"}, "shape must be one of"),
])
def test_structural_mistakes_are_errors(changes, expected):
    report = model_plan.check(_plan(**changes))
    assert not report.ok
    assert any(expected in e for e in report.errors), report.errors


def test_a_chain_that_never_reaches_the_ground_floats():
    plan = copy.deepcopy(TABLE)
    plan["parts"] = [
        {"name": "A", "size": [0.1, 0.1, 0.1], "at": [0, 0, 1.0], "rests_on": ["B"]},
        {"name": "B", "size": [0.1, 0.1, 0.1], "at": [0, 0, 1.1], "rests_on": ["A"]},
    ]
    plan["size"] = [0.1, 0.1, 0.2]
    errors = model_plan.check(plan).errors
    assert any("No part rests on the ground" in e for e in errors)
    assert any("never reach the ground" in e for e in errors)


def test_size_mismatch_and_unexplained_overlap_are_warnings():
    plan = copy.deepcopy(TABLE)
    plan["size"] = [1.5, 0.74, 0.7]
    # A box standing where a leg already is: 30% of the leg's volume, and nothing says why.
    plan["parts"].append({"name": "Box", "size": [0.2, 0.2, 0.2], "at": [0.625, -0.35, 0],
                          "rests_on": ["ground"]})
    report = model_plan.check(plan)
    assert any("in x but size says 1.500" in w for w in report.warnings), report.warnings
    assert any("Leg_FL and Box share" in w for w in report.warnings), report.warnings


def test_missing_purpose_is_an_error():
    plan = copy.deepcopy(TABLE)
    del plan["purpose"]
    assert "Missing 'purpose'." in model_plan.check(plan).errors


def _built(plan, **moves):
    boxes = {f"{plan['name']}_{p['name']}": [list(b) for b in model_plan.part_box(p)] for p in plan["parts"]}
    for part, delta in moves.items():
        box = boxes[f"{plan['name']}_{part}"]
        boxes[f"{plan['name']}_{part}"] = [[box[0][i] + delta[i] for i in range(3)], [box[1][i] + delta[i] for i in range(3)]]
    return boxes


def test_verify_accepts_a_faithful_build_and_notes_extra_detail():
    actual = _built(TABLE)
    actual["Table_Screw"] = [[0, 0, 0.66], [0.01, 0.01, 0.67]]
    report = model_plan.verify(TABLE, actual)
    assert report.ok, report.text("verify")
    assert any("Screw" in n for n in report.notes)


def test_verify_catches_a_moved_part_a_missing_part_and_floating():
    actual = _built(TABLE, Top=(0, 0, 0.05))
    del actual["Table_Leg_BR"]
    errors = model_plan.verify(TABLE, actual).errors
    assert any("Leg_BR: missing" in e for e in errors)
    assert any("Top: sits 50 mm from where the plan puts it" in e for e in errors)
    assert any("Top: rests on Leg_FL but does not touch it" in e for e in errors)


# ------------------------------------------------------------------ the tool

class FakeBlender:
    def __init__(self, reply):
        self.reply, self.sent = reply, []

    def send_command(self, command, params=None, read_only=False):
        self.sent.append((command, params))
        return self.reply


@pytest.fixture(autouse=True)
def fresh_plans(monkeypatch):
    monkeypatch.setattr(server, "_checked_plans", {})


def _tool(**kw):
    return asyncio.run(server.model_plan(None, **kw))


def test_build_refuses_a_plan_that_was_not_checked(monkeypatch):
    blender = FakeBlender({"result": ""})
    monkeypatch.setattr(server, "get_blender_connection", lambda: blender)
    assert "no checked plan" in _tool(action="build", name="Table")
    bad = _plan(Top__at=[0, 0, 0.9])
    assert "NOT OK" in _tool(action="check", plan=bad)
    assert "no checked plan" in _tool(action="build", name="Table")
    assert blender.sent == []


def test_check_then_build_sends_the_checked_plan(monkeypatch):
    blender = FakeBlender({"result": "Table 5\n"})
    monkeypatch.setattr(server, "get_blender_connection", lambda: blender)
    assert "Plan: OK" in _tool(action="check", plan=TABLE)
    reply = _tool(action="build", name="Table")
    assert reply.startswith("Built Table (5 parts so far).")
    (command, params), = blender.sent
    assert command == "execute_code" and "roxy.build(json.loads(" in params["code"]
    assert json.dumps(TABLE) in json.loads(params["code"].split("json.loads(")[1].split("))\n")[0])


def test_verify_uses_the_plan_stored_on_the_assembly(monkeypatch):
    monkeypatch.setattr(server, "_run_script", lambda script, args: {"plan": json.dumps(TABLE), "parts": _built(TABLE)})
    assert _tool(action="verify", name="Table").startswith("Table against its plan: OK")


def test_every_tool_description_fits_claude_codes_cap():
    for tool in asyncio.run(server.mcp.list_tools()):
        assert len(tool.description or "") < 2048, tool.name
