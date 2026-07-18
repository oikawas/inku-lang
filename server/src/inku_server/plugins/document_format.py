"""Declarative DDL vocabulary plugin documents.

Plugin files are parsed as data.  Nothing in this module imports or executes
code from a plugin document.  Validation failures reject the whole document;
this is a document-format boundary, not a governor for generated works.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
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
_RANGE_RE = re.compile(
    r"(?P<low>\d+)\s*(?:[〜～-]|to)\s*(?P<high>\d+)\s*(?P<unit>枚|個|本|marks?|items?|lines?)",
    re.IGNORECASE,
)
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
_CORE_MARKERS = {
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
        "touching",
        "along",
        "cutting",
        "not touching",
        "between",
    ),
}
_REGIONS = {
    "上半分": (0.10, 0.08, 0.90, 0.48),
    "中域": (0.18, 0.24, 0.82, 0.76),
    "下の隅": (0.58, 0.62, 0.92, 0.92),
    "upper half": (0.10, 0.08, 0.90, 0.48),
    "middle": (0.18, 0.24, 0.82, 0.76),
    "middle region": (0.18, 0.24, 0.82, 0.76),
    "lower corner": (0.58, 0.62, 0.92, 0.92),
}


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
        if line.lower().startswith("anchor "):
            continue
        match = _RANGE_RE.search(line)
        total += int(match.group("high")) if match else 1
    return total


def _validate_entry(entry: PluginEntry, manifest: PluginManifest) -> list[str]:
    reasons: list[str] = []
    for lang in manifest.languages:
        if not entry.surfaces.get(lang):
            reasons.append(f"{entry.heading}: surface_{lang} is required")
        if not entry.fires_on.get(lang):
            reasons.append(f"{entry.heading}: fires_on_{lang} is required")
        lines = entry.templates.get(lang)
        if not lines:
            reasons.append(f"{entry.heading}: expansion template for {lang} is required")
            continue
        budget = _instruction_budget(lines)
        if budget > MAX_ENTRY_INSTRUCTIONS:
            reasons.append(
                f"{entry.heading}: expansion budget {budget} exceeds {MAX_ENTRY_INSTRUCTIONS}"
            )
        for line in lines:
            if _PLUGIN_REFERENCE_RE.search(line):
                reasons.append(f"{entry.heading}: plugin references are forbidden in expansion: {line}")
            if _EXTERNAL_REFERENCE_RE.search(line):
                reasons.append(
                    f"{entry.heading}: URL and file references are forbidden in expansion: {line}"
                )
            match = _RANGE_RE.search(line)
            if match and int(match.group("high")) > 1 and _FIXED_COORD_RE.search(line):
                reasons.append(f"{entry.heading}: repeated members cannot use fixed coordinates")
            lower = line.lower()
            if not any(marker.lower() in lower for marker in _CORE_MARKERS[lang]):
                reasons.append(f"{entry.heading}: expansion line is outside core vocabulary: {line}")
    return reasons


def parse_plugin_document(text: str, *, source_path: str | None = None) -> PluginDocument:
    values, body = _parse_front_matter(text)
    manifest = _build_manifest(values)
    entries: list[PluginEntry] = []
    current_heading: str | None = None
    fields: dict[str, str] = {}
    templates: dict[str, list[str]] = {}
    template_lang: str | None = None

    def finish_entry() -> None:
        nonlocal current_heading, fields, templates, template_lang
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
        )
        entries.append(entry)
        current_heading = None
        fields = {}
        templates = {}
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


def _region_for_line(line: str, fallback: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    match = re.search(r"\{(?:領域|region)\s*:\s*([^}]+)\}", line, re.IGNORECASE)
    if not match:
        return fallback
    return _REGIONS.get(match.group(1).strip().lower(), fallback)


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


def _expand_entry(entry: PluginEntry, *, lang: str, seed_text: str) -> str:
    lines = entry.templates[lang]
    anchor_region = (0.18, 0.24, 0.82, 0.76)
    expanded: list[str] = []
    for line in lines:
        if line.lower().startswith("anchor "):
            anchor_region = _region_for_line(line, anchor_region)
            continue
        line_region = _region_for_line(line, anchor_region)
        clean = re.sub(
            r"\{(?:領域|region)\s*:\s*[^}]+\}",
            _format_region(line_region, lang=lang),
            line,
            flags=re.IGNORECASE,
        )
        match = _RANGE_RE.search(clean)
        if match is None:
            expanded.append(clean)
            continue
        low, high = int(match.group("low")), int(match.group("high"))
        if low < 1 or high < low:
            raise PluginFormatError([f"{entry.heading}: invalid repetition range"])
        count = low + _stable_int(seed_text, f"count-{entry.heading}") % (high - low + 1)
        singular = "一枚" if lang == "ja" else "one mark"
        base = clean[: match.start()] + singular + clean[match.end() :]
        for index, (member_region, rotation) in enumerate(
            _member_regions(line_region, count, seed_text), start=1
        ):
            suffix = (
                f" {_format_region(member_region, lang=lang)}に置き、回転は{rotation}度。"
                if lang == "ja"
                else f" Place member {index} in {_format_region(member_region, lang=lang)} with rotation {rotation} degrees."
            )
            expanded.append(base.rstrip("。.") + suffix)
    if _instruction_budget(tuple(expanded)) > MAX_ENTRY_INSTRUCTIONS:
        raise PluginFormatError([f"{entry.heading}: runtime expansion exceeds {MAX_ENTRY_INSTRUCTIONS}"])
    separator = "" if lang == "ja" else " "
    ending = "。" if lang == "ja" else "."
    return separator.join(line if line.endswith(("。", ".", "!", "?")) else line + ending for line in expanded)


def _is_metaphorical(source: str, phrase: str, *, lang: str) -> bool:
    folded = source.casefold()
    phrase_folded = phrase.casefold()
    index = folded.find(phrase_folded)
    if index < 0:
        return False
    window = folded[max(0, index - 16) : index + len(phrase_folded) + 16]
    markers = ("のよう", "みたい", "比喩") if lang == "ja" else ("like ", "as if", "metaphor")
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
    for document in documents:
        for entry in document.entries:
            qualified = entry.qualified_name(document.manifest.namespace)
            explicit = qualified.casefold() in result.casefold() or qualified.casefold() in source.casefold()
            trigger = qualified if explicit else None
            if not explicit:
                for phrase in entry.fires_on.get(lang, ()):
                    if phrase.casefold() in source.casefold() and not _is_metaphorical(source, phrase, lang=lang):
                        trigger = phrase
                        break
            if trigger is None:
                continue
            base = _strip_qualified_sentence(result, qualified, lang=lang) if explicit else result
            try:
                expansion = _expand_entry(
                    entry,
                    lang=lang,
                    seed_text=seed_text or source or result or qualified,
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
