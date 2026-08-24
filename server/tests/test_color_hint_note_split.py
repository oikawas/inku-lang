"""Contract tests for separating machine diagnostics from color descriptions."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from inku_server import composer
from inku_server.coerce import coerce_score
from inku_server.renderer import render
from inku_server.schema import Instruction, Score


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_SOURCE = ROOT / "src" / "inku_server" / "coerce" / "compose.py"
NORMALIZE_SOURCE = ROOT / "src" / "inku_server" / "coerce" / "normalize.py"
# The ten API-side write sites live in the render router since api.py was split
# into routers; the census below counts the same ten.
API_SOURCE = ROOT / "src" / "inku_server" / "api_core" / "routers" / "render.py"
GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "coerce_golden.json"

DIAGNOSTIC_FRAGMENTS = (
    "coverage from ddl clause",
    "fallback from",
    "inferred from ddl",
    "made visible",
    "density clustered",
    "density capped",
    "original count",
    "governed",
    "tempered",
    "restored",
    "promoted to primary",
    "constraint enforced",
    "ma pressure",
    "visual event",
    "counterweight preserved",
)

# H-20 joined this list at ddl-engine 9, which is when the two color stages were
# put in the order they read in: the repair puts a color in a cycle, and only
# then does the promotion look through the cycles for it. Before that a delivered
# color could not be promoted until a second pass over the same DDL, so H-01 and
# H-20 each came out of coerce differently the second time. H-08, H-12 and
# S-background-governor are still outside this list, for an unrelated reason --
# what moves on their second pass is geometry and `weight`, not color.
IDEMPOTENT_CASE_IDS = (
    "H-01", "H-02", "H-03", "H-05", "H-06", "H-07",
    "H-09", "H-11", "H-13", "H-14", "H-16", "H-18", "H-20",
    "S-crescent-sensory", "S-dedupe-identical", "S-explicit-constraint",
    "S-filled-tempering", "S-invalid-relation", "S-literal-grid",
    "S-per-instruction-density", "S-presence-auxiliary", "S-presence-from-ddl",
    "S-semantic-event", "S-shape-delivery", "S-spontaneous-grid",
    "S-structural-duplicate", "S-surface-tension", "S-total-density",
    "S-visual-event-type",
)


def _golden_cases() -> dict[str, dict]:
    return json.loads(GOLDEN_PATH.read_text())["cases"]


def _replay(case: dict) -> Score:
    case_input = case["input"]
    return coerce_score(
        Score.model_validate(case_input["score"]),
        ddl=case_input["ddl"],
    )


def test_note_is_the_second_instruction_field_and_stage2_is_told_not_to_emit_it() -> None:
    fields = list(Instruction.model_fields)
    properties = composer._score_tool_schema()["properties"]["instructions"]["items"]["properties"]

    assert fields[:2] == ["primitive", "note"]
    assert list(properties)[:2] == ["primitive", "note"]
    assert properties["note"]["description"] == "機械が付ける処理注記。描画に影響しない。出力しないこと"
    assert "note は機械専用の処理注記。Stage 2 からは絶対に出力しない" in composer.SYSTEM_PROMPT
    assert "Never emit it from Stage 2" in composer.SYSTEM_PROMPT_EN


def test_saved_scores_validate_with_or_without_note() -> None:
    saved = {
        "instructions": [
            {
                "primitive": "line",
                "from": [0.1, 0.5],
                "to": [0.9, 0.5],
                "color_hint": "cold blue-gray",
            }
        ]
    }
    old_score = Score.model_validate(saved)
    saved["instructions"][0]["note"] = "machine annotation"
    new_score = Score.model_validate(saved)

    assert old_score.instructions[0].note is None
    assert new_score.instructions[0].note == "machine annotation"


def test_all_coerce_golden_inputs_are_idempotent_after_one_ddl_pass() -> None:
    cases = _golden_cases()
    for case_id in IDEMPOTENT_CASE_IDS:
        case = cases[case_id]
        first = _replay(case)
        case_input = case["input"]
        second = coerce_score(
            first,
            ddl=case_input["ddl"],
        )
        assert second.model_dump(mode="json", by_alias=True) == first.model_dump(
            mode="json", by_alias=True
        ), case_id


def test_h01_promotes_the_delivered_color_on_the_first_pass() -> None:
    """The positive half of the ordering: one pass is enough (ddl-engine 9).

    H-01's DDL asks for yellow and its score has none, so this layer delivers
    yellow into a cycle and then promotes it to a primary stroke. Until engine 9
    the promotion ran first and could only see cycles that already existed, so
    the promotion landed on the *second* pass and coerce was not a fixed point.
    Asserting only "H-01 is idempotent" would pass an implementation that never
    promotes at all, so the promotion is named here.

    The note carries the weight from ddl-engine 10 on. H-01 names one color, so
    the exit branch reduces the cycle to that color and writes `color` itself --
    which means `color == "yellow"` no longer says the promotion ran. Only
    `_with_primary_color_delivery` writes the promotion note, and only when it
    moved a color, so that line is what still separates "promoted on the first
    pass" from "not promoted at all".
    """
    case = _golden_cases()["H-01"]

    first = _replay(case)
    data = first.model_dump(mode="json", by_alias=True)["instructions"][0]

    assert data["color"] == "yellow"
    assert "yellow restored in color_cycle from DDL color intent" in data["note"]
    assert "yellow promoted to primary stroke from DDL color intent" in data["note"]
    # Both ran, and then the exit folded what they built: one named color.
    assert data["arrangement"]["color_cycle"] == ["yellow"]
    assert "color_cycle reduced to yellow alone as the DDL names it alone" in data["note"]


def test_ddl_coerce_outputs_keep_machine_diagnostics_out_of_color_hint() -> None:
    seen_notes = 0
    seen_color_hints = 0
    for case_id, case in sorted(_golden_cases().items()):
        score = _replay(case)
        for instruction in score.instructions:
            if instruction.note:
                seen_notes += 1
            if not instruction.color_hint:
                continue
            seen_color_hints += 1
            lowered = instruction.color_hint.lower()
            offenders = [fragment for fragment in DIAGNOSTIC_FRAGMENTS if fragment in lowered]
            assert offenders == [], f"{case_id}: {instruction.color_hint}"

    assert seen_notes > 0
    assert seen_color_hints > 0


def test_word_boundary_stops_restored_from_selecting_red_without_moving_the_seed() -> None:
    diagnostic = "motion floor restored as a small directional trace"
    before = Instruction.model_validate(
        {
            "primitive": "line",
            "from": [0.1, 0.5],
            "to": [0.9, 0.5],
            "color": "gray",
            "color_hint": diagnostic,
        }
    )
    after = Instruction.model_validate(
        {
            "primitive": "line",
            "from": [0.1, 0.5],
            "to": [0.9, 0.5],
            "color": "gray",
            "note": diagnostic,
        }
    )

    before_svg = render(Score(instructions=[before]), render_seed=4242)
    after_svg = render(Score(instructions=[after]), render_seed=4242)
    assert before_svg == after_svg
    assert "#a2342a" not in after_svg


def test_the_57_write_sites_remain_split_by_role() -> None:
    compose_source = COMPOSE_SOURCE.read_text()
    normalize_source = NORMALIZE_SOURCE.read_text()
    api_source = API_SOURCE.read_text()

    # Folding away the staffage level (v2.11.0) deleted the six branches that
    # authored an instruction of their own, and with them 36 of the 47 literal
    # note fields -- every one of those sat in an instruction coerce invented.
    # The split by role is what this asserts, not the size of the inventory:
    # three fallback sites still write descriptive markers to color_hint, the
    # rest write machine notes, and the carry site preserves both fields.
    assert len(re.findall(r'\["note"\]\s*=', compose_source)) == 4
    # 22 since ddl-engine 11: `_with_stated_count_fidelity` signs its repair with
    # a machine note of its own, deliberately not the one the strict count road
    # writes -- two branches now make a stated count true, and a shared note
    # would leave a stored Score unable to say which of them did it.
    # 21 since ddl-engine 10: `_without_unrequested_color_cycle` writes a machine
    # note like the rest, in one clause -- `_append_note` dedupes by splitting on
    # ";", so a note carrying its own semicolon is appended again on every pass.
    assert len(re.findall(r"_append_note\(", compose_source)) - 1 == 22
    assert len(re.findall(r'"note"\s*:', compose_source)) == 11
    assert len(re.findall(r'\["color_hint"\]\s*=', compose_source)) == 3
    assert len(re.findall(r'"color_hint"\s*:', compose_source)) == 5
    # Four in normalize since the hard ceiling arrived: the fourth is `_with_note`,
    # the single helper both ceiling sites go through rather than writing the field
    # themselves. Five since ddl-engine 18: `_with_visible_particle` fills a shape
    # the description never asked to fill and now says so, the way its neighbour
    # `_with_visible_color` always has -- a repair whose only evidence is the
    # drawing cannot be told apart from a Stage 2 that asked for it.
    assert len(re.findall(r'\["note"\]\s*=', normalize_source)) == 5
    assert len(re.findall(r'(?:\["note"\]\s*=|"note"\s*:)', api_source)) == 10


@pytest.mark.parametrize(
    ("source_path", "function_name", "required"),
    [
        (NORMALIZE_SOURCE, "_with_presence_auxiliary_shape_repair", "_is_atmospheric_effect_hint(ins.color_hint)"),
        (NORMALIZE_SOURCE, "_with_presence_auxiliary_shape_repair", "_is_plain_material_hint(ins.note)"),
        (COMPOSE_SOURCE, "_with_visual_event_type_hints", 'event_type in (ins.note or "")'),
        (COMPOSE_SOURCE, "_with_crescent_sensory_suppression", 'descriptive_hint = (ins.color_hint or "").lower()'),
        (COMPOSE_SOURCE, "_with_crescent_sensory_suppression", 'isinstance(data.get("note"), str)'),
        (COMPOSE_SOURCE, "_with_semantic_visual_event_hints", '" ".join(ins.note or "" for ins in adjusted)'),
        (COMPOSE_SOURCE, "_has_focal_event_hint", 'hint = (ins.note or "").lower()'),
        (COMPOSE_SOURCE, "_with_existing_event_counterweight", '"small focal mark kept compact" in (ins.note or "").lower()'),
        (COMPOSE_SOURCE, "_with_existing_event_counterweight", '"circle focal mark kept compact" in (ins.note or "").lower()'),
        (COMPOSE_SOURCE, "_with_existing_event_counterweight", 'candidate_hint = (candidate.note or "").lower()'),
        (COMPOSE_SOURCE, "_with_existing_event_counterweight", 'compact_mark = "small focal mark kept compact" in hint'),
        (COMPOSE_SOURCE, "_with_color_cycle_delivery", '"small focal mark kept compact" in (data.get("note") or "")'),
        (COMPOSE_SOURCE, "_score_contains_motif", 'motif in (ins.note or "")'),
    ],
)
def test_the_13_readback_guard_locations_use_their_ruled_field(
    source_path: Path, function_name: str, required: str
) -> None:
    source = source_path.read_text()
    function = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    assert required in ast.get_source_segment(source, function)
