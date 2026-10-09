"""model_plan: a multi-part subject's structure is checked before building and verified after."""

import asyncio
import copy
import json

import pytest

from blender_mcp import model_plan, server

LEGS = [("Leg_FL", 0.625, -0.35), ("Leg_FR", -0.625, -0.35), ("Leg_BL", 0.625, 0.35), ("Leg_BR", -0.625, 0.35)]
TABLE = {
    "name": "Table", "purpose": "dining table for four", "size": [1.29, 0.74, 0.7],
    "features": ["legs 40 mm square tapering to 28 mm at the foot", "top edge rounded R6",
                 "legs inset 35 mm from the top's edges"],
    "parts": [{"name": "Top", "shape": "box", "size": [1.29, 0.74, 0.03], "at": [0, 0, 0.67],
               "radius": 0.006, "rests_on": [n for n, _, _ in LEGS]}]
    + [{"name": n, "shape": "box", "size": [0.04, 0.04, 0.67], "at": [x, y, 0], "radius": 0.003,
        "bottom": [0.028, 0.028], "rests_on": ["ground"]}
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


def test_bare_primitives_are_flagged():
    plan = _plan(Top__radius=None, Leg_FL__radius=None, Leg_FL__bottom=None, Leg_FR__shape="cylinder",
                 Leg_FR__radius=None, Leg_FR__bottom=None)
    warnings = model_plan.check(plan).warnings
    assert any(w.startswith("Bare primitives: Top, Leg_FL, Leg_FR.") for w in warnings), warnings
    # A part that really is that plain shape says so; a tapered cylinder has its form.
    plan = _plan(Top__radius=None, Top__plain=True, Leg_FL__radius=None, Leg_FL__bottom=None,
                 Leg_FL__top=[0.03, 0.03], Leg_FR__shape="cylinder", Leg_FR__radius=None)
    assert not any("Bare primitives" in w for w in model_plan.check(plan).warnings)


@pytest.mark.parametrize("features", [None, [], ["oak"], ["oak", "four legs", " "]])
def test_a_plan_must_name_the_features_that_identify_the_real_thing(features):
    plan = copy.deepcopy(TABLE)
    plan["features"] = features
    errors = model_plan.check(plan).errors
    assert any(e.startswith("features must list at least 3 details") for e in errors), errors


@pytest.mark.parametrize("changes, expected", [
    ({"Top__radius": 0.5}, "Top: radius must be positive and at most half"),
    ({"Leg_FL__bottom": [0.05, 0.03]}, "Leg_FL: bottom must be [width, depth]"),
    ({"Leg_FL__top": [0.03]}, "Leg_FL: top must be [width, depth]"),
    ({"Leg_FL__bottom_radius": -1}, "Leg_FL: bottom_radius must be"),
])
def test_a_form_that_does_not_fit_the_part_is_an_error(changes, expected):
    errors = model_plan.check(_plan(**changes)).errors
    assert any(expected in e for e in errors), errors


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


def test_verify_lists_parts_still_built_as_bare_primitives():
    plan = _plan(Leg_BR__plain=True)
    bare = [["Table_Top", "box"], ["Table_Leg_FL", "prism"], ["Table_Leg_BR", "box"]]
    report = model_plan.verify(plan, _built(plan), primitives=bare)
    assert any(w.startswith("2 of 5 parts are still bare primitives: Leg_FL (prism), Top (box).")
               for w in report.warnings), report.warnings
    assert any("legs 40 mm square tapering" in n for n in report.notes), report.notes
    assert not any("bare primitives" in w for w in model_plan.verify(plan, _built(plan), primitives=[]).warnings)


def test_verify_catches_a_moved_part_a_missing_part_and_floating():
    actual = _built(TABLE, Top=(0, 0, 0.05))
    del actual["Table_Leg_BR"]
    errors = model_plan.verify(TABLE, actual).errors
    assert any("Leg_BR: missing" in e for e in errors)
    assert any("Top: sits 50 mm from where the plan puts it" in e for e in errors)
    assert any("Top: rests on Leg_FL but does not touch it" in e for e in errors)


POLE = {
    "name": "Stand", "purpose": "pole with a shelf", "size": [0.2, 0.2, 1.0],
    "features": ["100 mm steel pole", "square shelf", "shelf clamped to the pole"],
    "parts": [{"name": "Pole", "shape": "cylinder", "size": [0.1, 0.1, 1.0], "at": [0, 0, 0],
               "rests_on": ["ground"]}],
}


def _with(base, *parts, size=None):
    plan = copy.deepcopy(base)
    plan["parts"] += parts
    if size:
        plan["size"] = size
    return plan


def test_a_shelf_beside_a_round_pole_is_measured_from_its_surface():
    # The shelf's corner reaches into the pole's bounding box, but 7 mm short of the pole itself.
    shelf = {"name": "Shelf", "size": [0.06, 0.06, 0.02], "at": [0.07, 0.07, 0.5], "rests_on": ["Pole"]}
    errors = model_plan.check(_with(POLE, shelf)).errors
    assert any("Shelf: rests on Pole but does not touch it (gap 7 mm)" in e for e in errors), errors
    # Pressed against the pole's side, it touches.
    shelf["at"] = [0.08, 0, 0.5]
    assert not any("Shelf" in e for e in model_plan.check(_with(POLE, shelf)).errors)


def test_parts_that_meet_only_at_an_edge_hold_nothing():
    block = {"name": "Block", "size": [0.1, 0.1, 0.1], "at": [0.695, -0.42, 0.67], "rests_on": ["Leg_FL"]}
    errors = model_plan.check(_with(TABLE, block)).errors
    assert any("Block: meets Leg_FL only along an edge" in e for e in errors), errors


def test_parts_that_almost_meet_are_flagged_in_the_plan():
    box = {"name": "Box", "size": [0.1, 0.1, 0.1], "at": [0.71, -0.35, 0], "rests_on": ["ground"]}
    warnings = model_plan.check(_with(TABLE, box, size=[1.4, 0.74, 0.7])).warnings
    assert any("Leg_FL and Box are 15 mm apart" in w for w in warnings), warnings


def test_verify_measures_real_surfaces_when_blender_reports_them():
    actual = _built(TABLE)
    gaps = [["Table_Top", f"Table_{n}", 0.0] for n, _, _ in LEGS]
    assert model_plan.verify(TABLE, actual, gaps).ok
    # An open lid's tilted box still reaches the legs; its surface stops 20 mm short.
    gaps[0][2] = 0.02
    errors = model_plan.verify(TABLE, actual, gaps).errors
    assert any("Top: rests on Leg_FL but does not touch it (gap 20 mm)" in e for e in errors), errors


def test_verify_finds_floating_detail():
    actual = _built(TABLE)
    actual["Table_Bolt"] = [[0.3, 0, 0.71], [0.31, 0.01, 0.72]]         # 10 mm above the top
    actual["Table_Washer"] = [[0.5, 0, 0.75], [0.52, 0.02, 0.752]]
    actual["Table_Nut"] = [[0.5, 0, 0.752], [0.51, 0.01, 0.76]]          # on the floating washer
    errors = model_plan.verify(TABLE, actual).errors
    assert any(e.startswith("Bolt: touches nothing - it floats (10 mm") for e in errors), errors
    assert any(e.startswith("Washer: touches only Nut") for e in errors), errors
    assert any(e.startswith("Nut: touches only Washer") for e in errors), errors
    # Sunk into the top, the bolt is fixed.
    actual["Table_Bolt"] = [[0.3, 0, 0.69], [0.31, 0.01, 0.705]]
    assert not any("Bolt" in e for e in model_plan.verify(TABLE, actual).errors)


def test_verify_warns_about_near_misses_and_faces_almost_flush():
    actual = _built(TABLE)
    # A trim strip 12 mm short of the top, and an apron 3 mm proud of the leg it is fixed to.
    actual["Table_Trim"] = [[-0.6, -0.37, 0.6], [0.6, -0.36, 0.658]]
    actual["Table_Apron"] = [[0.605, -0.33, 0.55], [0.648, 0.33, 0.6]]
    report = model_plan.verify(TABLE, actual)
    assert any("Trim and Top are 12 mm apart" in w or "Top and Trim are 12 mm apart" in w
               for w in report.warnings), report.warnings
    assert any("Leg_FL and Apron: their max x faces are 3.0 mm off flush" in w for w in report.warnings), \
        report.warnings


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
