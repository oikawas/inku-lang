"""Render engine registry.

The current implementation intentionally keeps engine loading static.  This
module defines the boundary where future render engines can be registered
without changing API or history metadata contracts.
"""

from __future__ import annotations

from .base import RenderEngine, RenderEngineResult
from .default import DEFAULT_RENDER_ENGINE


def current_render_engine() -> RenderEngine:
    return DEFAULT_RENDER_ENGINE


__all__ = [
    "DEFAULT_RENDER_ENGINE",
    "RenderEngine",
    "RenderEngineResult",
    "current_render_engine",
]
