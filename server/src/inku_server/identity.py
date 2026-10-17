"""A work's identities, computed by the shared core.

``dh1`` (description) and ``rh3`` (render) are stored in every history row.
Server, Android and Swift once each kept their own copy of these rules and the
copies drifted, so all of them now ask the shared core, which reproduces the
rules Server defined here (NFC, one kind of line break, Python's ``strip()``;
``json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)``).
``server/tests/data/identity-cases.json`` holds the rows every host checks.
"""

from __future__ import annotations

import importlib
import json
from functools import lru_cache
from types import ModuleType
from typing import Any

# The members of a history item that the render identity reads.
_RENDER_HASH_KEYS = (
    "score",
    "render_seed",
    "render_wild",
    "render_engine_id",
    "render_engine_version",
    "render_color_catalog_id",
    "catalog_id",
)


@lru_cache(maxsize=1)
def _native() -> ModuleType:
    return importlib.import_module("inku_render")


def description_hash(text: str) -> str:
    # dh1 is deterministic identity, not encryption, authentication, or proof of ownership.
    return _native().pipeline_description_hash(text)


def canonical_json(value: Any) -> str:
    """The canonical JSON Server hashes, written by the shared core."""
    written = _native().pipeline_canonical_json(json.dumps(value, ensure_ascii=False))
    if written is None:
        raise ValueError("value cannot be written as canonical JSON")
    return written


def render_hash(item: dict) -> str:
    """``rh3`` for one history item."""
    present = {key: item[key] for key in _RENDER_HASH_KEYS if key in item}
    hashed = _native().pipeline_render_hash(json.dumps(present, ensure_ascii=False))
    if hashed is None:
        raise ValueError("history item cannot be given a render identity")
    return hashed
