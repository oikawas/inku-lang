"""Machine-generated dump of in-implementation vocabulary and constant tables.

This module is a *mirror* of the implementation, not a source of truth. Every
value it emits is imported from the module that actually owns it, so the dump
cannot drift from behavior. It never participates in generation, acceptance, or
coercion — reading the reference has no effect on any produced work.

Sections (stable JSON keys):
    1 saijiki                — core vocabulary categories (ja/en) + plugin words
    2 normalized_ddl_phrases — relation literals, ground/background handling
    3 expansion_layer        — core markers, regions, repetition, plugin expansion
    4 score_schema           — pydantic JSON Schema + enums
    5 color_resolution       — core-6 colors per catalog
    6 weight_properties      — stroke width / dash / opacity / texture per weight
    7 performance            — canvas aspects, svg profiles, wobble tables, seeds
    8 verification           — geometry-assertion thresholds
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, get_args

from . import schema
from .color_catalogs import COLOR_KEYS, DEFAULT_COLOR_CATALOG_ID, color_catalogs
from .composer import (
    _COLOR_TERMS,
    _MOTION_OR_TEXTURE_TERMS,
    _PRIMITIVE_TERMS,
    _RELATION_LITERAL_MARKERS,
)
from .geometry_thresholds import (
    CLOSURE_LIMIT,
    CUSP_LIMIT_DEGREES,
    SAGITTA_RELATIVE_LIMIT,
)
from .saijiki import reference_categories as saijiki_reference_categories
from .plugins import (
    CANVAS_ASPECTS,
    DEFAULT_CANVAS_ASPECT_ID,
    plugin_status_items,
)
from .plugins.document_format import (
    ANCHOR_PREFIX,
    DOCUMENT_PLUGIN_MANAGER,
    MAX_ENTRY_INSTRUCTIONS,
    METAPHOR_MARKERS,
    SINGULAR_MEMBER,
    _CORE_MARKERS,
    _RANGE_RE,
    _REGIONS,
    _SAIJIKI_MARKERS,
)
from .plugins.system.canvas_aspect import CANVAS_BASE_PX
from .renderer import (
    AMPLITUDE_CLAMP_RATIO,
    AMPLITUDE_RATIO,
    BLUR_RATIO,
    CANVAS_PX,
    FREQUENCY_CYCLES,
    REPRESENTATIVE_MIN_RATIO,
    SEGMENT_COUNT_MAX,
    MIN_STROKE_WIDTH,
    SEGMENT_COUNT_MIN,
    SEGMENT_TARGET_RATIO,
    STYLE_TO_DASH,
    SVG_PROFILES,
    TEXTURE_FILTER_WEIGHTS,
    THINNESS_TO_WIDTH_SCALE,
    WEIGHT_STYLE,
    WEIGHT_TO_STROKE_WIDTH,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- #
# meta                                                                        #
# --------------------------------------------------------------------------- #
def _app_version() -> str | None:
    """Read web/APP_VERSION, the single source shared with the UI and /api/info.

    This used to scan +page.svelte for `const APP_VERSION = '...'`, which pinned
    that one line in a 7,400-line component: moving it broke the dump silently.
    """
    path = _REPO_ROOT / "web" / "APP_VERSION"
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _build_number() -> str | None:
    path = _REPO_ROOT / "web" / "BUILD_NUMBER"
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _git_short_hash() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _meta() -> dict[str, Any]:
    return {
        "app_version": _app_version(),
        "build_number": _build_number(),
        "git_short_hash": _git_short_hash(),
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "score_version": get_args(schema.ScoreVersion)[0],
        "plugins": [
            {
                "namespace": item.get("namespace"),
                "name": item.get("name"),
                "version": item.get("version"),
                "status": item.get("status"),
            }
            for item in plugin_status_items()
        ],
    }


# --------------------------------------------------------------------------- #
# §1 saijiki                                                                   #
# --------------------------------------------------------------------------- #
def _parse_saijiki_block(prompt: str, heading: str, separator: str) -> dict[str, list[str]]:
    """Extract the `category: value, value` block from a Stage 1 prompt string.

    The prompt string itself is the source of truth; nothing is hardcoded here.
    """
    lines = prompt.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index + 1
            break
    if start is None:
        return {}
    block: dict[str, list[str]] = {}
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            break
        if ":" not in stripped:
            continue
        key, _, raw = stripped.partition(":")
        values = [item.strip() for item in raw.split(separator) if item.strip()]
        if values:
            block[key.strip()] = values
    return block


def _plugin_words() -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for document in DOCUMENT_PLUGIN_MANAGER.documents():
        namespace = document.manifest.namespace
        for entry in document.entries:
            words.append(
                {
                    "qualified_name": entry.qualified_name(namespace),
                    "namespace": namespace,
                    "surface_ja": list(entry.surfaces.get("ja", ())),
                    "surface_en": list(entry.surfaces.get("en", ())),
                    "fires_on_ja": list(entry.fires_on.get("ja", ())),
                    "fires_on_en": list(entry.fires_on.get("en", ())),
                    "note_ja": entry.notes.get("ja", ""),
                    "note_en": entry.notes.get("en", ""),
                }
            )
    return words


def _saijiki() -> dict[str, Any]:
    # v1.92: saijiki テーブル (saijiki.py) を直接参照する。プロンプトのブロックは
    # 同じテーブルから生成されるため、_parse_saijiki_block による抽出結果と常に
    # 一致する (test_reference が両経路の同値を検査する)。
    return {
        "core_categories_ja": {
            name: list(words) for name, words in saijiki_reference_categories("ja")
        },
        "core_categories_en": {
            name: list(words) for name, words in saijiki_reference_categories("en")
        },
        "backing_enums": {
            "primitive": list(get_args(schema.Primitive)),
            "weight": list(get_args(schema.Weight)),
            "line_style": list(get_args(schema.LineStyle)),
            "color": list(get_args(schema.Color)),
            "amplitude": list(get_args(schema.Amplitude)),
            "frequency": list(get_args(schema.Frequency)),
            "quality": list(get_args(schema.Quality)),
        },
        "primitive_terms": {key: list(value) for key, value in _PRIMITIVE_TERMS.items()},
        "color_terms": {key: list(value) for key, value in _COLOR_TERMS.items()},
        "motion_or_texture_terms": list(_MOTION_OR_TEXTURE_TERMS),
        "plugin_words": _plugin_words(),
    }


# --------------------------------------------------------------------------- #
# §2 normalized_ddl_phrases                                                    #
# --------------------------------------------------------------------------- #
def _normalized_ddl_phrases() -> dict[str, Any]:
    return {
        "relation_literals": {
            relation_type: list(markers)
            for relation_type, markers in _RELATION_LITERAL_MARKERS.items()
        },
        "relation_enums": {
            "type": list(get_args(schema.RelationType)),
            "gap": list(get_args(schema.RelationGap)),
        },
        "ground_enums": {
            "material": list(get_args(schema.GroundMaterial)),
            "tone": list(get_args(schema.GroundTone)),
            "grain": list(get_args(schema.GroundGrain)),
        },
        "background_colors": list(get_args(schema.Color)),
        "notes": [
            "Stage 2 (composer) transcribes a relation only when a literal from "
            "relation_literals appears; relations are never inferred.",
            "Ground texture comes from a '地: ...' sentence and surface texture "
            "from a '面: ...' sentence; neither is inferred from scenery.",
            "background='gray' is refused; a gray subject stays a foreground "
            "color='gray' instead.",
        ],
    }


# --------------------------------------------------------------------------- #
# §3 expansion_layer                                                           #
# --------------------------------------------------------------------------- #
def _classify_marker(marker: str) -> str:
    lowered = marker.lower()
    if marker == ANCHOR_PREFIX.strip() or "領域" in marker or "region" in lowered:
        return "structural"
    primitive_surfaces = {
        term.lower() for terms in _PRIMITIVE_TERMS.values() for term in terms
    }
    if lowered in primitive_surfaces or marker in ("雲形", "cloudform"):
        return "shape"
    for category, langs in _SAIJIKI_MARKERS.items():
        if any(marker in words for words in langs.values()):
            return category  # material / color / variation / angle / ratio / place
    return "operation"


def _classified_markers(markers: tuple[str, ...]) -> list[dict[str, str]]:
    return [{"marker": marker, "class": _classify_marker(marker)} for marker in markers]


def _expansion_layer() -> dict[str, Any]:
    return {
        "core_markers": {
            "ja": _classified_markers(_CORE_MARKERS["ja"]),
            "en": _classified_markers(_CORE_MARKERS["en"]),
        },
        "regions": {key: list(value) for key, value in _REGIONS.items()},
        "repetition_range_regex": _RANGE_RE.pattern,
        "singular_member": dict(SINGULAR_MEMBER),
        "anchor_prefix": ANCHOR_PREFIX,
        "instruction_budget": {
            "max_entry_instructions": MAX_ENTRY_INSTRUCTIONS,
            "rule": (
                "Anchor lines cost 0; a line with a repetition range costs its "
                "upper bound; every other line costs 1. Both the parse-time and "
                "runtime expansions must stay within max_entry_instructions."
            ),
        },
        "fires_on_matching": {
            "order": [
                "Explicit namespaced word (e.g. Nature.wind) present in the DDL "
                "or the source text fires unconditionally.",
                "Otherwise a fires_on phrase present in the source text fires, "
                "unless it sits inside a metaphor window.",
            ],
            "metaphor_markers": {
                lang: list(markers) for lang, markers in METAPHOR_MARKERS.items()
            },
        },
    }


# --------------------------------------------------------------------------- #
# §4 score_schema                                                              #
# --------------------------------------------------------------------------- #
_ENUM_ALIASES = (
    "Primitive",
    "LineStyle",
    "Weight",
    "Color",
    "SurfaceTexture",
    "SurfaceDirection",
    "GroundMaterial",
    "GroundTone",
    "GroundGrain",
    "Amplitude",
    "Frequency",
    "Quality",
    "Dimension",
    "Layout",
    "Path",
    "Density",
    "Fade",
    "RhythmSpacing",
    "PresenceKind",
    "PresenceIntensity",
    "PresenceSymmetry",
    "GazePressure",
    "ContourDensity",
    "RelationType",
    "RelationGap",
    "InstructionMode",
    "CarveDepth",
    "SurfaceSpacingGradient",
)


def _score_schema() -> dict[str, Any]:
    return {
        "version": get_args(schema.ScoreVersion)[0],
        "enums": {
            name: list(get_args(getattr(schema, name))) for name in _ENUM_ALIASES
        },
        "json_schema": schema.Score.model_json_schema(),
    }


# --------------------------------------------------------------------------- #
# §5 color_resolution                                                          #
# --------------------------------------------------------------------------- #
def _color_resolution() -> dict[str, Any]:
    return {
        "core_keys": list(COLOR_KEYS),
        "default_catalog_id": DEFAULT_COLOR_CATALOG_ID,
        "catalogs": [
            {
                "id": catalog["id"],
                "name": catalog["name"],
                "map": {key: catalog["map"][key] for key in COLOR_KEYS},
            }
            for catalog in color_catalogs()
        ],
    }


# --------------------------------------------------------------------------- #
# §6 weight_properties                                                         #
# --------------------------------------------------------------------------- #
def _weight_properties() -> dict[str, Any]:
    weights: list[dict[str, Any]] = []
    for weight in get_args(schema.Weight):
        style = WEIGHT_STYLE.get(weight, {})
        weights.append(
            {
                "weight": weight,
                "stroke_width": WEIGHT_TO_STROKE_WIDTH[weight],
                "stroke_opacity": style.get("stroke_opacity"),
                "stroke_dasharray": style.get("stroke_dasharray"),
                "stroke_linecap": style.get("stroke_linecap"),
                "texture_filter": weight in TEXTURE_FILTER_WEIGHTS,
            }
        )
    return {
        "weights": weights,
        "line_style_dash": {style: STYLE_TO_DASH[style] for style in get_args(schema.LineStyle)},
        "texture_filter_weights": sorted(TEXTURE_FILTER_WEIGHTS),
        "thinness_width_scale": {
            str(key): value for key, value in THINNESS_TO_WIDTH_SCALE.items()
        },
        "min_stroke_width": MIN_STROKE_WIDTH,
        "canvas_px": CANVAS_PX,
    }


# --------------------------------------------------------------------------- #
# §7 performance                                                               #
# --------------------------------------------------------------------------- #
def _performance() -> dict[str, Any]:
    return {
        "canvas_aspects": [
            {
                "id": aspect.id,
                "category": aspect.category,
                "label": aspect.label,
                "ratio_w": aspect.ratio_w,
                "ratio_h": aspect.ratio_h,
                "intent": aspect.intent,
            }
            for aspect in CANVAS_ASPECTS
        ],
        "default_canvas_aspect_id": DEFAULT_CANVAS_ASPECT_ID,
        "canvas_base_px": CANVAS_BASE_PX,
        "svg_profiles": sorted(SVG_PROFILES),
        "amplitude_ratio": dict(AMPLITUDE_RATIO),
        "amplitude_clamp_ratio": AMPLITUDE_CLAMP_RATIO,
        "representative_min_ratio": REPRESENTATIVE_MIN_RATIO,
        "frequency_cycles": dict(FREQUENCY_CYCLES),
        "blur_ratio": dict(BLUR_RATIO),
        "segment_target_ratio": SEGMENT_TARGET_RATIO,
        "segment_count_range": [SEGMENT_COUNT_MIN, SEGMENT_COUNT_MAX],
        "default_anchor_region": list(_REGIONS["中域"]),
        "seed_summary": (
            "The JSON Score is deterministic; wobble and scatter are performed by "
            "the renderer from a performance seed (per-instruction, derived in "
            "renderer._seed_for_instruction). composition_seed re-salts intermediate "
            "expansion (expand_intermediate_ddl) to produce a sibling reading "
            "without changing the score's meaning."
        ),
    }


# --------------------------------------------------------------------------- #
# §8 verification                                                              #
# --------------------------------------------------------------------------- #
def _verification() -> dict[str, Any]:
    return {
        "geometry_thresholds": {
            "closure_limit": CLOSURE_LIMIT,
            "cusp_limit_degrees": CUSP_LIMIT_DEGREES,
            "sagitta_relative_limit": SAGITTA_RELATIVE_LIMIT,
        },
        "arc_guards": [
            "A touching arc pair uses the minor arc only: abs(minor_arc_delta) "
            "must stay below 180 degrees.",
            "An arc sagitta must be positive and smaller than half the chord.",
            "A touching relation pairs opposing apex sides so the pair reads as "
            "closed rather than as a smooth circle.",
        ],
    }


# --------------------------------------------------------------------------- #
# assembly                                                                     #
# --------------------------------------------------------------------------- #
def build_reference() -> dict[str, Any]:
    """Assemble the full reference as a JSON-serializable dict with stable keys."""
    return {
        "meta": _meta(),
        "saijiki": _saijiki(),
        "normalized_ddl_phrases": _normalized_ddl_phrases(),
        "expansion_layer": _expansion_layer(),
        "score_schema": _score_schema(),
        "color_resolution": _color_resolution(),
        "weight_properties": _weight_properties(),
        "performance": _performance(),
        "verification": _verification(),
    }


# --------------------------------------------------------------------------- #
# markdown rendering                                                           #
# --------------------------------------------------------------------------- #
def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    def cell(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)
        return str(value).replace("|", "\\|")

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(cell(value) for value in row) + " |")
    return lines


def render_markdown(reference: dict[str, Any] | None = None) -> str:
    ref = reference or build_reference()
    meta = ref["meta"]
    out: list[str] = ["# inku reference", ""]

    out.append(
        "> Machine-generated mirror of implementation tables. Read-only: it drives "
        "no generation or acceptance decision."
    )
    out.append("")
    out += _table(
        ["field", "value"],
        [
            ["app_version", meta["app_version"]],
            ["build_number", meta["build_number"]],
            ["git_short_hash", meta["git_short_hash"]],
            ["score_version", meta["score_version"]],
            ["generated_at", meta["generated_at"]],
        ],
    )
    out.append("")
    out.append("Loaded plugins:")
    out.append("")
    out += _table(
        ["namespace", "name", "version", "status"],
        [[p["namespace"], p["name"], p["version"], p["status"]] for p in meta["plugins"]],
    )
    out.append("")

    # §1 saijiki
    saijiki = ref["saijiki"]
    out.append("## 1. Saijiki (歳時記)")
    out.append("")
    out.append("### Core categories (ja)")
    out.append("")
    out += _table(
        ["category", "words"],
        [[key, values] for key, values in saijiki["core_categories_ja"].items()],
    )
    out.append("")
    out.append("### Core categories (en)")
    out.append("")
    out += _table(
        ["category", "words"],
        [[key, values] for key, values in saijiki["core_categories_en"].items()],
    )
    out.append("")
    out.append("### Backing enums")
    out.append("")
    out += _table(
        ["enum", "values"],
        [[key, values] for key, values in saijiki["backing_enums"].items()],
    )
    out.append("")
    if saijiki["plugin_words"]:
        out.append("### Plugin words")
        out.append("")
        out += _table(
            ["qualified_name", "surface_ja", "surface_en", "fires_on_ja", "fires_on_en", "note_ja", "note_en"],
            [
                [
                    word["qualified_name"],
                    word["surface_ja"],
                    word["surface_en"],
                    word["fires_on_ja"],
                    word["fires_on_en"],
                    word["note_ja"],
                    word["note_en"],
                ]
                for word in saijiki["plugin_words"]
            ],
        )
        out.append("")

    # §2 normalized DDL phrases
    phrases = ref["normalized_ddl_phrases"]
    out.append("## 2. Normalized DDL phrases")
    out.append("")
    out.append("### Relation literals (あいだ)")
    out.append("")
    out += _table(
        ["relation.type", "literal markers (ja/en)"],
        [[rtype, markers] for rtype, markers in phrases["relation_literals"].items()],
    )
    out.append("")
    out.append("### Relation / ground enums")
    out.append("")
    out += _table(
        ["enum", "values"],
        [[f"relation.{k}", v] for k, v in phrases["relation_enums"].items()]
        + [[f"ground.{k}", v] for k, v in phrases["ground_enums"].items()]
        + [["background", phrases["background_colors"]]],
    )
    out.append("")
    for note in phrases["notes"]:
        out.append(f"- {note}")
    out.append("")

    # §3 expansion layer
    expansion = ref["expansion_layer"]
    out.append("## 3. Expansion layer")
    out.append("")
    out.append("### Core markers")
    out.append("")
    for lang in ("ja", "en"):
        out.append(f"**{lang}**")
        out.append("")
        out += _table(
            ["marker", "class"],
            [[item["marker"], item["class"]] for item in expansion["core_markers"][lang]],
        )
        out.append("")
    out.append("### Regions")
    out.append("")
    out += _table(
        ["key", "region [x0,y0,x1,y1]"],
        [[key, value] for key, value in expansion["regions"].items()],
    )
    out.append("")
    out += _table(
        ["field", "value"],
        [
            ["repetition_range_regex", f"`{expansion['repetition_range_regex']}`"],
            ["singular_member", expansion["singular_member"]],
            ["anchor_prefix", f"`{expansion['anchor_prefix']}`"],
            ["max_entry_instructions", expansion["instruction_budget"]["max_entry_instructions"]],
        ],
    )
    out.append("")
    out.append(f"- Instruction budget: {expansion['instruction_budget']['rule']}")
    out.append(f"- fires_on order: {' '.join(expansion['fires_on_matching']['order'])}")
    out.append(
        "- Metaphor markers: "
        + "; ".join(
            f"{lang}: {', '.join(markers)}"
            for lang, markers in expansion["fires_on_matching"]["metaphor_markers"].items()
        )
    )
    out.append("")

    # §4 score schema
    score = ref["score_schema"]
    out.append("## 4. Score schema")
    out.append("")
    out.append(f"Score version: `{score['version']}`. Full JSON Schema is in the `--json` output.")
    out.append("")
    out += _table(
        ["enum", "values"],
        [[name, values] for name, values in score["enums"].items()],
    )
    out.append("")

    # §5 color resolution
    color = ref["color_resolution"]
    out.append("## 5. Color resolution")
    out.append("")
    out.append(f"Core keys: {', '.join(color['core_keys'])}. Default catalog: `{color['default_catalog_id']}`.")
    out.append("")
    out += _table(
        ["catalog"] + list(color["core_keys"]),
        [
            [catalog["name"]] + [catalog["map"][key] for key in color["core_keys"]]
            for catalog in color["catalogs"]
        ],
    )
    out.append("")

    # §6 weight properties
    weight = ref["weight_properties"]
    out.append("## 6. Weight properties")
    out.append("")
    out += _table(
        ["weight", "stroke_width", "stroke_opacity", "stroke_dasharray", "stroke_linecap", "texture_filter"],
        [
            [
                w["weight"],
                w["stroke_width"],
                w["stroke_opacity"],
                w["stroke_dasharray"],
                w["stroke_linecap"],
                w["texture_filter"],
            ]
            for w in weight["weights"]
        ],
    )
    out.append("")
    out += _table(
        ["line_style", "dasharray"],
        [[style, dash] for style, dash in weight["line_style_dash"].items()],
    )
    out.append("")

    # §7 performance
    performance = ref["performance"]
    out.append("## 7. Performance")
    out.append("")
    out += _table(
        ["id", "category", "label", "ratio_w", "ratio_h", "intent"],
        [
            [a["id"], a["category"], a["label"], a["ratio_w"], a["ratio_h"], a["intent"]]
            for a in performance["canvas_aspects"]
        ],
    )
    out.append("")
    out += _table(
        ["field", "value"],
        [
            ["default_canvas_aspect_id", performance["default_canvas_aspect_id"]],
            ["canvas_base_px", performance["canvas_base_px"]],
            ["svg_profiles", performance["svg_profiles"]],
            ["amplitude_ratio", performance["amplitude_ratio"]],
            ["amplitude_clamp_ratio", performance["amplitude_clamp_ratio"]],
            ["representative_min_ratio", performance["representative_min_ratio"]],
            ["frequency_cycles", performance["frequency_cycles"]],
            ["blur_ratio", performance["blur_ratio"]],
            ["segment_target_ratio", performance["segment_target_ratio"]],
            ["segment_count_range", performance["segment_count_range"]],
            ["default_anchor_region", performance["default_anchor_region"]],
        ],
    )
    out.append("")
    out.append(f"- Seeds: {performance['seed_summary']}")
    out.append("")

    # §8 verification
    verification = ref["verification"]
    out.append("## 8. Verification")
    out.append("")
    out += _table(
        ["threshold", "value"],
        [[key, value] for key, value in verification["geometry_thresholds"].items()],
    )
    out.append("")
    for guard in verification["arc_guards"]:
        out.append(f"- {guard}")
    out.append("")

    return "\n".join(out)
