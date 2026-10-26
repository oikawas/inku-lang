"""Plugin packages an administrator installs from the Web (`inku.plugin-package.v1`).

A package is one JSON file: the MacroDefinition v1 of each word, with the
summary Stage 1 reads and the note and example the Saijiki shows. It may also
come as a zip holding that file as `package.json` beside the PNG pictures its
words name in `preview`. Nothing in a package is executed. Checking one is
three steps -- the file's own shape, the shared core's definition checks, and
drawing each word's example through the shared pipeline -- and only a package
that passes all three is installed.

A word's Saijiki picture is the PNG it names, or else is drawn from its example
when the package is installed. An administrator may replace it with a PNG of
their own and go back to the original later. An installed package is exported
as such a zip, with the pictures it shows now, so it can be added elsewhere.

Packages live outside the repository (`INKU_PLUGIN_PACKAGE_DIR`), so a deploy
neither removes them nor leaves the checkout dirty.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from .document_format import MAX_PREVIEW_BYTES, PREVIEW_HIDPI_MARKER, PREVIEW_SUFFIX

PACKAGE_SCHEMA = "inku.plugin-package.v1"
MAX_PACKAGE_BYTES = 1_000_000
MAX_PACKAGE_WORDS = 64
MAX_SUMMARY_BYTES = 8192
MAX_TEXT_CHARS = 2000
# The size of the pictures the Saijiki already shows (Nature.leaves).
PREVIEW_SIZE = (216, 92)
PREVIEW_SEED = 1
LANGUAGES = ("ja", "en")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_PACKAGE_KEYS = {"schema", "namespace", "name", "version", "description_ja", "description_en", "authors", "license", "words"}
_WORD_KEYS = {"definition", "summary_ja", "summary_en", "note_ja", "note_en", "example_ja", "example_en", "preview"}
# A zip is read in memory, never unpacked to disk, and only up to these sizes:
# the archive itself, how many members it may list, and each PNG member.
ARCHIVE_PACKAGE_NAME = "package.json"
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 256
MAX_ARCHIVE_PICTURE_BYTES = MAX_PREVIEW_BYTES * 4
MAX_ARCHIVE_PICTURES_BYTES = 64 * 1024 * 1024
_PACKAGE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*\.[A-Za-z][A-Za-z0-9_-]*$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_DEFAULT_DIR = Path.home() / ".local" / "share" / "inku" / "plugin-packages"


@dataclass(frozen=True)
class Problem:
    """One reason a package cannot be installed: where, what, and the detail."""

    path: str
    code: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "detail": self.detail}


class PluginPackageError(ValueError):
    def __init__(self, problems: Sequence[Problem]):
        super().__init__("; ".join(f"{p.path}: {p.code}" for p in problems))
        self.problems = tuple(problems)


@dataclass(frozen=True)
class PackageWord:
    definition: dict[str, Any]
    summary: dict[str, str]
    note: dict[str, str]
    example: dict[str, str]
    # Where the word sits in the file's `words`, so its problems name the right place.
    index: int = 0
    # Problems with this word's own fields that still leave its definition checkable.
    problems: tuple[Problem, ...] = ()
    # The picture the word names in its zip, already fitted to the Saijiki frame (1x, 2x).
    picture: tuple[bytes, bytes] | None = None

    @property
    def namespace(self) -> str:
        return str(self.definition.get("namespace", ""))

    @property
    def heading(self) -> str:
        return str(self.definition.get("heading", ""))

    @property
    def aliases(self) -> tuple[str, ...]:
        aliases = self.definition.get("aliases") or ()
        return tuple(str(alias) for alias in aliases if isinstance(alias, str))

    @property
    def qualified_name(self) -> str:
        return f"{self.namespace}.{self.heading}"

    def visible_qualified_names(self) -> list[str]:
        return [self.qualified_name, *(f"{self.namespace}.{alias}" for alias in self.aliases)]

    def example_for(self, language: str) -> str:
        """The written example, or the bare call when the package names none.

        A Japanese example names the word by its first alias when it has one,
        the way the Japanese DDL a reader writes would.
        """
        written = self.example.get(language, "").strip()
        if written:
            return written
        if language == "ja":
            name = f"{self.namespace}.{self.aliases[0]}" if self.aliases else self.qualified_name
            return f"{name}。"
        return f"{self.qualified_name}."

    def summary_for(self, language: str) -> str:
        return self.summary.get(language) or self.summary.get("en" if language == "ja" else "ja", "")

    def preview_key(self) -> str:
        # A heading may hold any visible character, so the file is named by its digest.
        return hashlib.sha256(self.heading.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class PluginPackage:
    namespace: str
    name: str
    version: str
    description: dict[str, str]
    authors: tuple[str, ...]
    license: str
    words: tuple[PackageWord, ...]
    # Problems that do not stop the checks: the file is reported whole, then refused.
    problems: tuple[Problem, ...] = ()

    @property
    def id(self) -> str:
        return f"{self.namespace}.{self.name}"

    @property
    def is_sound(self) -> bool:
        return not self.problems and not any(word.problems for word in self.words)

    def word(self, heading: str) -> PackageWord | None:
        return next((word for word in self.words if word.heading == heading), None)


def _text(value: object, path: str, problems: list[Problem], *, limit: int = MAX_TEXT_CHARS) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        problems.append(Problem(path, "not_a_string"))
        return ""
    if len(value) > limit:
        problems.append(Problem(path, "text_too_long", str(limit)))
        return ""
    return value.strip()


def parse_plugin_package(
    text: str, *, archive: Mapping[str, bytes | None] | None = None, stored: bool = False
) -> PluginPackage:
    """Read a package file's own shape. The definitions are checked by the core later.

    Only what leaves nothing to check stops here (not JSON, no readable
    namespace or name, no words): every other problem is kept on the package
    or its word, so the core and the examples still check the rest and one
    upload shows the whole list. A package with any problem is not installed.

    `archive` holds the PNG members of the zip the file came in (see
    `read_package_archive`); a word's `preview` names one of them. `stored`
    reads a file this server already installed, whose pictures were taken
    out of its zip on installing, so `preview` names nothing to read again.
    """
    if len(text.encode("utf-8")) > MAX_PACKAGE_BYTES:
        raise PluginPackageError([Problem("", "package_too_large", str(MAX_PACKAGE_BYTES))])
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise PluginPackageError([Problem("", "invalid_json", f"{error.msg} (line {error.lineno}, column {error.colno})")]) from None
    if not isinstance(raw, dict):
        raise PluginPackageError([Problem("", "not_an_object")])
    problems: list[Problem] = []
    blocking: list[Problem] = []
    for key in sorted(set(raw) - _PACKAGE_KEYS):
        problems.append(Problem(key, "unknown_field"))
    if raw.get("schema") != PACKAGE_SCHEMA:
        problems.append(Problem("schema", "wrong_schema", PACKAGE_SCHEMA))
    namespace = raw.get("namespace")
    if not isinstance(namespace, str) or not _IDENTIFIER_RE.match(namespace):
        blocking.append(Problem("namespace", "invalid_identifier"))
        namespace = ""
    name = raw.get("name")
    if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
        blocking.append(Problem("name", "invalid_identifier"))
        name = ""
    version = raw.get("version")
    if not isinstance(version, str) or not _SEMVER_RE.match(version):
        problems.append(Problem("version", "invalid_semantic_version"))
        version = ""
    description = {lang: _text(raw.get(f"description_{lang}"), f"description_{lang}", problems) for lang in LANGUAGES}
    authors_raw = raw.get("authors") or []
    if not isinstance(authors_raw, list) or not all(isinstance(a, str) for a in authors_raw):
        problems.append(Problem("authors", "not_a_list_of_strings"))
        authors_raw = []
    license_text = _text(raw.get("license"), "license", problems, limit=200)
    words_raw = raw.get("words")
    words: list[PackageWord] = []
    if not isinstance(words_raw, list) or not words_raw:
        blocking.append(Problem("words", "no_words"))
    elif len(words_raw) > MAX_PACKAGE_WORDS:
        blocking.append(Problem("words", "too_many_words", str(MAX_PACKAGE_WORDS)))
    else:
        for index, item in enumerate(words_raw):
            word = _parse_word(item, index, namespace, problems, archive=archive, stored=stored)
            if word is not None:
                words.append(word)
    if blocking:
        raise PluginPackageError([*blocking, *problems])
    return PluginPackage(
        namespace=namespace,
        name=name,
        version=version,
        description=description,
        authors=tuple(authors_raw),
        license=license_text,
        words=tuple(words),
        problems=tuple(problems),
    )


def _parse_word(
    item: object,
    index: int,
    namespace: str,
    file_problems: list[Problem],
    *,
    archive: Mapping[str, bytes | None] | None,
    stored: bool,
) -> PackageWord | None:
    """One word; a word with no definition to check is a problem of the file instead."""
    path = f"words[{index}]"
    if not isinstance(item, dict):
        file_problems.append(Problem(path, "not_an_object"))
        return None
    definition = item.get("definition")
    if not isinstance(definition, dict):
        file_problems.append(Problem(f"{path}.definition", "not_an_object"))
        return None
    problems: list[Problem] = []
    for key in sorted(set(item) - _WORD_KEYS):
        problems.append(Problem(f"{path}.{key}", "unknown_field"))
    if namespace and definition.get("namespace") != namespace:
        problems.append(Problem(f"{path}.definition.namespace", "namespace_differs_from_package", namespace))
    summary = {lang: _text(item.get(f"summary_{lang}"), f"{path}.summary_{lang}", problems, limit=MAX_SUMMARY_BYTES) for lang in LANGUAGES}
    for lang in LANGUAGES:
        if len(summary[lang].encode("utf-8")) > MAX_SUMMARY_BYTES:
            problems.append(Problem(f"{path}.summary_{lang}", "text_too_long", str(MAX_SUMMARY_BYTES)))
    if not any(summary.values()):
        problems.append(Problem(f"{path}.summary_ja", "no_summary"))
    note = {lang: _text(item.get(f"note_{lang}"), f"{path}.note_{lang}", problems) for lang in LANGUAGES}
    example = {lang: _text(item.get(f"example_{lang}"), f"{path}.example_{lang}", problems, limit=500) for lang in LANGUAGES}
    picture = None if stored else _word_picture(item.get("preview"), f"{path}.preview", archive, problems)
    return PackageWord(definition=definition, summary=summary, note=note, example=example,
                       index=index, problems=tuple(problems), picture=picture)


def _word_picture(
    named: object, path: str, archive: Mapping[str, bytes | None] | None, problems: list[Problem]
) -> tuple[bytes, bytes] | None:
    """The picture a word names in its zip, fitted to the Saijiki frame, or None."""
    if named is None:
        return None
    if not isinstance(named, str) or not named.strip():
        problems.append(Problem(path, "not_a_string"))
        return None
    if archive is None:
        problems.append(Problem(path, "preview_needs_zip"))
        return None
    # Members are only looked up by name, never written out, but a name that
    # climbs or starts at the root is refused so the file reads as it means.
    parts = named.replace("\\", "/").split("/")
    if named.startswith("/") or ".." in parts:
        problems.append(Problem(path, "invalid_preview_path", named))
        return None
    if named not in archive:
        problems.append(Problem(path, "preview_not_found", named))
        return None
    data = archive[named]
    if data is None:
        problems.append(Problem(path, "image_too_large", str(MAX_ARCHIVE_PICTURE_BYTES)))
        return None
    try:
        return uploaded_preview_pngs(data)
    except PluginPackageError as error:
        problems.extend(Problem(path, problem.code, problem.detail) for problem in error.problems)
        return None


def read_package_archive(data: bytes) -> tuple[str, dict[str, bytes | None]]:
    """The `package.json` text of a zip and its PNG members, read in memory.

    Nothing is unpacked to disk. Sizes are checked against what is actually
    read rather than what the zip's directory claims, so a member that
    inflates past its limit is cut off there. A PNG member over the limit is
    kept as None, so the word naming it is told its picture is too large.
    """
    problem = lambda code, detail="": PluginPackageError([Problem("", code, detail)])  # noqa: E731
    if len(data) > MAX_ARCHIVE_BYTES:
        raise problem("archive_too_large", str(MAX_ARCHIVE_BYTES))
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        members = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError):
        raise problem("invalid_zip") from None
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise problem("too_many_archive_members", str(MAX_ARCHIVE_MEMBERS))

    def read(info: zipfile.ZipInfo, limit: int) -> bytes | None:
        try:
            with archive.open(info) as handle:
                content = handle.read(limit + 1)
        except (zipfile.BadZipFile, OSError, ValueError, RuntimeError, NotImplementedError):
            raise problem("invalid_zip", info.filename) from None
        return None if len(content) > limit else content

    package = next((info for info in members if info.filename == ARCHIVE_PACKAGE_NAME), None)
    if package is None:
        raise problem("archive_without_package_json", ARCHIVE_PACKAGE_NAME)
    raw = read(package, MAX_PACKAGE_BYTES)
    if raw is None:
        raise problem("package_too_large", str(MAX_PACKAGE_BYTES))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise problem("not_utf8", ARCHIVE_PACKAGE_NAME) from None
    pictures: dict[str, bytes | None] = {}
    total = 0
    for info in members:
        if info.is_dir() or not info.filename.lower().endswith(PREVIEW_SUFFIX):
            continue
        content = read(info, MAX_ARCHIVE_PICTURE_BYTES)
        total += len(content or b"")
        if total > MAX_ARCHIVE_PICTURES_BYTES:
            raise problem("archive_too_large", str(MAX_ARCHIVE_PICTURES_BYTES))
        pictures[info.filename] = content
    return text, pictures


# --------------------------------------------------------------------------- #
# The checks that need the shared core and pipeline                            #
# --------------------------------------------------------------------------- #

ExampleDrawer = Callable[[str, str, list[dict[str, Any]]], "ExampleDrawing"]


@dataclass(frozen=True)
class ExampleDrawing:
    """What drawing one example gave: the picture, or the reasons it stopped."""

    svg: str = ""
    marks: int = 0
    reasons: tuple[str, ...] = ()


def _resolve(binding: object, candidates: list[dict[str, str]], bundled: list[str]) -> dict[str, Any]:
    payload = json.dumps(
        {"maximum_entries": MAX_PACKAGE_WORDS + 256, "canonical": candidates, "legacy": [],
         "bundled_packages": bundled, "language": "en"},
        ensure_ascii=False, separators=(",", ":"),
    ).encode()
    return json.loads(binding.resolve_macro_catalog(payload))


def check_package(
    package: PluginPackage,
    *,
    binding: object,
    draw_example: ExampleDrawer,
    taken_names: Mapping[str, str],
) -> dict[str, Any]:
    """Check every word of a parsed package and draw its examples.

    `taken_names` maps each visible name another installed plugin already holds
    to that plugin's id; a word claiming one is refused, so installing never
    silently shadows or loses to another plugin.
    Returns the report the Web shows: per word, its problems and its picture.
    """
    # Source ids count the words that reached this step; problem paths use each
    # word's place in the file, which differs once a word was left out.
    candidates = [
        {"source_id": f"word:{position}", "definition_json": json.dumps(word.definition, ensure_ascii=False),
         "summary": word.summary_for("en")}
        for position, word in enumerate(package.words)
    ]
    resolved = _resolve(binding, candidates, [])
    by_source: dict[str, dict[str, Any]] = {entry["source_id"]: entry for entry in resolved.get("entries", [])}
    # A definition problem stops the word's examples from being drawn; a
    # problem with its other fields does not, so both are reported at once.
    definition_problems: dict[int, list[Problem]] = {position: [] for position in range(len(package.words))}
    for diagnostic in resolved.get("diagnostics", []):
        source = str(diagnostic.get("source_id", ""))
        if not source.startswith("word:"):
            continue
        position = int(source.removeprefix("word:"))
        path = f"words[{package.words[position].index}].definition"
        findings = diagnostic.get("findings") or []
        if findings:
            for finding in findings:
                definition_problems[position].append(
                    Problem(f"{path}{_finding_path(str(finding.get('path', '')))}", str(finding.get("code", "")))
                )
        else:
            definition_problems[position].append(Problem(path, str(diagnostic.get("reason", ""))))
    for position, word in enumerate(package.words):
        entry = by_source.get(f"word:{position}")
        if entry is None:
            continue
        for name in [entry["qualified_name"], *entry.get("aliases", [])]:
            holder = taken_names.get(name)
            if holder is not None:
                definition_problems[position].append(
                    Problem(f"words[{word.index}].definition", "name_taken", f"{name} ({holder})")
                )
    imported = [
        {"definition": word.definition, "summary": word.summary_for("en")}
        for position, word in enumerate(package.words)
        if not definition_problems[position]
    ]
    reports = []
    for position, word in enumerate(package.words):
        index = word.index
        problems = [*word.problems, *definition_problems[position]]
        report: dict[str, Any] = {
            "heading": word.heading,
            "qualified_name": word.qualified_name,
            "aliases": [f"{word.namespace}.{alias}" for alias in word.aliases],
            "summary_ja": word.summary_for("ja"),
            "summary_en": word.summary_for("en"),
            "note_ja": word.note.get("ja", ""),
            "note_en": word.note.get("en", ""),
            "example_ja": word.example_for("ja"),
            "example_en": word.example_for("en"),
            "digest": (by_source.get(f"word:{position}") or {}).get("digest", ""),
            "preview_png": "",
        }
        if not definition_problems[position]:
            for lang in LANGUAGES:
                drawing = draw_example(word.example_for(lang), lang, imported)
                if drawing.reasons or drawing.marks == 0:
                    for reason in drawing.reasons or ("example_draws_nothing",):
                        problems.append(Problem(f"words[{index}].example_{lang}", reason))
                elif lang == "ja":
                    report["preview_svg"] = drawing.svg
        report["problems"] = [problem.as_dict() for problem in problems]
        reports.append(report)
    ok = not package.problems and all(not report["problems"] for report in reports)
    return {
        "ok": ok,
        "id": package.id,
        "namespace": package.namespace,
        "name": package.name,
        "version": package.version,
        "description_ja": package.description.get("ja", ""),
        "description_en": package.description.get("en", ""),
        "problems": [problem.as_dict() for problem in package.problems],
        "words": reports,
    }


def _finding_path(path: str) -> str:
    # The core writes `$.body[0].count:0:0` for a JSON-pointer-like path with a
    # line and column; the line and column are of the definition alone, so
    # they say nothing to someone reading the whole package file.
    trimmed = re.sub(r":\d+:\d+$", "", path)
    if trimmed in {"", "$"}:
        return ""
    return trimmed[1:] if trimmed.startswith("$") else f".{trimmed}" if not trimmed.startswith((".", "[")) else trimmed


def preview_pngs(svg: str) -> tuple[bytes, bytes]:
    """The 1x and 2x pictures of a drawing, its marks cut out and fitted in the Saijiki frame.

    The whole canvas is mostly paper, so the marks are cut out first: a few
    small stars on a square canvas would otherwise be specks in a wide frame.
    """
    from inku_analysis.rasterizer import svg_to_png
    from PIL import Image, ImageChops

    source = Image.open(io.BytesIO(svg_to_png(svg, width=768, height=768))).convert("RGB")
    paper = source.getpixel((0, 0))
    difference = ImageChops.difference(source, Image.new("RGB", source.size, paper)).convert("L")
    box = difference.point(lambda value: 255 if value > 12 else 0).getbbox() or (0, 0, *source.size)
    margin = 24
    box = (max(0, box[0] - margin), max(0, box[1] - margin),
           min(source.width, box[2] + margin), min(source.height, box[3] + margin))
    cropped = source.crop(box)
    return tuple(_fit(cropped, paper, scale) for scale in (1, 2))  # type: ignore[return-value]


def _fit(image: Any, paper: tuple[int, int, int], scale: int) -> bytes:
    from PIL import Image

    width, height = PREVIEW_SIZE[0] * scale, PREVIEW_SIZE[1] * scale
    ratio = min(width / image.width, height / image.height)
    resized = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))), Image.LANCZOS)
    frame = Image.new("RGB", (width, height), paper)
    frame.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    out = io.BytesIO()
    frame.save(out, format="PNG", optimize=True)
    return out.getvalue()


def uploaded_preview_pngs(data: bytes) -> tuple[bytes, bytes]:
    """An administrator's own picture, fitted to the two sizes the Saijiki serves."""
    from PIL import Image, UnidentifiedImageError

    if len(data) > MAX_PREVIEW_BYTES * 4:
        raise PluginPackageError([Problem("image", "image_too_large", str(MAX_PREVIEW_BYTES * 4))])
    if not data.startswith(_PNG_SIGNATURE):
        raise PluginPackageError([Problem("image", "not_a_png")])
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise PluginPackageError([Problem("image", "not_a_png")]) from None
    if image.width * image.height > 4096 * 4096:
        raise PluginPackageError([Problem("image", "image_too_large")])
    image = image.convert("RGBA")
    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
    flattened = Image.alpha_composite(background, image).convert("RGB")
    # A picture whose shape differs from the frame is padded with its own
    # corner colour, so a dark night sky is not framed by white bars.
    paper = flattened.getpixel((0, 0))
    return tuple(_fit(flattened, paper, scale) for scale in (1, 2))  # type: ignore[return-value]


def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


# --------------------------------------------------------------------------- #
# Storage                                                                      #
# --------------------------------------------------------------------------- #


class PluginPackageManager:
    """Installed packages: one directory each, and one state file for which are off.

    <dir>/<id>/package.json         the file as uploaded
    <dir>/<id>/previews/<key>.png   the picture the word named in its zip, or else
                                    the one drawn from its example (and @2x)
    <dir>/<id>/custom/<key>.png     an administrator's replacement (and @2x)
    <dir>/.package-state.json       {"disabled": [ids]}
    """

    def __init__(self, directory: Path | None = None):
        self.directory = directory or Path(os.getenv("INKU_PLUGIN_PACKAGE_DIR", str(_DEFAULT_DIR))).expanduser()
        self._lock = RLock()
        self._signature: tuple[tuple[str, int, int], ...] | None = None
        self._packages: tuple[PluginPackage, ...] = ()
        self._rejected: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def _state_path(self) -> Path:
        return self.directory / ".package-state.json"

    def _package_files(self) -> list[Path]:
        if not self.directory.is_dir():
            return []
        return sorted(path / "package.json" for path in self.directory.iterdir()
                      if path.is_dir() and _PACKAGE_ID_RE.match(path.name) and (path / "package.json").is_file())

    def _current_signature(self) -> tuple[tuple[str, int, int], ...]:
        paths = self._package_files()
        if self._state_path().exists():
            paths.append(self._state_path())
        return tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)

    def _reload(self) -> None:
        with self._lock:
            signature = self._current_signature()
            if signature == self._signature:
                return
            packages, rejected = [], []
            for path in self._package_files():
                try:
                    package = parse_plugin_package(path.read_text(encoding="utf-8"), stored=True)
                    if not package.is_sound:
                        raise PluginPackageError([*package.problems, *(p for w in package.words for p in w.problems)])
                    if package.id != path.parent.name:
                        raise PluginPackageError([Problem("", "id_differs_from_directory")])
                    packages.append(package)
                except (OSError, UnicodeError, PluginPackageError) as error:
                    reasons = tuple(f"{p.path}: {p.code}" for p in error.problems) if isinstance(error, PluginPackageError) else (str(error),)
                    rejected.append((path.parent.name, reasons))
            self._packages, self._rejected, self._signature = tuple(packages), tuple(rejected), signature

    def _disabled(self) -> set[str]:
        try:
            raw = json.loads(self._state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        disabled = raw.get("disabled") if isinstance(raw, dict) else None
        return {item for item in disabled if isinstance(item, str)} if isinstance(disabled, list) else set()

    def _save_disabled(self, disabled: set[str]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._state_path().write_text(json.dumps({"disabled": sorted(disabled)}, indent=2) + "\n", encoding="utf-8")

    def packages(self) -> tuple[PluginPackage, ...]:
        self._reload()
        return self._packages

    def enabled_packages(self) -> tuple[PluginPackage, ...]:
        disabled = self._disabled()
        return tuple(package for package in self.packages() if package.id not in disabled)

    def is_enabled(self, package_id: str) -> bool:
        return package_id not in self._disabled()

    def get(self, package_id: str) -> PluginPackage | None:
        return next((package for package in self.packages() if package.id == package_id), None)

    @staticmethod
    def names_a_package(plugin_id: str) -> bool:
        """Whether an id has a package's shape (`Namespace.name`) rather than a document file name's."""
        return bool(_PACKAGE_ID_RE.match(plugin_id))

    def has(self, package_id: str) -> bool:
        if not _PACKAGE_ID_RE.match(package_id):
            return False
        self._reload()
        return any(package.id == package_id for package in self._packages) or any(
            rejected_id == package_id for rejected_id, _ in self._rejected
        )

    def _package_dir(self, package_id: str) -> Path:
        if not _PACKAGE_ID_RE.match(package_id):
            raise PluginPackageError([Problem("id", "invalid_package_id")])
        return self.directory / package_id

    def install(self, text: str, package: PluginPackage, previews: Mapping[str, tuple[bytes, bytes]]) -> None:
        """Write a checked package; a replaced package keeps the pictures an administrator chose."""
        with self._lock:
            target = self._package_dir(package.id)
            staging = self.directory / f".staging-{package.id}"
            if staging.exists():
                shutil.rmtree(staging)
            (staging / "previews").mkdir(parents=True)
            (staging / "package.json").write_text(text, encoding="utf-8")
            for key, (one, two) in previews.items():
                (staging / "previews" / f"{key}{PREVIEW_SUFFIX}").write_bytes(one)
                (staging / "previews" / f"{key}{PREVIEW_HIDPI_MARKER}{PREVIEW_SUFFIX}").write_bytes(two)
            keep = {word.preview_key() for word in package.words}
            custom = target / "custom"
            if custom.is_dir():
                (staging / "custom").mkdir()
                for path in custom.iterdir():
                    if path.name.split("@")[0].removesuffix(PREVIEW_SUFFIX) in keep:
                        shutil.copy2(path, staging / "custom" / path.name)
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
            self._signature = None

    def delete(self, package_id: str) -> None:
        with self._lock:
            target = self._package_dir(package_id)
            if not target.is_dir():
                raise FileNotFoundError(package_id)
            shutil.rmtree(target)
            disabled = self._disabled()
            if package_id in disabled:
                disabled.discard(package_id)
                self._save_disabled(disabled)
            self._signature = None

    def set_enabled(self, package_id: str, enabled: bool) -> None:
        with self._lock:
            if not self._package_dir(package_id).is_dir():
                raise FileNotFoundError(package_id)
            disabled = self._disabled()
            (disabled.discard if enabled else disabled.add)(package_id)
            self._save_disabled(disabled)
            self._signature = None

    def set_custom_preview(self, package_id: str, heading: str, pngs: tuple[bytes, bytes] | None) -> None:
        with self._lock:
            package = self.get(package_id)
            word = package.word(heading) if package else None
            if word is None:
                raise FileNotFoundError(f"{package_id} {heading}")
            custom = self._package_dir(package_id) / "custom"
            key = word.preview_key()
            paths = (custom / f"{key}{PREVIEW_SUFFIX}", custom / f"{key}{PREVIEW_HIDPI_MARKER}{PREVIEW_SUFFIX}")
            if pngs is None:
                for path in paths:
                    path.unlink(missing_ok=True)
                return
            custom.mkdir(parents=True, exist_ok=True)
            for path, png in zip(paths, pngs, strict=True):
                path.write_bytes(png)

    def preview_path(self, package: PluginPackage, word: PackageWord, *, hidpi: bool = False) -> Path | None:
        suffix = f"{PREVIEW_HIDPI_MARKER}{PREVIEW_SUFFIX}" if hidpi else PREVIEW_SUFFIX
        base = self._package_dir(package.id)
        for folder in ("custom", "previews"):
            path = base / folder / f"{word.preview_key()}{suffix}"
            if path.is_file():
                return path
        return None

    def has_custom_preview(self, package: PluginPackage, word: PackageWord) -> bool:
        return (self._package_dir(package.id) / "custom" / f"{word.preview_key()}{PREVIEW_SUFFIX}").is_file()

    def export(self, package_id: str) -> tuple[str, bytes]:
        """The installed package as a zip another server can add as it is: a file name and its bytes.

        `package.json` is the file as installed, each word's `preview` naming
        the picture it shows now (an administrator's replacement where there
        is one), written at the larger of the two sizes.
        """
        with self._lock:
            package = self.get(package_id)
            if package is None:
                raise FileNotFoundError(package_id)
            raw = json.loads((self._package_dir(package_id) / "package.json").read_text(encoding="utf-8"))
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for word in package.words:
                    entry = raw["words"][word.index]
                    entry.pop("preview", None)
                    picture = self.preview_path(package, word, hidpi=True) or self.preview_path(package, word)
                    if picture is None:
                        continue
                    member = f"previews/{word.preview_key()}{PREVIEW_SUFFIX}"
                    archive.writestr(member, picture.read_bytes())
                    entry["preview"] = member
                archive.writestr(ARCHIVE_PACKAGE_NAME, json.dumps(raw, ensure_ascii=False, indent=2) + "\n")
            return f"{package.id}-{package.version}.zip", out.getvalue()

    def preview_path_for_qualified_name(self, qualified_name: str, *, hidpi: bool = False) -> Path | None:
        # A switched-off package's pictures are still served: the settings list
        # shows them, and a name belongs to one installed package at most.
        for package in self.packages():
            for word in package.words:
                if qualified_name in word.visible_qualified_names():
                    return self.preview_path(package, word, hidpi=hidpi)
        return None

    # --- views for the rest of the server ---------------------------------- #

    def catalog_candidates(self, language: str) -> list[dict[str, str]]:
        """The enabled words as canonical candidates of a new work's macro catalog."""
        return [
            {"source_id": f"package:{package.id}",
             "definition_json": json.dumps(word.definition, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
             "summary": word.summary_for(language)}
            for package in self.enabled_packages()
            for word in package.words
        ]

    def saijiki_entries(self) -> list[dict[str, object]]:
        """Saijiki entries in the shape the plugin documents give theirs, plus the examples."""
        entries: list[dict[str, object]] = []
        for package in self.enabled_packages():
            for word in package.words:
                entries.append(self._entry(package, word))
        return entries

    def _entry(self, package: PluginPackage, word: PackageWord) -> dict[str, object]:
        aliases = [f"{word.namespace}.{alias}" for alias in word.aliases]
        preview = self.preview_path(package, word)
        return {
            "qualified_name": word.qualified_name,
            "aliases": aliases,
            "surface_ja": list(word.aliases) or [word.heading],
            "surface_en": [word.heading],
            "note_ja": word.note.get("ja") or word.note.get("en", ""),
            "note_en": word.note.get("en") or word.note.get("ja", ""),
            "example_ja": word.example_for("ja"),
            "example_en": word.example_for("en"),
            "fires_on_ja": [],
            "fires_on_en": [],
            "has_preview": preview is not None,
            "has_preview_hidpi": self.preview_path(package, word, hidpi=True) is not None,
            "preview_version": str(preview.stat().st_mtime_ns) if preview is not None else "",
            "custom_preview": self.has_custom_preview(package, word),
            "summary_ja": word.summary_for("ja"),
            "summary_en": word.summary_for("en"),
        }

    def status_items(self) -> list[dict[str, object]]:
        """Items in the shape of the plugin documents' list, marked as packages."""
        items: list[dict[str, object]] = []
        disabled = self._disabled()
        for package in self.packages():
            enabled = package.id not in disabled
            items.append({
                "id": package.id,
                "kind": "package",
                "name": package.name,
                "namespace": package.namespace,
                "version": package.version,
                "status": "enabled" if enabled else "disabled",
                "path": package.id,
                "entries": [self._entry(package, word) for word in package.words],
                "reasons": [],
                "enabled": enabled,
                "has_definitions": True,
                "deletable": True,
                "description_ja": package.description.get("ja", ""),
                "description_en": package.description.get("en", ""),
            })
        for package_id, reasons in self._rejected:
            items.append({
                "id": package_id, "kind": "package", "name": package_id, "namespace": "", "version": "",
                "status": "rejected", "path": package_id, "entries": [], "reasons": list(reasons),
                "enabled": package_id not in disabled, "has_definitions": False, "deletable": True,
            })
        return items

    def visible_names(self, *, enabled: bool | None = None, excluding: str | None = None) -> dict[str, str]:
        """Each visible name an installed package holds, mapped to its package id."""
        disabled = self._disabled()
        names: dict[str, str] = {}
        for package in self.packages():
            if package.id == excluding:
                continue
            if enabled is not None and (package.id not in disabled) != enabled:
                continue
            for word in package.words:
                for name in word.visible_qualified_names():
                    names[name] = package.id
        return names


PLUGIN_PACKAGE_MANAGER = PluginPackageManager()
