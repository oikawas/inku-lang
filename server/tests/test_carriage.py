"""搬送検査 -- T-6 of 契約 description-propagation-cut, [I-107].

Two directions, and they fail independently:

    dropped -- what the DDL declares does not reach the Score
    added   -- what the DDL never declared reaches it anyway

No threshold is asserted here. 契約 §5-6 leaves "what rate is acceptable" to a
separate decision, and a number invented at gate-writing time would be the
threshold forever. What is gated is that the instrument discriminates: a gate
that cannot tell a carried work from a dropped one reports whatever it is
handed. The production numbers come from scripts/measure_carriage.py.

Everything goes through `coerce_score` or the paint entry. Calling the
predicates on their own skips the caller's gate and over-reports -- the
44%-vs-0% incident.
"""

from __future__ import annotations

import json
import pathlib

import pytest

# Importing the app is what creates the schema for the test database.
from inku_server.api import app as _app  # noqa: F401
from inku_server.api_core.routers import render as render_routes
from inku_server.carriage import carriage_report
from inku_server.coerce import coerce_score
from inku_server.schema import Score

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "count_preservation_cases.json"


def _replay(ddl: str, score: Score):
    branch_report: dict[str, int] = {}
    after = coerce_score(score, ddl=ddl, branch_report=branch_report)
    return carriage_report(ddl, before=score, after=after, branch_report=branch_report)


def _score(instructions: list[dict], **changes) -> Score:
    return Score.model_validate({"instructions": instructions, **changes})


# ------------------------------------------------------- direction 1: dropped

def test_a_declared_line_style_that_never_arrives_is_reported():
    """The DDL names a style with one legal reading and the Score does not
    carry it. Unlike the material words, no branch of coerce repairs this one,
    so what the report says is what actually reached the renderer."""
    report = _replay(
        "黒い破線を一本引く。",
        _score([{"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5],
                 "color": "black", "style": "solid"}]),
    )

    assert any("破線" in warning for warning in report.dropped), report.dropped


def test_a_declared_line_style_that_does_arrive_is_not_reported():
    """Control. Without it, "report everything" passes the case above."""
    report = _replay(
        "黒い破線を一本引く。",
        _score([{"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5],
                 "color": "black", "style": "dashed"}]),
    )

    assert [warning for warning in report.dropped if "破線" in warning] == []


# --------------------------------------------------------- direction 2: added

def test_an_instruction_the_ddl_never_declared_is_counted_as_authored():
    """A DDL with one shape, and a Score coerce grows past it.

    This direction had no instrument at all. Before the cut it could not have
    one: coerce read `prose\\nDDL`, so anything it authored could be traced back
    to some word the author wrote, and an addition was indistinguishable from a
    delivery.

    Since the staffage level was folded away (v2.11.0) every addition answers to
    a clause -- the branches that answered to nothing are gone -- so the input
    here is a DDL whose second clause the Score never delivered.
    """
    report = _replay(
        "赤い円を三つ散らす。黒い細筆の細い線を右端に一本引く。",
        _score([{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1, "color": "red"}]),
    )

    assert report.instructions_out > report.instructions_in
    assert len(report.additions) == report.instructions_out - report.instructions_in
    assert report.branches_that_fired, "the branches that authored them are unnamed"


def test_an_untouched_score_reports_no_additions():
    """Control. A Score coerce leaves alone must not read as authored, or the
    instrument counts repair as authorship and every work looks the same."""
    report = _replay(
        "黒い線を四十本並べる。",
        _score([{"primitive": "line", "from": [0.1, 0.02 + index * 0.02],
                 "to": [0.9, 0.02 + index * 0.02], "color": "black"}
                for index in range(40)]),
    )

    assert report.additions == []
    assert report.instructions_in == report.instructions_out == 40


def test_a_repaired_instruction_is_not_an_addition():
    """Repair is most of what this layer does. A normalized field is not a new
    mark, and counting it as one would put the added rate at 100%."""
    report = _replay(
        "静かな水面。",
        _score([{"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5], "color": "white"}]),
    )

    # coerce rewrites the invisible white line to a visible colour, in place.
    assert report.instructions_out == 1
    assert report.additions == []


def test_the_ground_of_an_addition_is_recorded():
    """An addition that answers to a clause and one that answers to nothing are
    different facts. Collapsing them makes coerce's own composition invisible --
    which is the whole of what this direction is for."""
    report = _replay(
        "赤い円を三つ散らす。黒い細筆の細い線を右端に一本引く。",
        _score([{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1, "color": "red"}]),
    )

    assert report.declared_colors == frozenset({"red", "black"})
    assert report.declared_primitives == frozenset({"circle", "line"})
    grounds = {(addition.grounded_primitive, addition.grounded_color) for addition in report.additions}
    assert grounds, "no addition to attribute"
    assert all(isinstance(addition.grounded, bool) for addition in report.additions)


# ------------------------------------------------------------- the entry path

def test_the_report_can_be_taken_from_the_paint_entry_point(monkeypatch):
    """Not from a predicate. The Score the endpoint returns and the Score Stage 2
    wrote are both needed, and only the entry path holds them together."""
    ddl = "赤い円を三つ散らす。ゆっくり波打つ。"
    stage2 = _score([{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1, "color": "red"}])

    monkeypatch.setattr(render_routes, "sketch_from_life",
                        lambda text, **kwargs: ("円がある。", 1, 2))
    monkeypatch.setattr(render_routes, "interpret_detail",
                        lambda text, **kwargs: (ddl, None, 3, 4))
    monkeypatch.setattr(render_routes, "compose", lambda d, **kwargs: (stage2, 5, 6))

    response = None
    request = render_routes.PaintRequest(
        description="赤い円が三つ散っている",
        sketch=False,
        instruction_lang="ja",
        save_history=False,
        save_artifacts=False,
        count_generation=False,
    )
    for event in render_routes._paint_events(request, None, {"id": "test-user"}):
        if event["event"] == "done":
            response = event["response"]
    assert response is not None

    report = carriage_report(
        response.ddl,
        before=stage2,
        after=response.score,
        branch_report=dict(response.coerce_branch_counts or {}),
    )
    assert report.instructions_out >= report.instructions_in
    assert report.branches_that_fired


# ----------------------------------------------------------- non-vacuity

def test_the_instrument_has_a_denominator_on_the_real_corpus():
    """A rate over an empty denominator is not a rate. Report how many cases
    were looked at: a sweep that silently checked nothing reads exactly like a
    sweep that found nothing wrong.
    """
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    looked_at = 0
    with_a_declaration = 0
    with_additions = 0
    for case in cases:
        report = _replay(case["ddl"], Score.model_validate(case["score"]))
        looked_at += 1
        if report.declared_colors or report.declared_primitives:
            with_a_declaration += 1
        if report.additions:
            with_additions += 1

    assert looked_at == len(cases) >= 20
    assert with_a_declaration > 0, "no case in the corpus declares anything"
    assert with_additions > 0, "the added direction fires on nothing here"


@pytest.mark.parametrize("ddl", ["", None])
def test_an_empty_ddl_declares_nothing_rather_than_everything(ddl):
    """An empty declaration must not read as "everything is ungrounded", which
    would make every work look like pure invention."""
    report = _replay(ddl or "", _score([{"primitive": "line", "from": [0.2, 0.5],
                                         "to": [0.8, 0.5], "color": "black"}]))

    assert report.declared_colors == frozenset()
    assert report.declared_primitives == frozenset()
    assert report.dropped == []
