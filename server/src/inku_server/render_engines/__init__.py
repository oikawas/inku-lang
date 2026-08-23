"""Render engine registry.

The current implementation intentionally keeps engine loading static.  This
module defines the boundary where future render engines can be registered
without changing API or history metadata contracts.
"""

from __future__ import annotations

from .base import RenderEngine, RenderEngineResult
from .default import DEFAULT_RENDER_ENGINE
from .profiles import SVG_PROFILES, normalize_svg_profile
from .seeds import new_render_seed


def current_render_engine() -> RenderEngine:
    return DEFAULT_RENDER_ENGINE


__all__ = [
    "DEFAULT_RENDER_ENGINE",
    "RenderEngine",
    "RenderEngineResult",
    "SVG_PROFILES",
    "current_render_engine",
    "new_render_seed",
    "normalize_svg_profile",
]
