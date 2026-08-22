"""The drawing must not read the last bit of a libm result.

macOS libm and glibc can disagree by one ULP on sin/cos/hypot. Before engine
21, arrangement coordinates reached a hash and amplified that difference into
a different performance seed (ledger I-111). Engine 28 exposed a second route:
paper-contact sampling counted arc length directly, so the last bit could move
a sample, its sample-derived quantile, and a whole material-outline fragment
(ledger I-178).

Cross-platform identity cannot be observed from one machine, so the main test
perturbs all three libm calls by exactly one ULP. Its pair removes both platform
stabilisers and proves that the same perturbation still reaches the drawing.
The exposure test derives the current material-outline tools from rendered
corpus inputs, then requires the smaller two-pass sample to cover every tool and
the six cases that actually split between macOS and Linux under engine 28.
"""

from __future__ import annotations

import functools
import importlib.util
import inspect
import json
import math
import pathlib
import sys

from inku_server import renderer
from inku_server.render_engines.default import planning

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"

ENGINE_28_PLATFORM_SPLITS = frozenset(
    {
        "A-pencil-polygon",
        "B-perlin-medium-circle-pencil",
        "B-white-broad-arc-pencil",
        "C-fill-ellipse-pencil",
        "E-wild-pencil-ellipse",
        "E-wild-pencil-polygon",
    }
)

# Which of the six real splits a one-ULP nudge reaches depends on the host libm,
# because the nudge goes in one direction and the two platforms sit on opposite
# sides of the boundary. macOS was measured on 2026-08-09 against engine 28,
# before the contact-length quantiser existed; the linux test container was
# measured on 2026-08-17 (glibc 2.41, ledger-free run on pentala) and moves the
# one case macOS does not. Their union is asserted below to be exactly
# ENGINE_28_PLATFORM_SPLITS: a host that moved something outside that set would
# be a new route, not a recording difference.
MOVED_WITHOUT_CONTACT_LENGTH_QUANTISER_BY_PLATFORM = {
    "darwin": frozenset(
        {
            "B-perlin-medium-circle-pencil",
            "B-white-broad-arc-pencil",
            "C-fill-ellipse-pencil",
            "E-wild-pencil-ellipse",
            "E-wild-pencil-polygon",
        }
    ),
    "linux": frozenset({"A-pencil-polygon"}),
}

# Measured on 2026-08-03 against engine 20, before the arrangement quantiser
# existed. Every case is a layout that goes through sin/cos.
MOVED_WITHOUT_ARRANGEMENT_QUANTISER = frozenset(
    {
        "G-cluster-center",
        "G-cluster-corner",
        "G-cluster-edge",
        "G-cluster-preserve-edge",
        "G-composition-cluster-center",
        "G-composition-path-wave-edge",
        "G-path-hwave-edge",
        "G-path-wave-center",
        "G-path-wave-corner",
        "G-path-wave-edge",
        "G-radial-center-edge",
        "G-radial-nocenter-center",
        "G-radial-nocenter-corner",
        "G-radial-nocenter-edge",
        "G-fade-radial-edge",
    }
)


class _PreviousUlpHypotMath:
    """math with hypot nudged one ULP towards zero."""

    def __getattr__(self, name: str) -> object:
        return getattr(math, name)

    def hypot(self, *coordinates: float) -> float:
        return math.nextafter(math.hypot(*coordinates), 0.0)


class _OneUlpMath:
    """`math` with the three platform-sensitive calls nudged one ULP."""

    def __getattr__(self, name: str) -> object:
        return getattr(math, name)

    def sin(self, x: float) -> float:
        return math.nextafter(math.sin(x), math.inf)

    def cos(self, x: float) -> float:
        return math.nextafter(math.cos(x), math.inf)

    def hypot(self, *coordinates: float) -> float:
        return math.nextafter(math.hypot(*coordinates), math.inf)


@functools.lru_cache(maxsize=1)
def _generator():
    spec = importlib.util.spec_from_file_location("gen_render_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@functools.lru_cache(maxsize=1)
def _inputs() -> dict[str, dict]:
    return _generator().build_inputs()


@functools.lru_cache(maxsize=1)
def _baseline_drawings() -> dict[str, str]:
    module = _generator()
    return {
        case_id: module.render_case(render_input)
        for case_id, render_input in sorted(_inputs().items())
    }


def _has_material_outline(svg: str) -> bool:
    return 'class="material-outline' in svg or ' material-outline' in svg


@functools.lru_cache(maxsize=1)
def _material_outline_case_ids() -> tuple[str, ...]:
    return tuple(
        case_id
        for case_id, svg in _baseline_drawings().items()
        if _has_material_outline(svg)
    )


def _weight(case_id: str) -> str:
    return _inputs()[case_id]["score"]["instructions"][0]["weight"]


@functools.lru_cache(maxsize=1)
def _stability_case_ids() -> tuple[str, ...]:
    exposure = _material_outline_case_ids()
    representatives = {
        next(case_id for case_id in exposure if _weight(case_id) == weight)
        for weight in sorted({_weight(case_id) for case_id in exposure})
    }
    return tuple(
        sorted(
            representatives
            | ENGINE_28_PLATFORM_SPLITS
            | MOVED_WITHOUT_ARRANGEMENT_QUANTISER
        )
    )


@functools.lru_cache(maxsize=1)
def _frozen_stability_digests() -> dict[str, str]:
    manifest = json.loads(_generator().MANIFEST_PATH.read_text(encoding="utf-8"))
    return {
        case_id: manifest["cases"][case_id]["digest"]
        for case_id in _stability_case_ids()
    }


def _draw_stability_cases() -> dict[str, str]:
    module = _generator()
    return {
        case_id: module._normalized_digest(module.render_case(_inputs()[case_id]))
        for case_id in _stability_case_ids()
    }


def _moved_under_one_ulp(monkeypatch) -> set[str]:
    before = _draw_stability_cases()
    monkeypatch.setattr(renderer, "math", _OneUlpMath())
    monkeypatch.setattr(planning, "math", _OneUlpMath())
    after = _draw_stability_cases()
    monkeypatch.undo()
    return {case_id for case_id in before if before[case_id] != after[case_id]}


def test_stability_cases_cover_the_current_exposure() -> None:
    exposure = set(_material_outline_case_ids())
    selected = set(_stability_case_ids())
    assert selected <= exposure
    assert ENGINE_28_PLATFORM_SPLITS <= selected
    assert {_weight(case_id) for case_id in selected} == {
        _weight(case_id) for case_id in exposure
    }


def test_exposure_gate_is_derived_from_rendered_output() -> None:
    source = inspect.getsource(test_stability_cases_cover_the_current_exposure)
    assert "_material_outline_case_ids()" in source
    assert "len(" not in source


def test_one_ulp_of_arc_length_does_not_change_fragment_shape(monkeypatch) -> None:
    points = [(0.0, 0.0), (2.0, 0.0)]
    before = renderer._contact_fragments(
        points, coverage=0.2, grain_px=3.0, seed=0, closed=False
    )
    monkeypatch.setattr(renderer, "math", _PreviousUlpHypotMath())
    after = renderer._contact_fragments(
        points, coverage=0.2, grain_px=3.0, seed=0, closed=False
    )
    assert [len(piece) for piece, _ in before] == [
        len(piece) for piece, _ in after
    ]


def test_stability_cases_match_the_current_frozen_corpus() -> None:
    assert _draw_stability_cases() == _frozen_stability_digests()


def test_one_ulp_of_libm_does_not_move_the_drawing(monkeypatch) -> None:
    assert _moved_under_one_ulp(monkeypatch) == set()


def test_without_the_stabilisers_the_same_perturbation_is_seen(monkeypatch) -> None:
    """Keeps the main test honest by exposing both known platform routes."""
    expected_contact = MOVED_WITHOUT_CONTACT_LENGTH_QUANTISER_BY_PLATFORM.get(
        sys.platform
    )
    assert expected_contact is not None, (
        f"no contact-length recording for {sys.platform!r}; measure it by running"
        " this test there and add the set it reports"
    )
    monkeypatch.setattr(planning, "_quantise_instructions", lambda items: items)
    monkeypatch.setattr(renderer, "_quantise_contact_length", lambda value: value)
    moved = _moved_under_one_ulp(monkeypatch)
    assert moved == (MOVED_WITHOUT_ARRANGEMENT_QUANTISER | expected_contact)


def test_the_two_recordings_together_cover_every_engine_28_split() -> None:
    """The platform recordings partition the six splits; neither alone does.

    Reading one platform's set as "the cases that are sensitive" is how this
    file gets misread: macOS sees five, linux sees the sixth, and the drawing
    the product ships is stable on both because the quantisers are what remove
    the difference -- not the choice of machine.
    """
    recordings = MOVED_WITHOUT_CONTACT_LENGTH_QUANTISER_BY_PLATFORM.values()
    assert frozenset().union(*recordings) == ENGINE_28_PLATFORM_SPLITS
    assert all(recording for recording in recordings)
