"""Declarative DDL vocabulary plugin documents.

Plugin files are parsed as data.  Nothing in this module imports or executes
code from a plugin document.  Validation failures reject the whole document;
this is a document-format boundary, not a governor for generated works.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Iterable

from ..saijiki import (
    RELATIONS,
    core_grammar_markers as saijiki_core_grammar_markers,
    saijiki_marker_table,
    shape_markers as saijiki_shape_markers,
)


PLUGIN_SUFFIX = ".inku-plugin.md"
MAX_ENTRY_INSTRUCTIONS = 48
# v2.14: preview artwork is a raster, served by its own route rather than
# carried inside the saijiki payload. PNG is the only accepted form, which is
# also what keeps the picture inert: the browser shows it in an <img>, so a
# document cannot put markup on screen no matter what it declares.
PREVIEW_SUFFIX = ".png"
# The HiDPI sibling of `name.png` is `name@2x.png`, found by name rather than
# declared: a document names one picture, and the second is optional.
PREVIEW_HIDPI_MARKER = "@2x"
# A cap the served file must stay under. Measured against the bake that
# prompted this: 7 words came to 188 KB at 720px and 559 KB at 1440px, the
# largest single file being 160 KB.
MAX_PREVIEW_BYTES = 512 * 1024
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
_RELATION_LITERALS = {
    "ja": tuple(literal for word in RELATIONS for literal in word.literals_ja),
    "en": tuple(literal for word in RELATIONS for literal in word.literals_en),
}
_REGION_TOKEN_RE = re.compile(r"\{(?:領域|region)\s*:\s*([^}]+)\}", re.IGNORECASE)
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
    # v2.14: `preview: <file>.png` -- artwork for the saijiki preview, as a path
    # relative to the plugin document. Held as the declared path, not as the
    # file's contents: parsing stays free of I/O, and the reader below decides
    # what a document is allowed to put on screen. One image per word, shared
    # by both languages, the same way the built-in previews share theirs.
    preview: str = ""
    # `aliases: 若葉` -- other headings in the namespace that name this word,
    # such as the Japanese name beside an English canonical heading. They match
    # the `aliases` of the word's shared MacroDefinition.
    aliases: tuple[str, ...] = ()

    def qualified_name(self, namespace: str) -> str:
        return f"{namespace}.{self.heading}"

    def alias_qualified_names(self, namespace: str) -> list[str]:
        return [f"{namespace}.{alias}" for alias in self.aliases]

    def visible_qualified_names(self, namespace: str) -> list[str]:
        """The canonical qualified name first, then its aliases."""
        return [self.qualified_name(namespace), *self.alias_qualified_names(namespace)]


@dataclass(frozen=True)
class PluginDocument:
    manifest: PluginManifest
    entries: tuple[PluginEntry, ...]
    source_path: str | None = None


def entry_preview_path(
    document: PluginDocument, entry: PluginEntry, *, hidpi: bool = False
) -> Path | None:
    """The file behind the word's preview, or None when there is none to serve.

    Every refusal returns None rather than raising: a preview is decoration,
    and a document that draws its words correctly must not stop loading because
    its picture is missing. The saijiki panel already has a shape for a word
    with no artwork -- it shows the shared one.

    Refused: a path that leaves the document's own directory, a name that is
    not .png, and a file over the cap. `hidpi` asks for the `@2x` sibling and
    returns None when the document ships only the one size, so the caller can
    tell "no HiDPI" from "no preview at all".
    """
    declared = (entry.preview or "").strip()
    if not declared or not document.source_path:
        return None
    if not declared.lower().endswith(PREVIEW_SUFFIX):
        return None
    if hidpi:
        declared = declared[: -len(PREVIEW_SUFFIX)] + PREVIEW_HIDPI_MARKER + PREVIEW_SUFFIX
    base = Path(document.source_path).resolve().parent
    try:
        target = (base / declared).resolve()
        # `is_relative_to` is the check that matters: `../` and an absolute
        # path both land outside, and both are refused here rather than at the
        # open, which would already have followed the link.
        if not target.is_relative_to(base):
            return None
        if not target.is_file():
            return None
        if target.stat().st_size > MAX_PREVIEW_BYTES:
            return None
    except (OSError, ValueError):
        return None
    return target


def preview_path_for_qualified_name(qualified_name: str, *, hidpi: bool = False) -> Path | None:
    """The preview file for a word named as `Namespace.Word`, or None.

    The route hands over a name the browser sent, so the lookup goes through
    the loaded documents rather than through the filesystem: a name that
    matches no loaded word finds nothing, whatever it spells.
    """
    for document in DOCUMENT_PLUGIN_MANAGER.documents():
        namespace = document.manifest.namespace
        for entry in document.entries:
            if qualified_name in entry.visible_qualified_names(namespace):
                return entry_preview_path(document, entry, hidpi=hidpi)
    return None


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


def _region_key_of(line: str) -> str | None:
    match = _REGION_TOKEN_RE.search(line)
    return match.group(1).strip() if match else None


def _referenced_member(line: str, members: dict[str, str]) -> str | None:
    hits = [name for name in members if name and name.lower() in line.lower()]
    return max(hits, key=len) if hits else None


def _split_pair_segments(definition: str, lang: str) -> list[str]:
    """Split member definitions only for parse-time instruction budgeting."""
    separator = "、" if lang == "ja" else ", "
    segments: list[str] = []
    for part in definition.split(separator):
        if segments and any(literal in part for literal in _RELATION_LITERALS[lang]):
            segments.append(part)
        elif segments:
            segments[-1] = segments[-1] + separator + part
        else:
            segments.append(part)
    return segments


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
            preview=fields.get("preview", "").strip(),
            aliases=_split_values(fields.get("aliases", ""), ","),
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
        for name in (entry.heading, *entry.aliases):
            folded = name.casefold()
            if folded in seen_headings:
                reasons.append(f"duplicate word entry: {name}")
            seen_headings.add(folded)
        for alias in entry.aliases:
            # The parser reads a heading of letters, digits, `_`, and `-` only.
            if not alias or not all(character.isalnum() or character in "_-" for character in alias):
                reasons.append(f"{entry.heading}: invalid alias: {alias}")
        reasons.extend(_validate_entry(entry, manifest))
    if reasons:
        raise PluginFormatError(reasons)
    return PluginDocument(manifest=manifest, entries=tuple(entries), source_path=source_path)


def validate_plugin_document(text: str) -> PluginDocument:
    return parse_plugin_document(text)


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
                        name.casefold()
                        for entry in document.entries
                        for name in entry.visible_qualified_names(document.manifest.namespace)
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
                                    "aliases": entry.alias_qualified_names(document.manifest.namespace),
                                    "surface_ja": list(entry.surfaces.get("ja", ())),
                                    "surface_en": list(entry.surfaces.get("en", ())),
                                    "note_ja": entry.notes.get("ja", ""),
                                    "note_en": entry.notes.get("en", ""),
                                    # v2.14: whether artwork for the saijiki
                                    # preview exists, at each of the two
                                    # scales. This is the list /api/saijiki
                                    # serves; the route that serves the file
                                    # turns these into URLs, so the loader
                                    # stays free of the HTTP layer.
                                    "has_preview": entry_preview_path(document, entry) is not None,
                                    "has_preview_hidpi": entry_preview_path(document, entry, hidpi=True)
                                    is not None,
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

DOCUMENT_PLUGIN_MANAGER = PluginDocumentManager()
