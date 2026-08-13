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
        catalog_id: str | None = None,
        # The support to perform on. `None` performs on the one the Score
        # declares; a value overrules it without editing the Score, which is
        # how a composition can be drawn on a paper it did not compose for and
        # still say so.
        canvas_aspect: str | None = None,
        svg_profile: str | None = None,
        render_seed: int | None = None,
        composition_seed: int | None = None,
        wild: bool = False,
    ) -> RenderEngineResult:
        ...
