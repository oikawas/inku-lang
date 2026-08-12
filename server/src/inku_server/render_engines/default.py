from __future__ import annotations

from dataclasses import dataclass

from ..renderer import build_texture_metadata, render as render_svg
from ..schema import Score
from .base import RenderEngineResult


@dataclass(frozen=True)
class DefaultRenderEngine:
    id: str = "default"
    version: str = "32"

    def render(
        self,
        score: Score,
        *,
        color_map: dict[str, str] | None = None,
        catalog_id: str | None = None,
        canvas_aspect: str | None = None,
        svg_profile: str | None = None,
        render_seed: int | None = None,
        composition_seed: int | None = None,
        wild: bool = False,
    ) -> RenderEngineResult:
        svg = render_svg(
            score,
            color_map=color_map,
            catalog_id=catalog_id,
            canvas_aspect=canvas_aspect,
            svg_profile=svg_profile,
            render_seed=render_seed,
            composition_seed=composition_seed,
            wild=wild,
        )
        return RenderEngineResult(
            svg=svg,
            metadata={
                "render_engine_id": self.id,
                "render_engine_version": self.version,
                **build_texture_metadata(score, svg_profile=svg_profile),
            },
        )


DEFAULT_RENDER_ENGINE = DefaultRenderEngine()
