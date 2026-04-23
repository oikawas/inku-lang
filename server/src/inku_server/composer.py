"""Stage 2: Normalized DDL → JSON Score.

backend 切替: 環境変数 `INKU_LLM_BACKEND`
- `anthropic` (default): Claude Haiku 4.5 tool_use
- `openai`: OpenAI 互換 API (OVMS の Qwen2.5 等) に JSON 直接出力させる

揺らぎ (variation) の実現は Renderer 層 (SPEC §13.8) なので、ここでは
決定的な楽譜を出すだけ。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .schema import Score

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """あなたは inku DDL の第二段階コンパイラ。
入力: 正規化DDL (コア語彙のみの自然言語記述)
出力: JSON Score

# コア語彙 (Saijiki / 歳時記)

## かたち (primitive)
- 円 → circle (center, radius)
- 楕円 → ellipse (center, size)
- 三角 → triangle (position=bbox左上, size)
- 四角 → square (position=左上, size)
- 線 → line (from, to)
- 弧 → arc (未対応)

## てざわり (weight)
髪=hair, 鉛筆=pencil, ペン=pen(default), ロットリング=rotring,
クレヨン=crayon, チョーク=chalk, 細筆=brush_thin, 太筆=brush_thick, 縄=rope

## つらなり (style)
実線=solid(default), 破線=dashed, 点線=dotted, 一点鎖線=dash_dot

## いろ (color)
白=white, 黒=black(default), 青=blue, 赤=red, 緑=green, 灰=gray

## ゆらぎ (variation) — 任意
- amplitude: fine(細かく), medium, broad(大きく)
- frequency: slow(ゆっくり), medium, high(速く)
- quality: none, white, perlin, pink, wave(波打つ)
- dimensions: position_x/position_y/angle/length/thickness/rotation/radius のリスト

# 座標系

0.0〜1.0 の比率。左上=(0,0), 右下=(1,1)。
- 中心 → (0.5, 0.5)
- 上から1/3 → y=0.333
- 画面の2割 → 0.2
- 左端=x:0, 右端=x:1, 上端=y:0, 下端=y:1

# 出力ルール

- primitive ごとに必須フィールドを埋める
- 数値は小数 (0.5, 0.333 等)
- 指定無きフィールドはデフォルト (weight=pen, color=black, style=solid)
- 明示されない揺らぎは variation を付けない
- 複数指示は instructions 配列に順番通り並べる"""


def _submit_tool() -> dict[str, Any]:
    return {
        "name": "submit_score",
        "description": "正規化DDLから導出した JSON Score を提出する。",
        "input_schema": Score.model_json_schema(),
    }


def compose(ddl: str) -> Score:
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        return _compose_openai(ddl)
    return _compose_anthropic(ddl)


def _compose_anthropic(ddl: str) -> Score:
    from anthropic import Anthropic

    client = Anthropic()
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=[_submit_tool()],
        tool_choice={"type": "tool", "name": "submit_score"},
        messages=[{"role": "user", "content": ddl}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_score":
            return Score.model_validate(block.input)
    raise RuntimeError("Anthropic did not return submit_score tool call")


def _compose_openai(ddl: str) -> Score:
    from openai import OpenAI

    base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:18000/v3")
    api_key = os.getenv("OPENAI_API_KEY") or "none"
    model = os.getenv("OPENAI_MODEL", "qwen-api")

    client = OpenAI(base_url=base_url, api_key=api_key)

    schema_str = json.dumps(Score.model_json_schema(), ensure_ascii=False)
    system = (
        SYSTEM_PROMPT
        + "\n\n# 出力形式\n\n"
        + "以下の JSON Schema に厳密に準拠した **JSON オブジェクトのみ** を返せ。"
        + "説明文・前置き・マークダウン装飾は禁止。`{` から `}` までの単一 JSON のみ。\n\n"
        + f"Schema:\n{schema_str}"
    )

    resp = client.chat.completions.create(
        model=model,
        max_tokens=MAX_TOKENS,
        temperature=0.0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": ddl},
        ],
        stream=False,
    )
    text = (resp.choices[0].message.content or "").strip()
    data = _extract_json(text)
    return Score.model_validate(data)


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError(f"Could not extract JSON from response: {text[:500]}")
