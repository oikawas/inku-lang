"""The one-time move of saved records from Saijiki v1 to the current edition.

Saijiki v2 (DDL 16) names its edition on every visible document; a saved
document without the field was written with v1, and the core refuses it, and a
saved Macro definition that only a migration makes valid, with
``saijiki_migration_required``. The core owns the migration itself
(``migrate_saijiki_v1``, exposed by the native wheel as
``pipeline_migrate_saijiki_v1``): given one saved unit -- a v1 document and the
definitions its locks name, or definitions alone -- it returns the unit in the
current edition.

``plan`` reads the saved records as those units, asks the core, and returns
the statements that would write the answers over them, with a report of what
changes, what stays, and what the core refuses. ``census`` only reports (an
isolated read-only copy of the production database is counted with it), and
``migrate_saved_records`` writes the same plan once, inside the startup
migration's writer transaction (SPEC §3.3; the plan the author and the draw
session agreed on 2026-09-30):

- the committed document of each variation (``variation_authority``): its
  source, its document with the edition and the moved locks, and its digest;
  the acknowledgment of its current revision follows the new digest, so the
  next performance of it can still be linked;
- the definitions and locks frozen with each performance
  (``pipeline_history_links.fork_context_bytes``: ``config.definitions`` and
  ``macro_catalog.definition_locks``), with the digests that bind them to the
  work's instructions;
- the instructions of each saved work (``history.ddl`` and
  ``history.expanded_ddl``); its description, Score and SVG are never touched;
- the execution snapshots (``pipeline_candidate_executions``) are discarded,
  not migrated (the author, 2026-09-30).

A record the core refuses is left as it was and listed; it need not be perfect
(the author, 2026-09-30): v2 refuses an unmigrated record with
``saijiki_migration_required`` and nothing else breaks.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

MigrateUnit = Callable[[bytes], bytes]
Progress = Callable[[str], None]

# The table whose rows the migration discards instead of moving.
DISCARDED_TABLE = "pipeline_candidate_executions"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(value: Any) -> Any:
    try:
        return json.loads(bytes(value).decode("utf-8") if isinstance(value, (bytes, memoryview)) else value)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _execute(connection: Any, sql: str, args: tuple[Any, ...] = ()) -> Any:
    """A DB-API connection (sqlite3) or a SQLAlchemy connection, with qmark parameters."""
    driver = getattr(connection, "exec_driver_sql", None)
    if driver is not None:
        return driver(sql, args) if args else driver(sql)
    return connection.execute(sql, args)


def _rows(connection: Any, sql: str, args: tuple[Any, ...] = ()) -> Iterator[Any]:
    result = _execute(connection, sql, args)
    while batch := result.fetchmany(256):
        yield from batch


def _definitions_of(config: Any) -> list[Any]:
    definitions = config.get("definitions") if isinstance(config, Mapping) else None
    return list(definitions) if isinstance(definitions, list) else []


def _distinct(definitions: Iterable[Any]) -> list[Any]:
    """Each saved definition once: many performances freeze the same catalog."""
    seen: dict[str, Any] = {}
    for definition in definitions:
        seen.setdefault(_canonical(definition), definition)
    return list(seen.values())


_LOCK_FIELDS = ("qualified_name", "version", "digest", "aliases")


def document_locks(locks: Any) -> list[Any]:
    """The locks as a document holds them.

    A macro catalog freezes each lock's digest as bare hex; a document's lock
    carries it as ``sha256:<hex>``, and the core reads only that form.
    """
    moved: list[Any] = []
    for lock in locks if isinstance(locks, list) else []:
        if not isinstance(lock, Mapping):
            moved.append(lock)
            continue
        entry = {key: lock[key] for key in _LOCK_FIELDS if key in lock}
        digest = entry.get("digest")
        if isinstance(digest, str) and not digest.startswith("sha256:"):
            entry["digest"] = f"sha256:{digest}"
        moved.append(entry)
    return moved


def _definition_unit(definition: Any) -> bytes:
    return _canonical({"definitions": [definition]}).encode("utf-8")


def _document_unit(source: str, language: str, locks: list[Any], definitions: list[Any]) -> bytes:
    document = {"source": source, "language": language, "macro_locks": locks}
    return _canonical({"document": document, "definitions": _distinct(definitions)}).encode("utf-8")


class _Core:
    """The core's answers, one call per distinct unit, from several threads.

    The binding releases the GIL while the core works, so threads run calls in
    parallel. Each kind of unit keeps its call count, the time the calls took
    one by one, and the wall-clock time of its batch.
    """

    def __init__(self, migrate: MigrateUnit, workers: int, progress: Progress | None) -> None:
        self.migrate = migrate
        self.workers = max(1, workers)
        self.progress = progress
        self.answers: dict[bytes, dict[str, Any]] = {}
        self.calls: Counter[str] = Counter()
        self.seconds: Counter[str] = Counter()
        self.wall: Counter[str] = Counter()
        self.slowest: list[tuple[float, str, int]] = []

    def ask(self, kind: str, units: Iterable[bytes]) -> None:
        pending = [unit for unit in dict.fromkeys(units) if unit not in self.answers]

        def one(unit: bytes) -> tuple[bytes, bytes, float]:
            started = time.monotonic()
            output = self.migrate(unit)
            return unit, output, time.monotonic() - started

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for done, (unit, output, seconds) in enumerate(pool.map(one, pending), 1):
                try:
                    answer = json.loads(output.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    answer = None
                self.answers[unit] = answer if isinstance(answer, dict) else {"error": {"code": "unreadable_answer"}}
                self.calls[kind] += 1
                self.seconds[kind] += seconds
                self.slowest = sorted([*self.slowest, (seconds, kind, len(unit))], reverse=True)[:10]
                if self.progress and (done % 200 == 0 or done == len(pending)):
                    self.progress(f"{kind} {done}/{len(pending)} {round(time.monotonic() - started)}s")
        self.wall[kind] += time.monotonic() - started

    def report(self) -> dict[str, object]:
        return {
            "workers": self.workers,
            "calls": dict(self.calls),
            "ms_per_call": {kind: round(self.seconds[kind] * 1000 / calls, 1)
                            for kind, calls in self.calls.items() if calls},
            "call_seconds": {kind: round(seconds, 1) for kind, seconds in self.seconds.items()},
            "wall_seconds": {kind: round(seconds, 1) for kind, seconds in self.wall.items()},
            "slowest_calls": [{"ms": round(seconds * 1000), "kind": kind, "bytes": size}
                              for seconds, kind, size in self.slowest],
        }


@dataclass
class Plan:
    """The statements that write the migration over the saved records, and its report."""

    statements: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Link:
    owner_id: str
    history_id: str
    context: dict[str, Any]
    definitions: list[Any]
    catalog_locks: list[Any]


def plan(connection: Any, migrate: MigrateUnit, *, workers: int = 1, sample: int | None = None,
         history_ids: Iterable[str] | None = None, progress: Progress | None = None) -> Plan:
    """Ask the core about every saved record; return what writing its answers would do.

    Reads only. ``sample`` counts that many variations and works drawn at
    random; ``history_ids`` only those works. A plan drawn either way is for
    counting, never for writing.
    """
    core = _Core(migrate, workers, progress)
    result = Plan()
    counts: dict[str, Counter[str]] = {kind: Counter() for kind in (
        "definitions", "history_links", "executions", "variation_documents", "history")}
    edits: Counter[str] = Counter()
    refused_records: list[dict[str, object]] = []
    sweep_records: list[dict[str, object]] = []

    # The frozen catalogs of the performances, and the definitions each variation saved.
    links: dict[str, _Link] = {}
    saved_by_variation: dict[tuple[str, str], list[Any]] = {}
    for owner_id, history_id, variation_id, context_bytes, context_digest in _rows(
        connection, "SELECT owner_id, history_id, variation_id, fork_context_bytes, fork_context_digest"
                    " FROM pipeline_history_links"
    ):
        counts["history_links"]["rows"] += 1
        encoded = bytes(context_bytes)
        context = _json(encoded)
        if hashlib.sha256(encoded).hexdigest() != context_digest or not isinstance(context, dict):
            counts["history_links"]["unreadable"] += 1
            refused_records.append({"kind": "history_links", "id": f"{owner_id}/{history_id}",
                                    "error": {"code": "unreadable_context"}})
            continue
        definitions = _definitions_of(context.get("config"))
        catalog = context.get("macro_catalog")
        locks = catalog.get("definition_locks") if isinstance(catalog, Mapping) else None
        links[history_id] = _Link(owner_id, history_id, context, definitions,
                                  locks if isinstance(locks, list) else [])
        saved_by_variation.setdefault((owner_id, variation_id), []).extend(definitions)
    for owner_id, variation_id, state_bytes in _rows(
        connection, f"SELECT owner_id, variation_id, state_bytes FROM {DISCARDED_TABLE}"
    ):
        counts["executions"]["rows"] += 1
        wrapper = _json(state_bytes)
        snapshot = wrapper.get("snapshot") if isinstance(wrapper, Mapping) else None
        if isinstance(snapshot, Mapping):
            saved_by_variation.setdefault((owner_id, variation_id), []).extend(
                _definitions_of(snapshot.get("config")))
    for key, definitions in saved_by_variation.items():
        saved_by_variation[key] = _distinct(definitions)

    # Every distinct definition once; a document's unit carries the ones its locks name.
    distinct_definitions = _distinct(
        definition for definitions in saved_by_variation.values() for definition in definitions)
    core.ask("definitions", (_definition_unit(definition) for definition in distinct_definitions))

    def definition_answer(definition: Any) -> dict[str, Any]:
        answer = core.answers[_definition_unit(definition)]
        answers = answer.get("definitions")
        if isinstance(answers, list) and answers and isinstance(answers[0], dict):
            return answers[0]
        return {"error": answer.get("error") or {"code": "unknown"}}

    for definition in distinct_definitions:
        answer = definition_answer(definition)
        if "error" in answer:
            counts["definitions"][f"refused:{(answer['error'] or {}).get('code')}"] += 1
        else:
            counts["definitions"]["changed" if answer.get("changed") else "unchanged"] += 1

    def locked(definitions: list[Any], locks: list[Any]) -> list[Any]:
        names = {(lock.get("qualified_name"), lock.get("version")) for lock in locks if isinstance(lock, Mapping)}
        chosen = []
        for definition in definitions:
            answer = definition_answer(definition)
            if (answer.get("qualified_name"), answer.get("version")) in names:
                chosen.append(definition)
        return chosen

    # The documents: each work's instructions, and each variation's committed document.
    variation_rows: list[tuple[Any, ...]] = []
    history_rows: list[tuple[Any, ...]] = []
    only = set(history_ids) if history_ids is not None else None
    limit = f" ORDER BY random() LIMIT {int(sample)}" if sample else ""
    if only is None:
        variation_rows = list(_rows(
            connection, "SELECT owner_id, variation_id, revision, document_json, ddl_digest"
                        " FROM variation_authority" + limit))
    for row in _rows(connection, "SELECT id, ddl, expanded_ddl, instruction_lang_resolved FROM history" + limit):
        if only is None or row[0] in only:
            history_rows.append(row)

    variation_units: dict[tuple[str, str], bytes] = {}
    for owner_id, variation_id, _revision, document_json, _digest in variation_rows:
        document = _json(document_json)
        if not isinstance(document, Mapping) or "saijiki" in document:
            continue
        locks = document_locks(document.get("macro_locks"))
        definitions = locked(saved_by_variation.get((owner_id, variation_id), []), locks)
        variation_units[(owner_id, variation_id)] = _document_unit(
            str(document.get("source")), str(document.get("language")), locks, definitions)
    core.ask("variation_documents", variation_units.values())

    history_units: dict[tuple[str, str], bytes] = {}
    for history_id, ddl, expanded_ddl, language in history_rows:
        link = links.get(history_id)
        locks = document_locks(link.catalog_locks) if link else []
        definitions = locked(link.definitions, locks) if link else []
        for column, source in (("ddl", ddl), ("expanded_ddl", expanded_ddl)):
            if source:
                history_units[(history_id, column)] = _document_unit(
                    source, language if language in {"ja", "en"} else "ja", locks, definitions)
    core.ask("history", history_units.values())

    def document_answer(kind: str, record_id: str, unit: bytes, source: str,
                        locks: int) -> dict[str, Any] | None:
        """The migrated document, or None after listing the refusal."""
        answer = core.answers[unit]
        migrated = answer if "error" in answer else answer.get("document")
        if not isinstance(migrated, Mapping) or "error" in migrated or not isinstance(
                migrated.get("document"), Mapping):
            error = migrated.get("error") if isinstance(migrated, Mapping) else None
            counts[kind]["refused"] += 1
            refused_records.append({"kind": kind, "id": record_id, "error": error or {"code": "unknown"},
                                    "source": source, "locks": locks})
            return None
        for edit in migrated.get("edits") or []:
            edits[f"{edit.get('original')} -> {edit.get('replacement')}"] += 1
        sweeps = migrated.get("unassociated_sweeps") or []
        if sweeps:
            counts[kind]["with_unassociated_sweeps"] += 1
            sweep_records.append({"kind": kind, "id": record_id, "unassociated_sweeps": sweeps})
        counts[kind]["changed" if migrated.get("edits") else "unchanged"] += 1
        return dict(migrated)

    for owner_id, variation_id, revision, document_json, ddl_digest in variation_rows:
        tally = counts["variation_documents"]
        tally["rows"] += 1
        document = _json(document_json)
        if not isinstance(document, Mapping):
            tally["unreadable"] += 1
            refused_records.append({"kind": "variation_documents", "id": f"{owner_id}/{variation_id}",
                                    "error": {"code": "unreadable_document"}})
            continue
        if "saijiki" in document:
            tally["current"] += 1
            continue
        tally["v1"] += 1
        unit = variation_units[(owner_id, variation_id)]
        migrated = document_answer("variation_documents", f"{owner_id}/{variation_id}", unit,
                                   str(document.get("source")), len(document.get("macro_locks") or []))
        if migrated is None:
            continue
        new_document = migrated["document"]
        new_source = str(new_document.get("source"))
        new_digest = _sha256(new_source)
        result.statements.append((
            "UPDATE variation_authority SET source=?, document_json=?, ddl_digest=?"
            " WHERE owner_id=? AND variation_id=?",
            (new_source, _canonical(new_document), new_digest, owner_id, variation_id)))
        tally["written"] += 1
        if new_digest != ddl_digest:
            result.statements.append((
                "UPDATE variation_authority_actions SET ddl_digest=?"
                " WHERE owner_id=? AND variation_id=? AND revision=? AND ddl_digest=?",
                (new_digest, owner_id, variation_id, revision, ddl_digest)))

    for history_id, ddl, expanded_ddl, _language in history_rows:
        tally = counts["history"]
        tally["rows"] += 1
        link = links.get(history_id)
        if link:
            tally["linked"] += 1
        locks = len(link.catalog_locks) if link else 0
        migrated_texts: dict[str, str] = {}
        refused = False
        for column, source in (("ddl", ddl), ("expanded_ddl", expanded_ddl)):
            if not source:
                continue
            tally[f"{column}_present"] += 1
            answer = document_answer("history", f"{history_id}:{column}",
                                     history_units[(history_id, column)], source, locks)
            if answer is None:
                refused = True
            elif answer["document"].get("source") != source:
                migrated_texts[column] = str(answer["document"].get("source"))

        link_definitions: list[Any] = []
        if link and not refused:
            for definition in link.definitions:
                answer = definition_answer(definition)
                if "error" in answer:
                    refused = True
                    counts["history_links"]["refused"] += 1
                    refused_records.append({"kind": "history_links", "id": f"{link.owner_id}/{history_id}",
                                            "error": answer["error"]})
                    break
                link_definitions.append(answer.get("definition"))
        if refused:
            # A work is one unit with its link: the link's digest binds it to the instructions.
            tally["rows_left"] += 1
            continue

        if migrated_texts:
            result.statements.append((
                "UPDATE history SET ddl=?, expanded_ddl=? WHERE id=?",
                (migrated_texts.get("ddl", ddl), migrated_texts.get("expanded_ddl", expanded_ddl), history_id)))
            tally["rows_written"] += 1
        if link:
            statement = _link_statement(link, link_definitions, migrated_texts.get("ddl", ddl), definition_answer)
            if statement:
                result.statements.append(statement)
                counts["history_links"]["written"] += 1

    # A link whose work is gone still moves its definitions and locks.
    if only is None and not sample:
        present = {row[0] for row in history_rows}
        for history_id, link in links.items():
            if history_id in present:
                continue
            counts["history_links"]["without_history"] += 1
            answers = [definition_answer(definition) for definition in link.definitions]
            failed = next((answer for answer in answers if "error" in answer), None)
            if failed:
                counts["history_links"]["refused"] += 1
                refused_records.append({"kind": "history_links", "id": f"{link.owner_id}/{history_id}",
                                        "error": failed["error"]})
                continue
            statement = _link_statement(link, [answer.get("definition") for answer in answers], None,
                                        definition_answer)
            if statement:
                result.statements.append(statement)
                counts["history_links"]["written"] += 1

    counts["executions"]["discarded"] = counts["executions"]["rows"]
    result.statements.append((f"DELETE FROM {DISCARDED_TABLE}", ()))

    result.report = {
        "sample": sample,
        "core": core.report(),
        **{kind: dict(sorted(tally.items())) for kind, tally in counts.items()},
        "edits": dict(edits.most_common()),
        "refused_records": refused_records,
        "unassociated_sweep_records": sweep_records,
    }
    return result


def _link_statement(link: _Link, definitions: list[Any], ddl: str | None,
                    definition_answer: Callable[[Any], dict[str, Any]]) -> tuple[str, tuple[Any, ...]] | None:
    """Rewrite one frozen fork context: its definitions, its locks, and the work's digest."""
    moved = {}
    for definition in link.definitions:
        answer = definition_answer(definition)
        moved[(answer.get("qualified_name"), answer.get("version"))] = str(answer.get("digest", ""))
    locks = []
    for lock in link.catalog_locks:
        digest = moved.get((lock.get("qualified_name"), lock.get("version"))) if isinstance(lock, Mapping) else None
        # The catalog keeps bare hex; sha256: is the document's form.
        locks.append({**lock, "digest": digest.removeprefix("sha256:")} if digest else lock)
    context = dict(link.context)
    config = dict(context.get("config") or {})
    if definitions or "definitions" in config:
        config["definitions"] = definitions
    context["config"] = config
    context["macro_catalog"] = {**(context.get("macro_catalog") or {}), "definition_locks": locks}
    if ddl is not None:
        context["ddl_digest"] = _sha256(ddl)
    if context == link.context:
        return None
    encoded = _canonical(context).encode("utf-8")
    return (
        "UPDATE pipeline_history_links SET ddl_digest=?, fork_context_bytes=?, fork_context_digest=?"
        " WHERE owner_id=? AND history_id=?",
        (context["ddl_digest"], encoded, hashlib.sha256(encoded).hexdigest(), link.owner_id, link.history_id),
    )


def census(connection: Any, migrate: MigrateUnit, **options: Any) -> dict[str, Any]:
    """Report what the migration would do to the saved records; write nothing."""
    return plan(connection, migrate, **options).report


def migrate_saved_records(connection: Any, migrate: MigrateUnit, *, workers: int = 1,
                          progress: Progress | None = None) -> dict[str, Any]:
    """Write the migration over every saved record, once, inside the caller's transaction."""
    migration = plan(connection, migrate, workers=workers, progress=progress)
    started = time.monotonic()
    for sql, args in migration.statements:
        _execute(connection, sql, args)
    migration.report["write_seconds"] = round(time.monotonic() - started, 1)
    migration.report["statements"] = len(migration.statements)
    return migration.report
