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


def resolve_new_work_macro_catalog(binding: object, pipeline_config: Mapping[str, Any]) -> dict[str, Any]:
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
    output = json.loads(
        resolver(
            _bytes(
                {
                    "maximum_entries": maximum_entries,
                    "canonical": _canonical_candidates(definitions, summaries),
                    "legacy": legacy,
                    "bundled_packages": bundled_packages,
                    "language": pipeline_config.get("language", "en"),
                }
            )
        )
    )
    if output.get("schema") != "inku.macro-catalog-resolution.v1" or "error" in output:
        raise CandidateHostError(output.get("error", "invalid_macro_catalog_output"))
    entries = output.get("entries")
    locks = output.get("locks")
    diagnostics = output.get("diagnostics")
    if not isinstance(entries, list) or not isinstance(locks, list) or not isinstance(diagnostics, list):
        raise CandidateHostError("invalid_macro_catalog_output")
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
