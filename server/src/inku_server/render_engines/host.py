"""Implementation-neutral host preparation for render-engine requests."""

from __future__ import annotations

from typing import Any

from ..plugins import CanvasSize, canvas_size_for_aspect
from ..schema import CanvasSpec, Score


def score_canvas_aspect(score: Score) -> str:
    """Return the Score's declared aspect without consulting an engine."""
    if isinstance(score.canvas, CanvasSpec):
        return score.canvas.aspect
    return str(score.canvas or "square")


def resolved_canvas(score: Score, canvas_aspect: str | None) -> tuple[str, CanvasSize]:
    """Resolve the host-owned aspect catalog before crossing an engine boundary."""
    aspect = canvas_aspect or score_canvas_aspect(score)
    return aspect, canvas_size_for_aspect(aspect)


def canonical_score_payload(score: Score) -> dict[str, Any]:
    """Serialize a validated Score at the single native-engine handoff point."""
    return score.model_dump(mode="json", by_alias=True, exclude_none=False)
