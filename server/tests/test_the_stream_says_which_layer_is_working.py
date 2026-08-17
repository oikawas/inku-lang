"""待っているあいだ、どの層が働いているかが画面に出る -- contract
tasks/the-stream-says-which-layer-is-working.md ([I-302]).

T-242〜T-247, T-249〜T-251. (T-248 と T-252 は web 側、T-253 は
`test_api.py::test_paint_stream_matches_paint_response_shape`、T-254 は凍結物。)

A drawing passes through four layers and only two of them used to say
anything. The gates here measure *when* an event is written, not merely that
it appears: an event emitted in the right order but after the work it claims to
precede would tell the page nothing it did not already know.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.api_core.routers import render as render_routes
from inku_server.schema import Score

client = TestClient(app)

DESCRIPTION = "ひさかたの光のどけき春の日にしづ心なく花の散るらむ"

SCORE = Score.model_validate(
    {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
)


@pytest.fixture
def auth():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"stream-{suffix}")
    user = db.add_user(
        username=f"stream-{suffix}",
        email=f"stream-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


@pytest.fixture
def wired(monkeypatch):
    """Every model call replaced; the wiring left alone."""

    class FakeExpansion:
        ddl = "黒い円を中心に置く。"
        provenance: list = []
        warnings: list = []
        instructions: list = []

    monkeypatch.setattr(
        render_routes, "sketch_from_life", lambda text, **kw: ("[fine] 円がある。", 11, 22)
    )
    monkeypatch.setattr(
        render_routes, "interpret_detail", lambda text, **kw: ("黒い円を中心に置く。", None, 3, 4)
    )
    monkeypatch.setattr(
        render_routes.DOCUMENT_PLUGIN_MANAGER, "expand", lambda ddl, **kw: FakeExpansion()
    )
    monkeypatch.setattr(render_routes, "expand_intermediate_for_lang", lambda ddl, **kw: ddl)
    monkeypatch.setattr(render_routes, "compose", lambda ddl, **kw: (SCORE, 5, 6))
    monkeypatch.setattr(render_routes, "coerce_score", lambda score, **kw: score)
    monkeypatch.setattr(render_routes, "_add_history_item", lambda **kw: {
        "id": "h1",
        "description_hash": None,
        "lineage_node_id": None,
        "lineage_parent_node_id": None,
        "derivation_kind": None,
    })


def _body(**overrides) -> dict:
    body = {
        "description": DESCRIPTION,
        "sketch": False,
        "save_history": False,
        "save_artifacts": False,
        "count_generation": False,
    }
    body.update(overrides)
    return body


def _events(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def _names(response) -> list[str]:
    return [e["event"] for e in _events(response)]


def _request(**overrides):
    """A PaintRequest, for the gates that drive the generator directly."""
    return render_routes.PaintRequest(**_body(**overrides))


def _generator(**overrides):
    return render_routes._paint_events(_request(**overrides), None, {"id": "test-user"})


# --------------------------------------------------------------------- T-242

def test_t242_a_painted_sketch_puts_four_events_on_the_wire(auth, wired):
    """写生 on: every layer that can report does."""
    r = client.post("/api/paint/stream", json=_body(sketch=True), headers=auth)

    assert r.status_code == 200
    assert _names(r) == ["sketch", "stage1", "score", "done"]

    sketch = _events(r)[0]
    assert sketch["sketch_state"] == "fine"
    assert sketch["fallback_used"] is False
    assert sketch["elapsed_ms"] >= 0
    # The prose does not travel here: `done` already carries it, and a
    # description may run to 100,000 characters.
    assert "text" not in sketch


# --------------------------------------------------------------------- T-243

def test_t243_with_the_layer_off_no_sketch_event_is_written(auth, wired):
    """写生 off: the layer contributed nothing, so it reports nothing."""
    r = client.post("/api/paint/stream", json=_body(), headers=auth)

    assert r.status_code == 200
    assert _names(r) == ["stage1", "score", "done"]


# --------------------------------------------------------------------- T-244

def test_t244_the_sketch_event_is_written_before_stage1_runs(wired, monkeypatch):
    """順番ではなく時点を測る.

    An event that arrives first in the list but is written after interpretation
    has already run would tell the page nothing: by then the layer it names is
    finished and so is the next one. So pull exactly one event and ask whether
    Stage 1 has been called at all.
    """
    calls: list[str] = []

    def counted_interpret(text, **kw):
        calls.append(text)
        return ("黒い円を中心に置く。", None, 3, 4)

    monkeypatch.setattr(render_routes, "interpret_detail", counted_interpret)

    events = _generator(sketch=True)
    first = next(events)

    assert first["event"] == "sketch"
    assert calls == [], "Stage 1 had already run when the sketch event was written"
    events.close()


# --------------------------------------------------------------------- T-245

def test_t245_the_score_event_is_written_before_the_performance(wired, monkeypatch):
    """Same measurement one stage later: the Score is final, the drawing is not."""
    calls: list[object] = []
    original = render_routes._render_with_metadata

    def counted_render(score, metadata):
        calls.append(score)
        return original(score, metadata)

    monkeypatch.setattr(render_routes, "_render_with_metadata", counted_render)

    events = _generator()
    for event in events:
        if event["event"] == "score":
            break
    else:  # pragma: no cover - the score event is asserted elsewhere too
        raise AssertionError("no score event was written")

    assert calls == [], "the drawing had already been made when the score event was written"
    events.close()


# --------------------------------------------------------------------- T-246

def test_t246_a_sketch_that_came_with_the_request_still_reports(auth, wired, monkeypatch):
    """記述に写生文が付いてきた回.

    Stage 0.5 settled without a model call, so `elapsed_ms` is near zero -- and
    that is not a lie: the layer is genuinely decided. Splitting the event by
    "did we call the model" would put the same judgment in two places.
    """
    calls: list[str] = []

    def counted_sketch(text, **kw):
        calls.append(text)
        return ("[fine] 呼ばれてはならない。", 11, 22)

    monkeypatch.setattr(render_routes, "sketch_from_life", counted_sketch)

    r = client.post(
        "/api/paint/stream",
        json=_body(sketch=False, sketch_text="円がある。円は黒い。"),
        headers=auth,
    )

    assert r.status_code == 200
    assert _names(r) == ["sketch", "stage1", "score", "done"]
    assert calls == [], "the layer called the model for a sketch it was handed"


# --------------------------------------------------------------------- T-247

def test_t247_the_recorded_stage2_elapsed_is_not_shortened(wired, monkeypatch):
    """`t2` を `score` の位置へ繰り上げると、記録される作曲の所要が黙って縮む.

    `_render_metadata` is called after the Score is final and before `t2`, so
    sleeping in it lands inside the recorded Stage 2 span and outside the span
    the score event reports. If the two clocks were one, both would read 50.
    """
    original = render_routes._render_metadata

    def slow_metadata(*args, **kwargs):
        time.sleep(0.05)
        return original(*args, **kwargs)

    monkeypatch.setattr(render_routes, "_render_metadata", slow_metadata)

    score_event = None
    done_event = None
    for event in _generator():
        if event["event"] == "score":
            score_event = event
        elif event["event"] == "done":
            done_event = event

    assert score_event is not None and done_event is not None
    assert done_event["response"].elapsed_stage2_ms >= 50
    assert score_event["elapsed_ms"] < 50


# --------------------------------------------------------------------- T-249

def test_t249_after_a_sketch_event_a_stage1_failure_arrives_in_the_body(auth, wired, monkeypatch):
    """境目が 1 段ぶん前へ動いたことの固定.

    The response is committed once the first event is written. Stage 0.5 now
    writes one, so on a sketched request a Stage 1 failure can no longer be an
    HTTP status -- it is an error event instead. The page shows the same words
    either way: both paths hand the same detail and status to the same reader.
    """

    def failing_interpret(text, **kw):
        raise RuntimeError("interpret failed for test")

    monkeypatch.setattr(render_routes, "interpret_detail", failing_interpret)

    r = client.post("/api/paint/stream", json=_body(sketch=True), headers=auth)

    assert r.status_code == 200
    events = _events(r)
    assert [e["event"] for e in events] == ["sketch", "error"]
    assert events[-1]["status"] == 502


# --------------------------------------------------------------------- T-250

def test_t250_a_label_only_description_is_still_a_400_with_the_layer_on(auth, wired):
    """The guard sits before Stage 0.5, so it raises with no event written.

    This is `test_description_is_the_origin.py::test_t1_paint_stream_refuses_...`
    asked again with `sketch=true`: the boundary that moved must not have taken
    this refusal with it.
    """
    r = client.post("/api/paint/stream", json=_body(description="[note]", sketch=True), headers=auth)

    assert r.status_code == 400
    assert r.json()["detail"] == "description is only labels"


# --------------------------------------------------------------------- T-251

def test_t251_with_the_layer_off_a_stage1_failure_is_still_http_502(auth, wired, monkeypatch):
    """対の表明。**これが無いと T-249 だけでは「境目が常に前へ動いた」と読める。**"""

    def failing_interpret(text, **kw):
        raise RuntimeError("interpret failed for test")

    monkeypatch.setattr(render_routes, "interpret_detail", failing_interpret)

    r = client.post("/api/paint/stream", json=_body(), headers=auth)

    assert r.status_code == 502
