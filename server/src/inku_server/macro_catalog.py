"""Thin host discovery adapter for the shared Rust MacroDefinition registry."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .pipeline_candidate import CandidateHostError
from .plugins import PLUGIN_PACKAGE_MANAGER


def _bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()


def _canonical_candidates(
    definitions: Sequence[object], summaries: Sequence[object]
) -> list[dict[str, str]]:
    if len(definitions) != len(summaries):
        raise CandidateHostError("macro_catalog_summary_mismatch")
    candidates = []
    for index, (definition, summary) in enumerate(zip(definitions, summaries, strict=True)):
        if not isinstance(definition, Mapping) or not isinstance(summary, str):
            raise CandidateHostError("invalid_macro_catalog_source")
        candidates.append(
            {
                "source_id": f"manifest:definitions[{index}]",
                "definition_json": json.dumps(
                    definition,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ),
                "summary": summary,
            }
        )
    return candidates


def _installed_candidates() -> tuple[list[dict[str, str]], list[str]]:
    return [], ["Nature.leaves"] if PLUGIN_PACKAGE_MANAGER.is_enabled("Nature.leaves") else []


def _imported_candidates(imported: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "source_id": f"imported:{index}",
            "definition_json": json.dumps(item["definition"], ensure_ascii=False, allow_nan=False, separators=(",", ":")),
            # Stage 1 requires a summary; an export without one still names the plugin.
            "summary": str(item.get("note") or "").strip()
            or f"{item['definition'].get('namespace')}.{item['definition'].get('id') or item['definition'].get('heading')}",
        }
        for index, item in enumerate(imported)
    ]


def _resolve(binding: object, maximum_entries: int, canonical: list, legacy: list, bundled: list, language: str) -> dict:
    output = json.loads(
        binding.resolve_macro_catalog(
            _bytes(
                {
                    "maximum_entries": maximum_entries,
                    "canonical": canonical,
                    "legacy": legacy,
                    "bundled_packages": bundled,
                    "language": language,
                }
            )
        )
    )
    if output.get("schema") != "inku.macro-catalog-resolution.v1" or "error" in output:
        raise CandidateHostError(output.get("error", "invalid_macro_catalog_output"))
    if not all(isinstance(output.get(key), list) for key in ("entries", "locks", "diagnostics")):
        raise CandidateHostError("invalid_macro_catalog_output")
    return output


def _with_imported(
    binding: object, maximum_entries: int, installed: list, legacy: list, bundled: list, language: str,
    imported: Sequence[Mapping[str, Any]],
) -> dict:
    """Resolve imported definitions ahead of the installed ones.

    An imported definition wins its name for this work. The installed edition it
    shadows is not an error: identical content is silent, a different one or a
    name this server lacks is reported so the author knows which was used.
    """
    base = _resolve(binding, maximum_entries, installed, legacy, bundled, language)
    installed_digests = {entry["qualified_name"]: entry["digest"] for entry in base["entries"]}
    output = _resolve(binding, maximum_entries, _imported_candidates(imported) + installed, legacy, bundled, language)
    imported_names = {
        entry["qualified_name"]: entry["digest"]
        for entry in output["entries"]
        if str(entry.get("source_id", "")).startswith("imported:")
    }
    diagnostics = [
        item for item in output["diagnostics"]
        if not (item.get("reason") == "duplicate_qualified_name" and item.get("qualified_name") in imported_names
                and not str(item.get("source_id", "")).startswith("imported:"))
    ]
    for name, digest in sorted(imported_names.items()):
        if name not in installed_digests:
            reason = "imported_plugin_not_installed"
        elif installed_digests[name] != digest:
            reason = "imported_plugin_differs_from_installed"
        else:
            continue
        diagnostics.append({"source_id": "imported", "qualified_name": name, "disposition": "used",
                            "reason": reason, "warnings": [], "findings": []})
    return {**output, "diagnostics": diagnostics}


def resolve_new_work_macro_catalog(
    binding: object, pipeline_config: Mapping[str, Any], imported: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """Resolve current installed definitions for a new work only.

    Saved configs already contain their exact definitions and must bypass this
    function. Legacy Markdown contributes warning-bearing omissions; its prose
    expansion is never interpreted or reactivated here.
    """

    resolver = getattr(binding, "resolve_macro_catalog", None)
    if resolver is None:
        raise CandidateHostError("binding_macro_catalog_unavailable")
    prompt_limits = pipeline_config.get("prompt_limits")
    if not isinstance(prompt_limits, Mapping):
        raise CandidateHostError("invalid_macro_catalog_source")
    maximum_entries = prompt_limits.get("max_catalog_entries")
    if not isinstance(maximum_entries, int) or isinstance(maximum_entries, bool) or maximum_entries <= 0:
        raise CandidateHostError("invalid_macro_catalog_source")
    definitions = pipeline_config.get("definitions", [])
    summaries = pipeline_config.get("macro_summaries", [])
    if not isinstance(definitions, Sequence) or isinstance(definitions, (str, bytes)):
        raise CandidateHostError("invalid_macro_catalog_source")
    if not isinstance(summaries, Sequence) or isinstance(summaries, (str, bytes)):
        raise CandidateHostError("invalid_macro_catalog_source")
    legacy, bundled_packages = _installed_candidates()
    language = pipeline_config.get("language", "en")
    # The manifest's definitions first, then the packages an administrator
    # installed from the Web; both ahead of the bundled editions.
    installed = _canonical_candidates(definitions, summaries) + PLUGIN_PACKAGE_MANAGER.catalog_candidates(language)
    if imported:
        output = _with_imported(binding, maximum_entries, installed, legacy, bundled_packages, language, imported)
    else:
        output = _resolve(binding, maximum_entries, installed, legacy, bundled_packages, language)
    entries, locks, diagnostics = output["entries"], output["locks"], output["diagnostics"]
    return {
        "definitions": [entry["definition"] for entry in entries],
        "macro_summaries": [entry["summary"] for entry in entries],
        "definition_locks": locks,
        "diagnostics": diagnostics,
    }


def _installed_plugin_names() -> tuple[list[str], list[str]]:
    """Visible names and legacy identifiers of enabled and disabled packages."""
    enabled = set(PLUGIN_PACKAGE_MANAGER.visible_names(enabled=True))
    disabled = set(PLUGIN_PACKAGE_MANAGER.visible_names(enabled=False))
    for package in (*PLUGIN_PACKAGE_MANAGER.packages(), PLUGIN_PACKAGE_MANAGER.bundled()[0]):
        target = enabled if PLUGIN_PACKAGE_MANAGER.is_enabled(package.id) else disabled
        target.update(word.qualified_name for word in package.words)
    return sorted(enabled), sorted(disabled)


def installed_plugin_name_entries() -> list[dict[str, object]]:
    entries = []
    for package in (*PLUGIN_PACKAGE_MANAGER.packages(), PLUGIN_PACKAGE_MANAGER.bundled()[0]):
        active = PLUGIN_PACKAGE_MANAGER.is_enabled(package.id)
        for word in package.words:
            entries.extend({"name": name, "qualified_name": word.qualified_name, "enabled": active}
                           for name in word.visible_qualified_names())
    return entries


def plugin_offer_records(config: Mapping[str, Any], extra: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Project the run's saved offers using the definitions saved with it."""
    definitions = {}
    for definition in config.get("definitions", []):
        if not isinstance(definition, Mapping):
            continue
        identifier = f"{definition.get('namespace', '')}.{definition.get('id') or definition.get('heading', '')}"
        names = definition.get("names") or {}
        heading = str(definition.get("heading") or definition.get("id") or "")
        ja = (names.get("ja") or definition.get("aliases") or [heading])[0]
        legacy_en = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", heading).replace("_", " ").replace("-", " ").lower()
        en = (names.get("en") or [" ".join(legacy_en.split())])[0]
        definitions[identifier] = (f"｛{ja}｝", f"{{{en}}}")
    result = []
    for record in [*(config.get("plugin_offers") or []), *extra]:
        offer = record.get("offer") or {}
        def items(key):
            result_items = []
            for item in offer.get(key, []):
                qualified = item.get("qualified_name", "")
                ja, en = definitions.get(qualified, (f"｛{qualified}｝", f"{{{qualified}}}"))
                result_items.append({**item, "written_ja": item.get("written_ja") or ja,
                                     "written_en": item.get("written_en") or en})
            return result_items
        result.append({"stage": record.get("stage"), "offered": items("offered"), "omitted": items("omitted")})
    return result


def explain_plugin_diagnostics(
    binding: object, source: str, upstream_diagnostics: Sequence[Any],
    work_plugins: Sequence[str | Mapping[str, str]] = (),
) -> list[dict[str, Any]]:
    """Author-facing reasons for plugin sentences the compiler withheld.

    `work_plugins` are the names this work could use (its saved or imported
    definitions); they count as enabled even when this server lacks them.
    An older native wheel without the shared explainer yields no reasons.
    """
    explainer = getattr(binding, "explain_plugin_diagnostics", None)
    if explainer is None or not upstream_diagnostics:
        return []
    enabled, disabled = _installed_plugin_names()
    plugin_names = installed_plugin_name_entries()
    work_ids = []
    for item in work_plugins:
        if isinstance(item, str):
            work_ids.append(item)
            plugin_names.append({"name": item, "qualified_name": item, "enabled": True})
        elif isinstance(item, Mapping) and isinstance(item.get("name"), str) and isinstance(item.get("qualified_name"), str):
            work_ids.append(item["qualified_name"])
            plugin_names.append({"name": item["name"], "qualified_name": item["qualified_name"], "enabled": True})
    output = json.loads(
        explainer(
            _bytes(
                {
                    "source": source,
                    "upstream_diagnostics": list(upstream_diagnostics),
                    "enabled": sorted(set(enabled) | set(work_ids)),
                    "disabled": disabled,
                    "plugin_names": plugin_names,
                }
            )
        )
    )
    plugins = output.get("plugins")
    return plugins if output.get("schema") == "inku.plugin-diagnostics.v1" and isinstance(plugins, list) else []
