"""Refinements that change one part of a saved Score, decided by the shared core.

Changing the touches (てざわり), the support (じ) or the color arrangement swaps
one part of the saved Score and draws it again with the parent's seed. Server,
Android and Swift used to keep their own copies of these rules; the rules now
live in the shared core (``inku-pipeline/src/saved_variants.rs``), and
``server/tests/data/saved-variant-cases.json`` holds the rows every host checks.
This module only carries a request to the core and its answer back.
"""

from __future__ import annotations

import importlib
import json
from functools import lru_cache
from types import ModuleType
from typing import Any


class SavedVariantRefused(ValueError):
    """The core gave no answer; ``detail`` is the message Server shows."""

    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


@lru_cache(maxsize=1)
def _native() -> ModuleType:
    return importlib.import_module("inku_render")


def ask(action: str, **fields: Any) -> dict:
    request = json.dumps({"action": action, **fields}, ensure_ascii=False).encode("utf-8")
    answer = json.loads(_native().pipeline_saved_variants(request))
    if "error" in answer:
        raise RuntimeError(f"saved variant request failed: {answer['error']}")
    if answer.get("outcome") == "refused":
        raise SavedVariantRefused(str(answer.get("reason")), str(answer.get("detail")))
    return answer
