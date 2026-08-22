from __future__ import annotations

import pytest

from inku_server import renderer
from inku_server.schema import Score
from inku_server.svg_compat import CompatSvgViolation, validate_compat_svg


VALID_COMPAT_SVG = """<svg xmlns=\"http://www.w3.org/2000/svg\" baseProfile=\"full\" version=\"1.1\" viewBox=\"0 0 100 100\"><title>inku render (compat SVG)</title><desc>Portable SVG output.</desc><metadata id=\"inku_metadata\">{\"generator\":\"inku\"}</metadata><defs><pattern id=\"gp0\" patternUnits=\"userSpaceOnUse\" width=\"4\" height=\"4\"><circle cx=\"1\" cy=\"1\" r=\"0.5\" fill=\"#111111\" /></pattern></defs><g id=\"inku_artboard\"><rect id=\"background\" x=\"0\" y=\"0\" width=\"100\" height=\"100\" fill=\"#ffffff\" /><rect x=\"0\" y=\"0\" width=\"100\" height=\"100\" fill=\"url(#gp0)\" /><path id=\"mark_000\" d=\"M 0,0 L 100,100\" fill=\"none\" stroke=\"#111111\" stroke-width=\"1\" /></g></svg>"""

GROUND_GRADIENT_COMPAT_SVG = """<svg xmlns=\"http://www.w3.org/2000/svg\"><defs><linearGradient id=\"gg0\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\"><stop offset=\"0\" stop-color=\"#8a8a8a\" stop-opacity=\"0\"/><stop offset=\"1\" stop-color=\"#8a8a8a\" stop-opacity=\"0.18\"/></linearGradient><radialGradient id=\"gg1\"><stop offset=\"0\" stop-color=\"#8a8a8a\" stop-opacity=\"0.10\"/><stop offset=\"1\" stop-color=\"#8a8a8a\" stop-opacity=\"0\"/></radialGradient><pattern id=\"gp0\" patternUnits=\"userSpaceOnUse\" width=\"10\" height=\"10\"><rect x=\"0\" y=\"0\" width=\"10\" height=\"5\" fill=\"url(#gg0)\"/><circle cx=\"5\" cy=\"5\" r=\"2\" fill=\"url(#gg1)\"/></pattern></defs><rect x=\"0\" y=\"0\" width=\"100\" height=\"100\" fill=\"url(#gp0)\"/></svg>"""


def test_t324_accepts_the_defined_portable_subset():
    validate_compat_svg(VALID_COMPAT_SVG)


def test_t1_accepts_the_ground_gradients_emitted_by_the_renderer():
    validate_compat_svg(GROUND_GRADIENT_COMPAT_SVG)


@pytest.mark.parametrize(
    "fragment",
    (
        "<filter id=\"f\" />",
        "<clipPath id=\"c\" />",
        "<foreignObject />",
        "<path unknown-attr=\"x\" />",
        "<path fill=\"url(https://example.invalid/p.svg)\" />",
        "<path fill=\"url(#missing)\" />",
        "<evil:path xmlns:evil=\"urn:evil\" />",
    ),
)
def test_t324_rejects_every_outside_structure(fragment: str):
    svg = f"<svg xmlns=\"http://www.w3.org/2000/svg\">{fragment}</svg>"
    with pytest.raises(CompatSvgViolation):
        validate_compat_svg(svg)


def test_t328_renderer_checks_the_compat_document_before_return(monkeypatch):
    from inku_server.render_engines.default import engine

    checked: list[str] = []
    monkeypatch.setattr(engine, "validate_compat_svg", checked.append)

    svg = renderer.render(
        Score.model_validate(
            {"instructions": [{"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}]}
        ),
        svg_profile="compat",
        render_seed=123,
    )

    assert checked == [svg]
