"""Plans for multi-part models: the structure written down, checked, then verified.

A plan is the model's understanding of a subject as data - what it is, its
overall size, and every part with its size, position and what holds it up -
so a structure that can't stand (a floating part, a part outside the whole, two
parts in one place, parts that only meet at an edge or almost meet) is caught
before any geometry exists, and the built result - its added detail included -
can be compared against it afterwards.

Coordinates are metres relative to the assembly's origin, which sits at the
bottom centre of the whole subject. A part's `at` is the bottom centre of its
axis-aligned box, like the roxy helpers' origins.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Two parts closer than this touch. Generous enough for bevels and float noise.
CONTACT_TOL = 0.005
# Parts closer than this without touching almost certainly were meant to meet:
# a shelf 1 cm from its post, a bolt hovering over its plate.
NEAR_MISS = 0.03
# Faces of two touching parts this close to flush, but not flush, read as a
# careless step: a side panel standing 3 mm proud of the post it is fixed to.
FLUSH_MIN, FLUSH_MAX = 0.001, 0.006
MAX_LISTED = 12
# Identifying features a plan must name: the details that make the subject this real thing
# rather than something like it.
MIN_FEATURES = 3
# A part this thin lying flat on another part's face is usually a feature of that part modelled
# by stacking (a frame, a panel, a lip) rather than shaped into it.
THIN = 0.012
# This many identical parts placed one by one are a row or grid that Geometry Nodes should make.
REPEATS = 5
SHAPES = ("box", "cylinder", "custom")
GROUND = "ground"
MOVES = ("hinge", "slide")
AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
# A hinge's pivot further than this from its part can't be on the part's edge.
PIVOT_REACH = 0.05
# Poses sampled across a moving part's range when looking for collisions.
MOTION_STEPS = 24


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def text(self, title: str) -> str:
        lines = [f"{title}: {'OK' if self.ok else 'NOT OK'}"]
        for label, items in (("Errors (fix these)", self.errors), ("Warnings (check these)", self.warnings),
                             ("Notes", self.notes)):
            if items:
                lines.append(f"{label}:")
                lines.extend(f"- {item}" for item in items)
        return "\n".join(lines)


Box = tuple[tuple[float, float, float], tuple[float, float, float]]


def part_box(part: dict) -> Box:
    sx, sy, sz = part["size"]
    x, y, z = part["at"]
    return (x - sx / 2, y - sy / 2, z), (x + sx / 2, y + sy / 2, z + sz)


def touching(a: Box, b: Box, tol: float = CONTACT_TOL) -> bool:
    return all(a[0][i] <= b[1][i] + tol and b[0][i] <= a[1][i] + tol for i in range(3))


def box_gap(a: Box, b: Box) -> float:
    """Shortest distance between two boxes; 0 when they touch or overlap."""
    return math.sqrt(sum(max(a[0][i] - b[1][i], b[0][i] - a[1][i], 0.0) ** 2 for i in range(3)))


def overlap_ratio(a: Box, b: Box) -> float:
    """Shared volume as a fraction of the smaller box."""
    inter = 1.0
    for i in range(3):
        d = min(a[1][i], b[1][i]) - max(a[0][i], b[0][i])
        if d <= 0:
            return 0.0
        inter *= d
    vol = lambda box: max((box[1][0] - box[0][0]) * (box[1][1] - box[0][1]) * (box[1][2] - box[0][2]), 1e-12)
    return inter / min(vol(a), vol(b))


def _separations(a: dict, b: dict) -> list[float]:
    """How far apart two planned parts are along each independent direction (negative: they
    overlap by that much). Boxes have three; a cylinder makes x/y one radial direction, so a
    shelf beside a round post is measured from the post's surface, not its bounding box."""
    ba, bb = part_box(a), part_box(b)
    dz = max(ba[0][2] - bb[1][2], bb[0][2] - ba[1][2])
    cyl_a, cyl_b = a.get("shape") == "cylinder", b.get("shape") == "cylinder"
    if not (cyl_a or cyl_b):
        return [max(ba[0][i] - bb[1][i], bb[0][i] - ba[1][i]) for i in range(2)] + [dz]
    if cyl_a and cyl_b:
        d = math.dist(a["at"][:2], b["at"][:2])
        return [d - a["size"][0] / 2 - b["size"][0] / 2, dz]
    cyl, box = (a, bb) if cyl_a else (b, ba)
    cx, cy = cyl["at"][:2]
    nx, ny = min(max(cx, box[0][0]), box[1][0]), min(max(cy, box[0][1]), box[1][1])
    if (nx, ny) == (cx, cy):  # the axis is inside the box's footprint
        inside = min(cx - box[0][0], box[1][0] - cx, cy - box[0][1], box[1][1] - cy)
        return [-(inside + cyl["size"][0] / 2), dz]
    return [math.dist((cx, cy), (nx, ny)) - cyl["size"][0] / 2, dz]


def part_gap(a: dict, b: dict) -> float:
    return math.sqrt(sum(max(s, 0.0) ** 2 for s in _separations(a, b)))


def edge_only(a: dict, b: dict, tol: float = CONTACT_TOL) -> bool:
    """Touching, but along a line or at a point rather than across a face: nothing can be
    fixed there, so a part held up that way is really floating."""
    seps = _separations(a, b)
    return part_gap(a, b) <= tol and sum(s > -tol for s in seps) >= 2


def _supports(part: dict) -> list[str]:
    value = part.get("rests_on") or []
    return [value] if isinstance(value, str) else list(value)


def _gap_text(gap: float) -> str:
    return f"{gap * 1000:.0f} mm" if gap < 1 else "more than 50 mm" if math.isinf(gap) else f"{gap:.2f} m"


def _structure(boxes: dict[str, Box], plan: dict, report: Report, built: bool, gap) -> set[str]:
    """Supports must touch, and every part must reach the ground through them. Returns the
    parts that do."""
    parts = {p["name"]: p for p in plan["parts"]}
    holds: dict[str, list[str]] = {}
    for name, part in parts.items():
        if name not in boxes:
            continue
        supports = _supports(part)
        if not supports:
            report.errors.append(f"{name}: nothing holds it up. Set rests_on to the parts it sits on, hangs "
                                 f"from or is fixed to, or \"{GROUND}\".")
            continue
        for s in supports:
            if s == GROUND:
                if abs(boxes[name][0][2]) > CONTACT_TOL:
                    where = "is" if built else "would be"
                    report.errors.append(f"{name}: rests on the ground but its bottom {where} at "
                                         f"{boxes[name][0][2]:.3f} m, not 0.")
                else:
                    holds.setdefault(name, []).append(GROUND)
            elif s not in parts:
                report.errors.append(f"{name}: rests_on {s!r}, which is not a part of the plan.")
            elif s not in boxes:
                continue
            elif (g := gap(name, s)) > CONTACT_TOL:
                report.errors.append(f"{name}: rests on {s} but does not touch it (gap {_gap_text(g)}). "
                                     "Move it onto its support, or add the bracket, hinge or fixing that "
                                     "joins them as a part.")
            elif not built and edge_only(part, parts[s]):
                report.errors.append(f"{name}: meets {s} only along an edge or at a corner, which holds "
                                     "nothing. Overlap them across a face, or add the part that joins them.")
            else:
                holds.setdefault(name, []).append(s)
    grounded: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, supports in holds.items():
            if name not in grounded and any(s == GROUND or s in grounded for s in supports):
                grounded.add(name)
                changed = True
    if not any(GROUND in s for s in holds.values()) and holds:
        report.errors.append(f"No part rests on the ground. The parts the subject stands on need rests_on \"{GROUND}\".")
    for name in parts:
        if name in holds and name not in grounded:
            report.errors.append(f"{name}: its supports never reach the ground - the chain of rests_on floats.")
    return grounded


def _near_misses(names: list[str], gap, report: Report) -> None:
    """Parts that come within a few centimetres of each other without touching."""
    found = sorted((g, a, b) for i, a in enumerate(names) for b in names[i + 1:]
                   if CONTACT_TOL < (g := gap(a, b)) <= NEAR_MISS)
    for g, a, b in found[:MAX_LISTED]:
        report.warnings.append(f"{a} and {b} are {_gap_text(g)} apart. Meant to meet? Close the gap. A real "
                               "clearance (a drawer or door gap) is a few mm and the same all round.")
    if len(found) > MAX_LISTED:
        report.warnings.append(f"... and {len(found) - MAX_LISTED} more pairs that almost touch.")


def _not_flush(boxes: dict[str, Box], touching_pairs, report: Report) -> None:
    """Touching parts whose outer faces are a few mm off flush."""
    axes = "xyz"
    found = []
    for a, b in touching_pairs:
        A, B = boxes[a], boxes[b]
        for i in range(3):
            for side, label in ((0, "min"), (1, "max")):
                d = abs(A[side][i] - B[side][i])
                if FLUSH_MIN < d < FLUSH_MAX:
                    found.append(f"{a} and {b}: their {label} {axes[i]} faces are {d * 1000:.1f} mm off "
                                 "flush. Line them up exactly, or make the step deliberate (10 mm or more).")
    report.warnings.extend(found[:MAX_LISTED])
    if len(found) > MAX_LISTED:
        report.warnings.append(f"... and {len(found) - MAX_LISTED} more faces almost flush.")


def _overlaps(boxes: dict[str, Box], plan: dict, report: Report) -> None:
    related = {(p["name"], s) for p in plan["parts"] for s in _supports(p)}
    names = [n for n in boxes]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            r = overlap_ratio(boxes[a], boxes[b])
            if r > 0.2 and (a, b) not in related and (b, a) not in related:
                report.warnings.append(f"{a} and {b} share {r:.0%} of the smaller one's volume. Intended "
                                       "(one inside the other)? Otherwise move or resize one.")


def _form(name: str, part: dict, size, report: Report) -> None:
    """A box or cylinder part's rounding and taper, if it has them, must fit the part."""
    radius, bottom_radius = part.get("radius"), part.get("bottom_radius")
    if radius is not None and (not isinstance(radius, (int, float)) or radius <= 0
                               or radius > min(size[0], size[1]) / 2):
        report.errors.append(f"{name}: radius must be positive and at most half the part's width and depth.")
    if bottom_radius is not None and (not isinstance(bottom_radius, (int, float)) or bottom_radius < 0):
        report.errors.append(f"{name}: bottom_radius must be 0 (square bottom edges) or positive.")
    for end in ("top", "bottom"):
        value = part.get(end)
        if value is not None and (not isinstance(value, (list, tuple)) or len(value) != 2
                                  or any(not isinstance(v, (int, float)) or v <= 0 for v in value)
                                  or value[0] > size[0] + 1e-9 or value[1] > size[1] + 1e-9):
            report.errors.append(f"{name}: {end} must be [width, depth] at that end (a cylinder's [diameter, "
                                 "diameter]), positive and no larger than size, which is the part at its widest.")


def _primitives(plan: dict) -> list[str]:
    """Box and cylinder parts that will be built as bare primitives without saying the real
    thing is one."""
    return [p.get("name", "?") for p in plan["parts"] if p.get("shape", "box") in ("box", "cylinder")
            and not (p.get("radius") or p.get("top") or p.get("bottom") or p.get("plain"))]


def _features(plan: dict, report: Report) -> None:
    features = plan.get("features")
    if (not isinstance(features, list) or len(features) < MIN_FEATURES
            or not all(isinstance(f, str) and f.strip() for f in features)):
        report.errors.append(
            f"features must list at least {MIN_FEATURES} details that make this the real thing and not "
            "something like it, each concrete and measurable: what someone who knows it would look for "
            "first (\"rear legs splay back 6 degrees\", \"seat pan dished 15 mm\", \"19 mm steel tube bent "
            "at R40, no welds showing\"). Name the specific kind, not the category.")


# ------------------------------------------------------------------ moving parts
#
# A part with "moves" turns on a hinge or slides along an axis in the game: a door, a lid, a
# drawer, a window sash. Everything that rests on it moves with it. The model is built at its
# rest pose (range includes 0), and nothing it carries may run into the rest of the subject
# anywhere across its range.

def _axis(value) -> tuple[float, float, float] | None:
    if isinstance(value, str):
        sign, base = (-1.0 if value.startswith("-") else 1.0), AXES.get(value.lower().lstrip("+-"))
        return tuple(sign * c for c in base) if base else None
    if isinstance(value, (list, tuple)) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value):
        n = math.sqrt(sum(v * v for v in value))
        return tuple(v / n for v in value) if n > 1e-9 else None
    return None


def moving_groups(plan: dict) -> dict[str, list[str]]:
    """Each moving part and the parts it carries (whatever rests on it, directly or not)."""
    parts = plan["parts"]
    groups = {}
    for p in parts:
        if not p.get("moves"):
            continue
        group = [p["name"]]
        changed = True
        while changed:
            changed = False
            for q in parts:
                if q["name"] not in group and any(s in group for s in _supports(q)):
                    group.append(q["name"])
                    changed = True
        groups[p["name"]] = group
    return groups


def _check_moves(name: str, part: dict, report: Report) -> None:
    mv = part["moves"]
    if not isinstance(mv, dict) or mv.get("type") not in MOVES:
        report.errors.append(f"{name}: moves must be {{\"type\": \"hinge\" or \"slide\", \"axis\", \"range\", "
                             "and for a hinge \"pivot\"}.")
        return
    if _axis(mv.get("axis")) is None:
        report.errors.append(f"{name}: moves.axis must be \"x\", \"y\", \"z\" (or \"-z\"...) or a direction [x, y, z].")
    rng = mv.get("range")
    unit = "degrees" if mv["type"] == "hinge" else "metres"
    if (not isinstance(rng, (list, tuple)) or len(rng) != 2 or any(not isinstance(v, (int, float)) for v in rng)
            or not rng[0] <= 0 <= rng[1] or rng[0] == rng[1]):
        report.errors.append(f"{name}: moves.range must be [from, to] in {unit} around the rest pose the "
                             "model is built in, so it includes 0: [0, 100] for a door that opens 100 degrees.")
    if mv["type"] == "hinge":
        pivot = mv.get("pivot")
        if not isinstance(pivot, (list, tuple)) or len(pivot) != 3:
            report.errors.append(f"{name}: a hinge needs moves.pivot [x, y, z], a point on its turning axis "
                                 "(the hinge knuckles), in the plan's coordinates.")
        elif box_gap(part_box(part), (tuple(pivot), tuple(pivot))) > PIVOT_REACH:
            report.errors.append(f"{name}: its hinge pivot is {_gap_text(box_gap(part_box(part), (tuple(pivot), tuple(pivot))))} "
                                 "from the part. A hinge sits on the part's edge, where its knuckles are.")


def pose(mv: dict, t: float, pivot=None):
    """The transform of a moving part at t (degrees or metres along its range), as a function
    on points, and the same on directions."""
    axis = _axis(mv["axis"])
    if mv["type"] == "slide":
        d = tuple(a * t for a in axis)
        return (lambda p: tuple(p[i] + d[i] for i in range(3))), (lambda v: tuple(v))
    c = tuple(pivot if pivot is not None else mv["pivot"])
    th = math.radians(t)
    cos, sin = math.cos(th), math.sin(th)
    k = axis

    def rot(v):
        kv = sum(k[i] * v[i] for i in range(3))
        cross = (k[1] * v[2] - k[2] * v[1], k[2] * v[0] - k[0] * v[2], k[0] * v[1] - k[1] * v[0])
        return tuple(v[i] * cos + cross[i] * sin + k[i] * kv * (1 - cos) for i in range(3))

    return (lambda p: tuple(r + c[i] for i, r in enumerate(rot(tuple(p[j] - c[j] for j in range(3)))))), rot


def _obb(box: Box, point=None, direction=None):
    centre = tuple((box[0][i] + box[1][i]) / 2 for i in range(3))
    half = tuple((box[1][i] - box[0][i]) / 2 for i in range(3))
    axes = [AXES[a] for a in "xyz"]
    if point:
        centre, axes = point(centre), [direction(a) for a in axes]
    return centre, axes, half


def _obbs_overlap(a, b, tol: float = CONTACT_TOL) -> bool:
    """Separating-axis test between two oriented boxes; overlaps shallower than tol don't count,
    so parts that only touch (a door against its stop, a drawer on its runner) are clear."""
    (ca, aa, ha), (cb, ab, hb) = a, b
    t = tuple(cb[i] - ca[i] for i in range(3))
    dot = lambda u, v: sum(u[i] * v[i] for i in range(3))
    cross = lambda u, v: (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    candidates = aa + ab + [cross(u, v) for u in aa for v in ab]
    for axis in candidates:
        n = math.sqrt(dot(axis, axis))
        if n < 1e-9:
            continue
        axis = tuple(c / n for c in axis)
        ra = sum(ha[i] * abs(dot(aa[i], axis)) for i in range(3))
        rb = sum(hb[i] * abs(dot(ab[i], axis)) for i in range(3))
        if abs(dot(t, axis)) > ra + rb - tol:
            return False
    return True


def _sweep(plan: dict, boxes: dict[str, Box], report: Report) -> None:
    """Move each moving part through its range and report what its group runs into."""
    by_name = {p["name"]: p for p in plan["parts"]}
    for mover, group in moving_groups(plan).items():
        mv = by_name[mover]["moves"]
        others = [n for n in boxes if n not in group]
        at_rest = {(g, o) for g in group for o in others if _obbs_overlap(_obb(boxes[g]), _obb(boxes[o]))}
        lo, hi = mv["range"]
        amount = (lambda t: f"{t:.0f} degrees") if mv["type"] == "hinge" else (lambda t: f"{t * 1000:.0f} mm")
        hits: dict[tuple[str, str], float] = {}
        ground: dict[str, float] = {}
        for k in range(1, MOTION_STEPS + 1):
            for t in (lo * k / MOTION_STEPS, hi * k / MOTION_STEPS):
                if t == 0:
                    continue
                point, direction = pose(mv, t)
                for g in group:
                    moved = _obb(boxes[g], point, direction)
                    centre, axes, half = moved
                    bottom = centre[2] - sum(half[i] * abs(axes[i][2]) for i in range(3))
                    if bottom < -CONTACT_TOL and g not in ground:
                        ground[g] = t
                    for o in others:
                        if (g, o) not in at_rest and (g, o) not in hits and _obbs_overlap(moved, _obb(boxes[o])):
                            hits[(g, o)] = t
        for (g, o), t in sorted(hits.items(), key=lambda x: abs(x[1]))[:MAX_LISTED]:
            who = g if g == mover else f"{g} (carried by {mover})"
            report.errors.append(f"{who} runs into {o} at {amount(t)} of its {mv['type']}. Move the pivot to where "
                                 "the real hinge or runner is, give it the clearance the real one has, or "
                                 "shorten the range.")
        for g, t in sorted(ground.items()):
            report.errors.append(f"{g} goes through the ground at {amount(t)} of {mover}'s {mv['type']}.")


def _verify_motion(plan: dict, motion: list, strip, touch: dict, planned: dict, report: Report) -> None:
    """A moving part must turn about its hinge, carry everything fixed to it, and clear the
    rest of the subject across its whole range - with its real meshes, as the game will move it."""
    groups = moving_groups(plan)
    for m in motion:
        mover = m["part"]
        mv = planned[mover]["moves"]
        amount = (lambda t: f"{t:.0f} degrees") if mv["type"] == "hinge" else (lambda t: f"{t * 1000:.0f} mm")
        if mv["type"] == "hinge" and mv.get("pivot"):
            # Any point on the hinge axis will do; only the distance off the axis matters.
            axis = _axis(mv["axis"])
            d = [m["origin"][i] - mv["pivot"][i] for i in range(3)]
            off = math.sqrt(max(0.0, sum(c * c for c in d) - sum(d[i] * axis[i] for i in range(3)) ** 2))
            if off > CONTACT_TOL:
                report.errors.append(f"{mover}: its origin is {_gap_text(off)} off its hinge axis, and a game "
                                     "engine turns it about its origin. roxy.set_pivot(obj, pivot) moves the "
                                     "origin without moving the mesh.")
        carried = {strip(c) for c in m["carries"]}
        loose = [p for p in groups.get(mover, [])[1:] if p not in carried]
        loose += sorted(n for n in touch if n not in planned and n not in carried
                        and touch[n] and touch[n] <= set(groups.get(mover, [])) | carried)
        for p in loose:
            report.errors.append(f"{p} is fixed to {mover} but not parented to it, so it stays behind when "
                                 f"{mover} moves. roxy.carry({mover}, {p}).")
        for g, o, t in sorted(m["hits"], key=lambda h: abs(h[2]))[:MAX_LISTED]:
            g, o = strip(g), strip(o)
            who = g if g == mover else f"{g} (carried by {mover})"
            report.errors.append(f"{who} runs into {o} at {amount(t)} of its {mv['type']}. Move the pivot to "
                                 "where the real hinge or runner is, give it the clearance the real one has, "
                                 "or shorten the range.")
        for g, t in m["ground"]:
            report.errors.append(f"{strip(g)} goes through the ground at {amount(t)} of {mover}'s {mv['type']}.")
        if not m["hits"] and not m["ground"]:
            report.notes.append(f"{mover} moves through its whole range {mv['range']} without hitting anything.")


def _stacked(boxes: dict[str, Box], exempt: set, report: Report) -> None:
    """Thin plates laid on another part's face, inside its outline."""
    found = []
    for a, A in boxes.items():
        if a in exempt:
            continue
        dims = [A[1][i] - A[0][i] for i in range(3)]
        t = min(range(3), key=lambda i: dims[i])
        others = sorted(dims[i] for i in range(3) if i != t)
        if dims[t] > THIN or dims[t] > 0.2 * others[0]:
            continue
        for b, B in boxes.items():
            if b == a:
                continue
            against = abs(A[0][t] - B[1][t]) <= CONTACT_TOL or abs(A[1][t] - B[0][t]) <= CONTACT_TOL
            inside = all(B[0][i] <= A[0][i] + CONTACT_TOL and A[1][i] <= B[1][i] + CONTACT_TOL
                         for i in range(3) if i != t)
            if against and inside:
                found.append((a, b))
                break
    for a, b in found[:MAX_LISTED]:
        report.warnings.append(
            f"{a} is a thin plate laid on {b}'s face. If it is part of the same piece - a frame, a panel, a lip, "
            f"a step - shape it into {b} instead of stacking: roxy.inset (a frame round a recessed or raised "
            "field), roxy.extrude (a lip, plinth or boss grown from the face), roxy.cut (a recess or slot). "
            "A real applied piece (a veneer, a badge, a decal) can stay.")


def _repeats(boxes: dict[str, Box], report: Report) -> None:
    """Identical parts placed one by one: a row of slats, posts or tiles is one Geometry Nodes
    part whose count and spacing stay editable."""
    same: dict[tuple, list[str]] = {}
    for name, (lo, hi) in boxes.items():
        same.setdefault(tuple(round((hi[i] - lo[i]) * 1000) for i in range(3)), []).append(name)
    for names in same.values():
        if len(names) >= REPEATS:
            listed = ", ".join(sorted(names)[:6]) + (" ..." if len(names) > 6 else "")
            report.warnings.append(
                f"{len(names)} identical parts placed one by one ({listed}). A row or grid of the same "
                "piece is one part made with Geometry Nodes - roxy.repeat(source, count, step), or "
                "roxy.instances_along_curve along a path - so the count and spacing stay editable, with "
                "jitter where the real ones vary.")


def check(plan: dict) -> Report:
    """Check a plan's structure before anything is built."""
    report = Report()
    if not isinstance(plan, dict):
        report.errors.append("The plan must be an object with name, purpose, size and parts.")
        return report
    _features(plan, report)
    for key in ("name", "purpose", "size", "parts"):
        if not plan.get(key):
            report.errors.append(f"Missing {key!r}.")
    if report.errors:
        return report
    size = plan["size"]
    if len(size) != 3 or any(not isinstance(v, (int, float)) or v <= 0 for v in size):
        report.errors.append("size must be [width, depth, height] in metres, all positive.")
        return report

    boxes: dict[str, Box] = {}
    for i, part in enumerate(plan["parts"]):
        name = part.get("name") or f"#{i}"
        if not part.get("name"):
            report.errors.append(f"Part {name} has no name.")
        elif name in boxes:
            report.errors.append(f"Two parts are called {name}; names must be unique.")
        shape = part.get("shape", "box")
        if shape not in SHAPES:
            report.errors.append(f"{name}: shape must be one of {', '.join(SHAPES)}.")
        if shape == "custom" and not part.get("how"):
            report.warnings.append(f"{name}: custom shape without 'how' - say which roxy helper or technique "
                                   "will make it.")
        psize, at = part.get("size"), part.get("at")
        if not psize or len(psize) != 3 or any(not isinstance(v, (int, float)) or v <= 0 for v in psize):
            report.errors.append(f"{name}: size must be [x, y, z] in metres, all positive.")
            continue
        if not at or len(at) != 3:
            report.errors.append(f"{name}: at must be [x, y, z], the bottom centre of the part.")
            continue
        if shape == "cylinder" and abs(psize[0] - psize[1]) > 1e-6:
            report.warnings.append(f"{name}: a cylinder's size is [diameter, diameter, height]; x and y differ.")
        if shape in ("box", "cylinder"):
            _form(name, part, psize, report)
        if part.get("moves") is not None:
            _check_moves(name, part, report)
        boxes[name] = part_box(part)

    bare = _primitives(plan)
    if bare:
        listed = ", ".join(bare[:MAX_LISTED]) + (" ..." if len(bare) > MAX_LISTED else "")
        report.warnings.append(
            f"Bare primitives: {listed}. A subject built from plain boxes and cylinders is only something "
            "like the real thing. Give each part its real form: \"radius\" for its edge radius (moulded, "
            "cast, turned, upholstered, worn), \"top\" or \"bottom\" where an end narrows (legs tapering to "
            "the foot, plinths, casings with draft), or shape custom (roxy.loft, lathe, extrude_profile, "
            "sweep) for anything with a profile. Mark \"plain\": true only where the real thing is exactly "
            "that shape: a plain board, slab, wall, rod or tube.")
    if report.errors:
        return report

    by_name = {p["name"]: p for p in plan["parts"]}
    gap = lambda a, b: part_gap(by_name[a], by_name[b])
    _structure(boxes, plan, report, built=False, gap=gap)
    _overlaps(boxes, plan, report)
    _near_misses(list(boxes), gap, report)
    _sweep(plan, boxes, report)
    _stacked(boxes, {p["name"] for p in plan["parts"] if p.get("plain")}, report)
    _repeats(boxes, report)

    lo = [min(b[0][i] for b in boxes.values()) for i in range(3)]
    hi = [max(b[1][i] for b in boxes.values()) for i in range(3)]
    span = [hi[i] - lo[i] for i in range(3)]
    for i, axis in enumerate("xyz"):
        if abs(span[i] - size[i]) > max(0.01, 0.02 * size[i]):
            report.warnings.append(f"The parts span {span[i]:.3f} m in {axis} but size says {size[i]:.3f} m.")
    if abs((lo[0] + hi[0]) / 2) > 0.01 or abs((lo[1] + hi[1]) / 2) > 0.01:
        report.warnings.append("The parts are not centred on the origin in x/y; the origin should be the "
                               "bottom centre of the whole subject.")
    custom = [p["name"] for p in plan["parts"] if p.get("shape") == "custom"]
    report.notes.append(f"{len(boxes)} parts, spanning {span[0]:.3f} x {span[1]:.3f} x {span[2]:.3f} m.")
    for mover, group in moving_groups(plan).items():
        mv = by_name[mover]["moves"]
        report.notes.append(f"{mover} {'turns' if mv['type'] == 'hinge' else 'slides'} through {mv['range']} "
                            f"{'degrees' if mv['type'] == 'hinge' else 'metres'}, carrying {', '.join(group)}.")
    if custom:
        report.notes.append(f"Built by you after build: {', '.join(custom)} (name each <Name>_<Part>, "
                            "parent=the assembly, location=its 'at').")
    return report


def verify(plan: dict, actual: dict[str, Box], gaps: list | None = None,
           primitives: list | None = None, motion: list | None = None,
           materials: dict | None = None) -> Report:
    """Compare what was built (boxes in the assembly's own space) against its plan.

    gaps are [part, part, metres] between the real surfaces of the pairs that come close;
    without them (an older server script) the boxes stand in for the surfaces. Detail added
    after the plan is checked too: everything must be fixed to something that is held up.
    primitives are [part, kind] for the parts whose mesh is still a stand-in shape (box,
    prism, cone, sphere). motion is what Blender found moving each moving part through its
    range: its origin, what is parented under it, and what it ran into. materials maps each
    material on the parts to how it was aged (roxy.weather), or None.
    """
    report = Report()
    prefix = plan["name"] + "_"
    strip = lambda full: full[len(prefix):] if full.startswith(prefix) else full
    boxes: dict[str, Box] = {}
    for full, box in actual.items():
        boxes[strip(full)] = (tuple(box[0]), tuple(box[1]))
    measured: dict[frozenset, float] | None = None
    if gaps is not None:
        measured = {frozenset((strip(a), strip(b))): float(g) for a, b, g in gaps}

    def gap(a: str, b: str) -> float:
        if measured is None:
            return box_gap(boxes[a], boxes[b])
        return measured.get(frozenset((a, b)), math.inf)

    planned = {p["name"]: p for p in plan["parts"]}
    for name, part in planned.items():
        if name not in boxes:
            report.errors.append(f"{name}: missing - no object {prefix}{name} under {plan['name']}.")
            continue
        want, got = part_box(part), boxes[name]
        size_w = [want[1][i] - want[0][i] for i in range(3)]
        size_g = [got[1][i] - got[0][i] for i in range(3)]
        for i, axis in enumerate("xyz"):
            tol = max(0.005, 0.03 * size_w[i])
            if abs(size_g[i] - size_w[i]) > tol:
                report.errors.append(f"{name}: {axis} size is {size_g[i]:.3f} m, plan says {size_w[i]:.3f} m.")
        centre_w = [(want[0][i] + want[1][i]) / 2 for i in range(2)] + [want[0][2]]
        centre_g = [(got[0][i] + got[1][i]) / 2 for i in range(2)] + [got[0][2]]
        moved = max(abs(centre_g[i] - centre_w[i]) for i in range(3))
        if moved > max(0.005, 0.03 * max(size_w)):
            report.errors.append(f"{name}: sits {moved * 1000:.0f} mm from where the plan puts it.")
    extra = sorted(n for n in boxes if n not in planned)
    if extra:
        report.notes.append(f"Not in the plan (detail you added): {', '.join(extra)}.")
    held = _structure({n: b for n, b in boxes.items() if n in planned}, plan, report, built=True, gap=gap)
    _overlaps({n: b for n, b in boxes.items() if n in planned}, plan, report)

    # Detail is held up by whatever it touches; it floats unless that leads to the structure.
    names = list(boxes)
    touch = {n: set() for n in names}
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if gap(a, b) <= CONTACT_TOL:
                touch[a].add(b)
                touch[b].add(a)
                pairs.append((a, b))
    reached, todo = set(held), list(held)
    while todo:
        for n in touch[todo.pop()]:
            if n not in reached and n not in planned:
                reached.add(n)
                todo.append(n)
    if held or not planned:
        for n in extra:
            if n in reached:
                continue
            if not touch[n]:
                near = min((gap(n, o) for o in names if o != n), default=math.inf)
                report.errors.append(f"{n}: touches nothing - it floats ({_gap_text(near)} from the nearest "
                                     "part). Fix it to what holds it: sink a bolt into its plate, sit a lid "
                                     "on its rim or hinge, add the bracket a shelf hangs from.")
            else:
                report.errors.append(f"{n}: touches only {', '.join(sorted(touch[n]))}, which "
                                     "never connect to the structure - the group floats.")
    _near_misses(names, gap, report)
    # A moving part's gap to what surrounds it is its clearance, not a careless step.
    moving = {n for group in moving_groups(plan).values() for n in group}
    _not_flush(boxes, [(a, b) for a, b in pairs if (a in moving) == (b in moving)], report)
    plain = {n for n, p in planned.items() if p.get("plain")}
    left = sorted((strip(n), kind) for n, kind in primitives or [] if strip(n) in boxes and strip(n) not in plain)
    if left:
        listed = ", ".join(f"{n} ({kind})" for n, kind in left[:MAX_LISTED]) + (" ..." if len(left) > MAX_LISTED else "")
        report.warnings.append(
            f"{len(left)} of {len(boxes)} parts are still bare primitives: {listed}. A stand-in shape makes "
            "the subject only something like the real thing. Rebuild each in its real form "
            "(roxy.rounded_box, rounded_cylinder, loft, lathe, extrude_profile, sweep; roxy.fuse where it "
            "is one piece), or mark it \"plain\": true in the plan if the real thing is exactly that shape.")
    _verify_motion(plan, motion or [], strip, touch, planned, report)
    _stacked(boxes, plain, report)
    _repeats(boxes, report)
    fresh = sorted(m for m, aged in (materials or {}).items() if not aged)
    if fresh:
        report.warnings.append(
            f"Factory-fresh materials: {', '.join(fresh[:MAX_LISTED])}{' ...' if len(fresh) > MAX_LISTED else ''}. "
            "Nothing in use looks new: roxy.weather(obj) adds uneven colour, dirt in corners and near the floor, "
            "scuffed edges and dust over the existing material and textures (age \"used\" by default; "
            "\"new\" only when new is the point, like a showroom).")
    if plan.get("features"):
        report.notes.append("Confirm each identifying feature close up with look, and fix any that doesn't "
                            "read: " + "; ".join(plan["features"]) + ".")
    return report
