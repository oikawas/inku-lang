"""Which facts the history strip prints is the reader's setting, stored per account.

The distinction this file exists to hold is between an absent value and an empty
list. An account that predates the column has never answered and takes the
default; a reader who unticked all four has answered, and the answer is
"nothing". Fold the two together and "print nothing under the picture" becomes a
setting that cannot be saved -- it comes back as the default on the next load,
and every happy-path test still passes.

The web half of this pair is web/src/lib/historyStripFields.ts.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app


client = TestClient(app)


def _user() -> tuple[dict, dict[str, str], str, str]:
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"strip-fields-group-{suffix}")
    user = db.add_user(
        username=f"strip-fields-{suffix}",
        email=f"strip-fields-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return user, {"Authorization": f"Bearer {token}"}, token, group["id"]


@pytest.fixture
def account():
    user, headers, token, group_id = _user()
    try:
        yield {"id": user["id"], "headers": headers}
    finally:
        db.delete_all(user["id"])
        db.delete_session(token)
        db.delete_user(user["id"])
        db.delete_user_group(group_id)


def _save(headers: dict[str, str], fields) -> dict:
    response = client.patch(
        "/api/auth/me/settings",
        headers=headers,
        json={"history_strip_fields": fields},
    )
    return response


def test_t153_an_account_that_never_answered_gets_what_the_strip_printed_before(account):
    """T-153  the default is the old fixed pair, so no existing strip moves"""
    response = client.get("/api/auth/me", headers=account["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["history_strip_fields"] == ["generation", "model"]


def test_t154_an_empty_choice_is_stored_as_an_empty_choice(account):
    """T-154  "nothing under the picture" survives a save and a reload

    This is the one the default would eat. If the empty list were read as an
    absence anywhere on the way down -- the PATCH body, the column, the read
    back -- the reader would tick nothing, see nothing, reload, and find the
    generation and the model printed again.
    """
    saved = _save(account["headers"], [])
    assert saved.status_code == 200, saved.text
    assert saved.json()["history_strip_fields"] == []

    reloaded = client.get("/api/auth/me", headers=account["headers"])
    assert reloaded.json()["history_strip_fields"] == []


def test_t155_the_declared_order_is_restored_whatever_order_they_were_ticked(account):
    """T-155  the strip reads the same however the reader got there"""
    saved = _save(account["headers"], ["bytes", "generation"])
    assert saved.status_code == 200, saved.text
    assert saved.json()["history_strip_fields"] == ["generation", "bytes"]


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param(["generation", "model", "bytes"], id="three-at-once"),
        pytest.param(["generation", "generation"], id="the-same-one-twice"),
        pytest.param(["nope"], id="a-field-that-does-not-exist"),
        pytest.param("generation", id="not-a-list"),
    ],
)
def test_t156_a_request_the_control_cannot_make_is_refused_not_trimmed(account, fields):
    """T-156  a bad request is refused, so no unmade choice reaches the strip

    Trimming three down to two would put a pair on screen that nobody picked,
    and the reader's only clue would be the strip itself.
    """
    assert _save(account["headers"], fields).status_code in (400, 422)


def test_t157_a_refused_request_leaves_the_stored_choice_alone(account):
    """T-157  the refusal is not a write

    A validation that raised after the row was touched would leave the account
    holding half of a request that was rejected.
    """
    assert _save(account["headers"], ["bytes"]).status_code == 200
    assert _save(account["headers"], ["generation", "model", "bytes"]).status_code in (400, 422)
    assert client.get("/api/auth/me", headers=account["headers"]).json()["history_strip_fields"] == ["bytes"]


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        pytest.param(None, ["generation", "model"], id="absent-takes-the-default"),
        pytest.param([], [], id="empty-stays-empty"),
        pytest.param("generation", ["generation", "model"], id="not-a-list-is-an-absence"),
        pytest.param(["bytes", "nope"], ["bytes"], id="unknown-names-drop"),
        pytest.param(["bytes", "bytes"], ["bytes"], id="repeats-collapse"),
        pytest.param(["bytes", "generation"], ["generation", "bytes"], id="declared-order-restored"),
    ],
)
def test_t158_the_normaliser_tells_an_absence_from_an_empty_choice(stored, expected):
    """T-158  the rule itself, without the round trip"""
    assert db.normalize_history_strip_fields(stored) == expected


def test_t162_the_listing_sends_each_works_weight_even_when_it_withholds_the_picture(account):
    """T-162  svg_bytes survives include_svg=false

    The strip asks for the listing without the pictures -- twenty-one works are
    23.5 MB with them and 163 KB without. A client that counted the bytes it
    received would therefore report every work as 0 B, which is what the file
    size column did until this field existed. The count is taken while the
    picture is still in hand.
    """
    svg = "<svg xmlns='http://www.w3.org/2000/svg'>" + ("<path d='M 0 0 L 9 9'/>" * 40) + "</svg>"
    db.add_item({
        "id": str(uuid.uuid4()),
        "user_id": account["id"],
        "at": 5_000_000,
        "input": "重さのある作品",
        "source_text": "重さのある作品",
        "ddl": "背景を白で埋める。",
        "score": {"canvas": "square", "instructions": []},
        "svg": svg,
        "history_visibility": "normal",
    })
    expected = len(svg.encode("utf-8"))

    withheld = client.get(
        "/api/history",
        headers=account["headers"],
        params={"limit": 5, "include_svg": "false"},
    ).json()["items"][0]
    assert withheld["svg"] == "", "this test is not exercising the withholding path"
    assert withheld["svg_bytes"] == expected

    carried = client.get(
        "/api/history",
        headers=account["headers"],
        params={"limit": 5, "include_svg": "true"},
    ).json()["items"][0]
    # The same number by the same definition whichever way it was asked for.
    assert carried["svg_bytes"] == expected == len(carried["svg"].encode("utf-8"))
