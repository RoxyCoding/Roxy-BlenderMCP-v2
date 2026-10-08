"""Plans for multi-part models: the structure written down, checked, then verified.

A plan is the model's understanding of a subject as data - what it is, its
overall size, and every part with its size, position and what holds it up -
so a structure that can't stand (a floating part, a part outside the whole, two
parts in one place) is caught before any geometry exists, and the built result
can be compared against it afterwards.

Coordinates are metres relative to the assembly's origin, which sits at the
bottom centre of the whole subject. A part's `at` is the bottom centre of its
axis-aligned box, like the roxy helpers' origins.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Two parts closer than this touch. Generous enough for bevels and float noise.
CONTACT_TOL = 0.005
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


def touching(a: Box, b: Box, tol: float = CONTACT_TOL) -> bool:
    return all(a[0][i] <= b[1][i] + tol and b[0][i] <= a[1][i] + tol for i in range(3))


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


def _supports(part: dict) -> list[str]:
    value = part.get("rests_on") or []
    return [value] if isinstance(value, str) else list(value)


def _structure(boxes: dict[str, Box], plan: dict, report: Report, built: bool) -> None:
    """Supports must touch, and every part must reach the ground through them."""
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
            elif s in boxes and not touching(boxes[name], boxes[s]):
                gap = max(max(boxes[s][0][i] - boxes[name][1][i], boxes[name][0][i] - boxes[s][1][i]) for i in range(3))
                report.errors.append(f"{name}: rests on {s} but does not touch it (gap {gap * 1000:.0f} mm).")
            elif s in boxes:
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

    _structure(boxes, plan, report, built=False)
    _overlaps(boxes, plan, report)

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


def verify(plan: dict, actual: dict[str, Box]) -> Report:
    """Compare what was built (boxes in the assembly's own space) against its plan."""
    report = Report()
    prefix = plan["name"] + "_"
    boxes: dict[str, Box] = {}
    for full, box in actual.items():
        part = full[len(prefix):] if full.startswith(prefix) else full
        boxes[part] = (tuple(box[0]), tuple(box[1]))
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
    extra = [n for n in boxes if n not in planned]
    if extra:
        report.notes.append(f"Not in the plan (detail you added?): {', '.join(sorted(extra))}.")
    _structure({n: b for n, b in boxes.items() if n in planned}, plan, report, built=True)
    _overlaps({n: b for n, b in boxes.items() if n in planned}, plan, report)
    return report
