from __future__ import annotations

import base64
import struct
import uuid

from inku_server import db
from inku_server.okugaki import (
    _cached_vision_response,
    _vision_thumbnail_data_url,
    build_fact_sheet,
    build_generation_request,
    deterministic_invariants,
    generate_okugaki,
)

db.init_db()


def _png_size(data_url: str) -> tuple[int, int]:
    png = base64.b64decode(data_url.split(",", 1)[1])
    return struct.unpack(">II", png[16:24])


def test_okugaki_vision_thumbnails_use_bounded_aspect_correct_payloads():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"><rect width="20" height="10" fill="black"/></svg>'
    single = _vision_thumbnail_data_url([svg])
    pair = _vision_thumbnail_data_url([svg, svg])
    assert single is not None and _png_size(single) == (512, 512)
    assert pair is not None and _png_size(pair) == (768, 384)


def test_okugaki_successful_prefix_read_is_cached(monkeypatch):
    monkeypatch.setenv("INKU_OKUGAKI_CACHE_TTL_SECONDS", "1800")
    key = f"test-{uuid.uuid4()}"
    calls = 0

    def generate() -> str:
        nonlocal calls
        calls += 1
        return "cached observation"

    assert _cached_vision_response(key, generate) == "cached observation"
    assert _cached_vision_response(key, generate) == "cached observation"
    assert calls == 1


def _user(prefix: str = "okugaki") -> dict:
    suffix = uuid.uuid4().hex[:10]
    groups = db.list_user_groups()
    return db.add_user(
        f"{prefix}-{suffix}",
        f"{prefix}-{suffix}@example.test",
        "okugaki-test-password",
        "user",
        groups[0]["id"] if groups else None,
    )


def _item(user_id: str, text: str, at: int, **extra) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "input": text,
        "source_text": text,
        "ddl": text,
        "score": {
            "instructions": [{
                "primitive": "circle",
                "color": "black",
                "center": [0.5, 0.5],
                "radius": 0.1,
                "arrangement": {"density": "low", "path": "none"},
            }],
        },
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="2"/></svg>',
        "at": at,
        "render_seed": at,
        "render_build_number": "570",
        "render_engine_id": "default",
        "render_engine_version": "3",
        "render_color_catalog_id": "default",
        **extra,
    }


def test_branch_fact_sheet_handles_lineage_only_and_tombstone():
    user = _user()
    try:
        root = db.add_item(_item(user["id"], "root", 1000))
        hidden = db.add_item(_item(
            user["id"],
            "hidden",
            1001,
            history_visibility="lineage_only",
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="ddl_edit",
        ))
        child = db.add_item(_item(
            user["id"],
            "child",
            1002,
            lineage_parent_node_id=hidden["lineage_node_id"],
            derivation_kind="touch_change",
        ))
        assert db.delete_items(user["id"], [root["id"]]) == 1

        branch = db.get_lineage_branch(user["id"], child["lineage_node_id"])
        assert branch is not None
        assert [node["state"] for node in branch["nodes"]] == ["tombstone", "lineage_only", "active"]
        assert [edge["derivation_kind"] for edge in branch["edges"]] == ["ddl_edit", "touch_change"]
        sheet = build_fact_sheet(branch)
        assert sheet["branch_snapshot"] == [node["id"] for node in branch["nodes"]]
        assert sheet["generations"][0]["features"] is None
        assert sheet["generations"][1]["caption"] == "hidden"
    finally:
        db.delete_all(user["id"])
        assert db.delete_user(user["id"])


def test_invariants_are_deterministic_and_generation_requests_are_prefix_only():
    generations = [
        {"features": {"composition_family": "central_stillness", "primitives": ["circle"], "colors": ["black"], "densities": ["low"], "angles": [], "arrangement_paths": ["none"], "score_elements": ["circle:black:low:none"], "instruction_count": 1}},
        {"features": {"composition_family": "central_stillness", "primitives": ["circle", "line"], "colors": ["black"], "densities": ["low"], "angles": ["horizontal"], "arrangement_paths": ["none"], "score_elements": ["circle:black:low:none", "line:black:low:none"], "instruction_count": 2}},
    ]
    assert deterministic_invariants(generations) == deterministic_invariants(list(generations))
    assert deterministic_invariants(generations)["primitives"] == ["circle"]
    fact_sheet = {"generations": [{"node_id": "root"}, {"node_id": "middle"}, {"node_id": "future"}]}
    request = build_generation_request(fact_sheet, 1, ["root reading", "unused future reading"])
    encoded = str(request)
    assert "root" in encoded and "middle" in encoded
    assert "future" not in encoded
    assert request["prior_observations"] == ["root reading"]


def test_generate_signs_mechanically_and_storage_is_append_only_scoped_and_idempotent():
    user = _user()
    other = _user("other-okugaki")
    try:
        root = db.add_item(_item(user["id"], "root", 2000))
        child = db.add_item(_item(
            user["id"],
            "child",
            2001,
            lineage_parent_node_id=root["lineage_node_id"],
            derivation_kind="layout_change",
        ))
        before = db.get_items(user["id"], [child["id"]])[0]
        branch = db.get_lineage_branch(user["id"], child["lineage_node_id"])
        assert branch is not None
        calls = []

        def reader(**kwargs):
            calls.append(kwargs)
            return "画像は左が前世代、右が現世代です。両者の見える差を読んでください。\n\n黒い円が留まって見える。"

        generated = generate_okugaki(
            branch,
            model="test/vision",
            language="ja",
            settings={},
            reader=reader,
            at=1_700_000_000_000,
        )
        assert generated["body"].endswith("読み手: test/vision / 2023-11-15")
        assert generated["body"].startswith("私には、黒い円が留まって見える。")
        assert len(calls) == 3
        assert all(len(call.get("images", [])) <= 1 for call in calls)
        assert calls[1]["images"][0].startswith("data:image/png;base64,")
        first = db.add_okugaki(user["id"], generated, idempotency_key="same-key")
        replay = db.add_okugaki(user["id"], generated, idempotency_key="same-key")
        second = db.add_okugaki(user["id"], {**generated, "at": generated["at"] + 1})
        assert first["id"] == replay["id"]
        assert [item["id"] for item in db.list_okugaki(user["id"], child["lineage_node_id"])] == [first["id"], second["id"]]
        assert db.list_okugaki(other["id"], child["lineage_node_id"]) == []
        assert not db.delete_okugaki(other["id"], first["id"])
        assert db.delete_okugaki(user["id"], first["id"])
        after = db.get_items(user["id"], [child["id"]])[0]
        assert before["description_hash"] == after["description_hash"]
        assert before["render_hash"] == after["render_hash"]
    finally:
        db.delete_all(user["id"])
        db.delete_all(other["id"])
        assert db.delete_user(user["id"])
        assert db.delete_user(other["id"])


# --- 奥書の道は colophon で通る (v2.8.0) -------------------------------------


def test_the_routes_say_colophon_and_no_longer_say_okugaki():
    """**API パスは `colophon`。ローマ字のパスは残していない**（作者裁定 2026-07-27）。

    語を運んでいたのはパスだけである — `OkugakiItem` の応答フィールドに
    `okugaki` という名前のものは一つも無い。したがって改名はパスで閉じる。

    **DB のテーブル名・列名・`model_settings` の `okugaki_model` は動かさない。**
    辞書 §6 が識別子を範囲の外に置いており、保存済みデータに触れるため。
    """
    from fastapi.routing import iter_route_contexts

    from inku_server.api import app

    # fastapi 0.141 no longer flattens included routers into app.routes, so read
    # the paths through iter_route_contexts (measured 2026-08-02: 81 -> 0).
    paths = {
        ctx.path
        for ctx in iter_route_contexts(app.routes)
        if (ctx.path or "").startswith("/api/")
    }
    assert len(paths) > 50, "route enumeration went empty; the gate below would be vacuous"
    assert "/api/lineage/{node_id}/colophon" in paths
    assert "/api/colophon/{colophon_id}" in paths
    assert not [path for path in paths if "okugaki" in path], "ローマ字のパスが残っている"
