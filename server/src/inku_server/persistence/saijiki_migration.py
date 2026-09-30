"""The one-time move of saved records from Saijiki v1 to the current edition.

Saijiki v2 (DDL 16) names its edition on every visible document; a saved
document without the field was written with v1, and the core refuses it, and a
saved Macro definition that only a migration makes valid, with
``saijiki_migration_required``. The core owns the migration itself
(``migrate_saijiki_v1``, exposed by the native wheel as
``pipeline_migrate_saijiki_v1``): given one saved unit -- a v1 document and the
definitions its locks name, or definitions alone -- it returns the unit in the
current edition.

This module reads the saved records as those units. ``census`` only counts:
it writes nothing, and it is what an isolated copy of the production database
is measured with before anyone decides how and when the records are written
over (the author, 2026-09-30). The records are

- the committed document of each variation (``variation_authority``),
- the definitions and locks frozen with each performance
  (``pipeline_history_links.fork_context_bytes``: ``config.definitions`` and
  ``macro_catalog.definition_locks``),
- the latest execution snapshot of each run
  (``pipeline_candidate_executions.state_bytes``: its document and
  ``config.definitions``),
- the instructions of each saved work (``history.ddl`` and
  ``history.expanded_ddl``).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from typing import Any

MigrateUnit = Callable[[bytes], bytes]

# How many records each list in the report names; the counts stay exact.
LISTED_RECORDS = 200


def migrate_unit(migrate: MigrateUnit, document: Mapping[str, Any] | None,
                 definitions: Iterable[Any]) -> dict[str, Any]:
    """One saved unit through the core; the core's answer, or a refusal code."""
    unit: dict[str, Any] = {"definitions": list(definitions)}
    if document is not None:
        unit["document"] = {
            "source": document.get("source"),
            "language": document.get("language"),
            "macro_locks": document.get("macro_locks") or [],
        }
    output = migrate(json.dumps(unit, ensure_ascii=False).encode("utf-8"))
    try:
        answer = json.loads(output.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"error": {"code": "unreadable_answer"}}
    if not isinstance(answer, dict):
        return {"error": {"code": "unreadable_answer"}}
    return answer


def _json(value: Any) -> Any:
    try:
        return json.loads(bytes(value).decode("utf-8") if isinstance(value, (bytes, memoryview)) else value)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None


class _Tally:
    """Counts for one kind of record, and the records worth naming."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.refused: Counter[str] = Counter()
        self.edits: Counter[str] = Counter()
        self.refused_records: list[dict[str, str]] = []
        self.sweep_records: list[dict[str, object]] = []

    def document(self, record_id: str, answer: Mapping[str, Any] | None) -> None:
        if answer is None:
            return
        if "error" in answer:
            code = str((answer.get("error") or {}).get("code") or "unknown")
            self.refused[code] += 1
            if len(self.refused_records) < LISTED_RECORDS:
                self.refused_records.append({"id": record_id, "code": code})
            return
        edits = answer.get("edits") or []
        self.counts["migrated_changed" if edits else "migrated_unchanged"] += 1
        for edit in edits:
            self.edits[f"{edit.get('original')} -> {edit.get('replacement')}"] += 1
        sweeps = answer.get("unassociated_sweeps") or []
        if sweeps:
            self.counts["with_unassociated_sweeps"] += 1
            if len(self.sweep_records) < LISTED_RECORDS:
                self.sweep_records.append({"id": record_id, "count": len(sweeps)})

    def definitions(self, record_id: str, answers: Iterable[Mapping[str, Any]]) -> None:
        for answer in answers:
            if "error" in answer:
                code = str((answer.get("error") or {}).get("code") or "unknown")
                self.refused[f"definition:{code}"] += 1
                if len(self.refused_records) < LISTED_RECORDS:
                    self.refused_records.append({"id": record_id, "code": f"definition:{code}"})
            else:
                self.counts["definitions_changed" if answer.get("changed") else "definitions_unchanged"] += 1

    def report(self) -> dict[str, object]:
        return {
            **dict(sorted(self.counts.items())),
            "refused": dict(sorted(self.refused.items())),
            "edits": dict(self.edits.most_common()),
            "refused_records": self.refused_records,
            "unassociated_sweep_records": self.sweep_records,
        }


def _definitions_of(config: Any) -> list[Any]:
    definitions = config.get("definitions") if isinstance(config, Mapping) else None
    return list(definitions) if isinstance(definitions, list) else []


def census(connection: Any, migrate: MigrateUnit) -> dict[str, object]:
    """Count what the migration would do to every saved record; write nothing.

    ``connection`` is a DB-API connection (sqlite3) opened read-only.
    """
    rows = lambda sql: connection.execute(sql).fetchall()  # noqa: E731

    # Definitions saved with each variation, to hand the core with its document.
    saved_definitions: dict[tuple[str, str], list[Any]] = {}
    # The locks and definitions a saved work was performed with, for its instructions.
    performed_with: dict[str, tuple[list[Any], list[Any]]] = {}
    links = _Tally()
    for owner_id, history_id, variation_id, context_bytes in rows(
        "SELECT owner_id, history_id, variation_id, fork_context_bytes FROM pipeline_history_links"
    ):
        links.counts["rows"] += 1
        context = _json(context_bytes)
        if not isinstance(context, Mapping):
            links.refused["unreadable_context"] += 1
            continue
        definitions = _definitions_of(context.get("config"))
        locks = (context.get("macro_catalog") or {}).get("definition_locks") or []
        locks = locks if isinstance(locks, list) else []
        links.counts["definition_locks"] += len(locks)
        performed_with[history_id] = (locks, definitions)
        if definitions:
            links.counts["with_definitions"] += 1
            saved_definitions.setdefault((owner_id, variation_id), []).extend(definitions)
            answer = migrate_unit(migrate, None, definitions)
            links.definitions(f"{owner_id}/{history_id}", answer.get("definitions") or [])

    executions = _Tally()
    for owner_id, execution_id, variation_id, state_bytes in rows(
        "SELECT owner_id, execution_id, variation_id, state_bytes FROM pipeline_candidate_executions"
    ):
        executions.counts["rows"] += 1
        wrapper = _json(state_bytes)
        snapshot = wrapper.get("snapshot") if isinstance(wrapper, Mapping) else None
        if not isinstance(snapshot, Mapping):
            executions.refused["unreadable_snapshot"] += 1
            continue
        definitions = _definitions_of(snapshot.get("config"))
        if definitions:
            saved_definitions.setdefault((owner_id, variation_id), []).extend(definitions)
        document = snapshot.get("document")
        record_id = f"{owner_id}/{execution_id}"
        if isinstance(document, Mapping) and "saijiki" not in document:
            executions.counts["documents_v1"] += 1
            executions.document(record_id, migrate_unit(migrate, document, definitions).get("document"))
        elif isinstance(document, Mapping):
            executions.counts["documents_current"] += 1
        if definitions:
            executions.counts["with_definitions"] += 1
            executions.definitions(record_id, migrate_unit(migrate, None, definitions).get("definitions") or [])

    variations = _Tally()
    for owner_id, variation_id, document_json in rows(
        "SELECT owner_id, variation_id, document_json FROM variation_authority"
    ):
        variations.counts["rows"] += 1
        document = _json(document_json)
        if not isinstance(document, Mapping):
            variations.refused["unreadable_document"] += 1
            continue
        if "saijiki" in document:
            variations.counts["current"] += 1
            continue
        variations.counts["v1"] += 1
        if document.get("macro_locks"):
            variations.counts["with_locks"] += 1
        answer = migrate_unit(migrate, document, saved_definitions.get((owner_id, variation_id), []))
        variations.document(f"{owner_id}/{variation_id}", answer.get("document"))

    history = _Tally()
    for history_id, ddl, expanded_ddl, language in rows(
        "SELECT id, ddl, expanded_ddl, instruction_lang_resolved FROM history"
    ):
        history.counts["rows"] += 1
        language = language if language in {"ja", "en"} else "ja"
        for column, source in (("ddl", ddl), ("expanded_ddl", expanded_ddl)):
            if not source:
                continue
            history.counts[f"{column}_present"] += 1
            locks, definitions = performed_with.get(history_id, ([], []))
            answer = migrate_unit(migrate, {"source": source, "language": language, "macro_locks": locks}, definitions)
            history.document(f"{history_id}:{column}", answer.get("document"))

    return {
        "variation_documents": variations.report(),
        "history_links": links.report(),
        "executions": executions.report(),
        "history": history.report(),
    }
