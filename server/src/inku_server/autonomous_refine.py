"""The AI refinement's runs (AI自動推敲): moves the Server takes on its own from a saved work.

The author decided (2026-10-20) that the Server drives a run, so that it goes on
while no screen is open, and that a move is a laws move (the laws stage again on
the saved work, leaving out the laws its parent used) or a juxtaposition move (a
sentence from another of the author's works added after the description). What
the apps must agree on is the shared core's (``inku-pipeline/src/autonomous_refine.rs``):
which try comes next and when a run stops (``next``), whether a child looks
different from its parent (``measure``), and the record a child keeps on its
lineage edge (``record``). This module takes the tries, draws and saves the
children through the ordinary pipeline runs, and keeps where each run stands.

A child is saved in the history as the run draws it; its record is written to
its edge once it is measured. A child that passes the gate is the next turn's
parent. Children that do not pass also remain in the history.

A chunk move (まとまりの手, 2026-10-27) runs alone, toward the run's note: the
shared core's chunk moves (``chunk_moves.rs``) choose one move for one chunk of
the parent's titled DDL, apply it and check the child; this module sends the
requests the core asks for, as the second chunk prototype sent them, and draws
the child from its DDL. The child is kept when the core's checks pass: the gate
is measured for its record, not applied (the author's answer, 2026-10-27).

Where each run stands is kept in a store of its own beside the canonical
database (``<name>-autonomous-runs.db``; ``INKU_AUTONOMOUS_RUNS_DB_URL`` names
another). It is not where a work's record is kept -- every child keeps its move
on its lineage edge -- so adding it changes nothing in the canonical schema. A
run the Server was taking when it stopped reads as interrupted when it starts.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import HTTPException
from sqlalchemy import BigInteger, Column, String, Text, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import db as _db
from .description_labels import pipeline_description
from .persistence.config import CANONICAL_DB_ENV, PERSISTENCE_CONFIG, sqlite_database_path, validate_sqlite_url
from .persistence.engine import THUMBNAIL_SQLITE_PRAGMAS, create_sqlite_engine
from .pipeline_candidate import CandidateHostError

_logger = logging.getLogger(__name__)

RUNS_DB_ENV = "INKU_AUTONOMOUS_RUNS_DB_URL"
MOVES_DEFAULT = 5
NOTE_LIMIT = 1_000
#: The laws stage's reasons for stopping after its request was sent. Any other
#: reason stops it before anything is sent, which the core counts as a move
#: that could not start (drawing session's entry, machine.rs).
LAWS_SENT_FAILURES = frozenset({"laws_refused", "laws_compile", "laws_unavailable"})
#: How long a try waits for a pipeline worker when every one is busy.
_CAPACITY_WAIT_SECONDS = 3.0


def _now() -> int:
    return int(time.time() * 1000)


def _core(request: dict[str, Any]) -> dict[str, Any]:
    native = importlib.import_module("inku_render")
    answer = json.loads(native.pipeline_autonomous_refine(json.dumps(request, ensure_ascii=False).encode("utf-8")))
    if not isinstance(answer, dict) or answer.get("error"):
        raise RuntimeError(f"autonomous refinement core: {answer!r}")
    return answer


def _chunk_core(request: dict[str, Any]) -> dict[str, Any]:
    """The shared core's chunk moves (``inku-pipeline/src/chunk_moves.rs``)."""
    native = importlib.import_module("inku_render")
    answer = json.loads(native.pipeline_chunk_moves(json.dumps(request, ensure_ascii=False).encode("utf-8")))
    if not isinstance(answer, dict) or answer.get("error"):
        raise RuntimeError(f"chunk moves core ({request.get('action')}): {answer!r}")
    return answer


#: What a chunk move's requests are sent as: the action the second chunk prototype sent them as.
CHUNK_ACTION = "generate_normalized_ddl"
#: How long one of its requests may take, as the prototype allowed.
CHUNK_TIMEOUT_MS = 300_000
#: The side of the picture a choose request shows (the prototype's PNG, laid square).
CHUNK_PICTURE_SIDE = 1024
#: The failures after which a request is sent once more, a moment later.
_CHUNK_TRANSIENT = frozenset({"rate_limited", "transport_timeout", "transport_unavailable"})
_CHUNK_RESEND_SECONDS = 2.0


def _composition_of(item: dict[str, Any]) -> dict[str, Any] | None:
    """A read-and-draw work's composition record as the core titles a DDL from it: each line's thing, and the things."""
    record = item.get("description_ddl")
    composition = record.get("composition") if isinstance(record, dict) else None
    if not isinstance(composition, dict):
        return None
    owners, things = composition.get("things"), (composition.get("answer") or {}).get("things")
    if isinstance(owners, list) and isinstance(things, list):
        return {"owners": owners, "things": things}
    return None


def _chunk_count(item: dict[str, Any]) -> int:
    """The chunks a chunk move could take on a work: its title lines, or its composition's things."""
    request = {"action": "units", "ddl": str(item.get("ddl") or ""),
               "language": item.get("instruction_lang_resolved") or "ja"}
    composition = _composition_of(item)
    if composition is not None:
        request["composition"] = composition
    answer = _chunk_core(request)
    return len(answer.get("units") or []) if answer.get("outcome") == "ok" else 0


def _diagnostic_count(item: dict[str, Any]) -> int:
    """The diagnostics a saved work's drawing carries, every kind counted."""
    found = item.get("pipeline_diagnostics") or {}
    if not isinstance(found, dict):
        return 0
    count = sum(len(found.get(name) or []) for name in (
        "upstream_diagnostics", "downstream_diagnostics", "plugin_diagnostics", "relation_omissions",
        "resource_omissions"))
    return count + len((found.get("render_diagnostics") or {}).get("diagnostics") or [])


def _marks(item: dict[str, Any]) -> int:
    found = item.get("pipeline_diagnostics") or {}
    demand = ((found.get("resource_execution") or {}).get("demand") or {}) if isinstance(found, dict) else {}
    return int(demand.get("primitive_marks") or 0)


def _picture(svg: str) -> tuple[str, dict[str, Any]]:
    """The parent's picture as a choose request shows it: the PNG's data URL, and the image as the prompt names it
    (its type, length and SHA-256; the shared core sends no image its prompt does not name)."""
    from inku_analysis.rasterizer import svg_to_png
    png = svg_to_png(svg, width=CHUNK_PICTURE_SIDE, height=CHUNK_PICTURE_SIDE)
    named = {"media_type": "image/png", "byte_len": len(png), "sha256": hashlib.sha256(png).hexdigest()}
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii"), named


# ---------------------------------------------------------------------------
# Where each run stands
# ---------------------------------------------------------------------------


def runs_db_url(canonical_url: str, environ: dict[str, str] | None = None) -> str:
    """The run store's URL: the one named, or a file beside the canonical one named after it."""
    values = os.environ if environ is None else environ
    configured = values.get(RUNS_DB_ENV)
    if configured:
        return validate_sqlite_url(configured, setting=RUNS_DB_ENV)
    path = sqlite_database_path(canonical_url, setting=CANONICAL_DB_ENV)
    if path is None:
        return "sqlite://"
    return "sqlite:///" + str(path.with_name(f"{path.stem}-autonomous-runs.db"))


class _Base(DeclarativeBase):
    pass


class AutonomousRunRow(_Base):
    __tablename__ = "autonomous_refine_runs"

    id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
    # The work the run started from.
    history_id = Column(String, nullable=False, index=True)
    # running, done, stopped, failed or interrupted.
    state = Column(String, nullable=False, index=True)
    stop_reason = Column(String, nullable=True)
    settings_json = Column(Text, nullable=False)
    # The turns as the core reads them, each try with the child it drew.
    turns_json = Column(Text, nullable=False)
    # The try being taken.
    current_json = Column(Text, nullable=True)
    last_kept_history_id = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class RunStore:
    """The runs, one row each."""

    def __init__(self, url: str):
        path = sqlite_database_path(url, setting=RUNS_DB_ENV)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_sqlite_engine(url, setting=RUNS_DB_ENV, pragmas=THUMBNAIL_SQLITE_PRAGMAS)
        _Base.metadata.create_all(self.engine)
        self._sessions = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

    @staticmethod
    def _run(row: AutonomousRunRow) -> dict[str, Any]:
        return {
            "id": row.id, "owner_id": row.owner_id, "history_id": row.history_id, "state": row.state,
            "stop_reason": row.stop_reason, "settings": json.loads(row.settings_json),
            "turns": json.loads(row.turns_json),
            "current": json.loads(row.current_json) if row.current_json else None,
            "last_kept_history_id": row.last_kept_history_id, "error": row.error,
            "created_at": row.created_at, "updated_at": row.updated_at,
        }

    def save(self, run: dict[str, Any]) -> None:
        run["updated_at"] = _now()
        with self._sessions() as session:
            row = session.get(AutonomousRunRow, run["id"])
            if row is None:
                row = AutonomousRunRow(id=run["id"], owner_id=run["owner_id"], history_id=run["history_id"],
                                       created_at=run["created_at"])
                session.add(row)
            row.state = run["state"]
            row.stop_reason = run.get("stop_reason")
            row.settings_json = json.dumps(run["settings"], ensure_ascii=False)
            row.turns_json = json.dumps(run["turns"], ensure_ascii=False)
            row.current_json = json.dumps(run["current"], ensure_ascii=False) if run.get("current") else None
            row.last_kept_history_id = run.get("last_kept_history_id")
            row.error = run.get("error")
            row.updated_at = run["updated_at"]
            session.commit()

    def get(self, owner: str, run_id: str) -> dict[str, Any] | None:
        with self._sessions() as session:
            row = session.get(AutonomousRunRow, run_id)
            return self._run(row) if row is not None and row.owner_id == owner else None

    def running(self, owner: str) -> dict[str, Any] | None:
        with self._sessions() as session:
            row = session.scalars(select(AutonomousRunRow).where(
                AutonomousRunRow.owner_id == owner, AutonomousRunRow.state == "running",
            ).order_by(AutonomousRunRow.created_at.desc())).first()
            return self._run(row) if row is not None else None

    def for_history(self, owner: str, history_id: str, limit: int = 5) -> list[dict[str, Any]]:
        with self._sessions() as session:
            rows = session.scalars(select(AutonomousRunRow).where(
                AutonomousRunRow.owner_id == owner, AutonomousRunRow.history_id == history_id,
            ).order_by(AutonomousRunRow.created_at.desc()).limit(limit)).all()
            return [self._run(row) for row in rows]

    def interrupt_running(self) -> list[dict[str, Any]]:
        """Mark the runs that were being taken when the Server stopped, and return them."""
        with self._sessions() as session:
            rows = session.scalars(select(AutonomousRunRow).where(AutonomousRunRow.state == "running")).all()
            now = _now()
            for row in rows:
                row.state, row.stop_reason, row.current_json, row.updated_at = "interrupted", "interrupted", None, now
            session.commit()
            return [self._run(row) for row in rows]


# ---------------------------------------------------------------------------
# Taking the moves
# ---------------------------------------------------------------------------


class _Stopped(Exception):
    """The author stopped the run, or the Server is closing."""


def _code(error: Exception) -> str:
    """A short reason for a try from what refused it."""
    if isinstance(error, CandidateHostError):
        return error.code
    if isinstance(error, HTTPException):
        detail = error.detail
        if isinstance(detail, dict):
            return str(detail.get("code") or detail.get("message") or error.status_code)
        if isinstance(detail, str) and detail:
            return detail
        return str(error.status_code)
    return type(error).__name__


def _try(kind: str, outcome: str, **fields: Any) -> dict[str, Any]:
    return {"kind": kind, "outcome": outcome, **fields}


def _core_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The turns as the core reads them: the try's own fields, not the child it drew."""
    keys = ("kind", "outcome", "reason", "share", "main_law", "sentence", "rank")
    return [{"attempts": [{key: attempt[key] for key in keys if attempt.get(key) is not None}
                          for attempt in turn["attempts"]]} for turn in turns]


def _law_names(basis: dict[str, Any]) -> list[str]:
    main = basis.get("main_law")
    names = [main] if main else []
    names.extend(name for name in (basis.get("laws") or {}) if name != main)
    return names


class AutonomousRunner:
    """Takes the runs, one thread each; one running run an owner."""

    def __init__(self, store: RunStore, *, max_workers: int = 4):
        self.store = store
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="inku-autonomous")
        self._lock = threading.Lock()
        self._stops: dict[str, threading.Event] = {}
        self._closing = False

    # -- the API --------------------------------------------------------------

    def start(self, actor: dict, *, history_id: str, moves: int, kinds: list[str], note: str | None,
              model: str, language: str, wild: bool | None) -> dict[str, Any]:
        owner = actor["id"]
        chunks = "chunks" in kinds
        note = (note or "").strip() or None
        if chunks and len(set(kinds)) != 1:
            raise HTTPException(422, {"code": "autonomous_chunks_alone",
                                      "message": "The chunk move runs alone, without the other moves."})
        if chunks and note is None:
            raise HTTPException(422, {"code": "autonomous_note_required",
                                      "message": "The chunk move needs the run's direction in the note."})
        parent = self._work(owner, history_id, chunks=chunks)
        if not str(parent["item"].get("svg") or ""):
            raise HTTPException(422, {"code": "autonomous_source_has_no_image",
                                      "message": "The work has no image to compare its children with."})
        with self._lock:
            if self._closing:
                raise HTTPException(503, {"code": "autonomous_closing", "message": "The Server is stopping."})
            running = self.store.running(owner)
            if running is not None:
                raise HTTPException(409, {"code": "autonomous_run_running", "run_id": running["id"],
                                          "history_id": running["history_id"],
                                          "message": "Another refinement run of yours is going on."})
            run = {
                "id": uuid.uuid4().hex, "owner_id": owner, "history_id": history_id, "state": "running",
                "stop_reason": None, "turns": [], "current": None, "last_kept_history_id": None, "error": None,
                "settings": {"moves": moves, "kinds": list(dict.fromkeys(kinds)), "note": note, "model": model,
                             "language": language, "wild": wild},
                "created_at": _now(),
            }
            self.store.save(run)
            # The thread writes its own copy; the answer is the run as it began.
            began = json.loads(json.dumps(run))
            stop = self._stops[run["id"]] = threading.Event()
            self._pool.submit(self._drive, run, actor, parent, stop)
        _logger.info("autonomous_run_started run=%s history=%s moves=%s kinds=%s", run["id"], history_id, moves,
                     ",".join(run["settings"]["kinds"]))
        return began

    def get(self, owner: str, run_id: str) -> dict[str, Any]:
        run = self.store.get(owner, run_id)
        if run is None:
            raise HTTPException(404, "autonomous_run_not_found")
        return run

    def stop(self, owner: str, run_id: str) -> dict[str, Any]:
        run = self.get(owner, run_id)
        stop = self._stops.get(run_id)
        if run["state"] == "running" and stop is not None:
            stop.set()
        return self.get(owner, run_id)

    def stopping(self, run_id: str) -> bool:
        stop = self._stops.get(run_id)
        return stop is not None and stop.is_set()

    def for_history(self, owner: str, history_id: str) -> list[dict[str, Any]]:
        return self.store.for_history(owner, history_id)

    def recover(self) -> None:
        """When the Server starts: the runs it was taking were cut off."""
        for run in self.store.interrupt_running():
            _logger.warning("autonomous_run_interrupted run=%s", run["id"])

    def close(self) -> None:
        """Stop every run without waiting for a model's answer; the next start marks any
        run that did not end as interrupted."""
        with self._lock:
            self._closing = True
            for stop in self._stops.values():
                stop.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # -- one run ----------------------------------------------------------------

    def _work(self, owner: str, history_id: str, *, chunks: bool = False) -> dict[str, Any]:
        """A work of the owner's as a try starts from it, with what the core reads of it (and, for a chunk
        run, how many chunks it has)."""
        from .pipeline_api import laws_records_of
        from .pipeline_runtime import get_service

        items = _db.get_items(owner, [history_id])
        if not items or items[0].get("user_id") != owner:
            raise HTTPException(404, "autonomous_source_not_found")
        item = items[0]
        basis = laws_records_of(get_service().store, owner, history_id).get("laws_basis") or {}
        description = pipeline_description(item.get("source_text") or item.get("input") or "").strip()
        facts = {"description_locked": bool(item.get("description_locked")),
                 "ddl_work": item.get("display_label") == "DDL" or not description,
                 "laws": _law_names(basis)}
        if basis.get("main_law"):
            facts["main_law"] = basis["main_law"]
        if chunks:
            facts["chunks"] = _chunk_count(item)
        return {"id": history_id, "item": item, "facts": facts}

    def _drive(self, run: dict[str, Any], actor: dict, parent: dict[str, Any], stop: threading.Event) -> None:
        settings = run["settings"]
        # The juxtaposition's four sentences, kept for the turn that asked for them.
        answers: dict[int, dict[str, Any]] = {}
        try:
            while True:
                if stop.is_set():
                    raise _Stopped
                answer = _core({"action": "next", "moves": settings["moves"], "kinds": settings["kinds"],
                                "parent": parent["facts"], "note": settings["note"],
                                "turns": _core_turns(run["turns"])})
                if answer.get("outcome") != "ok":
                    raise RuntimeError(f"next refused: {answer.get('reason')}: {answer.get('detail')}")
                if "stop" in answer:
                    self._finish(run, "done", answer["stop"]["reason"])
                    return
                step = answer["next"]
                run["current"] = {"turn": step["turn"], "attempt": step["attempt"], "kind": step["kind"]}
                self.store.save(run)
                if step["kind"] == "laws":
                    taken = self._laws(run, parent, step, stop)
                elif step["kind"] == "chunks":
                    taken = self._chunks(run, parent, step, stop)
                else:
                    taken = self._juxtaposition(run, actor, parent, step, stop, answers)
                self._add(run, step, taken)
                if taken["outcome"] == "kept":
                    run["last_kept_history_id"] = taken["history_id"]
                    parent = self._work(run["owner_id"], taken["history_id"],
                                        chunks="chunks" in settings["kinds"])
                run["current"] = None
                self.store.save(run)
        except _Stopped:
            run["current"] = None
            self._finish(run, "interrupted" if self._closing else "stopped",
                         "interrupted" if self._closing else "stopped")
        except Exception as error:  # noqa: BLE001
            _logger.exception("autonomous_run_failed run=%s", run["id"])
            run["current"] = None
            run["error"] = f"{type(error).__name__}: {error}"[:500]
            self._finish(run, "failed", "error")
        finally:
            self._stops.pop(run["id"], None)

    @staticmethod
    def _add(run: dict[str, Any], step: dict[str, Any], taken: dict[str, Any]) -> None:
        while len(run["turns"]) < step["turn"]:
            run["turns"].append({"attempts": []})
        run["turns"][step["turn"] - 1]["attempts"].append({"attempt": step["attempt"], **taken})

    def _finish(self, run: dict[str, Any], state: str, reason: str) -> None:
        run["state"], run["stop_reason"] = state, reason
        self.store.save(run)
        _logger.info("autonomous_run_ended run=%s state=%s reason=%s turns=%s", run["id"], state, reason,
                     len(run["turns"]))

    # -- the moves --------------------------------------------------------------

    def _options(self, run: dict[str, Any], parent: dict[str, Any], *, kind: str, metadata: dict) -> dict:
        """The run options of a child: the parent's settings and the run's one model."""
        item, settings = parent["item"], run["settings"]
        options: dict[str, Any] = {
            "stage1_model": settings["model"], "stage2_model": settings["model"],
            "catalog_mode": "fixed",
            "lineage_parent_node_id": item.get("lineage_node_id"), "derivation_kind": kind,
            "derivation_metadata": metadata, "count_generation": True, "ui_lang": settings["language"],
        }
        catalog = item.get("render_color_catalog_id") or item.get("catalog_id")
        if catalog:
            options["catalog_id"] = catalog
        if item.get("render_canvas_aspect_id"):
            options["canvas_aspect"] = item["render_canvas_aspect_id"]
        options["wild"] = settings.get("wild") is True
        return options

    def _settle(self, owner: str, start: Callable[[], dict], stop: threading.Event) -> dict:
        """Start a pipeline run and take it to its saved child; a stop cancels it."""
        from .pipeline_compat import _settled

        while True:
            try:
                view = start()
                break
            except HTTPException as error:
                if not (isinstance(error.detail, dict) and error.detail.get("code") == "pipeline_capacity_reached"):
                    raise
            if stop.wait(_CAPACITY_WAIT_SECONDS):
                raise _Stopped
        try:
            return _settled(owner, view, perform=True, reader_left=stop.is_set)
        except HTTPException as error:
            if error.status_code == 499:
                raise _Stopped from None
            raise

    @staticmethod
    def _phase_reason(error: HTTPException) -> str | None:
        detail = error.detail if isinstance(error.detail, dict) else {}
        phase = (detail.get("current_view") or {}).get("phase") or {}
        return phase.get("reason")

    def _measured(self, run: dict[str, Any], parent: dict[str, Any], step: dict[str, Any], kind: str,
                  child: dict[str, Any], record: dict[str, Any], initial: dict[str, Any],
                  *, gated: bool = True) -> dict[str, Any]:
        """Measure a drawn child against its parent, and write its move on its lineage edge. A chunk move's
        child is kept whatever the share (``gated`` false): the share is recorded, the gate not applied."""
        measured = _core({"action": "measure", "before": str(parent["item"].get("svg") or ""),
                          "after": str(child.get("svg") or "")})
        if measured.get("outcome") != "ok":
            raise RuntimeError(f"measure refused: {measured.get('reason')}: {measured.get('detail')}")
        outcome = "kept" if measured["passes"] or not gated else "not_visible"
        settings = run["settings"]
        recorded = _core({"action": "record", "run": run["id"], "turn": step["turn"], "moves": settings["moves"],
                          "attempt": step["attempt"], "kind": kind, "model": settings["model"], "outcome": outcome,
                          "share": measured["share"], "note": settings["note"], **record})
        if recorded.get("outcome") != "ok":
            raise RuntimeError(f"record refused: {recorded.get('reason')}: {recorded.get('detail')}")
        if child.get("lineage_node_id"):
            _db.set_lineage_edge_metadata(run["owner_id"], child["lineage_node_id"],
                                          {**initial, **recorded["metadata"]})
        return {"outcome": outcome, "share": measured["share"], "history_id": child.get("history_id"),
                "lineage_node_id": child.get("lineage_node_id")}

    def _laws(self, run: dict[str, Any], parent: dict[str, Any], step: dict[str, Any],
              stop: threading.Event) -> dict[str, Any]:
        from .pipeline_api import laws_records_of, saved_work_parent
        from .pipeline_runtime import get_service

        owner, service, direction = run["owner_id"], get_service(), step["direction"]
        options = self._options(run, parent, kind="laws_change", metadata={})
        try:
            relation, source_work = saved_work_parent(service.store, owner, parent["id"])
        except (HTTPException, CandidateHostError) as error:
            return _try("laws", "unavailable", reason=_code(error))
        try:
            view = self._settle(owner, lambda: service.start(
                owner, "saved_laws", str(source_work.get("source") or ""), parent=relation,
                source_work=source_work, options=options, direction=direction), stop)
        except HTTPException as error:
            reason = self._phase_reason(error)
            if reason is not None:
                return _try("laws", "failed" if reason in LAWS_SENT_FAILURES else "unavailable", reason=reason)
            # Refused while the run was prepared (a model the run may not use, the plan's admission).
            return _try("laws", "unavailable", reason=_code(error))
        except CandidateHostError as error:
            return _try("laws", "unavailable", reason=_code(error))
        child = view["result"]
        basis = laws_records_of(service.store, owner, child["history_id"]).get("laws_basis")
        if not basis:
            raise RuntimeError(f"the laws child {child['history_id']} keeps no laws basis")
        laws = {"main_law": basis["main_law"], "main_layer": basis["main_layer"], "laws": basis["laws"],
                "reason": basis["reason"], "excluded": list(direction.get("exclude") or []),
                "cards": direction.get("cards") or "as_usual"}
        taken = self._measured(run, parent, step, "laws", child, {"laws": laws}, {})
        return _try("laws", taken.pop("outcome"), main_law=basis["main_law"], **taken)

    def _juxtaposition(self, run: dict[str, Any], actor: dict, parent: dict[str, Any], step: dict[str, Any],
                       stop: threading.Event, answers: dict[int, dict[str, Any]]) -> dict[str, Any]:
        from .api_core.routers.render import juxtaposition_choices, juxtaposition_offer, juxtaposition_settings
        from .pipeline_api import LinkedHistoryForkBody
        from .pipeline_runtime import get_service

        owner, service, settings = run["owner_id"], get_service(), run["settings"]
        turn = step["turn"]
        if not step.get("reuse") or turn not in answers:
            try:
                offer = juxtaposition_offer(actor, parent["item"], list(step.get("exclude") or []))
                model, vision = juxtaposition_settings(actor, settings["model"])
            except HTTPException as error:
                return _try("juxtaposition", "unavailable", reason=_code(error))
            try:
                answers[turn] = juxtaposition_choices(offer, model=model, settings=vision,
                                                      language=settings["language"])
            except HTTPException as error:
                return _try("juxtaposition", "failed", reason=_code(error))
        answer = answers[turn]
        rank = int(step["rank"])
        choice = answer["choices"][rank - 1]
        moved = {"sentence": choice["sentence"], "history_ids": list(choice["history_ids"]), "rank": choice["rank"],
                 "position": choice["position"], "reason": choice["reason"], "candidates": answer["candidates"]}
        # What the Web writes for a juxtaposition, so the lineage leaves the sentence out next time.
        initial = {"edited_from_history_id": parent["id"],
                   "juxtaposition": {**moved, "model": answer["model"]}}
        options = self._options(run, parent, kind="description_edit", metadata=initial)
        joined = choice["joined"]
        try:
            linked = service.store.read_linked_history(owner, parent["id"])
        except Exception:  # noqa: BLE001
            linked = None

        def start() -> dict:
            if linked is not None:
                return service.fork_linked_history(owner, parent["id"], LinkedHistoryForkBody(
                    kind="description", text=joined, options=options))
            return service.fork_legacy(owner, parent["id"], "description", joined, options=options)

        try:
            view = self._settle(owner, start, stop)
        except HTTPException as error:
            return _try("juxtaposition", "failed", reason=self._phase_reason(error) or _code(error),
                        sentence=choice["sentence"], rank=rank)
        except CandidateHostError as error:
            return _try("juxtaposition", "failed", reason=_code(error), sentence=choice["sentence"], rank=rank)
        taken = self._measured(run, parent, step, "juxtaposition", view["result"], {"juxtaposition": moved}, initial)
        return _try("juxtaposition", taken.pop("outcome"), sentence=choice["sentence"], rank=rank, **taken)

    @staticmethod
    def _chunk_context(owner: str, item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """What a chunk move shows beside the parent's DDL, and the parent's composition record when its DDL
        has no title lines. The description is the parent's; the reading's core images and the composition's
        proposition are those of the nearest work up the lineage that keeps a composition (a chunk move's
        child keeps none); the moves so far are the chunk moves on the lineage's edges, root first."""
        chain, moves = [item], []
        node = item.get("lineage_node_id")
        if node:
            lineage = _db.get_lineage(owner, node, descendant_depth=0, node_limit=60, include_svg=False) or {}
            nodes = {entry["id"]: entry for entry in lineage.get("nodes") or []}
            edge_into: dict[str, dict] = {}
            for edge in lineage.get("edges") or []:
                edge_into.setdefault(edge["child_node_id"], edge)
            current, seen = node, set()
            while current in edge_into and current not in seen:
                seen.add(current)
                edge = edge_into[current]
                ai_move = (edge.get("metadata") or {}).get("ai_move") or {}
                if ai_move.get("kind") == "chunks" and isinstance(ai_move.get("chunks"), dict):
                    moves.append(ai_move["chunks"])
                current = edge["parent_node_id"]
                history = (nodes.get(current) or {}).get("history")
                if isinstance(history, dict):
                    chain.append(history)
        moves.reverse()
        record = next((work["description_ddl"] for work in chain
                       if isinstance(work.get("description_ddl"), dict) and work["description_ddl"].get("composition")),
                      {})
        composition = record.get("composition") or {}
        context = {
            "description": pipeline_description(item.get("source_text") or item.get("input") or "").strip(),
            "reading_core": list((record.get("reading") or {}).get("core") or []),
            "thesis": str((composition.get("answer") or {}).get("thesis") or ""),
            "history": [{"generation": place, "move": move.get("move"), "targets": list(move.get("targets") or []),
                         "reason": move.get("reason"), "applied": True}
                        for place, move in enumerate(moves, start=1)],
        }
        return context, _composition_of(item)

    def _send_chunk(self, run: dict[str, Any], step: dict[str, Any], context: dict, request: dict,
                    picture: tuple[str, dict[str, Any]] | None, sent: int, stop: threading.Event,
                    language: str) -> tuple[str | None, str | None]:
        """Send one request the core asked for, as the prototype sent it: the answer's text, or the failure."""
        from .pipeline_runtime import get_service

        prompt = {"system": request["system"], "message": request["text"],
                  "response_schema": request["response_schema"], "action_name": CHUNK_ACTION}
        if picture is not None:
            # The picture goes only where the prompt names it (provider_wire refuses it otherwise).
            prompt["images"] = [picture[1]]
        digest = hashlib.sha256(json.dumps(prompt, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode("utf-8")).hexdigest()
        # What the pipeline's record of a sent system prompt reads; the provider body leaves them out.
        prompt.update(prompt_id=f"inku.chunk-moves-{request['purpose']}.v1", prompt_digest=f"sha256:{digest}",
                      instruction_language=language)
        perform = get_service().provider_with_context(run["owner_id"], context,
                                                      [picture[0]] if picture is not None else None)
        failure = None
        for attempt in (1, 2):
            if stop.is_set():
                raise _Stopped
            action = {"tag": CHUNK_ACTION, "timeout_ms": str(CHUNK_TIMEOUT_MS), "payload": {"prompt": prompt},
                      "identity": {"action_id": f"{run['id']}-t{step['turn']}-{request['purpose']}-{sent}",
                                   "attempt": attempt, "request_digest": digest}}
            result = perform(action)
            if result["tag"] != "provider_failed":
                return str(result.get("response") or ""), None
            failure = str(result.get("failure") or "provider_failed")
            if failure not in _CHUNK_TRANSIENT or stop.wait(_CHUNK_RESEND_SECONDS):
                break
        return None, failure

    def _chunks(self, run: dict[str, Any], parent: dict[str, Any], step: dict[str, Any],
                stop: threading.Event) -> dict[str, Any]:
        """One chunk move: the core's turn (``chunk_moves``) asked to send, draw, keep or give up."""
        from .pipeline_api import saved_work_parent
        from .pipeline_runtime import get_service

        owner, service, settings, item = run["owner_id"], get_service(), run["settings"], parent["item"]
        options = self._options(run, parent, kind="chunk_move", metadata={})
        try:
            relation, source_work = saved_work_parent(service.store, owner, parent["id"])
            config, context = service.prepare_for(owner, "direct_ddl", str(item.get("ddl") or ""), options,
                                                  source_work)
        except (HTTPException, CandidateHostError) as error:
            return _try("chunks", "unavailable", reason=_code(error))
        shown, composition = self._chunk_context(owner, item)
        done = len(shown["history"])
        seed = int(hashlib.sha256(f"{run['id']}:{step['turn']}".encode()).hexdigest()[:15], 16)
        request = {"action": "start", "config": config, "ddl": str(item.get("ddl") or ""),
                   "context": {**shown, "direction": settings["note"] or "", "generation": done + 1,
                               "of": done + settings["moves"] - step["turn"] + 1},
                   "seed": str(seed), "diagnostics": _diagnostic_count(item)}
        if composition is not None:
            request["composition"] = composition
        answer = _chunk_core(request)
        if answer.get("outcome") != "ok":
            return _try("chunks", "unavailable", reason=str(answer.get("reason")))
        picture = _picture(str(item.get("svg") or ""))
        child: dict[str, Any] | None = None
        sent = 0
        chunk_offers: dict[str, dict] = {}
        while True:
            if stop.is_set():
                raise _Stopped
            todo, state = answer["todo"], answer["state"]
            choice = state.get("choice") or {}
            if todo == "send":
                sent += 1
                asked = answer["request"]
                if asked["purpose"] == "rewrite":
                    chunk_offers["rewrite"] = {"stage": "chunk_rewrite", "offer": asked.get("plugin_offer") or {"offered": [], "omitted": []}}
                text, failure = self._send_chunk(run, step, context, asked,
                                                 picture if asked["image"] else None, sent, stop,
                                                 str(config.get("language") or "ja"))
                if text is None:
                    return _try("chunks", "failed", reason=failure, move=choice.get("move"))
                answer = _chunk_core({"action": "answer", "config": config, "state": state, "answer": text})
            elif todo == "draw":
                ddl = answer["ddl"]
                try:
                    view = self._settle(owner, lambda: service.start(
                        owner, "direct_ddl", ddl, parent=relation,
                        source_work={**source_work, "chunk_plugin_offers": list(chunk_offers.values())}, options=options), stop)
                    child = view["result"]
                    saved = _db.get_items(owner, [child["history_id"]])
                    drawn_item = saved[0] if saved else {}
                    drawn = {"rendered": bool(child.get("svg")), "diagnostics": _diagnostic_count(drawn_item),
                             "marks": _marks(drawn_item)}
                except (HTTPException, CandidateHostError):
                    child, drawn = None, {"rendered": False}
                answer = _chunk_core({"action": "drawn", "config": config, "state": state, "drawn": drawn})
            elif todo == "keep" and child is not None:
                record = answer["record"]
                taken = self._measured(run, parent, step, "chunks", child, {"chunks": record}, {}, gated=False)
                return _try("chunks", taken.pop("outcome"), move=record["move"], targets=record["targets"],
                            title=record.get("title"), **taken)
            else:
                return _try("chunks", "failed", reason=str(answer.get("reason") or todo), move=choice.get("move"))


_runner: AutonomousRunner | None = None
_runner_lock = threading.Lock()


def get_runner() -> AutonomousRunner:
    global _runner
    with _runner_lock:
        if _runner is None:
            _runner = AutonomousRunner(RunStore(runs_db_url(PERSISTENCE_CONFIG.canonical_url)))
        return _runner


def shutdown() -> None:
    with _runner_lock:
        runner = _runner
    if runner is not None:
        runner.close()
