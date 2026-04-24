"""学習モード: 記述サンプル自動生成 → 正規化DDL → EXAMPLE_POOL 追加を繰り返す。

表現の揺らぎ対応:
  VARIATION_STYLES を 1 イテレーションごとにローテーションして
  詩的・口語・抽象・自然現象・感覚表現など多様なスタイルをカバーする。

永続化:
  生成した (input, ddl) ペアを LEARNED_FILE に追記し、
  起動時に interpreter.EXAMPLE_POOL へ注入する。
  LEARNED_FILE 既定: /tmp/inku-learned.json
  永続化したい場合は環境変数 INKU_LEARNED_FILE に安定パスを指定する。
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from threading import Lock

from .interpreter import EXAMPLE_POOL, interpret_detail

LEARNED_FILE = Path(os.getenv("INKU_LEARNED_FILE", "/tmp/inku-learned.json"))
_learned_lock = Lock()

# 表現スタイルのリスト — 1イテレーションずつローテーションして多様性を確保
VARIATION_STYLES = [
    "詩的・比喩的（感情語を含んでよい: 美しい、儚い、激しい等）",
    "日常の口語表現（話し言葉、砕けた表現）",
    "抽象的な概念（孤独、静寂、緊張、始まり、終わり等）",
    "自然現象・天候・季節（嵐、霧、夜明け、波、冬の朝等）",
    "擬音語・感覚表現（ざわざわ、すっと、ぼんやり、ぴんと等）",
]

_GEN_SYSTEM_PROMPT = """あなたは inku DDL の多様な記述サンプル生成器。

inku DDL は「視覚的な短歌を書く言語」。記述者が実際に書きそうな多様な表現スタイルのテキストを 1 つ生成する。

条件:
- 最高 3 文。1 文でも可。短いほどよい
- 視覚的・造形的に描画できる内容（抽象アートとして表現可能なもの）
- 指定されたスタイルに沿って書く
- 出力はテキストのみ（説明・前置き・タイトル・コードブロック禁止）"""


def _extract_keywords(text: str) -> list[str]:
    words = re.findall(r"[぀-ヿ一-鿿]{2,}", text)
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        if w not in seen:
            seen.add(w)
            result.append(w)
    return result[:8]


def load_learned_examples() -> None:
    """起動時: LEARNED_FILE から EXAMPLE_POOL へ注入する。"""
    if not LEARNED_FILE.exists():
        return
    try:
        items = json.loads(LEARNED_FILE.read_text(encoding="utf-8"))
        for item in items:
            if isinstance(item, dict) and "input" in item and "output" in item:
                EXAMPLE_POOL.append(item)
    except Exception:  # noqa: BLE001
        pass


def _persist_learned() -> None:
    learned = [e for e in EXAMPLE_POOL if e.get("source") == "auto"]
    try:
        LEARNED_FILE.write_text(
            json.dumps(learned, ensure_ascii=False, indent=None),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass


def add_learned_example(input_text: str, ddl: str) -> dict:
    entry: dict = {
        "keywords": _extract_keywords(input_text),
        "input": input_text,
        "output": ddl,
        "source": "auto",
        "at": int(time.time()),
    }
    with _learned_lock:
        EXAMPLE_POOL.append(entry)
        _persist_learned()
    return entry


def learned_count() -> int:
    return sum(1 for e in EXAMPLE_POOL if e.get("source") == "auto")


def clear_learned_examples() -> None:
    with _learned_lock:
        to_remove = [e for e in EXAMPLE_POOL if e.get("source") == "auto"]
        for e in to_remove:
            EXAMPLE_POOL.remove(e)
        if LEARNED_FILE.exists():
            LEARNED_FILE.unlink(missing_ok=True)


# ── LLM バックエンド (interpreter.py と同じルーティング規則) ──────────────────

def _get_provider(model: str) -> str:
    if model.startswith("anthropic:"):
        return "anthropic"
    if "/" in model:
        return "nvidia"
    return "ovms"


def _strip_prefix(model: str) -> str:
    return model[len("anthropic:"):] if model.startswith("anthropic:") else model


def _generate_openai(style: str, model: str) -> str:
    from openai import OpenAI

    if "/" in model:
        base_url = "https://integrate.api.nvidia.com/v1"
        api_key = os.getenv("NVIDIA_API_KEY", "")
    else:
        base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:18000/v3")
        api_key = os.getenv("OPENAI_API_KEY") or "none"

    client = OpenAI(base_url=base_url, api_key=api_key)
    is_qwen3 = "qwen3" in model.lower()
    user_content = (
        f"/no_think 以下のスタイルで記述サンプルを 1 つ生成してください。\nスタイル: {style}"
        if is_qwen3
        else f"以下のスタイルで記述サンプルを 1 つ生成してください。\nスタイル: {style}"
    )
    resp = client.chat.completions.create(
        model=model,
        max_tokens=256,
        temperature=0.9,
        messages=[
            {"role": "system", "content": _GEN_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        stream=False,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # コードブロック除去
    raw = re.sub(r"^```(?:\w+)?\s*\n?|\n?```$", "", raw, flags=re.MULTILINE).strip()
    return raw


def _generate_anthropic(style: str, model: str) -> str:
    from anthropic import Anthropic

    client = Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=256,
        system=_GEN_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"以下のスタイルで記述サンプルを 1 つ生成してください。\nスタイル: {style}",
            }
        ],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            return block.text.strip()
    raise RuntimeError("Anthropic did not return text")


def generate_sample(style_idx: int, model: str | None) -> str:
    """指定スタイルで記述サンプルを 1 件生成する。"""
    style = VARIATION_STYLES[style_idx % len(VARIATION_STYLES)]
    if model:
        provider = _get_provider(model)
        if provider == "anthropic":
            return _generate_anthropic(style, _strip_prefix(model))
        return _generate_openai(style, model)
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        m = os.getenv("OPENAI_MODEL_STAGE1", "qwen3-api")
        return _generate_openai(style, m)
    return _generate_anthropic(style, "claude-opus-4-7")


def run_one_iteration(style_idx: int, model: str | None) -> dict:
    """1 イテレーション: サンプル生成 → interpret → EXAMPLE_POOL 追加。"""
    sample = generate_sample(style_idx, model)
    ddl, _ = interpret_detail(sample, model=model)
    entry = add_learned_example(sample, ddl)
    style_label = VARIATION_STYLES[style_idx % len(VARIATION_STYLES)].split("（")[0]
    return {
        "text": sample,
        "ddl": ddl,
        "style": style_label,
        "keywords": entry["keywords"],
    }
