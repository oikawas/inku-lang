"""Portable v2 DDL export with the definitions selected by saved locks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DDL_EXPORT_SCHEMA = "inku.ddl-export.v2"


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
        "schema": DDL_EXPORT_SCHEMA, "language": language, "ddl": source,
        "plugins": plugins, "exported_from": dict(exported_from or {}),
    }
