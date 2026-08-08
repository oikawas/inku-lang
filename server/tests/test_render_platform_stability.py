"""The drawing must not read the last bit of a libm result.

macOS libm and glibc disagree by one ULP on sin/cos for 7-10 of every 60
arguments. That is invisible wherever the number is merely printed -- the SVG
keeps six decimals -- but `_seed_for_instruction` hashes the whole instruction
dump, so before engine 21 a one-ULP difference produced a different performance
seed and moved the drawing by 0.08-0.17px. The frozen corpus then could not be
reproduced on the other platform, which is what kept CI red from 2026-08-01
(ledger I-111).

Cross-platform identity cannot be observed from one machine, so these two tests
stand in for it: perturb sin/cos by exactly one ULP and require the drawing to
stay put. The second test is what keeps the first from being vacuous -- without
it, a perturbation that never reached the renderer would also look green.
"""

from __future__ import annotations

import functools
import importlib.util
import math
import pathlib

from inku_server import renderer
from inku_server.schema import Score

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"

# Group G is the whole of the exposure: A-F never state an `arrangement`, so
# they never reach `_expand_arrangement` and never feed a coordinate to a hash.
GROUP_PREFIX = "G-"

# Measured on 2026-08-03 against engine 20, before the quantiser existed. Every
# one of them is a layout that goes through sin/cos: cluster, path=wave, radial.
MOVED_WITHOUT_QUANTISER = frozenset(
    {
        "G-cluster-center",
        "G-cluster-corner",
        "G-cluster-edge",
        "G-cluster-preserve-edge",
        # engine 23's composition twins: same score, so the same two layouts
        # reach sin/cos, only from the seed the case states.
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
    }
)


class _OneUlpMath:
    """`math` with sin/cos nudged one ULP -- the size of the real libm gap."""

    def __getattr__(self, name: str) -> object:
        return getattr(math, name)

    def sin(self, x: float) -> float:
        return math.nextafter(math.sin(x), math.inf)

    def cos(self, x: float) -> float:
        return math.nextafter(math.cos(x), math.inf)


@functools.lru_cache(maxsize=1)
def _generator():
    spec = importlib.util.spec_from_file_location("gen_render_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@functools.lru_cache(maxsize=1)
def _group_g_inputs() -> tuple[tuple[str, dict], ...]:
    inputs = _generator().build_inputs()
    return tuple(
        (case_id, render_input)
        for case_id, render_input in sorted(inputs.items())
        if case_id.startswith(GROUP_PREFIX)
    )


def _draw_group_g() -> dict[str, str]:
    module = _generator()
    return {
        case_id: module._normalized_digest(
            module.render(
                Score.model_validate(render_input["score"]),
                color_map=render_input["color_map"],
                catalog_id=render_input["catalog_id"],
                render_seed=render_input["render_seed"],
                composition_seed=render_input.get("composition_seed"),
                svg_profile=render_input["svg_profile"],
                wild=render_input["wild"],
            )
        )
        for case_id, render_input in _group_g_inputs()
    }


def _moved_under_one_ulp(monkeypatch) -> set[str]:
    before = _draw_group_g()
    monkeypatch.setattr(renderer, "math", _OneUlpMath())
    after = _draw_group_g()
    monkeypatch.undo()
    return {case_id for case_id in before if before[case_id] != after[case_id]}


def test_group_g_is_the_whole_exposure() -> None:
    """A gate that measured nothing would still pass the two tests below."""
    assert len(_group_g_inputs()) == 36


def test_one_ulp_of_libm_does_not_move_the_drawing(monkeypatch) -> None:
    assert _moved_under_one_ulp(monkeypatch) == set()


def test_without_the_quantiser_the_same_perturbation_is_seen(monkeypatch) -> None:
    """Keeps the test above honest.

    If this ever goes green, the perturbation stopped reaching the renderer and
    the test above is no longer measuring anything.
    """
    monkeypatch.setattr(renderer, "_quantise_instructions", lambda items: items)
    assert _moved_under_one_ulp(monkeypatch) == MOVED_WITHOUT_QUANTISER
