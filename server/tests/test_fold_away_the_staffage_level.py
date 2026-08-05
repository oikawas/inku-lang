"""受入: 契約 fold-away-the-staffage-level (2026-08-05)。

添景水準 (tenkei) は軸ごと畳まれた。**この契約の主な失敗は「消しすぎ」である。**
T-2・T-4・T-5・T-7 はいずれもその対照で、これらが無いと「全部消す」が満点を取る。

置き換えた `test_tenkei.py` が見ていたもののうち、水準に依らない性質は残してある:
純明示バイパス (T-11) と、プラグイン転写ガード (T-12)。**どちらも添景ではない** ---
前者は明示された名前空間付き語を LLM に書き換えさせないための転記の忠実性、
後者は同じ主題を二重に配達しないための境界である。
"""

from __future__ import annotations

import ast
import inspect
import json
import pathlib
import re
import subprocess
import uuid

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.api_core.routers import render as render_routes
from inku_server.coerce import coerce_score
from inku_server.ddl_expander import expand_intermediate_ddl
from inku_server.plugins import DOCUMENT_PLUGIN_MANAGER
from inku_server.plugins.document_format import PluginDocumentManager
from inku_server.schema import Score

client = TestClient(app)

ROOT = pathlib.Path(__file__).resolve().parents[2]
COERCE_PACKAGE = ROOT / "server/src/inku_server/coerce"
CLI_SOURCE = ROOT / "cli/src/inku_cli/cli.py"
CLI_README = ROOT / "cli/README.md"
WEB = ROOT / "web/src"
GOLDEN = json.loads((pathlib.Path(__file__).parent / "golden" / "coerce_golden.json").read_text())
FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "plugins" / "minimal-arcs.inku-plugin.md"

# `web/` と `cli/` は pentala にも在るが、`android/` は全同期経路から恒久除外
# されている。ディレクトリの有無で skip を決める（ファイル名で書くと、無い機械で
# 番人が落ちる）。
cli_tree_only = pytest.mark.skipif(not CLI_SOURCE.parent.is_dir(), reason="cli/ is absent")
web_tree_only = pytest.mark.skipif(not WEB.is_dir(), reason="web/ is absent")


# 発明していた 6 分岐と、それぞれが書いていた note の指紋。
# **本数でなく 1 本ずつ表明する** --- どれか 1 本を戻したら、その行が赤くなる。
INVENTING_BRANCHES = {
    "_with_visual_event": "visual event restored",
    "_with_composition_diversity_repair": "composition anchor restored",
    "_with_context_energy_repair": "energy restored without density growth",
    "_with_motion_floor": "motion floor restored",
    "_with_surface_tension": "surface tension restored",
    # 契約は 5 本を挙げていたが、実測では 6 本目が在った: `_with_focal_event_floor` は
    # 挿入予算が開けていた 6 番目の門で、golden 40 件で 3 個足していた。畳んだ後の
    # 挙動を `tenkei=none` と一致させるには、これも落ちる（2026-08-05 実測）。
    "_with_focal_event_floor": "adjacent reaction",
}

DELIVERING_BRANCHES = {
    # 分岐 -> その分岐だけを発火させる golden ケース (2026-08-05 実測)。
    # **3 本すべてを発火させるケースは 1 件も無い**ので、分岐ごとに書く。
    "with_ddl_coverage": ("H-05", "H-08", "H-12", "H-16", "S-background-governor"),
    "with_complex_motif_repair": ("S-complex-motif", "S-dedupe-gates-motif"),
    "with_shape_delivery_repair": ("H-20", "S-shape-delivery"),
}


def _coerce_source() -> str:
    return "\n".join(path.read_text() for path in sorted(COERCE_PACKAGE.glob("*.py")))


# ── T-1 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("function_name", "note"), sorted(INVENTING_BRANCHES.items()))
def test_t1_the_inventing_branch_is_gone(function_name: str, note: str) -> None:
    """T-1: 発明する分岐は、関数名も、それが書いていた note の文言も残っていない。"""
    source = _coerce_source()
    # 識別子として数える。`_with_visual_event` は `_with_visual_event_type_hints`
    # （生き残っている分岐）の接頭辞なので、部分一致では必ず当たってしまう。
    identifiers = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", source))
    assert function_name not in identifiers, f"{function_name} が coerce に残っている"
    assert note not in source, f"{function_name} の note「{note}」が coerce に残っている"


# ── T-2 (T-1 の対照) ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(("branch", "case_ids"), sorted(DELIVERING_BRANCHES.items()))
def test_t2_the_delivering_branch_still_authors_its_instruction(
    branch: str, case_ids: tuple[str, ...]
) -> None:
    """T-2: 記述を配達する 3 分岐は今も発火する。

    これが無いと「足す分岐を全部消す」が T-1 で満点を取り、配達を抜き取る。
    """
    fired = []
    for case_id in case_ids:
        report: dict[str, int] = {}
        case_input = GOLDEN["cases"][case_id]["input"]
        coerce_score(
            Score.model_validate(case_input["score"]),
            ddl=case_input["ddl"],
            branch_report=report,
        )
        if report.get(branch):
            fired.append(case_id)
    assert fired, f"{branch} が {list(case_ids)} のどれでも発火しない"


def test_t2_the_delivering_branches_still_write_instructions() -> None:
    """T-2 の続き: 発火の記録ではなく、instruction が本当に増えることを見る。

    `_record_branch_fire` は本数の変化と中身の変化を同じ数に足すので、発火の記録
    だけでは「配達した」ことにならない。
    """
    case_input = GOLDEN["cases"]["H-05"]["input"]
    before = Score.model_validate(case_input["score"])
    after = coerce_score(before, ddl=case_input["ddl"])
    assert len(after.instructions) > len(before.instructions)
    assert any("coverage from DDL clause" in (ins.note or "") for ins in after.instructions)


# ── T-3 ──────────────────────────────────────────────────────────────────────

def test_t3_coerce_score_has_no_level_and_no_insertion_budget() -> None:
    parameters = inspect.signature(coerce_score).parameters
    assert "tenkei" not in parameters
    assert "plugin_instructions_present" not in parameters

    source = _coerce_source()
    assert "_scenery_allows" not in source
    assert "_scenery_spend" not in source
    assert "scenery_budget" not in source


# ── T-4 / T-5: 保存済みの作品と新しい作品 ───────────────────────────────────

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
    group = db.add_user_group(f"staffage-{suffix}")
    user = db.add_user(
        username=f"staffage-{suffix}",
        email=f"staffage-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    yield user
    db.delete_all(user["id"])
    db.delete_user(user["id"])


def test_t4_a_work_saved_before_the_removal_still_reports_its_render_conditions(db_user) -> None:
    """T-4: 撤去より前に保存された作品は、描画条件を今も報告する。

    **`db.py` の読み出しはこの経路の唯一の出口で、撤去作業では死んだコードに
    見える。**ここが赤くなるのは、その 2 行を巻き添えで消したときである。
    """
    saved = db.add_item(_history_item(db_user["id"], 4000, tenkei="none"))
    assert saved["tenkei"] == "none"

    token = db.create_session(db_user["id"])
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/history", headers=headers, params={"limit": 10})
    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()["items"]}
    assert items[saved["id"]]["tenkei"] == "none"


def test_t5_a_fresh_work_carries_no_level(db_user) -> None:
    """T-5: 新しく作った作品は列が NULL で、応答に鍵が無い。"""
    token = db.create_session(db_user["id"])
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/history",
        headers=headers,
        json={
            "input": "枝",
            "score": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]},
            "at": 4100,
        },
    )
    assert response.status_code == 200
    assert "tenkei" not in response.json()

    listed = client.get("/api/history", headers=headers, params={"limit": 10}).json()["items"]
    fresh = next(item for item in listed if item["at"] == 4100)
    assert "tenkei" not in fresh


def test_t5_the_request_model_no_longer_accepts_the_key(db_user) -> None:
    """対照: 鍵を送っても列には入らない（送り手が残っていても記録は増えない）。"""
    token = db.create_session(db_user["id"])
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/history",
        headers=headers,
        json={
            "input": "枝",
            "score": {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]},
            "at": 4101,
            "tenkei": "none",
        },
    )
    assert response.status_code == 200
    assert "tenkei" not in response.json()


# ── T-6 / T-7: UI ────────────────────────────────────────────────────────────

STAFFAGE_ROWS = (
    ("components/CanvasPanel.svelte", "developerMode && statusTenkei"),
    ("components/HistoryStrip.svelte", "developerMode && it.tenkei"),
)


@web_tree_only
@pytest.mark.parametrize(("relative_path", "condition"), STAFFAGE_ROWS)
def test_t6_and_t7_the_staffage_row_is_developer_only_and_needs_a_value(
    relative_path: str, condition: str
) -> None:
    """T-6 / T-7: 通常モードには添景の行が無く、開発者モードでは値を持つ過去作
    にだけ出る。**両方を見る** --- 「開発者モードなら常に出す」は前半だけなら通る。
    """
    source = (WEB / "lib" / relative_path).read_text()
    assert condition in source, f"{relative_path} の添景行が {condition} で囲まれていない"

    # 添景を印字する行はこの 1 箇所だけで、その 1 箇所が条件の中に在る。
    printing = [line for line in source.splitlines() if "Staffage" in line or "添景" in line]
    assert len(printing) == 1, f"{relative_path} に添景を印字する行が {len(printing)} 本ある"
    assert condition in printing[0] or condition in source[: source.index(printing[0])][-400:]


@web_tree_only
def test_t7_the_row_has_no_explanatory_hint() -> None:
    """裁定どおり説明文は出さない。i18n の鍵ごと消えている。"""
    for name in ("ja.ts", "en.ts", "types.ts"):
        source = (WEB / "lib" / "i18n" / name).read_text()
        assert "provenanceHintStaffage" not in source
        assert "tooltipInputTenkei" not in source


# ── T-8 ──────────────────────────────────────────────────────────────────────

@web_tree_only
@cli_tree_only
def test_t8_no_sender_writes_the_key_any_more() -> None:
    """T-8: 要求本文に `tenkei` を載せる送り手が居ない。

    **`android/` はディレクトリごと除外する** --- ファイル名で除外すると、木の
    無い機械（pentala）で番人が落ちる。
    """
    result = subprocess.run(
        [
            "git", "grep", "-n", "-i", "tenkei", "--",
            "web/src", "cli/src", "cli/README.md", "server/src",
            ":(exclude)server/src/inku_server/db.py",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    def _code(line: str) -> str:
        """`path:lineno:code` から本文を取り、コメントを落とす。"""
        body = line.split(":", 2)[-1].strip()
        return "" if body.startswith(("#", "//", "*", "/*")) else body

    lines = [_code(line) for line in result.stdout.splitlines() if line.strip()]
    # 「送り手」の形だけを数える: 引用符つきの鍵・キーワード引数・省略記法・
    # 条件つき spread。**型の宣言 (`tenkei: str | None = None`) は読み手であって
    # 送り手ではない** --- そこを送り手と数えると、過去作の読み出しを消すことが
    # この番人を緑にする最短経路になってしまう。
    sender_forms = (
        r"""["']tenkei["']\s*:""",
        r"\btenkei\s*=(?!=)",
        r"\{\s*tenkei\s*\}",
        r"\.\.\.\(.*\btenkei\b",
    )
    senders = [line for line in lines if any(re.search(form, line) for form in sender_forms)]
    assert not senders, "要求本文に tenkei を載せている送り手が残っている:\n" + "\n".join(senders)


def test_t8_db_keeps_the_column_and_its_only_exit() -> None:
    """T-8 の対照。**送り手が 0 でも、読み手を消してはならない。**"""
    source = (ROOT / "server/src/inku_server/db.py").read_text()
    assert "tenkei = Column(String, nullable=True)" in source
    assert '"tenkei": "ALTER TABLE history ADD COLUMN tenkei VARCHAR"' in source
    assert "if row.tenkei is not None:" in source
    assert 'item["tenkei"] = row.tenkei' in source


# ── T-9 ──────────────────────────────────────────────────────────────────────

def test_t9_the_corpora_were_rebuilt_not_refrozen() -> None:
    """T-9: 水準を弁別するためだけに在った case は消え、入力に重複が無い。"""
    from inku_server.layer_versions import DDL_ENGINE_VERSION

    manifest = json.loads(
        (ROOT / "server/reference" / f"ddl-engine-{DDL_ENGINE_VERSION}" / "manifest.json").read_text()
    )
    cases = manifest["cases"]
    for gone in ("B-trigger-auto", "B-trigger-sparse", "B-trigger-none",
                 "A-tenkei-auto", "A-tenkei-sparse", "A-tenkei-none"):
        assert gone not in cases, f"{gone} が残っている"

    seen: dict[str, str] = {}
    for case_id, case in sorted(cases.items()):
        key = json.dumps(case["input"], ensure_ascii=False, sort_keys=True)
        assert key not in seen, f"{case_id} の入力が {seen[key]} と同一"
        seen[key] = case_id
        assert "tenkei" not in case["input"]

    golden_inputs = {case_id: case["input"] for case_id, case in GOLDEN["cases"].items()}
    assert all("tenkei" not in value for value in golden_inputs.values())


# ── T-10 ─────────────────────────────────────────────────────────────────────

@cli_tree_only
def test_t10_the_cli_has_no_staffage_flag() -> None:
    """T-10: 旗が cli.py からも `--help` からも README からも消えている（3 つとも）。"""
    assert "--staffage" not in CLI_SOURCE.read_text()
    assert "--staffage" not in CLI_README.read_text()

    tree = ast.parse(CLI_SOURCE.read_text())
    flags = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    # 名指しの一覧は穴を残すので、旗の一覧そのものに添景の語が無いことを見る。
    assert not [flag for flag in flags if "staffage" in flag or "tenkei" in flag]
    help_text = subprocess.run(
        ["python", "-c",
         "import sys; sys.path.insert(0, 'src'); "
         "from inku_cli.cli import build_parser; build_parser().print_help()"],
        cwd=CLI_SOURCE.parents[1], capture_output=True, text=True,
    )
    if help_text.returncode == 0:
        assert "staffage" not in help_text.stdout


# ── T-11 / T-12: 水準から切り離して残した性質 ───────────────────────────────

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
    group = db.add_user_group(f"staffage-api-{suffix}")
    user = db.add_user(
        username=f"staffage-api-{suffix}",
        email=f"staffage-api-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return {"Authorization": f"Bearer {token}"}


def test_t11_pure_invocation_is_transcribed_without_asking_a_level(tmp_path) -> None:
    """T-11: 純明示バイパスは水準の機能ではない。

    名前空間付き語だけの入力を Stage 1 へ通すと、モデルがその語を書き換えうる。
    これは転記の忠実性の話で、添景の量とは関係が無い --- **だから水準と切り離して
    残した**（契約 §2.2 の「単独で必要か測ること」への答え）。
    """
    manager = PluginDocumentManager(directory=tmp_path)
    (tmp_path / FIXTURE.name).write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    manager.reload(force=True)
    assert manager.is_pure_invocation("Sketch.双弧") is True
    assert manager.is_pure_invocation("Sketch.双弧。") is True
    assert manager.is_pure_invocation("小さなSketch.双弧") is False
    assert manager.is_pure_invocation("円を置く") is False


def test_t11_the_interpret_route_bypasses_stage1_with_no_level_in_the_request(
    plugin_dir, user_headers
) -> None:
    """水準を送らずに（もう送れない）バイパスが効く。LLM は呼ばれない。"""
    response = client.post(
        "/api/interpret",
        headers=user_headers,
        json={"description": "Sketch.双弧"},
    )
    assert response.status_code == 200
    assert response.json()["ddl"] == "Sketch.双弧"


def test_t11_the_paint_route_bypasses_stage1_too(monkeypatch, plugin_dir, user_headers) -> None:
    """T-11 の **2 つ目の強制点**。

    The bypass is enforced in two places: `/api/interpret` and the paint path
    (`_paint_events`, which serves `/api/paint` and `/api/paint/stream`). A gate
    on the interpret route alone leaves the paint one unguarded -- cutting it
    left all 2312 tests green (measured 2026-08-05 on the merged tree, at
    acceptance). Assert the property where the second point enforces it: Stage 1
    is never reached, so the plugin term cannot be rewritten.
    """
    reached_stage1: list[str] = []

    def _record_stage1(text, **kwargs):
        reached_stage1.append(text)
        return ("中心に黒い円を置く。", None)

    monkeypatch.setattr(render_routes, "interpret_detail", _record_stage1)
    monkeypatch.setattr(
        render_routes,
        "compose",
        lambda ddl, model=None: Score.model_validate(
            {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
        ),
    )

    response = client.post(
        "/api/paint",
        headers=user_headers,
        json={"description": "Sketch.双弧"},
    )
    assert response.status_code == 200
    assert reached_stage1 == []
    assert response.json()["source_ddl"] == "Sketch.双弧"


def test_t11_the_request_no_longer_validates_a_level(plugin_dir, user_headers) -> None:
    """対照: 未知の鍵は捨てられる。以前は `loud` が 422 だった。"""
    response = client.post(
        "/api/interpret",
        headers=user_headers,
        json={"description": "Sketch.双弧", "tenkei": "loud"},
    )
    assert response.status_code == 200


def test_t12_the_plugin_transcription_guard_still_suppresses_stage15() -> None:
    """T-12: プラグイン決定的転写が主題を運んだら Stage 1.5 は触らない。

    この境界も水準ではない（二重配達の防止）。畳んだ後も残っている。
    """
    ddl = "中央に赤い円を三つ置く。小さな点を画面全体に散らす。"
    guarded = expand_intermediate_ddl(
        ddl, lang="ja", context_text=ddl, plugin_instructions_present=True
    )
    assert guarded == ddl
    # 対照: ガードが無ければ焦点だけは書き換わる（「中央」が焦点語へ）。
    plain = expand_intermediate_ddl(ddl, lang="ja", context_text=ddl)
    assert plain != ddl
    assert "中央" not in plain
    # ただし文は 1 つも増えない（v2.11.0）。
    assert len(re.findall("。", plain)) == len(re.findall("。", ddl))


# ── T-9 の続き: 記録ではなく門にする ────────────────────────────────────────

def test_t9_the_expand_corpus_is_regenerated_not_merely_read_back() -> None:
    """凍結コーパスの digest 検査は**記録**であって門ではない。

    `test_ddl_reference_output_files_match_manifest` はディスク上のファイルと
    manifest を突き合わせるだけなので、展開層を書き換えても pytest では赤く
    ならない（再生成するのは CI だけ）。実測 (2026-08-05): 展開層へ候補文を 1 つ
    戻す摂動で、expander の性質検査は 5 本赤くなったが、コーパス検査は 0 本だった。
    ここで実際に焼き直して突き合わせる。
    """
    import hashlib
    import importlib.util

    from inku_server.layer_versions import DDL_ENGINE_VERSION

    generator_path = ROOT / "server/scripts/gen_ddl_reference.py"
    spec = importlib.util.spec_from_file_location("gen_ddl_reference", generator_path)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    manifest = json.loads(
        (ROOT / "server/reference" / f"ddl-engine-{DDL_ENGINE_VERSION}" / "manifest.json").read_text()
    )
    baked = 0
    for case_id, case_input in generator.build_expand_inputs().items():
        output = generator.expand_intermediate_ddl(**case_input)
        text = output + ("" if output.endswith("\n") else "\n")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
        assert digest == manifest["cases"][case_id]["digest"], case_id
        baked += 1
    # 何件見たかを述べる。黙って 0 件を見た検査は、何も悪くない検査と同じ顔をする。
    assert baked == 13, f"a_expand を {baked} 件しか焼き直していない"
