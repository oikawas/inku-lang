"""Render engine registry.

The current implementation intentionally keeps engine loading static.  This
module defines the boundary where future render engines can be registered
without changing API or history metadata contracts.
"""

from __future__ import annotations

from .base import RenderEngine, RenderEngineResult
from .default import DEFAULT_RENDER_ENGINE
from .default.adapter import _bind_renderer


def _render_svg(*args: object, **kwargs: object) -> str:
    from ..renderer import render

    return render(*args, **kwargs)


def _build_texture_metadata(*args: object, **kwargs: object) -> dict:
    from ..renderer import build_texture_metadata

    return build_texture_metadata(*args, **kwargs)


_bind_renderer(render=_render_svg, texture_metadata=_build_texture_metadata)


def current_render_engine() -> RenderEngine:
    return DEFAULT_RENDER_ENGINE


__all__ = [
    "DEFAULT_RENDER_ENGINE",
    "RenderEngine",
    "RenderEngineResult",
    "current_render_engine",
]
