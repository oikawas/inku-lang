"""SVG to PNG rasterization shared by the inku server and CLI.

cairosvg does not implement feTurbulence / feDisplacementMap / feGaussianBlur and
silently drops them, so the material filters (pencil, crayon, chalk, brush_thick)
disappear from every PNG path while remaining visible in the browser. resvg renders
all three, so it is preferred; cairosvg stays as a fallback for installations that
lack it. Both backends agree on intrinsic size, aspect-preserving scaling from a
single width or height, and a transparent background.

This module is deliberately not re-exported from the package root: the analysis
mirror in ``__init__`` stays independent of rendering, and this is a rendering tool.
"""

from __future__ import annotations

from typing import Callable

BACKEND_RESVG = "resvg"
BACKEND_CAIROSVG = "cairosvg"


class RasterizerUnavailable(RuntimeError):
    """No rasterizer backend is installed."""


def _resvg_renderer() -> Callable[..., bytes] | None:
    try:
        import resvg_py
    except ImportError:
        return None

    def render(svg: str, width: int | None, height: int | None) -> bytes:
        kwargs: dict[str, int] = {}
        if width is not None:
            kwargs["width"] = width
        if height is not None:
            kwargs["height"] = height
        return bytes(resvg_py.svg_to_bytes(svg_string=svg, **kwargs))

    return render


def _cairosvg_renderer() -> Callable[..., bytes] | None:
    try:
        import cairosvg
    except ImportError:
        return None

    def render(svg: str, width: int | None, height: int | None) -> bytes:
        kwargs: dict[str, int] = {}
        if width is not None:
            kwargs["output_width"] = width
        if height is not None:
            kwargs["output_height"] = height
        return cairosvg.svg2png(bytestring=svg.encode("utf-8"), **kwargs)

    return render


_BACKENDS = ((BACKEND_RESVG, _resvg_renderer), (BACKEND_CAIROSVG, _cairosvg_renderer))


def rasterizer_backend() -> str | None:
    """Return the backend name that would be used, or None when none is installed.

    Not cached: tests swap backends by patching ``sys.modules``, and the probe is a
    plain import lookup once the module is loaded.
    """
    for name, factory in _BACKENDS:
        if factory() is not None:
            return name
    return None


def svg_to_png(svg: str, *, width: int | None = None, height: int | None = None) -> bytes:
    """Rasterize ``svg`` to PNG bytes.

    Omitting both width and height renders at the SVG's intrinsic size; giving only
    one scales the other to preserve the aspect ratio. The background stays
    transparent unless the SVG paints one.

    Raises RasterizerUnavailable when neither backend is installed.
    """
    for _name, factory in _BACKENDS:
        render = factory()
        if render is not None:
            return render(svg, width, height)
    raise RasterizerUnavailable("no SVG rasterizer is installed (expected resvg-py or cairosvg)")
