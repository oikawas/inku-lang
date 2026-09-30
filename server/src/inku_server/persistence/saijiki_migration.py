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
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from typing import Any

MigrateUnit = Callable[[bytes], bytes]

# How many records each list in the report names; the counts stay exact.
LISTED_RECORDS = 200


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _distinct(definitions: Iterable[Any]) -> list[Any]:
    """Each saved definition once: many performances freeze the same catalog."""
    seen: dict[str, Any] = {}
    for definition in definitions:
        seen.setdefault(_canonical(definition), definition)
    return list(seen.values())


def remembering(migrate: MigrateUnit) -> MigrateUnit:
    """The same unit gives the same answer: ask the core once per distinct unit."""
    answers: dict[bytes, bytes] = {}

    def ask(unit: bytes) -> bytes:
        if unit not in answers:
            answers[unit] = migrate(unit)
        return answers[unit]

    return ask


def migrate_unit(migrate: MigrateUnit, document: Mapping[str, Any] | None,
                 definitions: Iterable[Any]) -> dict[str, Any]:
    """One saved unit through the core; the core's answer, or a refusal code."""
    unit: dict[str, Any] = {"definitions": _distinct(definitions)}
    if document is not None:
        unit["document"] = {
            "source": document.get("source"),
            "language": document.get("language"),
            "macro_locks": document.get("macro_locks") or [],
        }
    output = migrate(_canonical(unit).encode("utf-8"))
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


class _Clock:
    """Time spent in the core per kind of record, to estimate the whole run."""

    def __init__(self, migrate: MigrateUnit) -> None:
        self.migrate = remembering(migrate)
        self.calls: Counter[str] = Counter()
        self.seconds: Counter[str] = Counter()
        self.kind = ""

    def __call__(self, unit: bytes) -> bytes:
        started = time.monotonic()
        try:
            return self.migrate(unit)
        finally:
            self.calls[self.kind] += 1
            self.seconds[self.kind] += time.monotonic() - started


def census(connection: Any, migrate: MigrateUnit, *, sample: int | None = None) -> dict[str, object]:
    """Count what the migration would do to the saved records; write nothing.

    ``connection`` is a DB-API connection (sqlite3) opened read-only. With
    ``sample``, each kind of record is counted on that many rows drawn at
    random, and the definitions and locks a drawn record needs are looked up
    for it, so a drawn document is not refused for a definition that was
    simply not drawn. Each kind reports its total rows, the rows counted, and
    the core's time per call, from which the whole run can be estimated.
    """
    clock = _Clock(migrate)
    limit = f" ORDER BY random() LIMIT {int(sample)}" if sample else ""

    def rows(sql: str, *args: Any) -> list[Any]:
        return connection.execute(sql, args).fetchall()

    def total(table: str) -> int:
        return int(rows(f"SELECT COUNT(*) FROM {table}")[0][0])

    def definitions_saved_for(owner_id: str, variation_id: str) -> list[Any]:
        found: list[Any] = []
        for (context_bytes,) in rows(
            "SELECT fork_context_bytes FROM pipeline_history_links WHERE owner_id=? AND variation_id=?",
            owner_id, variation_id,
        ):
            context = _json(context_bytes)
            if isinstance(context, Mapping):
                found.extend(_definitions_of(context.get("config")))
        for (state_bytes,) in rows(
            "SELECT state_bytes FROM pipeline_candidate_executions WHERE owner_id=? AND variation_id=?",
            owner_id, variation_id,
        ):
            wrapper = _json(state_bytes)
            snapshot = wrapper.get("snapshot") if isinstance(wrapper, Mapping) else None
            if isinstance(snapshot, Mapping):
                found.extend(_definitions_of(snapshot.get("config")))
        return _distinct(found)

    def performed_with(history_id: str) -> tuple[list[Any], list[Any]]:
        for (context_bytes,) in rows(
            "SELECT fork_context_bytes FROM pipeline_history_links WHERE history_id=?", history_id
        ):
            context = _json(context_bytes)
            if isinstance(context, Mapping):
                locks = (context.get("macro_catalog") or {}).get("definition_locks") or []
                return (locks if isinstance(locks, list) else []), _definitions_of(context.get("config"))
        return [], []

    report: dict[str, object] = {}

    clock.kind = "history_links"
    links = _Tally()
    links.counts["total_rows"] = total("pipeline_history_links")
    for owner_id, history_id, context_bytes in rows(
        "SELECT owner_id, history_id, fork_context_bytes FROM pipeline_history_links" + limit
    ):
        links.counts["rows"] += 1
        context = _json(context_bytes)
        if not isinstance(context, Mapping):
            links.refused["unreadable_context"] += 1
            continue
        definitions = _definitions_of(context.get("config"))
        locks = (context.get("macro_catalog") or {}).get("definition_locks") or []
        links.counts["definition_locks"] += len(locks) if isinstance(locks, list) else 0
        if definitions:
            links.counts["with_definitions"] += 1
            answer = migrate_unit(clock, None, definitions)
            links.definitions(f"{owner_id}/{history_id}", answer.get("definitions") or [])
    report["history_links"] = links

    clock.kind = "executions"
    executions = _Tally()
    executions.counts["total_rows"] = total("pipeline_candidate_executions")
    for owner_id, execution_id, state_bytes in rows(
        "SELECT owner_id, execution_id, state_bytes FROM pipeline_candidate_executions" + limit
    ):
        executions.counts["rows"] += 1
        wrapper = _json(state_bytes)
        snapshot = wrapper.get("snapshot") if isinstance(wrapper, Mapping) else None
        if not isinstance(snapshot, Mapping):
            executions.refused["unreadable_snapshot"] += 1
            continue
        definitions = _definitions_of(snapshot.get("config"))
        document = snapshot.get("document")
        record_id = f"{owner_id}/{execution_id}"
        if isinstance(document, Mapping) and "saijiki" not in document:
            executions.counts["documents_v1"] += 1
            executions.document(record_id, migrate_unit(clock, document, definitions).get("document"))
        elif isinstance(document, Mapping):
            executions.counts["documents_current"] += 1
        if definitions:
            executions.counts["with_definitions"] += 1
            executions.definitions(record_id, migrate_unit(clock, None, definitions).get("definitions") or [])
    report["executions"] = executions

    clock.kind = "variation_documents"
    variations = _Tally()
    variations.counts["total_rows"] = total("variation_authority")
    for owner_id, variation_id, document_json in rows(
        "SELECT owner_id, variation_id, document_json FROM variation_authority" + limit
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
        locked = {(lock.get("qualified_name"), lock.get("version")) for lock in document.get("macro_locks") or []
                  if isinstance(lock, Mapping)}
        definitions = []
        if locked:
            variations.counts["with_locks"] += 1
            definitions = [definition for definition in definitions_saved_for(owner_id, variation_id)
                           if isinstance(definition, Mapping)
                           and (f"{definition.get('namespace')}.{definition.get('heading')}",
                                definition.get("version")) in locked]
        answer = migrate_unit(clock, document, definitions)
        variations.document(f"{owner_id}/{variation_id}", answer.get("document"))
    report["variation_documents"] = variations

    clock.kind = "history"
    history = _Tally()
    history.counts["total_rows"] = total("history")
    for history_id, ddl, expanded_ddl, language in rows(
        "SELECT id, ddl, expanded_ddl, instruction_lang_resolved FROM history" + limit
    ):
        history.counts["rows"] += 1
        language = language if language in {"ja", "en"} else "ja"
        locks, definitions = performed_with(history_id)
        for column, source in (("ddl", ddl), ("expanded_ddl", expanded_ddl)):
            if not source:
                continue
            history.counts[f"{column}_present"] += 1
            answer = migrate_unit(clock, {"source": source, "language": language, "macro_locks": locks}, definitions)
            history.document(f"{history_id}:{column}", answer.get("document"))
    report["history"] = history

    return {
        "sample": sample,
        "core_calls": dict(clock.calls),
        "core_ms_per_call": {
            kind: round(clock.seconds[kind] * 1000 / calls, 1) for kind, calls in clock.calls.items() if calls
        },
        **{kind: tally.report() for kind, tally in report.items()},
    }
