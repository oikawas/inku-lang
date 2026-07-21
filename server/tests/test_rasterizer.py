import builtins

import pytest

from inku_analysis.rasterizer import (
    BACKEND_CAIROSVG,
    BACKEND_RESVG,
    RasterizerUnavailable,
    rasterizer_backend,
    svg_to_png,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

PLAIN_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">'
    '<circle cx="100" cy="100" r="60" fill="black"/>'
    "</svg>"
)

# The same circle behind the material filter the renderer emits for pencil / crayon /
# chalk / brush_thick.
FILTERED_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">'
    "<defs><filter id=\"grain\" x=\"-20%\" y=\"-20%\" width=\"140%\" height=\"140%\">"
    '<feTurbulence type="fractalNoise" baseFrequency="0.18" numOctaves="2" seed="7" result="noise"/>'
    '<feDisplacementMap in="SourceGraphic" in2="noise" scale="8"/>'
    "</filter></defs>"
    '<circle cx="100" cy="100" r="60" fill="black" filter="url(#grain)"/>'
    "</svg>"
)


def _block_imports(monkeypatch, *names):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in names:
            raise ImportError(f"missing {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_resvg_is_the_preferred_backend():
    assert rasterizer_backend() == BACKEND_RESVG


def test_falls_back_to_cairosvg_when_resvg_is_absent(monkeypatch):
    _block_imports(monkeypatch, "resvg_py")
    assert rasterizer_backend() == BACKEND_CAIROSVG
    assert svg_to_png(PLAIN_SVG, width=64).startswith(PNG_MAGIC)


def test_raises_when_no_backend_is_installed(monkeypatch):
    _block_imports(monkeypatch, "resvg_py", "cairosvg")
    assert rasterizer_backend() is None
    with pytest.raises(RasterizerUnavailable):
        svg_to_png(PLAIN_SVG, width=64)


@pytest.mark.parametrize(
    "kwargs, expected_prefix",
    [
        ({}, b"\x00\x00\x01\x90\x00\x00\x00\xc8"),  # intrinsic 400x200
        ({"width": 768}, b"\x00\x00\x03\x00\x00\x00\x01\x80"),  # 768x384, aspect kept
        ({"height": 768}, b"\x00\x00\x06\x00\x00\x00\x03\x00"),  # 1536x768, aspect kept
        ({"width": 768, "height": 384}, b"\x00\x00\x03\x00\x00\x00\x01\x80"),
    ],
)
def test_output_size_matches_between_backends(monkeypatch, kwargs, expected_prefix):
    """PNG IHDR carries width and height as big-endian uint32 at byte offset 16."""
    resvg_png = svg_to_png(PLAIN_SVG, **kwargs)
    assert resvg_png[16:24] == expected_prefix

    with monkeypatch.context() as ctx:
        _block_imports(ctx, "resvg_py")
        cairo_png = svg_to_png(PLAIN_SVG, **kwargs)
    assert cairo_png[16:24] == expected_prefix


def test_resvg_renders_material_filters_that_cairosvg_drops(monkeypatch):
    """The reason this module exists: cairosvg silently ignores feTurbulence /
    feDisplacementMap, so the filtered and unfiltered circles rasterize identically."""
    resvg_filtered = svg_to_png(FILTERED_SVG, width=256)
    resvg_plain = svg_to_png(PLAIN_SVG, width=256)

    with monkeypatch.context() as ctx:
        _block_imports(ctx, "resvg_py")
        cairo_filtered = svg_to_png(FILTERED_SVG, width=256)
        cairo_plain = svg_to_png(PLAIN_SVG, width=256)

    assert cairo_filtered == cairo_plain, "cairosvg was expected to drop the filter"
    assert resvg_filtered != resvg_plain, "resvg was expected to render the filter"
