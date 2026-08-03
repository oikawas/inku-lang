"""`thinness` の宣言位置を固定する (I-036 / I-037 / I-038)。

宣言順は Stage 2 の tool schema に並びごと渡り、**任意フィールドは後ろにあるほど埋まる**。
`thinness` は `weight` の直後 (位置 14) では 3〜18% しか搬送されない。

だが**末尾は 1 席しかない**。`thinness` がその席を取った版 (v2.9.5) では `surface` が
末尾を失い、搬送が 92% → 42% へ落ちて **Stage 2 の出力そのものが半分に縮んだ**
(2026-08-02 に 168 本で実測)。よって `thinness` は `surface` の**直前**に置き、
**末尾は `surface` のために空けておく**。

位置は絵を動かす。凍結コーパスも `check_frozen_corpora.py` も Stage 2 を通らないので、
この性質を捕まえるゲートは他に無い。`thinness` を末尾へ戻したら P-1 が、`weight` の隣へ
戻したら P-2 が、`sort_keys` を戻したら P-4 が赤くなること。

宣言順の現物は 3 つある (server / Kotlin の複製 / Android の fixture)。突き合わせの辺も
3 本で、Kotlin ↔ fixture は Android 単体テストが見ているが、server から出る 2 本は
どこも見ていなかった。P-6 と P-7 がその 2 本を埋める。
"""

from __future__ import annotations

import json
import pathlib
from contextlib import contextmanager
from typing import Iterator

import pytest

from inku_server import composer
from inku_server.renderer import _seed_for_instruction
from inku_server.schema import Instruction, Score

ROOT = pathlib.Path(__file__).resolve().parents[2]

# `android/` is permanently excluded from every pentala sync path (standing rule
# 2026-07-30), so on the deployed server the whole tree is absent. Key the skip to
# the DIRECTORY, not to the files below: wherever `android/` exists -- every
# checkout, every developer machine, CI -- these assertions still run, and a moved
# or renamed file is a failure rather than a skip.
ANDROID_TREE = ROOT / "android"
android_only = pytest.mark.skipif(
    not ANDROID_TREE.is_dir(),
    reason="android/ is never synced to the server; the port is checked where the tree exists",
)

KOTLIN_SCHEMA = (
    ANDROID_TREE
    / "app/src/main/java/app/inku/mobile/pipeline/ServerScoreSchemaJson.kt"
)
ANDROID_FIXTURE = (
    ANDROID_TREE / "app/src/test/resources/server_reference/score_schema_contract.json"
)

# engine 16 段 3 で入った本体。位置を移す本契約では 1 文字も動かない。
THINNESS_SCHEMA = {
    "anyOf": [
        {"enum": ["fine", "extra_fine"], "type": "string"},
        {"type": "null"},
    ],
    "default": None,
    "description": (
        "線の細さ。道具の既定より細く引く指定。fine=細い / extra_fine=極細。"
        "省略時は道具の既定。太くする指定は無い"
    ),
    "title": "Thinness",
}


def _instruction_properties() -> dict[str, object]:
    schema = composer._score_tool_schema()
    return schema["properties"]["instructions"]["items"]["properties"]


@contextmanager
def thinness_at(index: int) -> Iterator[None]:
    """`thinness` を index へ動かし、抜けるときに元の並びへ戻す。

    `Instruction.model_fields` だけを触っても `_score_tool_schema()` には届かない。
    `Score` 側も rebuild しないと、`Instruction.model_json_schema()` には出るのに
    tool schema には出ないという食い違いが起きる (I-036 の食い違いの原因)。
    """
    original = dict(Instruction.model_fields)
    fields = dict(original)
    held = fields.pop("thinness")
    keys = list(fields)
    assert 0 <= index <= len(keys), f"index {index} out of range for {len(keys)} fields"
    rebuilt = {k: fields[k] for k in keys[:index]}
    rebuilt["thinness"] = held
    rebuilt.update({k: fields[k] for k in keys[index:]})
    try:
        Instruction.model_fields.clear()
        Instruction.model_fields.update(rebuilt)
        Instruction.model_rebuild(force=True)
        Score.model_rebuild(force=True)
        yield
    finally:
        Instruction.model_fields.clear()
        Instruction.model_fields.update(original)
        Instruction.model_rebuild(force=True)
        Score.model_rebuild(force=True)


def test_surface_is_declared_last() -> None:
    """P-1 末尾: `Instruction` の最後の宣言は `surface` である。

    末尾は 1 席しかない。ここを他のフィールドへ譲ると `surface` の搬送が 92% → 42% へ
    落ち、Stage 2 の出力が半分に縮む。**今後どのフィールドを足しても、末尾へ置いたら
    この検査が赤くなる** — 次に任意フィールドを足す者が同じ退行を黙って通さないため、
    「`thinness` が直前」(P-2) とは別に立てている。
    """
    properties = _instruction_properties()
    assert len(properties) == 25
    assert list(properties)[-1] == "surface"
    assert list(Instruction.model_fields)[-1] == "surface"


def test_thinness_is_declared_immediately_before_surface() -> None:
    """P-2 位置: 任意フィールドは後ろにあるほど埋まる。`surface` の直前から動かさない。"""
    properties = list(_instruction_properties())
    assert properties[-2:] == ["thinness", "surface"]
    assert list(Instruction.model_fields)[-2:] == ["thinness", "surface"]


def test_thinness_schema_body_is_unchanged() -> None:
    """P-3 内容: 移したのは位置だけで、型・既定値・description は engine 16 のまま。"""
    assert _instruction_properties()["thinness"] == THINNESS_SCHEMA


def test_stage2_digest_sees_declaration_order() -> None:
    """P-4 指紋: 絵を動かす並べ替えが `stage2_prompt_digest` に残ること。

    `sort_keys=True` は並びを潰すので、この検査は指紋が並び順に開いていることを要求する。
    """
    def sorted_tool_json() -> str:
        return json.dumps(composer._submit_tool(), ensure_ascii=False, sort_keys=True)

    system_prompt = "order-probe"
    at_last = composer._stage2_prompt_digest(system_prompt)
    sorted_at_last = sorted_tool_json()
    with thinness_at(14):
        assert list(_instruction_properties()).index("thinness") == 14
        after_weight = composer._stage2_prompt_digest(system_prompt)
        sorted_after_weight = sorted_tool_json()
    assert at_last != after_weight
    # 動いたのは並びだけ。鍵を並べ替えて潰すと同一になる ＝ 旧 digest が盲目だった理由。
    assert sorted_at_last == sorted_after_weight
    assert composer._stage2_prompt_digest(system_prompt) == at_last


def test_seed_for_instruction_ignores_declaration_order() -> None:
    """P-5 恒等: 演奏 seed は明示タプルで組み直すので並び順を見ない。

    §3.1 の「決定的な層は 1 バイトも動かない」の前提。ここが赤いなら凍結コーパスが
    緑であることの説明が崩れている。
    """
    instruction = Instruction.model_validate(
        {
            "primitive": "line",
            "from": [0.2, 0.3],
            "to": [0.8, 0.7],
            "weight": "brush_thin",
            "thinness": "fine",
        }
    )
    at_last = _seed_for_instruction(instruction, performance_seed=1234)
    with thinness_at(14):
        moved = Instruction.model_validate(instruction.model_dump(by_alias=True))
        after_weight = _seed_for_instruction(moved, performance_seed=1234)
    assert at_last == after_weight


def _kotlin_instruction_order() -> list[str]:
    """The port keeps a full copy of the tool schema as one raw string literal."""
    parts = KOTLIN_SCHEMA.read_text(encoding="utf-8").split('"""')
    assert len(parts) == 3, f"expected one raw string literal in {KOTLIN_SCHEMA.name}"
    schema = json.loads(parts[1])
    return list(schema["properties"]["instructions"]["items"]["properties"])


@android_only
def test_android_schema_copy_keeps_the_server_declaration_order() -> None:
    """P-6 辺 server ↔ Kotlin: 複製が宣言順ごと server と一致すること。

    port の schema は意図的に部分集合 ([I-008]) なので、等号ではなく **server の順序の
    部分列** であることを見る。server だけ直して複製を落とすと、Android の
    ローカル LLM 経路だけが縮んだまま残る。この辺を見る検査は他に無かった。
    """
    server_order = list(_instruction_properties())
    kotlin_order = _kotlin_instruction_order()
    assert set(kotlin_order) <= set(server_order)
    assert kotlin_order == [k for k in server_order if k in set(kotlin_order)]
    assert kotlin_order[-2:] == ["thinness", "surface"]


@android_only
def test_android_fixture_tables_keep_the_server_declaration_order() -> None:
    """P-7 辺 server ↔ fixture: 焼き直し忘れを捕まえる。

    `ServerScoreVocabularyTest` は Kotlin ↔ fixture を見るが、fixture を作る
    `gen_android_reference.py` を回す検査は CI にも `server/tests/` にも無い。宣言順を
    動かして fixture を焼き直さないと、Android 側だけが旧い並びで固定される。
    **2 つの表を両方見る** — 片方だけだと、生成器を回さず手で片方を直した場合が素通りする。
    """
    fixture = json.loads(ANDROID_FIXTURE.read_text(encoding="utf-8"))
    server_order = list(_instruction_properties())
    dump_order = list(
        json.loads(
            Instruction.model_validate({"primitive": "line"}).model_dump_json(
                by_alias=True
            )
        )
    )
    assert fixture["instruction_property_order"] == server_order
    assert fixture["dump_property_order"] == dump_order
    assert server_order[-2:] == ["thinness", "surface"]
    assert dump_order[-2:] == ["thinness", "surface"]
