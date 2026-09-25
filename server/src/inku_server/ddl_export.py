"""Portable DDL export: the visible DDL with the plugin definitions it uses.

A saved work already keeps its exact plugin definitions, so it redraws the same
way on this server. Plain DDL text does not: another server may lack a plugin or
hold a different edition. An export carries the definitions the DDL names so the
reading side can use them for that work alone (see macro_catalog imported
definitions). Definitions are data-only `inku.macro-definition.v1` objects and
are validated again by the shared Rust boundary when they are read.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DDL_EXPORT_SCHEMA = "inku.ddl-export.v1"


def _qualified_name(definition: Mapping[str, Any]) -> str | None:
    namespace, heading = definition.get("namespace"), definition.get("heading")
    return f"{namespace}.{heading}" if isinstance(namespace, str) and isinstance(heading, str) else None


def _visible_names(definition: Mapping[str, Any]) -> list[str]:
    """The canonical qualified name and its aliases; the DDL may write any of them."""
    name = _qualified_name(definition)
    if name is None:
        return []
    aliases = definition.get("aliases") or []
    return [name, *(f"{definition['namespace']}.{alias}" for alias in aliases if isinstance(alias, str))]


def build_ddl_export(
    source: str,
    language: str,
    definitions: Sequence[Mapping[str, Any]] = (),
    summaries: Sequence[str] = (),
    exported_from: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep only the definitions whose qualified name the DDL writes."""
    plugins = []
    seen: set[str] = set()
    for index, definition in enumerate(definitions):
        name = _qualified_name(definition)
        if name is None or name in seen or not any(visible in source for visible in _visible_names(definition)):
            continue
        seen.add(name)
        summary = summaries[index] if index < len(summaries) and isinstance(summaries[index], str) else ""
        plugins.append({"definition": dict(definition), "summary": summary})
    return {
        "schema": DDL_EXPORT_SCHEMA,
        "language": language,
        "ddl": source,
        "plugins": plugins,
        "exported_from": dict(exported_from or {}),
    }
