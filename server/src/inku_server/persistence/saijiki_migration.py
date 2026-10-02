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
``migrate_once`` writes the same plan once, while the service is stopped, by
hand and not at startup (the author, 2026-09-30; SPEC §3.3 and the plan the
author and the draw session agreed on the same day):

- the committed document of each variation (``variation_authority``): its
  source, its document with the edition and the moved locks, and its digest;
  the acknowledgment of its current revision follows the new digest, so the
  next performance of it can still be linked;
- the definitions and locks frozen with each performance
  (``pipeline_history_links.fork_context_bytes``: ``config.definitions`` and
  ``macro_catalog.definition_locks``), with the digests that bind them to the
  work's instructions;
- the instructions of each saved work (``history.ddl`` and, only in old
  schemas, ``history.expanded_ddl``); its description, Score and SVG are never touched;
- the execution snapshots (``pipeline_candidate_executions``) are discarded,
  not migrated (the author, 2026-09-30).

A record the core refuses is left as it was and listed; it need not be perfect
(the author, 2026-09-30): v2 refuses an unmigrated record with
``saijiki_migration_required`` and nothing else breaks.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import time
from collections import Counter, deque
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from multiprocessing.connection import wait as wait_for
from pathlib import Path
from typing import Any

MigrateUnit = Callable[[bytes], bytes]
Progress = Callable[[str], None]

# The table whose rows the migration discards instead of moving.
DISCARDED_TABLE = "pipeline_candidate_executions"
# The app setting that records the migration was written; a second run refuses.
DONE_SETTING = "saijiki_v2_saved_records"


class MigrationAlreadyWritten(RuntimeError):
    """The saved records were already moved to Saijiki v2; v1 would misread them."""


class CoreCallFailed(RuntimeError):
    """A call to the core was killed past its time, or its process died; the run stops."""


class BlankListInvalid(ValueError):
    """A record named to be emptied is missing, already empty, or bound to its link by its digest."""


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


def _serve(migrate: MigrateUnit, connection: Any) -> None:
    """A worker process: answer units until an empty one says stop."""
    while unit := connection.recv_bytes():
        started = time.monotonic()
        output = migrate(unit)
        connection.send((output, time.monotonic() - started))
    os._exit(0)


class _Worker:
    """One worker process and the unit it is on."""

    def __init__(self, migrate: MigrateUnit) -> None:
        # fork: the child inherits the migrate function without pickling it.
        context = multiprocessing.get_context("fork")
        self.connection, child = context.Pipe()
        self.process = context.Process(target=_serve, args=(migrate, child), daemon=True)
        self.process.start()
        child.close()
        self.job: tuple[bytes, str, str, float] | None = None

    def give(self, unit: bytes, label: str, key: str) -> None:
        self.job = (unit, label, key, time.monotonic())
        self.connection.send_bytes(unit)

    def kill(self) -> None:
        self.process.kill()
        self.process.join()
        self.connection.close()

    def stop(self) -> None:
        try:
            self.connection.send_bytes(b"")
        except OSError:
            pass
        self.process.join(5)
        if self.process.is_alive():
            self.process.kill()
            self.process.join()
        self.connection.close()


class _Core:
    """The core's answers, one call per distinct unit, from several worker processes.

    Each call runs in a worker process, so a call that runs longer than
    ``timeout`` seconds is killed with its process, answered ``timeout``, and
    a new process takes the next unit: the run goes on to the last record.
    Each kind of unit keeps its call count, the time the calls took one by one,
    and the wall-clock time of its batch.

    With a journal, each call is written down as it starts, with the record it
    was asked for, and again as it ends -- with its answer and how long it
    took, or with how long it ran before it was killed.

    With ``abort_on_failure`` (the production run, the author 2026-09-30), a
    call that is killed or whose process dies raises ``CoreCallFailed`` instead,
    and the whole migration stops there.
    """

    def __init__(self, migrate: MigrateUnit, workers: int, progress: Progress | None,
                 journal: Path | None = None, timeout: float | None = None,
                 abort_on_failure: bool = False) -> None:
        self.migrate = migrate
        self.workers = max(1, workers)
        self.progress = progress
        self.timeout = timeout
        self.abort_on_failure = abort_on_failure
        self.answers: dict[bytes, dict[str, Any]] = {}
        self.calls: Counter[str] = Counter()
        self.seconds: Counter[str] = Counter()
        self.wall: Counter[str] = Counter()
        self.slowest: list[tuple[float, str, str]] = []
        self.killed: list[dict[str, object]] = []
        self._journal = journal.open("a", encoding="utf-8", buffering=1) if journal is not None else None

    def _write(self, entry: dict[str, object]) -> None:
        if self._journal is not None:
            self._journal.write(_canonical(entry) + "\n")

    def close(self) -> None:
        if self._journal is not None:
            self._journal.close()
            self._journal = None

    def _answered(self, kind: str, unit: bytes, label: str, key: str, answer: dict[str, Any],
                  seconds: float, event: str) -> None:
        self.answers[unit] = answer
        self._write({"event": event, "kind": kind, "unit": key, "record": label,
                     "ms": round(seconds * 1000), "answer": answer})
        self.calls[kind] += 1
        self.seconds[kind] += seconds
        self.slowest = sorted([*self.slowest, (seconds, kind, label)], reverse=True)[:10]

    def ask(self, kind: str, units: Mapping[bytes, str]) -> None:
        """Answer each unit; ``units`` maps a unit to the record it was asked for."""
        queue = deque((unit, label, hashlib.sha256(unit).hexdigest())
                      for unit, label in units.items() if unit not in self.answers)
        total = len(queue)
        started = time.monotonic()
        workers = [_Worker(self.migrate) for _ in range(min(self.workers, total))]
        done = 0
        try:
            while queue or any(worker.job for worker in workers):
                for worker in workers:
                    if worker.job is None and queue:
                        unit, label, key = queue.popleft()
                        self._write({"event": "start", "kind": kind, "unit": key, "record": label})
                        worker.give(unit, label, key)
                busy = {worker.connection: worker for worker in workers if worker.job}
                for connection in wait_for(list(busy), timeout=1.0):
                    worker = busy[connection]
                    unit, label, key, began = worker.job
                    try:
                        output, seconds = connection.recv()
                        try:
                            answer = json.loads(output.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            answer = None
                        if not isinstance(answer, dict):
                            answer = {"error": {"code": "unreadable_answer"}}
                        self._answered(kind, unit, label, key, answer, seconds, "done")
                        worker.job = None
                    except EOFError:
                        # The process ended without answering (the core aborted it).
                        self._answered(kind, unit, label, key, {"error": {"code": "worker_died"}},
                                       time.monotonic() - began, "died")
                        worker.kill()
                        workers[workers.index(worker)] = _Worker(self.migrate)
                        if self.abort_on_failure:
                            raise CoreCallFailed(f"{kind} {label}: the core's process ended without answering")
                    done += 1
                    if self.progress and (done % 200 == 0 or done == total):
                        self.progress(f"{kind} {done}/{total} {round(time.monotonic() - started)}s")
                if self.timeout is None:
                    continue
                now = time.monotonic()
                for index, worker in enumerate(workers):
                    if worker.job and now - worker.job[3] > self.timeout:
                        unit, label, key, began = worker.job
                        worker.kill()
                        workers[index] = _Worker(self.migrate)
                        self._answered(kind, unit, label, key,
                                       {"error": {"code": "timeout", "seconds": self.timeout}},
                                       now - began, "killed")
                        self.killed.append({"kind": kind, "record": label, "ms": round((now - began) * 1000)})
                        if self.abort_on_failure:
                            raise CoreCallFailed(f"{kind} {label}: no answer within {self.timeout} seconds")
                        done += 1
                        if self.progress:
                            self.progress(f"{kind} killed {label} after {round(now - began)}s")
        finally:
            for worker in workers:
                if worker.job:
                    worker.kill()
                else:
                    worker.stop()
        self.wall[kind] += time.monotonic() - started

    def report(self) -> dict[str, object]:
        return {
            "workers": self.workers,
            "timeout_seconds": self.timeout,
            "killed": self.killed,
            "calls": dict(self.calls),
            "ms_per_call": {kind: round(self.seconds[kind] * 1000 / calls, 1)
                            for kind, calls in self.calls.items() if calls},
            "call_seconds": {kind: round(seconds, 1) for kind, seconds in self.seconds.items()},
            "wall_seconds": {kind: round(seconds, 1) for kind, seconds in self.wall.items()},
            "slowest_calls": [{"ms": round(seconds * 1000), "kind": kind, "record": label}
                              for seconds, kind, label in self.slowest],
        }


@dataclass
class Plan:
    """The statements that write the migration over the saved records, and its report.

    ``discards`` remove rows on purpose; they run after the updates have been
    checked against the invariants, which require every existing key to survive.
    """

    statements: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    discards: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Link:
    owner_id: str
    history_id: str
    context: dict[str, Any]
    definitions: list[Any]
    catalog_locks: list[Any]


def plan(connection: Any, migrate: MigrateUnit, *, workers: int = 1, sample: int | None = None,
         history_ids: Iterable[str] | None = None, progress: Progress | None = None,
         journal: Path | None = None, timeout: float | None = None,
         abort_on_failure: bool = False, blank: Iterable[str] | None = None) -> Plan:
    """Ask the core about every saved record; return what writing its answers would do.

    Reads only. ``sample`` counts that many variations and works drawn at
    random; ``history_ids`` only those works. A plan drawn either way is for
    counting, never for writing. ``journal`` keeps each answer as it comes;
    a call longer than ``timeout`` seconds is killed and its record listed.

    ``blank`` names instruction texts (``<history id>:<column>``) that are not
    migrated but emptied: the core never sees them, and the column becomes
    NULL, the state of a work saved before its DDL was kept, which the Server
    and the Web already read as "no DDL" (the author and the draw session,
    2026-10-01: texts that were not DDL at all, and that the core could not
    read in time). The list is given explicitly; no rule by length or shape
    picks it. The work's description, Score and SVG stay.
    """
    core = _Core(migrate, workers, progress, journal, timeout, abort_on_failure)
    try:
        return _plan(connection, core, sample=sample, history_ids=history_ids, blank=set(blank or ()))
    finally:
        core.close()


def _plan(connection: Any, core: _Core, *, sample: int | None, history_ids: Iterable[str] | None,
          blank: set[str]) -> Plan:
    result = Plan()
    counts: dict[str, Counter[str]] = {kind: Counter() for kind in (
        "definitions", "history_links", "executions", "variation_documents", "history")}
    edits: Counter[str] = Counter()
    refused_records: list[dict[str, object]] = []
    sweep_records: list[dict[str, object]] = []
    blanked_records: list[dict[str, object]] = []

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
    labels: dict[bytes, str] = {}
    for definition in distinct_definitions:
        name = (f"{definition.get('namespace')}.{definition.get('heading')}@{definition.get('version')}"
                if isinstance(definition, Mapping) else "definition")
        labels.setdefault(_definition_unit(definition), name)
    core.ask("definitions", labels)

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
    history_columns = {row[1] for row in _rows(connection, "PRAGMA table_info(history)")}
    has_expanded_ddl = "expanded_ddl" in history_columns
    expanded_projection = "expanded_ddl" if has_expanded_ddl else "NULL"
    for row in _rows(connection, "SELECT id, ddl, " + expanded_projection +
                     ", instruction_lang_resolved FROM history" + limit):
        if only is None or row[0] in only:
            history_rows.append(row)

    # Every text named to be emptied must be there, hold text, and not be the
    # instructions a performance's link binds by digest.
    by_id = {row[0]: row for row in history_rows}
    for record_id in sorted(blank):
        history_id, _, column = record_id.partition(":")
        if column not in {"ddl", "expanded_ddl"}:
            raise BlankListInvalid(f"{record_id}: not a history text")
        if column == "expanded_ddl" and not has_expanded_ddl:
            raise BlankListInvalid(f"{record_id}: not a history text in this schema")
        row = by_id.get(history_id)
        if row is None:
            if only is None and not sample:
                raise BlankListInvalid(f"{record_id}: no such work")
            continue
        if not (row[1] if column == "ddl" else row[2]):
            raise BlankListInvalid(f"{record_id}: already empty")
        if column == "ddl" and history_id in links:
            raise BlankListInvalid(f"{record_id}: bound to its performance link by its digest")

    variation_units: dict[tuple[str, str], bytes] = {}
    for owner_id, variation_id, _revision, document_json, _digest in variation_rows:
        document = _json(document_json)
        if not isinstance(document, Mapping) or "saijiki" in document:
            continue
        locks = document_locks(document.get("macro_locks"))
        definitions = locked(saved_by_variation.get((owner_id, variation_id), []), locks)
        variation_units[(owner_id, variation_id)] = _document_unit(
            str(document.get("source")), str(document.get("language")), locks, definitions)
    labels = {}
    for (owner_id, variation_id), unit in variation_units.items():
        labels.setdefault(unit, f"{owner_id}/{variation_id}")
    core.ask("variation_documents", labels)

    history_units: dict[tuple[str, str], bytes] = {}
    for history_id, ddl, expanded_ddl, language in history_rows:
        link = links.get(history_id)
        locks = document_locks(link.catalog_locks) if link else []
        definitions = locked(link.definitions, locks) if link else []
        for column, source in (("ddl", ddl), ("expanded_ddl", expanded_ddl)):
            if source and f"{history_id}:{column}" not in blank:
                history_units[(history_id, column)] = _document_unit(
                    source, language if language in {"ja", "en"} else "ja", locks, definitions)
    labels = {}
    for (history_id, column), unit in history_units.items():
        labels.setdefault(unit, f"{history_id}:{column}")
    core.ask("history", labels)

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
        migrated_texts: dict[str, str | None] = {}
        refused = False
        for column, source in (("ddl", ddl), ("expanded_ddl", expanded_ddl)):
            if not source:
                continue
            tally[f"{column}_present"] += 1
            if f"{history_id}:{column}" in blank:
                tally["blanked"] += 1
                blanked_records.append({"id": f"{history_id}:{column}", "chars": len(source)})
                migrated_texts[column] = None
                continue
            answer = document_answer("history", f"{history_id}:{column}",
                                     history_units[(history_id, column)], source, locks)
            if answer is None:
                refused = True
            elif answer["document"].get("source") != source:
                migrated_texts[column] = str(answer["document"].get("source"))
        new_ddl = migrated_texts.get("ddl", ddl)

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
            if has_expanded_ddl:
                result.statements.append((
                    "UPDATE history SET ddl=?, expanded_ddl=? WHERE id=?",
                    (new_ddl, migrated_texts.get("expanded_ddl", expanded_ddl), history_id)))
            else:
                result.statements.append((
                    "UPDATE history SET ddl=? WHERE id=?", (new_ddl, history_id)))
            tally["rows_written"] += 1
        if link:
            statement = _link_statement(link, link_definitions, new_ddl, definition_answer)
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
    result.discards.append((f"DELETE FROM {DISCARDED_TABLE}", ()))

    result.report = {
        "sample": sample,
        "core": core.report(),
        **{kind: dict(sorted(tally.items())) for kind, tally in counts.items()},
        "edits": dict(edits.most_common()),
        "refused_records": refused_records,
        "blanked_records": blanked_records,
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
                          progress: Progress | None = None,
                          checked: Callable[[], None] | None = None,
                          journal: Path | None = None, timeout: float | None = None,
                          abort_on_failure: bool = False, blank: Iterable[str] | None = None) -> dict[str, Any]:
    """Write the migration over every saved record inside the caller's transaction.

    ``checked`` runs after the updates and before the discards; it raises to
    stop the transaction (the caller's invariant check).
    """
    migration = plan(connection, migrate, workers=workers, progress=progress, journal=journal, timeout=timeout,
                     abort_on_failure=abort_on_failure, blank=blank)
    started = time.monotonic()
    for sql, args in migration.statements:
        _execute(connection, sql, args)
    if checked:
        checked()
    for sql, args in migration.discards:
        _execute(connection, sql, args)
    migration.report["write_seconds"] = round(time.monotonic() - started, 1)
    migration.report["statements"] = len(migration.statements)
    return migration.report


def migrate_once(database: Path, migrate: MigrateUnit, *, workers: int = 1,
                 progress: Progress | None = None, journal: Path | None = None,
                 timeout: float | None = None, abort_on_failure: bool = False,
                 blank: Iterable[str] | None = None) -> dict[str, Any]:
    """Move the saved records of one SQLite database to Saijiki v2, once.

    Run it while the service is stopped. It keeps a verified Backup API
    snapshot beside the database first (``migration-backups/``), then writes
    under a single writer lock: every key and each work's id, description,
    Score and SVG must survive, SQLite's checks must pass, and the setting
    ``DONE_SETTING`` records the run, so a second run refuses. Any failure
    rolls back and keeps the snapshot. Returns the report with its timings.
    """
    from sqlalchemy import create_engine

    from .backup import create_sqlite_snapshot
    from .invariants import capture_invariants, require_integrity, verify_invariants

    started = time.monotonic()
    database = database.expanduser().resolve(strict=True)
    engine = create_engine(f"sqlite:///{database}", future=True)
    try:
        with engine.connect() as connection:
            if _already_written(connection):
                raise MigrationAlreadyWritten(str(database))
        snapshot = create_sqlite_snapshot(
            database, database.parent / "migration-backups" / f"{database.stem}-pre-saijiki-v2-{time.time_ns()}.db")
        snapshot_seconds = time.monotonic() - started
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                if _already_written(connection):
                    raise MigrationAlreadyWritten(str(database))
                before = capture_invariants(connection)
                report = migrate_saved_records(connection, migrate, workers=workers, progress=progress,
                                               checked=lambda: verify_invariants(connection, before),
                                               journal=journal, timeout=timeout,
                                               abort_on_failure=abort_on_failure, blank=blank)
                summary = {"refused_records": len(report["refused_records"]), "statements": report["statements"]}
                _execute(connection, "INSERT INTO app_settings(key, value, at) VALUES (?, ?, ?)",
                         (DONE_SETTING, _canonical(summary), int(time.time() * 1000)))
                require_integrity(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    finally:
        engine.dispose()
    report["snapshot"] = str(snapshot.path)
    report["snapshot_seconds"] = round(snapshot_seconds, 1)
    report["total_seconds"] = round(time.monotonic() - started, 1)
    return report


def _already_written(connection: Any) -> bool:
    return bool(list(_rows(connection, "SELECT 1 FROM app_settings WHERE key=?", (DONE_SETTING,))))
