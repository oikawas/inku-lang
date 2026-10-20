"""The AI refinement's runs (AI自動推敲, 2026-10-21): start one, read how it stands, stop it."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from ...autonomous_refine import MOVES_DEFAULT, NOTE_LIMIT, get_runner
from ..common import _resolved_vision_model
from ..deps import _current_user

router = APIRouter(dependencies=[Depends(_current_user)])


class AutonomousRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    history_id: str = Field(..., min_length=1, max_length=200)
    moves: int = Field(default=MOVES_DEFAULT, ge=1, le=10)
    kinds: list[Literal["laws", "juxtaposition"]] = Field(
        default_factory=lambda: ["laws", "juxtaposition"], min_length=1, max_length=2
    )
    # The author's direction; it reaches the laws move only.
    note: str | None = Field(default=None, max_length=NOTE_LIMIT)
    # One model takes every move and draws every child; none takes the account's Vision model.
    model: str | None = Field(default=None, min_length=1, max_length=200)
    language: str = Field(default="ja", pattern="^(ja|en)$")
    # The Wild switch for every child; none keeps each parent's.
    wild: bool | None = None


class AutonomousTry(BaseModel):
    attempt: int
    kind: str
    # kept, not_visible, unavailable or failed.
    outcome: str
    reason: str | None = None
    # The share of the drawn cells the child changed (the visible-difference gate).
    share: float | None = None
    main_law: str | None = None
    sentence: str | None = None
    rank: int | None = None
    history_id: str | None = None
    lineage_node_id: str | None = None


class AutonomousTurn(BaseModel):
    attempts: list[AutonomousTry]


class AutonomousCurrent(BaseModel):
    turn: int
    attempt: int
    kind: str


class AutonomousSettings(BaseModel):
    moves: int
    kinds: list[str]
    note: str | None = None
    model: str
    language: str
    wild: bool | None = None


class AutonomousRunResponse(BaseModel):
    id: str
    history_id: str
    # running, done, stopped, failed or interrupted.
    state: str
    stop_reason: str | None = None
    # A stop was asked for and the try being taken is ending.
    stopping: bool = False
    settings: AutonomousSettings
    turns: list[AutonomousTurn]
    current: AutonomousCurrent | None = None
    last_kept_history_id: str | None = None
    error: str | None = None
    created_at: int
    updated_at: int


class AutonomousRunList(BaseModel):
    runs: list[AutonomousRunResponse]


def _view(run: dict) -> AutonomousRunResponse:
    fields = {key: value for key, value in run.items() if key != "owner_id"}
    return AutonomousRunResponse(**fields, stopping=get_runner().stopping(run["id"]))


@router.post("/api/refine/autonomous", response_model=AutonomousRunResponse)
def api_autonomous_start(body: AutonomousRunBody, actor: dict = Depends(_current_user)) -> AutonomousRunResponse:
    """Start a run from a saved work; one run of an owner's goes on at a time (409)."""
    return _view(get_runner().start(
        actor, history_id=body.history_id, moves=body.moves, kinds=list(body.kinds), note=body.note,
        model=_resolved_vision_model(body.model, actor), language=body.language, wild=body.wild,
    ))


@router.get("/api/refine/autonomous", response_model=AutonomousRunList)
def api_autonomous_for_history(
    history_id: str = Query(..., min_length=1, max_length=200),
    actor: dict = Depends(_current_user),
) -> AutonomousRunList:
    """The latest runs started from a work, newest first."""
    return AutonomousRunList(runs=[_view(run) for run in get_runner().for_history(actor["id"], history_id)])


@router.get("/api/refine/autonomous/{run_id}", response_model=AutonomousRunResponse)
def api_autonomous_get(run_id: str, actor: dict = Depends(_current_user)) -> AutonomousRunResponse:
    return _view(get_runner().get(actor["id"], run_id))


@router.post("/api/refine/autonomous/{run_id}/stop", response_model=AutonomousRunResponse)
def api_autonomous_stop(run_id: str, actor: dict = Depends(_current_user)) -> AutonomousRunResponse:
    """Stop a run: the drawing under way is cancelled and the children kept so far stay."""
    return _view(get_runner().stop(actor["id"], run_id))
