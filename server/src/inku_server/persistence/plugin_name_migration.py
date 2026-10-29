"""Manual one-time migration of saved plugin spellings to braced v2 names.

The core changes only DDL text. Saved definitions and locks keep their exact
bytes and meaning. The default CLI path calls ``census`` on a read-only DB;
``migrate_once`` is an explicit, stopped-service operation with a verified
snapshot and one SQLite writer transaction.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .saijiki_migration import _Core, _canonical, _execute, _json, _rows, document_locks

DONE_SETTING = "plugin_names_v2_saved_records"
MigrateUnit = Callable[[bytes], bytes]


class MigrationAlreadyWritten(RuntimeError):
    """The one-time migration was committed earlier."""


def _digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _definitions(context: Mapping[str, Any]) -> list[Any]:
    config = context.get("config")
    definitions = config.get("definitions") if isinstance(config, Mapping) else None
    return definitions if isinstance(definitions, list) else []


def _locks(context: Mapping[str, Any]) -> list[Any]:
    catalog = context.get("macro_catalog")
    locks = catalog.get("definition_locks") if isinstance(catalog, Mapping) else None
    return locks if isinstance(locks, list) else []


def _unit(source: str, language: str, locks: list[Any], definitions: list[Any]) -> bytes:
    return _canonical({"document": {"source": source, "language": language,
                                     "macro_locks": document_locks(locks)},
                       "definitions": definitions}).encode("utf-8")


@dataclass
class Plan:
    statements: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


def plan(connection: Any, migrate: MigrateUnit, *, workers: int = 1,
         timeout: float = 120.0, journal: Path | None = None) -> Plan:
    """Read all saved units and ask the core; no SQL statement is executed."""
    counts: Counter[str] = Counter()
    refused: list[dict[str, Any]] = []
    links: dict[str, tuple[str, str, dict[str, Any]]] = {}
    variation_definitions: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for owner, history_id, variation_id, context_bytes, context_digest in _rows(
        connection, "SELECT owner_id,history_id,variation_id,fork_context_bytes,fork_context_digest "
                    "FROM pipeline_history_links"):
        counts["links"] += 1
        encoded = bytes(context_bytes)
        context = _json(encoded)
        if hashlib.sha256(encoded).hexdigest() != context_digest or not isinstance(context, dict):
            refused.append({"kind": "link", "id": history_id, "code": "unreadable_context"})
            continue
        links[history_id] = (owner, variation_id, context)
        variation_definitions[(owner, variation_id)].extend(_definitions(context))

    histories = list(_rows(connection, "SELECT id,ddl,instruction_lang_resolved FROM history"))
    variations = list(_rows(connection, "SELECT owner_id,variation_id,revision,source,document_json,ddl_digest "
                                         "FROM variation_authority"))
    units: dict[bytes, str] = {}
    history_units: dict[str, bytes] = {}
    variation_units: dict[tuple[str, str], bytes] = {}
    for history_id, source, language in histories:
        counts["history_rows"] += 1
        if not source:
            continue
        link = links.get(history_id)
        context = link[2] if link else {}
        unit = _unit(source, language if language in {"ja", "en"} else "ja",
                     _locks(context), _definitions(context))
        history_units[history_id] = unit
        units.setdefault(unit, f"history:{history_id}")
    for owner, variation_id, _revision, source, document_json, ddl_digest in variations:
        counts["variation_rows"] += 1
        document = _json(document_json)
        if not isinstance(document, dict) or document.get("source") != source or _digest(source) != ddl_digest:
            refused.append({"kind": "variation", "id": f"{owner}/{variation_id}",
                            "code": "unreadable_document"})
            continue
        definitions = list({_canonical(item): item for item in variation_definitions[(owner, variation_id)]}.values())
        unit = _unit(source, document.get("language") if document.get("language") in {"ja", "en"} else "ja",
                     document.get("macro_locks") if isinstance(document.get("macro_locks"), list) else [],
                     definitions)
        variation_units[(owner, variation_id)] = unit
        units.setdefault(unit, f"variation:{owner}/{variation_id}")

    core = _Core(migrate, workers, None, journal, timeout, abort_on_failure=True)
    try:
        core.ask("plugin_names", units)
        answers = core.answers
        core_report = core.report()
    finally:
        core.close()

    result = Plan()

    def changed(unit: bytes, label: str, old: str) -> str | None:
        answer = answers[unit]
        document = answer.get("document")
        if answer.get("schema") != "inku.plugin-name-migration.v1" or not isinstance(document, dict):
            refused.append({"kind": label.split(":", 1)[0], "id": label, "code": answer.get("error", "core_refused")})
            return None
        new = document.get("source")
        if not isinstance(new, str) or document.get("macro_locks") != _json(unit)["document"]["macro_locks"]:
            refused.append({"kind": label.split(":", 1)[0], "id": label, "code": "invalid_core_answer"})
            return None
        if answer.get("problems"):
            refused.append({"kind": label.split(":", 1)[0], "id": label, "code": "partial",
                            "problems": answer["problems"]})
        counts["unchanged" if new == old else "changed"] += 1
        return new

    for history_id, source, _language in histories:
        unit = history_units.get(history_id)
        if unit is None:
            continue
        new = changed(unit, f"history:{history_id}", source)
        if new is None or new == source:
            continue
        result.statements.append(("UPDATE history SET ddl=? WHERE id=? AND ddl=?", (new, history_id, source)))
        if history_id in links:
            owner, _variation, context = links[history_id]
            new_context = dict(context)
            new_context["ddl_digest"] = _digest(new)
            encoded = _canonical(new_context).encode("utf-8")
            result.statements.append((
                "UPDATE pipeline_history_links SET ddl_digest=?,fork_context_bytes=?,fork_context_digest=? "
                "WHERE owner_id=? AND history_id=? AND ddl_digest=?",
                (_digest(new), encoded, hashlib.sha256(encoded).hexdigest(), owner, history_id, _digest(source))))

    for owner, variation_id, revision, source, document_json, old_digest in variations:
        unit = variation_units.get((owner, variation_id))
        if unit is None:
            continue
        new = changed(unit, f"variation:{owner}/{variation_id}", source)
        if new is None or new == source:
            continue
        document = _json(document_json)
        document["source"] = new
        new_digest = _digest(new)
        result.statements.append((
            "UPDATE variation_authority SET source=?,document_json=?,ddl_digest=? "
            "WHERE owner_id=? AND variation_id=? AND ddl_digest=?",
            (new, _canonical(document), new_digest, owner, variation_id, old_digest)))
        result.statements.append((
            "UPDATE variation_authority_actions SET ddl_digest=? "
            "WHERE owner_id=? AND variation_id=? AND revision=? AND ddl_digest=?",
            (new_digest, owner, variation_id, revision, old_digest)))

    result.report = {"counts": dict(counts), "refused_records": refused,
                     "core": core_report, "statements": len(result.statements)}
    return result


def census(database: Path, migrate: MigrateUnit, **options: Any) -> dict[str, Any]:
    """Count an existing database without allowing writes to it."""
    import sqlite3
    from urllib.parse import quote

    database = database.expanduser().resolve(strict=True)
    uri = "file:" + quote(str(database), safe="/") + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        return plan(connection, migrate, **options).report


def migrate_once(database: Path, migrate: MigrateUnit, **options: Any) -> dict[str, Any]:
    """Snapshot, then change all related rows under one writer lock or roll back."""
    from sqlalchemy import create_engine
    from .backup import create_sqlite_snapshot
    from .invariants import capture_invariants, require_integrity, verify_invariants

    database = database.expanduser().resolve(strict=True)
    engine = create_engine(f"sqlite:///{database}", future=True)
    try:
        with engine.connect() as connection:
            if list(_rows(connection, "SELECT 1 FROM app_settings WHERE key=?", (DONE_SETTING,))):
                raise MigrationAlreadyWritten(str(database))
        snapshot = create_sqlite_snapshot(
            database, database.parent / "migration-backups" /
            f"{database.stem}-pre-plugin-names-v2-{time.time_ns()}.db")
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                if list(_rows(connection, "SELECT 1 FROM app_settings WHERE key=?", (DONE_SETTING,))):
                    raise MigrationAlreadyWritten(str(database))
                before = capture_invariants(connection)
                migration = plan(connection, migrate, **options)
                for sql, args in migration.statements:
                    _execute(connection, sql, args)
                verify_invariants(connection, before)
                for history_id, ddl, digest in _rows(
                    connection, "SELECT h.id,h.ddl,l.ddl_digest FROM history h "
                                "JOIN pipeline_history_links l ON l.history_id=h.id"):
                    if ddl is not None and _digest(ddl) != digest:
                        raise ValueError(f"link digest mismatch: {history_id}")
                _execute(connection, "INSERT INTO app_settings(key,value,at) VALUES (?,?,?)",
                         (DONE_SETTING, _canonical({"statements": len(migration.statements)}),
                          int(time.time() * 1000)))
                require_integrity(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    finally:
        engine.dispose()
    return {**migration.report, "snapshot": str(snapshot.path)}
