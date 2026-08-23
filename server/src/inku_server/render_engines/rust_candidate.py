"""Explicit shadow adapter for the Rust Render Engine 41 candidate."""

from __future__ import annotations

import importlib
import json
from types import ModuleType

from ..schema import Score
from .base import RenderEngineResult
from .host import canonical_score_payload, resolved_canvas
from .profiles import normalize_svg_profile


def _native_binding() -> ModuleType:
    """Load the independent wheel only when the shadow candidate is invoked."""
    return importlib.import_module("inku_render")


def _default_color_map(native: ModuleType) -> dict[str, str]:
    payload = json.loads(native.default_color_map_json())
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in payload.items()
    ):
        raise RuntimeError("Rust default color map is not a string map")
    return payload


class RustCandidateRenderEngine:
    """Thin one-call adapter; all render semantics remain in the Rust core."""

    @property
    def id(self) -> str:
        return str(_native_binding().render_engine_id())

    @property
    def version(self) -> str:
        return str(_native_binding().render_engine_version())

    def render(
        self,
        score: Score,
        *,
        color_map: dict[str, str] | None = None,
        catalog_id: str | None = None,
        canvas_aspect: str | None = None,
        svg_profile: str | None = None,
        render_seed: int | None = None,
        composition_seed: int | None = None,
        wild: bool = False,
    ) -> RenderEngineResult:
        native = _native_binding()
        aspect, canvas = resolved_canvas(score, canvas_aspect)
        request = {
            "score": canonical_score_payload(score),
            "options": {
                "resolved_color_map": dict(color_map or _default_color_map(native)),
                "catalog_id": catalog_id,
                "canvas": {"width": canvas.width, "height": canvas.height},
                "canvas_aspect_id": aspect,
                "svg_profile": normalize_svg_profile(svg_profile),
                "render_seed": render_seed,
                "composition_seed": composition_seed,
                "wild": wild,
            },
        }
        svg, metadata_json = native.render(
            json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        )
        metadata = json.loads(metadata_json)
        if not isinstance(svg, str) or not isinstance(metadata, dict):
            raise RuntimeError("Rust render binding returned an invalid output boundary")
        return RenderEngineResult(svg=svg, metadata=metadata)


RUST_CANDIDATE_RENDER_ENGINE = RustCandidateRenderEngine()
