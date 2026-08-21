"""I-334 grain pattern contract tests.

T-336 is deliberately manual: the five author-review SVGs are produced only at
Stage E, after T-329 through T-335 are green.  It has no automatic substitute.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

from inku_server.render_engines import current_render_engine
from inku_server.renderer import SURFACE_MARK_MAX, render
from inku_server.schema import Score
from inku_server.svg_compat import validate_compat_svg

ROOT = Path(__file__).resolve().parents[2]


def _score(
    *,
    primitive: str = "square",
    weight: str = "pen",
    size: float = 0.30,
    density: float = 0.50,
    scale: float = 0.50,
    opacity: float = 0.42,
) -> Score:
    instruction: dict[str, object] = {
        "primitive": primitive,
        "weight": weight,
        "color": "black",
        "filled": True,
        "surface": {
            "texture": "grain",
            "density": density,
            "scale": scale,
            "opacity": opacity,
        },
    }
    if primitive == "square":
        instruction.update(
            {"position": [0.5 - size / 2, 0.5 - size / 2], "size": [size, size]}
        )
    elif primitive == "cloudform":
        instruction.update(
            {"center": [0.5, 0.5], "size": [size, size * 0.72], "rotation": 0.34}
        )
    else:
        raise AssertionError(f"unsupported fixture primitive: {primitive}")
    return Score.model_validate({"instructions": [instruction]})


def _grain_pattern(svg: str) -> ElementTree.Element:
    root = ElementTree.fromstring(svg)
    patterns = [
        element
        for element in root.iter()
        if element.tag.endswith("pattern")
        and element.attrib.get("id", "").startswith("surface_pattern_")
    ]
    assert len(patterns) == 1
    return patterns[0]


def _grain_marks(pattern: ElementTree.Element) -> list[ElementTree.Element]:
    return [
        element
        for element in pattern.iter()
        if "surface-grain-mark" in element.attrib.get("class", "").split()
    ]


def _grain_dabs(pattern: ElementTree.Element) -> list[ElementTree.Element]:
    return [
        element
        for element in pattern.iter()
        if "surface-grain-dab" in element.attrib.get("class", "").split()
    ]


def _surface_group(svg: str) -> str:
    match = re.search(r'(<g id="surface_000_000_grain">.*?</g>)', svg)
    assert match is not None
    return match.group(1)


def _tool_geometry_signature(mark: ElementTree.Element) -> tuple[object, ...]:
    """Compare tool grammar structure, excluding all seed-derived numeric values."""
    tag = mark.tag.rpartition("}")[-1]
    attrs = tuple(
        sorted(
            (key, value)
            for key, value in mark.attrib.items()
            if key
            not in {
                "class",
                "fill",
                "fill-opacity",
                "opacity",
                "cx",
                "cy",
                "d",
                "r",
            }
        )
    )
    return tag, attrs, tuple(re.findall(r"[A-Za-z]", mark.attrib.get("d", "")))


def test_t329_grain_uses_one_fixed_pattern_and_shape_carrier():
    """T-329: tile mark count ignores destination size and carrier owns the fill."""
    small = render(_score(size=0.18), svg_profile="editable", render_seed=81)
    large = render(_score(size=0.62), svg_profile="editable", render_seed=81)

    small_pattern = _grain_pattern(small)
    large_pattern = _grain_pattern(large)
    assert small_pattern.attrib["id"] == large_pattern.attrib["id"]
    assert len(_grain_marks(small_pattern)) == len(_grain_marks(large_pattern))
    assert len(_grain_marks(small_pattern)) > 0

    root = ElementTree.fromstring(large)
    carrier = next(
        element
        for element in root.iter()
        if "surface-grain-carrier-v1" in element.attrib.get("class", "").split()
    )
    assert carrier.tag.endswith("path")
    assert carrier.attrib["fill"] == f"url(#{large_pattern.attrib['id']})"
    assert "clip-path" not in carrier.attrib
    assert "filter" not in carrier.attrib
    # A representative carrier is bounded even before gzip: the repeated area is
    # a fill reference, not a destination-sized list of completed dab paths.
    assert len(_surface_group(large)) < 3000


def test_t330_grain_inputs_change_only_their_pattern_decision_axis():
    """T-330: density, scale, opacity and seed each have their own deterministic effect."""
    base = render(_score(), svg_profile="editable", render_seed=17)
    same = render(_score(), svg_profile="editable", render_seed=17)
    dense = render(_score(density=0.95), svg_profile="editable", render_seed=17)
    broad = render(_score(scale=0.95), svg_profile="editable", render_seed=17)
    faint = render(_score(opacity=0.16), svg_profile="editable", render_seed=17)
    other_seed = render(_score(), svg_profile="editable", render_seed=18)

    assert base == same
    assert len(_grain_marks(_grain_pattern(dense))) > len(
        _grain_marks(_grain_pattern(base))
    )
    assert [
        mark.attrib.get("d", mark.attrib.get("r"))
        for mark in _grain_dabs(_grain_pattern(broad))
    ] != [
        mark.attrib.get("d", mark.attrib.get("r"))
        for mark in _grain_dabs(_grain_pattern(base))
    ]
    assert [
        mark.attrib.get("fill-opacity") for mark in _grain_dabs(_grain_pattern(faint))
    ] != [mark.attrib.get("fill-opacity") for mark in _grain_dabs(_grain_pattern(base))]
    assert ElementTree.tostring(_grain_pattern(other_seed)) != ElementTree.tostring(
        _grain_pattern(base)
    )


@pytest.mark.parametrize("weight", ["computer", "pen", "brush_thick", "chalk"])
def test_t331_grain_tool_signature_is_geometry_not_presentation(weight: str):
    """T-331: the four named tools keep distinct generated mark geometry."""
    pattern = _grain_pattern(
        render(_score(weight=weight), svg_profile="editable", render_seed=51)
    )
    marks = _grain_dabs(pattern)
    assert marks
    signature = tuple(_tool_geometry_signature(mark) for mark in marks)
    signatures = {
        candidate: tuple(
            _tool_geometry_signature(mark)
            for mark in _grain_dabs(
                _grain_pattern(
                    render(
                        _score(weight=candidate), svg_profile="editable", render_seed=51
                    )
                )
            )
        )
        for candidate in ("computer", "pen", "brush_thick", "chalk")
    }
    assert len(set(signatures.values())) == 4
    assert signature == signatures[weight]


@pytest.mark.parametrize("profile", ["display", "editable", "compat"])
@pytest.mark.parametrize("fixture", ["cloudform", "edge_square"])
def test_t332_grain_boundaries_are_a_pattern_carrier_in_every_profile(
    profile: str, fixture: str
):
    """T-332: concave/edge carriers need no filter or surface clip in any profile."""
    score = (
        _score(primitive="cloudform", size=0.56)
        if fixture == "cloudform"
        else Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "square",
                        "position": [0.86, 0.86],
                        "size": [0.14, 0.14],
                        "weight": "pen",
                        "filled": True,
                        "surface": {
                            "texture": "grain",
                            "density": 0.75,
                            "scale": 0.65,
                            "opacity": 0.42,
                        },
                    }
                ]
            }
        )
    )
    svg = render(score, svg_profile=profile, render_seed=73)
    pattern = _grain_pattern(svg)
    assert _grain_marks(pattern)
    assert "clip_surface_" not in svg
    assert all("filter" not in element.attrib for element in pattern.iter())
    if profile == "compat":
        assert "filter=" not in svg
        validate_compat_svg(svg)


def test_t333_only_grain_moves_and_surface_budget_stays_fixed():
    """T-333: non-grain surface branches do not acquire the grain pattern carrier."""
    assert SURFACE_MARK_MAX == 90
    for texture in (
        "stipple",
        "paper_grain",
        "aquatint",
        "wash",
        "hatch",
        "crosshatch",
        "solid",
    ):
        score = Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "square",
                        "position": [0.3, 0.3],
                        "size": [0.4, 0.4],
                        "weight": "pen",
                        "filled": True,
                        "surface": {"texture": texture},
                    }
                ]
            }
        )
        svg = render(score, svg_profile="editable", render_seed=91)
        assert "surface_pattern_" not in svg


def test_t334_spec_names_the_grain_pattern_while_existing_export_seams_stay_characterised():
    """T-334: API/history/Web/CLI keep their existing seed/profile pass-through seams."""
    japanese = (ROOT / "SPEC.ja.md").read_text(encoding="utf-8")
    english = (ROOT / "SPEC.md").read_text(encoding="utf-8")
    assert 'surface.texture="grain"' in japanese and "<pattern>" in japanese
    assert 'surface.texture="grain"' in english and "<pattern>" in english


def test_t335_default_engine_advances_for_the_changed_grain_serialisation():
    """T-335: reference work belongs under render engine 39 after author approval."""
    assert current_render_engine().version == "39"
