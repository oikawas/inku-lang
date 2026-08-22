from __future__ import annotations

from dataclasses import dataclass

from ...schema import Score
from ..base import RenderEngineResult
from . import engine


@dataclass(frozen=True)
class DefaultRenderEngine:
    id: str = engine.ENGINE_ID
    version: str = engine.ENGINE_VERSION

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
        return engine.render_result(
            score,
            color_map=color_map,
            catalog_id=catalog_id,
            canvas_aspect=canvas_aspect,
            svg_profile=svg_profile,
            render_seed=render_seed,
            composition_seed=composition_seed,
            wild=wild,
        )


DEFAULT_RENDER_ENGINE = DefaultRenderEngine()
