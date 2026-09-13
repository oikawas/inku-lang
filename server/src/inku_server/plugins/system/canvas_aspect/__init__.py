"""Canvas aspect system plugin."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from ....canvas_formats import canvas_format, canvas_format_ids, canvas_format_registry


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

_DISPLAY = {
    "square": ("Basic", "Square", "Standard square canvas"),
    "golden": ("Standard", "Golden Ratio", "Classical Western proportion"),
    "a4": ("Modern", "A4 Root Rectangle", "Modern print-oriented root rectangle"),
    "b4": ("Modern", "B4 Root Rectangle", "Modern print-oriented root rectangle"),
    "pillar": ("Classic JP", "Pillar", "Tall Japanese pillar-picture format"),
    "oban": ("Ukiyoe", "Oban", "Ukiyo-e oban woodblock proportion"),
    "wide": ("Cinema", "CinemaScope", "Wide cinematic panorama"),
    "byobu": ("Classic JP", "Byobu", "Japanese folding screen panel"),
    "vertical": ("Mobile", "Mobile Vertical", "Contemporary phone-screen format"),
    "sd_monitor": ("Display", "SD Monitor", "Traditional 4:3 display format"),
    "hd_monitor": ("Display", "HD Monitor", "Widescreen 16:9 display format"),
}


def _canvas_aspects() -> tuple[CanvasAspect, ...]:
    result: list[CanvasAspect] = []
    for item in canvas_format_registry().formats:
        category, label, intent = _DISPLAY.get(item.id, ("Other", item.id, item.id))
        result.append(
            CanvasAspect(
                item.id,
                category,
                label,
                float(item.width_units),
                float(item.height_units),
                intent,
            )
        )
    return tuple(result)


class _CanvasAspects(Sequence[CanvasAspect]):
    """Lazy compatibility view; registry identity stays in the Rust binding."""

    def __getitem__(self, index):
        return _canvas_aspects()[index]

    def __len__(self) -> int:
        return len(_canvas_aspects())

    def __iter__(self) -> Iterator[CanvasAspect]:
        return iter(_canvas_aspects())


CANVAS_ASPECTS: Sequence[CanvasAspect] = _CanvasAspects()


def canvas_aspect_ids() -> set[str]:
    return canvas_format_ids()


def normalize_canvas_aspect_id(value: str | None) -> str:
    if value in canvas_format_ids():
        return value
    return DEFAULT_CANVAS_ASPECT_ID


def canvas_aspect_ratio_for_aspect(value: str | None) -> float:
    item = canvas_format(normalize_canvas_aspect_id(value))
    return item.width_units / item.height_units


def canvas_size_for_aspect(value: str | None) -> CanvasSize:
    item = canvas_format(normalize_canvas_aspect_id(value))
    return CanvasSize(
        width=round(CANVAS_BASE_PX * item.width_units / item.height_units),
        height=CANVAS_BASE_PX,
    )
