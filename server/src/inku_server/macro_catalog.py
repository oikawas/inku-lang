"""Thin host discovery adapter for the shared Rust MacroDefinition registry."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .pipeline_candidate import CandidateHostError
from .plugins import DOCUMENT_PLUGIN_MANAGER


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
    candidates = []
    bundled_packages = []
    bundled_document = Path(__file__).resolve().parents[2] / "plugins/nature-leaves.inku-plugin.md"
    for document in DOCUMENT_PLUGIN_MANAGER.documents():
        # The installed document remains the enable/disable handle. Arbitrary
        # user Markdown with the same namespace is not translated implicitly.
        is_bundled = document.source_path and Path(document.source_path).resolve() == bundled_document
        if is_bundled:
            bundled_packages.append("Nature.leaves")
        source_id = (
            "bundled:Nature.leaves" if is_bundled else Path(document.source_path).name
            if document.source_path
            else document.manifest.name
        )
        for entry in document.entries:
            candidates.append(
                {
                    "source_id": source_id,
                    "qualified_name": entry.qualified_name(document.manifest.namespace),
                }
            )
    return candidates, bundled_packages


def _imported_candidates(imported: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "source_id": f"imported:{index}",
            "definition_json": json.dumps(item["definition"], ensure_ascii=False, allow_nan=False, separators=(",", ":")),
            # Stage 1 requires a summary; an export without one still names the plugin.
            "summary": str(item.get("summary") or "").strip()
            or f"{item['definition'].get('namespace')}.{item['definition'].get('heading')}",
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
    installed = _canonical_candidates(definitions, summaries)
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
    """Qualified names of enabled and of installed-but-disabled plugin documents."""
    from .plugins.document_format import PluginFormatError, parse_plugin_document

    enabled = sorted(
        entry.qualified_name(document.manifest.namespace)
        for document in DOCUMENT_PLUGIN_MANAGER.documents()
        for entry in document.entries
    )
    disabled = []
    for item in DOCUMENT_PLUGIN_MANAGER.items():
        if item.enabled:
            continue
        try:
            document = parse_plugin_document(
                (DOCUMENT_PLUGIN_MANAGER.directory / item.path).read_text(encoding="utf-8"),
                source_path=item.path,
            )
        except (OSError, PluginFormatError):
            continue
        disabled.extend(entry.qualified_name(document.manifest.namespace) for entry in document.entries)
    return enabled, sorted(disabled)


def explain_plugin_diagnostics(
    binding: object, source: str, upstream_diagnostics: Sequence[Any], work_plugins: Sequence[str] = ()
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
    output = json.loads(
        explainer(
            _bytes(
                {
                    "source": source,
                    "upstream_diagnostics": list(upstream_diagnostics),
                    "enabled": sorted(set(enabled) | set(work_plugins)),
                    "disabled": disabled,
                }
            )
        )
    )
    plugins = output.get("plugins")
    return plugins if output.get("schema") == "inku.plugin-diagnostics.v1" and isinstance(plugins, list) else []
