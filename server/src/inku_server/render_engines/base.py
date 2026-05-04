from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..schema import Score


@dataclass(frozen=True)
class RenderEngineResult:
    svg: str
    metadata: dict[str, str]


class RenderEngine(Protocol):
    id: str
    version: str

    def render(
        self,
        score: Score,
        *,
        color_map: dict[str, str] | None = None,
        svg_profile: str | None = None,
    ) -> RenderEngineResult:
        ...
