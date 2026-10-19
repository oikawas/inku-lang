"""Juxtaposition: a sentence from the author's other works, added after a work's description.

A model picks four candidate sentences; the author chooses one, and the work is
redrawn from the longer description through the ordinary description fork. This
module gathers the candidates and asks the model. It saves nothing.

The rules follow the prototype that measured this (step 1d of the autonomous
refinement study):

- A candidate is the first sentence of another work's description, labels removed.
- One sentence counts once. Spacing, the "(AI)" mark and the kana or kanji
  spelling of one poem do not make a new sentence (`same_text`).
- The candidates are shuffled for every request. The prototype's models leaned
  to the head of a long list, so a fixed order would choose for them.
- Sentences the lineage already added are left out. The prototype's models kept
  coming back to one sentence across works.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from .autonomous_refine import _json_body, _png_data_url
from .model_settings import provider_for_model
from .vision_client import vision_connection, vision_text

CHOICES = 4
CANDIDATE_LIMIT = 600  # the prototype offered 549 sentences, about 18k tokens
SAME_TEXT = 0.8  # share of two-character pieces at which two sentences are the same one

_SENTENCE = re.compile(r"(.+?(?:[。！？]|[.!?](?=\s|$)))")
_AI_MARK = re.compile(r"[(（]AI[)）]")
_SPACE = re.compile(r"\s+")
_JAPANESE = re.compile(r"[぀-ヿ㐀-鿿]")


class JuxtapositionAnswerError(RuntimeError):
    """The model named sentences that were not offered, and did so again when told."""


def first_sentence(text: str) -> str:
    stripped = (text or "").strip()
    match = _SENTENCE.match(stripped)
    return (match.group(1) if match else stripped).strip()


def text_key(text: str) -> str:
    """The form two sentences are compared in: no spacing, no "(AI)" mark."""
    return _SPACE.sub("", _AI_MARK.sub("", text or ""))


def _pieces(key: str) -> frozenset[str]:
    return frozenset(key[index:index + 2] for index in range(len(key) - 1)) or frozenset({key})


def _alike(key: str, pieces: frozenset[str], other_key: str, other_pieces: frozenset[str]) -> bool:
    if key == other_key:
        return True
    shared = len(pieces & other_pieces)
    return shared / (len(pieces) + len(other_pieces) - shared) >= SAME_TEXT


def same_text(a: str, b: str) -> bool:
    """Whether two sentences are one: the same poem spelt with kana or kanji counts once."""
    key_a, key_b = text_key(a), text_key(b)
    return _alike(key_a, _pieces(key_a), key_b, _pieces(key_b))


def language_of(text: str) -> str:
    return "ja" if _JAPANESE.search(text or "") else "en"


def _twin(kept: list[dict[str, Any]], index: dict[str, list[int]], key: str, pieces: frozenset[str]) -> int | None:
    """The kept sentence this one repeats, if any.

    Counting the pieces each kept sentence shares with this one finds the likely
    twins without comparing every pair. The share can only fall as the count
    falls, so the search stops at the first count too small to reach the line.
    """
    shared = Counter(position for piece in pieces for position in index.get(piece, ()))
    for position, count in shared.most_common():
        if count / len(pieces) < SAME_TEXT:
            return None
        other = kept[position]
        if _alike(key, pieces, other["key"], other["pieces"]):
            return position
    return None


def gather_candidates(
    sources: Iterable[tuple[str, str]],
    *,
    description: str,
    lineage: Iterable[str] = (),
    added: Iterable[str] = (),
    exclude: Iterable[str] = (),
    rng: random.Random | None = None,
    limit: int = CANDIDATE_LIMIT,
) -> list[dict[str, Any]]:
    """Candidate sentences, in a fresh random order.

    `sources` pairs a work id with its description, labels already removed. Only
    sentences in the description's language are offered. A sentence is left out
    when it is the work's own description, any description of its lineage, a
    sentence the lineage already added, or one in `exclude` (shown before). Each
    candidate carries the ids of every work it came from.
    """
    language = language_of(description)
    by_sentence: dict[str, list[str]] = {}
    for history_id, text in sources:
        sentence = first_sentence(text)
        if sentence and language_of(sentence) == language:
            by_sentence.setdefault(sentence, []).append(history_id)
    avoid = [text for text in (description, *lineage) if text]
    avoid += [first_sentence(text) for text in avoid]
    avoid += [text for text in (*added, *exclude) if text]
    avoid_keys = [(key, _pieces(key)) for key in {text_key(text) for text in avoid}]
    kept: list[dict[str, Any]] = []
    index: dict[str, list[int]] = defaultdict(list)
    # A sentence opening with a number such as "#25 " is looked at last, so that the
    # same sentence without the number is the one that stays.
    for sentence in sorted(by_sentence, key=lambda text: (text.startswith("#"), text)):
        key = text_key(sentence)
        pieces = _pieces(key)
        if any(_alike(key, pieces, other_key, other_pieces) for other_key, other_pieces in avoid_keys):
            continue
        twin = _twin(kept, index, key, pieces)
        if twin is not None:
            kept[twin]["history_ids"] += by_sentence[sentence]
            continue
        for piece in pieces:
            index[piece].append(len(kept))
        kept.append({"sentence": sentence, "key": key, "pieces": pieces, "history_ids": list(by_sentence[sentence])})
    draw = rng or random.Random()
    chosen = list(range(len(kept)))
    if len(chosen) > limit:
        chosen = draw.sample(chosen, limit)
    draw.shuffle(chosen)
    return [{"id": f"c{position + 1:04d}", "sentence": kept[position]["sentence"],
             "history_ids": sorted(kept[position]["history_ids"])} for position in chosen]


def _system(language: str) -> str:
    if language == "en":
        return (
            "You help an author take their own work further. The author creates; everything you offer is a proposal. "
            "You never score, praise or condemn, and never use evaluative words such as better, improved, beautiful, "
            "appealing or balanced. "
            "The aim is to shake the work loose: the author is stuck with it. Choose a sentence from the author's other "
            "works to be added, unchanged, after this work's description. Neither the description nor the chosen "
            "sentence is rewritten. As a juxtaposition, two things set side by side to make a new meaning, choose a "
            "sentence that moves the idea of the work itself in a direction the author would not think of. Choose four "
            "candidates in the order you would pick them, and for each write in one sentence how adding it moves the "
            'idea of the work. Return JSON only: {"choices": [{"id": "...", "reason": "..."}]} with exactly four items.'
        )
    return (
        "あなたは、作者が自分の作品をさらに深めるのを手伝う助手です。創作の主体は作者で、あなたの手はすべて提案です。"
        "良し悪し・点数・好み・称賛・否定は書きません。「良くなる」「改善」「美しい」「魅力的」「バランスが良い」などの評価の語を"
        "使いません。"
        "目的は「揺さぶり」です。作者は、この作品で煮詰まっています。作者のほかの作品の記述から一文を選び、この作品の記述の"
        "後ろに、そのまま足します。元の記述も、選んだ一文も書き換えません。二つのものを並べて新しい意味を生む「取り合わせ」"
        "として、作者が自分では思いつかない方向へ、作品の考えそのものを動かす一文を選びます。候補から4つを、選びたい順に"
        "並べます。それぞれに、足すと作品の考えがどう動くかを1文で書きます。"
        '答えは JSON だけを返します：{"choices": [{"id": "…", "reason": "…"}]}（choices はちょうど4つ）。'
    )


def _message(language: str, description: str, lineage: list[str], candidates: list[dict[str, Any]]) -> str:
    colon = ": " if language == "en" else "："
    listed = "\n".join(f"{candidate['id']}{colon}{candidate['sentence']}" for candidate in candidates)
    if language == "en":
        steps = "\n".join(f"{number}. {text}" for number, text in enumerate(lineage, start=1)) or "(the work is its own root)"
        return (
            f"## The picture\nThe attached image.\n\n## The description\n{description}\n\n"
            f"## The lineage's descriptions (root to this work)\n{steps}\n\n"
            f"## Candidate sentences (the first sentence of the author's other works; {len(candidates)}; "
            f"each line starts with its id)\n{listed}\n\n"
            "## Answer\n- choices: four, in the order you would pick them. For each:\n"
            "  - id: the candidate's id, copied from the head of its line.\n"
            "  - reason: how adding this sentence moves the idea of the work (one sentence, no evaluative words).\n"
            "- The four ids differ."
        )
    steps = "\n".join(f"{number}. {text}" for number, text in enumerate(lineage, start=1)) or "（系譜は今の作品だけ）"
    return (
        f"## 今の画\n添えた画像のとおり。\n\n## 今の記述\n{description}\n\n## 系譜の記述（根から今の作品まで）\n{steps}\n\n"
        f"## 候補の一文（作者のほかの作品の記述の、最初の一文。{len(candidates)}件。行の頭は番号）\n{listed}\n\n"
        "## 答えること\n- choices：4つ。選びたい順に並べる。各項に次を書く。\n"
        "  - id：候補の番号（行の頭の番号をそのまま写す）。\n"
        "  - reason：この一文を足すと、作品の考えがどう動くか（1文。評価の語を使わない）。\n"
        "- 4つの id は互いに違う。"
    )


def _checked(raw: str, offered: dict[str, dict[str, Any]], language: str) -> tuple[list[tuple[str, str]] | None, str]:
    """The four (id, reason) pairs, or why the answer cannot be used."""
    english = language == "en"
    try:
        parsed = json.loads(_json_body(raw))
    except json.JSONDecodeError:
        return None, "the answer is not JSON" if english else "答えが JSON でない"
    choices = parsed.get("choices") if isinstance(parsed, dict) else None
    if not isinstance(choices, list) or len(choices) != CHOICES:
        return None, (f"choices does not hold exactly {CHOICES} items" if english
                      else f"choices がちょうど{CHOICES}つでない")
    pairs = [(str(choice.get("id") or "").strip(), str(choice.get("reason") or "").strip())
             if isinstance(choice, dict) else ("", "") for choice in choices]
    missing = [choice_id or "—" for choice_id, _ in pairs if choice_id not in offered]
    if missing:
        return None, (f"ids that were not offered ({', '.join(missing)}); copy the id at the head of a line" if english
                      else f"候補に無い番号（{'・'.join(missing)}。行の頭の番号をそのまま写す）")
    if len({choice_id for choice_id, _ in pairs}) != CHOICES:
        return None, "an id appears more than once" if english else "同じ番号が2回以上ある（4つは互いに違う番号にする）"
    if any(not reason for _, reason in pairs):
        return None, "a reason is empty" if english else "理由が空の項がある"
    return pairs, ""


def _resend_note(language: str, reason: str) -> str:
    if language == "en":
        return f"\n\n## About the previous answer\nIt could not be used: {reason}. Answer again by the rules above."
    return f"\n\n## 前の答えについて\n前の答えは使えなかった：{reason}。上の決まりどおりに答え直してください。"


def _ask(*, model: str, system: str, text: str, image: str, settings: dict[str, Any]) -> str:
    provider, model_id = provider_for_model(model, stage="stage1", settings=settings)
    return vision_text(
        vision_connection(provider, settings), model_id, system=system, text=text, images=[image],
        temperature=0.35, max_tokens=1200,
    )


def suggest_juxtaposition(
    *,
    svg: str,
    description: str,
    lineage: list[str],
    candidates: list[dict[str, Any]],
    model: str,
    language: str,
    settings: dict[str, Any],
    reader: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """Four sentences the model would add, with why, in the order it picked them.

    An answer that names a sentence not offered, repeats one or leaves a reason
    empty is sent back once with the reason. `position` is where the sentence
    stood in the shuffled list (0 the head, 1 the tail), kept so that a lean to
    the head of the list can be counted later.
    """
    if len(candidates) < CHOICES:
        raise ValueError("not enough candidate sentences")
    read = reader or _ask
    offered = {candidate["id"]: candidate for candidate in candidates}
    system = _system(language)
    text = _message(language, description, lineage, candidates)
    image = _png_data_url(svg)
    pairs, reason = None, ""
    for attempt in range(2):
        prompt = text if attempt == 0 else text + _resend_note(language, reason)
        pairs, reason = _checked(read(model=model, system=system, text=prompt, image=image, settings=settings),
                                 offered, language)
        if pairs is not None:
            break
    if pairs is None:
        raise JuxtapositionAnswerError(reason)
    order = {candidate["id"]: position for position, candidate in enumerate(candidates)}
    last = max(1, len(candidates) - 1)
    return {
        "choices": [
            {"sentence": offered[choice_id]["sentence"], "reason": why[:2000],
             "history_ids": list(offered[choice_id]["history_ids"]), "rank": rank,
             "position": round(order[choice_id] / last, 3)}
            for rank, (choice_id, why) in enumerate(pairs, start=1)
        ],
        "candidates": len(candidates),
        "model": model,
    }
