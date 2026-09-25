"""T-95..T-104 of 契約 a-work-redraws-under-the-limits-it-was-drawn-under (ledger I-154).

Two defects, one contract.

  replay    the limits a work was drawn under are recorded on its row, and
            nothing read them back. The same request that restored the work's
            colors from that row redrew it at whatever ceiling the installation
            happens to hold today -- measured 2026-08-16 as a work recorded at
            `represented_count_max: 120` coming back drawn at 60, with
            `render_color_source: "snapshot"` in the same answer (T-95..T-101).

  silence   nine settings bound how much ink a work may carry and two of them
            could say so. Lowering one halved a picture -- 2,149,767 bytes to
            1,038,689 -- while `render_limit_notes` stayed None on both and the
            note inside the Score did not differ by a byte (T-102..T-104).

What each stage can get wrong, and what catches it here:

  source    a redraw that reads only the colors off the row (T-95); a row with
            no record answered as if nobody had named a work (T-96); a fresh
            drawing answered as if a row had been read (T-97);
  reporting `render_limits` alone, which names numbers but not where they came
            from, so a faithful replay and today's settings read identically
            (T-99);
  request   a caller raising a ceiling the administrator lowered (T-101);
  naming    a limit that took effect without saying which one it was (T-102),
            and one that says so when it did not (T-103);
  spill     the plugin budget reading a module constant instead of the setting,
            so the warning it writes states a number no administrator set
            (T-104). Since the shared compiler (2026-09-14) the budget reaches
            the compiler itself, so T-104 reads the number a new drawing ran
            under and where it came from.
"""

from __future__ import annotations

import copy
import importlib
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql_text

from inku_server import db, pipeline_product
from inku_server.api import app
from inku_server.api_core.rendering import (
    LIMITS_SOURCE_HEADER,
    LIMITS_SOURCE_REQUEST,
    LIMITS_SOURCE_SETTINGS,
    LIMITS_SOURCE_WORK,
    LIMITS_SOURCE_WORK_UNRECORDED,
)
from inku_server.limits import DEFAULT_LIMITS, LIMIT_FIELD_NAMES, Limits, using_limits
from inku_server.saved_score_compat import coerce_saved_score

client = TestClient(app)

# One scatter, far above every per-instruction budget, so the density governors
# are the only thing deciding the count that comes out. 600 is the number the
# defect was measured on.
CROWD = 600
CROWD_SCORE = {
    "instructions": [
        {
            "primitive": "ellipse",
            "at": {"region": [0.05, 0.05, 0.95, 0.95]},
            "size": [0.01, 0.01],
            "arrangement": {"count": CROWD, "layout": "scatter"},
        }
    ]
}

# The setting an administrator lowers between the drawing and the redraw. Only
# `represented_count_max` moves: a redraw that honours the work's row must come
# back at 120 whatever this says, and a second moved field would leave two
# explanations for one number.
LOWERED = {"represented_count_max": 60}


@pytest.fixture
def stored_limits():
    """Store a setting and put it back afterwards.

    app_settings is process-wide, so a leaked value would silently retune every
    test that runs after this one.
    """
    written: list[dict] = []

    def store(values: dict) -> dict:
        if not written:
            written.append(db.get_render_limit_settings())
        return db.update_render_limit_settings(values)

    yield store
    if written:
        db.update_render_limit_settings(written[0])


@pytest.fixture
def author():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"i154-{suffix}")
    user = db.add_user(
        username=f"i154-{suffix}",
        email=f"i154-{suffix}@example.test",
        password="password-123",
        permission_groups=["admins"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    headers = {"Authorization": f"Bearer {token}"}
    created: list[str] = []
    yield headers, user, created
    if created:
        db.delete_items(user["id"], created)
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def _save(headers, created, score=None, at=1_785_000_000_000, input_text="群れ") -> dict:
    """Save a work the way the browser does, through coerce site 2.

    `input_text` is a parameter because two saves of one picture are ONE row:
    the render hash is taken over the input, the Score and the SVG, and a second
    save that hashes the same replaces the first rather than adding to it. A
    test wanting two rows has to give them something to differ by, and the input
    is the field that does not reach the drawing.
    """
    saved = client.post(
        "/api/history",
        json={"input": input_text, "score": score or CROWD_SCORE, "at": at},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    item = saved.json()
    created.append(item["id"])
    return item


def _forget_the_recorded_limits(item_id: str) -> None:
    """Make the row look like one saved before the column existed.

    Absent is a third state, distinct from "the defaults" -- db.py deliberately
    adds the column without a DEFAULT so an old row stays absent -- and this is
    the only way to get one without a migration to travel back to.
    """
    with db.engine.begin() as connection:
        connection.execute(
            sql_text("UPDATE history SET render_limits = NULL WHERE id = :id"),
            {"id": item_id},
        )


def _counts(payload: dict) -> list[int]:
    return [
        ins["arrangement"]["count"]
        for ins in payload["instructions"]
        if ins.get("arrangement")
    ]


def _render_score(headers, *, score=None, **body) -> dict:
    response = client.post(
        "/api/render-score",
        json={"score": score or CROWD_SCORE, "input": "群れ", **body},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _notes_for(score: dict, limits: Limits, ddl: str | None = None) -> list[str]:
    """The limit notes the saved-Score seam writes under recorded limits."""
    del ddl
    notes: list[str] = []
    with using_limits(limits):
        coerce_saved_score(score, limits=limits, limit_notes=notes)
    return notes


def _named(notes: list[str]) -> set[str]:
    return {line.split(":", 1)[0] for line in notes if ":" in line}


# --------------------------------------------------------------------------
# T-95  the work's own row decides the redraw
# --------------------------------------------------------------------------


def test_t95_a_work_is_redrawn_under_the_limits_it_was_drawn_under(author, stored_limits):
    """The defect, reproduced and then measured the other way round.

    The work is saved at the defaults, so its row records 120. The setting then
    drops to 60 -- and the redraw names the work, which is the whole of what a
    client has to do. Before this contract the answer came back at 60 with the
    colors restored from the very same row.
    """
    headers, _user, created = author
    item = _save(headers, created)
    assert item["render_limits"]["represented_count_max"] == 120

    stored_limits(LOWERED)

    # A drawing nobody named still follows today's setting -- the control that
    # separates "the row was read" from "the setting never bound at all".
    assert _counts(_render_score(headers)["score"]) == [60]

    redrawn = _render_score(headers, work_id=item["id"])
    assert _counts(redrawn["score"]) == [120], "the redraw must use the work's own ceiling"
    assert redrawn["render_limits_source"] == LIMITS_SOURCE_WORK
    assert redrawn["render_limits"]["represented_count_max"] == 120
    # The two halves of the same row. The colors were already restored from it
    # before this contract; the limits were not, and nothing said so.
    assert redrawn["render_color_source"] == "snapshot"


# --------------------------------------------------------------------------
# T-96  a work with no record says so
# --------------------------------------------------------------------------


def test_t96_a_work_without_a_record_names_its_own_state(author, stored_limits):
    """`work_unrecorded` is not `settings` with extra words.

    Both draw at today's numbers. Only one of them was asked to replay a work
    and could not, and a client that cannot tell them apart cannot tell a
    faithful redraw from a drawing that lost its ceiling.
    """
    headers, _user, created = author
    item = _save(headers, created)
    _forget_the_recorded_limits(item["id"])

    stored_limits(LOWERED)

    redrawn = _render_score(headers, work_id=item["id"])
    assert redrawn["render_limits_source"] == LIMITS_SOURCE_WORK_UNRECORDED
    assert redrawn["render_limits_source"] != LIMITS_SOURCE_SETTINGS
    assert _counts(redrawn["score"]) == [60], "with no record, today's setting draws it"


# --------------------------------------------------------------------------
# T-97  a drawing that names no work says settings
# --------------------------------------------------------------------------


def test_t97_a_drawing_that_names_no_work_is_drawn_at_the_settings(author, stored_limits):
    headers, _user, _created = author
    stored_limits(LOWERED)

    drawn = _render_score(headers)
    assert drawn["render_limits_source"] == LIMITS_SOURCE_SETTINGS
    assert drawn["render_limits_source"] != LIMITS_SOURCE_WORK_UNRECORDED
    assert drawn["render_limits"]["represented_count_max"] == 60


# --------------------------------------------------------------------------
# T-98  the export path was already holding the work
# --------------------------------------------------------------------------


def test_t98_a_non_display_export_draws_under_the_work_limits(author, stored_limits):
    """GET /api/history/{id}/svg?profile=editable, which this contract does not touch.

    It hands `work=item` to `_render_score_svg` already, so wiring the limits
    inside that function is the whole of the change here -- and the claim is
    that it arrived, not that a line was written. The control is a second work
    holding the same picture with its record forgotten: same score, same route,
    same request, and the only difference is the row.
    """
    headers, _user, created = author
    recorded = _save(headers, created, input_text="群れ・記録あり")
    forgotten = _save(headers, created, at=1_785_000_001_000, input_text="群れ・記録なし")
    # Two rows, not one row saved twice: see `_save`.
    assert recorded["id"] != forgotten["id"]
    _forget_the_recorded_limits(forgotten["id"])

    # Lower BOTH: the stored score already carries the represented count, so the
    # per-instruction budget is what decides whether it is touched again at all.
    stored_limits({"represented_count_max": 60, "max_expanded_per_instruction": 100})

    def _export(item_id: str) -> str:
        response = client.get(f"/api/history/{item_id}/svg?profile=editable", headers=headers)
        assert response.status_code == 200, response.text
        return response.text

    under_the_work = _export(recorded["id"])
    under_the_settings = _export(forgotten["id"])
    assert len(under_the_work) > len(under_the_settings), (
        "the recorded work must export more ink than the same picture drawn at "
        "today's lowered settings"
    )


class _Stage1:
    """Stage 1 answering one fixed drawing, so the shared pipeline needs no model."""

    def __init__(self, _options, **_kwargs):
        pass

    def __call__(self, action):
        assert action["tag"] == "generate_normalized_ddl", action["tag"]
        return {
            "tag": "normalized_ddl_generated",
            "identity": action["identity"],
            "response": json.dumps({"normalized_ddl": "中心に黒い円を置く。"}),
            "elapsed_ms": "3",
        }


# --------------------------------------------------------------------------
# T-99  the four paths all name their source
# --------------------------------------------------------------------------


def test_t99_every_render_path_names_the_limits_source(author, monkeypatch):
    """Three response models and one header.

    The header exists because /api/render-svg answers with the picture itself:
    a caller reading the body has nowhere to look, which is the same reason the
    color source rides in a header beside it.
    """
    headers, _user, _created = author

    scored = _render_score(headers)
    assert scored["render_limits_source"] == LIMITS_SOURCE_SETTINGS

    svg = client.post(
        "/api/render-svg",
        json={"score": CROWD_SCORE, "svg_profile": "editable"},
        headers=headers,
    )
    assert svg.status_code == 200, svg.text
    assert svg.headers[LIMITS_SOURCE_HEADER] == LIMITS_SOURCE_SETTINGS

    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", _Stage1)
    painted = client.post("/api/paint", json={"description": "一滴の墨"}, headers=headers)
    assert painted.status_code == 200, painted.text
    assert painted.json()["render_limits_source"] == LIMITS_SOURCE_SETTINGS

    composed = client.post("/api/compose", json={"ddl": "中心に黒い円を置く。"}, headers=headers)
    assert composed.status_code == 200, composed.text
    assert composed.json()["render_limits_source"] == LIMITS_SOURCE_SETTINGS


# --------------------------------------------------------------------------
# T-100  the request outranks the row
# --------------------------------------------------------------------------


def test_t100_the_request_outranks_the_work_row(author):
    """A caller naming limits is naming them for this render, work or no work.

    The other order reads as "the work's ceiling can never be departed from",
    which would leave no way to preview a work under a smaller budget.
    """
    headers, _user, created = author
    item = _save(headers, created)
    assert item["render_limits"]["represented_count_max"] == 120

    redrawn = _render_score(headers, work_id=item["id"], limits={"represented_count_max": 90})
    assert _counts(redrawn["score"]) == [90]
    assert redrawn["render_limits_source"] == LIMITS_SOURCE_REQUEST
    assert redrawn["render_limits"]["represented_count_max"] == 90


# --------------------------------------------------------------------------
# T-101  and cannot outrank the administrator
# --------------------------------------------------------------------------


def test_t101_a_request_cannot_raise_a_limit_the_settings_lowered(author, stored_limits):
    """Element-wise, so one impossible field does not lose the other eight.

    `normalize_limits` rounds only against LIMIT_ABSOLUTE_MAX (100000), and one
    mark measured ~17.9 KB of SVG -- 100,000 of them is about 1.8 GB. The
    administrator's number is the ceiling; the request may only come under it.
    """
    headers, _user, _created = author
    stored_limits(LOWERED)

    drawn = _render_score(headers, limits={"represented_count_max": 240})
    assert _counts(drawn["score"]) == [60], "the setting is the ceiling, not a suggestion"
    assert drawn["render_limits_source"] == LIMITS_SOURCE_REQUEST
    assert drawn["render_limits"]["represented_count_max"] == 60

    # The eight it did not name are still today's numbers, not the defaults of
    # a request that replaced the whole set.
    today = db.get_render_limit_settings()
    for name in LIMIT_FIELD_NAMES:
        if name == "represented_count_max":
            continue
        assert drawn["render_limits"][name] == today[name], name


# --------------------------------------------------------------------------
# T-102  each of the nine names itself when it binds
# --------------------------------------------------------------------------

# One case per limit. Each names the input that makes THAT limit the one doing
# the work -- a single Score in which all nine bind would let one limit hide
# behind another, and the parametrize would then be measuring one thing nine
# times. Where a limit cannot be reached alone it is said so in the comment.
_BINDING_CASES: list[tuple[str, dict, dict, str | None]] = [
    # 65 instructions against a ceiling of 64: the list is cut. Each circle sits
    # somewhere else on purpose -- coerce dedupes identical instructions long
    # before the ceiling runs, and 65 copies of one circle arrive there as one.
    (
        "max_instructions",
        {"max_instructions": 64},
        {
            "instructions": [
                {"primitive": "circle", "center": [0.02 + index * 0.015, 0.5], "radius": 0.02}
                for index in range(65)
            ]
        },
        None,
    ),
    # Two grids the density governors deliberately spare, over the whole-work
    # ceiling: only the hard ceiling at the exit of coerce can bring them back.
    (
        "max_expanded_primitives",
        {"max_expanded_primitives": 120},
        {
            "instructions": [
                {
                    "primitive": "square",
                    "at": {"region": [0.0, 0.0, 1.0, 1.0]},
                    "size": [0.02, 0.02],
                    "arrangement": {"count": 200, "layout": "grid", "rows": 10, "cols": 20},
                }
            ]
        },
        None,
    ),
    # One scatter over the per-instruction budget while the work as a whole
    # stays under the total one.
    (
        "max_expanded_per_instruction",
        {"max_expanded_per_instruction": 100, "max_expanded_primitives": 400},
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "at": {"region": [0.05, 0.05, 0.95, 0.95]},
                    "size": [0.01, 0.01],
                    "arrangement": {"count": 300, "layout": "scatter"},
                }
            ]
        },
        None,
    ),
    # The band's floor, reached by making 0.42 of the crowd fall below it. It
    # necessarily names `represented_count_max` as well -- the ceiling is what
    # turned the tally into a band in the first place -- so the case measures
    # that the floor is named ON TOP of it, and the ceiling case below is the
    # one that shows the floor is not named on every work.
    (
        "represented_count_min",
        {"represented_count_max": 200, "represented_count_min": 180},
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "at": {"region": [0.05, 0.05, 0.95, 0.95]},
                    "size": [0.01, 0.01],
                    "arrangement": {"count": 300, "layout": "scatter"},
                }
            ]
        },
        None,
    ),
    (
        "represented_count_max",
        {"represented_count_max": 60},
        CROWD_SCORE,
        None,
    ),
]


@pytest.mark.parametrize(
    ("name", "setting", "score", "ddl"),
    _BINDING_CASES,
    ids=[case[0] for case in _BINDING_CASES],
)
def test_t102_a_limit_that_takes_effect_names_itself(name, setting, score, ddl):
    limits = Limits(**{**{f: getattr(DEFAULT_LIMITS, f) for f in LIMIT_FIELD_NAMES}, **setting})
    notes = _notes_for(score, limits, ddl)
    assert name in _named(notes), f"{name} bound and did not name itself: {notes}"
    assert any(line.startswith(f"{name}: ") for line in notes), (
        "the name has to lead the line, or a reader cannot tell the nine apart"
    )


# --------------------------------------------------------------------------
# T-103  and stays quiet when it did not
# --------------------------------------------------------------------------


def test_t103_a_limit_that_did_not_take_effect_says_nothing(author):
    """Three works well inside every default, through the route that reports.

    A note written unconditionally would carry the same nine names on every
    drawing, which is the same silence written out longhand.
    """
    headers, _user, _created = author
    for score in (
        {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]},
        {
            "instructions": [
                {"primitive": "line", "at": {"region": [0.1, 0.1, 0.9, 0.9]}},
                {"primitive": "square", "center": [0.5, 0.5], "size": [0.2, 0.2]},
            ]
        },
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "at": {"region": [0.2, 0.2, 0.8, 0.8]},
                    "size": [0.02, 0.02],
                    "arrangement": {"count": 12, "layout": "scatter"},
                }
            ]
        },
    ):
        drawn = _render_score(headers, score=score)
        assert not drawn.get("render_limit_notes"), drawn.get("render_limit_notes")


# --------------------------------------------------------------------------
# T-104  the plugin budget reads the setting
# --------------------------------------------------------------------------


def test_t104_a_new_drawing_runs_under_the_budget_that_is_in_force(
    author, stored_limits, monkeypatch
):
    """The work budget a new drawing is compiled under is today's setting.

    This read the number back out of the plugin warning, which wrote
    `DEFAULT_LIMITS.max_expanded_primitives` into its own text: 400 on an
    installation that had set 100. The warning left with the Python expander
    (2026-09-14); the shared compiler receives the budget itself, so the answer
    says which number drew the work, and a request may lower it but not raise it.
    """
    headers, _user, _created = author
    stored_limits({"max_expanded_primitives": 100})
    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", _Stage1)

    def paint(**body) -> dict:
        painted = client.post("/api/paint", json={"description": "青葉を二十", **body}, headers=headers)
        assert painted.status_code == 200, painted.text
        return painted.json()

    drawn = paint()
    assert drawn["render_limits"]["max_expanded_primitives"] == 100
    assert DEFAULT_LIMITS.max_expanded_primitives != 100
    assert drawn["render_limits_source"] == LIMITS_SOURCE_SETTINGS

    lowered = paint(limits={"max_expanded_primitives": 50})
    assert lowered["render_limits"]["max_expanded_primitives"] == 50
    assert lowered["render_limits_source"] == LIMITS_SOURCE_REQUEST

    raised = paint(limits={"max_expanded_primitives": 900})
    assert raised["render_limits"]["max_expanded_primitives"] == 100
    assert raised["render_limits_source"] == LIMITS_SOURCE_REQUEST


# --------------------------------------------------------------------------
# T-108  the declaration is not a blank cheque
# --------------------------------------------------------------------------


def test_t108_a_second_key_in_a_declared_schema_still_fails_the_surface_gate(monkeypatch):
    """Six schemas were declared to move. Nothing else in them may.

    A declaration written as a bare name -- "this schema is allowed to change"
    -- passes anything that happens inside it afterwards, and the gate
    would then be measuring the schema list rather than the schemas. So the
    surface is doctored with one extra property in one declared schema and the
    gate is required to notice.

    `app.openapi` is replaced rather than the model, because FastAPI settles a
    route's response schema when the route is declared: adding a pydantic field
    at runtime moves nothing (measured 2026-08-16).
    """
    real = app.openapi()

    def doctored() -> dict:
        spec = copy.deepcopy(real)
        spec["components"]["schemas"]["RenderScoreResponse"]["properties"][
            "render_limits_alibi"
        ] = {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Render Limits Alibi"}
        return spec

    monkeypatch.setattr(app, "openapi", doctored)

    # The ACL and card gates left with the legacy decision layers (2026-09-14),
    # and T-8 no longer hashes schema bodies (2026-09-25); every byte of the
    # surface is now measured by the one gate against the recorded baseline.
    gates = [
        ("test_api_surface", "test_api_surface_is_unchanged"),
    ]
    for module_name, test_name in gates:
        # As a sibling in this package, the way the other surface readers
        # import it.
        module = importlib.import_module(f"{__package__}.{module_name}")
        with pytest.raises(AssertionError):
            getattr(module, test_name)()
