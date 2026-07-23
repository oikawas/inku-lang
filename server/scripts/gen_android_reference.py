"""Generate the server-side reference corpus the Android port is verified against.

The Android renderer is being caught up from engine 2 to engine 10. Parity is
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
- `<name>.svg`                            full renders at the current engine version
- `svg_index.json`                        the Score, seed, byte size, element counts,
                                          and class attributes of each SVG

Element counts and class attributes are the comparison surface for the port: the
class strings carry the control-point and event counts (`contour-stroke-v1
controls-62 events-1`), the fill stroke count (`fill-stroke-v1 strokes-48`), and
the hatch spacing (`surface-stroke-v1 hatch-spacing-22.500`).
"""

from __future__ import annotations

import json
import math
import pathlib
import re

from inku_server import renderer
from inku_server import stroke_engine as se
from inku_server.schema import Score

OUT = pathlib.Path(__file__).resolve().parents[2] / "android/app/src/test/resources/server_reference"
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
        }
        for s in samples
    ]


def _along(name, centerline, base_width, weight, seed, closed, anchors=frozenset()):
    result = se.synthesize_along(centerline, base_width, weight, seed, closed=closed, anchors=anchors)
    return {
        "name": name,
        "input": {
            "centerline": [list(p) for p in centerline],
            "base_width": base_width,
            "weight": weight,
            "seed": seed,
            "closed": closed,
            "anchors": sorted(anchors),
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
    ]
    (OUT / "stroke_engine_synthesize_along.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2))

    energy = [
        {"seed": seed, "samples": [round(se.latent_energy(i / 20.0, seed), 9) for i in range(21)]}
        for seed in (1, 12345, 999)
    ]
    (OUT / "stroke_engine_latent_energy.json").write_text(json.dumps(energy, ensure_ascii=False, indent=2))

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
    ]
    (OUT / "stroke_engine_synthesize_stroke.json").write_text(json.dumps(straight, ensure_ascii=False, indent=2))

    primitive_fixtures()


def _stroke(name, start, end, base_width, weight, seed, samples=49):
    result = se.synthesize_stroke(start, end, base_width, weight, seed, samples=samples)
    return {
        "name": name,
        "input": {
            "start": list(start), "end": list(end), "base_width": base_width,
            "weight": weight, "seed": seed, "samples": samples,
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
            (2, 0.04, 49),       # hair: rate too low to fire
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

    (OUT / "stroke_engine_primitives.json").write_text(json.dumps({
        "grammars": {
            weight: {
                "stiffness": g.stiffness, "damping": g.damping,
                "energy_width": g.energy_width, "energy_lateral": g.energy_lateral,
                "event_rate": g.event_rate, "taper": g.taper, "bulge": g.bulge,
            }
            for weight, g in se.GRAMMARS.items()
        },
        "closed_envelope_floor": se.CLOSED_ENVELOPE_FLOOR,
        "unit": unit,
        "smooth_noise": smooth,
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
}

TAGS = ("path", "polyline", "polygon", "circle", "ellipse", "line", "rect", "g")


def svg_fixtures() -> None:
    index: dict[str, dict] = {}
    for name, raw in SCORES.items():
        svg = renderer.render(Score.model_validate(raw), render_seed=RENDER_SEED, svg_profile=SVG_PROFILE)
        (OUT / f"{name}.svg").write_text(svg)
        index[name] = {
            "score": raw,
            "render_seed": RENDER_SEED,
            "svg_profile": SVG_PROFILE,
            "bytes": len(svg),
            "counts": {tag: len(re.findall(f"<{tag}[ />]", svg)) for tag in TAGS},
            "classes": sorted(set(re.findall(r'class="([^"]+)"', svg))),
        }
    (OUT / "svg_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2))


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

    (OUT / "renderer_variation_primitives.json").write_text(json.dumps({
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

    (OUT / "renderer_seed_range.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))


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
            "AMPLITUDE_RATIO": renderer.AMPLITUDE_RATIO,
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
        },
        "canvases": {a: {"width": c.width, "height": c.height, "unit": c.unit, "unit_scale": renderer._unit_scale(c)} for a, c in canvases.items()},
        "representative_size_px": [],
        "amplitude_px": [],
        "blur_std_px": [],
        "segment_count": [],
        "stroke_sample_count": [],
        "stroke_width_px": [],
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

    (OUT / "renderer_proportional.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))


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
    for name, (ins, aspect) in fill_group_cases.items():
        canvas = canvases[aspect]
        seed = renderer._seed_for_instruction(ins, RENDER_SEED)
        if ins.primitive == "square":
            assert ins.position is not None and ins.size is not None
            px, py = renderer._px(ins.position, canvas)
            w = ins.size[0] * canvas.width
            h = ins.size[1] * canvas.height
            contour = [(px, py), (px + w, py), (px + w, py + h), (px, py + h)]
        else:
            assert ins.center is not None and ins.radius is not None
            ccx = ins.center[0] * canvas.width
            ccy = ins.center[1] * canvas.height
            rr = ins.radius * canvas.unit
            count = renderer._stroke_sample_count(2 * math.pi * rr, canvas)
            contour = [
                (ccx + rr * math.cos(2 * math.pi * i / count), ccy + rr * math.sin(2 * math.pi * i / count))
                for i in range(count)
            ]
        attrs = {"stroke": "#111111", "fill": "#111111", "fill_opacity": 1.0, "stroke_opacity": 1.0}
        group = renderer._render_fill_strokes(
            svgwrite.Drawing(), ins, contour, attrs, canvas, RENDER_SEED, use_filters=False
        )
        paths = [] if group is None else [e.attribs.get("d", "") for e in group.elements]
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

    (OUT / "renderer_fill_and_arc.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SCORES.update(VARIATION_SCORES)
    stroke_engine_fixtures()
    variation_fixtures()
    proportional_fixtures()
    seed_range_fixtures()
    fill_and_arc_fixtures()
    svg_fixtures()
    print(f"wrote {len(list(OUT.iterdir()))} files to {OUT}")


if __name__ == "__main__":
    main()
