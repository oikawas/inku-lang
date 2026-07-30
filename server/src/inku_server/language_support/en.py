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

COERCE_MARKERS = {
    "material_weight_hints": (
        (("rotring",), "rotring"),
        (("pencil",), "pencil"),
        (("crayon",), "crayon"),
        (("chalk",), "chalk"),
        (("fine-brush", "fine brush"), "brush_thin"),
        (("thick-brush", "thick brush"), "brush_thick"),
        (("ink-wash", "ink wash"), "brush_thin"),
    ),
    "color_markers": (
        (("white",), "white"),
        (("black", "dark", "shadow", "ink"), "black"),
        (("blue", "sky", "water", "lake", "sea", "rain", "cold"), "blue"),
        (("red",), "red"),
        (("green", "forest", "leaf", "grass", "moss", "bamboo", "garden", "scent", "fragrance"), "green"),
        (("gray", "grey"), "gray"),
        (("yellow", "gold"), "yellow"),
        (("orange", "lantern"), "orange"),
        (("purple", "violet", "lilac"), "purple"),
    ),
    "negated_color_markers": {
        "green": ("not green", "avoid green", "without green", "no green"),
    },
    "shape_intent_markers": (
        (("polygon", "crystal", "mineral", "hard shard"), "polygon"),
        (("mountain", "sharp", "peak", "ridge", "triangle"), "triangle"),
        (("arc", "spiral", "coil", "curl", "ripple"), "arc"),
        (("paper", "fragment", "fold", "shard", "square"), "square"),
    ),
    "motif_intent_markers": (
        (("leaf", "fallen leaves", "autumn leaves", "dry leaves"), "leaf_cluster"),
        (("paper", "fragment", "shard", "letter"), "paper_shard"),
        (("ripple", "spiral", "coil"), "ripple_knot"),
        (("mountain", "ridge", "peak"), "mountain_sign"),
    ),
    "atmospheric_effect": (
        "membrane", "haze", "fog", "mist", "atmosphere", "soft light", "scent", "fragrance",
        "five-sense", "reflection",
    ),
    "quiet_density": (
        # "one " was here and matched the number itself: "one hundred twenty lines"
        # tripped the quiet-density governor and lost the very count it asked for.
        "quiet", "silence", "negative space", "thin", "pale", "slight", "single",
        "presence", "trace", "memory", "forgotten", "shadow", "cold", "transparent", "membrane",
        "haze", "fog", "mist", "blur", "low cloud", "pressing down",
    ),
    "vertical_density": ("rain", "snow", "falling", "vertical", "top to bottom"),
    "motion": (
        "moving", "sway", "flow", "fade", "dissolve", "stretch", "turn", "wind", "wave",
        "goes home first", "returns first", "low cloud", "pressing down", "shadow only", "blur", "tear",
        "trembling", "single drop", "remain", "remains", "drift", "drifts", "drifting",
        "pull", "pulls", "toward", "upper-right focus",
        "before", "after", "again and again", "as if", "at once", "bow", "bows", "sound", "sounds",
        "wake", "rose", "raised", "appeared", "disappeared", "returned", "shifted",
        "whistle", "whistled", "dog moved", "flock moved", "listen", "tilted", "lit up", "bell",
        "moved his feet", "under the table", "father did", "father's father", "line of birds",
        "grandmother", "planted", "mango", "tree still stands",
    ),
    "colorful": ("festival", "colored paper", "fruit", "neon", "sunset", "colorful", "multi-color"),
    "leaf_grain": ("leaf", "autumn forest", "fallen leaves", "autumn leaves", "dry leaves"),
    "silence_layer": ("abandoned school", "corridor", "long silence"),
    "hard_edge": (
        "factory", "steel frame", "rust", "girder", "warehouse", "grid", "cut", "cuts", "brick",
        "parking-lot", "parking lot", "rectangle",
    ),
    "playful_motion": ("bicycle", "slope", "petal", "colored paper", "wind chime"),
    "edge_light": ("night", "black", "dark", "lighthouse", "only light", "sea", "glass", "neon"),
    "strong_edge_light": ("lighthouse", "only light", "cutting light", "single beam"),
    "vanishing_trace": ("breath", "footprint", "fade", "fading", "dissolve", "outline", "memory", "trace", "far"),
    "rhythm": (
        "rhythm", "dance", "dancers", "moved his feet", "under the table", "bounce", "alternating", "playful", "joy", "celebration",
        "quilt", "patchwork", "handmade", "folk",
    ),
    "visual_event": (
        "collision", "burst", "focus", "turning point", "pop", "release",
        "wandering", "fading", "trembling", "single drop", "goes home first", "curling",
        "low cloud", "pressing down", "shadow only", "blur", "tear",
        "breath", "reflect", "reflection", "reflections", "lighthouse", "only light", "footprint", "outline",
        "unravel", "petal", "quiet", "negative space", "horizon", "prairie", "open road",
        "jazz", "syncopated", "backbeat", "blue-note", "improvised",
        "dark pause", "pause", "transparent reflections", "bus-stop window",
        "quilt", "patchwork", "handmade", "folk", "scent", "fragrance", "grass", "parking-lot", "parking lot",
        "diagonal", "rectangle", "red interruption", "chalk", "dust",
        "before", "after", "again and again", "as if", "at once", "bow", "bows", "sound", "sounds",
        "wake", "cloth", "applause", "rose", "river surface", "another road", "same beat", "shifted",
        "appeared", "disappeared", "returned", "slightly changed", "whistle", "whistled", "dog moved",
        "flock moved", "listen", "drop", "tatami", "tilted", "whole room", "departure board", "lit up", "bell",
        "moved his feet", "under the table", "father did", "father's father", "line of birds",
        "grandmother", "planted", "mango", "tree still stands",
    ),
    "ma_pressure": (
        "negative space", "ma", "empty space", "presence", "pull", "push", "avoid",
        "paper", "newspaper", "letter", "sheet", "wind", "crossing", "wander", "drift",
        "horizon", "prairie", "open road",
        "jazz", "syncopated", "blue-note", "city corner",
        "dark pause", "pause", "transparent", "reflections", "sparse", "dust", "chalk",
        "before", "after", "again and again", "as if", "at once", "bow", "sounds", "wake", "cloth",
        "river surface", "another road", "whistle", "flock", "tatami", "whole room", "under the table",
    ),
    "semantic_visual_event_hints": (
        (("open road", "upper-right focus"), "visual event preserved as a road-pull focus accent"),
        (("blue-note", "dark pause", "pause"), "visual event preserved as a blue-note pause accent"),
        (
            ("transparent reflection", "transparent reflections", "transparent membrane", "transparent", "faint reflection", "reflection"),
            "visual event preserved as a reflected accent",
        ),
        (("red interruption", "interruption"), "visual event preserved as a small interruption accent"),
        (("brick wall dust", "chalk", "dust"), "visual event preserved as chalk dust tension"),
        (("before", "after", "again and again", "as if", "at once"), "visual event preserved as temporal hinge"),
        (("bow", "bows", "sound", "sounds", "wake", "cloth", "applause"), "visual event preserved as action residue"),
        (("whistled", "dog moved", "flock moved", "listen"), "visual event preserved as chain reaction"),
        (("drop", "tatami", "tilted", "whole room"), "visual event preserved as tilted-room drop"),
        (("departure board", "lit up", "bell"), "visual event preserved as pre-bell light hinge"),
        (("festival", "dancers", "moved his feet", "under the table"), "visual event preserved as hidden foot rhythm"),
        (("bows", "father did", "father's father", "each morning"), "visual event preserved as three-generation bow sequence"),
        (("line of birds", "river surface", "another road"), "visual event preserved as doubled river road"),
    ),
    "surface_tension": ("cloth", "fabric", "fruit", "heavy", "weight", "shadow", "sink"),
    "intentional_large_surface": ("large", "huge", "wide", "broad surface", "cloth", "fabric"),
    "generated_background_plan": ("presence", "transparent membrane", "five-sense", "boundary blur", "full canvas"),
    "explicit_surface": (
        "background", "ground color", "full canvas", "fill the canvas", "night sky", "darkness", "dark field",
    ),
    "sunset_sky": ("sunset sky", "dusk sky"),
    "dawn": ("dawn", "daybreak", "sunrise"),
    "night": ("night",),
}


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


def expand_intermediate(
    ddl: str,
    context_text: str | None = None,
    composition_seed: int | None = None,
    *,
    plugin_instructions_present: bool = False,
    tenkei: str = "auto",
    focus: str | None = None,
    variation_amplitude: str | None = None,
    variation_seed: int | None = None,
    variation_report: dict | None = None,
) -> str:
    expanded = expand_intermediate_ddl(
        ddl,
        lang="en",
        context_text=context_text,
        composition_seed=composition_seed,
        plugin_instructions_present=plugin_instructions_present,
        tenkei=tenkei,
        focus=focus,
        variation_amplitude=variation_amplitude,
        variation_seed=variation_seed,
        variation_report=variation_report,
    )
    # v1.96: taste additions are recipes too — suppressed by the pair-transcription
    # guard (2a) and emitted only at the "auto" scenery level.
    if plugin_instructions_present or tenkei != "auto":
        return expanded
    return _append_sentences(expanded, _english_taste_additions(expanded, context_text))


SUPPORT = InstructionLanguageSupport(
    code="en",
    stage1_prompt=STAGE1_PROMPT,
    stage2_prompt=STAGE2_PROMPT,
    expand_intermediate=expand_intermediate,
    coerce_markers=COERCE_MARKERS,
)
