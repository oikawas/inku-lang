"""Generate the server-side reference corpus the Android port is verified against.

The Android renderer is being caught up from engine 12 to engine 14. Parity is
checked against fixtures produced here, so the expected values always come from
the server implementation rather than from the port's own behavior.

Run from `server/`:

    UV_CACHE_DIR=/tmp/inku-uv-cache uv run python scripts/gen_android_reference.py

Outputs land in `android/app/src/test/resources/server_reference/`:

- `stroke_engine_primitives.json`         tool grammars, `_unit`, `_smooth_noise`,
                                          `_event_map`, normals and arc-length parameters
- `stroke_engine_latent_energy.json`      latent_energy samples per seed
- `stroke_engine_synthesize_stroke.json`  per-sample state, outline and burr for six straight strokes
- `stroke_engine_synthesize_along.json`   per-sample state, both banks, burr and the path `d`
                                          for four strokes along a centerline
- `renderer_seed_range.json`              unsigned 64-bit seeds and `_seed_for_instruction`
- `renderer_fill_and_arc.json`            fill scanlines, hatch line geometry and arc centerlines
- `renderer_cloudform_and_relations.json` cloudform contours per tool grammar, minor-arc
                                          reconstruction, and region-before-relation resolution
- `ddl_expand.json`                       Stage 1.5 expansion: variation and plugin expansion
                                          and `variation_report`, with every argument written out
- `<name>.svg`                            full renders at the current engine version
- `svg_index.json`                        the Score, seed, byte size, element counts,
                                          and class attributes of each SVG

Element counts and class attributes are the comparison surface for the port: the
class strings carry the control-point and event counts (`contour-stroke-v1
controls-62 events-1`), the fill stroke count (`fill-stroke-v1 strokes-48`), and
the hatch spacing (`surface-stroke-v1 hatch-spacing-22.500`).
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import math
import pathlib
import re
from collections.abc import Iterator

from inku_server import arc_geometry as ag
from inku_server.ddl_expander import (
    FOCUS_IDS,
    VARIATION_AMPLITUDES,
    expand_intermediate_ddl,
)
from inku_server import cloudform as cf
from inku_server import renderer
from inku_server.color_catalogs import (
    DEFAULT_COLOR_CATALOG_ID,
    color_catalog_ids,
    render_color_map_for_catalog,
)
from inku_server import stroke_engine as se
from inku_server.layer_versions import DDL_ENGINE_VERSION
from inku_server.render_engines import current_render_engine
from inku_server.schema import Instruction, Score, Variation

OUT = pathlib.Path(__file__).resolve().parents[2] / "android/app/src/test/resources/server_reference"

# Fixtures no engine version governs. They are rebaked in place and the port
# follows them, the way it always did -- `score_schema_contract.json` moved once,
# in `4eef595c`, and that frequency is why versioning them would buy nothing.
FLAT_FIXTURES = frozenset({
    "coerce_governors.json",
    "count_preservation.json",
    "lineage_wiring.json",
    "prompts.json",
    "score_schema_contract.json",
})

# The one fixture the DDL engine governs; everything else answers to the renderer.
DDL_ENGINE_FIXTURE = "ddl_expand.json"

MANIFEST_NAME = "manifest.json"


def render_engine_dir() -> pathlib.Path:
    return OUT / f"render-engine-{current_render_engine().version}"


def ddl_engine_dir() -> pathlib.Path:
    return OUT / f"ddl-engine-{DDL_ENGINE_VERSION}"


def out_path(name: str) -> pathlib.Path:
    """The file a fixture is written to: the directory of the version governing it.

    Only the current version of each axis is ever written. Older ones are held by
    their `manifest.json` instead of being rebaked -- the same rule
    `server/reference/` follows, and the reason raising the engine now adds a
    directory rather than rewriting expectations the port still holds.
    """
    if name in FLAT_FIXTURES:
        return OUT / name
    if name == DDL_ENGINE_FIXTURE:
        return ddl_engine_dir() / name
    return render_engine_dir() / name


def write_manifest(directory: pathlib.Path, layer: str, version: str) -> None:
    """Freeze a version directory by name and digest so a later tree can hold it."""
    files = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name != MANIFEST_NAME
    }
    (directory / MANIFEST_NAME).write_text(json.dumps({
        "layer": layer,
        "version": version,
        "files": files,
    }, ensure_ascii=False, indent=2) + "\n")
RENDER_SEED = 12345
SVG_PROFILE = "editable"  # structured output without filters; the port compares against this


def _samples(samples) -> list[dict]:
    return [
        {
            "t": round(s.t, 9),
            "x": round(s.x, 6),
            "y": round(s.y, 6),
            "width": round(s.width, 9),
            "energy": round(s.energy, 9),
            "lateral": round(s.lateral, 9),
            "event": s.event,
            # engine 13: the distance the lattice moved the sample. Zero for
            # every tool that does not quantize; the renderer turns it into the
            # opacity of one raster-bleed cell.
            "residual": round(s.residual, 9),
        }
        for s in samples
    ]


def _along(name, centerline, base_width, weight, seed, closed, anchors=frozenset(),
           grid_step=0.0, wild=False):
    result = se.synthesize_along(
        centerline, base_width, weight, seed, closed=closed, anchors=anchors,
        grid_step=grid_step, wild=wild,
    )
    return {
        "name": name,
        "input": {
            "centerline": [list(p) for p in centerline],
            "base_width": base_width,
            "weight": weight,
            "seed": seed,
            "closed": closed,
            "anchors": sorted(anchors),
            "grid_step": grid_step,
            "wild": wild,
        },
        "samples": _samples(result.samples),
        "left": [[round(x, 6), round(y, 6)] for x, y in result.left],
        "right": [[round(x, 6), round(y, 6)] for x, y in result.right],
        "event_count": result.event_count,
        "burr_side": result.burr_side,
        "burr_opacity": round(result.burr_opacity, 9),
        "path_d": se.contour_stroke_path(result),
    }


def stroke_engine_fixtures() -> None:
    line = [(100.0, 500.0), (300.0, 500.0), (500.0, 500.0), (700.0, 500.0), (900.0, 500.0)]
    circle = [(500 + 200 * math.cos(2 * math.pi * i / 48), 500 + 200 * math.sin(2 * math.pi * i / 48)) for i in range(48)]
    square = [(300.0, 300.0), (700.0, 300.0), (700.0, 700.0), (300.0, 700.0)]

    cases = [
        _along("open_line_pen", line, 6.0, "pen", 12345, False),
        _along("open_line_brush_thick", line, 6.0, "brush_thick", 999, False),
        _along("closed_circle_pencil", circle, 5.0, "pencil", 4242, True),
        _along("closed_square_crayon", square, 5.0, "crayon", 7, True, frozenset({0, 1, 2, 3})),
        # Closed, no anchors, with events: the seam correction and the event
        # branches have to hold at the same time.
        _along("closed_circle_chalk_events", circle, 5.0, "chalk", 12, True),
        # engine 14: `wild` now reaches the contour path, not only straight
        # strokes. A port that left `synthesize_along` on the engine 12 wiring
        # produces the OFF result here and passes everything else.
        _along("closed_circle_pencil_wild", circle, 5.0, "pencil", 4242, True, wild=True),
        # engine 13/14: the computer on the canvas-wide lattice. 18.0 px is
        # `canvas.unit * 0.018` for every square canvas.
        _along("closed_circle_computer_grid", circle, 5.0, "computer", 4242, True,
               grid_step=18.0),
        # The same contour with `wild` ON. A periodic grammar ignores `wild`, so
        # this must equal `closed_circle_computer_grid` value for value.
        _along("closed_circle_computer_grid_wild", circle, 5.0, "computer", 4242, True,
               grid_step=18.0, wild=True),
    ]
    out_path("stroke_engine_synthesize_along.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2))

    energy = [
        {"seed": seed, "samples": [round(se.latent_energy(i / 20.0, seed), 9) for i in range(21)]}
        for seed in (1, 12345, 999)
    ]
    out_path("stroke_engine_latent_energy.json").write_text(json.dumps(energy, ensure_ascii=False, indent=2))

    # The seeds are chosen so the event branches are actually taken: chalk seed 1
    # fires a `fade`, chalk seed 2 a `catch`, pencil seed 12 both a `correction`
    # and a `fade`, and chalk seed 21 would fire three but is cut to two by the
    # cap in `_event_map`. A port that never emits events passes only the first
    # four cases.
    straight = [
        _stroke("line_pen_no_event", (100.0, 500.0), (900.0, 500.0), 6.0, "pen", 12345),
        _stroke("line_rotring_flat", (100.0, 500.0), (900.0, 500.0), 6.0, "rotring", 12345),
        _stroke("line_brush_thick_taper", (200.0, 200.0), (800.0, 800.0), 8.0, "brush_thick", 999),
        _stroke("line_burin_bulge", (100.0, 300.0), (900.0, 700.0), 4.0, "burin", 4242),
        _stroke("line_chalk_fade", (100.0, 500.0), (900.0, 500.0), 6.0, "chalk", 1),
        _stroke("line_chalk_catch", (100.0, 500.0), (900.0, 500.0), 6.0, "chalk", 2),
        _stroke("line_pencil_two_events", (100.0, 500.0), (900.0, 500.0), 6.0, "pencil", 12),
        _stroke("line_chalk_event_cap", (100.0, 500.0), (900.0, 500.0), 6.0, "chalk", 21),
        _stroke("line_short_pencil", (400.0, 400.0), (600.0, 400.0), 3.0, "pencil", 31, samples=17),
        # engine 12: the centreline gesture. `rotring` has gesture 0.0, so its
        # pair is byte-identical in both states — a port that scales the wrong
        # term passes the OFF cases and fails only these.
        _stroke("line_pencil_gesture_off", (100.0, 500.0), (900.0, 500.0), 6.0, "pencil", 12345),
        _stroke("line_pencil_gesture_wild", (100.0, 500.0), (900.0, 500.0), 6.0, "pencil", 12345, wild=True),
        _stroke("line_brush_thick_wild", (200.0, 200.0), (800.0, 800.0), 8.0, "brush_thick", 999, wild=True),
        _stroke("line_rotring_wild", (100.0, 500.0), (900.0, 500.0), 6.0, "rotring", 12345, wild=True),
        # engine 13: the computer. Its energy, swell and gesture come from fixed
        # commensurate frequencies, so the figure repeats independently of the
        # seed — the pair below differs only in `seed` and must agree sample for
        # sample. Width lands on `base_width / width_steps` steps.
        _stroke("line_computer_plain", (100.0, 500.0), (900.0, 500.0), 6.0, "computer", 12345),
        _stroke("line_computer_other_seed", (100.0, 500.0), (900.0, 500.0), 6.0, "computer", 999),
        # engine 14: one canvas-wide lattice. Both of these carry the SAME
        # `grid_step`, so the short stroke lands on the same cells as the long
        # one. A port that keeps the engine 13 rule (pitch as a fraction of the
        # stroke) passes the long case and fails the short one.
        _stroke("line_computer_grid", (100.0, 500.0), (900.0, 500.0), 6.0, "computer", 12345,
                grid_step=18.0),
        _stroke("line_computer_grid_short", (450.0, 500.0), (550.0, 500.0), 6.0, "computer", 12345,
                grid_step=18.0, samples=17),
        # `wild` is ignored by a periodic grammar: this must equal
        # `line_computer_grid` value for value, including `residual`.
        _stroke("line_computer_grid_wild", (100.0, 500.0), (900.0, 500.0), 6.0, "computer", 12345,
                grid_step=18.0, wild=True),
        # A hand tool on the same lattice. The renderer never does this (only
        # quantizing tools get a non-zero step), but it separates "quantize when
        # the grammar says so" from "quantize when the caller passes a step":
        # the second is the implementation.
        _stroke("line_pencil_grid", (100.0, 500.0), (900.0, 500.0), 6.0, "pencil", 12345,
                grid_step=18.0),
    ]
    out_path("stroke_engine_synthesize_stroke.json").write_text(json.dumps(straight, ensure_ascii=False, indent=2))

    primitive_fixtures()


def _stroke(name, start, end, base_width, weight, seed, samples=49, wild=False, grid_step=0.0):
    result = se.synthesize_stroke(
        start, end, base_width, weight, seed, samples=samples, wild=wild, grid_step=grid_step
    )
    return {
        "name": name,
        "input": {
            "start": list(start), "end": list(end), "base_width": base_width,
            "weight": weight, "seed": seed, "samples": samples, "wild": wild,
            "grid_step": grid_step,
        },
        "samples": _samples(result.samples),
        "outline": [[round(x, 6), round(y, 6)] for x, y in result.outline],
        "event_count": result.event_count,
        "burr_side": result.burr_side,
        "burr_opacity": round(result.burr_opacity, 9),
        "path_d": se.polygon_path(result.outline),
    }


def primitive_fixtures() -> None:
    """The functions under `latent_energy` and `synthesize_*`, sampled directly.

    `_unit` is a THIRD hash construction, different from both `_hash01` and
    `_hash_to_unit` in the renderer: it hashes "{seed}:{label}:{index}" and reads
    the first 8 bytes as an UNSIGNED little-endian int64 over `2**64 - 1`, so it
    lands in [0, 1). Getting the signedness or the divisor wrong shifts every
    stroke without breaking determinism, which is the failure mode the geometry
    port already hit once.

    `_event_map` and the closed-loop helpers are not reachable through
    `latent_energy`, so they are pinned here rather than left to the end-to-end
    comparison.
    """
    labels = ("energy-1", "energy-6", "event-arrival", "event-kind", "catch-side", "burr-side", "burr-ink")
    unit = [
        {"seed": seed, "label": label, "index": index, "value": round(se._unit(seed, label, index), 12)}
        for seed in (1, 12345)
        for label in labels
        for index in (0, 1, 7, 48)
    ]
    smooth = [
        {"t": t, "seed": seed, "octave": octave, "value": round(se._smooth_noise(t, seed, octave), 12)}
        for seed in (12345, 999)
        for octave in (1, 3, 6)
        for t in (0.0, 0.25, 0.5, 1.0)
    ]
    # rate 0.0 (rotring) must yield no events at all; 0.9 (chalk) hits the
    # two-event cap; count 8 exercises the range(3, count - 3) window.
    events = [
        {
            "seed": seed, "rate": rate, "count": count,
            "events": [{"index": i, "kind": k} for i, k in sorted(se._event_map(seed, rate, count).items())],
        }
        for seed, rate, count in (
            (12345, 0.0, 49),    # rotring: rate 0 never fires
            (999, 0.0, 49),
            (12345, 0.9, 49),    # empty even at the highest rate
            (1, 0.9, 49),        # one fade
            (2, 0.9, 49),        # one catch
            (12, 0.9, 49),       # correction then fade
            (4, 0.9, 49),        # fade then correction
            (21, 0.9, 49),       # three would fire; the cap keeps two
            (31, 0.9, 49),       # four would fire; the cap keeps two
            (12, 0.55, 49),      # same seed, lower rate
            (2, 0.04, 49),       # silverpoint: rate too low to fire
            (18, 0.9, 8),        # short run: the window is range(3, 5)
            (68, 0.9, 8),        # both window slots fire
            (12345, 0.9, 4),     # empty window
            (647, 0.12, 100),    # probability capped at 0.12
            (1593, 0.12, 100),   # three would fire; the cap keeps two
        )
    ]

    open_line = [(100.0, 500.0), (300.0, 520.0), (500.0, 480.0), (900.0, 500.0)]
    closed_tri = [(500.0, 300.0), (700.0, 700.0), (300.0, 700.0)]
    normals = [
        {
            "name": name, "closed": closed, "points": [list(p) for p in pts],
            "normals": [[round(nx, 12), round(ny, 12)] for nx, ny in se.centerline_normals(pts, closed)],
            "arc_length_parameters": [round(v, 12) for v in se._arc_length_parameters(pts, closed)],
        }
        for name, pts, closed in (
            ("open_polyline", open_line, False),
            ("closed_triangle", closed_tri, True),
            ("closed_polyline_as_open", closed_tri, False),
        )
    ]

    # engine 12 primitives. `_edge_window` replaces the old `max(0, sin(pi t))`
    # envelope and has no peak in the middle; `_swell` is where the widest point
    # of a stroke now comes from, so it moves per seed. `_smooth_noise_salted`
    # is a FOURTH noise construction (explicit salt plus an explicit frequency)
    # and `_gesture_wave` is built on top of it with one and two cycles.
    edge_window = [
        {"t": t, "value": round(se._edge_window(t), 12)}
        for t in (0.0, 0.05, 0.08, 0.16, 0.3, 0.5, 0.7, 0.84, 0.92, 0.95, 1.0)
    ]
    swell = [
        {"t": t, "seed": seed, "value": round(se._swell(t, seed), 12)}
        for seed in (1, 12345, 999)
        for t in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]
    salted = [
        {
            "t": t, "seed": seed, "salt": salt, "frequency": frequency,
            "value": round(se._smooth_noise_salted(t, seed, salt, frequency), 12),
        }
        for seed in (12345, 999)
        for salt, frequency in (("swell", 1.0), ("gesture-lat", 1.0), ("gesture-lon", 2.0))
        for t in (0.0, 0.25, 0.5, 1.0)
    ]
    gesture = [
        {"t": t, "seed": seed, "salt": salt, "value": round(se._gesture_wave(t, seed, salt), 12)}
        for seed in (1, 12345)
        for salt in ("gesture-lat", "gesture-lon")
        for t in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]

    # engine 13: the machine terms. They take no seed at all, which is the whole
    # point — a computer stroke repeats exactly. A port that salts them with the
    # seed passes the shape tests and fails the two-seed identity above.
    machine = [
        {
            "t": t,
            "energy": round(se._machine_energy(t), 12),
            "swell": round(se._machine_swell(t), 12),
            "gesture": round(se._machine_gesture(t), 12),
        }
        for t in (0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0)
    ]
    # engine 14: rounding onto the lattice. Negative values and exact half steps
    # are where `round` and `floor(x+0.5)` part company.
    grid = [
        {"value": v, "step": step, "point": round(se.grid_point(v, step), 12)}
        for step in (0.0, 18.0, 7.5)
        for v in (0.0, 8.9, 9.0, 9.1, 17.999, 18.0, 27.0, 500.0, -9.0, -27.0, -500.5)
    ]
    # engine 14: the pitch itself. It is `min(width, height) * quantize`, so the
    # non-square canvases below all keep the square canvas's step. A port that
    # reads the long side (or the stroke length) diverges here first.
    from inku_server.plugins import canvas_size_for_aspect

    grid_step_px = [
        {
            "weight": w,
            "aspect": aspect,
            "canvas": [canvas_size_for_aspect(aspect).width, canvas_size_for_aspect(aspect).height],
            "value": round(renderer._grid_step_px(w, canvas_size_for_aspect(aspect)), 12),
        }
        for aspect in ("square", "wide", "pillar", "vertical")
        for w in ("computer", "pen", "rotring")
    ]

    out_path("stroke_engine_primitives.json").write_text(json.dumps({
        "grammars": {
            weight: {
                "stiffness": g.stiffness, "damping": g.damping,
                "energy_width": g.energy_width, "energy_lateral": g.energy_lateral,
                "event_rate": g.event_rate, "taper": g.taper, "bulge": g.bulge,
                "gesture": g.gesture,
                # engine 13: exact repetition, the lattice pitch as a fraction of
                # the canvas short side, and the number of width steps.
                "periodic": g.periodic, "quantize": g.quantize,
                "width_steps": g.width_steps,
            }
            for weight, g in se.GRAMMARS.items()
        },
        "wild_gain": se.WILD_GAIN,
        "gesture_edge": se._GESTURE_EDGE,
        "raster_bleed_opacity": renderer.RASTER_BLEED_OPACITY,
        "machine": machine,
        "grid_point": grid,
        "grid_step_px": grid_step_px,
        "unit": unit,
        "smooth_noise": smooth,
        "edge_window": edge_window,
        "swell": swell,
        "smooth_noise_salted": salted,
        "gesture_wave": gesture,
        "event_map": events,
        "centerline": normals,
    }, ensure_ascii=False, indent=2))


SCORES: dict[str, dict] = {
    "01_circle_pen": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "weight": "pen"}]},
    "02_line_brush": {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "weight": "brush_thick"}]},
    "03_square_filled": {"instructions": [{"primitive": "square", "position": [0.3, 0.3], "size": [0.4, 0.4], "weight": "pencil", "filled": True}]},
    "04_arc_crayon": {"instructions": [{"primitive": "arc", "center": [0.5, 0.5], "radius": 0.3, "angle_start": 0, "angle_end": 180, "weight": "crayon"}]},
    "05_circle_rotring": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "weight": "rotring"}]},
    "06_surface_hatch": {"instructions": [{"primitive": "square", "position": [0.25, 0.25], "size": [0.5, 0.5], "weight": "pen", "surface": {"texture": "hatch", "density": 0.5, "direction": "diagonal_rising"}}]},
    # engine 13/14: the computer tool. 17 and 18 differ only in length, and the
    # `raster-bleed` cells of both must sit on the same lattice — that is what
    # "one drawing, one grid" means. 19 puts the lattice on a closed contour,
    # 20 puts it on a canvas whose long side is 2.35x the short one (the pitch
    # must not move), and 21 sends it through the hatch call site.
    "17_line_computer": {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "weight": "computer"}]},
    "18_line_computer_short": {"instructions": [{"primitive": "line", "from": [0.45, 0.3], "to": [0.55, 0.3], "weight": "computer"}]},
    "19_circle_computer": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "weight": "computer"}]},
    "20_line_computer_wide": {"canvas": {"aspect": "wide"}, "instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "weight": "computer"}]},
    "21_hatch_computer": {"instructions": [{"primitive": "square", "position": [0.25, 0.25], "size": [0.5, 0.5], "weight": "computer", "surface": {"texture": "hatch", "density": 0.5, "direction": "diagonal_rising"}}]},
    # engine 16. 26 is a fill too small to scan: engine 15 flattened it into a
    # region fill, engine 16 places it as one stroke. 27-30 are the thickness
    # axis: 27 thins the ink itself, 28 is one of the two tools whose material
    # layer width is proportional to the ink (so the layer has to follow it),
    # 29 is the thinnest tool, which accepts no thinning at all, and 30 sends
    # the axis through the fill spacing, where it decides how many strokes fit.
    "26_tinyfill_circle_pen": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.005, "weight": "pen", "filled": True}]},
    "27_circle_pen_extra_fine": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "weight": "pen", "thinness": "extra_fine"}]},
    "28_circle_brush_thick_fine": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "weight": "brush_thick", "thinness": "fine"}]},
    "29_circle_silverpoint_extra_fine": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "weight": "silverpoint", "thinness": "extra_fine"}]},
    "30_square_filled_pencil_fine": {"instructions": [{"primitive": "square", "position": [0.3, 0.3], "size": [0.4, 0.4], "weight": "pencil", "filled": True, "thinness": "fine"}]},
    # engine 15 gave the corner shapes the material layer, and not one of the
    # cases above is a triangle or a polygon, so the port had to hold its own
    # hand-copied digests for them (CornerShapeMaterialLayerTest). These two put
    # the same shapes in the corpus, where the walk over the index reaches them.
    "31_triangle_pencil": {"instructions": [{"primitive": "triangle", "position": [0.3, 0.3], "size": [0.4, 0.4], "weight": "pencil"}]},
    "32_polygon_brush_thin": {"instructions": [{"primitive": "polygon", "center": [0.5, 0.5], "radius": 0.25, "sides": 6, "weight": "brush_thin"}]},
}

# Each of these repeats the Score of a tracked OFF render, so the pair is the
# test. engine 14 moved the line: `wild` now reaches every contour, not only the
# `line` primitive, so 16 must DIFFER from 01 (under engine 12 it was
# byte-identical). The two identities left are the discriminating ones —
# cloudform does not go through the stroke path at all, and a periodic grammar
# ignores `wild` — so a port that wires the flag in globally fails 24 and 25.
#
#   must differ:    15 vs 02   16 vs 01   22 vs 04   23 vs 03
#   must be equal:  24 vs 11   25 vs 17
WILD_SCORES: dict[str, str] = {
    "15_line_brush_wild": "02_line_brush",
    "16_circle_pen_wild": "01_circle_pen",
    "22_arc_crayon_wild": "04_arc_crayon",
    "23_square_filled_wild": "03_square_filled",
    "24_cloudform_pencil_wild": "11_cloudform_pencil",
    "25_line_computer_wild": "17_line_computer",
}

# engine 17. Every case above renders through the default catalog with `black`
# and no `color_hint`, so none of them reaches the palette assignment at all —
# a port that declares "17" without implementing it stays green on all of them.
# These six are the ones that reach it, one per branch of the assignment:
#
#   33  band holds exactly one palette color            dye_earth.purple
#   34  achromatic runs out and falls to the nearest    cool_material.black
#       lightness (this is [I-062]: the ink lands on
#       #e5e8e8, 0.062 away from the paper in OKLCH L)
#   35  band holds three, so the seed picks             sea_stone.blue
#   36  band is empty, so the nearest hue answers       default.yellow -> green
#   37  a hint of "brown" resolves to the orange slot   ink_season
#   38  the background is assigned, not looked up       ink_porcelain.blue
CATALOG_SCORES: dict[str, tuple[str, dict]] = {
    "33_circle_pen_dye_earth_purple": (
        "dye_earth",
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "weight": "pen", "color": "purple"}]},
    ),
    "34_circle_pen_cool_material_black": (
        "cool_material",
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "weight": "pen", "color": "black"}]},
    ),
    "35_square_filled_sea_stone_blue": (
        "sea_stone",
        {"instructions": [{"primitive": "square", "position": [0.3, 0.3], "size": [0.4, 0.4], "weight": "pencil", "filled": True, "color": "blue"}]},
    ),
    "36_circle_pen_default_yellow": (
        "default",
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "weight": "pen", "color": "yellow"}]},
    ),
    "37_circle_pen_ink_season_brown_hint": (
        "ink_season",
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "weight": "pen", "color": "black", "color_hint": "brown"}]},
    ),
    "38_line_pen_ink_porcelain_background": (
        "ink_porcelain",
        {"background": "blue", "instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "weight": "pen", "color": "white"}]},
    ),
}

TAGS = ("path", "polyline", "polygon", "circle", "ellipse", "line", "rect", "g")


def svg_fixtures() -> None:
    index: dict[str, dict] = {}
    cases = [
        (name, raw, False, None, DEFAULT_COLOR_CATALOG_ID)
        for name, raw in SCORES.items()
    ]
    cases += [
        (name, SCORES[source], True, source, DEFAULT_COLOR_CATALOG_ID)
        for name, source in WILD_SCORES.items()
    ]
    cases += [
        (name, raw, False, None, catalog_id)
        for name, (catalog_id, raw) in CATALOG_SCORES.items()
    ]
    for name, raw, wild, source, catalog_id in cases:
        composition_seed = SVG_COMPOSITION_SEEDS.get(name)
        svg = renderer.render(
            Score.model_validate(raw),
            color_map=render_color_map_for_catalog(catalog_id),
            catalog_id=catalog_id,
            render_seed=RENDER_SEED,
            composition_seed=composition_seed,
            svg_profile=SVG_PROFILE,
            wild=wild,
        )
        out_path(f"{name}.svg").write_text(svg)
        index[name] = {
            "score": raw,
            "render_seed": RENDER_SEED,
            "svg_profile": SVG_PROFILE,
            "wild": wild,
            "color_catalog_id": catalog_id,
            "bytes": len(svg),
            "counts": {tag: len(re.findall(f"<{tag}[ />]", svg)) for tag in TAGS},
            "classes": sorted(set(re.findall(r'class="([^"]+)"', svg))),
            "stroke_colors": sorted(set(re.findall(r'stroke="(#[0-9a-fA-F]{6})"', svg))),
            "fill_colors": sorted(set(re.findall(r'fill="(#[0-9a-fA-F]{6})"', svg))),
        }
        if source is not None:
            index[name]["wild_off_twin"] = source
        if composition_seed is not None:
            index[name]["composition_seed"] = composition_seed
    out_path("svg_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2))


def variation_fixtures() -> None:
    """Primitives behind the geometry variation, sampled directly.

    These pin the exact hash inputs. `_hash01` hashes "{seed}:{salt}:{i}" and
    `_hash_to_unit` hashes "{seed}:{i}" then reads a signed little-endian int64
    over 2**63 — two different constructions that a port can easily conflate.
    """
    from inku_server.schema import Variation

    hash01 = [
        {"i": i, "seed": seed, "salt": salt, "value": renderer._hash01(i, seed, salt)}
        for i, seed, salt in (
            (0, 12345, "wave-phase"), (0, 111, "wave-phase"), (0, 222, "wave-phase"),
            (3, 12345, "wave-phase"), (7, 999, "speck"), (0, 1, ""),
        )
    ]
    hash_to_unit = [
        {"i": i, "seed": seed, "value": renderer._hash_to_unit(i, seed)}
        for i, seed in ((0, 12345), (1, 12345), (3, 12345), (-1, 12345), (17, 999))
    ]
    value_noise = [
        {"x": x, "seed": 12345, "value": renderer._value_noise_1d(x, 12345)}
        for x in (0.0, 0.25, 1.5, 3.75, 12.0)
    ]
    periodic_noise = [
        {"x": x, "seed": 12345, "period": 6, "value": renderer._periodic_value_noise_1d(x, 12345, 6)}
        for x in (0.0, 0.5, 2.5, 5.9, 6.0)
    ]

    offsets = []
    for quality in ("wave", "perlin", "pink", "white"):
        for frequency in ("slow", "medium", "high"):
            variation = Variation(amplitude="medium", frequency=frequency, quality=quality, dimensions=["position_y"])
            samples = []
            for step in range(9):
                t = step / 8.0
                samples.append({
                    "t": t,
                    "segment": step,
                    "open": renderer._sample_offset(t, variation, 12345, step, 10.0),
                    "periodic": renderer._sample_offset_periodic(t, variation, 12345, step, 10.0),
                })
            offsets.append({"quality": quality, "frequency": frequency, "seed": 12345, "amp": 10.0, "samples": samples})

    out_path("renderer_variation_primitives.json").write_text(json.dumps({
        "frequency_cycles": renderer.FREQUENCY_CYCLES,
        "wave_phase": [{"seed": s, "value": renderer._wave_phase(s)} for s in (111, 222, 12345)],
        "hash01": hash01,
        "hash_to_unit": hash_to_unit,
        "value_noise_1d": value_noise,
        "periodic_value_noise_1d": periodic_noise,
        "sample_offset": offsets,
    }, ensure_ascii=False, indent=2))


def seed_range_fixtures() -> None:
    """Seeds as they actually occur, and the derivation that produces them.

    `_seed_for_instruction` returns `struct.unpack("<Q", ...)`, an UNSIGNED 64-bit
    integer, so roughly half of all real seeds exceed 2**63. Python prints those
    as their unsigned decimal; a Kotlin `Long` holding the same bits prints a
    negative number, and every hash keyed on `f"{seed}:..."` then diverges. The
    Phase 2c/2a fixtures all used small literal seeds, so none of them could see
    this. These do.

    The instruction cases also pin the canonical payload itself — key order,
    the `from` alias, the variation-field filter, and the fields that get popped
    — which a port otherwise has to guess from Pydantic's dump order.
    """
    from inku_server.schema import Instruction, Variation

    big = [
        0,
        1,
        2**31 - 1,
        2**31,
        2**32,
        2**63 - 1,
        2**63,  # first value a signed 64-bit Long renders as negative
        2**63 + 1,
        2**64 - 1,
        11790467468943091504,  # the real seed of `line_plain` below; a Long renders it negative
    ]
    out: dict = {
        "note": "seeds are unsigned 64-bit; format them as unsigned decimal before hashing",
        "stroke_engine_unit": [
            {"seed": seed, "label": label, "index": index,
             "value": round(se._unit(seed, label, index), 12)}
            for seed in big
            for label, index in (("energy-1", 0), ("event-arrival", 7), ("burr-side", 0))
        ],
        "renderer_hash01": [
            {"i": i, "seed": seed, "salt": salt, "value": renderer._hash01(i, seed, salt)}
            for seed in big
            for i, salt in ((0, "wave-phase"), (5, ""))
        ],
        "renderer_hash_to_unit": [
            {"i": i, "seed": seed, "value": renderer._hash_to_unit(i, seed)}
            for seed in big
            for i in (0, 3)
        ],
        "instruction_seed": [],
    }

    cases = {
        "line_plain": (Instruction(primitive="line", **{"from": (0.1, 0.5)}, to=(0.9, 0.5), weight="brush_thick"), None),
        "line_plain_render_seed": (Instruction(primitive="line", **{"from": (0.1, 0.5)}, to=(0.9, 0.5), weight="brush_thick"), 12345),
        "line_variation_white": (Instruction(primitive="line", **{"from": (0.1, 0.5)}, to=(0.9, 0.5), weight="pencil",
                                             variation=Variation(amplitude="medium", frequency="medium", quality="white", dimensions=["position_y"])), 12345),
        "circle_plain": (Instruction(primitive="circle", center=(0.5, 0.5), radius=0.2, weight="pen"), 12345),
        "circle_variation_wave": (Instruction(primitive="circle", center=(0.5, 0.5), radius=0.25, weight="pen",
                                              variation=Variation(amplitude="broad", frequency="medium", quality="wave", dimensions=["position_x", "position_y"])), 12345),
        "circle_variation_pink": (Instruction(primitive="circle", center=(0.5, 0.5), radius=0.25, weight="pen",
                                              variation=Variation(amplitude="medium", frequency="medium", quality="pink", dimensions=["position_x"])), 12345),
        "square_filled": (Instruction(primitive="square", position=(0.3, 0.3), size=(0.4, 0.4), weight="pencil", filled=True), 12345),
        "arc_crayon": (Instruction(primitive="arc", center=(0.5, 0.5), radius=0.3, angle_start=0, angle_end=180, weight="crayon"), 12345),
    }
    for name, (ins, performance_seed) in cases.items():
        payload = ins.model_dump(mode="json")
        out["instruction_seed"].append({
            "name": name,
            "instruction": payload,
            "performance_seed": performance_seed,
            "seed": renderer._seed_for_instruction(ins, performance_seed),
            "variation_seed_fields": (
                sorted(renderer._variation_seed_fields(ins))
                if renderer._variation_seed_fields(ins) is not None
                else None
            ),
        })

    out_path("renderer_seed_range.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))


def proportional_fixtures() -> None:
    """The engine 7 proportional system, sampled per canvas aspect.

    Everything here derives from `canvas.unit` (the shorter side) or from the
    shape's representative size, so a port that keeps an absolute px constant
    anywhere shows up as a mismatch on a non-square canvas.
    """
    from inku_server.plugins import canvas_size_for_aspect
    from inku_server.schema import Instruction, Variation

    aspects = ["square", "wide", "pillar", "vertical"]
    canvases = {a: canvas_size_for_aspect(a) for a in aspects}

    shapes = {
        "circle_r020": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.2),
        "circle_r005": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.05),
        "ellipse_06x03": Instruction(primitive="ellipse", center=(0.5, 0.5), size=(0.6, 0.3)),
        "square_04": Instruction(primitive="square", position=(0.3, 0.3), size=(0.4, 0.4)),
        "line_diagonal": Instruction(primitive="line", **{"from": (0.1, 0.1)}, to=(0.9, 0.9)),
        "arc_r030": Instruction(primitive="arc", center=(0.5, 0.5), radius=0.3, angle_start=0, angle_end=180),
        "tiny_dot": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.001),
    }

    out: dict = {
        "constants": {
            "AMPLITUDE_WIDTHS": renderer.AMPLITUDE_WIDTHS,
            "BLUR_RATIO": renderer.BLUR_RATIO,
            "BLUR_MIN_RATIO": renderer.BLUR_MIN_RATIO,
            "REPRESENTATIVE_MIN_RATIO": renderer.REPRESENTATIVE_MIN_RATIO,
            "AMPLITUDE_CLAMP_RATIO": renderer.AMPLITUDE_CLAMP_RATIO,
            "SEGMENT_TARGET_RATIO": renderer.SEGMENT_TARGET_RATIO,
            "SEGMENT_COUNT_MIN": renderer.SEGMENT_COUNT_MIN,
            "SEGMENT_COUNT_MAX": renderer.SEGMENT_COUNT_MAX,
            "STROKE_SAMPLE_TARGET_RATIO": renderer.STROKE_SAMPLE_TARGET_RATIO,
            "STROKE_SAMPLE_MIN": renderer.STROKE_SAMPLE_MIN,
            "STROKE_SAMPLE_MAX": renderer.STROKE_SAMPLE_MAX,
            "SPECK_ANCHOR_PERIMETER_RATIO": renderer.SPECK_ANCHOR_PERIMETER_RATIO,
            "SPECK_COUNT_MIN": renderer.SPECK_COUNT_MIN,
            "SPECK_COUNT_MAX_GAIN": renderer.SPECK_COUNT_MAX_GAIN,
            "CANVAS_PX": renderer.CANVAS_PX,
            "MATERIAL_INTENSITY_LEVEL": renderer.MATERIAL_INTENSITY_LEVEL,
            "MATERIAL_INTENSITY_SELECTED": renderer.MATERIAL_INTENSITY[renderer.MATERIAL_INTENSITY_LEVEL],
            "WEIGHT_TO_STROKE_WIDTH": renderer.WEIGHT_TO_STROKE_WIDTH,
            # engine 16 stage 3: the thickness axis. A multiplier on the tool's own
            # width, with a floor at the thinnest tool, so no amount of thinning
            # reorders the tools.
            "THINNESS_TO_WIDTH_SCALE": {
                ("null" if k is None else k): v
                for k, v in renderer.THINNESS_TO_WIDTH_SCALE.items()
            },
            "MIN_STROKE_WIDTH": renderer.MIN_STROKE_WIDTH,
        },
        "canvases": {a: {"width": c.width, "height": c.height, "unit": c.unit, "unit_scale": renderer._unit_scale(c)} for a, c in canvases.items()},
        "representative_size_px": [],
        "amplitude_px": [],
        "blur_std_px": [],
        "segment_count": [],
        "stroke_sample_count": [],
        "stroke_width_px": [],
        "stroke_width_thinness_px": [],
        "material_outline_thinness": [],
        "speck_count": [],
    }

    for aspect, canvas in canvases.items():
        for shape_name, ins in shapes.items():
            out["representative_size_px"].append({
                "aspect": aspect, "shape": shape_name,
                "raw": renderer._representative_size_px(ins, canvas),
                "clamped": renderer._clamped_representative_px(ins, canvas),
            })
            for amplitude in ("fine", "medium", "broad"):
                variation = Variation(amplitude=amplitude, frequency="medium", quality="perlin", dimensions=["position_y"])
                out["amplitude_px"].append({"aspect": aspect, "shape": shape_name, "amplitude": amplitude,
                                            "value": renderer._amplitude_px(variation, ins, canvas)})
                out["blur_std_px"].append({"aspect": aspect, "shape": shape_name, "amplitude": amplitude,
                                           "value": renderer._blur_std_px(variation, ins, canvas)})

        for path_len in (10.0, 120.0, 1256.6, 5000.0, 40000.0):
            out["segment_count"].append({"aspect": aspect, "path_len_px": path_len,
                                         "value": renderer._segment_count(path_len, canvas)})
            out["stroke_sample_count"].append({"aspect": aspect, "length_px": path_len,
                                               "value": renderer._stroke_sample_count(path_len, canvas)})
            for base in (18, 28, 36):
                out["speck_count"].append({"aspect": aspect, "base": base, "path_len_px": path_len,
                                           "value": renderer._speck_count(base, path_len, canvas)})

        for weight in sorted(renderer.WEIGHT_TO_STROKE_WIDTH):
            out["stroke_width_px"].append({"aspect": aspect, "weight": weight,
                                           "value": renderer._stroke_width_px(weight, canvas)})
            # Every tool at every thinness, so a port that drops the floor shows up
            # as silverpoint going below 0.5 and as the tool order collapsing.
            for thinness in (None, "fine", "extra_fine"):
                out["stroke_width_thinness_px"].append({
                    "aspect": aspect, "weight": weight, "thinness": thinness,
                    "value": renderer._stroke_width_px(weight, canvas, thinness),
                })

        # The material layer follows the thinned ink where its width is proportional
        # to it, and keeps its own distance: strength is not distance (engine 15).
        # The tool list comes from the specs themselves so a new tool cannot slip
        # past this fixture.
        for weight in sorted(renderer._MATERIAL_OUTLINE_SPECS):
            for thinness in (None, "fine", "extra_fine"):
                layers = renderer._material_outline_profile(weight, canvas, thinness)
                out["material_outline_thinness"].append({
                    "aspect": aspect, "weight": weight, "thinness": thinness,
                    "layers": [
                        {"offset": round(offset, 9), "width": round(width, 9),
                         "opacity": round(opacity, 9), "dash": dash}
                        for offset, width, opacity, dash in layers
                    ],
                })

    out_path("renderer_proportional.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))


VARIATION_SCORES: dict[str, dict] = {
    "07_circle_wave": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.25, "weight": "pen", "variation": {"amplitude": "broad", "frequency": "medium", "quality": "wave", "dimensions": ["position_x", "position_y"]}}]},
    "08_circle_perlin": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.25, "weight": "pen", "variation": {"amplitude": "fine", "frequency": "high", "quality": "perlin", "dimensions": ["radius"]}}]},
    "09_line_white": {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "weight": "pencil", "variation": {"amplitude": "medium", "frequency": "medium", "quality": "white", "dimensions": ["position_y"]}}]},
    "10_arc_wave": {"instructions": [{"primitive": "arc", "center": [0.5, 0.5], "radius": 0.3, "angle_start": 0, "angle_end": 180, "weight": "pen", "variation": {"amplitude": "medium", "frequency": "slow", "quality": "wave", "dimensions": ["position_y"]}}]},
}


def fill_and_arc_fixtures() -> None:
    """The engine 9/10 interior fill, hatch strokes and arc centerlines.

    Everything the phase 2f port needs before it can compare a `<path d>`: the
    scan angle and spacing that place the scanlines, the per-brush seed, the
    intersection segments themselves, the hatch line geometry, and the arc
    centerlines that feed `synthesize_along`.

    The scanline walk is where a port silently diverges. The half-open edge test
    (`da <= 0 < db`) decides whether a scanline grazing a vertex is counted once
    or twice, the spacing jitter advances the offset by a hashed factor rather
    than by a constant, and the `index % 2` flip reverses every other brush. Any
    one of those getting dropped still produces a plausible fill and a wrong
    `strokes-NN`.
    """
    from inku_server.plugins import canvas_size_for_aspect
    from inku_server.schema import Instruction, SurfaceSpec

    canvases = {a: canvas_size_for_aspect(a) for a in ("square", "pillar")}

    def poly(points):
        return [[round(x, 6), round(y, 6)] for x, y in points]

    # A convex square, a sampled circle and a concave L: the concave contour is
    # the one that needs more than two intersections per scanline.
    contours = {
        "square_400": [(300.0, 300.0), (700.0, 300.0), (700.0, 700.0), (300.0, 700.0)],
        "circle_r200": [
            (500.0 + 200.0 * math.cos(2 * math.pi * i / 62), 500.0 + 200.0 * math.sin(2 * math.pi * i / 62))
            for i in range(62)
        ],
        "concave_l": [
            (200.0, 200.0), (800.0, 200.0), (800.0, 400.0),
            (400.0, 400.0), (400.0, 800.0), (200.0, 800.0),
        ],
    }

    fill_shapes = {
        "square_pencil": Instruction(primitive="square", position=(0.3, 0.3), size=(0.4, 0.4), weight="pencil", filled=True),
        "square_brush_thick": Instruction(primitive="square", position=(0.3, 0.3), size=(0.4, 0.4), weight="brush_thick", filled=True),
        "circle_pen": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.2, weight="pen", filled=True),
        "square_rotring": Instruction(primitive="square", position=(0.3, 0.3), size=(0.4, 0.4), weight="rotring", filled=True),
        "tiny_dot_pencil": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.004, weight="pencil", filled=True),
        "square_surface": Instruction(primitive="square", position=(0.25, 0.25), size=(0.5, 0.5), weight="pen", filled=True,
                                      surface=SurfaceSpec(texture="hatch", density=0.5, direction="diagonal_rising")),
    }

    seeds = [0, 12345, 2**63, 11790467468943091504]

    out: dict = {
        "note": "fill scanlines, hatch strokes and arc centerlines; seeds are unsigned 64-bit",
        "constants": {
            "FILL_SPACING_WIDTH_GAIN": renderer.FILL_SPACING_WIDTH_GAIN,
            "FILL_SPACING_UNIT_RATIO": renderer.FILL_SPACING_UNIT_RATIO,
            "FILL_SPACING_JITTER": renderer.FILL_SPACING_JITTER,
            "FILL_MIN_SCANLINES": renderer.FILL_MIN_SCANLINES,
            "FILL_MIN_STROKE_WIDTHS": renderer.FILL_MIN_STROKE_WIDTHS,
            "FILL_DAB_SAMPLES": renderer.FILL_DAB_SAMPLES,
            "FILL_DAB_MIN_TRAVEL": renderer.FILL_DAB_MIN_TRAVEL,
        },
        "fill_scan_angle": [
            {"seed": seed, "value": round(renderer._fill_scan_angle(seed), 12)}
            for seed in seeds
        ],
        "fill_scan_spacing": [
            {"aspect": aspect, "shape": name, "weight": ins.weight,
             "value": round(renderer._fill_scan_spacing(ins, canvas), 9)}
            for aspect, canvas in canvases.items()
            for name, ins in fill_shapes.items()
        ],
        "fill_stroke_seed": [
            {"seed": seed, "index": index, "value": renderer._fill_stroke_seed(seed, index)}
            for seed in seeds
            for index in (0, 1, 47, 4096)
        ],
        # `_fills_interior` is `false` whenever a surface is present, whatever
        # `filled` says, and `_interior_fill` degrades rotring to a region fill.
        "fills_interior": [
            {"shape": name, "filled": ins.filled, "has_surface": ins.surface is not None,
             "value": renderer._fills_interior(ins),
             "uses_hand_stroke": renderer._uses_hand_stroke(ins.weight)}
            for name, ins in fill_shapes.items()
        ],
        "scanline_segments": [],
        "fill_stroke_group": [],
        "fill_dab_group": [],
        "surface_hatch": [],
        "arc_centerline": [],
    }

    # The contour the fill scans is NOT the sampled stroke contour. Without a
    # variation the caller passes the bare `corners` (4 points for a square) and
    # only the varied branch passes the sampled contour. Scanning the sampled
    # contour instead changes nothing visually but shifts every intersection,
    # so `strokes-NN` comes out wrong. `03_square_filled` is the case that pins it.
    import svgwrite

    fill_group_cases = {
        "square_filled_pencil": (fill_shapes["square_pencil"], "square"),
        "square_filled_brush_thick": (fill_shapes["square_brush_thick"], "square"),
        "square_filled_pencil_pillar": (fill_shapes["square_pencil"], "pillar"),
        "circle_filled_pen": (fill_shapes["circle_pen"], "square"),
        "tiny_dot_pencil": (fill_shapes["tiny_dot_pencil"], "square"),
    }
    # `svgwrite` keeps a path's `d` in the element's command list, not in
    # `attribs`, so reading `attribs["d"]` yields an empty string and any test
    # comparing it is vacuously true. Serialise the element and read `d` back.
    def path_d_list(group):
        if group is None:
            return []
        return [
            re.search(r' d="([^"]*)"', element.tostring()).group(1)
            for element in group.elements
        ]

    def contour_for(ins, canvas):
        if ins.primitive == "square":
            assert ins.position is not None and ins.size is not None
            px, py = renderer._px(ins.position, canvas)
            w = ins.size[0] * canvas.width
            h = ins.size[1] * canvas.height
            return [(px, py), (px + w, py), (px + w, py + h), (px, py + h)]
        assert ins.center is not None and ins.radius is not None
        ccx = ins.center[0] * canvas.width
        ccy = ins.center[1] * canvas.height
        rr = ins.radius * canvas.unit
        count = renderer._stroke_sample_count(2 * math.pi * rr, canvas)
        return [
            (ccx + rr * math.cos(2 * math.pi * i / count), ccy + rr * math.sin(2 * math.pi * i / count))
            for i in range(count)
        ]

    for name, (ins, aspect) in fill_group_cases.items():
        canvas = canvases[aspect]
        seed = renderer._seed_for_instruction(ins, RENDER_SEED)
        contour = contour_for(ins, canvas)
        attrs = {"stroke": "#111111", "fill": "#111111", "fill_opacity": 1.0, "stroke_opacity": 1.0}
        group = renderer._render_fill_strokes(
            svgwrite.Drawing(), ins, contour, attrs, canvas, RENDER_SEED, use_filters=False
        )
        paths = path_d_list(group)
        out["fill_stroke_group"].append({
            "case": name,
            "aspect": aspect,
            "weight": ins.weight,
            "seed": seed,
            "scan_contour": poly(contour),
            "angle": round(renderer._fill_scan_angle(seed), 12),
            "spacing": round(renderer._fill_scan_spacing(ins, canvas), 9),
            "base_width": round(renderer._stroke_width_px(ins.weight, canvas), 9),
            # None means the fill degraded to a region fill (`FILL_MIN_SCANLINES`).
            "class": None if group is None else group.attribs.get("class"),
            "stroke_count": len(paths),
            "path_d": paths,
        })

    # engine 16 stage 2: a fill too small to scan is not flattened into a region
    # fill, it is placed as one stroke. The cases below pin the routing decision
    # itself (`_interior_fill`), not just the dab: the machine tool still gets a
    # region fill, the sizes either side of the measured ~3% boundary go opposite
    # ways, and the thinned dab is narrower than the default one.
    fill_dab_cases = {
        "tiny_circle_pen": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.005, weight="pen", filled=True),
        "tiny_circle_pencil": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.004, weight="pencil", filled=True),
        "tiny_circle_brush_thick": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.005, weight="brush_thick", filled=True),
        "tiny_circle_silverpoint": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.005, weight="silverpoint", filled=True),
        # The machine pole: rotring never leaves the region fill, at any size.
        "tiny_circle_rotring": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.005, weight="rotring", filled=True),
        # A sliver still has enough scanlines to be scanned, so `interior_class`
        # stays a scan here; the recorded dab is what the long axis would give.
        "sliver_square_pen": Instruction(primitive="square", position=(0.4, 0.49), size=(0.2, 0.004), weight="pen", filled=True),
        # Either side of the boundary measured at 2.9-3.2% of the short side.
        "boundary_below_pen": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.014, weight="pen", filled=True),
        "boundary_above_pen": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.017, weight="pen", filled=True),
        "large_circle_pen": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.2, weight="pen", filled=True),
        # The thickness axis does NOT narrow a dab this small: the width is
        # `max(tool width, short axis)` and the shape wins (2.0 and 0.7 both lose
        # to 10px). What moves is the seed, so the same dab is played by another
        # hand. `base_width` records the tool width either way.
        "tiny_circle_pen_extra_fine": Instruction(primitive="circle", center=(0.5, 0.5), radius=0.005, weight="pen", filled=True, thinness="extra_fine"),
    }
    for name, ins in fill_dab_cases.items():
        canvas = canvases["square"]
        contour = contour_for(ins, canvas)
        attrs = {"stroke": "#111111", "fill": "#111111", "fill_opacity": 1.0, "stroke_opacity": 1.0}
        scan = renderer._render_fill_strokes(
            svgwrite.Drawing(), ins, contour, attrs, canvas, RENDER_SEED, use_filters=False
        )
        dab = renderer._render_fill_dab(
            svgwrite.Drawing(), ins, contour, attrs, canvas, RENDER_SEED, use_filters=False
        )
        chosen, region_fill = renderer._interior_fill(
            svgwrite.Drawing(), ins, contour, attrs, canvas, RENDER_SEED, use_filters=False
        )
        dab_paths = path_d_list(dab)
        out["fill_dab_group"].append({
            "case": name,
            "weight": ins.weight,
            "thinness": ins.thinness,
            "seed": renderer._seed_for_instruction(ins, RENDER_SEED),
            "contour": poly(contour),
            "base_width": round(renderer._stroke_width_px(ins.weight, canvas, ins.thinness), 9),
            # None here is what engine 15 called the degradation point.
            "scan_class": None if scan is None else scan.attribs.get("class"),
            "dab_class": None if dab is None else dab.attribs.get("class"),
            "dab_path_count": len(dab_paths),
            "dab_path_d": dab_paths,
            # What `_interior_fill` actually returns for this instruction.
            "interior_class": None if chosen is None else chosen.attribs.get("class"),
            "interior_region_fill": region_fill,
        })

    for contour_name, contour in contours.items():
        for seed in seeds:
            angle = renderer._fill_scan_angle(seed)
            for spacing in (18.0, 45.0):
                segments = renderer._scanline_segments(contour, angle, spacing, seed)
                out["scanline_segments"].append({
                    "contour": contour_name,
                    "contour_points": poly(contour),
                    "seed": seed,
                    "angle": round(angle, 12),
                    "spacing": spacing,
                    "count": len(segments),
                    "scanline_indices": sorted({index for index, _, _ in segments}),
                    "segments": [
                        {"index": index,
                         "start": [round(s[0], 6), round(s[1], 6)],
                         "end": [round(e[0], 6), round(e[1], 6)]}
                        for index, s, e in segments
                    ],
                })

    # Hatch geometry, straight out of `_render_surface_vectors`. The port has to
    # reproduce the line placement before it can stroke it: the loop runs over
    # `range(-count // 2, count // 2 + 1)`, and the per-line seed is
    # `_fill_stroke_seed(seed, i + layer_index * 4096)` where `i` is the LINE
    # index, not the sample index that shadows it inside the comprehension.
    hatch_cases = {
        "hatch_diagonal_rising": SurfaceSpec(texture="hatch", density=0.5, direction="diagonal_rising"),
        "hatch_dense": SurfaceSpec(texture="hatch", density=0.9, direction="horizontal"),
        "crosshatch_gradient": SurfaceSpec(texture="crosshatch", density=0.4, direction="vertical",
                                       spacing_gradient="coarse_to_dense"),
    }
    for aspect, canvas in canvases.items():
        for case_name, surface in hatch_cases.items():
            ins = Instruction(primitive="square", position=(0.25, 0.25), size=(0.5, 0.5),
                              weight="pen", surface=surface)
            bbox = renderer._shape_bbox(ins, canvas)
            assert bbox is not None
            x, y, w, h = bbox
            seed = renderer._seed_for_instruction(ins, RENDER_SEED)
            angle = renderer._surface_line_angle(surface)
            spacing = max(5.0, canvas.unit * (0.010 + (1.0 - surface.density) * 0.025))
            span = math.hypot(w, h) * 1.3
            count = min(80, max(3, int(span / spacing)))
            angles = [angle]
            if surface.texture == "crosshatch":
                angles.append(angle + math.radians(60 + renderer._hash01(8, seed, "cross-angle") * 30))
            lines = []
            for layer_index, layer_angle in enumerate(angles):
                lux, luy = math.cos(layer_angle), math.sin(layer_angle)
                lnx, lny = -luy, lux
                for i in range(-count // 2, count // 2 + 1):
                    progress = (i + count / 2) / max(1, count)
                    gradient = 1.0
                    if surface.spacing_gradient == "coarse_to_dense":
                        gradient = 1.35 - progress * 0.7
                    elif surface.spacing_gradient == "dense_to_coarse":
                        gradient = 0.65 + progress * 0.7
                    offset = (i * spacing * gradient
                              + renderer._hash_to_unit(i + layer_index * 401 + 500, seed) * spacing * 0.12)
                    ox, oy = lnx * offset, lny * offset
                    lines.append({
                        "layer": layer_index,
                        "i": i,
                        "gradient": round(gradient, 12),
                        "offset": round(offset, 9),
                        "start": [round(x + w / 2 + ox - lux * span / 2, 6),
                                  round(y + h / 2 + oy - luy * span / 2, 6)],
                        "end": [round(x + w / 2 + ox + lux * span / 2, 6),
                                round(y + h / 2 + oy + luy * span / 2, 6)],
                        "hatch_class": f"hatch-spacing-{spacing * gradient:.3f}",
                        "stroke_seed": renderer._fill_stroke_seed(seed, i + layer_index * 4096),
                    })
            out["surface_hatch"].append({
                "aspect": aspect,
                "case": case_name,
                "seed": seed,
                "bbox": [round(v, 6) for v in bbox],
                "angle": round(angle, 12),
                "spacing": round(spacing, 9),
                "span": round(span, 9),
                "count": count,
                "layer_angles": [round(a, 12) for a in angles],
                "sample_count": max(2, renderer._stroke_sample_count(span, canvas)),
                "line_width": round(max(0.45, canvas.unit * 0.0016), 9),
                "lines": lines,
            })

    # Arc centerlines. `_render_arc_hand_stroke` picks the sample count from the
    # ARC LENGTH (`r * |end - start|` in radians), not from the chord, and the
    # varied branch goes through `_arc_points_with_variation` instead.
    from inku_server.schema import Variation

    arc_cases = {
        "arc_crayon": (Instruction(primitive="arc", center=(0.5, 0.5), radius=0.3,
                                   angle_start=0, angle_end=180, weight="crayon"), "square"),
        "arc_wave": (Instruction(primitive="arc", center=(0.5, 0.5), radius=0.3,
                                 angle_start=0, angle_end=180, weight="pen",
                                 variation=Variation(amplitude="medium", frequency="slow",
                                                     quality="wave", dimensions=["position_y"])), "square"),
        "arc_crayon_pillar": (Instruction(primitive="arc", center=(0.5, 0.5), radius=0.3,
                                          angle_start=20, angle_end=300, weight="crayon"), "pillar"),
    }
    for name, (ins, aspect) in arc_cases.items():
        canvas = canvases[aspect]
        cx = 0.5 * canvas.width
        cy = 0.5 * canvas.height
        r = 0.3 * canvas.unit
        seed = renderer._seed_for_instruction(ins, RENDER_SEED)
        varied = renderer._needs_contour_variation(ins.variation)
        if varied:
            assert ins.variation is not None
            centerline = renderer._arc_points_with_variation(
                cx, cy, r, ins.angle_start, ins.angle_end, ins.variation, seed,
                renderer._amplitude_px(ins.variation, ins, canvas), canvas,
            )
        else:
            arc_len = r * abs(math.radians(ins.angle_end) - math.radians(ins.angle_start))
            centerline = renderer._arc_points(
                cx, cy, r, ins.angle_start, ins.angle_end,
                renderer._stroke_sample_count(arc_len, canvas),
            )
        stroke = se.synthesize_along(centerline, renderer._stroke_width_px(ins.weight, canvas),
                                     ins.weight, seed, closed=False)
        out["arc_centerline"].append({
            "case": name,
            "aspect": aspect,
            "seed": seed,
            "varied": varied,
            "cx": round(cx, 6), "cy": round(cy, 6), "r": round(r, 6),
            "angle_start": ins.angle_start, "angle_end": ins.angle_end,
            "arc_length_px": round(r * abs(math.radians(ins.angle_end) - math.radians(ins.angle_start)), 9),
            "centerline": poly(centerline),
            "intent_path_d": (None if varied
                              else renderer._arc_path_d(cx, cy, r, ins.angle_start, ins.angle_end)),
            "class": f"arc-stroke-v1 controls-{len(stroke.samples)} events-{stroke.event_count}",
            "path_d": se.contour_stroke_path(stroke),
        })

    out_path("renderer_fill_and_arc.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))


WEIGHTS_ALL = (
    "silverpoint", "pencil", "pen", "rotring", "crayon",
    "chalk", "brush_thin", "brush_thick", "burin", "drypoint",
    # engine 13. Its lateral energy is 0.34, so the cloudform touch term is not
    # zero: a port that treats the computer as "rotring with a lattice" lands on
    # a different contour for every angle.
    "computer",
)

CLOUDFORM_SCORES: dict[str, dict] = {
    "11_cloudform_pencil": {"instructions": [{"primitive": "cloudform", "center": [0.5, 0.5], "size": [0.5, 0.34], "weight": "pencil"}]},
    "12_cloudform_rotring": {"instructions": [{"primitive": "cloudform", "center": [0.5, 0.5], "size": [0.5, 0.34], "weight": "rotring"}]},
    # 双弧（葉形）。prior が arc のとき sagitta の符号が反転し、対向する劣弧になる。
    "13_touching_arcs": {"instructions": [
        {"primitive": "arc", "center": [0.5, 0.5], "radius": 0.26, "angle_start": 200.0, "angle_end": 340.0, "weight": "pen"},
        {"primitive": "arc", "center": [0.5, 0.5], "radius": 0.26, "angle_start": 20.0, "angle_end": 160.0, "weight": "pen",
         "relation": {"type": "touching", "contact": "both_ends"}},
    ]},
    # region 配置 → relation 解決の順序（v1.94）。逆順だと relation が無言で落ちる。
    "14_region_then_relation": {"instructions": [
        {"primitive": "arc", "center": [0.35, 0.4], "radius": 0.18, "angle_start": 200.0, "angle_end": 340.0, "weight": "pencil"},
        {"primitive": "arc", "center": [0.5, 0.5], "radius": 0.18, "angle_start": 20.0, "angle_end": 160.0, "weight": "pencil",
         "at": {"region": [0.55, 0.55, 0.95, 0.95]},
         "relation": {"type": "touching", "contact": "both_ends"}},
    ]},
}


def _round_points(points) -> list[list[float]]:
    return [[round(x, 9), round(y, 9)] for x, y in points]


def cloudform_and_relation_fixtures() -> None:
    """Phase 2g expectations: cloudform contours, minor arcs, and resolve order.

    The discriminating axis is the tool grammar. `_base_radius` scales its touch
    term by `GRAMMARS[weight].energy_lateral * 0.018`, so a port that invents its
    own weight table (rather than reusing the grammar table already ported in 2c)
    lands on different radii for every tool. `rotring` is the sharpest probe: its
    lateral energy is exactly 0.0, so its contour must carry no touch term at all.
    """
    out: dict = {}

    # 道具ごとの lateral energy。雲形の touch 項はこの値だけで決まる。
    out["tool_energy_lateral"] = [
        {"weight": w, "energy_lateral": se.GRAMMARS[w].energy_lateral,
         "touch_gain": round(se.GRAMMARS[w].energy_lateral * 0.018, 12)}
        for w in WEIGHTS_ALL
    ]

    # seed 導出。符号なし 64bit をまたぐ値を混ぜる。
    out["cloudform_seed"] = [
        {"performance_seed": ps, "instruction_index": ii, "mark_index": mi,
         "value": str(cf.cloudform_seed(ps, ii, mi))}
        for ps, ii, mi in (
            (None, 0, 0), (12345, 0, 0), (12345, 1, 0), (12345, 0, 2),
            (2**63 + 1, 0, 0), (2**64 - 1, 3, 1),
        )
    ]

    # _base_radius を全道具 × 代表角で。ここが外れると輪郭全体が外れる。
    thetas = [0.0, math.tau / 8, math.tau / 3, math.tau * 0.77]
    seed = cf.cloudform_seed(12345, 0, 0)
    out["base_radius"] = [
        {"weight": w, "seed": str(seed), "theta": round(t, 12),
         "value": round(cf._base_radius(t, seed, None, w), 12)}
        for w in WEIGHTS_ALL for t in thetas
    ]

    varied = Variation.model_validate(
        {"amplitude": "broad", "frequency": "medium", "quality": "wave",
         "dimensions": ["position_x", "position_y"]})
    out["base_radius_varied"] = [
        {"weight": w, "seed": str(seed), "theta": round(t, 12),
         "value": round(cf._base_radius(t, seed, varied, w), 12)}
        for w in ("pencil", "rotring", "brush_thick") for t in thetas
    ]

    # 輪郭そのもの。全道具 + 変奏 + 高位 seed。
    contours = []
    for w in WEIGHTS_ALL:
        c = cf.generate_cloudform_contour(
            (0.5, 0.5), (0.5, 0.34), performance_seed=12345,
            instruction_index=0, mark_index=0, variation=None, weight=w)
        contours.append({"case": f"{w}-plain", "weight": w, "performance_seed": 12345,
                         "variation": None, "point_count": len(c.points),
                         "points": _round_points(c.points), "path_d": c.path_d})
    for w, ps, var in (("pencil", 12345, varied), ("rotring", 12345, varied),
                       ("pencil", 2**63 + 1, None), ("brush_thick", 2**64 - 1, None)):
        c = cf.generate_cloudform_contour(
            (0.5, 0.5), (0.5, 0.34), performance_seed=ps,
            instruction_index=0, mark_index=0, variation=var, weight=w)
        contours.append({
            "case": f"{w}-seed{ps}-{'varied' if var else 'plain'}", "weight": w,
            "performance_seed": str(ps),
            "variation": (var.model_dump(by_alias=True) if var else None),
            "point_count": len(c.points), "points": _round_points(c.points),
            "path_d": c.path_d})
    out["cloudform_contour"] = contours

    # 劣弧再構成の素。touching はこの 3 関数の上に載る。
    out["minor_arc_delta"] = [
        {"angle_start": a, "angle_end": b, "value": round(ag.minor_arc_delta(a, b), 12)}
        for a, b in ((0.0, 90.0), (0.0, 270.0), (350.0, 10.0), (10.0, 350.0), (0.0, 180.0), (-45.0, 200.0))
    ]
    out["arc_from_endpoints_and_sagitta"] = []
    for start, end, sag in (((100.0, 500.0), (400.0, 500.0), 60.0),
                            ((100.0, 500.0), (400.0, 500.0), -60.0),
                            ((200.0, 200.0), (600.0, 640.0), 90.0)):
        g = ag.arc_from_endpoints_and_sagitta(start, end, sag)
        out["arc_from_endpoints_and_sagitta"].append({
            "start": list(start), "end": list(end), "sagitta": sag,
            "center": [round(g.center[0], 9), round(g.center[1], 9)],
            "radius": round(g.radius, 9),
            "angle_start": round(g.angle_start, 9), "angle_end": round(g.angle_end, 9),
            "signed_sagitta_roundtrip": round(
                ag.signed_arc_sagitta(g.center, g.radius, g.angle_start, g.angle_end), 9),
        })

    # region 配置 → relation 解決の順序。逆順だと relation が落ちる。
    resolved = []
    for name, raw in CLOUDFORM_SCORES.items():
        if name.startswith(("11_", "12_")):
            continue
        score = Score.model_validate(raw)
        after = renderer._resolve_performance_score(score, RENDER_SEED)
        resolved.append({
            "case": name, "performance_seed": RENDER_SEED,
            "score_in": raw,
            "score_out": after.model_dump(by_alias=True),
        })
    # 負例: circle への touching は落ちるのが正しい（line/arc でないため）。
    circle_raw = {"instructions": [
        {"primitive": "circle", "center": [0.36, 0.5], "radius": 0.16, "weight": "pen"},
        {"primitive": "circle", "center": [0.68, 0.5], "radius": 0.16, "weight": "pen",
         "relation": {"type": "touching", "contact": "both_ends"}},
    ]}
    circle_after = renderer._resolve_performance_score(Score.model_validate(circle_raw), RENDER_SEED)
    resolved.append({"case": "circle_touching_drops", "performance_seed": RENDER_SEED,
                     "score_in": circle_raw, "score_out": circle_after.model_dump(by_alias=True)})

    # grid arrangement + relation は relation が落ちるのが正しい。
    grid_raw = {"instructions": [
        {"primitive": "circle", "center": [0.3, 0.3], "radius": 0.1, "weight": "pen"},
        {"primitive": "circle", "center": [0.6, 0.6], "radius": 0.1, "weight": "pen",
         "arrangement": {"layout": "grid", "count": 4, "rows": 2, "cols": 2},
         "relation": {"type": "touching", "contact": "both_ends"}},
    ]}
    grid_after = renderer._resolve_performance_score(Score.model_validate(grid_raw), RENDER_SEED)
    resolved.append({"case": "grid_drops_relation", "performance_seed": RENDER_SEED,
                     "score_in": grid_raw, "score_out": grid_after.model_dump(by_alias=True)})
    out["resolve_performance_score"] = resolved

    out_path("renderer_cloudform_and_relations.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2))


DDL_EXPAND_JA = "中心に黒い四角を置く。白い横線を三本引く。"
DDL_EXPAND_EN = "Place one black square near the center. Draw three white horizontal lines."
DDL_EXPAND_SCATTER = "赤い円を三つ置く。小さな点を画面全体に散らす。"
DDL_EXPAND_PLUGIN = "黒い線を三本引く。Nature.うねり。"
DDL_EXPAND_SENSORY = "湿った空気が漂い、匂いが残る。線を三本引く。円を二つ置く。"
DDL_EXPAND_MUSIC = "祭りの太鼓が鳴り響き、色とりどりの紙が舞う。線を五本引く。円を三つ置く。四角を二つ置く。"
DDL_EXPAND_SENSORY_EN = "A damp air lingers and a scent remains. Draw three lines. Place two circles."


def _expand_case(name, ddl, **overrides):
    """One expansion case with every argument of expand_intermediate_ddl written out."""
    kwargs = {
        "ddl": ddl,
        "lang": "ja",
        "context_text": ddl,
        "composition_seed": None,
        "enable_plugins": False,
        "plugin_instructions_present": False,
        "focus": None,
        "variation_amplitude": None,
        "variation_seed": None,
    }
    kwargs.update(overrides)
    report: dict = {}
    output = expand_intermediate_ddl(**kwargs, variation_report=report)
    return {
        "case": name,
        "input": dict(kwargs),
        "output": output,
        "bytes": len(output.encode("utf-8")),
        "variation_report": report,
    }


def ddl_expand_fixtures() -> None:
    """Stage 1.5 expansion: the layer Android has not ported yet.

    Fifteen of these cases use the same inputs as `a_expand/` in the server's own
    corpus (`server/reference/ddl-engine-1/`), so the two agree where they overlap
    and a divergence points at one side. The rest exist to discriminate: variation
    seeds above 2**63 (a Long prints negative in Kotlin and every seeded key
    shifts), a focus that has to resolve, `composition_seed` which only touches the
    context, and `variation_report`, which is an output the DDL text does not show.
    """
    cases = [
        _expand_case("A-base-ja", DDL_EXPAND_JA),
        _expand_case("A-base-en", DDL_EXPAND_EN, lang="en", context_text=DDL_EXPAND_EN),
        _expand_case("A-variation-amplitude-only", DDL_EXPAND_JA, variation_amplitude="large"),
        _expand_case("A-variation-seed-only", DDL_EXPAND_JA, variation_seed=12345),
        _expand_case("A-plugin-enabled", DDL_EXPAND_PLUGIN, context_text=DDL_EXPAND_PLUGIN, enable_plugins=True),
        _expand_case("A-plugin-disabled", DDL_EXPAND_PLUGIN, context_text=DDL_EXPAND_PLUGIN, enable_plugins=False),
    ]
    for amplitude in ("small", "medium", "large"):
        for seed in (1, 12345):
            cases.append(_expand_case(
                f"A-variation-{amplitude}-{seed}", DDL_EXPAND_JA,
                variation_amplitude=amplitude, variation_seed=seed,
            ))
    # Beyond the server corpus: the discriminators this port needs.
    for seed in (2 ** 63 + 1, 2 ** 64 - 1):
        cases.append(_expand_case(
            f"B-variation-seed-{seed}", DDL_EXPAND_JA,
            variation_amplitude="medium", variation_seed=seed,
        ))
    cases.append(_expand_case(
        "B-variation-en", DDL_EXPAND_EN, lang="en", context_text=DDL_EXPAND_EN,
        variation_amplitude="large", variation_seed=12345,
    ))
    cases.append(_expand_case(
        "B-scatter-varied", DDL_EXPAND_SCATTER, context_text=DDL_EXPAND_SCATTER,
        variation_amplitude="large", variation_seed=12345,
    ))
    # Four real focus ids give four distinct expansions; an unknown one has to fall
    # back to the same output as no focus at all, which is a spec, not an accident.
    for focus in ("upper_left", "lower_right", "right_half", "upper_edge", "not-a-focus"):
        cases.append(_expand_case(
            f"B-focus-{focus}", DDL_EXPAND_JA,
            focus=focus, variation_amplitude="medium", variation_seed=12345,
        ))
    # Inputs whose context used to drive the candidate pool. The pool went away
    # with the staffage level (v2.11.0), so what these now pin is that a rich
    # context adds nothing of its own -- the expansion is the focus reframing.
    cases.append(_expand_case(
        "B-sensory", DDL_EXPAND_SENSORY, context_text=DDL_EXPAND_SENSORY))
    cases.append(_expand_case(
        "B-music", DDL_EXPAND_MUSIC, context_text=DDL_EXPAND_MUSIC))
    cases.append(_expand_case(
        "B-sensory-en", DDL_EXPAND_SENSORY_EN, lang="en",
        context_text=DDL_EXPAND_SENSORY_EN))
    for composition_seed in (0, 12345, 2 ** 63 + 1):
        cases.append(_expand_case(f"B-vary-seed-{composition_seed}", DDL_EXPAND_JA, composition_seed=composition_seed))
    cases.append(_expand_case("B-plugin-instructions-present", DDL_EXPAND_PLUGIN,
                              context_text=DDL_EXPAND_PLUGIN, enable_plugins=True,
                              plugin_instructions_present=True))
    cases.append(_expand_case("B-context-differs", DDL_EXPAND_JA, context_text=DDL_EXPAND_SCATTER))
    cases.append(_expand_case("B-context-none", DDL_EXPAND_JA, context_text=None))

    from inku_server.plugins import DOCUMENT_PLUGIN_MANAGER
    out = {
        "note": (
            "Expansion is deterministic and calls no LLM. Fifteen A-* cases share their "
            "inputs with server/reference/ddl-engine-1/a_expand/, so those outputs must "
            "match both corpora."
        ),
        "plugin_vocabulary_ja": list(DOCUMENT_PLUGIN_MANAGER.prompt_vocabulary("ja")),
        "plugin_vocabulary_en": list(DOCUMENT_PLUGIN_MANAGER.prompt_vocabulary("en")),
        "variation_amplitudes": list(VARIATION_AMPLITUDES),
        "focus_ids": sorted(FOCUS_IDS),
        "cases": cases,
    }
    out_path("ddl_expand.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))


def prompt_fixtures() -> None:
    """Android が抱えるプロンプトの複製が server から離れたことを検出させる。

    Android は端末内で全パイプラインを回すので Stage 1 / Stage 2 のプロンプトを
    Kotlin の定数として複製している。CI は Android を回さないため、この複製が
    黙って古くなる。指紋を焼いて Kotlin 側で突き合わせる。

    LiteRT 専用の短縮プロンプト (`*_LITERT`) はここに含めない。端末内の小さな
    モデル向けに意図して別物にしてあり、server に対応物が無い。
    """
    from inku_server.composer import SYSTEM_PROMPT as STAGE2_JA
    from inku_server.composer import SYSTEM_PROMPT_EN as STAGE2_EN
    from inku_server.interpreter import SYSTEM_PROMPT_PREFIX as STAGE1_JA
    from inku_server.interpreter import SYSTEM_PROMPT_PREFIX_EN as STAGE1_EN

    mirrored = {
        "STAGE1_PROMPT_PREFIX_JA": STAGE1_JA,
        "STAGE1_PROMPT_PREFIX_EN": STAGE1_EN,
        "STAGE2_SYSTEM_PROMPT_JA": STAGE2_JA,
        "STAGE2_SYSTEM_PROMPT_EN": STAGE2_EN,
    }
    out = {
        "note": (
            "Kotlin の同名定数は server のこれと一字一句同じであること。"
            "LiteRT 用の短縮プロンプトは対象外。"
        ),
        "prompts": {
            name: {
                "bytes": len(text.encode("utf-8")),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
            for name, text in mirrored.items()
        },
    }
    out_path("prompts.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))


def count_preservation_fixtures() -> None:
    """明示された個数が密度ガバナーと予算を素通りすることの期待値。

    Android は `_with_context_density_governor` と 2 つの予算関数を
    `LocalFallbackPipeline` へ移植しているが、v2.7.6 の「明示個数は免除する」が
    入っていない。server 側の 50 ケースをそのまま渡し、**Android が移植した
    3 関数だけ**を通した結果を焼く。coerce 全体ではないので apples-to-apples。
    """
    from inku_server.coerce.compose import _with_context_density_governor
    from inku_server.coerce.normalize import (
        _with_per_instruction_density_budget,
        _with_total_density_budget,
    )

    source = json.loads(
        (
            pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "count_preservation_cases.json"
        ).read_text(encoding="utf-8")
    )
    cases = []
    for case in source["cases"]:
        score = Score.model_validate(case["score"])
        instructions = _with_context_density_governor(
            list(score.instructions),
            ddl=case["ddl"],
            background=score.background,
        )
        instructions = _with_per_instruction_density_budget(instructions)
        instructions = _with_total_density_budget(instructions)
        counts = [
            (ins.arrangement.count if ins.arrangement is not None else 1)
            for ins in instructions
        ]
        cases.append(
            {
                "id": case["id"],
                "lang": case["lang"],
                "kind": case["kind"],
                "ddl": case["ddl"],
                "requested": case["requested"],
                "score": case["score"],
                "expected_counts": counts,
                "requested_survives": case["requested"] in counts,
            }
        )
    literal = [case for case in cases if case["kind"] == "literal"]
    represented = [case for case in cases if case["kind"] == "represented"]
    out = {
        "note": (
            "Android が移植した 3 関数 (withContextDensityGovernor, "
            "withPerInstructionDensityBudget, withTotalDensityBudget) を "
            "この順で通した結果。expected_counts と完全一致すること。"
            "literal は要求値がそのまま残り、represented は仕様の帯 80-120 へ代表化される。"
            "**両方が要る** — 全部を素通しにすると represented が壊れ、"
            "全部を代表化すると literal が壊れる。"
        ),
        "representative_count": source["representative_count"],
        "requested_counts": source["requested_counts"],
        "literal_total": len(literal),
        "literal_requested_survives": sum(1 for case in literal if case["requested_survives"]),
        "represented_total": len(represented),
        "represented_counts": sorted({count for case in represented for count in case["expected_counts"]}),
        "total": len(cases),
        "cases": cases,
    }
    out_path("count_preservation.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))


COLOR_ASSIGNMENT_SEEDS = (RENDER_SEED, 999)

# Hints chosen for what they discriminate, not for coverage of the word lists.
# engine 17 matches ASCII tokens as whole words, so a token buried inside a
# longer word no longer fires; before, `"ink" in normalized` did. The Japanese
# tokens are still matched as substrings, because the text has no word breaks.
HINT_CASES: tuple[tuple[str, str, str], ...] = (
    # (catalog_id, color written in the Score, color_hint)
    ("ink_season", "black", "brown"),            # brown alone -> the orange slot
    ("ink_season", "black", "brown and blue"),   # brown is discarded, blue wins
    ("ink_season", "black", "赤と青"),            # priority order: red before blue
    ("ink_season", "black", "青と赤"),            # word order must not matter
    # `red` is the written color in this pair so the hint changes the answer:
    # with `black` both rows land on #111111 and the pair proves nothing.
    ("ink_season", "red", "ink"),                # ASCII token as its own word
    ("ink_season", "red", "inkstone"),           # embedded: no longer a match
    ("ink_season", "black", "sky blue"),         # multi-word hint
    ("ink_season", "black", "blueprint"),        # embedded: no longer a match
    ("cool_material", "red", "moss"),            # no hue in the hint -> fallback
    ("cool_material", "red", ""),                # empty hint -> fallback
    ("default", "black", "purple"),              # empty band reached through a hint
    ("sea_stone", "white", "yellow"),            # band with three, through a hint
    ("dye_earth", "black", "紫"),                # Japanese token, substring match
    ("vivid_material", "black", "gold"),         # yellow through a synonym
    ("open_air_light", "black", "terracotta"),   # orange through a synonym
)


def color_assignment_fixtures() -> None:
    """The palette assignment engine 17 put between the catalog and the ink.

    The SVG corpus cannot carry this on its own: `_work_color_assignment` only
    does anything when the color map holds `palette:` keys, and every case in
    SCORES renders through the bare default map. So the table is pinned here
    directly, together with the OKLCH conversion and the band split it rests on,
    so that a wrong band boundary is a separate failure from a wrong assignment.
    """
    catalog_ids = color_catalog_ids()
    palette_bands: dict[str, dict] = {}
    for catalog_id in catalog_ids:
        cmap = render_color_map_for_catalog(catalog_id)
        achromatic: list[list] = []
        chromatic: dict[str, list[str]] = {c: [] for c in renderer._CHROMATIC_COLORS}
        seen: set[str] = set()
        for key, hex_value in cmap.items():
            if not key.startswith("palette:") or hex_value in seen:
                continue
            oklch = renderer._oklch_from_hex(hex_value)
            if oklch is None:
                continue
            seen.add(hex_value)
            lightness, chroma, hue = oklch
            if chroma < renderer._OKLCH_CHROMA_FLOOR:
                achromatic.append([round(lightness, 12), hex_value])
            else:
                chromatic[renderer._chromatic_band(hue)].append(hex_value)
        palette_bands[catalog_id] = {
            "achromatic": sorted(achromatic),
            "chromatic": {band: sorted(v) for band, v in chromatic.items()},
        }

    assignment: dict[str, dict[str, dict[str, str]]] = {}
    for catalog_id in catalog_ids:
        cmap = render_color_map_for_catalog(catalog_id)
        assignment[catalog_id] = {
            str(seed): renderer._work_color_assignment(cmap, seed, catalog_id)
            for seed in COLOR_ASSIGNMENT_SEEDS
        }

    # The seed only reaches a band that holds more than one color. Naming the
    # pairs that move keeps "the seed is wired in" from being provable by a port
    # that ignores the seed entirely — most of the table is the same either way.
    first, second = (str(s) for s in COLOR_ASSIGNMENT_SEEDS[:2])
    seed_sensitive = sorted(
        f"{catalog_id}.{color}"
        for catalog_id in catalog_ids
        for color in renderer._ACHROMATIC_COLORS + renderer._CHROMATIC_COLORS
        if assignment[catalog_id][first][color] != assignment[catalog_id][second][color]
    )

    hints = []
    for catalog_id, color, hint in HINT_CASES:
        cmap = render_color_map_for_catalog(catalog_id)
        work = renderer._work_color_assignment(cmap, RENDER_SEED, catalog_id)
        hints.append(
            {
                "catalog_id": catalog_id,
                "render_seed": RENDER_SEED,
                "color": color,
                "color_hint": hint,
                "hues": sorted(renderer._hint_hues(hint)),
                "expected": renderer._resolve_color(
                    color, hint or None, cmap, work_assignment=work
                ),
            }
        )

    oklch = {}
    for catalog_id in catalog_ids:
        for hex_value in render_color_map_for_catalog(catalog_id).values():
            if hex_value in oklch:
                continue
            lightness, chroma, hue = renderer._oklch_from_hex(hex_value)
            oklch[hex_value] = {
                "lightness": round(lightness, 12),
                "chroma": round(chroma, 12),
                "hue": round(hue, 12),
            }
    for hex_value in renderer.COLOR_MAP.values():
        if hex_value not in oklch:
            lightness, chroma, hue = renderer._oklch_from_hex(hex_value)
            oklch[hex_value] = {
                "lightness": round(lightness, 12),
                "chroma": round(chroma, 12),
                "hue": round(hue, 12),
            }

    out = {
        "note": (
            "engine 17: the catalog palette reaches the drawing. `assignment` is "
            "the whole answer; `palette_bands` and `oklch` are the two steps under "
            "it, pinned separately so a wrong band boundary does not read as a "
            "wrong assignment."
        ),
        "constants": {
            "default_color_map": dict(renderer.COLOR_MAP),
            "achromatic_colors": list(renderer._ACHROMATIC_COLORS),
            "chromatic_colors": list(renderer._CHROMATIC_COLORS),
            "chromatic_bands": {k: list(v) for k, v in renderer._CHROMATIC_BANDS.items()},
            "chromatic_band_centers": dict(renderer._CHROMATIC_BAND_CENTERS),
            "oklch_chroma_floor": renderer._OKLCH_CHROMA_FLOOR,
            "hint_hue_priority": list(renderer._HINT_HUE_PRIORITY),
            "work_color_seed_fields": list(renderer._WORK_COLOR_SEED_FIELDS),
            "default_catalog_id": DEFAULT_COLOR_CATALOG_ID,
        },
        "oklch": dict(sorted(oklch.items())),
        "palette_bands": palette_bands,
        "assignment": assignment,
        "seeds": [str(s) for s in COLOR_ASSIGNMENT_SEEDS],
        "seed_sensitive": seed_sensitive,
        "hint_resolution": hints,
    }
    out_path("renderer_color_assignment.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2)
    )


def score_schema_contract_fixture() -> None:
    """The parts of the Score schema the port must not diverge from.

    The port declares a deliberately smaller schema than the server ([I-008]):
    it must not offer Stage 2 a ground it cannot draw. So this pins the two
    things that are shared rather than the whole document — the color
    vocabulary, and the order the fields are declared in, which the tool schema
    carries to the model and `model_dump_json` carries to the seed.
    """
    schema = Score.model_json_schema()
    instruction = schema["$defs"]["Instruction"]["properties"]
    out = {
        "note": (
            "The port's schema is a subset by design. `instruction_property_order` "
            "is the server's order; the port's own fields must appear in the same "
            "relative order, which is what puts `surface` at the end, with "
            "`thinness` immediately before it."
        ),
        "instruction_property_order": list(instruction),
        "dump_property_order": list(
            json.loads(
                Instruction.model_validate({"primitive": "line"}).model_dump_json(
                    by_alias=True
                )
            )
        ),
        "enums": {
            "color": instruction["color"]["enum"],
            "background": schema["properties"]["background"]["enum"],
            "color_cycle": schema["$defs"]["Arrangement"]["properties"]["color_cycle"][
                "items"
            ]["enum"],
        },
        "descriptions": {
            "note": instruction["note"]["description"],
            "color": instruction["color"]["description"],
        },
    }
    out_path("score_schema_contract.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2)
    )


# The anchors group G is built on. "edge" is the one under which the frame
# correction fires; "center" is the control, because a group whose centroid
# already sits on the anchor has nothing to move.
G_ANCHORS: dict[str, list[float]] = {
    "center": [0.5, 0.5], "corner": [0.2, 0.2], "edge": [0.85, 0.85],
}
BASE_ARRANGEMENT: dict = {
    "count": 60, "layout": "scatter", "rows": None, "cols": None, "jitter": 0.12,
    "path": "none", "color_cycle": [], "margin": 0.1, "center": None,
    "radius": None, "density": "none", "cluster_count": None, "fade": "none",
    "preserve_space": False, "rhythm_spacing": "none",
}


def arrangement_cases() -> dict[str, dict]:
    """The cases of the server's group G, plus one that states a region.

    These mirror `gen_render_reference.py` case for case, so the two corpora
    move together; the extra `G-grid-region-edge` exists because engine 20's one
    carve-out (a grid that tiles a stated region does NOT go through the second
    stage) has no case in group G, and a port that runs every layout through the
    fit would stay green without it.

    Every case here was a `circle` until engine 26, which is the one shape the
    per-member angle leaves alone -- so the corpus could not see engines 23, 24
    or 26 at all, not for want of a mechanism but for want of a case. The eight
    borrowed from group G at the bottom are that hole, one per mechanism.
    """
    cases: dict[str, dict] = {}

    def g(case_id: str, anchor: str, **changes) -> None:
        arrangement = copy.deepcopy(BASE_ARRANGEMENT)
        arrangement.update(changes)
        cases[case_id] = {
            "primitive": "circle", "weight": "pen",
            "center": list(G_ANCHORS[anchor]), "radius": 0.03,
            "arrangement": arrangement,
        }

    def g_shape(case_id: str, primitive: str, geometry: dict, **changes) -> None:
        """A group of something other than a circle, on the `edge` anchor.

        The anchor is in the coordinates rather than in an argument because
        `gen_render_reference.py` writes these the same way: an arc states a
        centre and a radius, a square a corner and a size, and the two cannot
        share one anchor parameter. All of them sit where `G_ANCHORS["edge"]`
        does, which is the anchor under which the frame correction fires.
        """
        arrangement = copy.deepcopy(BASE_ARRANGEMENT)
        arrangement.update(changes)
        cases[case_id] = {
            "primitive": primitive, "weight": "pen",
            "arrangement": arrangement, **geometry,
        }

    for anchor in G_ANCHORS:
        g(f"G-scatter-{anchor}", anchor)
        g(f"G-scatter-small-{anchor}", anchor, count=5)
    for anchor in G_ANCHORS:
        g(f"G-cluster-{anchor}", anchor, cluster_count=3)
    g("G-cluster-preserve-edge", "edge", cluster_count=3, preserve_space=True)
    for path in ("wave", "diagonal", "top_to_bottom"):
        g(f"G-path-{path}-edge", "edge", layout="vertical", path=path)
    g("G-path-wave-center", "center", layout="vertical", path="wave")
    g("G-path-wave-corner", "corner", layout="vertical", path="wave")
    g("G-path-hwave-edge", "edge", layout="horizontal", path="wave")
    for anchor in G_ANCHORS:
        g(f"G-vertical-nopath-{anchor}", anchor, layout="vertical")
        g(f"G-horizontal-nopath-{anchor}", anchor, layout="horizontal")
    for anchor in G_ANCHORS:
        g(f"G-radial-nocenter-{anchor}", anchor, layout="radial", count=12)
    g("G-radial-center-edge", "edge", layout="radial", count=12, center=[0.3, 0.3])
    # A stated radius of zero is falsy, and the server reads falsy as unstated:
    # `r = arr.radius if arr.radius else 0.3`. A port that fetches the radius with
    # a default instead keeps the zero and collapses the whole ring onto its
    # centre. No other case states a radius at all, so without this one the two
    # readings are indistinguishable and every fixture stays green either way.
    g("G-radial-zero-radius-edge", "edge", layout="radial", count=12, radius=0)
    for anchor in G_ANCHORS:
        g(f"G-grid-{anchor}", anchor, layout="grid", count=16, rows=4, cols=4)
    g("G-scatter-dense-edge", "edge", density="high")
    g("G-scatter-fade-edge", "edge", fade="outward")
    g("G-scatter-rhythm-edge", "edge", rhythm_spacing="loose")

    g("G-grid-region-edge", "edge", layout="grid", count=16, rows=4, cols=4)
    cases["G-grid-region-edge"]["at"] = {"region": [0.55, 0.05, 0.95, 0.45]}

    # engine 26: the per-member angle. `arc` is the largest target there is in
    # production (377 groups against `ellipse`'s 373) and `cloudform` (64) the
    # next the corpus had never carried; both are shapes the rule turns.
    g_shape("G-angle-arc-edge", "arc",
            {"center": [0.85, 0.85], "radius": 0.06,
             "angle_start": 15.0, "angle_end": 285.0}, count=12)
    g_shape("G-angle-cloudform-edge", "cloudform",
            {"center": [0.85, 0.85], "size": [0.10, 0.06]}, count=12)
    # The pair that separates `rotation is not None` from `if ins.rotation:`.
    # A group that names its own angle is left alone, and `rotation: 0` names
    # one -- it says "do not tilt these", which is an answer and not a missing
    # one. 141 groups in production give exactly that answer, and a truthy test
    # would turn every one of them. Both of these must come out unturned; only
    # the zero one changes under the wrong reading, which is why the thirty is
    # here beside it rather than alone.
    g_shape("G-angle-stated-zero-edge", "ellipse",
            {"center": [0.85, 0.85], "size": [0.10, 0.06], "rotation": 0.0},
            count=12)
    g_shape("G-angle-stated-30-edge", "ellipse",
            {"center": [0.85, 0.85], "size": [0.10, 0.06], "rotation": 30.0},
            count=12)
    # engine 25: the per-member size on something other than a circle. A circle
    # reaches only `radius x k`; a square reaches the bbox rule, where growing
    # `size` has to pull `position` back by half the growth to leave the anchor
    # where it was.
    g_shape("G-size-square-edge", "square",
            {"position": [0.81, 0.81], "size": [0.08, 0.08]}, count=12)
    # engine 24: the fade reaches every member. `G-scatter-fade-edge` above is
    # the only fading route the corpus walked, and it is one of the thirty that
    # are never drawn -- the ceiling lands on `color_hint` and `anchors` cannot
    # see it. These two are drawn. `radial` is the ring whose own centre the
    # ramp has to be measured from, and `count=2` is the shortest group that
    # fades at all.
    g("G-fade-radial-edge", "edge", fade="outward", layout="radial", count=12)
    g("G-fade-count2-edge", "edge", fade="outward", count=2)
    # engine 23: the placement seed. This case is identical to `G-scatter-edge`
    # in every field; what makes it a different drawing is the composition seed
    # handed to `render()` beside the score, which is why the seed lives in
    # `ARRANGEMENT_COMPOSITION_SEEDS` and not in the instruction.
    g("G-composition-scatter-edge", "edge")
    return cases


# engine 23 split the placement seed off the performance seed. Nothing in an
# `Instruction` carries it -- it arrives as an argument to `render()` -- so the
# cases that state one are listed here beside the case ids, the way
# `gen_render_reference.py` keeps it beside its own case records.
#
# The value matches the server's `G_COMPOSITION_SEED` so the two corpora can be
# read against each other.
G_COMPOSITION_SEED = 777
# A performance seed that is neither of the two above, for the half of the
# claim that says the placement does NOT follow it.
OTHER_PERFORMANCE_SEED = 54321
ARRANGEMENT_COMPOSITION_SEEDS: dict[str, int] = {
    "G-composition-scatter-edge": G_COMPOSITION_SEED,
}


def arrangement_fixtures() -> None:
    """Where each mark of an expanded group lands (engine 20 and 21).

    `render()` resolves the performance score and then hands `render_seed` to
    `_expand_arrangement` a second time, so the expansion is seeded; a port that
    calls its own expansion without the seed produces a different scatter for 22
    of these 33 cases while every other fixture here stays green.

    The comparison surface is the anchor of each expanded mark -- for a circle
    that is its `center` -- because that is the quantity both engines move.
    Compare it EXACTLY, not within a tolerance: two cases
    (`G-vertical-nopath-center`, `G-horizontal-nopath-center`) are moved by
    nothing but engine 21's nine-decimal quantisation, 4.9e-10, and a tolerance
    of 1e-6 lets a port skip engine 21 and stay green on all 33.

    The placement seed is the composition seed's since engine 23, and the two
    were the same number here until now -- both `RENDER_SEED` -- so no fixture
    in this corpus could tell which of them the expansion was reading. The
    `composition_seed_split` block at the bottom is the only place they differ.
    """
    out: dict = {
        "note": "anchors of every expanded mark; compare exactly, no tolerance",
        "render_seed": RENDER_SEED,
        "arrangement_quantum": renderer.ARRANGEMENT_QUANTUM,
        "cases": [],
    }
    for case_id, raw in arrangement_cases().items():
        ins = Instruction.model_validate(raw)
        composition_seed = ARRANGEMENT_COMPOSITION_SEEDS.get(case_id)
        # `renderer.render` reads this with `is None` and never with `or`,
        # because 0 is a seed a caller can legitimately state (renderer.py:3354).
        placement_seed = (
            composition_seed if composition_seed is not None else RENDER_SEED
        )
        expanded = renderer._expand_arrangement(
            ins, placement_seed, None, performance_seed=RENDER_SEED
        )
        case: dict = {
            "case_id": case_id,
            "instruction": ins.model_dump(mode="json"),
            "count": len(expanded),
            "anchors": [list(renderer._anchor(item)) for item in expanded],
        }
        if composition_seed is not None:
            case["composition_seed"] = composition_seed
        out["cases"].append(case)

    # engine 23, stated as the difference it makes rather than as one more row.
    # One instruction, three expansions: the placement moves when the seed that
    # feeds the placement moves, and stays put when the other one does. A port
    # that reads the layout off the performance seed passes the third and fails
    # the second; a port that reads the sizes off the placement seed fails
    # neither, which is why the anchors and not the geometry are compared -- the
    # anchors are what the split is about.
    split_id = "G-composition-scatter-edge"
    split_ins = Instruction.model_validate(arrangement_cases()[split_id])

    def anchors(placement_seed: int, performance_seed: int) -> list[list[float]]:
        return [
            list(renderer._anchor(item))
            for item in renderer._expand_arrangement(
                split_ins, placement_seed, None, performance_seed=performance_seed
            )
        ]

    out["composition_seed_split"] = {
        "note": (
            "placement follows the composition seed and nothing else does; "
            "compare exactly"
        ),
        "case_id": split_id,
        "instruction": split_ins.model_dump(mode="json"),
        "render_seed": RENDER_SEED,
        "composition_seed": G_COMPOSITION_SEED,
        "other_performance_seed": OTHER_PERFORMANCE_SEED,
        "anchors_no_composition_seed": anchors(RENDER_SEED, RENDER_SEED),
        "anchors_with_composition_seed": anchors(G_COMPOSITION_SEED, RENDER_SEED),
        "anchors_other_performance_seed": anchors(RENDER_SEED, OTHER_PERFORMANCE_SEED),
    }
    out_path("renderer_arrangement.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2)
    )


# Four of the cases above, drawn. The JSON fixture pins where the marks land;
# these pin that the drawing follows -- a port can place the group correctly and
# still lose it downstream, and the walk over `svg_index.json` reaches these the
# day they exist. One per mechanism: the frame correction, the radial centre,
# the grid carve-out, and a cluster (the second largest route in production).
ARRANGEMENT_SVG_CASES: tuple[tuple[str, str], ...] = (
        ("39_arrangement_scatter_small_edge", "G-scatter-small-edge"),
        ("40_arrangement_radial_nocenter_corner", "G-radial-nocenter-corner"),
        ("41_arrangement_grid_region_edge", "G-grid-region-edge"),
        ("42_arrangement_cluster_center", "G-cluster-center"),
        # engines 23, 24 and 26 reach no drawing in this corpus without these.
        # 43 and 44 are the two shapes the per-member angle turns; 45 and 46 the
        # pair that tells `is not None` from a truthy test, and they must come
        # out identical to a run with the rule switched off. 47 is the per-member
        # size away from a circle, 48 and 49 the fade that has to reach every
        # member, and 50 the placement seed.
        ("43_arrangement_angle_arc_edge", "G-angle-arc-edge"),
        ("44_arrangement_angle_cloudform_edge", "G-angle-cloudform-edge"),
        ("45_arrangement_angle_stated_zero_edge", "G-angle-stated-zero-edge"),
        ("46_arrangement_angle_stated_30_edge", "G-angle-stated-30-edge"),
        ("47_arrangement_size_square_edge", "G-size-square-edge"),
        ("48_arrangement_fade_radial_edge", "G-fade-radial-edge"),
        ("49_arrangement_fade_count2_edge", "G-fade-count2-edge"),
        ("50_arrangement_composition_scatter_edge", "G-composition-scatter-edge"),
        # The positive half of engine 24, and the reason 48 and 49 cannot carry
        # it: those two are the groups the fade must leave alone -- a ring is
        # equidistant from its own centre and so is a pair, so both come out
        # with no ceiling at all, and a port that never fades matches them.
        # `G-scatter-fade-edge` is the case engine 24 actually moved: it is the
        # one of the server's 535 frozen cases whose drawing changed
        # (`test_one_case_of_the_frozen_corpus_moved`). It has been in this
        # corpus since engine 20, on the side that is never drawn.
        ("51_arrangement_scatter_fade_edge", "G-scatter-fade-edge"),
)
ARRANGEMENT_SCORES: dict[str, dict] = {
    name: {"instructions": [arrangement_cases()[case_id]]}
    for name, case_id in ARRANGEMENT_SVG_CASES
}
ARRANGEMENT_SVG_NAME_BY_CASE: dict[str, str] = {
    case_id: name for name, case_id in ARRANGEMENT_SVG_CASES
}

# The composition seed travels beside the score rather than inside it, so the
# one drawing that states one needs it written down here as well -- and read
# back out of `svg_index.json` by whatever re-renders these.
SVG_COMPOSITION_SEEDS: dict[str, int] = {
    "50_arrangement_composition_scatter_edge": G_COMPOSITION_SEED,
}


# --- can these drawings fail? ------------------------------------------------
# Ported one for one from `gen_render_reference.py`, which has carried these
# since engine 24. A case that draws the same picture whether the mechanism runs
# or not records that nothing broke and nothing else, and this corpus has just
# been shown to be able to hold such a case for five engine versions without
# anyone noticing. The checks run at bake time, on the bake's own call, so a
# case that cannot fail cannot be written.
#
# What each mechanism is withheld BY is the whole of the check's strength. The
# size and angle guards replace the engine function itself, so they separate
# engine 26 from engine 24. The fade guard drops the declaration instead, which
# is the shape the server's has -- and it is weaker: engine 23 answered `fade`
# with one constant for the whole group, so a port that fades a group flatly
# still passes it. `_assert_fade_reaches_every_member` below is the other half,
# and it asks the corpus a question rather than changing what the engine does.
ANGLE_CASES = ("G-angle-arc-edge", "G-angle-cloudform-edge")
STATED_ANGLE_CASES = ("G-angle-stated-zero-edge", "G-angle-stated-30-edge")
# Every drawn group the size rule reaches. `G-grid-region-edge` is not here:
# a grid is the tiling whose point is that the cells match, and it is excluded.
SIZE_CASES = (
    "G-scatter-small-edge", "G-radial-nocenter-corner", "G-cluster-center",
    "G-size-square-edge",
)
FADE_CASES = ("G-fade-radial-edge", "G-fade-count2-edge", "G-scatter-fade-edge")
# The two that must come out with no ceiling at all, and stay that way.
DEGENERATE_FADE_CASES = ("G-fade-radial-edge", "G-fade-count2-edge")


def _render_arrangement_case(raw: dict, composition_seed: int | None = None) -> str:
    """Draw one group exactly the way `svg_fixtures` draws it."""
    return renderer.render(
        Score.model_validate({"instructions": [raw]}),
        color_map=render_color_map_for_catalog(DEFAULT_COLOR_CATALOG_ID),
        catalog_id=DEFAULT_COLOR_CATALOG_ID,
        render_seed=RENDER_SEED,
        composition_seed=composition_seed,
        svg_profile=SVG_PROFILE,
        wild=False,
    )


@contextlib.contextmanager
def _withheld(name: str) -> Iterator[None]:
    """Draw as the previous engine did, by making one rule a pass-through."""
    original = getattr(renderer, name)
    setattr(renderer, name, lambda items, arr, member_seed: items)
    try:
        yield
    finally:
        setattr(renderer, name, original)


def _assert_size_cases_discriminate(cases: dict[str, dict]) -> None:
    """Withholding the per-member size has to change every drawn size case."""
    for case_id in SIZE_CASES:
        drawn = _render_arrangement_case(cases[case_id])
        with _withheld("_apply_member_sizes"):
            withheld = _render_arrangement_case(cases[case_id])
        if drawn == withheld:
            raise AssertionError(f"{case_id}: the drawing does not read the member size")


def _assert_angle_cases_discriminate(cases: dict[str, dict]) -> None:
    """The turning pair has to move when the angle is withheld; the stating pair
    has to stay put -- and still has to read `rotation`, or it records nothing.

    Dropping the stated angle is what separates `rotation: 0` from an unstated
    angle: neither draws a `rotate()` of its own, so the exclusion is the only
    place the difference shows.
    """
    primitives = {cases[case_id]["primitive"] for case_id in ANGLE_CASES}
    if primitives != {"arc", "cloudform"}:
        raise AssertionError(
            f"the turning pair does not reach the missing shapes: {sorted(primitives)}"
        )
    for case_id in ANGLE_CASES:
        drawn = _render_arrangement_case(cases[case_id])
        with _withheld("_apply_member_rotations"):
            if _render_arrangement_case(cases[case_id]) == drawn:
                raise AssertionError(f"{case_id}: the drawing does not read the member angle")
    for case_id in STATED_ANGLE_CASES:
        drawn = _render_arrangement_case(cases[case_id])
        with _withheld("_apply_member_rotations"):
            if _render_arrangement_case(cases[case_id]) != drawn:
                raise AssertionError(f"{case_id}: a group that states its angle was turned")
        dropped = copy.deepcopy(cases[case_id])
        dropped["rotation"] = None
        if _render_arrangement_case(dropped) == drawn:
            raise AssertionError(f"{case_id}: the drawing does not read `rotation`")


def _assert_fade_cases_discriminate(cases: dict[str, dict]) -> None:
    """Every drawn fading case has to notice `fade` before it is written."""
    for case_id in FADE_CASES:
        stated = cases[case_id]
        withheld = copy.deepcopy(stated)
        withheld["arrangement"]["fade"] = "none"
        if _render_arrangement_case(stated) == _render_arrangement_case(withheld):
            raise AssertionError(f"{case_id}: the drawing does not read `fade`")


def _assert_fade_reaches_every_member(cases: dict[str, dict]) -> None:
    """At least one drawn fading group carries more than one ceiling.

    The check above cannot ask this: dropping the declaration takes the whole
    group's fade away, and engine 23 already drew that difference with a single
    constant. So the corpus is asked directly -- some drawn group has to hold
    distinct per-member levels, or `fade` is pinned only where it is absent.

    And the two degenerate groups have to hold none: a ring is equidistant from
    its own centre and so is a pair, and ranking them would draw a gradient
    nobody stated.
    """
    def levels(case_id: str) -> list[float | None]:
        ins = Instruction.model_validate(cases[case_id])
        return [
            renderer._fade_level_from_hint(item.color_hint)
            for item in renderer._expand_arrangement(
                ins, RENDER_SEED, None, performance_seed=RENDER_SEED
            )
        ]

    ramped = [
        case_id for case_id in FADE_CASES
        if len({level for level in levels(case_id) if level is not None}) > 1
    ]
    if not ramped:
        raise AssertionError(
            "no drawn fading group carries a per-member ceiling; the corpus "
            "pins `fade` only where the rule declines to fire"
        )
    for case_id in DEGENERATE_FADE_CASES:
        if any(level is not None for level in levels(case_id)):
            raise AssertionError(f"{case_id}: a group that cannot fade was ramped")


def assert_arrangement_cases_discriminate() -> None:
    cases = arrangement_cases()
    drawn = set(ARRANGEMENT_SVG_NAME_BY_CASE)
    for case_id in (*SIZE_CASES, *ANGLE_CASES, *STATED_ANGLE_CASES, *FADE_CASES):
        if case_id not in drawn:
            raise AssertionError(f"{case_id} is checked here but never drawn")
    _assert_size_cases_discriminate(cases)
    _assert_angle_cases_discriminate(cases)
    _assert_fade_cases_discriminate(cases)
    _assert_fade_reaches_every_member(cases)


def coerce_governor_fixtures() -> None:
    """What coerce decides about the background, and how it tempers a large shape.

    Both mechanisms live in `LocalFallbackPipeline` on the port, and neither has
    a baked expectation: the governor cases below are the only ones that tell a
    marker list that is one word short from one that is complete, and the two
    temperings the port never received change a shape's size without changing
    the number of instructions, so a count-based comparison stays green.

    The DDLs are chosen to REACH the branch. The governor only washes to white
    when the density governor or a presence fires, so every dark case here
    carries a density marker; without one the governor returns its input and the
    case tells nothing apart.
    """
    from inku_server.coerce import compose as _c

    background_cases = [
        ("clause-black", "背景を黒で塗りつぶす。細い線を10本散らす。", "black"),
        ("bare-word-black", "背景の前に円を描く。細い線を10本散らす。", "black"),
        ("no-marker-black", "細い線を10本散らす。", "black"),
        ("night-black", "夜の細い線を10本散らす。", "black"),
        ("dawn-black", "夜明けの細い線を10本散らす。", "black"),
        ("dark-field-black", "a dark field, ten thin lines scattered", "black"),
        ("night-sky-black", "night sky, ten thin lines scattered", "black"),
        ("fill-background-en", "fill the background with black. scatter ten thin lines.", "black"),
        ("large-surface-red", "大きな布を広げる。細い線を5本引く。", "red"),
        ("white-stays", "細い線を10本散らす。", "white"),
        ("blue-no-marker", "静かな細い線を1本引く。", "blue"),
        ("green-ground-color", "地色を緑にする。静かな線を1本引く。", "green"),
    ]
    temper_cases = [
        ("square-filled-plain", "四角を描く", {"primitive": "square", "weight": "pen", "center": [0.5, 0.5], "size": [0.6, 0.5], "filled": True}),
        ("square-open-plain", "四角を描く", {"primitive": "square", "weight": "pen", "center": [0.5, 0.5], "size": [0.6, 0.5], "filled": False}),
        ("square-filled-quiet", "静かな一つの形", {"primitive": "square", "weight": "pen", "center": [0.5, 0.5], "size": [0.6, 0.5], "filled": True}),
        ("triangle-open-plain", "三角を描く", {"primitive": "triangle", "weight": "pen", "center": [0.5, 0.5], "size": [0.7, 0.4], "filled": False}),
        ("circle-filled-control", "円を描く", {"primitive": "circle", "weight": "pen", "center": [0.5, 0.5], "radius": 0.30, "filled": True}),
        ("square-small-control", "四角を描く", {"primitive": "square", "weight": "pen", "center": [0.5, 0.5], "size": [0.2, 0.15], "filled": True}),
        ("large-surface-exempt", "大きな布を広げる", {"primitive": "square", "weight": "pen", "center": [0.5, 0.5], "size": [0.6, 0.5], "filled": True}),
    ]

    out: dict = {
        "note": "what coerce decides about the background and how it tempers a large shape",
        "background_cases": [],
        "tempering_cases": [],
        "stage2_user_message": {
            "note": "the DDL is the whole user message; the description is not prefixed (composer.py)",
            "ddl": "背景を黒で塗りつぶす。細い線を10本散らす。",
            "original_text": "夜の静けさ",
            "expected": "背景を黒で塗りつぶす。細い線を10本散らす。",
        },
    }
    for case_id, ddl, background in background_cases:
        out["background_cases"].append({
            "case_id": case_id,
            "ddl": ddl,
            "background_in": background,
            "expected": _c._with_background_dominance_governor(background, ddl=ddl),
            "explicit_background_intent": _c._has_explicit_background_intent(ddl),
        })
    for case_id, ddl, raw in temper_cases:
        ins = Instruction.model_validate(raw)
        # The real order, and it matters: the filled tempering runs first as a
        # pass of its own (coerce/__init__.py:181), and only then does the
        # density-governor pass run symbolic -> single -> filled
        # (compose.py:2093-2095). Chaining single before filled instead makes the
        # filled tempering unreachable -- its threshold (0.20) is above single's
        # (0.14), so single always caps the shape below it first, and a fixture
        # built that way cannot tell a port that skipped the filled pass.
        stepped = _c._with_unintentional_filled_shape_tempering(ins, ddl=ddl)
        stepped = _c._with_quiet_symbolic_shape_tempering(stepped, ddl=ddl)
        stepped = _c._with_quiet_single_shape_tempering(stepped, ddl=ddl)
        both = _c._with_unintentional_filled_shape_tempering(stepped, ddl=ddl)
        out["tempering_cases"].append({
            "case_id": case_id,
            "ddl": ddl,
            "instruction": ins.model_dump(mode="json", exclude_none=True),
            "expected": both.model_dump(mode="json", exclude_none=True),
            "changed": both.model_dump() != ins.model_dump(),
        })
    out_path("coerce_governors.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2)
    )


def lineage_wiring_fixtures() -> None:
    """Bake what the server writes to the lineage tables when a work is saved.

    The Android port owns the same two tables, the same DAO and the same
    migration, and nothing calls them: `LineageDao` is reachable only from
    `InkuDatabase`, so no row is ever written ([I-068]). This is the decision
    table that wiring has to reproduce.

    Every case runs the real `db.add_item` against a throwaway SQLite file, so
    the expectations come from the implementation and not from a reading of it.
    `db` is imported here rather than at module scope: the URL is read at import
    time, and the rest of the generator never pulls `db` in.
    """
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["INKU_DB_URL"] = f"sqlite:///{tmp}/lineage.db"
        os.environ["INKU_DB_BACKUP_DIR"] = f"{tmp}/backups"
        from inku_server import db

        db.init_db()
        user = db.add_user("baker", "baker@example.invalid", "pw-not-used", ["admins"], None)
        uid = user["id"]

        def item(item_id, *, at=1000, **extra):
            base = {
                "id": item_id, "user_id": uid, "at": at,
                "input": "円を描く", "source_text": "円を描く", "ddl": "円を描く。",
                "score": {"version": "0.1.0", "canvas": "square",
                          "background": "white", "instructions": []},
                "svg": "<svg/>", "elapsed_ms": 1,
            }
            base.update(extra)
            return base

        def written(history_id):
            with db.SessionLocal() as session:
                row = session.query(db.HistoryRow).filter(
                    db.HistoryRow.id == history_id).first()
                if row is None or row.lineage_node_id is None:
                    return None, None
                node = session.get(db.LineageNodeRow, row.lineage_node_id)
                edge = session.query(db.LineageEdgeRow).filter(
                    db.LineageEdgeRow.child_node_id == node.id).first()
                return node, edge

        cases = []

        db.add_item(item("h-root"))
        root, root_edge = written("h-root")
        cases.append({
            "case_id": "root-work-writes-one-node-and-no-edge",
            "given": {"parent": None, "derivation_kind": None, "history_visibility": None},
            "expected": {
                "node_written": True,
                "state": root.state,
                "root_is_self": root.root_node_id == root.id,
                "edge_written": root_edge is not None,
                "description_hash_present": bool(root.description_hash),
                "render_hash_present": bool(root.render_hash),
                "node_at_equals_item_at": root.at == 1000,
            },
        })

        db.add_item(item("h-child", at=2000, lineage_parent_node_id=root.id,
                         derivation_kind="touch_change",
                         derivation_metadata={"b": 1, "a": 2}))
        child, child_edge = written("h-child")
        cases.append({
            "case_id": "declared-derivation-writes-an-edge-and-inherits-the-root",
            "given": {"parent": "<the root node>", "derivation_kind": "touch_change",
                      "derivation_metadata": {"b": 1, "a": 2}},
            "expected": {
                "node_written": True,
                "edge_written": child_edge is not None,
                "derivation_kind": None if child_edge is None else child_edge.derivation_kind,
                "root_is_self": child.root_node_id == child.id,
                "child_root_equals_parent_root": child.root_node_id == root.root_node_id,
                "metadata_json": None if child_edge is None else child_edge.metadata_json,
                "edge_at_equals_item_at": child_edge is not None and child_edge.at == 2000,
            },
        })

        db.add_item(item("h-grand", at=3000, lineage_parent_node_id=child.id,
                         derivation_kind="variation"))
        grand, grand_edge = written("h-grand")
        cases.append({
            "case_id": "grandchild-keeps-the-original-root",
            "given": {"parent": "<the child node>", "derivation_kind": "variation"},
            "expected": {
                "root_equals_the_root_of_the_first_work": grand.root_node_id == root.id,
                "root_equals_the_parent": grand.root_node_id == child.id,
                "edge_parent_is_the_child_node": (
                    grand_edge is not None and grand_edge.parent_node_id == child.id),
            },
        })

        db.add_item(item("h-hidden", at=4000, history_visibility="lineage_only"))
        hidden, _ = written("h-hidden")
        cases.append({
            "case_id": "lineage-only-visibility-sets-the-node-state",
            "given": {"history_visibility": "lineage_only"},
            "expected": {"node_written": True, "state": hidden.state},
        })

        def rejects(case_id, given, **extra):
            try:
                db.add_item(item(f"h-{case_id}", at=5000, **extra))
            except ValueError as exc:
                cases.append({"case_id": case_id, "given": given,
                              "expected": {"rejected": True, "message": str(exc)}})
            else:
                cases.append({"case_id": case_id, "given": given,
                              "expected": {"rejected": False, "message": None}})

        # Node ids are uuid4, so `given` carries a label: a rebake has to
        # reproduce these bytes exactly.
        rejects("unknown-derivation-kind-is-rejected",
                {"lineage_parent_node_id": "<the root node>", "derivation_kind": "not_a_kind"},
                lineage_parent_node_id=root.id, derivation_kind="not_a_kind")
        rejects("derivation-kind-without-a-parent-is-rejected",
                {"derivation_kind": "touch_change"}, derivation_kind="touch_change")
        rejects("missing-parent-is-rejected",
                {"lineage_parent_node_id": "00000000-0000-0000-0000-000000000000",
                 "derivation_kind": "replay"},
                lineage_parent_node_id="00000000-0000-0000-0000-000000000000",
                derivation_kind="replay")
        rejects("non-object-derivation-metadata-is-rejected",
                {"lineage_parent_node_id": "<the root node>", "derivation_kind": "replay",
                 "derivation_metadata": ["not", "an", "object"]},
                lineage_parent_node_id=root.id, derivation_kind="replay",
                derivation_metadata=["not", "an", "object"])

        out_path("lineage_wiring.json").write_text(json.dumps({
            "note": (
                "What the server writes to lineage_nodes / lineage_edges when a work "
                "is saved. Baked by running db.add_item on a throwaway SQLite file."
            ),
            "derivation_kinds": sorted(db.LINEAGE_DERIVATION_KINDS),
            "cases": cases,
        }, ensure_ascii=False, indent=2))


def main() -> None:
    for directory in (OUT, render_engine_dir(), ddl_engine_dir()):
        directory.mkdir(parents=True, exist_ok=True)
    SCORES.update(VARIATION_SCORES)
    SCORES.update(CLOUDFORM_SCORES)
    SCORES.update(ARRANGEMENT_SCORES)
    # Before anything is written: a case that cannot fail must not be baked.
    assert_arrangement_cases_discriminate()
    stroke_engine_fixtures()
    variation_fixtures()
    proportional_fixtures()
    seed_range_fixtures()
    fill_and_arc_fixtures()
    cloudform_and_relation_fixtures()
    ddl_expand_fixtures()
    count_preservation_fixtures()
    prompt_fixtures()
    color_assignment_fixtures()
    score_schema_contract_fixture()
    arrangement_fixtures()
    coerce_governor_fixtures()
    lineage_wiring_fixtures()
    svg_fixtures()
    write_manifest(render_engine_dir(), "render-engine", current_render_engine().version)
    write_manifest(ddl_engine_dir(), "ddl-engine", DDL_ENGINE_VERSION)
    written = (
        sum(1 for path in OUT.iterdir() if path.is_file())
        + sum(1 for path in render_engine_dir().iterdir() if path.is_file())
        + sum(1 for path in ddl_engine_dir().iterdir() if path.is_file())
    )
    print(f"wrote {written} files to {OUT} (older version directories untouched)")


if __name__ == "__main__":
    main()
