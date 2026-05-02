"""Canvas aspect system plugin."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanvasAspect:
    id: str
    category: str
    label: str
    ratio_w: float
    ratio_h: float
    intent: str


@dataclass(frozen=True)
class CanvasSize:
    width: int
    height: int

    @property
    def unit(self) -> int:
        return min(self.width, self.height)


CANVAS_ASPECT_PLUGIN_ID = "canvas-aspect"
DEFAULT_CANVAS_ASPECT_ID = "square"
CANVAS_BASE_PX = 1000

CANVAS_ASPECTS: tuple[CanvasAspect, ...] = (
    CanvasAspect("square", "Basic", "Square", 1.0, 1.0, "Standard square canvas"),
    CanvasAspect("golden", "Standard", "Golden Ratio", 1.618, 1.0, "Classical Western proportion"),
    CanvasAspect("a4", "Modern", "A4 Root Rectangle", 1.0, 1.414, "Modern print-oriented root rectangle"),
    CanvasAspect("b4", "Modern", "B4 Root Rectangle", 1.0, 1.414, "Modern print-oriented root rectangle"),
    CanvasAspect("pillar", "Classic JP", "Pillar", 1.0, 5.0, "Tall Japanese pillar-picture format"),
    CanvasAspect("oban", "Ukiyoe", "Oban", 2.0, 3.0, "Ukiyo-e oban woodblock proportion"),
    CanvasAspect("wide", "Cinema", "CinemaScope", 2.35, 1.0, "Wide cinematic panorama"),
    CanvasAspect("byobu", "Classic JP", "Byobu", 2.2, 1.0, "Japanese folding screen panel based on one half of a six-panel pair"),
    CanvasAspect("vertical", "Mobile", "Mobile Vertical", 9.0, 16.0, "Contemporary phone-screen format"),
)

_CANVAS_ASPECT_BY_ID = {item.id: item for item in CANVAS_ASPECTS}


def canvas_aspect_ids() -> set[str]:
    return set(_CANVAS_ASPECT_BY_ID)


def normalize_canvas_aspect_id(value: str | None) -> str:
    if value in _CANVAS_ASPECT_BY_ID:
        return value
    return DEFAULT_CANVAS_ASPECT_ID


def canvas_size_for_aspect(value: str | None) -> CanvasSize:
    aspect = _CANVAS_ASPECT_BY_ID[normalize_canvas_aspect_id(value)]
    ratio = aspect.ratio_w / aspect.ratio_h
    if ratio >= 1:
        return CanvasSize(width=round(CANVAS_BASE_PX * ratio), height=CANVAS_BASE_PX)
    return CanvasSize(width=round(CANVAS_BASE_PX * ratio), height=CANVAS_BASE_PX)
