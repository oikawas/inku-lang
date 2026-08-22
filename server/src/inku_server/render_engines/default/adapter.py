from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...schema import Score
from ..base import RenderEngineResult

RenderSvg = Callable[..., str]
BuildTextureMetadata = Callable[..., dict[str, Any]]

render_svg: RenderSvg | None = None
build_texture_metadata: BuildTextureMetadata | None = None


def _bind_renderer(
    *,
    render: RenderSvg,
    texture_metadata: BuildTextureMetadata,
) -> None:
    """Bind the facade entrypoints without importing the facade from this package."""
    global render_svg, build_texture_metadata
    render_svg = render
    build_texture_metadata = texture_metadata


@dataclass(frozen=True)
class DefaultRenderEngine:
    id: str = "default"
    version: str = "40"

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
        if render_svg is None or build_texture_metadata is None:
            raise RuntimeError("default render engine facade is not bound")
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
