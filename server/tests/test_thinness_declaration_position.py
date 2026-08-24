"""Pin the declaration position of `thinness` (I-036 / I-037 / I-038).

Stage 2 preserves tool-schema declaration order, and optional fields are filled
more often when they appear later. `thinness` reached only 3-18% when placed
immediately after `weight` at position 14.

There is only one final slot. In v2.9.5, `thinness` took it from `surface`, whose
delivery fell from 92% to 42%, cutting Stage 2 output roughly in half across 168
measured runs on 2026-08-02. Therefore `thinness` stays immediately before
`surface`, leaving the final slot to `surface`.

Position changes the drawing. Neither the frozen corpus nor
`check_frozen_corpora.py` runs Stage 2, so these checks are the only gate for this
property. P-1 fails if `thinness` moves last, P-2 fails if it returns beside
`weight`, and P-4 fails if `sort_keys` returns.

Declaration order has three copies: Server, Kotlin, and the Android fixture.
Android unit tests cover Kotlin against the fixture; P-6 and P-7 cover the two
edges originating at the Server.
"""

from __future__ import annotations

import json
import pathlib
from contextlib import contextmanager
from typing import Iterator

import pytest

from inku_server import composer
from inku_server.schema import Instruction, Score

ROOT = pathlib.Path(__file__).resolve().parents[2]

# `android/` is permanently excluded from every pentala sync path (standing rule
# 2026-07-30), so on the deployed server the whole tree is absent. Key the skip to
# the DIRECTORY, not to the files below: wherever `android/` exists -- every
# checkout, every developer machine, CI -- these assertions still run, and a moved
# or renamed file is a failure rather than a skip.
ANDROID_TREE = ROOT / "android"
android_only = pytest.mark.skipif(
    not ANDROID_TREE.is_dir(),
    reason="android/ is never synced to the server; the port is checked where the tree exists",
)

KOTLIN_SCHEMA = (
    ANDROID_TREE
    / "app/src/main/java/app/inku/mobile/pipeline/ServerScoreSchemaJson.kt"
)
ANDROID_FIXTURE = (
    ANDROID_TREE / "app/src/test/resources/server_reference/score_schema_contract.json"
)

# Engine 16 stage 3 introduced this body; the ordering contract changes no byte of it.
THINNESS_SCHEMA = {
    "anyOf": [
        {"enum": ["fine", "extra_fine"], "type": "string"},
        {"type": "null"},
    ],
    "default": None,
    "description": (
        "線の細さ。道具の既定より細く引く指定。fine=細い / extra_fine=極細。"
        "省略時は道具の既定。太くする指定は無い"
    ),
    "title": "Thinness",
}


def _instruction_properties() -> dict[str, object]:
    schema = composer._score_tool_schema()
    return schema["properties"]["instructions"]["items"]["properties"]


@contextmanager
def thinness_at(index: int) -> Iterator[None]:
    """Move `thinness` to an index and restore the original order on exit.

    Changing only `Instruction.model_fields` does not reach `_score_tool_schema()`.
    `Score` must also be rebuilt, or the field appears in
    `Instruction.model_json_schema()` but not in the tool schema, the mismatch
    that caused I-036.
    """
    original = dict(Instruction.model_fields)
    fields = dict(original)
    held = fields.pop("thinness")
    keys = list(fields)
    assert 0 <= index <= len(keys), f"index {index} out of range for {len(keys)} fields"
    rebuilt = {k: fields[k] for k in keys[:index]}
    rebuilt["thinness"] = held
    rebuilt.update({k: fields[k] for k in keys[index:]})
    try:
        Instruction.model_fields.clear()
        Instruction.model_fields.update(rebuilt)
        Instruction.model_rebuild(force=True)
        Score.model_rebuild(force=True)
        yield
    finally:
        Instruction.model_fields.clear()
        Instruction.model_fields.update(original)
        Instruction.model_rebuild(force=True)
        Score.model_rebuild(force=True)


def test_surface_is_declared_last() -> None:
    """P-1 final slot: `surface` is the last `Instruction` declaration.

    There is only one final slot. Giving it to another field cuts `surface`
    delivery from 92% to 42% and halves Stage 2 output. This check fails whenever
    a future field is appended, independently of P-2, so the regression cannot
    pass silently.
    """
    properties = _instruction_properties()
    assert len(properties) == 25
    assert list(properties)[-1] == "surface"
    assert list(Instruction.model_fields)[-1] == "surface"


def test_thinness_is_declared_immediately_before_surface() -> None:
    """P-2 position: keep `thinness` immediately before the final `surface`."""
    properties = list(_instruction_properties())
    assert properties[-2:] == ["thinness", "surface"]
    assert list(Instruction.model_fields)[-2:] == ["thinness", "surface"]


def test_thinness_schema_body_is_unchanged() -> None:
    """P-3 body: type, default, and description remain those of Engine 16."""
    assert _instruction_properties()["thinness"] == THINNESS_SCHEMA


def test_stage2_digest_sees_declaration_order() -> None:
    """P-4 fingerprint: declaration reordering changes `stage2_prompt_digest`.

    `sort_keys=True` destroys order, so this requires the digest to preserve it.
    """
    def sorted_tool_json() -> str:
        return json.dumps(composer._submit_tool(), ensure_ascii=False, sort_keys=True)

    system_prompt = "order-probe"
    at_last = composer._stage2_prompt_digest(system_prompt)
    sorted_at_last = sorted_tool_json()
    with thinness_at(14):
        assert list(_instruction_properties()).index("thinness") == 14
        after_weight = composer._stage2_prompt_digest(system_prompt)
        sorted_after_weight = sorted_tool_json()
    assert at_last != after_weight
    # Only order moved. Sorting keys makes both forms equal, which explains the old blind digest.
    assert sorted_at_last == sorted_after_weight
    assert composer._stage2_prompt_digest(system_prompt) == at_last


def _kotlin_instruction_order() -> list[str]:
    """The port keeps a full copy of the tool schema as one raw string literal."""
    parts = KOTLIN_SCHEMA.read_text(encoding="utf-8").split('"""')
    assert len(parts) == 3, f"expected one raw string literal in {KOTLIN_SCHEMA.name}"
    schema = json.loads(parts[1])
    return list(schema["properties"]["instructions"]["items"]["properties"])


@android_only
def test_android_schema_copy_keeps_the_server_declaration_order() -> None:
    """P-6 Server-to-Kotlin edge: the copy preserves Server declaration order.

    The port schema is intentionally a subset (I-008), so it must be an ordered
    subsequence rather than equal. If only the Server is repaired, Android's local
    LLM path otherwise remains truncated. No other check covered this edge.
    """
    server_order = list(_instruction_properties())
    kotlin_order = _kotlin_instruction_order()
    assert set(kotlin_order) <= set(server_order)
    assert kotlin_order == [k for k in server_order if k in set(kotlin_order)]
    assert kotlin_order[-2:] == ["thinness", "surface"]


@android_only
def test_android_fixture_tables_keep_the_server_declaration_order() -> None:
    """Keep both historical Android order tables aligned with the Server schema.

    The Android corpus is now immutable and manifest-owned, so Stage 6 does not
    rebake it. Both stored order tables still describe the compatibility input
    and must agree with the Server declaration until shared schema generation
    replaces them.
    """
    fixture = json.loads(ANDROID_FIXTURE.read_text(encoding="utf-8"))
    server_order = list(_instruction_properties())
    dump_order = list(
        json.loads(
            Instruction.model_validate({"primitive": "line"}).model_dump_json(
                by_alias=True
            )
        )
    )
    assert fixture["instruction_property_order"] == server_order
    assert fixture["dump_property_order"] == dump_order
    assert server_order[-2:] == ["thinness", "surface"]
    assert dump_order[-2:] == ["thinness", "surface"]
