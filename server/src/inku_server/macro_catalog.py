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


def _legacy_candidates() -> list[dict[str, str]]:
    candidates = []
    for document in DOCUMENT_PLUGIN_MANAGER.documents():
        source_id = (
            Path(document.source_path).name
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
    return candidates


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
    output = json.loads(
        resolver(
            _bytes(
                {
                    "maximum_entries": maximum_entries,
                    "canonical": _canonical_candidates(definitions, summaries),
                    "legacy": _legacy_candidates(),
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
