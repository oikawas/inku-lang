import math
import re
import time
import pytest
from pydantic import ValidationError
from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect
from inku_server.render_engines.default.marks import _stroke_sample_count
from inku_server.renderer import render
from inku_server.schema import Score
from inku_server.stroke_engine import GRAMMARS, synthesize_stroke


def _line(weight: str) -> Score:
    return Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.1, 0.5],
                    "to": [0.9, 0.5],
                    "weight": weight,
                }
            ]
        }
    )


def _line_length_px(score: Score) -> float:
    ins = score.instructions[0]
    canvas = canvas_size_for_aspect(None)
    return math.hypot(
        (ins.to[0] - ins.from_[0]) * canvas.width,
        (ins.to[1] - ins.from_[1]) * canvas.height,
    )


def test_rope_is_not_a_score_weight():
    with pytest.raises(ValidationError):
        _line("rope")


def test_print_schema_is_strict_and_versioned_values_exist():
    score = Score.model_validate(
        {
            "canvas": {
                "aspect": "square",
                "ground": {"material": "mezzotint", "tone": "black"},
            },
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.2,
                    "mode": "carve",
                    "carve_depth": "half",
                    "surface": {"texture": "aquatint", "tone_steps": 3},
                }
            ],
        }
    )
    assert score.instructions[0].surface.tone_steps == 3
    with pytest.raises(ValidationError):
        Score.model_validate(
            {"instructions": [{"primitive": "line", "unknown_print_field": True}]}
        )


def test_burin_width_ratio_and_rotring_block():
    stroke = synthesize_stroke((0, 0), (100, 0), 3.2, "burin", 42)
    assert (
        stroke.samples[len(stroke.samples) // 2].width
        / max(stroke.samples[0].width, stroke.samples[-1].width)
        >= 2
    )
    assert GRAMMARS["rotring"].energy_width == GRAMMARS["rotring"].energy_lateral == 0


def test_drypoint_burr_is_one_sided_and_seeded():
    a = synthesize_stroke((0, 0), (100, 0), 2.6, "drypoint", 10)
    b = synthesize_stroke((0, 0), (100, 0), 2.6, "drypoint", 11)
    assert a.burr_side in {-1, 1} and 0.15 <= a.burr_opacity <= 0.35
    assert (a.burr_side, a.burr_opacity) != (b.burr_side, b.burr_opacity)


def test_stroke_render_is_seed_deterministic_and_budgeted():
    score = _line("pencil")
    a = render(score, render_seed=123)
    assert a == render(score, render_seed=123) and a != render(score, render_seed=124)
    # 分割数は線長比例。この fixture の線長で決まる本数を規則から算出する
    expected = _stroke_sample_count(
        _line_length_px(score), canvas_size_for_aspect(None)
    )
    assert f"controls-{expected}" in a


def test_burin_cut_is_not_masked_by_a_fixed_width_line():
    svg = render(_line("burin"), render_seed=31)
    assert "stroke-engine-v1" in svg
    assert "<line" not in svg
    assert "<path" in svg


def test_drypoint_uses_one_shared_burr_filter():
    svg = render(_line("drypoint"), render_seed=31)
    assert svg.count('id="texture-drypoint"') == 1
    assert svg.count('filter="url(#texture-drypoint)"') == 1
    assert "<polyline" in svg


def test_surface_tone_and_mezzotint_carve_profiles():
    score = Score.model_validate(
        {
            "canvas": {
                "aspect": "square",
                "ground": {"material": "mezzotint", "tone": "black", "grain": "fine"},
            },
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.25,
                    "mode": "carve",
                    "carve_depth": "half",
                    "surface": {"texture": "aquatint", "tone_steps": 3},
                },
                {
                    "primitive": "square",
                    "position": [0.1, 0.1],
                    "size": [0.25, 0.25],
                    "surface": {
                        "texture": "crosshatch",
                        "spacing_gradient": "coarse_to_dense",
                    },
                },
            ],
        }
    )
    svg = render(score, render_seed=9)
    assert "#151515" in svg and set(re.findall(r"aquatint-step-(\d)", svg)) == {
        "1",
        "2",
        "3",
    }
    spacings = [float(v) for v in re.findall(r"hatch-spacing-([0-9.]+)", svg)]
    assert spacings and min(spacings) < max(spacings) and "layer_15_plate_tone" in svg


def test_print_literal_gate_drops_unmarked_and_invalid_carve():
    from inku_server.composer import _enforce_print_literal_gate

    inferred = Score.model_validate(
        {
            "canvas": {
                "aspect": "square",
                "ground": {"material": "mezzotint", "tone": "black"},
            },
            "instructions": [
                {
                    "primitive": "line",
                    "weight": "burin",
                    "mode": "carve",
                    "carve_depth": "bright",
                }
            ],
        }
    )
    dropped = _enforce_print_literal_gate(inferred, "中央に線を一本引く。")
    assert isinstance(dropped.canvas, str)
    assert dropped.instructions[0].weight == "pen"
    assert dropped.instructions[0].mode == "additive"

    no_ground = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "mode": "carve", "carve_depth": "half"}
            ]
        }
    )
    dropped_carve = _enforce_print_literal_gate(
        no_ground, "黒地から光を彫り出す（半明）。"
    )
    assert dropped_carve.instructions[0].mode == "additive"
    assert dropped_carve.instructions[0].carve_depth is None


def test_stage15_has_no_printmaking_injection_path():
    from pathlib import Path

    source = Path("src/inku_server/ddl_expander.py").read_text()
    for token in ("burin", "drypoint", "mezzotint", "aquatint", 'mode="carve"'):
        assert token not in source


def test_print_render_performance_budget():
    instructions = [
        {
            "primitive": "circle",
            "center": [0.15 + (i % 5) * 0.17, 0.15 + (i // 5) * 0.2],
            "radius": 0.045,
            "mode": "carve",
            "carve_depth": "half",
        }
        for i in range(20)
    ]
    score = Score.model_validate(
        {
            "canvas": {
                "aspect": "square",
                "ground": {
                    "material": "mezzotint",
                    "tone": "black",
                    "grain": "fine",
                    "density": 0.8,
                },
            },
            "instructions": instructions,
        }
    )
    started = time.perf_counter()
    svg = render(score, render_seed=77)
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0 and len(svg.encode()) < 1_500_000
