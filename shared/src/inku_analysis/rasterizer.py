"""SVG to PNG rasterization shared by the inku server and CLI.

The core wheel's ``inku_render.svg_to_png`` is the only backend.

cairosvg used to stand behind it for installations without resvg. It does not
implement feTurbulence / feDisplacementMap / feGaussianBlur, and rather than
failing it drops them: a filtered rect comes back as one flat colour. Every
material filter — the ground of every sheet, pencil, crayon, chalk, thick-brush —
vanishes from the PNG while remaining visible in a browser, and the PNG still
looks clean. A rasterizer that quietly returns the wrong picture is worse than
one that is missing, because a wrong picture gets used to decide things. It was,
repeatedly.

There is no fallback. Where the core wheel is absent, rasterizing raises.

This module is deliberately not re-exported from the package root: the analysis
mirror in ``__init__`` stays independent of rendering, and this is a rendering tool.
"""

from __future__ import annotations

import json
from typing import Callable

from .texture_fold import fold_texture_runs, should_fold

BACKEND_RESVG = "resvg"


class RasterizerUnavailable(RuntimeError):
    """The shared core rasterizer is not installed."""


def _resvg_renderer() -> Callable[..., bytes] | None:
    try:
        import inku_render
    except ImportError:
        return None
    if not callable(getattr(inku_render, "svg_to_png", None)):
        return None

    def render(
        svg: str,
        width: int | None,
        height: int | None,
        font_files: list[str] | None,
    ) -> bytes:
        kwargs: dict[str, object] = {}
        if width is not None:
            kwargs["width"] = width
        if height is not None:
            kwargs["height"] = height
        if font_files:
            kwargs["font_files"] = list(font_files)
        return bytes(inku_render.svg_to_png(svg, **kwargs))

    return render


def rasterizer_backend() -> str | None:
    """Return the backend name that would be used, or None when it is not installed.

    Not cached: tests swap the backend by patching ``sys.modules``, and the probe is
    a plain import lookup once the module is loaded.
    """
    return BACKEND_RESVG if _resvg_renderer() is not None else None


def rasterizer_info() -> dict[str, str]:
    """Identify the backend that would rasterize, for recording alongside PNG output.

    Two machines running different versions of resvg produce different pixels from
    the same SVG, so artifacts carry this to stay comparable. Returns an empty dict
    when the core wheel is not installed.
    """
    if rasterizer_backend() is None:
        return {}
    import inku_render
    return json.loads(inku_render.raster_identity_json())


def svg_to_png(
    svg: str,
    *,
    width: int | None = None,
    height: int | None = None,
    font_files: list[str] | None = None,
) -> bytes:
    """Rasterize ``svg`` to PNG bytes.

    Omitting both width and height renders at the SVG's intrinsic size; giving only
    one scales the other to preserve the aspect ratio. The background stays
    transparent unless the SVG paints one.

    ``font_files`` loads specific font files; the shared core never loads the
    host's system fonts. Text is reproducible across machines when the same
    files are given: the drawings themselves carry no text, but anything typeset
    around them does, and an installed-font lookup makes the output a property of
    the machine. A ``font-family`` in the SVG has to match the loaded font's
    typographic family name (name ID 16, falling back to ID 1) exactly -- an
    unmatched family draws nothing at all rather than substituting.

    Raises RasterizerUnavailable when the core wheel is not installed. There is no second
    backend to fall back to; see the module docstring for why.
    """
    render = _resvg_renderer()
    if render is None:
        raise RasterizerUnavailable(
            "the shared core PNG rasterizer is not available"
        )
    # Decided here rather than by the callers: there are nine places that
    # rasterize, and a flag any one of them could forget is a flag some of them
    # would. The size is only known here anyway. See `texture_fold` for what the
    # boundary is and what was measured to put it there.
    if should_fold(width, height):
        svg = fold_texture_runs(svg)
    return render(svg, width, height, font_files)
