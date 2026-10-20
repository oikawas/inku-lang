"""Juxtaposition: a sentence from the author's other works, added after a work's description.

A model picks four candidate sentences; the author chooses one, and the work is
redrawn from the longer description through the ordinary description fork.

The rules are the shared core's (``inku-pipeline/src/juxtaposition.rs``, moved
there from this module and from Web on 2026-10-20 so that macOS and Android ask
the same copy): which sentences are offered and how they are told apart, the
prompt, how an answer is checked, and how the chosen sentence is joined. This
module carries the requests to the core, draws the image, sends the prompt and
gives the answer back. It saves nothing.
"""

from __future__ import annotations

import importlib
import json
import random
from collections.abc import Callable, Iterable
from functools import lru_cache
from types import ModuleType
from typing import Any

from .autonomous_refine import _png_data_url
from .model_settings import provider_for_model
from .vision_client import vision_connection, vision_text

CHOICES = 4


class JuxtapositionAnswerError(RuntimeError):
    """The model named sentences that were not offered, and did so again when told."""


@lru_cache(maxsize=1)
def _native() -> ModuleType:
    return importlib.import_module("inku_render")


def _core(action: str, **fields: Any) -> dict[str, Any]:
    request = json.dumps({"action": action, **fields}, ensure_ascii=False).encode("utf-8")
    answer = json.loads(_native().pipeline_juxtaposition(request))
    if "error" in answer:
        raise RuntimeError(f"juxtaposition request failed: {answer['error']}")
    return answer


def same_text(a: str, b: str) -> bool:
    """Whether two sentences are one: the same poem spelt with kana or kanji counts once."""
    return bool(_core("same", a=a, b=b)["same"])


def gather_candidates(
    sources: Iterable[tuple[str, str]],
    *,
    description: str,
    lineage: Iterable[str] = (),
    added: Iterable[str] = (),
    exclude: Iterable[str] = (),
    rng: random.Random | None = None,
    limit: int,
) -> list[dict[str, Any]]:
    """At most `limit` candidate sentences, in a fresh random order.

    `sources` pairs a work id with its description, labels already removed. The
    core keeps the sentences in the description's language that are not the
    work's own, its lineage's or a sentence its lineage added or that was shown
    before (`exclude`), and draws their order from the seed given here.
    """
    seed = (rng or random.SystemRandom()).getrandbits(64)
    answer = _core(
        "gather",
        sources=[{"id": history_id, "text": text} for history_id, text in sources],
        description=description, lineage=list(lineage), added=list(added), exclude=list(exclude),
        seed=str(seed), limit=limit,
    )
    return answer["candidates"]


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
    written: str | None = None,
) -> dict[str, Any]:
    """Four sentences the model would add, with why, in the order it picked them.

    An answer that names a sentence not offered, repeats one or leaves a reason
    empty is sent back once with the reason. Each choice carries `position`,
    where the sentence stood in the shuffled list (0 the head, 1 the tail), and
    `joined`: the sentence after the description as the work keeps it
    (`written`, labels and all), which the model reads without its labels.
    """
    if len(candidates) < CHOICES:
        raise ValueError("not enough candidate sentences")
    read = reader or _ask
    image = _png_data_url(svg)
    stored = description if written is None else written
    reason = None
    for _attempt in range(2):
        prompt = _core("prompt", language=language, description=description, lineage=list(lineage),
                       candidates=candidates, resend=reason)
        answer = read(model=model, system=prompt["system"], text=prompt["text"], image=image, settings=settings)
        checked = _core("check", language=language, answer=answer, candidates=candidates, description=stored)
        if checked["outcome"] == "ok":
            return {"choices": checked["choices"], "candidates": checked["candidates"], "model": model}
        reason = checked["detail"]
    raise JuxtapositionAnswerError(reason)
