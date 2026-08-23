"""Legacy SVG-only compatibility entrypoint.

The canonical engine returns SVG and render metadata together. Existing callers
that need only SVG may continue to use :func:`render`; domain implementation
symbols belong to their modules under ``render_engines.default``.
"""

from __future__ import annotations

from .render_engines.default import engine as _engine
from .schema import Score as _Score

__all__ = ("render",)


def render(
    score: _Score,
    color_map: dict[str, str] | None = None,
    *,
    catalog_id: str | None = None,
    canvas_aspect: str | None = None,
    svg_profile: str | None = None,
    render_seed: int | None = None,
    composition_seed: int | None = None,
    wild: bool = False,
) -> str:
    """Render a Score and return only the canonical engine's SVG."""

    return _engine.render_result(
        score,
        color_map=color_map,
        catalog_id=catalog_id,
        canvas_aspect=canvas_aspect,
        svg_profile=svg_profile,
        render_seed=render_seed,
        composition_seed=composition_seed,
        wild=wild,
    ).svg
