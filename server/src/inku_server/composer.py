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
「原文」が付いている場合は正規化DDL を主とし、原文は省略された属性（色・素材・数量など）の補完に使え。

# 変換ルール (厳守)

- 座標: 0.0-1.0 比率 (左上=(0,0) 右下=(1,1))
- circle/ellipse/arc → center フィールド。square/triangle → position フィールド (bbox 左上)
- 中央配置の square/triangle: position = [0.5-w/2, 0.5-h/2]
- **複数同一図形 → 1 instruction + arrangement。複数 instruction 生成は絶対禁止**
- variation は明示された揺らぎがある場合のみ付ける
- **count は 1〜1000 の整数。「たくさん・多数・無数」は 20 程度。DDL に明示的な数があればその値を使う**
- **塗りつぶし指示 (塗る・塗りつぶす・ベタ・中を塗る等) → filled=true。輪郭のみは filled 省略 (default false)**
- **背景色 → Score の background フィールド。「背景を黒で塗りつぶす」→ {"background":"black","instructions":[...]}**
- **色とりどり・ランダム配色 → arrangement の color_cycle に使う色を列挙。例: ["red","blue","green","black","gray"]**

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

入力: 背景を黒で塗りつぶす。中央に白い横線を引く。
出力: {"background":"black","instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5],"color":"white"}]}

入力: 赤・青・緑・黒の色とりどりの円を放射状に八つ並べる。
出力: {"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.05,"arrangement":{"count":8,"layout":"radial","color_cycle":["red","blue","green","black","gray","red","blue","green"]}}]}

# わりあい (比率・描画範囲)

- **縦長の四角** → size の高さ(size[1]) が幅(size[0]) の約2倍。例: size=[0.15,0.35]
- **横長の四角** → size の幅(size[0]) が高さ(size[1]) の約2倍。例: size=[0.35,0.15]
- **全幅の線** → from=[0.0,y] to=[1.0,y]
- **半幅の線** → from=[0.25,y] to=[0.75,y]
- **半円** → arc、angle_start=0、angle_end=180 (上半分)
- **上弦** → arc、angle_start=270、angle_end=90 (右側半円、D字形)
- **下弦** → arc、angle_start=90、angle_end=270 (左側半円、C字形)
- **三日月** → arc、angle_start=210、angle_end=330 (細い下弦弧、約120°)

入力: 縦長の四角を中央に置く。
出力: {"instructions":[{"primitive":"square","position":[0.425,0.325],"size":[0.15,0.35]}]}

入力: 全幅の横線を中央に引く。
出力: {"instructions":[{"primitive":"line","from":[0.0,0.5],"to":[1.0,0.5]}]}

入力: 半幅の横線を中央に引く。
出力: {"instructions":[{"primitive":"line","from":[0.25,0.5],"to":[0.75,0.5]}]}

入力: 半円の弧を中央に置く。半径は0.2。
出力: {"instructions":[{"primitive":"arc","center":[0.5,0.5],"radius":0.2,"angle_start":0,"angle_end":180}]}

入力: 上弦の弧を中央に置く。半径は0.15。
出力: {"instructions":[{"primitive":"arc","center":[0.5,0.5],"radius":0.15,"angle_start":270,"angle_end":90}]}

入力: 背景を黒で塗りつぶす。三日月の弧を右上に置く。半径は0.12。
出力: {"background":"black","instructions":[{"primitive":"arc","center":[0.7,0.25],"radius":0.12,"angle_start":210,"angle_end":330,"color":"white"}]}

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


def _build_user_message(ddl: str, original_text: str | None) -> str:
    if original_text and original_text.strip() != ddl.strip():
        return f"[原文]\n{original_text}\n\n[正規化DDL]\n{ddl}"
    return ddl


def compose(
    ddl: str,
    *,
    model: str | None = None,
    original_text: str | None = None,
    system_prompt: str | None = None,
) -> tuple[Score, int | None, int | None]:
    """(score, tokens_in, tokens_out) を返す。system_prompt 指定時はスナップショット使用。"""
    user_msg = _build_user_message(ddl, original_text)
    effective_prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    if model:
        provider = _get_provider(model)
        if provider == "anthropic":
            return _compose_anthropic(user_msg, model=_strip_prefix(model), system_prompt=effective_prompt)
        return _compose_openai(user_msg, model=model, system_prompt=effective_prompt)
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        return _compose_openai(user_msg, model=None, system_prompt=effective_prompt)
    return _compose_anthropic(user_msg, system_prompt=effective_prompt)


def _compose_anthropic(user_msg: str, *, model: str | None = None, system_prompt: str = SYSTEM_PROMPT) -> tuple[Score, int | None, int | None]:
    from anthropic import Anthropic

    client = Anthropic()
    resp = client.messages.create(
        model=model or DEFAULT_ANTHROPIC_MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        tools=[_submit_tool()],
        tool_choice={"type": "tool", "name": "submit_score"},
        messages=[{"role": "user", "content": user_msg}],
    )
    tin = getattr(resp.usage, "input_tokens", None)
    tout = getattr(resp.usage, "output_tokens", None)
    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_score":
            return Score.model_validate(block.input), tin, tout
    raise RuntimeError("Anthropic did not return submit_score tool call")


def _compose_openai(user_msg: str, *, model: str | None = None, system_prompt: str = SYSTEM_PROMPT) -> tuple[Score, int | None, int | None]:
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
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": "submit_score"}},
        stream=False,
    )
    usage = resp.usage
    tin: int | None = getattr(usage, "prompt_tokens", None)
    tout: int | None = getattr(usage, "completion_tokens", None)

    msg = resp.choices[0].message
    if msg.tool_calls:
        args = msg.tool_calls[0].function.arguments
        return Score.model_validate(json.loads(args)), tin, tout

    text = (msg.content or "").strip()
    args = _extract_tool_call_args(text)
    if args is not None:
        return Score.model_validate(args), tin, tout

    data = _extract_json(text)
    return Score.model_validate(data), tin, tout


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
