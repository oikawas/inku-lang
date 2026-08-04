"""記述は作品の出自である -- 契約 tasks/description-is-the-origin.md.

T-1 (削って空になった記述は 400)、T-2 (compose の対の表明)、T-3 (本物の記述は
止めない)、T-5 (種の連鎖から写生文が落ちた)、T-6 (逆向き: 種は効く)、
T-9 (CLI の DDL モードと web の指示書新規作成が同じ形)。
T-4 は web/src/routes/description-gate.test.ts、T-7 / T-8 は cli/tests/test_cli.py。

The gates run through the routes, not through the predicates: judging
``pipeline_description`` on its own would pass while no route consulted it.
T-5 / T-6 enter the expansion layer by its own entry function, because that is
where the chain lives -- the corpus never reaches it (契約 §0.4).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.api_core.routers import render as render_routes
from inku_server.plugins.document_format import DOCUMENT_PLUGIN_MANAGER
from inku_server.schema import Score

client = TestClient(app)

REPO = Path(__file__).resolve().parents[2]

SCORE = Score.model_validate(
    {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
)

# Every one of these survives request validation (min_length=1) and comes back
# empty from the cut. They are the shapes an author actually types: a batch
# line's numbering, a source note in brackets of either width.
LABEL_ONLY = [
    "1. ",
    "[note]",
    "［疎  紀友則 / 古今和歌集（春下）］",
    "12) ",
    "３．",
]

# The same shapes with a description attached -- the form the production rows
# take (契約 §0.2: 14 of 2,023 works carry a label, none of them empty after it).
LABELLED_BUT_REAL = [
    "1. 水面に光",
    "[demo] 一滴の墨",
    "［疎  紀友則 / 古今和歌集（春下）］ 花の散るらむ",
    "12) 岸の下草がゆれている",
    "３．夜である",
]


@pytest.fixture
def auth():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"origin-{suffix}")
    user = db.add_user(
        username=f"origin-{suffix}",
        email=f"origin-{suffix}@example.test",
        password="password-123",
        role="user",
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


def _paint_body(description: str) -> dict:
    return {
        "description": description,
        "sketch": False,
        "save_history": False,
        "save_artifacts": False,
        "count_generation": False,
    }


# --------------------------------------------------------------------- T-1
# 3 routes x 5 shapes. The two paint routes share one generator, but they are
# asked separately: the stream commits its response at the first event, so a
# guard that reached only the non-streaming route would leave the other one
# painting from an empty string and answering 200.

@pytest.mark.parametrize("description", LABEL_ONLY)
def test_t1_interpret_refuses_a_description_that_the_cut_empties(auth, wired, description):
    r = client.post(
        "/api/interpret", json={"description": description, "sketch": False}, headers=auth
    )
    assert r.status_code == 400, description
    assert r.json()["detail"] == "description is only labels"


@pytest.mark.parametrize("description", LABEL_ONLY)
def test_t1_paint_refuses_a_description_that_the_cut_empties(auth, wired, description):
    r = client.post("/api/paint", json=_paint_body(description), headers=auth)
    assert r.status_code == 400, description
    assert r.json()["detail"] == "description is only labels"


@pytest.mark.parametrize("description", LABEL_ONLY)
def test_t1_paint_stream_refuses_a_description_that_the_cut_empties(auth, wired, description):
    r = client.post("/api/paint/stream", json=_paint_body(description), headers=auth)
    # A real status, not an in-band error event: nothing has been written yet,
    # so this route answers like the other two.
    assert r.status_code == 400, description
    assert r.json()["detail"] == "description is only labels"


# --------------------------------------------------------------------- T-2

def test_t2_compose_still_draws_an_instruction_sheet_with_no_description(auth, wired):
    """対の表明。**これが無いと「記述が空なら全部 400」が T-1 を通ってしまう。**

    web の「指示書を新規作成」(`drawNewDdl` -> `composeOne(nextDdl, '')`) と
    `inku-cli paint "<DDL>" --input-mode ddl` はどちらも記述を持たない。
    `ComposeRequest.description` が任意なのは仕様であって穴ではない (契約 §0.3)。
    """
    r = client.post(
        "/api/compose",
        json={"ddl": "黒い円を中心に置く。", "description": "", "save_history": False},
        headers=auth,
    )
    assert r.status_code == 200
    assert "<svg" in r.json()["svg"]


def test_t2_compose_draws_when_the_description_key_is_absent(auth, wired):
    """CLI の形。鍵ごと欠落しても 200 で絵が返る。"""
    r = client.post(
        "/api/compose",
        json={"ddl": "黒い円を中心に置く。", "save_history": False},
        headers=auth,
    )
    assert r.status_code == 200
    assert "<svg" in r.json()["svg"]


def test_t2_compose_draws_a_label_only_description_it_is_handed(auth, wired):
    """compose には番人を入れていない。**入れると上の 2 つが壊れる。**"""
    r = client.post(
        "/api/compose",
        json={"ddl": "黒い円を中心に置く。", "description": "[note]", "save_history": False},
        headers=auth,
    )
    assert r.status_code == 200


# --------------------------------------------------------------------- T-3

@pytest.mark.parametrize("description", LABELLED_BUT_REAL)
def test_t3_a_labelled_description_that_keeps_its_body_is_painted(auth, wired, description):
    """番人は本物の記述を止めない。**本番 2,023 件はこの形しか持っていない。**"""
    r = client.post("/api/paint", json=_paint_body(description), headers=auth)
    assert r.status_code == 200, description


@pytest.mark.parametrize("description", LABELLED_BUT_REAL)
def test_t3_interpret_accepts_a_labelled_description_that_keeps_its_body(auth, wired, description):
    r = client.post(
        "/api/interpret", json={"description": description, "sketch": False}, headers=auth
    )
    assert r.status_code == 200, description


def test_t3_the_guard_reads_both_the_raw_text_and_the_cut(auth, wired):
    """2 条件であることの表明。片方だけを見る実装は、ここで裏返る。

    `req.description` の非空を見ない実装 (削り後だけを見る) は、空白だけの記述を
    「番号と括弧だけ」と答えて 400 にする -- 作者が書いていない札を名指しする文言
    になる。削り後を見ない実装 (生だけを見る) は `[note]` を通してしまう。
    """
    # Raw non-empty + cut empty -> refused.
    assert client.post("/api/paint", json=_paint_body("[note]"), headers=auth).status_code == 400
    # Raw whitespace only -> the cut is empty too, but no label was written, so
    # this is not the condition the message describes and it is not refused here.
    assert client.post("/api/paint", json=_paint_body("   "), headers=auth).status_code == 200
    # Raw non-empty + cut non-empty -> painted.
    assert client.post("/api/paint", json=_paint_body("[note] 水面に光"), headers=auth).status_code == 200


# --------------------------------------------------------------------- T-5 / T-6
# The seed chain, entered through the expansion layer's own entry function.
# The frozen corpora never reach it (契約 §0.4), so they cannot stand in.

DDL = "黒い鉛筆の細い弧を下域に置く。"
PROSE = "岸に下草がある。下草は細い。"          # Stage 0.5 rewrites this every run
DESCRIPTION_A = "岸の下草がゆれている"
DESCRIPTION_B = "線"


def _expanded(seed_text):
    result = DOCUMENT_PLUGIN_MANAGER.expand(DDL, source_text=PROSE, lang="ja", seed_text=seed_text)
    digest = hashlib.sha256(
        json.dumps(list(result.instructions), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:12]
    return len(result.instructions), digest


def test_t5_an_empty_seed_falls_to_the_ddl_and_not_to_the_sketch_prose():
    """段 3。**写生文は種ではない** -- Stage 0.5 が毎回書き直すので、そこへ落ちると
    「同じ記述なら同じ数」が何も赤くならずに失われる。

    実測 (2026-08-04): 空 -> 16 要素 (DDL の値)。段 3 の前は 14 要素 (写生文の値)
    だった。摂動は `document_format.py` の連鎖に当てる -- 呼び出し側の
    `render.py` の `or ddl` に当てると、同じ性質の 2 箇所目に吸収される。
    """
    on_the_ddl = _expanded(DDL)
    on_the_prose = _expanded(PROSE)

    assert on_the_ddl != on_the_prose, "この入力では種の違いが出ない: 検査が空振りしている"
    for empty in ("", None):
        assert _expanded(empty) == on_the_ddl, f"種 {empty!r} が DDL の値へ落ちていない"
        assert _expanded(empty) != on_the_prose, f"種 {empty!r} が写生文へ落ちている"


def test_t6_a_seed_that_was_given_is_the_seed_that_is_used():
    """逆向き。**「空なら DDL」だけの表明は、種を無視して常に DDL を使う実装を通す。**

    同じ DDL・同じ写生文で記述だけを変えると要素数が変わる (実測: 10 と 6)。
    不変性の表明は逆向きと対で据える。
    """
    a = _expanded(DESCRIPTION_A)
    b = _expanded(DESCRIPTION_B)
    on_the_ddl = _expanded(DDL)

    assert a != b, "違う種が同じ結果になっている: 種が読まれていない"
    assert a != on_the_ddl and b != on_the_ddl, "渡した種が DDL の落ち先に潰れている"
    assert (a[0], b[0]) == (10, 6)


# --------------------------------------------------------------------- T-9

def test_t9_the_cli_ddl_mode_and_the_web_new_sheet_send_the_same_shape():
    """どちらの入口も記述を持たない -- CLI は鍵ごと欠落、web は '' を送る。

    `android/` と同じ理由で、pentala に無いディレクトリを踏む表明はその有無で
    skip する。ここは `cli/` と `web/` の両方を読む。
    """
    cli_src = REPO / "cli" / "src" / "inku_cli" / "cli.py"
    web_page = REPO / "web" / "src" / "routes" / "+page.svelte"
    if not cli_src.parent.is_dir() or not web_page.parent.is_dir():
        pytest.skip("cli/ か web/ がこの木に無い")

    cli_text = cli_src.read_text(encoding="utf-8")
    compose_payload = cli_text[cli_text.index("def _compose_payload") :]
    compose_payload = compose_payload[: compose_payload.index("\ndef ", 1)]
    assert '"description"' not in compose_payload, (
        "CLI の DDL モードが description を送っている: 出自の無い作品に記述を与えている"
    )
    assert "--description" not in cli_text.split("def add_refine_perform_arguments")[0], (
        "paint / batch に --description が戻っている"
    )

    web_text = web_page.read_text(encoding="utf-8")
    draw_new_ddl = web_text[web_text.index("async function drawNewDdl") :]
    draw_new_ddl = draw_new_ddl[: draw_new_ddl.index("\nasync function ", 1)]
    assert "composeOne(nextDdl, ''" in draw_new_ddl, (
        "web の「指示書を新規作成」が記述なしで描かなくなっている"
    )
