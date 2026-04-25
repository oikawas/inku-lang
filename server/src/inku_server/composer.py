"""Stage 2: Normalized DDL → JSON Score.

設計原則:
  SYSTEM_PROMPT は「手順」のみ。フィールド仕様は schema.py の description が正典。
  新しい primitive や属性を追加する場合は schema.py を更新する。ここは変えない。

モデル ID によるバックエンド自動選択:
- `anthropic:<model>` → Anthropic tool_use API
- `org/model` (スラッシュ含む) → NVIDIA NIM API
- それ以外 → OVMS (ローカル OpenAI 互換)
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .schema import Score

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096

# 手順のみ。フィールド仕様は submit_score スキーマの description を参照。
# 例は「最も非自明なパターン」に絞る — 追加は EXAMPLE_POOL (interpreter.py) と同じ方針で。
SYSTEM_PROMPT = """あなたは inku DDL の第二段階コンパイラ。
正規化DDL を解析し submit_score を呼び出せ。
フィールド仕様は submit_score スキーマの description フィールドが正典。

# 変換ルール (厳守)

- 座標: 0.0-1.0 比率 (左上=(0,0) 右下=(1,1))
- circle/ellipse/arc → center フィールド。square/triangle → position フィールド (bbox 左上)
- 中央配置の square/triangle: position = [0.5-w/2, 0.5-h/2]
- **複数同一図形 → 1 instruction + arrangement。複数 instruction 生成は絶対禁止**
- variation は明示された揺らぎがある場合のみ付ける
- **count は 1〜1000 の整数。「たくさん・多数・無数」は 20 程度。DDL に明示的な数があればその値を使う**
- **塗りつぶし指示 (塗る・塗りつぶす・ベタ・中を塗る等) → filled=true。輪郭のみは filled 省略 (default false)**

# 例 (最重要パターン)

入力: 縦の実線を横に三本並べる。
出力: {"instructions":[{"primitive":"line","from":[0.5,0.0],"to":[0.5,1.0],"arrangement":{"count":3,"layout":"horizontal"}}]}

入力: 青い小さな円をランダムに五つ散らす。半径0.04。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.04,"color":"blue","arrangement":{"count":5,"layout":"scatter"}}]}

入力: 上から半分に横線。小刻みに震える。
出力: {"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"variation":{"amplitude":"fine","frequency":"medium","quality":"perlin","dimensions":["position_y"]}}]}

入力: 画面中央に一辺0.4の緑の四角。
出力: {"instructions":[{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"color":"green"}]}

入力: 赤い塗りつぶし円を中央に。半径0.2。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.2,"color":"red","filled":true}]}

説明・前置き禁止。submit_score 呼び出しのみ。"""


def _submit_tool() -> dict[str, Any]:
    return {
        "name": "submit_score",
        "description": "正規化DDLから導出した JSON Score を提出する。",
        "input_schema": Score.model_json_schema(),
    }


def _get_provider(model: str) -> str:
    if model.startswith("anthropic:"):
        return "anthropic"
    if "/" in model:
        return "nvidia"
    return "ovms"


def _strip_prefix(model: str) -> str:
    if model.startswith("anthropic:"):
        return model[len("anthropic:"):]
    return model


def compose(ddl: str, *, model: str | None = None) -> Score:
    if model:
        provider = _get_provider(model)
        if provider == "anthropic":
            return _compose_anthropic(ddl, model=_strip_prefix(model))
        return _compose_openai(ddl, model=model)
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        return _compose_openai(ddl, model=None)
    return _compose_anthropic(ddl)


def _compose_anthropic(ddl: str, *, model: str | None = None) -> Score:
    from anthropic import Anthropic

    client = Anthropic()
    resp = client.messages.create(
        model=model or DEFAULT_ANTHROPIC_MODEL,
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

    model = model or os.getenv("OPENAI_MODEL", "qwen-api")

    if "/" in model:
        base_url = "https://integrate.api.nvidia.com/v1"
        api_key = os.getenv("NVIDIA_API_KEY", "")
    else:
        base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:18000/v3")
        api_key = os.getenv("OPENAI_API_KEY") or "none"

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
    """Tool call の arguments 部を各モデル方言から抽出する。

    対応する形式:
    - Qwen2.5: `<tool_call>{"name":"X","arguments":{...}}</tool_call>`
    - Gemma 3: ```json {"tool_calls":[{"name":"X","arguments":{...}}]} ```
    - その他: 裸の {"instructions":[...]} (Score 直接)
    """
    m = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
    if m:
        try:
            payload = json.loads(m.group(1))
            return payload.get("arguments", payload)
        except json.JSONDecodeError:
            pass

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
