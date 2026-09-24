"""Saved sketch metadata.

The retired Python Stage 0.5 producer rewrote the description. The shared
pipeline's sketch runs only when the author asks for it, supplements place and
light beside the description, and records `supplemented`, `not_needed`
(nothing to supplement), `fallback` or `off`. These small types remain because existing history rows and
request models still carry the state that older work recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field


SKETCH_GRAINS = ("fine", "coarse")
DEFAULT_SKETCH_GRAIN = "fine"
SKETCH_STATES = ("fine", "coarse", "fallback", "off", "not_applicable", "not_needed", "supplemented")


def normalize_sketch_grain(value: str | None) -> str:
    grain = str(value or "").strip().lower()
    return grain if grain in SKETCH_GRAINS else DEFAULT_SKETCH_GRAIN


@dataclass
class SketchDetail:
    text: str
    grain: str = DEFAULT_SKETCH_GRAIN
    tokens_in: int | None = None
    tokens_out: int | None = None
    fallback_used: bool = False
    fallback_reasons: list[str] = field(default_factory=list)
    raw: str | None = None
    prompt_digest: str | None = None


def sketch_state_of(
    detail: SketchDetail | None, *, requested: bool, has_description: bool
) -> str:
    if detail is not None:
        if detail.fallback_used:
            return "fallback"
        return normalize_sketch_grain(detail.grain)
    if not has_description:
        return "not_applicable"
    if requested:
        return "not_applicable"
    return "off"


def normalize_sketch_state(value: str | None) -> str | None:
    if value is None:
        return None
    state = str(value).strip().lower()
    return state if state in SKETCH_STATES else None
