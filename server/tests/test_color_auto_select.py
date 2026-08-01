"""Acceptance for the color catalog's automatic selection (ledger I-082).

Stage 1 and Stage 2 are stubbed the way test_api does it: what is under test is
which catalog the paint resolves to, not what the two models write.

The LLM is never reached. Where the *choice* is what matters the real
`select_catalog_id` runs with only `_ask_model` replaced, so that hollowing out
the selector shows up here; where the *number of calls* is what matters the
whole function is replaced by a counter.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import api as api_module
from inku_server import color_selector, db
from inku_server.api import app
from inku_server.color_catalogs import color_catalog_ids, color_catalogs
from inku_server.color_selector import build_catalog_card, select_catalog_id
from inku_server.schema import Score

client = TestClient(app)

DESCRIPTION = "祭りの夜、灯りが水面に散る。"
# Neither of these is `default`, so a fallback that lands on `default` is
# distinguishable from a fallback that keeps what the caller asked for.
REQUESTED = "ink_season"
ANSWERED = "lantern_dew"


@pytest.fixture
def headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"catalog-auto-{suffix}")
    user = db.add_user(
        username=f"catalog-auto-{suffix}",
        email=f"catalog-auto-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


FAKE_SCORE = {
    "instructions": [
        {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1, "color": "black"}
    ]
}


@pytest.fixture(autouse=True)
def stub_stages(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "interpret_detail",
        lambda text, model=None, include_thinking=False: ("中心に黒い円を置く。", None),
    )
    monkeypatch.setattr(
        api_module, "compose", lambda ddl, model=None: Score.model_validate(FAKE_SCORE)
    )


def _paint(headers: dict[str, str], **extra) -> dict:
    body = {
        "description": DESCRIPTION,
        "catalog_id": REQUESTED,
        "count_generation": False,
        **extra,
    }
    response = client.post("/api/paint", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _counting_selector(monkeypatch, *, real: bool) -> list[str]:
    """Replace or wrap the selector so calls can be counted.

    `real=True` keeps the module's own function underneath, so a selector that
    stopped choosing is visible here; `real=False` replaces it outright, which is
    what a control needs.
    """
    calls: list[str] = []

    def counted(source_text: str, *, fallback_id: str) -> str:
        calls.append(source_text)
        if real:
            return select_catalog_id(source_text, fallback_id=fallback_id)
        return ANSWERED

    monkeypatch.setattr(api_module, "select_catalog_id", counted)
    return calls


def _answer(monkeypatch, reply: str) -> None:
    monkeypatch.setattr(color_selector, "_ask_model", lambda text: reply)


# --- the positive control for perturbation (1) -------------------------------
# An identity `select_catalog_id` -- one that always returns fallback_id -- has
# to fail here. The other auto-path assertions are about counts and fallbacks
# and would survive it.


def test_auto_paints_with_the_catalog_the_model_named(monkeypatch, headers):
    _answer(monkeypatch, f'```json\n{{"catalog_id": "{ANSWERED}"}}\n```')
    data = _paint(headers, catalog_mode="auto")
    assert data["render_color_catalog_id"] == ANSWERED
    assert data["catalog_id"] == ANSWERED
    assert data["render_color_map"] == api_module._catalog_render_color_map(ANSWERED)


def test_auto_reads_the_description_not_the_instructions(monkeypatch, headers):
    """The model is handed the raw description.

    Arm B of the stage 0 probe -- normalized DDL -- answered `default` for 52 of
    60 descriptions, so which text arrives is part of the mechanism.
    """
    seen: list[str] = []

    def capture(text: str) -> str:
        seen.append(text)
        return f'{{"catalog_id": "{ANSWERED}"}}'

    monkeypatch.setattr(color_selector, "_ask_model", capture)
    _paint(headers, catalog_mode="auto")
    assert seen == [DESCRIPTION]


# --- T-1 ---------------------------------------------------------------------


def test_t1_fixed_never_reaches_the_selector(monkeypatch, headers):
    """Count the calls.

    Asserting that the returned id equals the requested one is tautological
    here: the fallback returns that same id.
    """
    calls = _counting_selector(monkeypatch, real=False)
    _paint(headers, catalog_mode="fixed")
    assert calls == []


# --- T-2 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        # Measured once in 60 calls on 2026-08-01: a catalog id that does not exist.
        '{"catalog_id": "ink_ink_season"}',
        "",
        "   ",
        "I would suggest something warm.",
        '{"catalog_id": "DROP TABLE works"}',
    ],
)
def test_t2_an_id_outside_the_list_falls_back_to_the_requested_one(monkeypatch, reply):
    _answer(monkeypatch, reply)
    chosen = select_catalog_id(DESCRIPTION, fallback_id=REQUESTED)
    assert chosen == REQUESTED
    assert chosen != "default"


def test_t2_a_failing_call_falls_back_to_the_requested_one(monkeypatch):
    def boom(text: str) -> str:
        raise RuntimeError("provider is down")

    monkeypatch.setattr(color_selector, "_ask_model", boom)
    chosen = select_catalog_id(DESCRIPTION, fallback_id=REQUESTED)
    assert chosen == REQUESTED
    assert chosen != "default"


def test_t2_the_fallback_reaches_the_drawing(monkeypatch, headers):
    _answer(monkeypatch, '{"catalog_id": "ink_ink_season"}')
    data = _paint(headers, catalog_mode="auto")
    assert data["render_color_catalog_id"] == REQUESTED


def test_t2_every_id_in_the_list_is_accepted(monkeypatch):
    """Each real id survives the allowlist, so it refuses names rather than answers."""
    for catalog_id in color_catalog_ids():
        _answer(monkeypatch, f'{{"catalog_id": "{catalog_id}"}}')
        assert select_catalog_id(DESCRIPTION, fallback_id=REQUESTED) == catalog_id


# --- T-3 ---------------------------------------------------------------------


def test_t3_the_card_carries_every_catalog():
    """Adding a catalog to the module has to reach the prompt.

    The card is generated rather than written down, and this is what says so: a
    card built from anything shorter than the whole list fails here.
    """
    card = build_catalog_card()
    catalogs = color_catalogs()
    assert len(catalogs) == 13
    for catalog in catalogs:
        assert catalog["id"] in card
        assert catalog["name"] in card
        assert catalog["sub"] in card
        assert catalog["sub_ja"] in card
        for entry in catalog["palette"]:
            assert str(entry.get("name_ja") or entry["name"]) in card
    # One line per catalog, so a truncated card cannot pass by naming an id in
    # some other line's text.
    assert sum(1 for line in card.splitlines() if line.startswith("- ")) == len(catalogs)


# --- T-4 ---------------------------------------------------------------------


def test_t4_redrawing_a_stored_work_never_chooses_again(monkeypatch, headers):
    _answer(monkeypatch, f'{{"catalog_id": "{ANSWERED}"}}')
    calls = _counting_selector(monkeypatch, real=True)

    painted = _paint(headers, catalog_mode="auto")
    assert painted["render_color_catalog_id"] == ANSWERED
    assert len(calls) == 1

    redrawn = client.post(
        "/api/render-score",
        json={"score": FAKE_SCORE, "catalog_id": painted["render_color_catalog_id"]},
        headers=headers,
    )
    assert redrawn.status_code == 200, redrawn.text
    assert redrawn.json()["catalog_id"] == ANSWERED
    assert len(calls) == 1


# --- T-5 ---------------------------------------------------------------------


def test_t5_a_client_that_sends_no_mode_behaves_as_fixed(monkeypatch, headers):
    calls = _counting_selector(monkeypatch, real=False)
    data = _paint(headers)
    assert calls == []
    assert data["render_color_catalog_id"] == REQUESTED


def test_t5_an_unknown_mode_is_refused(headers):
    response = client.post(
        "/api/paint",
        json={
            "description": DESCRIPTION,
            "catalog_id": REQUESTED,
            "catalog_mode": "shuffle",
            "count_generation": False,
        },
        headers=headers,
    )
    assert response.status_code == 422


# --- T-6 ---------------------------------------------------------------------


def test_t6_refinement_keeps_the_draw(monkeypatch, headers):
    """"Another catalog" exists to see one description in a different color.

    Reading the description would settle on the same catalog every time, which
    is the feature disappearing, so this path stays away from the model.
    """

    def must_not_run(source_text: str, *, fallback_id: str) -> str:
        raise AssertionError("the selector must not run for catalog_mode=random")

    monkeypatch.setattr(api_module, "select_catalog_id", must_not_run)
    data = _paint(headers, catalog_mode="random")
    assert data["render_color_catalog_id"] != REQUESTED
    assert data["render_color_catalog_id"] in color_catalog_ids()


def test_t6_the_draw_reaches_more_than_one_catalog(monkeypatch):
    """A broken draw that always returns the same neighbour would pass a
    single-call test, so ask for several and count the distinct answers."""

    def must_not_run(source_text: str, *, fallback_id: str) -> str:
        raise AssertionError("the selector must not run for catalog_mode=random")

    monkeypatch.setattr(api_module, "select_catalog_id", must_not_run)
    drawn = {
        api_module._resolved_paint_catalog_id(
            REQUESTED, mode="random", source_text=DESCRIPTION
        )
        for _ in range(24)
    }
    assert len(drawn) > 1
    assert REQUESTED not in drawn
