"""English instruction-language support."""

from __future__ import annotations

import hashlib
import re

from ..composer import SYSTEM_PROMPT_EN as STAGE2_PROMPT
from ..ddl_expander import expand_intermediate_ddl
from ..interpreter import SYSTEM_PROMPT_EN as STAGE1_PROMPT
from .base import InstructionLanguageSupport

_ENGLISH_TASTE_MARKERS = (
    "syncopated city rhythm",
    "blue-note value",
    "quilt-like patchwork",
    "subway-map pressure",
    "billboard edge",
    "prairie horizon",
    "coastal fog plane",
    "warehouse grid",
)


def _seed(text: str, salt: str) -> int:
    digest = hashlib.sha256(f"{salt}:{text}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _pick(candidates: list[str], count: int, *, text: str, salt: str) -> list[str]:
    ranked = sorted(candidates, key=lambda item: _seed(f"{text}:{item}", salt))
    return ranked[: min(count, len(ranked))]


def _append_sentences(text: str, additions: list[str]) -> str:
    if not additions:
        return text
    base = text.strip()
    if base and not base.endswith((".", "!", "?")):
        base += "."
    return " ".join([base, *additions]).strip()


def _has_terms(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if " " in term or "-" in term:
            if term in text:
                return True
            continue
        if re.search(rf"\b{re.escape(term)}\b", text):
            return True
    return False


def _english_taste_additions(expanded: str, context_text: str | None) -> list[str]:
    context = f"{context_text or ''}\n{expanded}".lower()
    if any(marker in context for marker in _ENGLISH_TASTE_MARKERS):
        return []

    additions: list[str] = []
    if _has_terms(context, ("jazz", "blues", "swing", "syncopation", "backbeat", "improvisation", "improvised")):
        additions.extend(
            _pick(
                [
                    "Line up seven short blue fine-brush lines left to right as syncopated city rhythm. Swaying slowly.",
                    "Place three thin gray arcs from a lower-right focus as blue-note value. Radius 0.08.",
                ],
                1,
                text=context,
                salt="en-jazz",
            )
        )
    if _has_terms(context, ("quilt", "patchwork", "porch", "domestic", "folk", "handmade")):
        additions.append("Line up nine small rotated squares in red, blue, green, gray as quilt-like patchwork.")
    if _has_terms(context, ("subway", "metro", "rail", "map", "crossing lines", "transit")):
        additions.append("Draw five thin rotring lines toward an upper-right focus as subway-map pressure.")
    if _has_terms(context, ("billboard", "neon", "sign", "highway", "motel", "parking lot")):
        additions.append("Place two large thin rectangles cut by a diagonal as billboard edge pressure.")
    if _has_terms(context, ("prairie", "plain", "horizon", "wide field", "open road", "dust bowl")):
        additions.append("Draw one long pale horizontal line near the lower third as prairie horizon.")
    if _has_terms(context, ("coastal fog", "atlantic", "pacific", "pier", "lighthouse", "harbor")):
        additions.append("Layer three pale blue watercolor ellipses along the upper edge as coastal fog plane. Edges blurring.")
    if _has_terms(context, ("warehouse", "loft", "factory", "brick", "fire escape", "grid window")):
        additions.append("Scatter four thin rotated gray squares in the right half as warehouse grid cuts.")
    return additions[:2]


def expand_intermediate(ddl: str, context_text: str | None = None) -> str:
    expanded = expand_intermediate_ddl(ddl, lang="en", context_text=context_text)
    return _append_sentences(expanded, _english_taste_additions(expanded, context_text))


SUPPORT = InstructionLanguageSupport(
    code="en",
    stage1_prompt=STAGE1_PROMPT,
    stage2_prompt=STAGE2_PROMPT,
    expand_intermediate=expand_intermediate,
)
