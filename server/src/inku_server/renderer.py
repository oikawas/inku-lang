"""SVG-only compatibility entrypoint.

The canonical engine returns SVG and render metadata together. Existing callers
that need only SVG may continue to use :func:`render`; implementation details
remain behind the render-engine boundary.
"""

from __future__ import annotations

from . import render_engines as _render_engines
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

    return _render_engines.current_render_engine().render(
        score,
        color_map=color_map,
        catalog_id=catalog_id,
        canvas_aspect=canvas_aspect,
        svg_profile=svg_profile,
        render_seed=render_seed,
        composition_seed=composition_seed,
        wild=wild,
    ).svg
