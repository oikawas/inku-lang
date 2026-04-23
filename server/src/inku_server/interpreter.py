"""Stage 1: 自由記述 → 正規化DDL (Saijiki 語彙のみ)

backend 切替: 環境変数 `INKU_LLM_BACKEND`
- `anthropic`: Claude Opus 4.7 (未実装、後日)
- `openai`: OVMS qwen3-api (Qwen3-8B) に `/no_think` で問い合わせ

設計原則 (SPEC §1, §13):
- 感情語彙は排除、物理・運動語彙に置換
- 作者の主張を入れず、記述を提示
- 出力は 1〜3 文の簡潔な日本語。次段 (composer) が パース可能な正規化DDL
"""

from __future__ import annotations

import os
import re

ANTHROPIC_MODEL = "claude-opus-4-7"
MAX_TOKENS = 1024

SYSTEM_PROMPT = """あなたは inku DDL の第一段階インタプリタ。

入力: 作者の自由な記述 (詩的・比喩的・感情語を含むことがある)
出力: **正規化DDL** (Saijiki 歳時記の語彙のみを使った簡潔な日本語指示)

# 原則

1. **感情語彙を排除せよ** (美しく→削除、激しく→速く、静かに→ゆっくり)
2. 座標は 0.0〜1.0 の比率で考える (左上=(0,0), 右下=(1,1))
3. 出力は 1〜3 文の普通の日本語。箇条書き禁止、説明禁止、前置き禁止
4. 使えるのは Saijiki の語彙のみ

# Saijiki (歳時記)

## かたち
円、楕円、三角、四角、線、弧

## てざわり
髪、鉛筆、ペン (既定)、ロットリング、クレヨン、チョーク、細筆、太筆、縄

## つらなり (線の種類)
実線 (既定)、破線、点線、一点鎖線

## いろ
白、黒 (既定)、青、赤、緑、灰

## ゆらぎ
細かく、大きく、ゆっくり、速く、揺れる、波打つ、震える、滲む

## ばしょ
上、下、中央、左端、右端、上端、下端、中心、隅

# 変換例

入力: 山の向こうに月が昇る
出力: 画面下1/3に灰色の横線を引く。右上に黒い円を置く。半径は画面の1割。

入力: 激しい嵐の中で
出力: 画面全体に黒い線を速く揺れるように散らす。

入力: 静かな水面に落ちる一滴
出力: 中央に黒い小さな円を置く。その周りに青い破線の円を三つ、半径を広げて並べる。

入力: 冬の朝、窓ガラスの結晶
出力: 画面中央に白い細い線を放射状に六本引く。端が細かく震える。

# 出力形式

正規化DDL のテキストのみ。前置き・説明・タグ・コードブロック装飾はすべて禁止。"""


def interpret(text: str) -> str:
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        return _interpret_openai(text)
    return _interpret_anthropic(text)


def _interpret_anthropic(text: str) -> str:
    from anthropic import Anthropic

    client = Anthropic()
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            return block.text.strip()
    raise RuntimeError("Anthropic did not return text content")


def _interpret_openai(text: str) -> str:
    from openai import OpenAI

    base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:18000/v3")
    api_key = os.getenv("OPENAI_API_KEY") or "none"
    model = os.getenv("OPENAI_MODEL_STAGE1", "qwen3-api")

    client = OpenAI(base_url=base_url, api_key=api_key)

    # Qwen3 thinking モード抑制
    user_content = f"/no_think {text}"

    resp = client.chat.completions.create(
        model=model,
        max_tokens=MAX_TOKENS,
        temperature=0.3,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        stream=False,
    )
    out = (resp.choices[0].message.content or "").strip()
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.DOTALL).strip()
    return out
