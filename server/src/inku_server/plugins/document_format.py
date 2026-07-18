"""Declarative DDL vocabulary plugin documents.

Plugin files are parsed as data.  Nothing in this module imports or executes
code from a plugin document.  Validation failures reject the whole document;
this is a document-format boundary, not a governor for generated works.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Iterable


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
_RANGE_RE = re.compile(
    r"(?P<low>\d+)\s*(?:[〜～-]|to)\s*(?P<high>\d+)\s*"
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
# Core grammar markers: structural anchors, shapes, verbs, relations.
_BASE_CORE_MARKERS = {
    "ja": (
        "anchor",
        "{領域:",
        "領域",
        "線",
        "円",
        "楕円",
        "三角",
        "四角",
        "多角形",
        "弧",
        "雲形",
        "置く",
        "引く",
        "並べる",
        "散らす",
        "敷き詰める",
        "描く",
        "埋める",
        "触れる",
        "沿う",
        "切る",
        "触れない",
        "間に",
    ),
    "en": (
        "anchor",
        "{region:",
        "region",
        "line",
        "circle",
        "ellipse",
        "triangle",
        "square",
        "polygon",
        "arc",
        "cloudform",
        "place",
        "draw",
        "arrange",
        "scatter",
        "tile",
        "fill",
        "touching",
        "along",
        "cutting",
        "not touching",
        "between",
    ),
}
# v1.92 で saijiki 導出へ置換: 歳時記の修飾カテゴリを marker として暫定追加 (A-1)。
# 語は reference §1 (Stage 1 プロンプトの Saijiki ブロック) を正とする。
_SAIJIKI_MARKERS = {
    "material": {
        "ja": ("髪", "鉛筆", "ペン", "ロットリング", "クレヨン", "チョーク", "細筆", "太筆", "ビュラン", "ドライポイント"),
        "en": ("hair", "pencil", "pen", "rotring", "crayon", "chalk", "fine-brush", "thick-brush", "burin", "drypoint"),
    },
    "color": {
        "ja": ("白", "黒", "青", "赤", "緑", "灰"),
        "en": ("white", "black", "blue", "red", "green", "gray"),
    },
    "variation": {
        "ja": ("細かく", "大きく", "ゆっくり", "速く", "揺れる", "波打つ", "震える", "滲む"),
        "en": ("fine", "large", "slowly", "quickly", "swaying", "undulating", "trembling", "blurring"),
    },
    "angle": {
        "ja": ("水平", "垂直", "斜め", "右上がり", "右下がり", "回転"),
        "en": ("horizontal", "vertical", "diagonal", "rising", "falling", "rotated"),
    },
    "ratio": {
        "ja": ("縦長", "横長", "全幅", "半幅", "半円", "上弦", "下弦", "三日月"),
        "en": ("tall", "wide", "full-width", "half-width", "semicircle", "waxing", "waning", "crescent"),
    },
    "place": {
        "ja": ("上", "下", "中央", "左端", "右端", "上端", "下端", "中心", "隅"),
        "en": ("top", "bottom", "center", "left-edge", "right-edge", "top-edge", "bottom-edge", "middle", "corner"),
    },
}


def _merged_core_markers(lang: str) -> tuple[str, ...]:
    extra = tuple(word for category in _SAIJIKI_MARKERS.values() for word in category[lang])
    return _BASE_CORE_MARKERS[lang] + extra


_CORE_MARKERS = {"ja": _merged_core_markers("ja"), "en": _merged_core_markers("en")}
# Drawable primitive markers — a repetition line must name one of these or a
# defined member (A-2), otherwise it references an undefined shape.
_SHAPE_MARKERS = {
    "ja": ("線", "円", "楕円", "三角", "四角", "多角形", "弧", "雲形"),
    "en": ("line", "circle", "ellipse", "triangle", "square", "polygon", "arc", "cloudform"),
}
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


@dataclass(frozen=True)
class PluginLoadItem:
    name: str
    namespace: str
    version: str
    status: str
    path: str
    entries: tuple[dict[str, object], ...] = ()
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "version": self.version,
            "status": self.status,
            "path": self.path,
            "entries": list(self.entries),
            "reasons": list(self.reasons),
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


def _instruction_budget(lines: tuple[str, ...]) -> int:
    total = 0
    for line in lines:
        if line.lower().startswith(ANCHOR_PREFIX):
            continue
        match = _RANGE_RE.search(line)
        total += int(match.group("high")) if match else 1
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
        budget = _instruction_budget(lines)
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
) -> list[str]:
    count = _resolve_count(match, seed_text, f"count-{salt}")
    member_name = _referenced_member(line, members)
    if kind == "diagonal":
        member_regions = _diagonal_member_regions(count, f"{seed_text}:{salt}")
    else:
        member_regions = _member_regions(region, count, f"{seed_text}:{salt}")

    if member_name is not None:
        # A-2: inline the member definition at each member's region.
        base = members[member_name].rstrip("。.")
    else:
        singular = _singular_for_unit(match.group("unit"), lang)  # A-5 unit-preserving
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
    ]


def _expand_entry(
    entry: PluginEntry, *, lang: str, seed_text: str, warnings: list[str]
) -> str:
    lines = entry.templates.get(lang, ())
    members = entry.members.get(lang, {})
    anchor_regions: list[tuple[float, float, float, float]] = [_DEFAULT_REGION]
    expanded: list[str] = []
    for line_idx, line in enumerate(lines):
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

        for spot_idx, (kind, region) in enumerate(targets):
            expanded.extend(
                _expand_range_line(
                    line,
                    match,
                    kind,
                    region,
                    members,
                    lang=lang,
                    seed_text=seed_text,
                    salt=f"{entry.heading}:{line_idx}:{spot_idx}",
                )
            )

    if _instruction_budget(tuple(expanded)) > MAX_ENTRY_INSTRUCTIONS:
        raise PluginFormatError([f"{entry.heading}: runtime expansion exceeds {MAX_ENTRY_INSTRUCTIONS}"])
    separator = "" if lang == "ja" else " "
    ending = "。" if lang == "ja" else "."
    return separator.join(part if part.endswith(("。", ".", "!", "?")) else part + ending for part in expanded)


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


def _strip_qualified_sentence(ddl: str, qualified: str, *, lang: str) -> str:
    if lang == "ja":
        sentences = [part.strip() for part in re.split(r"(?<=。)", ddl) if part.strip()]
    else:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", ddl) if part.strip()]
    return ("" if lang == "ja" else " ").join(part for part in sentences if qualified.casefold() not in part.casefold())


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
            try:
                expansion = _expand_entry(
                    entry,
                    lang=lang,
                    seed_text=seed_text or source or result or qualified,
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
            joiner = "" if lang == "ja" else " "
            result = joiner.join(part for part in (base.strip(), expansion.strip()) if part)
            provenance.append(
                {
                    "input_term": trigger,
                    "plugin_term": qualified,
                    "plugin_name": document.manifest.name,
                    "plugin_version": document.manifest.version,
                }
            )
    if _PLUGIN_REFERENCE_RE.search(result):
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
        return tuple(
            (str(path), path.stat().st_mtime_ns, path.stat().st_size)
            for path in self._files()
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
            for path in self._files():
                try:
                    document = parse_plugin_document(
                        path.read_text(encoding="utf-8"), source_path=str(path)
                    )
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
