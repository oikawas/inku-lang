"""Generate the server-side reference corpus the Android port is verified against.

The Android renderer is being caught up from engine 2 to engine 10. Parity is
checked against fixtures produced here, so the expected values always come from
the server implementation rather than from the port's own behavior.

Run from `server/`:

    UV_CACHE_DIR=/tmp/inku-uv-cache uv run python scripts/gen_android_reference.py

Outputs land in `android/app/src/test/resources/server_reference/`:

- `stroke_engine_latent_energy.json`      latent_energy samples per seed
- `stroke_engine_synthesize_along.json`   both banks and the path `d` for four strokes
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
        "left": [[round(x, 6), round(y, 6)] for x, y in result.left],
        "right": [[round(x, 6), round(y, 6)] for x, y in result.right],
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
    ]
    (OUT / "stroke_engine_synthesize_along.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2))

    energy = [
        {"seed": seed, "samples": [round(se.latent_energy(i / 20.0, seed), 9) for i in range(21)]}
        for seed in (1, 12345, 999)
    ]
    (OUT / "stroke_engine_latent_energy.json").write_text(json.dumps(energy, ensure_ascii=False, indent=2))


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


VARIATION_SCORES: dict[str, dict] = {
    "07_circle_wave": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.25, "weight": "pen", "variation": {"amplitude": "broad", "frequency": "medium", "quality": "wave", "dimensions": ["position_x", "position_y"]}}]},
    "08_circle_perlin": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.25, "weight": "pen", "variation": {"amplitude": "fine", "frequency": "high", "quality": "perlin", "dimensions": ["radius"]}}]},
    "09_line_white": {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "weight": "pencil", "variation": {"amplitude": "medium", "frequency": "medium", "quality": "white", "dimensions": ["position_y"]}}]},
    "10_arc_wave": {"instructions": [{"primitive": "arc", "center": [0.5, 0.5], "radius": 0.3, "angle_start": 0, "angle_end": 180, "weight": "pen", "variation": {"amplitude": "medium", "frequency": "slow", "quality": "wave", "dimensions": ["position_y"]}}]},
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SCORES.update(VARIATION_SCORES)
    stroke_engine_fixtures()
    variation_fixtures()
    svg_fixtures()
    print(f"wrote {len(list(OUT.iterdir()))} files to {OUT}")


if __name__ == "__main__":
    main()
