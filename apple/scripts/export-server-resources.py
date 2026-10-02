"""Generate Apple installation data from the Server-owned source defaults."""

from __future__ import annotations

import ast
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server/src/inku_server"
OUTPUT = ROOT / "apple/Sources/InkuUI/Resources"


def literal_assignment(path: Path, name: str):
    module = ast.parse(path.read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
    raise ValueError(f"Server constant unavailable: {name}")


class BindingPlaceholder:
    """Palette and registry are resolved by the real Rust core at runtime."""

    canvas_registry: ClassVar[dict] = {"registry": {"schema": ""}, "digest": ""}

    @staticmethod
    def resolve_palette(_request: bytes) -> bytes:
        return b"{}"


def main() -> None:
    catalogs = literal_assignment(SERVER / "color_catalogs.py", "_CATALOG_DEFINITIONS")
    source = ast.parse((SERVER / "pipeline_defaults.py").read_text())
    constants = {"ADDITIONAL_RESOURCE_LIMITS", "HOST_LIMITS"}
    selected = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    selected += [
        node for node in source.body
        if (isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in constants for target in node.targets
        )) or (isinstance(node, ast.FunctionDef) and node.name == "default_manifest")
    ]
    limit_source = ast.parse((SERVER / "limits.py").read_text())
    limit_class = next(node for node in limit_source.body if isinstance(node, ast.ClassDef) and node.name == "Limits")
    limits = {
        node.target.id: ast.literal_eval(node.value)
        for node in limit_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None
    }
    catalog_maps = {item["id"]: item["map"] for item in catalogs}
    environment = {
        "json": json,
        "deepcopy": deepcopy,
        "os": SimpleNamespace(getenv=lambda _name, default: default),
        "DEFAULT_LIMITS": SimpleNamespace(**limits),
        "CANVAS_BASE_PX": literal_assignment(
            SERVER / "plugins/system/canvas_aspect/__init__.py", "CANVAS_BASE_PX"),
        "render_color_map_for_catalog": lambda name: catalog_maps[name],
        "_bytes": lambda value: json.dumps(value).encode(),
    }
    # Execute only the trusted, versioned Server default factory and its constants.
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(module, "server/pipeline_defaults.py", "exec"), environment)  # noqa: S102
    manifest = environment["default_manifest"](BindingPlaceholder())
    # Parse versioned documents with the Server's data-only parser. Never load
    # user installations or execute the Markdown expansion prose.
    sys.path.insert(0, str(ROOT / "server/src"))
    from inku_server.plugins import bundled_package_for
    from inku_server.plugins.document_format import (
        entry_preview_path,
        parse_plugin_document,
    )

    legacy = []
    bundled = []
    plugin_words = []
    OUTPUT.mkdir(parents=True, exist_ok=True)
    previews = OUTPUT / "plugin-previews"
    previews.mkdir(exist_ok=True)
    for path in sorted((ROOT / "server/plugins").glob("*.inku-plugin.md")):
        document = parse_plugin_document(path.read_text(encoding="utf-8"), source_path=str(path))
        package = bundled_package_for(path)
        if package is not None:
            bundled.append(package)
        source_id = f"bundled:{package}" if package is not None else path.name
        for entry in document.entries:
            legacy.append({"source_id": source_id,
                           "qualified_name": entry.qualified_name(document.manifest.namespace)})
            preview = entry_preview_path(document, entry, hidpi=True) or entry_preview_path(document, entry)
            preview_name = None
            if preview is not None:
                preview_name = f"{document.manifest.namespace}-{entry.heading}.png"
                shutil.copyfile(preview, previews / preview_name)
            plugin_words.append({"id": entry.qualified_name(document.manifest.namespace),
                                 "aliases": entry.alias_qualified_names(document.manifest.namespace),
                                 "surfaces": entry.surfaces, "notes": entry.notes,
                                 "fires_on": entry.fires_on, "preview": preview_name,
                                 "package_id": package, "source_id": source_id})
    macro_sources = {"maximum_entries": manifest["pipeline"]["prompt_limits"]["max_catalog_entries"],
                     "canonical": [], "legacy": legacy, "bundled_packages": sorted(set(bundled))}
    saijiki = json.loads((ROOT / "core/crates/inku-ddl/assets/saijiki-v2.json").read_text(encoding="utf-8"))
    for name, value in [("server-defaults.json", manifest), ("color-catalogs.json", catalogs),
                        ("macro-sources.json", macro_sources), ("plugin-words.json", plugin_words),
                        ("saijiki.json", saijiki)]:
        (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(f"Generated Server defaults, {len(catalogs)} catalogs, {len(plugin_words)} plugin words and canonical Saijiki.")


if __name__ == "__main__":
    main()
