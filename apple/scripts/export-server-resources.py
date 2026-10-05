"""Generate Apple installation data from the Server-owned source defaults."""

from __future__ import annotations

import ast
import argparse
import json
import runpy
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[2]
DESTINATION_ROOT = ROOT
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


def provider_catalog() -> tuple[dict, list[dict]]:
    # This versioned module contains data expressions only; loading it does not
    # import Server settings, inspect credentials or contact a provider.
    catalog = runpy.run_path(str(SERVER / "verified_model_catalog.py"))

    def resolve(node):
        if isinstance(node, ast.Name):
            return catalog[node.id]
        if isinstance(node, ast.List):
            return [resolve(item) for item in node.elts]
        if isinstance(node, ast.Dict):
            return {resolve(key): resolve(value) for key, value in zip(node.keys, node.values)}
        return ast.literal_eval(node)

    source = ast.parse((SERVER / "model_settings.py").read_text())
    definition = next(node.value for node in source.body if isinstance(node, ast.AnnAssign)
                      and isinstance(node.target, ast.Name) and node.target.id == "PROVIDER_DEFINITIONS")
    return catalog, resolve(definition)


def provider_defaults() -> dict:
    # Allowlist public versioned fields only. Do not call default_model_settings:
    # that factory also reads installation URLs and API keys from the environment.
    _, definitions = provider_catalog()
    return {
        "schema": "inku.provider-defaults.v1",
        "providers": [{
            "id": provider["id"],
            "label": provider["label"],
            "kind": provider["kind"],
            "baseURL": provider["default_base_url"],
            "requiresAPIKey": provider["requires_api_key"],
            "credentialID": provider["id"],
        } for provider in definitions],
    }


def model_guidance() -> dict:
    catalog, definitions = provider_catalog()
    model_keys = {
        "id", "label", "purposes", "recommendation_llm", "recommendation_vision",
        "recommendation_stage1", "recommendation_stage2", "recommendation_level",
        "speed_class", "speed_label", "comment_ja", "comment_en", "eol", "eol_date",
        "requires_subscription",
    }
    providers = []
    for provider in definitions:
        hide_speed = bool(provider.get("speed_developer_only"))
        models = []
        for model in provider["models"]:
            shown = {key: value for key, value in model.items() if key in model_keys}
            # Match the release Server catalog's speed visibility. The evaluation
            # comments remain verbatim, including their measurement caveats.
            if hide_speed:
                shown.pop("speed_class", None)
                shown.pop("speed_label", None)
            models.append(shown)
        providers.append({"id": provider["id"], "label": provider["label"],
                          "kind": provider["kind"], "speed_hidden": hide_speed, "models": models})
    return {"schema": "inku.model-guidance.v1", "version": catalog["MODEL_CONFIG_VERSION"],
            "updated": catalog["MODEL_CONFIG_LAST_UPDATED"], "providers": providers}


class BindingPlaceholder:
    """Palette and registry are resolved by the real Rust core at runtime."""

    canvas_registry: ClassVar[dict] = {"registry": {"schema": ""}, "digest": ""}

    @staticmethod
    def resolve_palette(_request: bytes) -> bytes:
        return b"{}"


def main() -> None:
    global ROOT, SERVER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT, help="Product checkout containing the canonical Server/Web resources")
    arguments = parser.parse_args()
    ROOT = arguments.source_root.resolve()
    SERVER = ROOT / "server/src/inku_server"
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
    # Match Server render_color_map_for_catalog without loading installation
    # settings: palette names are verbatim and later duplicate names win.
    catalog_maps = {}
    for item in catalogs:
        color_map = dict(item["map"])
        for color in item["palette"]:
            color_map[f"palette:{color['name']}"] = color["code"]
        catalog_maps[item["id"]] = color_map
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
    manifest["model_guidance"] = model_guidance()
    manifest["provider_defaults"] = provider_defaults()
    rules = []
    normalization = next(node for node in limit_source.body if isinstance(node, ast.FunctionDef)
                         and node.name == "normalize_limits")
    for node in normalization.body:
        if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Subscript)
                and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "min"):
            rules.append({"target": ast.literal_eval(node.targets[0].slice),
                          "ceiling": ast.literal_eval(node.value.args[1].slice)})
    settings_source = ast.parse((SERVER / "pipeline_settings.py").read_text())
    budget_mapping = next(ast.literal_eval(node.value) for node in ast.walk(settings_source)
                          if isinstance(node, ast.Assign) and any(
                              isinstance(target, ast.Name) and target.id == "mapping" for target in node.targets))
    manifest["drawing_limits"] = {
        "defaults": limits,
        "absoluteMaximum": literal_assignment(SERVER / "limits.py", "LIMIT_ABSOLUTE_MAX"),
        "groups": [{"id": name, "fields": list(fields)}
                   for name, fields in literal_assignment(SERVER / "limits.py", "LIMIT_GROUPS")],
        "normalization": rules,
        "budgetMapping": budget_mapping,
        "bytesPerMark": literal_assignment(SERVER / "limits.py", "BYTES_PER_MARK"),
    }
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
    subprocess.run(["node", str(DESTINATION_ROOT / "apple/scripts/export-web-reference.mjs"), "--source-root", str(ROOT)], check=True)
    print(f"Generated Server defaults, {len(catalogs)} catalogs, {len(plugin_words)} plugin words and canonical Saijiki.")


if __name__ == "__main__":
    main()
