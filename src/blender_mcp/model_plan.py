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

# Every tolerance scales with the parts it compares, capped at the value that
# suits furniture: a 1 mm gap is a tight fit between a shelf and its post but a
# visible hole between a 5 mm jump ring and the pin it hangs from. The scale of
# a pair is the longest side of the smaller part.

# Two parts closer than this touch. Generous enough for bevels and float noise
# (surfaces are measured to 0.1 mm).
CONTACT_TOL, CONTACT_REL, CONTACT_MIN = 0.005, 0.02, 0.0002
# Parts closer than this without touching almost certainly were meant to meet:
# a shelf 1 cm from its post, a bolt hovering over its plate.
NEAR_MISS, NEAR_REL = 0.03, 0.5
# Faces of two touching parts this close to flush, but not flush, read as a
# careless step: a side panel standing 3 mm proud of the post it is fixed to.
FLUSH_MIN, FLUSH_MAX, FLUSH_REL = 0.001, 0.006, 0.05
# Parts that pass further than this into each other are not joined, they are
# overlapped: a pin butted into the side of a ring, a cap stacked into a gem, a
# trim line sunk into the panel it should sit on or in a groove cut for it.
# Scaled by the thinner part's thinnest side: 0.3 mm is nothing in a plank and
# half of a 0.7 mm wire.
PENETRATION_TOL, PENETRATION_REL, PENETRATION_MIN = 0.0005, 0.1, 0.00005
MAX_LISTED = 12
SHAPES = ("box", "cylinder", "custom")
GROUND = "ground"


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


def _longest(box: Box) -> float:
    return max(box[1][i] - box[0][i] for i in range(3))


def _thinnest(box: Box) -> float:
    return min(box[1][i] - box[0][i] for i in range(3))


def pair_scale(*boxes: Box) -> float:
    """The size a pair's tolerances scale with: the longest side of the smaller part."""
    return min(_longest(b) for b in boxes)


def contact_tol(*boxes: Box) -> float:
    return min(CONTACT_TOL, max(CONTACT_MIN, CONTACT_REL * pair_scale(*boxes)))


def near_miss(*boxes: Box) -> float:
    return min(NEAR_MISS, NEAR_REL * pair_scale(*boxes))


def flush_band(*boxes: Box) -> tuple[float, float]:
    hi = min(FLUSH_MAX, FLUSH_REL * pair_scale(*boxes))
    return hi * FLUSH_MIN / FLUSH_MAX, hi


def penetration_tol(*boxes: Box) -> float:
    return min(PENETRATION_TOL, max(PENETRATION_MIN, PENETRATION_REL * min(_thinnest(b) for b in boxes)))


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
    if gap < 0.01:
        return f"{gap * 1000:.1f} mm"
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
                if abs(boxes[name][0][2]) > contact_tol(boxes[name]):
                    where = "is" if built else "would be"
                    report.errors.append(f"{name}: rests on the ground but its bottom {where} at "
                                         f"{boxes[name][0][2]:.3f} m, not 0.")
                else:
                    holds.setdefault(name, []).append(GROUND)
            elif s not in parts:
                report.errors.append(f"{name}: rests_on {s!r}, which is not a part of the plan.")
            elif s not in boxes:
                continue
            elif (g := gap(name, s)) > contact_tol(boxes[name], boxes[s]):
                report.errors.append(f"{name}: rests on {s} but does not touch it (gap {_gap_text(g)}). "
                                     "Move it onto its support, or add the bracket, hinge or fixing that "
                                     "joins them as a part.")
            elif not built and edge_only(part, parts[s], contact_tol(boxes[name], boxes[s])):
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


def _near_misses(boxes: dict[str, Box], gap, report: Report) -> None:
    """Parts that come close to each other, for their size, without touching."""
    names = list(boxes)
    found = sorted((g, a, b) for i, a in enumerate(names) for b in names[i + 1:]
                   if contact_tol(boxes[a], boxes[b]) < (g := gap(a, b)) <= near_miss(boxes[a], boxes[b]))
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
        lo, hi = flush_band(A, B)
        for i in range(3):
            for side, label in ((0, "min"), (1, "max")):
                d = abs(A[side][i] - B[side][i])
                if lo < d < hi:
                    found.append(f"{a} and {b}: their {label} {axes[i]} faces are {d * 1000:.1f} mm off "
                                 f"flush. Line them up exactly, or make the step deliberate "
                                 f"({_gap_text(hi * 10 / 6)} or more).")
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


def check(plan: dict) -> Report:
    """Check a plan's structure before anything is built."""
    report = Report()
    if not isinstance(plan, dict):
        report.errors.append("The plan must be an object with name, purpose, size and parts.")
        return report
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
        boxes[name] = part_box(part)
    if report.errors:
        return report

    by_name = {p["name"]: p for p in plan["parts"]}
    gap = lambda a, b: part_gap(by_name[a], by_name[b])
    _structure(boxes, plan, report, built=False, gap=gap)
    _overlaps(boxes, plan, report)
    _near_misses(boxes, gap, report)

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
    if custom:
        report.notes.append(f"Built by you after build: {', '.join(custom)} (name each <Name>_<Part>, "
                            "parent=the assembly, location=its 'at').")
    return report


def verify(plan: dict, actual: dict[str, Box], gaps: list | None = None) -> Report:
    """Compare what was built (boxes in the assembly's own space) against its plan.

    gaps are [part, part, metres] between the real surfaces of the pairs that come close,
    with a fourth value for pairs that overlap: how far one passes into the other;
    without them (an older server script) the boxes stand in for the surfaces. Detail added
    after the plan is checked too: everything must be fixed to something that is held up.
    """
    report = Report()
    prefix = plan["name"] + "_"
    strip = lambda full: full[len(prefix):] if full.startswith(prefix) else full
    boxes: dict[str, Box] = {}
    for full, box in actual.items():
        boxes[strip(full)] = (tuple(box[0]), tuple(box[1]))
    measured: dict[frozenset, float] | None = None
    depths: dict[tuple[str, str], float] = {}
    if gaps is not None:
        measured = {}
        for a, b, g, *rest in gaps:
            measured[frozenset((strip(a), strip(b)))] = float(g)
            if rest:
                depths[(strip(a), strip(b))] = float(rest[0])

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
            if gap(a, b) <= contact_tol(boxes[a], boxes[b]):
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
                                     "part). Fix it to what holds it: seat a bolt in a hole through its plate, sit a lid "
                                     "on its rim or hinge, add the bracket a shelf hangs from.")
            else:
                report.errors.append(f"{n}: touches only {', '.join(sorted(touch[n]))}, which "
                                     "never connect to the structure - the group floats.")
    _penetrations(depths, boxes, report)
    _near_misses(boxes, gap, report)
    _not_flush(boxes, pairs, report)
    return report


def _penetrations(depths: dict[tuple[str, str], float], boxes: dict[str, Box], report: Report) -> None:
    """Parts whose real surfaces pass through each other instead of being joined."""
    def tol(a, b):
        return penetration_tol(boxes[a], boxes[b]) if a in boxes and b in boxes else PENETRATION_TOL
    found = sorted(((d, a, b) for (a, b), d in depths.items() if d > tol(a, b)), reverse=True)
    for d, a, b in found[:MAX_LISTED]:
        report.errors.append(
            f"{a} and {b} pass {d * 1000:.1f} mm into each other. Overlapping two solids is not a joint, "
            "even where another part hides it. Join them the way the real thing is made: cut the hole, "
            "socket, groove or seat one sits in (roxy.cut), make them one piece (a pin and its eye are one "
            "bent wire: roxy.sweep), pass a ring through the other's opening with clearance, or rest one "
            "face on the other.")
    if len(found) > MAX_LISTED:
        report.errors.append(f"... and {len(found) - MAX_LISTED} more pairs pass into each other.")
