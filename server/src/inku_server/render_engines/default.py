from __future__ import annotations

from dataclasses import dataclass

from ..renderer import render as render_svg
from ..schema import Score
from .base import RenderEngineResult


@dataclass(frozen=True)
class DefaultRenderEngine:
    id: str = "default"
    version: str = "1"

    def render(
        self,
        score: Score,
        *,
        color_map: dict[str, str] | None = None,
        svg_profile: str | None = None,
    ) -> RenderEngineResult:
        svg = render_svg(score, color_map=color_map, svg_profile=svg_profile)
        return RenderEngineResult(
            svg=svg,
            metadata={
                "render_engine_id": self.id,
                "render_engine_version": self.version,
            },
        )


DEFAULT_RENDER_ENGINE = DefaultRenderEngine()
