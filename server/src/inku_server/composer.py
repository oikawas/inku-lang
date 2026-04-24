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

# 手順 (順番に考えよ)

## 1. primitive を決める

| 日本語 | primitive | 必須フィールド | 補助フィールド |
|---|---|---|---|
| 線 | line | from=(x1,y1), to=(x2,y2) | — |
| 円 | circle | center=(cx,cy), radius | — |
| 楕円 | ellipse | center=(cx,cy), size=(w,h) | — |
| 三角 | triangle | position=(bbox左上x, bbox左上y), size=(w,h) | — |
| 四角 | square | position=(左上x, 左上y), size=(w,h) | — |

**重要**: 円/楕円は `center` (中心)、三角/四角は `position` (bbox 左上) を使う。混同禁止。

## 2. 「中央に配置」= position と center で値が違う

同じ「中央配置」でも:
- circle/ellipse の center = (0.5, 0.5) そのまま
- square/triangle の position = (0.5 - w/2, 0.5 - h/2) **左上に補正要**

例: 中央に一辺0.4の四角 → position=(0.3, 0.3), size=(0.4, 0.4)

## 3. 必須数値の既定値

ユーザー指定がない場合の既定:
- circle.radius = 0.1
- ellipse.size = (0.4, 0.2)
- square.size = (0.3, 0.3)
- triangle.size = (0.3, 0.3)
- line の位置は必ず from/to を埋める (省略禁止)

## 4. 日本語→値 マッピング (厳守)

### style (つらなり)
| 日本語 | 値 |
|---|---|
| 実線 (default) | solid |
| 破線 | dashed |
| 点線 | dotted |
| 一点鎖線 | dash_dot |

### weight (てざわり)
髪=hair, 鉛筆=pencil, ペン=pen(default), ロットリング=rotring,
クレヨン=crayon, チョーク=chalk, 細筆=brush_thin, 太筆=brush_thick, 縄=rope

### color (いろ)
白=white, 黒=black(default), 青=blue, 赤=red, 緑=green, 灰=gray

### variation (ゆらぎ) — 明示された場合のみ付ける
| 日本語 | amplitude | quality |
|---|---|---|
| 細かく揺れる / 小刻み | fine | perlin |
| 大きく揺れる | broad | perlin |
| 波打つ | (文脈次第) | wave |
| 震える | fine | perlin |
| 滲む | (各値を文脈から) | pink |

frequency: ゆっくり=slow, 速く=high, 無指定=medium

### variation.dimensions (揺れる軸) — **線の進行方向と垂直な軸**
- 横線 (y固定、xが0→1に進行) が揺れる → dimensions=["position_y"]
- 縦線 (x固定、yが0→1に進行) が揺れる → dimensions=["position_x"]
- 斜め線: dimensions=["position_x","position_y"] 両方

## 5. 座標系

0.0〜1.0 の比率。左上=(0,0), 右下=(1,1)。
- 中心 → (0.5, 0.5)
- 上から1/3 → y=0.333
- 画面の2割 → 0.2
- 左端=x:0, 右端=x:1, 上端=y:0, 下端=y:1

## 6. 出力

- 説明文 / 前置き / マークダウン fence 禁止
- `{` から `}` までの単一 JSON オブジェクト
- instructions 配列、順番通り

# 例

入力: 上端中央に小さな黒い円。半径0.05。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.1],"radius":0.05}]}

入力: 画面中央に一辺0.4の緑の四角。
出力: {"instructions":[{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"color":"green"}]}

入力: 左端から右端へy=0.7で点線を引く。
出力: {"instructions":[{"primitive":"line","from":[0.0,0.7],"to":[1.0,0.7],"style":"dotted"}]}

入力: 左端に縦線を引く。上から下まで。波打つ。
出力: {"instructions":[{"primitive":"line","from":[0.0,0.0],"to":[0.0,1.0],"variation":{"amplitude":"medium","frequency":"medium","quality":"wave","dimensions":["position_x"]}}]}

入力: 上から半分に横線。小刻みに震える。
出力: {"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}
"""


def _submit_tool() -> dict[str, Any]:
    return {
        "name": "submit_score",
        "description": "正規化DDLから導出した JSON Score を提出する。",
        "input_schema": Score.model_json_schema(),
    }


def compose(ddl: str, *, model: str | None = None) -> Score:
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        return _compose_openai(ddl, model=model)
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


def _compose_openai(ddl: str, *, model: str | None = None) -> Score:
    from openai import OpenAI

    base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:18000/v3")
    api_key = os.getenv("OPENAI_API_KEY") or "none"
    model = model or os.getenv("OPENAI_MODEL", "qwen-api")

    client = OpenAI(base_url=base_url, api_key=api_key)

    tool = {
        "type": "function",
        "function": {
            "name": "submit_score",
            "description": "正規化DDLから導出した JSON Score を提出する。",
            "parameters": Score.model_json_schema(),
        },
    }

    resp = client.chat.completions.create(
        model=model,
        max_tokens=MAX_TOKENS,
        temperature=0.0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": ddl},
        ],
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": "submit_score"}},
        stream=False,
    )

    msg = resp.choices[0].message
    if msg.tool_calls:
        args = msg.tool_calls[0].function.arguments
        return Score.model_validate(json.loads(args))

    text = (msg.content or "").strip()
    args = _extract_tool_call_args(text)
    if args is not None:
        return Score.model_validate(args)

    data = _extract_json(text)
    return Score.model_validate(data)


def _extract_tool_call_args(text: str) -> dict | None:
    """Tool call の `arguments` 部を各モデル方言から抽出する。

    対応する形式:
    - Qwen2.5: `<tool_call>{"name":"X","arguments":{...}}</tool_call>`
    - Gemma 3: ```json {"tool_calls":[{"name":"X","arguments":{...}}]} ```
    - その他: 裸の {"instructions":[...]} (Score 直接)
    """
    # Qwen 方言
    m = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
    if m:
        try:
            payload = json.loads(m.group(1))
            return payload.get("arguments", payload)
        except json.JSONDecodeError:
            pass

    # Gemma 方言 (markdown fence + {"tool_calls":[{...}]})
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            payload = json.loads(m.group(1))
            if isinstance(payload, dict):
                tcs = payload.get("tool_calls")
                if isinstance(tcs, list) and tcs:
                    args = tcs[0].get("arguments") or tcs[0].get("parameters")
                    if isinstance(args, dict):
                        return args
                if "arguments" in payload and isinstance(payload["arguments"], dict):
                    return payload["arguments"]
                if "instructions" in payload:
                    return payload
        except json.JSONDecodeError:
            pass

    return None


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
