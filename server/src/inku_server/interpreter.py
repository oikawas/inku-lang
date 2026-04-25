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

from .expansion import expand_input

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

# 属性保持 — 脱落禁止

感情語の除去だけが「正規化」であり、**属性の省略は誤り**。
入力に明示された以下の属性は必ず出力に含める:

- **いろ**: 青い・赤い・白い・灰色の → 省かない (「青いクレヨン線」→「青い」を落とさない)
- **てざわり**: クレヨン・筆・鉛筆・チョーク・縄 → 省かない
- **太さ・サイズ**: 細い・太い・小さな・大きな → 保持
- **方向・ばしょ**: 縦・横・放射状・中央・右端・右半分など → 保持
- **ゆらぎ**: 震える・波打つ・滲む・細かく → 数量文の後に別文で記述
- **配置パターン**: ランダム・格子・放射状・等間隔 → 保持

複数属性を持つ図形は 1 文に収める: 「青いクレヨンの太い縦線を横に三十本並べる。」

# 数量表現

数量詞が含まれる場合、**色・素材・方向・サイズとともに 1 文に**まとめよ。

- 「三本の竹を縦に並べる」→「縦の実線を横に三本並べる。」
- 「五つの赤い点をランダムに置く」→「赤い小さな円をランダムに五つ散らす。」
- 「背景を青のクレヨン線で埋め尽くす」→「青いクレヨンの縦線を横に三十本並べる。」
- 「たくさん」「多数」「無数」「いっぱい」→ 二十個程度 (上限500)
- 100本・200個などの具体的な数 → そのまま記述する

# ランダム配置

「ランダムに」「バラバラに」「散らばって」→ そのまま「ランダムに」「散らす」と記述する。

# 色とりどり・ランダム配色

「色とりどり」「カラフル」「様々な色」「虹色」「多色」→ 使う色を明示して「赤・青・緑・黒の色とりどりに」と記述する。
色の指定がない場合は「赤・青・緑・黒・灰の色とりどりに」をデフォルトとして使う。

# 背景色

「背景を塗りつぶす」「背景を○色にする」「暗い背景」→ 「背景を○色で塗りつぶす。」(独立した文として最初に置く)。
例: 「黒い背景に白い線」→ 「背景を黒で塗りつぶす。白い横線を中央に引く。」

# Saijiki (歳時記)

かたち: 円、楕円、三角、四角、線、弧
てざわり: 髪、鉛筆、ペン(既定)、ロットリング、クレヨン、チョーク、細筆、太筆、縄
つらなり: 実線(既定)、破線、点線、一点鎖線
いろ: 白、黒(既定)、青、赤、緑、灰
ゆらぎ: 細かく、大きく、ゆっくり、速く、揺れる、波打つ、震える、滲む
ばしょ: 上、下、中央、左端、右端、上端、下端、中心、隅

# 語彙展開ヒント

入力に `[語彙展開ヒント]` が付加されている場合は、ヒントを参考に非 Saijiki 語を歳時記語彙に変換せよ。
ヒントは候補であり、文脈・構図・バランスを考慮して最適なものを選ぶこと。

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
    # 属性保持: 素材 + 色 + 数量 + 配置
    {
        "keywords": ["クレヨン", "背景", "埋め", "埋め尽く", "全体", "びっしり"],
        "input": "背景を青のクレヨン線で埋め尽くす",
        "output": "青いクレヨンの縦線を横に三十本並べる。",
    },
    # 属性保持: 素材 + 太さ
    {
        "keywords": ["鉛筆", "細い", "ロットリング", "髪", "繊細"],
        "input": "鉛筆で細い縦線を十本引く",
        "output": "鉛筆の細い縦線を横に十本並べる。",
    },
    # 属性保持: ゆらぎ + 数量 (揺らぎは別文)
    {
        "keywords": ["震え", "震える", "揺れ", "揺らぐ", "波打つ", "ぶれ"],
        "input": "細かく震える縦線を三本並べる",
        "output": "縦の実線を横に三本並べる。細かく震える。",
    },
    # 属性保持: 色 + ばしょ + 数量
    {
        "keywords": ["右", "左", "半分", "端", "角", "隅"],
        "input": "右半分に赤い小さな円を二十個散らす",
        "output": "赤い小さな円を右半分にランダムに二十個散らす。",
    },
    # 属性保持: 素材 + 太さ + 色 + 大量
    {
        "keywords": ["クレヨン", "青", "300", "三百", "百", "大量", "密"],
        "input": "三百本の青いクレヨン線を横に並べる",
        "output": "青いクレヨンの縦線を横に三百本並べる。",
    },
    # 属性保持: 複数要素の合成 (地・天)
    {
        "keywords": ["地平", "空", "地面", "境界", "水平線", "丘", "地"],
        "input": "地平線の向こうに広がる空",
        "output": "画面下端に灰色の横線を一本引く。上半分に白い大きな四角を置く。",
    },
    # 属性保持: チョーク + 色 + ゆらぎ
    {
        "keywords": ["チョーク", "黒板", "白", "ざらざら", "かすれ", "粗"],
        "input": "チョークで白い丸を描く",
        "output": "中央に白いチョークの円を置く。境界が滲む。",
    },
    # 背景塗りつぶし
    {
        "keywords": ["背景", "塗りつぶす", "黒板", "暗い", "暗く", "ダーク", "黒い背景"],
        "input": "黒い背景に白い線を引く",
        "output": "背景を黒で塗りつぶす。白い横線を中央に引く。",
    },
    {
        "keywords": ["背景", "赤", "青", "緑", "灰", "空色", "地色"],
        "input": "青い背景に黒い縦線を五本引く",
        "output": "背景を青で塗りつぶす。黒い縦線を横に五本並べる。",
    },
    # 色とりどり・ランダム配色
    {
        "keywords": ["色とりどり", "カラフル", "虹", "様々な色", "多色", "いろいろな色"],
        "input": "色とりどりの小さな円を散らす",
        "output": "赤・青・緑・黒・灰の色とりどりの小さな円をランダムに二十個散らす。半径は0.03。",
    },
    {
        "keywords": ["色とりどり", "カラフル", "放射", "虹", "輪"],
        "input": "色とりどりの点を放射状に並べる",
        "output": "赤・青・緑・黒の色とりどりの小さな円を放射状に八つ並べる。",
    },
]

# api.py が import する SYSTEM_PROMPT — プレフィックスを公開する
SYSTEM_PROMPT = SYSTEM_PROMPT_PREFIX + "\n\n# 変換例\n\n(推論時に入力関連の例を動的に選択して注入)"


def _select_examples(text: str, k: int = 5) -> str:
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


def _build_system_prompt(text: str, k: int = 5) -> str:
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
    expanded = expand_input(text)  # 非 Saijiki 語があれば展開ヒントを付加

    if model:
        provider = _get_provider(model)
        if provider == "anthropic":
            return _interpret_anthropic(expanded, model=_strip_prefix(model), system_prompt=system_prompt), None
        return _interpret_openai_detail(expanded, model=model, include_thinking=include_thinking, system_prompt=system_prompt)
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        return _interpret_openai_detail(expanded, model=None, include_thinking=include_thinking, system_prompt=system_prompt)
    return _interpret_anthropic(expanded, system_prompt=system_prompt), None


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
