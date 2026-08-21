"""Direct profile tests for engine 40's non-computer solid mottle."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from inku_server.render_engines import current_render_engine
from inku_server.renderer import render
from inku_server.schema import Score
from inku_server.svg_compat import validate_compat_svg

ROOT = Path(__file__).resolve().parents[2]
SVG_NS = "{http://www.w3.org/2000/svg}"
SEED = 2718
OLD_LARGE_SOLID_BYTES = 201_971


def _solid_score(weight: str) -> Score:
    return Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.42,
                    "weight": weight,
                    "filled": True,
                    "surface": {"texture": "solid"},
                }
            ]
        }
    )


def _render(weight: str, profile: str) -> str:
    return render(_solid_score(weight), render_seed=SEED, svg_profile=profile)


def _elements(svg: str, name: str):
    return ElementTree.fromstring(svg).iter(f"{SVG_NS}{name}")


def _classed(svg: str, class_name: str):
    return [
        element
        for element in ElementTree.fromstring(svg).iter()
        if class_name in element.attrib.get("class", "").split()
    ]


def test_t337_non_computer_solid_has_stable_base_fill_and_calibrated_mottle():
    """Display/editable keep a real base, then a deterministic standard filter overlay."""
    for profile in ("display", "editable"):
        first = _render("pen", profile)
        assert first == _render("pen", profile)

        mottle_filter = next(
            element
            for element in _elements(first, "filter")
            if element.attrib["id"].startswith("solid-mottle-")
        )
        filter_id = mottle_filter.attrib["id"]
        turbulence = next(mottle_filter.iter(f"{SVG_NS}feTurbulence"))
        assert turbulence.attrib["baseFrequency"] == "0.035000"
        assert turbulence.attrib["numOctaves"] == "3"
        component = next(mottle_filter.iter(f"{SVG_NS}feFuncA"))
        assert component.attrib["tableValues"] == "0.310000 1"

        base = _classed(first, "solid-base-fill-v1")
        overlay = _classed(first, "solid-mottle-overlay-v1")
        assert len(base) == len(overlay) == 1
        assert "filter" not in base[0].attrib
        assert overlay[0].attrib["filter"] == f"url(#{filter_id})"

    paired = Score.model_validate(
        {
            "instructions": [
                _solid_score("pen").instructions[0].model_dump(),
                _solid_score("pen").instructions[0].model_dump(),
            ]
        }
    )
    paired_svg = render(paired, render_seed=SEED, svg_profile="editable")
    paired_ids = [
        element.attrib["id"]
        for element in _elements(paired_svg, "filter")
        if element.attrib["id"].startswith("solid-mottle-")
    ]
    assert len(paired_ids) == len(set(paired_ids)) == 2


def test_t338_non_computer_solid_compat_is_flat_and_portable():
    svg = _render("pen", "compat")

    validate_compat_svg(svg)
    assert not list(_elements(svg, "filter"))
    assert not list(_elements(svg, "clipPath"))
    assert len(_classed(svg, "solid-base-fill-v1")) == 1
    assert not _classed(svg, "solid-mottle-overlay-v1")


def test_t339_computer_keeps_its_raster_while_non_computer_drops_scanline_growth():
    for profile in ("display", "editable", "compat"):
        computer = _render("computer", profile)
        assert _classed(computer, "fill-stroke-v1")
        assert not _classed(computer, "solid-mottle-overlay-v1")

    hand = _render("pen", "display")
    assert _classed(hand, "solid-mottle-overlay-v1")
    assert not _classed(hand, "fill-stroke-v1")
    assert len(hand.encode("utf-8")) <= OLD_LARGE_SOLID_BYTES // 2


def test_t340_profile_pass_through_docs_and_engine_history_match_engine_40():
    """Web/CLI already pass profiles through; descriptions and histories name the new boundary."""
    web_download = (ROOT / "web/src/lib/features/export/download.ts").read_text(encoding="utf-8")
    cli = (ROOT / "cli/src/inku_cli/cli.py").read_text(encoding="utf-8")
    spec_ja = (ROOT / "SPEC.ja.md").read_text(encoding="utf-8")
    spec_en = (ROOT / "SPEC.md").read_text(encoding="utf-8")
    history_ja = (ROOT / "docs/spec/render-engine-history.ja.md").read_text(encoding="utf-8")
    history_en = (ROOT / "docs/spec/render-engine-history.md").read_text(encoding="utf-8")

    assert "svg_profile: profile" in web_download
    assert '"svg_profile": svg_profile' in cli
    assert "SVG-native editor" in spec_ja
    assert "filter-free flat vector fallback" in spec_ja
    assert "SVG-native editors" in spec_en
    assert "filter-free flat vector fallback" in spec_en
    assert "engine 40" in history_ja
    assert "engine 40" in history_en
    assert current_render_engine().version == "40"
