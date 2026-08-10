"""The derivation kinds the server accepts and the kinds the web client sends.

[I-137]: the web client has sent `sketch_grain_change` since v2.9.37 and the
server did not know the name, so `db.add_item` raised and the whole save was
lost -- the work reached neither the history nor the lineage. The existing
acceptance test walks `db.LINEAGE_DERIVATION_KINDS` itself, so it stays green
whatever that set contains; nothing compared the two lists.

The gates here are the comparison it was missing, in both directions: the names
are written out rather than read from the product, and the client's list is
parsed out of its own source.
"""

from __future__ import annotations

import pathlib
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app

client = TestClient(app)

ROOT = pathlib.Path(__file__).resolve().parents[2]
WEB_DERIVATION = ROOT / "web/src/lib/derivation.ts"
web_tree_only = pytest.mark.skipif(not WEB_DERIVATION.is_file(), reason="web/ is absent")

# Written out, not imported: a kind dropped from the product has to show up here
# as a failure. Keep sorted.
EXPECTED_KINDS = {
    "age_change",
    "canvas_aspect_change",
    "catalog_change",
    "ddl_edit",
    "description_edit",
    "external_seed_change",
    "hacho_change",
    "language_comparison",
    "layout_change",
    "model_comparison",
    "reinterpretation",
    "render_engine_change",
    "renga_reply",
    "replay",
    "sketch_grain_change",
    "touch_change",
    "variation",
}

# Kinds the server names but no web screen sends. Four are reserved for
# operations that do not exist yet on either side (`hacho` / `renga` / `age`
# have no implementation anywhere); `render_engine_change` and
# `external_seed_change` are written by other paths.
RESERVED_WITHOUT_A_WEB_SENDER = {
    "age_change",
    "external_seed_change",
    "hacho_change",
    "render_engine_change",
    "renga_reply",
}


def _web_client_kinds() -> set[str]:
    """The `DerivationKind` union in `web/src/lib/derivation.ts`.

    Read from the union rather than from the label tables: the union is what
    the submit path is typed against, and a kind can reach the wire before
    anyone gives it a label.
    """
    source = WEB_DERIVATION.read_text(encoding="utf-8")
    match = re.search(r"export type DerivationKind\s*=(.*?);", source, re.S)
    assert match, "the DerivationKind union moved; this gate reads it by name"
    kinds = set(re.findall(r"'([a-z_]+)'", match.group(1)))
    assert len(kinds) > 5, f"parsed too few kinds out of the union: {sorted(kinds)}"
    return kinds


def test_the_server_accepts_exactly_the_seventeen_named_kinds():
    assert db.LINEAGE_DERIVATION_KINDS == EXPECTED_KINDS


@web_tree_only
def test_the_server_knows_every_kind_the_web_client_can_send():
    """The defect [I-137] recorded: a name on the wire the server rejects."""
    unknown = _web_client_kinds() - db.LINEAGE_DERIVATION_KINDS
    assert not unknown, (
        f"the web client sends {sorted(unknown)}, which db.add_item rejects; "
        "every save that names one is lost"
    )


@web_tree_only
def test_the_kinds_with_no_web_sender_are_the_ones_held_in_reserve():
    """The other direction, so a kind cannot be added to the server unnoticed.

    Without this, `test_the_server_knows_every_kind...` alone is satisfied by a
    server list that grows without limit.
    """
    assert db.LINEAGE_DERIVATION_KINDS - _web_client_kinds() == RESERVED_WITHOUT_A_WEB_SENDER


def _user() -> dict:
    suffix = uuid.uuid4().hex[:10]
    group = db.list_user_groups()[0]
    return db.add_user(
        f"kind-parity-{suffix}",
        f"kind-parity-{suffix}@example.test",
        "kind-parity-password",
        ["users"],
        group["id"],
    )


def _payload(at: int, **extra) -> dict:
    payload = {
        "input": "写生の区切りを変えて描き直す",
        "ddl": "中心に円",
        "score": {"instructions": []},
        "svg": "<svg/>",
        "at": at,
    }
    payload.update(extra)
    return payload


def test_a_regrained_redraw_is_saved_and_writes_the_edge():
    """The behaviour the missing name cost, measured through the save endpoint.

    `POST /api/history` is the route the describe tab uses, so this fails the
    way the author's browser failed rather than the way the set does.
    """
    user = _user()
    token = db.create_session(user["id"])
    headers = {"Authorization": f"Bearer {token}"}
    try:
        root = client.post(
            "/api/history",
            json=_payload(1_700_000_000_000, sketch_grain="fine"),
            headers=headers,
        )
        assert root.status_code == 200
        parent_node_id = root.json()["lineage_node_id"]

        child = client.post(
            "/api/history",
            json=_payload(
                1_700_000_001_000,
                sketch_grain="coarse",
                lineage_parent_node_id=parent_node_id,
                derivation_kind="sketch_grain_change",
            ),
            headers=headers,
        )
        assert child.status_code == 200, child.text

        graph = client.get(
            f"/api/lineage/{child.json()['lineage_node_id']}", headers=headers
        )
        assert graph.status_code == 200
        edges = graph.json()["edges"]
        assert [edge["derivation_kind"] for edge in edges] == ["sketch_grain_change"]
    finally:
        db.delete_session(token)
        db.delete_all(user["id"])
        assert db.delete_user(user["id"])
