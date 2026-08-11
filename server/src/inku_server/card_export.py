"""Compose a work into a single shareable sheet: picture, headnote, seed, seal.

Typesetting happens here rather than in the browser because a card has to look
the same wherever it was made. A browser draws the headnote in whatever font the
viewer happens to have installed, so the same work would leave as a different
picture depending on the machine; here the bundled face travels with the server
and the CLI can produce the identical sheet.

The picture is nested rather than rasterized and pasted, so the whole card stays
one vector document until the single rasterization at the end.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape

from inku_analysis.rasterizer import svg_to_png

# The bundled face. resvg matches ``font-family`` against the font's typographic
# family name (name ID 16) -- name ID 1 of this variable font reads
# "Noto Serif JP ExtraLight" and matching against it draws nothing at all, so the
# two constants below have to stay in step with the file.
FONT_DIR = Path(__file__).parent / "fonts"
FONT_PATH = FONT_DIR / "NotoSerifJP-Variable.ttf"
FONT_FAMILY = "Noto Serif JP"

CardLayout = Literal["square", "portrait"]

# Square for a timeline that crops to 1:1, portrait for the 4:5 that both X and
# Instagram show at full height.
LAYOUT_SIZES: dict[str, tuple[int, int]] = {
    "square": (1080, 1080),
    "portrait": (1080, 1350),
}

MARGIN = 72
HEADNOTE_SIZE = 32
HEADNOTE_LINE_HEIGHT = 54
FOOTER_SIZE = 22
GAP = 40

# The headnote is the description the author typed, and it has no length limit.
# Past this many lines the text would crowd the picture out of its own card, so
# it is cut with an ellipsis; the picture keeps the majority of the sheet.
MAX_HEADNOTE_LINES = 6

INK = "#1b1a17"
SUBDUED = "#6b6558"
GROUND = "#fbfaf7"

_SVG_ROOT = re.compile(r"^\s*(?:<\?xml[^>]*\?>\s*)?<svg\b([^>]*)>", re.IGNORECASE)
_VIEWBOX = re.compile(r'\bviewBox\s*=\s*"([^"]*)"', re.IGNORECASE)
_WIDTH = re.compile(r'\bwidth\s*=\s*"([\d.]+)', re.IGNORECASE)
_HEIGHT = re.compile(r'\bheight\s*=\s*"([\d.]+)', re.IGNORECASE)


def _work_viewbox(svg: str) -> tuple[str, float]:
    """Return the work's viewBox and its aspect ratio (width / height)."""
    match = _SVG_ROOT.search(svg)
    attrs = match.group(1) if match else ""
    box = _VIEWBOX.search(attrs)
    if box:
        parts = box.group(1).replace(",", " ").split()
        if len(parts) == 4:
            try:
                _, _, w, h = (float(p) for p in parts)
                if w > 0 and h > 0:
                    return box.group(1), w / h
            except ValueError:
                pass
    width = _WIDTH.search(attrs)
    height = _HEIGHT.search(attrs)
    if width and height:
        w, h = float(width.group(1)), float(height.group(1))
        if w > 0 and h > 0:
            return f"0 0 {width.group(1)} {height.group(1)}", w / h
    return "0 0 1000 1000", 1.0


def _work_body(svg: str) -> str:
    """The work's markup with its own root element stripped off."""
    match = _SVG_ROOT.search(svg)
    if not match:
        return svg
    body = svg[match.end():]
    close = body.rfind("</svg>")
    return body[:close] if close >= 0 else body


def _char_width(char: str) -> float:
    """Advance in em. Full-width forms take a full em, everything else half."""
    code = ord(char)
    if (
        0x1100 <= code <= 0x115F
        or 0x2E80 <= code <= 0xA4CF
        or 0xAC00 <= code <= 0xD7A3
        or 0xF900 <= code <= 0xFAFF
        or 0xFE30 <= code <= 0xFE6F
        or 0xFF00 <= code <= 0xFF60
        or 0xFFE0 <= code <= 0xFFE6
    ):
        return 1.0
    return 0.5


def wrap_headnote(text: str, *, max_em: float) -> list[str]:
    """Break the headnote into lines that fit ``max_em`` ems.

    Japanese breaks between characters and Latin between words, so a run of
    non-full-width characters is kept together until it no longer fits.
    """
    lines: list[str] = []
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not paragraph.strip():
            continue
        line, width = "", 0.0
        token, token_width = "", 0.0

        def flush_token(line: str, width: float, token: str, token_width: float):
            if not token:
                return line, width
            if width + token_width > max_em and line:
                lines.append(line)
                return token, token_width
            return line + token, width + token_width

        for char in paragraph:
            advance = _char_width(char)
            if advance == 1.0 or char.isspace():
                line, width = flush_token(line, width, token, token_width)
                token, token_width = "", 0.0
                if char.isspace() and not line:
                    continue
                if width + advance > max_em and line:
                    lines.append(line)
                    line, width = "", 0.0
                    if char.isspace():
                        continue
                line += char
                width += advance
            else:
                token += char
                token_width += advance
        line, width = flush_token(line, width, token, token_width)
        if line:
            lines.append(line)
    return lines


def _seed_tail(seed: int | str | None) -> str | None:
    """The last four digits of the seed, or None when the work carries no seed."""
    if seed is None:
        return None
    digits = "".join(ch for ch in str(seed) if ch.isdigit())
    if not digits:
        return None
    return digits[-4:].rjust(4, "0")


def compose_card_svg(
    svg: str,
    *,
    headnote: str = "",
    seed: int | str | None = None,
    layout: CardLayout = "square",
    seal: bool = True,
) -> str:
    """Lay the work out as a card and return the composed SVG document."""
    if layout not in LAYOUT_SIZES:
        raise ValueError(f"unknown layout: {layout!r}")
    width, height = LAYOUT_SIZES[layout]
    content_width = width - MARGIN * 2

    lines = wrap_headnote(headnote or "", max_em=content_width / HEADNOTE_SIZE)
    truncated = len(lines) > MAX_HEADNOTE_LINES
    if truncated:
        lines = lines[:MAX_HEADNOTE_LINES]
        lines[-1] = lines[-1][:-1] + "…" if len(lines[-1]) > 1 else "…"

    footer_baseline = height - MARGIN
    headnote_block = len(lines) * HEADNOTE_LINE_HEIGHT
    headnote_top = footer_baseline - FOOTER_SIZE - GAP - headnote_block

    frame_top = MARGIN
    frame_bottom = headnote_top - (GAP if lines else 0)
    frame_height = max(frame_bottom - frame_top, 1)

    viewbox, aspect = _work_viewbox(svg)
    fitted_width = min(content_width, frame_height * aspect)
    fitted_height = fitted_width / aspect if aspect else frame_height
    work_x = (width - fitted_width) / 2
    work_y = frame_top + (frame_height - fitted_height) / 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect id="inku_card_ground" x="0" y="0" width="{width}" height="{height}" fill="{GROUND}"/>',
        f'<svg id="inku_card_work" x="{work_x:.2f}" y="{work_y:.2f}" '
        f'width="{fitted_width:.2f}" height="{fitted_height:.2f}" '
        f'viewBox="{viewbox}" preserveAspectRatio="xMidYMid meet">{_work_body(svg)}</svg>',
    ]

    if lines:
        parts.append('<g id="inku_card_headnote">')
        for index, line in enumerate(lines):
            baseline = headnote_top + HEADNOTE_LINE_HEIGHT * (index + 1) - 12
            parts.append(
                f'<text x="{MARGIN}" y="{baseline}" font-family="{FONT_FAMILY}" '
                f'font-size="{HEADNOTE_SIZE}" fill="{INK}">{escape(line)}</text>'
            )
        parts.append("</g>")

    tail = _seed_tail(seed)
    if tail is not None:
        parts.append(
            f'<text id="inku_card_seed" x="{MARGIN}" y="{footer_baseline}" '
            f'font-family="{FONT_FAMILY}" font-size="{FOOTER_SIZE}" fill="{SUBDUED}" '
            f'letter-spacing="2">seed {tail}</text>'
        )

    if seal:
        parts.append(
            f'<text id="inku_card_seal" x="{width - MARGIN}" y="{footer_baseline}" '
            f'font-family="{FONT_FAMILY}" font-size="{FOOTER_SIZE}" fill="{SUBDUED}" '
            f'text-anchor="end" letter-spacing="4">inku</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def build_card(
    svg: str,
    *,
    headnote: str = "",
    seed: int | str | None = None,
    layout: CardLayout = "square",
    seal: bool = True,
) -> bytes:
    """Compose the card and rasterize it to PNG bytes at the layout's own size."""
    width, height = LAYOUT_SIZES[layout] if layout in LAYOUT_SIZES else (0, 0)
    if not width:
        raise ValueError(f"unknown layout: {layout!r}")
    document = compose_card_svg(
        svg, headnote=headnote, seed=seed, layout=layout, seal=seal
    )
    return svg_to_png(
        document,
        width=width,
        height=height,
        font_files=[str(FONT_PATH)],
        skip_system_fonts=True,
    )
