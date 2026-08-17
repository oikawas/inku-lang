"""Render engine 14: the wild toggle reaches past the straight line.

SPEC §13.4 puts `wild` on the whole work, but until engine 14 only
`synthesize_stroke` read it, so contours, arcs, fills and hatches were deaf to
it. These checks pin how far it reaches, which combinations are allowed to stay
identical, and that the material layer moves with the ink instead of staying
behind on the geometry.
"""

from __future__ import annotations

import math
import pathlib
import re
from xml.etree import ElementTree

from inku_server.plugins import canvas_size_for_aspect
from inku_server.renderer import (
    _material_outline_profile,
    _outline_wander_px,
    _stroke_width_px,
    render,
)
from inku_server.schema import Instruction, Score
from inku_server.stroke_engine import synthesize_along


def _plain_mark(weight: str) -> Instruction:
    """A line that names the tool and nothing else.

    `_material_outline_profile` takes the instruction since render engine 38:
    both widths it reads are asked of `_mark_width_px`, which is where a
    described mark is seen. This bound is about the tool, so the subject states
    no surface.
    """
    return Instruction(
        primitive="line", **{"from": (0.18, 0.50)}, to=(0.82, 0.50), weight=weight,
    )


RENDER_SEED = 12345
REFERENCE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "reference"

TOOLS = (
    "brush_thick", "brush_thin", "burin", "chalk", "computer", "crayon",
    "drypoint", "pen", "pencil", "rotring", "silverpoint",
)
PRIMITIVES = ("line", "circle", "ellipse", "triangle", "square", "polygon", "arc", "cloudform")
GEOMETRY: dict[str, dict] = {
    "line": {"from": [0.18, 0.50], "to": [0.82, 0.50]},
    "circle": {"center": [0.50, 0.50], "radius": 0.24},
    "ellipse": {"center": [0.50, 0.50], "size": [0.48, 0.30]},
    "triangle": {"position": [0.28, 0.28], "size": [0.44, 0.44]},
    "square": {"position": [0.28, 0.28], "size": [0.44, 0.44]},
    "polygon": {"center": [0.50, 0.50], "radius": 0.25, "sides": 7},
    "arc": {"center": [0.50, 0.50], "radius": 0.27, "angle_start": 15.0, "angle_end": 285.0},
    "cloudform": {"center": [0.50, 0.50], "size": [0.48, 0.32]},
}
BASE_SURFACE = {
    "texture": "hatch", "density": 0.55, "scale": 0.40, "opacity": 0.36,
    "bleed": 0.25, "direction": "diagonal_rising", "spacing_gradient": "none",
    "tone_steps": 3, "seed": 24680,
}

# The only combinations allowed to come out byte-identical with the toggle on.
# Every one of them has a reason that predates this engine, and none of them is
# a special case written into the synthesizer.
#
# Engine 15 put `cloudform` on the shared closed-contour path, so the nine hand
# tools now move with the toggle and the exemption shrank from 25 to 16: the two
# machine poles, across all eight shapes, and nothing else.
IDENTICAL_UNDER_WILD = (
    # rotring is the machine pole: ToolGrammar.gesture is 0.0 (engine 8).
    {("rotring", primitive) for primitive in PRIMITIVES}
    # the computer repeats without error, so `wild` does not touch it (engine 13).
    | {("computer", primitive) for primitive in PRIMITIVES}
)


def _svg(instruction: dict, *, wild: bool) -> str:
    score = Score.model_validate({"instructions": [instruction]})
    return render(score, render_seed=RENDER_SEED, svg_profile="editable", wild=wild)


def _moves(instruction: dict) -> bool:
    return _svg(instruction, wild=False) != _svg(instruction, wild=True)


def test_wild_reaches_every_tool_and_primitive_except_the_documented_16() -> None:
    identical = {
        (tool, primitive)
        for tool in TOOLS
        for primitive in PRIMITIVES
        if not _moves({"primitive": primitive, "weight": tool, **GEOMETRY[primitive]})
    }
    assert identical == IDENTICAL_UNDER_WILD
    assert len(identical) == 16


def test_wild_reaches_fills() -> None:
    for primitive in ("circle", "square", "polygon"):
        for tool in ("pencil", "crayon", "brush_thick"):
            instruction = {
                "primitive": primitive, "weight": tool, "filled": True,
                **GEOMETRY[primitive],
            }
            assert _moves(instruction), (primitive, tool)
    # rotring's fill degenerates to a region fill, so there is no stroke to move.
    assert not _moves(
        {"primitive": "square", "weight": "rotring", "filled": True, **GEOMETRY["square"]}
    )


def _surface_stroke_paths(instruction: dict, *, wild: bool) -> list[str]:
    """The `d` of each hatch stroke, not the whole document.

    The square's own contour moves under `wild`, so a document comparison says
    "changed" even when the hatch is still wired to the old path.
    """
    root = ElementTree.fromstring(_svg(instruction, wild=wild))
    return [
        node.attrib["d"]
        for node in root.iter()
        if "surface-stroke-v1" in (node.attrib.get("class") or "")
    ]


def test_wild_reaches_the_hatch_inside_a_surface() -> None:
    """⚠ 本数は engine 35 で 39 → 29・78 → 58 に減った。

    行を輪郭で切った版なので、**輪郭と交わらない行が 1 本も描かれなくなった**
    (10 本 / 20 本)。**寸法は変わっていない。減ったのは本数だけである。**
    この検査が測っているのは「wild が面の中のハッチまで届くこと」で、そちらは
    本数が変わっても同じ —— 描かれた全部が wild で別の `d` になる。
    """
    for texture, tool, expected in (("hatch", "pen", 29), ("crosshatch", "pencil", 58)):
        instruction = {
            "primitive": "square", "weight": tool, "filled": False,
            **GEOMETRY["square"], "surface": {**BASE_SURFACE, "texture": texture},
        }
        off = _surface_stroke_paths(instruction, wild=False)
        on = _surface_stroke_paths(instruction, wild=True)
        assert len(off) == len(on) == expected, (texture, tool, len(off), len(on))
        assert sum(1 for a, b in zip(off, on) if a != b) == expected


_GEOMETRY_ATTRS = ("d", "points", "cx", "cy", "r", "rx", "ry", "x", "y", "width", "height")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

# A stratum is drawn at its own offset from the centreline it rides, so the
# distance from the ink is that offset and nothing more. The bound is taken from
# the tool's own profile (3.50px for pencil, 11.20px for brush_thick) plus one
# pixel for the polyline discretisation. Left on the geometry the layers are far
# outside it; see the report for the measured separation.
LAYER_DISTANCE_SLACK_PX = 1.0


def _outline_layers(root) -> list[tuple[str, tuple]]:
    """The material strata as (tag, geometry) — the element type is part of it.

    Before engine 28 a circle kept its `<circle>` and a square its `<rect>`, and
    only a layer built from the performance became a polyline; now every layer
    is built from the performance, so the type is part of what turned over.
    The class carries a stratum token as well, so the match is on the token.
    """
    layers = []
    for node in root.iter():
        if "material-outline" not in (node.attrib.get("class") or "").split():
            continue
        geometry = tuple(
            (name, node.attrib[name]) for name in _GEOMETRY_ATTRS if name in node.attrib
        )
        layers.append((node.tag.rsplit("}", 1)[-1], geometry))
    return layers


def _points_of(value: str) -> list[tuple[float, float]]:
    numbers = [float(match) for match in _NUMBER.findall(value)]
    return list(zip(numbers[0::2], numbers[1::2]))


def _band_centerlines(root, *, closed: bool) -> list[list[tuple[float, float]]]:
    """The performed centreline, read back out of the drawn stroke band.

    The band is the two banks of the stroke: one subpath per bank when the
    contour is closed, one there-and-back subpath when it is open. Since render
    engine 19 an open stroke the ground refused is cut into runs, one
    there-and-back subpath each, so the centreline comes back in pieces. They
    are kept apart rather than joined: a straight chord across a gap is not
    somewhere the tool ever went.
    """
    candidates = [
        node.attrib["d"]
        for node in root.iter()
        if node.attrib.get("d")
        and node.attrib.get("class") is None
        and node.attrib.get("fill") not in (None, "none")
    ]
    band = max(candidates, key=len)
    subpaths = [part for part in band.split("M") if part.strip()]
    if closed:
        left, right = _points_of(subpaths[0]), _points_of(subpaths[1])
        return [[((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(left, right)]]
    runs: list[list[tuple[float, float]]] = []
    for subpath in subpaths:
        walk = _points_of(subpath)
        half = len(walk) // 2
        left, right = walk[:half], walk[::-1][:half]
        runs.append([((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(left, right)])
    return runs


def _distance_to_polyline(
    point: tuple[float, float], polyline: list[tuple[float, float]]
) -> tuple[float, str]:
    """Distance to the run, and where on it the nearest point landed.

    "before" / "after" mean the nearest point is a terminus the vertex has
    overshot; "inside" means there is ink directly beside it.
    """
    px, py = point
    best, landed = math.inf, "inside"
    final = len(polyline) - 2
    for index, ((ax, ay), (bx, by)) in enumerate(zip(polyline, polyline[1:])):
        dx, dy = bx - ax, by - ay
        span = dx * dx + dy * dy
        raw = 0.0 if span <= 1e-12 else ((px - ax) * dx + (py - ay) * dy) / span
        t = max(0.0, min(1.0, raw))
        distance = math.hypot(px - (ax + dx * t), py - (ay + dy * t))
        if distance < best:
            best = distance
            if index == 0 and raw < 0.0:
                landed = "before"
            elif index == final and raw > 1.0:
                landed = "after"
            else:
                landed = "inside"
    return best, landed


def _outline_distances_to_ink(instruction: dict, *, wild: bool) -> list[float]:
    """One distance per material-outline vertex that has ink beside it.

    Since render engine 19 the ground cuts an open stroke into runs, and the
    material outline still spans the bare paper between them (SPEC: the cut is
    made in the ink body, not in the texture strata). A vertex over a gap has
    no ink beside it, so it is left out rather than measured against the
    nearest run's terminus.
    """
    root = ElementTree.fromstring(_svg(instruction, wild=wild))
    closed = instruction["primitive"] != "arc"
    runs = _band_centerlines(root, closed=closed)
    if closed:
        # The reconstruction returns the ring as an open list, so the segment
        # that joins its last point back to its first is missing. A vertex
        # sitting over that seam is measured against a distant endpoint instead
        # of against the ink under it -- with the ~20px spacing of the run that
        # is a spurious 10px, which is larger than anything the layer's own
        # offset can produce. Close the ring before measuring.
        runs = [run + run[:1] for run in runs]
    distances: list[float] = []
    over_a_gap = 0
    for node in root.iter():
        if "material-outline" not in (node.attrib.get("class") or "").split():
            continue
        if "points" in node.attrib:
            vertices = _points_of(node.attrib["points"])
        elif "d" in node.attrib:
            vertices = _points_of(node.attrib["d"])
        elif "cx" in node.attrib:
            cx, cy, r = (float(node.attrib[name]) for name in ("cx", "cy", "r"))
            vertices = [
                (cx + r * math.cos(i * math.tau / 64), cy + r * math.sin(i * math.tau / 64))
                for i in range(64)
            ]
        else:
            x, y = float(node.attrib["x"]), float(node.attrib["y"])
            w, h = float(node.attrib["width"]), float(node.attrib["height"])
            vertices = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        for vertex in vertices:
            index, (distance, landed) = min(
                enumerate(_distance_to_polyline(vertex, run) for run in runs),
                key=lambda pair: pair[1][0],
            )
            # A loop has no cut ends, and neither has the start of the first
            # run nor the end of the last: those are where the stroke itself
            # begins and ends.
            if not closed and (
                (landed == "before" and index > 0)
                or (landed == "after" and index < len(runs) - 1)
            ):
                over_a_gap += 1
                continue
            distances.append(distance)
    # A reader that dropped most of the layer would pass wherever it was drawn.
    assert len(distances) > over_a_gap, (len(distances), over_a_gap)
    return distances


def _frozen_outline_layers(case_id: str) -> list[tuple[str, tuple]]:
    """The same layer as last frozen, found in the newest version that moved it."""
    versions = sorted(
        (int(path.name.rsplit("-", 1)[-1]), path)
        for path in REFERENCE_ROOT.glob("render-engine-*")
        if path.name.rsplit("-", 1)[-1].isdigit()
    )
    for _, directory in reversed(versions):
        candidate = directory / f"{case_id}.svg"
        if candidate.exists():
            return _outline_layers(
                ElementTree.fromstring(candidate.read_text(encoding="utf-8"))
            )
    raise AssertionError(f"no frozen SVG for {case_id}")


def test_material_outline_follows_the_ink_whether_or_not_wild_is_on() -> None:
    """engine 28: the layer is beside the ink in both states.

    Until engine 27 this test asserted the opposite half -- with wild off the
    layer was the frozen geometric one, attribute for attribute -- and that is
    worth keeping in view, because it means the old behaviour was not an
    oversight: it was held in place deliberately, for byte compatibility with
    the frozen corpora. The author's ruling (2026-08-09) is that the decoration
    takes its offset from the ink itself, so the wild gate is gone and the
    frozen comparison with it.
    """
    # The mark has to actually leave its geometry, or the two readings cannot be
    # told apart: on an unvaried shape the ink sits on the ideal line, so a layer
    # drawn from either one lands in the same place and the bound below is
    # satisfied by a renderer that never changed.
    wander = {
        "amplitude": "broad",
        "frequency": "medium",
        "quality": "wave",
        "dimensions": ["position_x", "position_y", "radius"],
    }
    for primitive in ("circle", "arc", "square"):
        for tool in ("pencil", "brush_thick", "crayon"):
            instruction = {
                "primitive": primitive,
                "weight": tool,
                "variation": wander,
                **GEOMETRY[primitive],
            }
            off = _outline_layers(ElementTree.fromstring(_svg(instruction, wild=False)))
            on = _outline_layers(ElementTree.fromstring(_svg(instruction, wild=True)))
            assert off and on, (primitive, tool)
            # Wild still moves the ink, so the layer that rides it moves too.
            assert off != on, (primitive, tool)
            # The layer is beside the ink in BOTH states, not only when wild.
            # This is the half that engine 28 turned over.
            # engine 28 gives each stratum a low-frequency drift off its own
            # offset, so the bound asks the renderer for it rather than
            # restating the formula: a test that hard-codes it stops tracking
            # the design the moment the design moves.
            canvas = canvas_size_for_aspect("square")
            # The slack carries the reconstruction, not the design: the band's
            # centreline is recovered from the drawn band at ~20px spacing and
            # with the envelope's own wobble, and that error grows with the
            # tool's width, so the tool's stroke is part of it.
            bound = (
                max(
                    abs(offset) + _outline_wander_px(offset, canvas)
                    for offset, _, _, _ in _material_outline_profile(_plain_mark(tool), canvas)
                )
                + _stroke_width_px(tool, canvas)
                + LAYER_DISTANCE_SLACK_PX
            )
            for wild in (False, True):
                assert max(_outline_distances_to_ink(instruction, wild=wild)) < bound, (
                    primitive,
                    tool,
                    wild,
                )


def _polygon_area(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for index, (x, y) in enumerate(points):
        nx, ny = points[(index + 1) % len(points)]
        total += x * ny - nx * y
    return abs(total) / 2


def _closed_centerlines() -> dict[str, tuple[list[tuple[float, float]], frozenset[int]]]:
    circle = [
        (500 + 240 * math.cos(i * math.tau / 240), 500 + 240 * math.sin(i * math.tau / 240))
        for i in range(240)
    ]
    corners = {
        "square": [(280.0, 280.0), (720.0, 280.0), (720.0, 720.0), (280.0, 720.0)],
        "polygon": [
            (
                500 + 250 * math.cos(math.radians(-90) + i * math.tau / 7),
                500 + 250 * math.sin(math.radians(-90) + i * math.tau / 7),
            )
            for i in range(7)
        ],
    }
    result: dict[str, tuple[list[tuple[float, float]], frozenset[int]]] = {
        "circle": (circle, frozenset())
    }
    for name, points in corners.items():
        contour: list[tuple[float, float]] = []
        anchors: list[int] = []
        for index, start in enumerate(points):
            end = points[(index + 1) % len(points)]
            anchors.append(len(contour))
            contour.extend(
                (start[0] + (end[0] - start[0]) * k / 40, start[1] + (end[1] - start[1]) * k / 40)
                for k in range(40)
            )
        result[name] = (contour, frozenset(anchors))
    return result


def test_the_performance_does_not_resize_the_figure() -> None:
    """How big a figure is belongs to the Score, not to the performance.

    The gesture is a wander around the intended path, so its mean is removed on
    a closed loop. Without that subtraction the whole loop inflates or shrinks.
    """
    for name, (contour, anchors) in _closed_centerlines().items():
        for tool in ("pencil", "brush_thick"):
            areas = [
                _polygon_area(
                    [
                        (sample.x, sample.y)
                        for sample in synthesize_along(
                            contour, 3.0, tool, RENDER_SEED,
                            closed=True, anchors=anchors, wild=wild,
                        ).samples
                    ]
                )
                for wild in (False, True)
            ]
            ratio = areas[1] / areas[0]
            assert 0.95 <= ratio <= 1.05, (name, tool, ratio)
