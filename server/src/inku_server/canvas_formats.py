"""Read the canonical canvas format registry from the shared Rust binding."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class CanvasFormat:
    id: str
    width_units: int
    height_units: int


@dataclass(frozen=True)
class CanvasFormatRegistry:
    schema: str
    digest: str
    formats: tuple[CanvasFormat, ...]


@lru_cache(maxsize=1)
def canvas_format_registry() -> CanvasFormatRegistry:
    # Import lazily: pipeline_runtime owns binding construction, while legacy
    # render modules import this compatibility adapter during API startup.
    from .pipeline_runtime import get_binding

    payload = get_binding().canvas_registry
    if not isinstance(payload, dict):
        raise RuntimeError("binding_canvas_registry_unavailable")
    registry = payload.get("registry")
    digest = payload.get("digest")
    if not isinstance(registry, dict) or not isinstance(digest, str) or not digest:
        raise RuntimeError("binding_canvas_registry_invalid")
    schema = registry.get("schema")
    raw_formats = registry.get("formats")
    if not isinstance(schema, str) or not isinstance(raw_formats, list):
        raise RuntimeError("binding_canvas_registry_invalid")
    formats: list[CanvasFormat] = []
    seen: set[str] = set()
    for raw in raw_formats:
        if not isinstance(raw, dict):
            raise RuntimeError("binding_canvas_registry_invalid")
        format_id = raw.get("id")
        width = raw.get("width_units")
        height = raw.get("height_units")
        if (
            not isinstance(format_id, str)
            or not format_id
            or format_id in seen
            or not isinstance(width, int)
            or isinstance(width, bool)
            or width <= 0
            or not isinstance(height, int)
            or isinstance(height, bool)
            or height <= 0
        ):
            raise RuntimeError("binding_canvas_registry_invalid")
        seen.add(format_id)
        formats.append(CanvasFormat(format_id, width, height))
    if "square" not in seen:
        raise RuntimeError("binding_canvas_registry_invalid")
    return CanvasFormatRegistry(schema=schema, digest=digest, formats=tuple(formats))


def canvas_format_ids() -> set[str]:
    return {item.id for item in canvas_format_registry().formats}


def canvas_format(value: str) -> CanvasFormat:
    for item in canvas_format_registry().formats:
        if item.id == value:
            return item
    raise KeyError(value)
