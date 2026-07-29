"""`thinness` の宣言位置を固定する (I-036 / I-037 / I-038)。

宣言順は Stage 2 の tool schema に並びごと渡り、**任意フィールドは後ろにあるほど埋まる**。
`thinness` は `weight` の直後 (位置 14) では 4〜18% しか搬送されず、末尾 (位置 23) で
84〜91% 搬送される。位置は絵を動かすので、ここで固定する。

凍結コーパスも `check_frozen_corpora.py` も Stage 2 を通らないので、この性質を
捕まえるゲートは他に無い。位置を戻したら P-1 が、`sort_keys` を戻したら P-3 が
赤くなること。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Iterator

from inku_server import composer
from inku_server.renderer import _seed_for_instruction
from inku_server.schema import Instruction, Score

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


def test_thinness_is_declared_last() -> None:
    """P-1 位置: 任意フィールドは後ろにあるほど埋まる。末尾から動かさない。"""
    properties = _instruction_properties()
    assert len(properties) == 24
    assert list(properties)[-1] == "thinness"
    assert list(Instruction.model_fields)[-1] == "thinness"


def test_thinness_schema_body_is_unchanged() -> None:
    """P-2 内容: 移したのは位置だけで、型・既定値・description は engine 16 のまま。"""
    assert _instruction_properties()["thinness"] == THINNESS_SCHEMA


def test_stage2_digest_sees_declaration_order() -> None:
    """P-3 指紋: 絵を動かす並べ替えが `stage2_prompt_digest` に残ること。

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
    """P-4 恒等: 演奏 seed は明示タプルで組み直すので並び順を見ない。

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
