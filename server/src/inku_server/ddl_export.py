"""Portable v2 DDL export with the definitions selected by saved locks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

DDL_EXPORT_SCHEMA = "inku.ddl-export.v2"


def migrate_v2_export(source: str, language: str, plugins: list[dict[str, Any]], *,
                      include_details: bool = False) -> dict[str, Any]:
    """Migrate one portable export with locks derived from its own definitions."""
    import inku_render

    definitions = [item["definition"] for item in plugins]
    # A v2 definition may contain old touch IDs that the v3 catalog quite
    # correctly refuses. Migrate definitions first, then bind the document to
    # their new identities; otherwise old exported packages cannot be read.
    first = json.loads(inku_render.pipeline_migrate_saijiki_v2(
        json.dumps({"definitions": definitions}, ensure_ascii=False).encode()))
    entries = first.get("definitions", [])
    if (first.get("error") or len(entries) != len(definitions)
            or any(not isinstance(entry, dict) or entry.get("error") for entry in entries)):
        raise ValueError("invalid_export_definitions")
    locks = [{"qualified_name": entry["qualified_name"], "version": entry["version"],
              "digest": entry["digest"] if entry["digest"].startswith("sha256:")
              else "sha256:" + entry["digest"]} for entry in entries]
    request = {"document": {"source": source, "language": language, "macro_locks": locks,
                             "saijiki": "inku.saijiki.v2"},
               "definitions": [entry["definition"] for entry in entries]}
    result = json.loads(inku_render.pipeline_migrate_saijiki_v2(
        json.dumps(request, ensure_ascii=False).encode()))
    document = result.get("document")
    migrated = result.get("definitions")
    if (result.get("error") or not isinstance(document, dict) or document.get("error")
            or not isinstance(document.get("document"), dict) or not isinstance(migrated, list)
            or len(migrated) != len(plugins) or any("error" in item for item in migrated)):
        raise ValueError("saijiki_export_migration_refused")
    response = {"ddl": document["document"]["source"],
                "plugins": [{"definition": item["definition"], "note": plugin.get("note", "")}
                            for item, plugin in zip(migrated, plugins, strict=True)],
                "edits": len(document.get("edits", []))}
    if include_details:
        response["edit_details"] = document.get("edits", [])
        response["unassociated_tools"] = document.get("unassociated_tools", [])
        response["unassociated_sweeps"] = document.get("unassociated_sweeps", [])
    return response


def _qualified_name(definition: Mapping[str, Any]) -> str | None:
    namespace = definition.get("namespace")
    identifier = definition.get("id") or definition.get("heading")
    return f"{namespace}.{identifier}" if isinstance(namespace, str) and isinstance(identifier, str) else None


def build_ddl_export(
    source: str,
    language: str,
    definitions: Sequence[Mapping[str, Any]] = (),
    summaries: Sequence[str] = (),
    exported_from: Mapping[str, Any] | None = None,
    *,
    locks: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Carry only the exact definitions the work locked, independent of spelling."""
    plugins = []
    seen: set[tuple[str, str]] = set()
    locked = {(lock.get("qualified_name"), lock.get("version")) for lock in locks}
    for index, definition in enumerate(definitions):
        name = _qualified_name(definition)
        version = definition.get("version")
        if name is None or (name, version) not in locked or (name, version) in seen:
            continue
        seen.add((name, version))
        note = summaries[index] if index < len(summaries) and isinstance(summaries[index], str) else ""
        plugins.append({"definition": dict(definition), "note": note})
    return {
        "schema": DDL_EXPORT_SCHEMA, "saijiki": "inku.saijiki.v3", "language": language, "ddl": source,
        "plugins": plugins, "exported_from": dict(exported_from or {}),
    }
