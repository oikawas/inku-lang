"""Public tests for the SVG-only renderer compatibility facade."""

from __future__ import annotations

from types import SimpleNamespace

from inku_server import renderer
from inku_server.render_engines.base import RenderEngineResult
from inku_server.schema import Score


def test_renderer_exposes_only_the_svg_entrypoint() -> None:
    assert renderer.__all__ == ("render",)


def test_renderer_delegates_every_option_to_the_current_engine(monkeypatch) -> None:
    score = Score.model_validate(
        {"instructions": [{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]}]}
    )
    captured: dict[str, object] = {}

    def render(received_score: Score, **options: object) -> RenderEngineResult:
        captured["score"] = received_score
        captured.update(options)
        return RenderEngineResult(svg="<svg data-owner='current'/>", metadata={})

    engine = SimpleNamespace(render=render)
    monkeypatch.setattr(renderer._render_engines, "current_render_engine", lambda: engine)

    svg = renderer.render(
        score,
        color_map={"black": "#101010"},
        catalog_id="catalog",
        canvas_aspect="wide",
        svg_profile="editable",
        render_seed=17,
        composition_seed=23,
        wild=True,
    )

    assert svg == "<svg data-owner='current'/>"
    assert captured == {
        "score": score,
        "color_map": {"black": "#101010"},
        "catalog_id": "catalog",
        "canvas_aspect": "wide",
        "svg_profile": "editable",
        "render_seed": 17,
        "composition_seed": 23,
        "wild": True,
    }
