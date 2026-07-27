"""SVG to PNG rasterization shared by the inku server and CLI.

**resvg is the only backend, and that is deliberate.**

cairosvg used to stand behind it for installations without resvg. It does not
implement feTurbulence / feDisplacementMap / feGaussianBlur, and rather than
failing it drops them: a filtered rect comes back as one flat colour. Every
material filter — the ground of every sheet, pencil, crayon, chalk, thick-brush —
vanishes from the PNG while remaining visible in a browser, and the PNG still
looks clean. A rasterizer that quietly returns the wrong picture is worse than
one that is missing, because a wrong picture gets used to decide things. It was,
repeatedly.

So there is no fallback. Where resvg is absent, rasterizing raises.

This module is deliberately not re-exported from the package root: the analysis
mirror in ``__init__`` stays independent of rendering, and this is a rendering tool.
"""

from __future__ import annotations

from typing import Callable

BACKEND_RESVG = "resvg"


class RasterizerUnavailable(RuntimeError):
    """resvg is not installed."""


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
    when resvg is not installed.
    """
    if rasterizer_backend() is None:
        return {}
    try:
        from importlib.metadata import version

        return {"backend": BACKEND_RESVG, "version": version("resvg-py")}
    except Exception:
        return {"backend": BACKEND_RESVG}


def svg_to_png(svg: str, *, width: int | None = None, height: int | None = None) -> bytes:
    """Rasterize ``svg`` to PNG bytes.

    Omitting both width and height renders at the SVG's intrinsic size; giving only
    one scales the other to preserve the aspect ratio. The background stays
    transparent unless the SVG paints one.

    Raises RasterizerUnavailable when resvg is not installed. There is no second
    backend to fall back to; see the module docstring for why.
    """
    render = _resvg_renderer()
    if render is None:
        raise RasterizerUnavailable(
            "resvg-py is not installed, and it is the only supported SVG rasterizer"
        )
    return render(svg, width, height)
