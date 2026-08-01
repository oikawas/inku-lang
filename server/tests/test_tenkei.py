"""v1.96 添景水準 (tenkei) と 2a ガード回復のテスト。

- Stage 1.5: plugin_instructions_present ガード / none / sparse の決定的写像
- coerce: 添景系挿入 7 分岐の none/sparse ゲート（auto は現行不変）
- 純明示バイパス判定と /api/interpret の Stage 1 バイパス
- Stage 1 プロンプトの水準規範文
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.coerce import coerce_score
from inku_server.ddl_expander import expand_intermediate_ddl
from inku_server.interpreter import _build_system_prompt
from inku_server.plugins import DOCUMENT_PLUGIN_MANAGER
from inku_server.plugins.document_format import PluginDocumentManager
from inku_server.schema import Score

client = TestClient(app)

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "minimal-arcs.inku-plugin.md"

# Stage 1.5 のプール追加が発火しやすい DDL（円・散らす・葉 のトリガ語を含む）
TRIGGER_DDL = "赤い円を三つ置く。小さな点を画面全体に散らす。"


def _sentence_count(ddl: str) -> int:
    return len([s for s in ddl.replace("\n", "。").split("。") if s.strip()])


# --- Stage 1.5 ---


def test_stage15_plugin_instructions_guard_suppresses_additions():
    base = expand_intermediate_ddl(TRIGGER_DDL, lang="ja", context_text=TRIGGER_DDL)
    guarded = expand_intermediate_ddl(
        TRIGGER_DDL,
        lang="ja",
        context_text=TRIGGER_DDL,
        plugin_instructions_present=True,
    )
    assert _sentence_count(base) > _sentence_count(TRIGGER_DDL)
    assert guarded == TRIGGER_DDL


def test_stage15_tenkei_none_keeps_focal_rewrite_only():
    ddl = "中央に赤い円を三つ置く。小さな点を画面全体に散らす。"
    none_out = expand_intermediate_ddl(ddl, lang="ja", context_text=ddl, tenkei="none")
    assert _sentence_count(none_out) == _sentence_count(ddl)
    # 焦点書き換え（中央→動的焦点）は none でも維持される
    assert "中央" not in none_out


def test_stage15_tenkei_sparse_caps_additions_to_one():
    base = expand_intermediate_ddl(TRIGGER_DDL, lang="ja", context_text=TRIGGER_DDL)
    sparse = expand_intermediate_ddl(
        TRIGGER_DDL, lang="ja", context_text=TRIGGER_DDL, tenkei="sparse"
    )
    original = _sentence_count(TRIGGER_DDL)
    assert _sentence_count(base) >= _sentence_count(sparse)
    # sparse は追加候補 1 つまで。1 候補は最大 2 文（例: 「…並べる。横長にする。」）
    assert _sentence_count(sparse) <= original + 2


def test_stage15_tenkei_auto_unchanged():
    assert expand_intermediate_ddl(
        TRIGGER_DDL, lang="ja", context_text=TRIGGER_DDL
    ) == expand_intermediate_ddl(
        TRIGGER_DDL, lang="ja", context_text=TRIGGER_DDL, tenkei="auto"
    )


# --- coerce ---

GATED_BRANCHES = (
    "with_composition_diversity_repair",
    "with_context_energy_repair",
    "with_surface_tension",
    "with_motion_floor",
    "with_visual_event",
    "with_focal_event_floor",
)

# 添景系挿入（B10 composition_diversity）が発火する文脈と最小 Score（実測で選定）
SCENERY_DDL = "緑の小さな楕円を三つ置く。ゆっくり揺れる。"


def _minimal_score() -> Score:
    return Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.06, 0.03],
                    "color": "green",
                    "weight": "pen",
                    "arrangement": {"count": 3, "layout": "scatter"},
                }
            ],
        }
    )


def test_coerce_tenkei_none_blocks_scenery_insertions():
    auto_counts: dict[str, int] = {}
    auto = coerce_score(_minimal_score(), ddl=SCENERY_DDL, branch_report=auto_counts)
    none_counts: dict[str, int] = {}
    none = coerce_score(
        _minimal_score(), ddl=SCENERY_DDL, branch_report=none_counts, tenkei="none"
    )
    assert sum(auto_counts.get(b, 0) for b in GATED_BRANCHES) > 0
    assert sum(none_counts.get(b, 0) for b in GATED_BRANCHES) == 0
    assert len(none.instructions) <= len(auto.instructions)
    # 修復系（フィールド補修）は none でも動く
    assert "coerce_and_repair_instruction" in none_counts


def test_coerce_tenkei_sparse_allows_at_most_one_insertion():
    sparse_counts: dict[str, int] = {}
    sparse = coerce_score(
        _minimal_score(), ddl=SCENERY_DDL, branch_report=sparse_counts, tenkei="sparse"
    )
    none_result = coerce_score(_minimal_score(), ddl=SCENERY_DDL, tenkei="none")
    assert len(sparse.instructions) <= len(none_result.instructions) + 1


def test_coerce_tenkei_auto_is_current_behavior():
    a = coerce_score(_minimal_score(), ddl=SCENERY_DDL)
    b = coerce_score(_minimal_score(), ddl=SCENERY_DDL, tenkei="auto")
    assert [i.model_dump(by_alias=True) for i in a.instructions] == [
        i.model_dump(by_alias=True) for i in b.instructions
    ]


def test_coerce_plugin_present_gates_complex_motif_on_none():
    # 「葉」モチーフ marker で B9 が発火する DDL。プラグイン転写済みなら none でゲート
    ddl = "緑の葉を三枚置く。"
    auto_counts: dict[str, int] = {}
    coerce_score(_minimal_score(), ddl=ddl, branch_report=auto_counts)
    gated_counts: dict[str, int] = {}
    coerce_score(
        _minimal_score(),
        ddl=ddl,
        branch_report=gated_counts,
        tenkei="none",
        plugin_instructions_present=True,
    )
    if auto_counts.get("with_complex_motif_repair", 0) > 0:
        assert gated_counts.get("with_complex_motif_repair", 0) == 0


# --- 純明示バイパス判定 ---


def test_is_pure_invocation(tmp_path):
    manager = PluginDocumentManager(directory=tmp_path)
    (tmp_path / FIXTURE.name).write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    manager.reload(force=True)
    assert manager.is_pure_invocation("Sketch.双弧") is True
    assert manager.is_pure_invocation("Sketch.双弧。") is True
    assert manager.is_pure_invocation("  Sketch.双弧 、 Sketch.双弧 ") is True
    assert manager.is_pure_invocation("小さなSketch.双弧") is False
    assert manager.is_pure_invocation("円を置く") is False
    assert manager.is_pure_invocation("") is False


# --- Stage 1 プロンプト規範 ---


def test_stage1_prompt_tenkei_norms():
    auto_prompt = _build_system_prompt("赤い円", lang="ja")
    none_prompt = _build_system_prompt("赤い円", lang="ja", tenkei="none")
    sparse_prompt = _build_system_prompt("赤い円", lang="ja", tenkei="sparse")
    assert "添景の抑制" not in auto_prompt
    assert "この生成の指定: なし" in none_prompt
    assert "この生成の指定: 控えめ" in sparse_prompt
    en_none = _build_system_prompt("a red circle", lang="en", tenkei="none")
    assert "Scenery suppression" in en_none


# --- API: /api/interpret の純明示バイパス（LLM 呼び出しなしで完結） ---


@pytest.fixture
def plugin_dir(tmp_path):
    original = DOCUMENT_PLUGIN_MANAGER.directory
    DOCUMENT_PLUGIN_MANAGER.directory = tmp_path
    (tmp_path / FIXTURE.name).write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    DOCUMENT_PLUGIN_MANAGER.reload(force=True)
    yield tmp_path
    DOCUMENT_PLUGIN_MANAGER.directory = original
    DOCUMENT_PLUGIN_MANAGER.reload(force=True)


@pytest.fixture
def user_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"tenkei-{suffix}")
    user = db.add_user(
        username=f"tenkei-{suffix}",
        email=f"tenkei-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return {"Authorization": f"Bearer {token}"}


def test_api_interpret_pure_invocation_bypasses_stage1(plugin_dir, user_headers):
    r = client.post(
        "/api/interpret",
        headers=user_headers,
        json={"description": "Sketch.双弧", "tenkei": "none"},
    )
    assert r.status_code == 200
    assert r.json()["ddl"] == "Sketch.双弧"


def test_api_interpret_rejects_invalid_tenkei(plugin_dir, user_headers):
    r = client.post(
        "/api/interpret",
        headers=user_headers,
        json={"description": "Sketch.双弧", "tenkei": "loud"},
    )
    assert r.status_code == 422


# --- v1.97: 作品ごとの保存と親継承 ---


def _history_item(user_id: str, at: int, **extra) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "input": "根",
        "source_text": "根",
        "ddl": "中心に黒い円を置く。",
        "score": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]},
        "svg": "<svg/>",
        "at": at,
        "render_seed": 1,
        "render_build_number": "605",
        "render_engine_id": "default",
        "render_engine_version": "3",
        "render_color_catalog_id": "default",
        **extra,
    }


@pytest.fixture
def db_user():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"tenkei-db-{suffix}")
    user = db.add_user(
        username=f"tenkei-db-{suffix}",
        email=f"tenkei-db-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    yield user
    db.delete_all(user["id"])
    db.delete_user(user["id"])


def test_tenkei_persists_on_history_and_resolves_for_node(db_user):
    root = db.add_item(_history_item(db_user["id"], 3000, tenkei="none"))
    assert root["tenkei"] == "none"
    assert db.tenkei_for_node(db_user["id"], root["lineage_node_id"]) == "none"

    # 未記録の作品 (保存開始前相当) は None
    legacy = db.add_item(_history_item(db_user["id"], 3001))
    assert "tenkei" not in legacy
    assert db.tenkei_for_node(db_user["id"], legacy["lineage_node_id"]) is None


def test_resolved_tenkei_precedence(db_user):
    from inku_server.api_core.rendering import _resolved_tenkei

    root = db.add_item(_history_item(db_user["id"], 3100, tenkei="none"))
    node_id = root["lineage_node_id"]
    actor = {"id": db_user["id"]}

    # 明示値 > 継承 > auto
    assert _resolved_tenkei("sparse", actor, node_id) == "sparse"
    assert _resolved_tenkei(None, actor, node_id) == "none"
    assert _resolved_tenkei(None, actor, None) == "auto"
    assert _resolved_tenkei(None, actor, "missing-node") == "auto"


def test_history_post_inherits_tenkei_from_parent(db_user, plugin_dir):
    token = db.create_session(db_user["id"])
    headers = {"Authorization": f"Bearer {token}"}
    root = db.add_item(_history_item(db_user["id"], 3200, tenkei="none"))

    r = client.post(
        "/api/history",
        headers=headers,
        json={
            "input": "枝",
            "score": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]},
            "at": 3201,
            "lineage_parent_node_id": root["lineage_node_id"],
            "derivation_kind": "touch_change",
        },
    )
    assert r.status_code == 200
    saved = r.json()
    assert saved["tenkei"] == "none"
    # 保存された派生作品からさらに継承できる（renderer 専用派生でも途切れない）
    assert db.tenkei_for_node(db_user["id"], saved["lineage_node_id"]) == "none"
