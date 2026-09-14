"""Saved sketch metadata compatibility after the Stage 0.5 producer retirement."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from inku_server.api_core.models import HistoryPostBody, HistoryItem
from inku_server.api_core.routers.history import _derived_sketch_state
from inku_server.sketch import SKETCH_STATES, SketchDetail, sketch_state_of


DESCRIPTION = "ひさかたの光のどけき春の日にしづ心なく花の散るらむ"


def test_saved_sketch_state_vocabulary_and_derivation() -> None:
    assert SKETCH_STATES == ("fine", "coarse", "fallback", "off", "not_applicable")
    assert sketch_state_of(None, requested=False, has_description=True) == "off"
    assert sketch_state_of(None, requested=False, has_description=False) == "not_applicable"
    assert (
        sketch_state_of(
            SketchDetail(text="x", grain="fine", fallback_used=True),
            requested=True,
            has_description=True,
        )
        == "fallback"
    )


def test_client_saved_score_derives_sketch_state_when_omitted() -> None:
    base = {"input": DESCRIPTION, "score": {"instructions": []}, "at": 1}
    assert _derived_sketch_state(HistoryPostBody(**base)) == "off"
    assert (
        _derived_sketch_state(
            HistoryPostBody(**base, sketch_text="円がある。", sketch_grain="coarse")
        )
        == "coarse"
    )


def test_unknown_saved_sketch_state_is_refused() -> None:
    with pytest.raises(ValidationError):
        HistoryPostBody(
            input=DESCRIPTION,
            score={"instructions": []},
            at=1,
            sketch_state="sketched",
        )


def test_saved_sketch_state_survives_history_response_model() -> None:
    item = HistoryItem(
        id="sketch-state-read",
        at=1,
        input=DESCRIPTION,
        score={},
        svg="",
        elapsed_ms=0,
        sketch_text="円がある。",
        sketch_grain="fine",
        sketch_state="fine",
    )
    assert item.sketch_state == "fine"
