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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from .document_format import PREVIEW_HIDPI_MARKER, PREVIEW_SUFFIX

PREVIEW_SEED = 1
LANGUAGES = ("ja", "en")

ARCHIVE_PACKAGE_NAME = "package.json"
_PACKAGE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*\.[A-Za-z][A-Za-z0-9_-]*$")
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


@dataclass(frozen=True)
class ExampleDrawing:
    svg: str = ""
    marks: int = 0
    reasons: tuple[str, ...] = ()


def package_core(payload: dict[str, Any]) -> dict[str, Any]:
    from inku_render import pipeline_plugin_package

    result = json.loads(pipeline_plugin_package(json.dumps(payload, ensure_ascii=False).encode("utf-8")))
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


def parse_plugin_package(text: str, *, stored: bool = True) -> PluginPackage:
    if not stored:
        raise ValueError("only stored package reading is supported here")
    result = package_core({"action": "read_stored", "document": text})
    if result["outcome"] == "refused":
        raise PluginPackageError([Problem(**p) for p in result["problems"]])
    raw = result["package"]
    words = tuple(PackageWord(
        definition=w["definition"],
        summary={lang: w[f"summary_{lang}"] for lang in LANGUAGES},
        note={lang: w[f"note_{lang}"] for lang in LANGUAGES},
        example={lang: w[f"example_{lang}"] for lang in LANGUAGES},
        index=w["index"], problems=tuple(Problem(**p) for p in w["problems"]),
    ) for w in raw["words"])
    return PluginPackage(namespace=raw["namespace"], name=raw["name"], version=raw["version"],
                         description={lang: raw[f"description_{lang}"] for lang in LANGUAGES},
                         authors=tuple(raw["authors"]), license=raw["license"], words=words,
                         problems=tuple(Problem(**p) for p in raw["problems"]))


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
