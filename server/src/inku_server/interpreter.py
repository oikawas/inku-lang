"""Stage 1: 自由記述 → 正規化DDL (Saijiki 語彙のみ)

設計原則 (プロンプトを無限増殖させないアルゴリズム):
  - SYSTEM_PROMPT_PREFIX: ルールのみ。機能追加でここは増えない
  - EXAMPLE_POOL: 変換例のプール。増やしても推論コストは増えない
  - _build_system_prompt(text): 推論時に入力と関連性の高い例を k 件だけ選択して注入

モデル ID によるバックエンド自動選択:
- `anthropic:<model>` → Anthropic API
- `org/model` (スラッシュ含む) → NVIDIA NIM API
- それ以外 → OVMS (ローカル OpenAI 互換)
"""

from __future__ import annotations

import os
import re

DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-7"
MAX_TOKENS = 1024

# ルールのみ。例は EXAMPLE_POOL に分離。
# 新機能追加 → EXAMPLE_POOL に例を追加するだけ。ここは変えない。
SYSTEM_PROMPT_PREFIX = """あなたは inku DDL の第一段階インタプリタ。

入力: 作者の自由な記述 (詩的・比喩的・感情語を含むことがある)
出力: **正規化DDL** (Saijiki 歳時記の語彙のみを使った簡潔な日本語指示)

# 原則

1. **感情語彙を排除せよ** (美しく→削除、激しく→速く、静かに→ゆっくり)
2. **出力は静止画**。時間経過を表す動詞は禁止:
   - 禁止: 動く、動かす、広がる、広げる、流れる、伸びる、昇る、落ちる、散る、沈む、塗る、塗りつぶす
   - 使える動作動詞: 置く、並べる、引く、描く、散らす、埋める
   - 「ゆらぎ」は静止画に含める質感であり、動きの描写ではない
3. 座標は 0.0〜1.0 の比率で考える (左上=(0,0), 右下=(1,1))
4. 出力は普通の日本語。箇条書き禁止、説明禁止、前置き禁止
5. 使えるのは Saijiki の語彙のみ

# 数量表現 — 最重要ルール

数量詞が含まれる場合、**1文でまとめて記述せよ**。複数の文に展開しない。
次段の構造化処理が arrangement フィールドで展開するため、文を増やす必要はない。

- 「三本の竹を縦に並べる」→「縦の実線を横に三本並べる」(1文)
- 「五つの赤い点をランダムに置く」→「赤い小さな円をランダムに五つ散らす」(1文)
- 「たくさん」「多数」「無数」「いっぱい」→ **二十個程度**にまとめる (上限500)
- 100本・200個などの具体的な数 → **そのまま記述する**

# ランダム配置

「ランダムに」「バラバラに」「散らばって」→ そのまま「ランダムに」「散らす」と記述する。

# Saijiki (歳時記)

かたち: 円、楕円、三角、四角、線、弧
てざわり: 髪、鉛筆、ペン(既定)、ロットリング、クレヨン、チョーク、細筆、太筆、縄
つらなり: 実線(既定)、破線、点線、一点鎖線
いろ: 白、黒(既定)、青、赤、緑、灰
ゆらぎ: 細かく、大きく、ゆっくり、速く、揺れる、波打つ、震える、滲む
ばしょ: 上、下、中央、左端、右端、上端、下端、中心、隅

# 出力形式

正規化DDL のテキストのみ。前置き・説明・タグ・コードブロック装飾はすべて禁止。"""

# 変換例プール。推論時に入力と関連性の高い k 件を選択して使う。
# 例を増やしても推論プロンプトは増えない (k 件固定)。
EXAMPLE_POOL: list[dict] = [
    {
        "keywords": ["月", "昇", "空", "夜", "星", "天"],
        "input": "山の向こうに月が昇る",
        "output": "画面下1/3に灰色の横線を引く。右上に黒い円を置く。半径は画面の1割。",
    },
    {
        "keywords": ["嵐", "激しい", "激しく", "荒れ", "風", "速"],
        "input": "激しい嵐の中で",
        "output": "画面全体に黒い線を速く揺れるように散らす。",
    },
    {
        "keywords": ["水", "滴", "雨", "波紋", "落ちる", "雫"],
        "input": "静かな水面に落ちる一滴",
        "output": "中央に黒い小さな円を置く。その周りに青い破線の円を三つ、半径を広げて並べる。",
    },
    {
        "keywords": ["冬", "結晶", "放射", "氷", "雪", "霜"],
        "input": "冬の朝、窓ガラスの結晶",
        "output": "画面中央に白い細い線を放射状に六本引く。端が細かく震える。",
    },
    {
        "keywords": ["本", "竹", "縦", "並べ", "個", "つ", "複数"],
        "input": "三本の竹を縦に並べる",
        "output": "縦の実線を横に三本並べる。",
    },
    {
        "keywords": ["点", "ランダム", "散ら", "バラバラ", "撒く", "無秩序"],
        "input": "五つの赤い点をランダムに置く",
        "output": "赤い小さな円をランダムに五つ散らす。半径は0.04。",
    },
    {
        "keywords": ["横線", "本", "引く", "並べ", "青", "二", "水平"],
        "input": "二本の青い横線を引く",
        "output": "青い横線を縦に二本並べる。",
    },
    {
        "keywords": ["花", "散る", "散", "桜", "春", "花びら"],
        "input": "花びらが散る",
        "output": "画面全体に細かい点をランダムに散らす。",
    },
    {
        "keywords": ["光", "放射", "差す", "太陽", "輝", "レイ"],
        "input": "光が差す",
        "output": "放射状に細い線を数本引く。",
    },
    {
        "keywords": ["波", "海", "川", "同心円", "広がる"],
        "input": "波が広がる",
        "output": "中心から破線の円を三つ並べる。",
    },
    {
        "keywords": ["霧", "霞", "滲む", "ぼんやり", "曖昧"],
        "input": "霧の中の輪郭",
        "output": "中央に灰色の大きな円を置く。境界が滲む。",
    },
    {
        "keywords": ["格子", "網", "交差", "縦横", "マス"],
        "input": "格子を描く",
        "output": "横線を縦に四本並べる。縦線を横に四本並べる。",
    },
    {
        "keywords": ["たくさん", "多数", "無数", "いっぱい", "沢山", "大量"],
        "input": "たくさんの小さな点を散らす",
        "output": "黒い小さな円をランダムに二十個散らす。半径は0.02。",
    },
    {
        "keywords": ["100", "200", "500", "1000", "百", "千", "本"],
        "input": "100本の細い線をランダムに並べる",
        "output": "黒い細い縦線をランダムに百本散らす。",
    },
]

# api.py が import する SYSTEM_PROMPT — プレフィックスを公開する
SYSTEM_PROMPT = SYSTEM_PROMPT_PREFIX + "\n\n# 変換例\n\n(推論時に入力関連の例を動的に選択して注入)"


def _select_examples(text: str, k: int = 3) -> str:
    """入力テキストと関連性の高い例を k 件選んで返す。

    キーワードの一致数でスコアリングし、上位 k 件を選択する。
    全スコアが 0 の場合は先頭 k 件 (汎用例) を使う。
    """
    scored = [(sum(1 for kw in ex["keywords"] if kw in text), ex) for ex in EXAMPLE_POOL]
    scored.sort(key=lambda x: -x[0])
    top = scored[:k]
    if all(s == 0 for s, _ in top):
        top = [(0, ex) for ex in EXAMPLE_POOL[:k]]
    return "\n\n".join(
        f"入力: {ex['input']}\n出力: {ex['output']}" for _, ex in top
    )


def _build_system_prompt(text: str, k: int = 3) -> str:
    """推論ごとのシステムプロンプトを構築する (PREFIX + 動的例 k 件)。"""
    examples = _select_examples(text, k=k)
    return SYSTEM_PROMPT_PREFIX + "\n\n# 変換例\n\n" + examples


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


def interpret(text: str, *, model: str | None = None) -> str:
    """後方互換: DDL 本文のみ返す (thinking は捨てる)。"""
    ddl, _ = interpret_detail(text, model=model, include_thinking=False)
    return ddl


def interpret_detail(
    text: str,
    *,
    model: str | None = None,
    include_thinking: bool = False,
) -> tuple[str, str | None]:
    """(ddl, thinking) を返す。"""
    system_prompt = _build_system_prompt(text)

    if model:
        provider = _get_provider(model)
        if provider == "anthropic":
            return _interpret_anthropic(text, model=_strip_prefix(model), system_prompt=system_prompt), None
        return _interpret_openai_detail(text, model=model, include_thinking=include_thinking, system_prompt=system_prompt)
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        return _interpret_openai_detail(text, model=None, include_thinking=include_thinking, system_prompt=system_prompt)
    return _interpret_anthropic(text, system_prompt=system_prompt), None


def _interpret_anthropic(text: str, *, model: str | None = None, system_prompt: str) -> str:
    from anthropic import Anthropic

    client = Anthropic()
    resp = client.messages.create(
        model=model or DEFAULT_ANTHROPIC_MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": text}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            return block.text.strip()
    raise RuntimeError("Anthropic did not return text content")


def _interpret_openai_detail(
    text: str,
    *,
    model: str | None = None,
    include_thinking: bool = False,
    system_prompt: str,
) -> tuple[str, str | None]:
    from openai import OpenAI

    model = model or os.getenv("OPENAI_MODEL_STAGE1", "qwen3-api")

    if "/" in model:
        base_url = "https://integrate.api.nvidia.com/v1"
        api_key = os.getenv("NVIDIA_API_KEY", "")
    else:
        base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:18000/v3")
        api_key = os.getenv("OPENAI_API_KEY") or "none"

    client = OpenAI(base_url=base_url, api_key=api_key)

    is_qwen3 = "qwen3" in model.lower()
    if is_qwen3 and not include_thinking:
        user_content = f"/no_think {text}"
    else:
        user_content = text

    resp = client.chat.completions.create(
        model=model,
        max_tokens=MAX_TOKENS,
        temperature=0.3,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
    )
    raw = (resp.choices[0].message.content or "").strip()

    thinking: str | None = None
    m = re.search(r"<think>(.*?)</think>", raw, re.DOTALL)
    if m:
        thinking_text = m.group(1).strip()
        if include_thinking and thinking_text:
            thinking = thinking_text
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    ddl = re.sub(r"^```(?:\w+)?\s*\n?|\n?```$", "", raw, flags=re.MULTILINE).strip()
    return ddl, thinking
