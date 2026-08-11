"""Declarative DDL vocabulary plugin documents.

Plugin files are parsed as data.  Nothing in this module imports or executes
code from a plugin document.  Validation failures reject the whole document;
this is a document-format boundary, not a governor for generated works.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Iterable

from ..counts import _explicit_counts_from_ddl
from ..limits import DEFAULT_LIMITS
from ..saijiki import (
    RELATIONS,
    core_grammar_markers as saijiki_core_grammar_markers,
    saijiki_marker_table,
    shape_markers as saijiki_shape_markers,
)


PLUGIN_SUFFIX = ".inku-plugin.md"
MAX_ENTRY_INSTRUCTIONS = 48
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_ENTRY_RE = re.compile(r"^##\s+(?:語|Word)\s*:\s*(.+?)\s*$", re.IGNORECASE)
_TEMPLATE_RE = re.compile(
    r"^###\s+(展開|Expansion)(?:\s*[:(]?\s*(ja|en)\s*\)?)?\s*$",
    re.IGNORECASE,
)
# v1.92 で saijiki 導出へ置換: en 反復単位を複数語対応で拡張 (A-5)。多語単位は
# 単語単位より先に並べる (leaf forms を forms より前に置く)。箇所/spots は anchor
# 反復 (A-6) 用。単数形は単位保存 (_singular_for_unit)。単位語は reference §3 の
# repetition_range_regex がそのまま公開する。
# v1.94: en は数と単位の間に形容詞 1 語を許す（例: "5-7 tall blades"）。
# "to" の誤吸収を防ぐため介在語から to を除外する。ja 単位は文法上隣接のため不変。
_RANGE_RE = re.compile(
    r"(?P<low>\d+)\s*(?:[〜～-]|to)\s*(?P<high>\d+)\s*"
    r"(?:(?P<adj>(?!to\b)[A-Za-z][A-Za-z-]*)\s+)?"
    r"(?P<unit>leaf\ forms?|cloudforms?|forms?|blades?|spots?|arcs?"
    r"|marks?|items?|lines?|枚|個|本|箇所)",
    re.IGNORECASE,
)
# member 定義行 (A-2): `member 名前: 定義` / `member name: definition`
_MEMBER_RE = re.compile(r"^member\s+(?P<name>.+?)\s*[:：]\s*(?P<definition>.+)$", re.IGNORECASE)
# コメント行 (v2 delta §3): `注: …` / `note: …`。展開・閉包検査の対象外。
_COMMENT_RE = re.compile(r"^(?:注|note)\s*[:：]\s*(?P<body>.*)$", re.IGNORECASE)
# anchor 反復 (A-6) の箇所単位。
_ANCHOR_SPOT_UNITS = ("箇所", "spot", "spots")
_FIXED_COORD_RE = re.compile(
    r"(?:\[|\()\s*0?\.\d+\s*,\s*0?\.\d+(?:\s*,\s*0?\.\d+\s*,\s*0?\.\d+)?\s*(?:\]|\))"
)
_PLUGIN_REFERENCE_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Z][A-Za-z0-9_-]*\.[^\s、。,;:]+")
_EXTERNAL_REFERENCE_RE = re.compile(
    r"(?:https?://|file://|(?:^|\s)(?:\.\.?/|/)[^\s]+)",
    re.IGNORECASE,
)
_RESERVED_NAMESPACES = {
    "core",
    "form",
    "forms",
    "touch",
    "touches",
    "color",
    "colors",
    "place",
    "places",
    "motion",
    "motions",
    "relation",
    "relations",
    "canvas",
    "score",
    "renderer",
}
# Core grammar markers: structural anchors + saijiki-derived shapes/verbs/relations.
# v1.92: 語彙の所属は saijiki テーブル (saijiki.py) が単一情報源。構造マーカー
# (anchor / 領域) はプラグイン文書の文法であり、ここが所有する。
_STRUCTURAL_MARKERS = {
    "ja": ("anchor", "{領域:", "領域"),
    "en": ("anchor", "{region:", "region"),
}
_BASE_CORE_MARKERS = {
    lang: _STRUCTURAL_MARKERS[lang] + saijiki_core_grammar_markers(lang) for lang in ("ja", "en")
}
# 歳時記の修飾カテゴリ (material/color/variation/angle/ratio/place) — saijiki 導出。
_SAIJIKI_MARKERS = saijiki_marker_table()


def _merged_core_markers(lang: str) -> tuple[str, ...]:
    extra = tuple(word for category in _SAIJIKI_MARKERS.values() for word in category[lang])
    return _BASE_CORE_MARKERS[lang] + extra


_CORE_MARKERS = {"ja": _merged_core_markers("ja"), "en": _merged_core_markers("en")}
# Drawable primitive markers — a repetition line must name one of these or a
# defined member (A-2), otherwise it references an undefined shape.
_SHAPE_MARKERS = {"ja": saijiki_shape_markers("ja"), "en": saijiki_shape_markers("en")}
_REGIONS = {
    "上半分": (0.10, 0.08, 0.90, 0.48),
    "中域": (0.18, 0.24, 0.82, 0.76),
    "下の隅": (0.58, 0.62, 0.92, 0.92),
    "下端の帯": (0.06, 0.78, 0.94, 0.95),
    "upper half": (0.10, 0.08, 0.90, 0.48),
    "middle": (0.18, 0.24, 0.82, 0.76),
    "middle region": (0.18, 0.24, 0.82, 0.76),
    "lower corner": (0.58, 0.62, 0.92, 0.92),
    "bottom band": (0.06, 0.78, 0.94, 0.95),
}
# Diagonal-band keys (A-3): not a rectangle. Member sub-regions are laid along a
# descending diagonal at expansion time, so these resolve to a computation, not a
# fixed region. The bbox bounds the diagonal run.
_DIAGONAL_REGION_KEYS = frozenset(
    {
        "左上から右下への斜めの帯",
        "diagonal band, upper-left to lower-right",
    }
)
_DIAGONAL_BBOX = (0.10, 0.10, 0.90, 0.92)
_DEFAULT_REGION = (0.18, 0.24, 0.82, 0.76)
# Single source for the expansion-layer literals also surfaced by the reference
# dump. Keep these named so the mirror imports them instead of duplicating values.
ANCHOR_PREFIX = "anchor "
# Default fallback singular; unit-preserving singulars come from _singular_for_unit (A-5).
SINGULAR_MEMBER = {"ja": "一枚", "en": "one mark"}
METAPHOR_MARKERS = {
    "ja": ("のよう", "みたい", "比喩"),
    "en": ("like ", "as if", "metaphor"),
}


def _known_region_keys() -> frozenset[str]:
    return frozenset(key.lower() for key in _REGIONS) | frozenset(
        key.lower() for key in _DIAGONAL_REGION_KEYS
    )


def _singular_for_unit(unit: str | None, lang: str) -> str:
    """Unit-preserving singular for a repetition unit (A-5)."""
    if not unit:
        return SINGULAR_MEMBER[lang]
    if lang == "ja":
        return "一" + unit
    base = unit[:-1] if unit.lower().endswith("s") else unit
    return "one " + base


class PluginFormatError(ValueError):
    def __init__(self, reasons: Iterable[str]):
        self.reasons = tuple(str(reason) for reason in reasons)
        super().__init__("; ".join(self.reasons))


@dataclass(frozen=True)
class PluginManifest:
    namespace: str
    name: str
    version: str
    authors: tuple[str, ...]
    languages: tuple[str, ...]
    license: str
    description_ja: str
    description_en: str


@dataclass(frozen=True)
class PluginEntry:
    heading: str
    surfaces: dict[str, tuple[str, ...]]
    fires_on: dict[str, tuple[str, ...]]
    notes: dict[str, str]
    templates: dict[str, tuple[str, ...]]
    members: dict[str, dict[str, str]] = field(default_factory=dict)
    comments: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def qualified_name(self, namespace: str) -> str:
        return f"{namespace}.{self.heading}"


@dataclass(frozen=True)
class PluginDocument:
    manifest: PluginManifest
    entries: tuple[PluginEntry, ...]
    source_path: str | None = None


@dataclass(frozen=True)
class PluginExpansionResult:
    ddl: str
    provenance: tuple[dict[str, str], ...] = ()
    warnings: tuple[str, ...] = ()
    # v1.94 輪1: 対 member（relation literal を含む member 定義）の決定的転写。
    # 機械が書いた member 文は LLM を通さず、ここに Score instruction 断片として
    # 確定する（DDL テキストからは除外される）。coerce の対象にもしない。
    instructions: tuple[dict, ...] = ()


@dataclass(frozen=True)
class PluginLoadItem:
    name: str
    namespace: str
    version: str
    status: str
    path: str
    entries: tuple[dict[str, object], ...] = ()
    reasons: tuple[str, ...] = ()
    enabled: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.path,
            "name": self.name,
            "namespace": self.namespace,
            "version": self.version,
            "status": self.status,
            "path": self.path,
            "entries": list(self.entries),
            "reasons": list(self.reasons),
            "enabled": self.enabled,
        }


def _parse_scalar(value: str) -> object:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return [item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()]
    return value.strip("\"'")


def _parse_front_matter(text: str) -> tuple[dict[str, object], str]:
    normalized = text.replace("\r\n", "\n").lstrip("\ufeff")
    if not normalized.startswith("---\n"):
        raise PluginFormatError(["front matter must start with ---"])
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise PluginFormatError(["front matter must end with ---"])
    values: dict[str, object] = {}
    reasons: list[str] = []
    for number, line in enumerate(normalized[4:end].splitlines(), start=2):
        if not line.strip():
            continue
        if ":" not in line:
            reasons.append(f"front matter line {number} must contain ':'")
            continue
        key, raw = line.split(":", 1)
        values[key.strip()] = _parse_scalar(raw)
    if reasons:
        raise PluginFormatError(reasons)
    return values, normalized[end + 5 :]


def _split_values(value: str, separator: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(separator) if item.strip())


def _build_manifest(values: dict[str, object]) -> PluginManifest:
    required = (
        "namespace",
        "name",
        "version",
        "authors",
        "languages",
        "license",
        "description_ja",
        "description_en",
    )
    reasons = [f"manifest field is required: {key}" for key in required if not values.get(key)]
    namespace = str(values.get("namespace") or "")
    name = str(values.get("name") or "")
    version = str(values.get("version") or "")
    authors_value = values.get("authors")
    languages_value = values.get("languages")
    authors = tuple(authors_value) if isinstance(authors_value, list) else ((str(authors_value),) if authors_value else ())
    languages = tuple(str(item).lower() for item in languages_value) if isinstance(languages_value, list) else ()
    if namespace and not _IDENTIFIER_RE.fullmatch(namespace):
        reasons.append("namespace must be an ASCII identifier")
    if namespace.lower() in _RESERVED_NAMESPACES:
        reasons.append(f"namespace conflicts with core vocabulary: {namespace}")
    if name and not _IDENTIFIER_RE.fullmatch(name):
        reasons.append("name must be an ASCII identifier")
    if version and not _SEMVER_RE.fullmatch(version):
        reasons.append("version must use semantic versioning")
    if not languages or any(lang not in {"ja", "en"} for lang in languages):
        reasons.append("languages must be a non-empty subset of [ja, en]")
    if reasons:
        raise PluginFormatError(reasons)
    return PluginManifest(
        namespace=namespace,
        name=name,
        version=version,
        authors=authors,
        languages=languages,
        license=str(values["license"]),
        description_ja=str(values["description_ja"]),
        description_en=str(values["description_en"]),
    )


def _instruction_budget(
    lines: tuple[str, ...],
    members: dict[str, str] | None = None,
    *,
    lang: str = "ja",
) -> int:
    total = 0
    for line in lines:
        if line.lower().startswith(ANCHOR_PREFIX):
            continue
        match = _RANGE_RE.search(line)
        if match is None:
            total += 1
            continue
        cost = int(match.group("high"))
        if members:
            # v1.94 対分離: member 参照行は member 定義のセグメント数ぶん膨らむ
            name = _referenced_member(line, members)
            if name is not None:
                cost *= len(_split_pair_segments(members[name].rstrip("。."), lang))
        total += cost
    return total


def _check_line_syntax(line: str, heading: str, reasons: list[str]) -> None:
    if _PLUGIN_REFERENCE_RE.search(line):
        reasons.append(f"{heading}: plugin references are forbidden in expansion: {line}")
    if _EXTERNAL_REFERENCE_RE.search(line):
        reasons.append(f"{heading}: URL and file references are forbidden in expansion: {line}")
    match = _RANGE_RE.search(line)
    if match and int(match.group("high")) > 1 and _FIXED_COORD_RE.search(line):
        reasons.append(f"{heading}: repeated members cannot use fixed coordinates")


def _validate_entry(entry: PluginEntry, manifest: PluginManifest) -> list[str]:
    reasons: list[str] = []
    for lang in manifest.languages:
        if not entry.surfaces.get(lang):
            reasons.append(f"{entry.heading}: surface_{lang} is required")
        if not entry.fires_on.get(lang):
            reasons.append(f"{entry.heading}: fires_on_{lang} is required")
        lines = entry.templates.get(lang)
        members = entry.members.get(lang, {})
        if not lines:
            reasons.append(f"{entry.heading}: expansion template for {lang} is required")
            continue
        budget = _instruction_budget(lines, members, lang=lang)
        if budget > MAX_ENTRY_INSTRUCTIONS:
            reasons.append(
                f"{entry.heading}: expansion budget {budget} exceeds {MAX_ENTRY_INSTRUCTIONS}"
            )
        # A-2: member definitions must themselves be core vocabulary.
        member_markers = tuple(members.keys())
        for name, definition in members.items():
            _check_line_syntax(definition, entry.heading, reasons)
            if not any(marker.lower() in definition.lower() for marker in _CORE_MARKERS[lang]):
                reasons.append(f"{entry.heading}: member '{name}' definition is outside core vocabulary: {definition}")
        for line in lines:
            _check_line_syntax(line, entry.heading, reasons)
            lower = line.lower()
            # A-4: unknown region keys are rejected at load time.
            key = _region_key_of(line)
            if key is not None and key.lower() not in _known_region_keys():
                reasons.append(f"{entry.heading}: unknown region key: {key}")
            allowed = _CORE_MARKERS[lang] + member_markers
            if not any(marker.lower() in lower for marker in allowed):
                reasons.append(f"{entry.heading}: expansion line is outside core vocabulary: {line}")
            # A-2: a repetition line must name a primitive or a defined member.
            if _RANGE_RE.search(line) and not line.lower().startswith(ANCHOR_PREFIX):
                shape_ok = any(m.lower() in lower for m in _SHAPE_MARKERS[lang]) or any(
                    name.lower() in lower for name in member_markers
                )
                if not shape_ok:
                    reasons.append(
                        f"{entry.heading}: repetition references an undefined member or non-core shape: {line}"
                    )
    return reasons


def parse_plugin_document(text: str, *, source_path: str | None = None) -> PluginDocument:
    values, body = _parse_front_matter(text)
    manifest = _build_manifest(values)
    entries: list[PluginEntry] = []
    current_heading: str | None = None
    fields: dict[str, str] = {}
    templates: dict[str, list[str]] = {}
    members: dict[str, dict[str, str]] = {}
    comments: dict[str, list[str]] = {}
    template_lang: str | None = None

    def finish_entry() -> None:
        nonlocal current_heading, fields, templates, members, comments, template_lang
        if current_heading is None:
            return
        entry = PluginEntry(
            heading=current_heading,
            surfaces={
                lang: _split_values(fields.get(f"surface_{lang}", ""), "|")
                for lang in ("ja", "en")
            },
            fires_on={
                lang: _split_values(fields.get(f"fires_on_{lang}", ""), ",")
                for lang in ("ja", "en")
            },
            notes={lang: fields.get(f"note_{lang}", "") for lang in ("ja", "en")},
            templates={lang: tuple(lines) for lang, lines in templates.items()},
            members={lang: dict(defs) for lang, defs in members.items()},
            comments={lang: tuple(items) for lang, items in comments.items()},
        )
        entries.append(entry)
        current_heading = None
        fields = {}
        templates = {}
        members = {}
        comments = {}
        template_lang = None

    reasons: list[str] = []
    for number, raw_line in enumerate(body.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        entry_match = _ENTRY_RE.match(line)
        if entry_match:
            finish_entry()
            current_heading = entry_match.group(1).strip()
            continue
        template_match = _TEMPLATE_RE.match(line)
        if template_match:
            if current_heading is None:
                reasons.append(f"body line {number}: expansion appears before an entry")
                continue
            template_lang = (template_match.group(2) or ("ja" if template_match.group(1) == "展開" else "en")).lower()
            templates.setdefault(template_lang, [])
            continue
        if current_heading is None:
            reasons.append(f"body line {number}: expected '## 語:' or '## Word:'")
            continue
        if template_lang is not None:
            member_match = _MEMBER_RE.match(line)
            if member_match:  # A-2: member definition
                members.setdefault(template_lang, {})[
                    member_match.group("name").strip()
                ] = member_match.group("definition").strip()
                continue
            comment_match = _COMMENT_RE.match(line)
            if comment_match:  # v2 delta §3: comment line, exempt from expansion/closure
                comments.setdefault(template_lang, []).append(comment_match.group("body").strip())
                continue
            templates[template_lang].append(line)
            continue
        if ":" not in line:
            reasons.append(f"body line {number}: entry field must contain ':'")
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    finish_entry()
    if not entries:
        reasons.append("at least one word entry is required")
    seen_headings: set[str] = set()
    for entry in entries:
        folded = entry.heading.casefold()
        if folded in seen_headings:
            reasons.append(f"duplicate word entry: {entry.heading}")
        seen_headings.add(folded)
        reasons.extend(_validate_entry(entry, manifest))
    if reasons:
        raise PluginFormatError(reasons)
    return PluginDocument(manifest=manifest, entries=tuple(entries), source_path=source_path)


def validate_plugin_document(text: str) -> PluginDocument:
    return parse_plugin_document(text)


def _stable_int(text: str, salt: str) -> int:
    digest = hashlib.sha256(f"{salt}:{text}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


_REGION_TOKEN_RE = re.compile(r"\{(?:領域|region)\s*:\s*([^}]+)\}", re.IGNORECASE)


def _line_has_region(line: str) -> bool:
    return _REGION_TOKEN_RE.search(line) is not None


def _region_key_of(line: str) -> str | None:
    match = _REGION_TOKEN_RE.search(line)
    return match.group(1).strip() if match else None


def _resolve_region_spec(
    line: str,
    fallback: tuple[float, float, float, float] | None,
    *,
    warnings: list[str],
    heading: str,
) -> tuple[str, tuple[float, float, float, float]]:
    """Resolve a line's region to ('rect', bbox) or ('diagonal', bbox).

    A-3: diagonal-band keys resolve to a computation, not a rectangle.
    A-4: an unknown key at runtime records a warning and falls back to the
    default band (no silent fallback). Load-time rejection is in _validate_entry.
    """
    key = _region_key_of(line)
    if key is None:
        return ("rect", fallback if fallback is not None else _DEFAULT_REGION)
    lowered = key.lower()
    if lowered in {k.lower() for k in _DIAGONAL_REGION_KEYS}:
        return ("diagonal", _DIAGONAL_BBOX)
    region = _REGIONS.get(lowered)
    if region is not None:
        return ("rect", region)
    warnings.append(f"{heading}: unknown region key at runtime, using default band: {key}")
    return ("rect", _DEFAULT_REGION)


def _format_region(region: tuple[float, float, float, float], *, lang: str) -> str:
    values = ", ".join(f"{value:.3f}" for value in region)
    return f"領域 [{values}]" if lang == "ja" else f"region [{values}]"


def _member_regions(
    region: tuple[float, float, float, float], count: int, seed_text: str
) -> list[tuple[tuple[float, float, float, float], int]]:
    x0, y0, x1, y1 = region
    horizontal = (x1 - x0) >= (y1 - y0)
    result: list[tuple[tuple[float, float, float, float], int]] = []
    for index in range(count):
        fraction = (index + 0.5) / count
        jitter = ((_stable_int(seed_text, f"member-{index}") % 2001) / 2000 - 0.5) * 0.08
        if horizontal:
            cx = x0 + (x1 - x0) * min(0.95, max(0.05, fraction + jitter))
            cy = (y0 + y1) / 2 + jitter * (y1 - y0)
        else:
            cx = (x0 + x1) / 2 + jitter * (x1 - x0)
            cy = y0 + (y1 - y0) * min(0.95, max(0.05, fraction + jitter))
        width = min(0.22, max(0.06, (x1 - x0) / max(2, count)))
        height = min(0.22, max(0.06, (y1 - y0) / 3))
        member = (
            max(0.0, cx - width / 2),
            max(0.0, cy - height / 2),
            min(1.0, cx + width / 2),
            min(1.0, cy + height / 2),
        )
        rotation = -35 + _stable_int(seed_text, f"rotation-{index}") % 71
        result.append((member, rotation))
    return result


def _diagonal_member_regions(
    count: int, seed_text: str
) -> list[tuple[tuple[float, float, float, float], int]]:
    """Lay member sub-regions along the descending diagonal (A-3).

    Upper-left to lower-right: x and y both increase along the run, so the band
    is a diagonal, not a rectangle. Equal spacing plus deterministic jitter.
    """
    x0, y0, x1, y1 = _DIAGONAL_BBOX
    result: list[tuple[tuple[float, float, float, float], int]] = []
    for index in range(count):
        fraction = (index + 0.5) / count
        jitter = ((_stable_int(seed_text, f"diag-{index}") % 2001) / 2000 - 0.5) * 0.08
        t = min(0.97, max(0.03, fraction + jitter))
        cx = x0 + (x1 - x0) * t
        cy = y0 + (y1 - y0) * t
        half = 0.06
        member = (
            max(0.0, cx - half),
            max(0.0, cy - half),
            min(1.0, cx + half),
            min(1.0, cy + half),
        )
        rotation = -35 + _stable_int(seed_text, f"diag-rot-{index}") % 71
        result.append((member, rotation))
    return result


def _anchor_spot_regions(
    band: tuple[float, float, float, float], count: int, seed_text: str
) -> list[tuple[float, float, float, float]]:
    """One vertical strip per anchor spot along the band (A-6).

    Each strip rises from the band upward, so members arranged inside it read as
    growing from that root. Spots are spread along the band's long axis.
    """
    x0, y0, x1, y1 = band
    top = min(y0, 0.30)
    result: list[tuple[float, float, float, float]] = []
    for index in range(count):
        fraction = (index + 0.5) / max(1, count)
        jitter = ((_stable_int(seed_text, f"spot-{index}") % 2001) / 2000 - 0.5) * 0.06
        cx = x0 + (x1 - x0) * min(0.94, max(0.06, fraction + jitter))
        result.append((max(0.0, cx - 0.13), top, min(1.0, cx + 0.13), y1))
    return result


def _referenced_member(line: str, members: dict[str, str]) -> str | None:
    """Longest defined member name that appears in the line, if any (A-2)."""
    hits = [name for name in members if name and name.lower() in line.lower()]
    return max(hits, key=len) if hits else None


def _resolve_count(match: "re.Match[str]", seed_text: str, salt: str) -> int:
    low, high = int(match.group("low")), int(match.group("high"))
    if low < 1 or high < low:
        raise PluginFormatError([f"invalid repetition range: {match.group(0)}"])
    return low + _stable_int(seed_text, salt) % (high - low + 1)


# v1.94 対分離: member 定義内の relation literal（前の弧に両端で触れる 等）
_RELATION_LITERALS = {
    "ja": tuple(lit for word in RELATIONS for lit in word.literals_ja),
    "en": tuple(lit for word in RELATIONS for lit in word.literals_en),
}


# v1.94 輪1: 対 member の決定的転写 ------------------------------------------

_SLIM_HINTS = ("膨らみは細く", "bulge kept slim")


def _pair_instructions(
    segments: list[str],
    member_regions: list[tuple[tuple[float, float, float, float], int]],
    *,
    seed_text: str,
    salt: str,
) -> list[dict]:
    """対 member（配置弧 + touching 弧）を Score instruction へ決定的に転写する。

    幾何は member region・回転・seed から導出し、掃引角は member ごとに揺らす
    （固定値のスタンプ化を避ける）。「膨らみは細く」ヒントは細い掃引へ写像する。
    place 弧は `at` を保持し、領域内の位置決めは従来どおり演奏（seed）に属する。
    weight / color は既定のまま返し、直後の様式行（素材で、色で。）が消費時に
    上書きする。
    """
    slim = any(h in seg for seg in segments for h in _SLIM_HINTS)
    out: list[dict] = []
    for index, (region, rotation) in enumerate(member_regions, start=1):
        x0, y0, x1, y1 = region
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        radius = round(0.45 * min(x1 - x0, y1 - y0), 4)
        h1 = _stable_int(seed_text, f"{salt}:span1:{index}")
        h2 = _stable_int(seed_text, f"{salt}:span2:{index}")
        if slim:
            span1, span2 = 40 + h1 % 20, 35 + h2 % 20
        else:
            span1, span2 = 55 + h1 % 30, 45 + h2 % 30
        start1 = 270 - span1 / 2
        out.append(
            {
                "primitive": "arc",
                "center": [round(cx, 4), round(cy, 4)],
                "radius": radius,
                "angle_start": float(round(start1)),
                "angle_end": float(round(start1 + span1)),
                "rotation": float(rotation),
                "at": {"region": [round(v, 4) for v in region]},
            }
        )
        start2 = 270 - span2 / 2
        out.append(
            {
                "primitive": "arc",
                "center": [round(cx, 4), round(cy, 4)],
                "radius": radius,
                "angle_start": float(round(start2)),
                "angle_end": float(round(start2 + span2)),
                "relation": {"type": "touching"},
            }
        )
    return out


def _parse_style_line(line: str, lang: str) -> dict[str, str] | None:
    """「ロットリングで、赤で。」/ "In rotring, in red." 型の純粋な様式行を解釈する。

    全 token が てざわり/いろ の表層語に解決できる場合だけ weight/color を返す。
    ひとつでも解決できなければ None（様式行として消費せず、テキストのまま残す）。
    """
    from ..saijiki import color_for_surface, weight_for_surface

    weights = weight_for_surface()
    colors = color_for_surface()
    text = line.strip().rstrip("。.")
    parts = text.split("、") if lang == "ja" else text.split(", ")
    resolved: dict[str, str] = {}
    for part in parts:
        part = part.strip()
        if lang == "ja":
            m = re.fullmatch(r"(.+?)で", part)
            token = m.group(1).strip() if m else None
        else:
            m = re.fullmatch(r"[Ii]n (.+)", part)
            token = m.group(1).strip() if m else None
        if token is None:
            return None
        if token in weights:
            resolved["weight"] = weights[token]
        elif token in colors:
            resolved["color"] = colors[token]
        else:
            return None
    return resolved or None


def _split_pair_segments(definition: str, lang: str) -> list[str]:
    """member 定義を relation literal 境界で対の要素へ分割する (v1.94 対分離).

    「弧を置き、前の弧に両端で触れる」のような対の定義を、各要素が独立した
    region 付き文になるよう分割する。これにより Stage 2 は member ごとに
    「配置弧 + touching 弧」の 2 instruction を書け、Build 590 の明示 region 数
    上限とも整合する（両文が region を持つため上限は自然に 2N になる）。
    relation literal を含まない定義は分割されない（従来どおり 1 文）。
    """
    literals = _RELATION_LITERALS[lang]
    separator = "、" if lang == "ja" else ", "
    segments: list[str] = []
    for part in definition.split(separator):
        if segments and any(lit in part for lit in literals):
            cleaned = part
            if lang == "en":
                for lead in ("and then ", "then ", "and "):
                    if cleaned.lower().startswith(lead):
                        cleaned = cleaned[len(lead):]
                        break
            segments.append(cleaned)
        elif segments:
            segments[-1] = segments[-1] + separator + part
        else:
            segments.append(part)
    return segments


def _member_suffix(region: tuple[float, float, float, float], rotation: int, index: int, *, lang: str) -> str:
    formatted = _format_region(region, lang=lang)
    if lang == "ja":
        return f" {formatted}に置き、回転は{rotation}度。"
    return f" Place member {index} in {formatted} with rotation {rotation} degrees."


def _expand_range_line(
    line: str,
    match: "re.Match[str]",
    kind: str,
    region: tuple[float, float, float, float],
    members: dict[str, str],
    *,
    lang: str,
    seed_text: str,
    salt: str,
) -> tuple[list[str], list[dict]]:
    count = _resolve_count(match, seed_text, f"count-{salt}")
    member_name = _referenced_member(line, members)
    if kind == "diagonal":
        member_regions = _diagonal_member_regions(count, f"{seed_text}:{salt}")
    else:
        member_regions = _member_regions(region, count, f"{seed_text}:{salt}")

    if member_name is not None:
        # A-2: inline the member definition at each member's region.
        # v1.94 対分離: relation literal を含む定義は対の各要素を独立文にする。
        segments = _split_pair_segments(members[member_name].rstrip("。."), lang)
        if len(segments) >= 2:
            # v1.94 輪1: 対 member は決定的転写（テキストは出力しない）
            return [], _pair_instructions(
                segments, member_regions, seed_text=seed_text, salt=salt
            )
        out: list[str] = []
        for index, (member_region, rotation) in enumerate(member_regions, start=1):
            suffix = _member_suffix(member_region, rotation, index, lang=lang)
            for segment in segments:
                out.append(segment + suffix)
        return out, []

    singular = _singular_for_unit(match.group("unit"), lang)  # A-5 unit-preserving
    adj = match.groupdict().get("adj")
    if adj and lang == "en" and singular.startswith("one "):
        singular = f"one {adj} " + singular[len("one "):]  # 例: one tall blade
    cleaned = re.sub(
        r"\{(?:領域|region)\s*:\s*[^}]+\}",
        _format_region(region, lang=lang),
        line[: match.start()] + singular + line[match.end() :],
        flags=re.IGNORECASE,
    )
    base = cleaned.rstrip("。.")

    return [
        base + _member_suffix(member_region, rotation, index, lang=lang)
        for index, (member_region, rotation) in enumerate(member_regions, start=1)
    ], []


def _expand_entry(
    entry: PluginEntry, *, lang: str, seed_text: str, warnings: list[str]
) -> tuple[str, list[dict]]:
    lines = entry.templates.get(lang, ())
    members = entry.members.get(lang, {})
    anchor_regions: list[tuple[float, float, float, float]] = [_DEFAULT_REGION]
    expanded: list[str] = []
    instructions: list[dict] = []
    pending_style_targets: list[dict] = []  # 直前の対 member 転写（様式行の適用先）
    for line_idx, line in enumerate(lines):
        # v1.94 輪1: 対 member 転写の直後の様式は消費して適用する。
        # 行頭の様式文（「鉛筆で、緑で。」）だけを消費し、続く運動句などの
        # 残余（「細かく震える。」）はテキストとして残す。
        if pending_style_targets:
            targets, pending_style_targets = pending_style_targets, []
            if lang == "ja":
                head, sep, rest = line.partition("。")
            else:
                head, sep, rest = line.partition(". ")
            style = _parse_style_line(head, lang)
            if style is not None:
                for ins in targets:
                    ins.update(style)
                rest = rest.strip()
                if not rest:
                    continue
                line = rest
        if line.lower().startswith(ANCHOR_PREFIX):
            kind, region = _resolve_region_spec(
                line, _DEFAULT_REGION, warnings=warnings, heading=entry.heading
            )
            band = region  # diagonal anchors collapse to their bbox as a band
            match = _RANGE_RE.search(line)
            if match is not None and match.group("unit").lower() in _ANCHOR_SPOT_UNITS:
                count = _resolve_count(match, seed_text, f"spots-{entry.heading}-{line_idx}")
                anchor_regions = _anchor_spot_regions(
                    band, count, f"{seed_text}:spots:{entry.heading}:{line_idx}"
                )
            else:
                anchor_regions = [band]
            continue

        match = _RANGE_RE.search(line)
        if match is None:
            kind, region = _resolve_region_spec(
                line, _DEFAULT_REGION, warnings=warnings, heading=entry.heading
            )
            cleaned = re.sub(
                r"\{(?:領域|region)\s*:\s*[^}]+\}",
                _format_region(region, lang=lang),
                line,
                flags=re.IGNORECASE,
            )
            expanded.append(cleaned)
            continue

        if _line_has_region(line):
            kind, region = _resolve_region_spec(
                line, _DEFAULT_REGION, warnings=warnings, heading=entry.heading
            )
            targets = [(kind, region)]
        else:
            # A-6: inherit each anchor spot; one member run per spot.
            targets = [("rect", spot) for spot in anchor_regions]

        line_instructions: list[dict] = []
        for spot_idx, (kind, region) in enumerate(targets):
            text_lines, instr_dicts = _expand_range_line(
                line,
                match,
                kind,
                region,
                members,
                lang=lang,
                seed_text=seed_text,
                salt=f"{entry.heading}:{line_idx}:{spot_idx}",
            )
            expanded.extend(text_lines)
            line_instructions.extend(instr_dicts)
        if line_instructions:
            instructions.extend(line_instructions)
            pending_style_targets = line_instructions

    if _instruction_budget(tuple(expanded)) + len(instructions) > MAX_ENTRY_INSTRUCTIONS:
        raise PluginFormatError([f"{entry.heading}: runtime expansion exceeds {MAX_ENTRY_INSTRUCTIONS}"])
    separator = "" if lang == "ja" else " "
    ending = "。" if lang == "ja" else "."
    text = separator.join(part if part.endswith(("。", ".", "!", "?")) else part + ending for part in expanded)
    return text, instructions


def _phrase_positions(source_folded: str, phrase_folded: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        index = source_folded.find(phrase_folded, start)
        if index < 0:
            return positions
        positions.append(index)
        start = index + 1


def _is_metaphorical_at(source_folded: str, index: int, length: int, *, lang: str) -> bool:
    window = source_folded[max(0, index - 16) : index + length + 16]
    markers = METAPHOR_MARKERS.get(lang, METAPHOR_MARKERS["en"])
    return any(marker in window for marker in markers)


def _sentences_of(text: str, *, lang: str) -> list[str]:
    if lang == "ja":
        return [part.strip() for part in re.split(r"(?<=。)", text) if part.strip()]
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _strip_qualified_sentence(ddl: str, qualified: str, *, lang: str) -> str:
    sentences = _sentences_of(ddl, lang=lang)
    return ("" if lang == "ja" else " ").join(part for part in sentences if qualified.casefold() not in part.casefold())


# The count belongs to the phrase the plugin is named in, not to the whole
# sentence.  Measured on the seven upstream misses (2026-08-11): read at sentence
# granularity, five of the seven sentences hold a second count -- a `一つ` or `一本`
# belonging to some other object -- and the ambiguity rule then leaves every one of
# them at one unit.  At phrase granularity the count beside the reference is alone
# in its phrase, and the three that fit the work budget come true.
_PHRASE_BOUNDARY = re.compile(r"(?<=[。、；;])|(?<=[.!?,])\s+")


def _phrases_of(text: str, *, lang: str) -> list[str]:
    return [part.strip() for part in _PHRASE_BOUNDARY.split(text) if part and part.strip()]


def _phrase_that_names(text: str, marker: str, *, lang: str) -> str | None:
    """The phrase the plugin is named in -- where the body states how many."""
    if not text or not marker:
        return None
    folded = marker.casefold()
    for phrase in _phrases_of(text, lang=lang):
        if folded in phrase.casefold():
            return phrase
    return None


def _stated_unit_count(clause: str | None) -> int | None:
    """How many whole units the body asked for, or None if it did not say.

    Ruling A (2026-08-11): what a plugin offers is one unit, and a count in the
    body means "that whole, N times".  The reader is the shared one in `..counts`,
    so this layer and the coerce layer answer "how many did the description say"
    the same way and a hole in the reader cannot be fixed on one side only.

    A phrase stating more than one count is left at one unit: which of them is the
    unit count is not decidable here, and choosing would place a number nobody
    wrote.
    """
    stated = _explicit_counts_from_ddl(clause)
    if len(stated) != 1:
        return None
    value = next(iter(stated))
    return value if value > 1 else None


def _expansion_cost(text: str, instructions: list[dict], *, lang: str) -> int:
    """What one unit costs the work: transcribed instructions plus expanded lines."""
    return len(instructions) + len(_sentences_of(text, lang=lang))


def expand_plugin_ddl(
    ddl: str,
    *,
    source_text: str | None,
    lang: str,
    documents: Iterable[PluginDocument],
    seed_text: str | None = None,
) -> PluginExpansionResult:
    result = ddl
    provenance: list[dict[str, str]] = []
    warnings: list[str] = []
    instructions: list[dict] = []
    source = source_text or ""
    source_folded = source.casefold()
    result_folded = result.casefold()

    # A-7: gather firing candidates, then keep the longest match at each position.
    explicit_fires: dict[tuple[int, int], str] = {}
    phrase_candidates: list[tuple[int, int, int, int, str]] = []
    entry_index: dict[tuple[int, int], tuple[PluginDocument, PluginEntry, str]] = {}
    for document in documents:
        for entry in document.entries:
            qualified = entry.qualified_name(document.manifest.namespace)
            key = (id(document), id(entry))
            entry_index[key] = (document, entry, qualified)
            if qualified.casefold() in result_folded or qualified.casefold() in source_folded:
                explicit_fires[key] = qualified
                continue
            for phrase in entry.fires_on.get(lang, ()):
                folded = phrase.casefold()
                for index in _phrase_positions(source_folded, folded):
                    if _is_metaphorical_at(source_folded, index, len(folded), lang=lang):
                        continue
                    phrase_candidates.append((index, index + len(folded), key[0], key[1], phrase))

    phrase_candidates.sort(key=lambda candidate: (-(candidate[1] - candidate[0]), candidate[0]))
    accepted_spans: list[tuple[int, int]] = []
    accepted_trigger: dict[tuple[int, int], str] = {}
    for start, end, doc_id, entry_id, phrase in phrase_candidates:
        if any(not (end <= s or start >= e) for s, e in accepted_spans):
            continue  # overlaps a longer accepted match at the same position
        accepted_spans.append((start, end))
        accepted_trigger.setdefault((doc_id, entry_id), phrase)

    for document in documents:
        for entry in document.entries:
            key = (id(document), id(entry))
            qualified = entry.qualified_name(document.manifest.namespace)
            explicit = key in explicit_fires
            if explicit:
                trigger = explicit_fires[key]
            elif key in accepted_trigger:
                trigger = accepted_trigger[key]
            else:
                continue
            base = _strip_qualified_sentence(result, qualified, lang=lang) if explicit else result
            # `source` is not a fallback seed.  It is the sketch prose, which
            # Stage 0.5 rewrites on every run, so falling back to it would quietly
            # cost "the same description draws the same counts" -- and nothing
            # would turn red.  A caller that passes no seed lands on the DDL being
            # expanded, which is the fallback render.py already writes by hand.
            unit_seed = seed_text or result or qualified
            try:
                expansion, entry_instructions = _expand_entry(
                    entry,
                    lang=lang,
                    seed_text=unit_seed,
                    warnings=warnings,
                )
            except (KeyError, PluginFormatError) as exc:
                warnings.append(f"{qualified}: expansion dropped: {exc}")
                result = base or (
                    "黒い鉛筆の小さな弧を中域に置く。"
                    if lang == "ja"
                    else "Place a small black pencil arc in the middle region."
                )
                continue

            # Ruling A: the body says how many of the whole unit to place.  An
            # explicit reference states its count in the DDL clause that names the
            # plugin; a firing word states it in the description, which is the only
            # place that word appears at all.
            if explicit:
                phrase = _phrase_that_names(result, trigger, lang=lang) or _phrase_that_names(
                    source, trigger, lang=lang
                )
            else:
                phrase = _phrase_that_names(source, trigger, lang=lang)
            requested = _stated_unit_count(phrase)
            unit_cost = _expansion_cost(expansion, entry_instructions, lang=lang)
            expansions = [expansion]
            units = 1
            if requested is not None:
                budget = DEFAULT_LIMITS.max_expanded_primitives
                if unit_cost * requested > budget:
                    # A count that cannot be delivered whole is declined, never
                    # trimmed: a trimmed count is neither the one the description
                    # asked for nor one anybody else chose, and no reader of the
                    # Score could say what it means.
                    warnings.append(
                        f"{qualified}: {requested} units of {unit_cost} marks exceeds the "
                        f"{budget}-mark work budget; expansion kept at one unit"
                    )
                else:
                    for index in range(1, requested):
                        # Each unit resolves the plugin document's own range on its
                        # own seed.  Repeating one unit verbatim would hand the
                        # score N copies of one figure, which the duplicate repair
                        # would then collapse back to one.
                        try:
                            more_text, more_instructions = _expand_entry(
                                entry,
                                lang=lang,
                                seed_text=f"{unit_seed}#unit-{index}",
                                warnings=warnings,
                            )
                        except (KeyError, PluginFormatError) as exc:
                            warnings.append(
                                f"{qualified}: unit {index + 1} of {requested} dropped: {exc}"
                            )
                            break
                        expansions.append(more_text)
                        entry_instructions.extend(more_instructions)
                        units += 1
            joiner = "" if lang == "ja" else " "
            result = joiner.join(
                part for part in (base.strip(), *(text.strip() for text in expansions)) if part
            )
            instructions.extend(entry_instructions)
            provenance.append(
                {
                    "input_term": trigger,
                    "plugin_term": qualified,
                    "plugin_name": document.manifest.name,
                    "plugin_version": document.manifest.version,
                    # How many whole units the body asked for and got.  Declining an
                    # oversized count leaves this at 1, which is what tells a decline
                    # apart from a description that never stated a count.
                    "units": str(units),
                }
            )
    if _PLUGIN_REFERENCE_RE.search(result):
        # v1.94: fires_on 発火経路の drop 過敏の緩和。Stage 1 が混入させた
        # stray な名前空間参照は、展開全体ではなく当該文だけを警告付きで
        # 除去する（展開テンプレート自体はロード時に閉包検査済み）。
        if lang == "ja":
            sentences = [part for part in re.split(r"(?<=。)", result) if part.strip()]
            joiner = ""
        else:
            sentences = [part for part in re.split(r"(?<=[.!?])\s+", result) if part.strip()]
            joiner = " "
        kept = [part for part in sentences if not _PLUGIN_REFERENCE_RE.search(part)]
        removed = len(sentences) - len(kept)
        if kept:
            warnings.append(
                f"stray non-core reference removed from {removed} sentence(s); expansion kept"
            )
            result = joiner.join(part.strip() for part in kept)
        else:
            warnings.append("plugin expansion left a non-core reference; expansion was dropped")
            fallback = (
                "黒い鉛筆の小さな弧を中域に置く。"
                if lang == "ja"
                else "Place a small black pencil arc in the middle region."
            )
            return PluginExpansionResult(ddl=fallback, provenance=(), warnings=tuple(warnings))
    return PluginExpansionResult(
        ddl=result,
        provenance=tuple(provenance),
        warnings=tuple(warnings),
        instructions=tuple(instructions),
    )


class PluginDocumentManager:
    def __init__(self, directory: Path | None = None):
        default = Path(__file__).resolve().parents[3] / "plugins"
        self.directory = directory or Path(os.getenv("INKU_DOCUMENT_PLUGIN_DIR", default))
        self._lock = RLock()
        self._signature: tuple[tuple[str, int, int], ...] = ()
        self._documents: tuple[PluginDocument, ...] = ()
        self._items: tuple[PluginLoadItem, ...] = ()

    def _files(self) -> list[Path]:
        if not self.directory.exists():
            return []
        return sorted(self.directory.glob(f"*{PLUGIN_SUFFIX}"))

    def _current_signature(self) -> tuple[tuple[str, int, int], ...]:
        paths = list(self._files())
        state = self._state_path()
        if state.exists():
            paths.append(state)
        return tuple(
            (str(path), path.stat().st_mtime_ns, path.stat().st_size)
            for path in paths
        )

    def _state_path(self) -> Path:
        return self.directory / ".plugin-state.json"

    def _load_disabled(self) -> set[str]:
        try:
            raw = json.loads(self._state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        disabled = raw.get("disabled") if isinstance(raw, dict) else None
        if not isinstance(disabled, list):
            return set()
        return {entry for entry in disabled if isinstance(entry, str)}

    def _save_disabled(self, disabled: set[str]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._state_path().write_text(
            json.dumps({"disabled": sorted(disabled)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def reload(self, *, force: bool = True) -> tuple[PluginLoadItem, ...]:
        with self._lock:
            signature = self._current_signature()
            if not force and signature == self._signature:
                return self._items
            documents: list[PluginDocument] = []
            items: list[PluginLoadItem] = []
            identities: set[tuple[str, str]] = set()
            qualified_words: set[str] = set()
            disabled_ids = self._load_disabled()
            for path in self._files():
                enabled = path.name not in disabled_ids
                try:
                    document = parse_plugin_document(
                        path.read_text(encoding="utf-8"), source_path=str(path)
                    )
                    if not enabled:
                        # 無効化: 文書は残すが展開・語彙・衝突予約の対象にしない。
                        items.append(
                            PluginLoadItem(
                                name=document.manifest.name,
                                namespace=document.manifest.namespace,
                                version=document.manifest.version,
                                status="disabled",
                                path=path.name,
                                enabled=False,
                            )
                        )
                        continue
                    identity = (
                        document.manifest.namespace.casefold(),
                        document.manifest.name.casefold(),
                    )
                    qnames = {
                        entry.qualified_name(document.manifest.namespace).casefold()
                        for entry in document.entries
                    }
                    reasons: list[str] = []
                    if identity in identities:
                        reasons.append(
                            f"plugin identity collision: {document.manifest.namespace}.{document.manifest.name}"
                        )
                    collisions = sorted(qnames & qualified_words)
                    if collisions:
                        reasons.append(f"qualified word collision: {', '.join(collisions)}")
                    if reasons:
                        raise PluginFormatError(reasons)
                    identities.add(identity)
                    qualified_words.update(qnames)
                    documents.append(document)
                    items.append(
                        PluginLoadItem(
                            name=document.manifest.name,
                            namespace=document.manifest.namespace,
                            version=document.manifest.version,
                            status="enabled",
                            path=path.name,
                            entries=tuple(
                                {
                                    "qualified_name": entry.qualified_name(document.manifest.namespace),
                                    "surface_ja": list(entry.surfaces.get("ja", ())),
                                    "surface_en": list(entry.surfaces.get("en", ())),
                                    "note_ja": entry.notes.get("ja", ""),
                                    "note_en": entry.notes.get("en", ""),
                                }
                                for entry in document.entries
                            ),
                        )
                    )
                except (OSError, UnicodeError, PluginFormatError) as exc:
                    reasons = exc.reasons if isinstance(exc, PluginFormatError) else (str(exc),)
                    items.append(
                        PluginLoadItem(
                            name=path.name.removesuffix(PLUGIN_SUFFIX),
                            namespace="",
                            version="",
                            status="rejected",
                            path=path.name,
                            reasons=tuple(reasons),
                            enabled=enabled,
                        )
                    )
            self._signature = signature
            self._documents = tuple(documents)
            self._items = tuple(items)
            return self._items

    def items(self) -> tuple[PluginLoadItem, ...]:
        self.reload(force=False)
        return self._items

    def documents(self) -> tuple[PluginDocument, ...]:
        self.reload(force=False)
        return self._documents

    # --- 管理操作 (admin API 用): 例外は PluginFormatError=422 /
    # FileNotFoundError=404 / FileExistsError=409 に対応する。

    def _safe_plugin_path(self, plugin_id: str) -> Path:
        name = plugin_id.strip()
        if (
            not name
            or name != Path(name).name
            or not name.endswith(PLUGIN_SUFFIX)
            or name.startswith(".")
        ):
            raise PluginFormatError([f"invalid plugin id: {plugin_id!r}"])
        return self.directory / name

    @staticmethod
    def _derive_filename(document: PluginDocument) -> str:
        slug = f"{document.manifest.namespace}-{document.manifest.name}".lower()
        slug = re.sub(r"\s+", "-", slug)
        slug = re.sub(r"[^a-z0-9._-]", "", slug).strip("-.")
        if not slug:
            raise PluginFormatError(["cannot derive a filename from the plugin manifest"])
        return f"{slug}{PLUGIN_SUFFIX}"

    def item_for(self, plugin_id: str) -> PluginLoadItem | None:
        return next((item for item in self.items() if item.path == plugin_id), None)

    def content(self, plugin_id: str) -> str:
        with self._lock:
            path = self._safe_plugin_path(plugin_id)
            if not path.is_file():
                raise FileNotFoundError(plugin_id)
            return path.read_text(encoding="utf-8")

    def _write_and_reload(self, path: Path, content: str, *, previous: str | None) -> PluginLoadItem:
        # クロスファイル衝突は reload でしか判らず、ロード順によっては書き込んだ
        # ファイルではなく既存側が rejected になる。書き込み前の状態と比較し、
        # 新たな rejected を生む書き込みは丸ごと巻き戻す。
        self.reload(force=False)
        before = {item.path: item.status for item in self._items}
        path.write_text(content, encoding="utf-8")
        self.reload(force=True)
        item = next((it for it in self._items if it.path == path.name), None)
        newly_rejected = [
            it
            for it in self._items
            if it.status == "rejected" and before.get(it.path) not in (None, "rejected")
        ]
        if item is None or item.status == "rejected" or newly_rejected:
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(previous, encoding="utf-8")
            self.reload(force=True)
            reasons: list[str] = []
            if item is not None:
                reasons.extend(item.reasons)
            for other in newly_rejected:
                reasons.extend(f"{other.path}: {reason}" for reason in other.reasons)
            raise PluginFormatError(reasons or ["plugin failed to load"])
        return item

    def create(self, content: str, filename: str | None = None) -> PluginLoadItem:
        document = validate_plugin_document(content)
        with self._lock:
            name = filename if filename is not None else self._derive_filename(document)
            path = self._safe_plugin_path(name)
            if path.exists():
                raise FileExistsError(name)
            self.directory.mkdir(parents=True, exist_ok=True)
            return self._write_and_reload(path, content, previous=None)

    def update(self, plugin_id: str, content: str) -> PluginLoadItem:
        validate_plugin_document(content)
        with self._lock:
            path = self._safe_plugin_path(plugin_id)
            if not path.is_file():
                raise FileNotFoundError(plugin_id)
            previous = path.read_text(encoding="utf-8")
            return self._write_and_reload(path, content, previous=previous)

    def delete(self, plugin_id: str) -> None:
        with self._lock:
            path = self._safe_plugin_path(plugin_id)
            if not path.is_file():
                raise FileNotFoundError(plugin_id)
            path.unlink()
            disabled = self._load_disabled()
            if plugin_id in disabled:
                disabled.discard(plugin_id)
                self._save_disabled(disabled)
            self.reload(force=True)

    def set_enabled(self, plugin_id: str, enabled: bool) -> PluginLoadItem:
        with self._lock:
            path = self._safe_plugin_path(plugin_id)
            if not path.is_file():
                raise FileNotFoundError(plugin_id)
            disabled = self._load_disabled()
            if enabled:
                disabled.discard(plugin_id)
            else:
                disabled.add(plugin_id)
            self._save_disabled(disabled)
            self.reload(force=True)
            item = next((it for it in self._items if it.path == plugin_id), None)
            if item is None:
                raise FileNotFoundError(plugin_id)
            return item

    def qualified_names(self) -> tuple[str, ...]:
        names: list[str] = []
        for document in self.documents():
            for entry in document.entries:
                names.append(entry.qualified_name(document.manifest.namespace))
        return tuple(dict.fromkeys(names))

    def is_pure_invocation(self, text: str) -> bool:
        """入力がロード済み名前空間付き語と区切り記号だけで構成されるか (v1.96 純明示バイパス判定)。"""
        stripped = (text or "").strip()
        if not stripped:
            return False
        names = sorted(self.qualified_names(), key=len, reverse=True)
        if not names:
            return False
        remaining = stripped
        found = False
        for name in names:
            if name in remaining:
                found = True
                remaining = remaining.replace(name, " ")
        if not found:
            return False
        return re.fullmatch(r"[\s、。，,.．・]*", remaining) is not None

    def prompt_vocabulary(self, lang: str) -> tuple[str, ...]:
        terms: list[str] = []
        for document in self.documents():
            for entry in document.entries:
                terms.append(entry.qualified_name(document.manifest.namespace))
                terms.extend(entry.surfaces.get(lang, ()))
                terms.extend(entry.fires_on.get(lang, ()))
        return tuple(dict.fromkeys(terms))

    def expand(
        self,
        ddl: str,
        *,
        source_text: str | None,
        lang: str,
        seed_text: str | None = None,
    ) -> PluginExpansionResult:
        return expand_plugin_ddl(
            ddl,
            source_text=source_text,
            lang=lang,
            documents=self.documents(),
            seed_text=seed_text,
        )


DOCUMENT_PLUGIN_MANAGER = PluginDocumentManager()
