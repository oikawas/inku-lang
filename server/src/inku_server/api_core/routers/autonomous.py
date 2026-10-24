"""The AI refinement's runs (AI自動推敲, 2026-10-21): start one, read how it stands, stop it."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from ...autonomous_refine import MOVES_DEFAULT, NOTE_LIMIT, get_runner
from ..common import _resolved_vision_model
from ..deps import _current_user

router = APIRouter(dependencies=[Depends(_current_user)])


class AutonomousRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    history_id: str = Field(
        ..., min_length=1, max_length=200,
        description="ID of the saved work to refine. The work must have an image, or the run is refused with 422.",
    )
    moves: int = Field(
        default=MOVES_DEFAULT, ge=1, le=10,
        description="Number of moves the run takes, from 1 to 10. Defaults to 5.",
    )
    kinds: list[Literal["laws", "juxtaposition"]] = Field(
        default_factory=lambda: ["laws", "juxtaposition"], min_length=1, max_length=2,
        description=(
            "Move kinds the run may take: laws (the laws stage again on the saved work, leaving out the "
            "laws its parent used) and juxtaposition (adds a sentence from another of the author's works "
            "after the description). Defaults to both; at least one is required."
        ),
    )
    # The author's direction; it reaches the laws move only.
    note: str | None = Field(
        default=None, max_length=NOTE_LIMIT,
        description="The author's direction for the laws move, up to 1,000 characters. Only the laws move reads it, though it is kept on each child's lineage record. Blank text is treated as no note.",
    )
    # One model takes every move and draws every child; none takes the account's Vision model.
    model: str | None = Field(
        default=None, min_length=1, max_length=200,
        description="Model used for every move and for drawing every child, as a model ID. Omitted uses the account's Vision model.",
    )
    language: str = Field(
        default="ja", pattern="^(ja|en)$",
        description="Language of the run's instructions: ja or en. Defaults to ja.",
    )
    # The Wild switch for every child; none keeps each parent's.
    wild: bool | None = Field(
        default=None,
        description="Wild setting applied to every child. Omitted keeps each parent's setting.",
    )


class AutonomousTry(BaseModel):
    attempt: int = Field(description="Number of this try within its turn.")
    kind: str = Field(description="Move kind of this try: laws or juxtaposition.")
    # kept, not_visible, unavailable or failed.
    outcome: str = Field(
        description=(
            "Result of the try: kept (the child differs visibly from its parent and becomes the next parent), "
            "not_visible (the child does not differ visibly enough and stays in the lineage only), "
            "unavailable (the move could not be taken), or failed (an error ended the try)."
        ),
    )
    reason: str | None = Field(default=None, description="Reason for the outcome, when one is recorded. Null otherwise.")
    # The share of the drawn cells the child changed (the visible-difference gate).
    share: float | None = Field(
        default=None,
        description="Share of the drawn cells the child changed from its parent, used by the visible-difference check. Null when not measured.",
    )
    main_law: str | None = Field(default=None, description="Main law that the laws move's basis named for the child, when recorded. Null for other moves.")
    sentence: str | None = Field(default=None, description="Sentence the juxtaposition move chose, when recorded. On a failed try it may not have been added to the description. Null for laws moves.")
    rank: int | None = Field(default=None, description="Rank of the chosen sentence among the juxtaposition candidates, counted from 1, when recorded.")
    history_id: str | None = Field(default=None, description="ID of the child work this try saved, when it saved one.")
    lineage_node_id: str | None = Field(default=None, description="ID of the lineage node that records this try's move on its edge.")


class AutonomousTurn(BaseModel):
    attempts: list[AutonomousTry] = Field(description="The tries taken in this turn, in the order they were taken.")


class AutonomousCurrent(BaseModel):
    turn: int = Field(description="Turn now under way, counted from 1.")
    attempt: int = Field(description="Try now under way within the turn.")
    kind: str = Field(description="Move kind now being taken: laws or juxtaposition.")


class AutonomousSettings(BaseModel):
    moves: int = Field(description="Number of moves the run was started with.")
    kinds: list[str] = Field(description="Move kinds the run was started with.")
    note: str | None = Field(default=None, description="The author's direction the run was started with. Null when none was given.")
    model: str = Field(description="Model the run was started with, used for every move and every child drawing.")
    language: str = Field(description="Language of the run's instructions: ja or en.")
    wild: bool | None = Field(default=None, description="Wild setting applied to every child. Null keeps each parent's setting.")


class AutonomousRunResponse(BaseModel):
    id: str = Field(description="ID of the run.")
    history_id: str = Field(description="ID of the saved work the run started from.")
    # running, done, stopped, failed or interrupted.
    state: str = Field(
        description="State of the run: running, done (the run ended on its own), stopped (a stop was asked for), failed (an error ended it), or interrupted (the Server stopped while it ran).",
    )
    stop_reason: str | None = Field(default=None, description="Why the run ended. Null while it is running.")
    # A stop was asked for and the try being taken is ending.
    stopping: bool = Field(default=False, description="True after a stop was asked for while a try is still ending.")
    settings: AutonomousSettings = Field(description="Settings the run was started with.")
    turns: list[AutonomousTurn] = Field(description="Turns taken so far, each with its tries.")
    current: AutonomousCurrent | None = Field(default=None, description="The turn, try and move kind now under way. Null when no try is being taken.")
    last_kept_history_id: str | None = Field(
        default=None, description="ID of the last child the run kept. The work's history shows it when the run ends.",
    )
    error: str | None = Field(default=None, description="Error message when the run failed. Null otherwise.")
    created_at: int = Field(description="When the run started, as Unix time in milliseconds.")
    updated_at: int = Field(description="When the run was last updated, as Unix time in milliseconds.")


class AutonomousRunList(BaseModel):
    runs: list[AutonomousRunResponse] = Field(description="The latest runs started from the work, newest first.")


def _view(run: dict) -> AutonomousRunResponse:
    fields = {key: value for key, value in run.items() if key != "owner_id"}
    return AutonomousRunResponse(**fields, stopping=get_runner().stopping(run["id"]))


@router.post("/api/refine/autonomous", response_model=AutonomousRunResponse, summary="Start an autonomous refinement run")
def api_autonomous_start(body: AutonomousRunBody, actor: dict = Depends(_current_user)) -> AutonomousRunResponse:
    """Start a run from a saved work; one run of an owner's goes on at a time (409)."""
    return _view(get_runner().start(
        actor, history_id=body.history_id, moves=body.moves, kinds=list(body.kinds), note=body.note,
        model=_resolved_vision_model(body.model, actor), language=body.language, wild=body.wild,
    ))


@router.get("/api/refine/autonomous", response_model=AutonomousRunList, summary="List autonomous refinement runs for a work")
def api_autonomous_for_history(
    history_id: str = Query(..., min_length=1, max_length=200, description="ID of the saved work whose runs to list."),
    actor: dict = Depends(_current_user),
) -> AutonomousRunList:
    """The latest runs started from a work, newest first."""
    return AutonomousRunList(runs=[_view(run) for run in get_runner().for_history(actor["id"], history_id)])


@router.get("/api/refine/autonomous/{run_id}", response_model=AutonomousRunResponse, summary="Read an autonomous refinement run")
def api_autonomous_get(run_id: str = Path(description="ID of the run to read."), actor: dict = Depends(_current_user)) -> AutonomousRunResponse:
    """Read a run's state, its turns and tries, and the settings it started with. Only the caller's own runs are found; another ID returns 404 (autonomous_run_not_found)."""
    return _view(get_runner().get(actor["id"], run_id))


@router.post("/api/refine/autonomous/{run_id}/stop", response_model=AutonomousRunResponse, summary="Stop an autonomous refinement run")
def api_autonomous_stop(run_id: str = Path(description="ID of the run to stop."), actor: dict = Depends(_current_user)) -> AutonomousRunResponse:
    """Stop a run: the drawing under way is cancelled and the children kept so far stay."""
    return _view(get_runner().stop(actor["id"], run_id))
