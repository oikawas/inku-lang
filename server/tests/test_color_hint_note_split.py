"""Contract tests for separating machine diagnostics from color descriptions."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from inku_server import composer
from inku_server.coerce import coerce_score
from inku_server.renderer import COLOR_MAP, _resolve_color, _seed_for_instruction
from inku_server.schema import Instruction, Score


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_SOURCE = ROOT / "src" / "inku_server" / "coerce" / "compose.py"
NORMALIZE_SOURCE = ROOT / "src" / "inku_server" / "coerce" / "normalize.py"
API_SOURCE = ROOT / "src" / "inku_server" / "api.py"
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

IDEMPOTENT_CASE_IDS = (
    "H-01", "H-02", "H-03", "H-05", "H-06", "H-07",
    "H-09", "H-11", "H-13", "H-14", "H-16", "H-18",
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
        tenkei=case_input["tenkei"],
        plugin_instructions_present=case_input["plugin_instructions_present"],
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
            tenkei=case_input["tenkei"],
            plugin_instructions_present=case_input["plugin_instructions_present"],
        )
        assert second.model_dump(mode="json", by_alias=True) == first.model_dump(
            mode="json", by_alias=True
        ), case_id


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

    assert _resolve_color(before.color, before.color_hint, COLOR_MAP) == COLOR_MAP["gray"]
    assert _resolve_color(after.color, after.color_hint, COLOR_MAP) == COLOR_MAP["gray"]
    assert _seed_for_instruction(before, 4242) == _seed_for_instruction(after, 4242)


def test_the_92_write_sites_remain_split_by_role() -> None:
    compose_source = COMPOSE_SOURCE.read_text()
    normalize_source = NORMALIZE_SOURCE.read_text()
    api_source = API_SOURCE.read_text()

    # The compose inventory retains all 79 original sites. Seven fallback
    # sites still write descriptive markers to color_hint; the others write
    # machine notes. The carry site now preserves both fields.
    assert len(re.findall(r'\["note"\]\s*=', compose_source)) == 4
    assert len(re.findall(r"_append_note\(", compose_source)) - 1 == 21
    assert len(re.findall(r'"note"\s*:', compose_source)) == 47
    assert len(re.findall(r'\["color_hint"\]\s*=', compose_source)) == 3
    assert len(re.findall(r'"color_hint"\s*:', compose_source)) == 5
    assert len(re.findall(r'\["note"\]\s*=', normalize_source)) == 3
    assert len(re.findall(r'(?:\["note"\]\s*=|"note"\s*:)', api_source)) == 10


@pytest.mark.parametrize(
    ("source_path", "function_name", "required"),
    [
        (NORMALIZE_SOURCE, "_with_presence_auxiliary_shape_repair", "_is_atmospheric_effect_hint(ins.color_hint)"),
        (NORMALIZE_SOURCE, "_with_presence_auxiliary_shape_repair", "_is_plain_material_hint(ins.note)"),
        (COMPOSE_SOURCE, "_with_motion_floor", '"motion floor restored" in (ins.note or "")'),
        (COMPOSE_SOURCE, "_with_visual_event", '"visual event restored" in (ins.note or "")'),
        (COMPOSE_SOURCE, "_with_visual_event_type_hints", 'event_type in (ins.note or "")'),
        (COMPOSE_SOURCE, "_with_crescent_sensory_suppression", 'descriptive_hint = (ins.color_hint or "").lower()'),
        (COMPOSE_SOURCE, "_with_crescent_sensory_suppression", 'isinstance(data.get("note"), str)'),
        (COMPOSE_SOURCE, "_with_semantic_visual_event_hints", '" ".join(ins.note or "" for ins in adjusted)'),
        (COMPOSE_SOURCE, "_has_focal_event_hint", 'hint = (ins.note or "").lower()'),
        (COMPOSE_SOURCE, "_with_existing_event_counterweight", '"small focal mark kept compact" in (ins.note or "").lower()'),
        (COMPOSE_SOURCE, "_with_existing_event_counterweight", '"circle focal mark kept compact" in (ins.note or "").lower()'),
        (COMPOSE_SOURCE, "_with_existing_event_counterweight", 'candidate_hint = (candidate.note or "").lower()'),
        (COMPOSE_SOURCE, "_with_existing_event_counterweight", 'compact_mark = "small focal mark kept compact" in hint'),
        (COMPOSE_SOURCE, "_with_minimum_focal_extent", 'if "small focal mark kept compact" in hint'),
        (COMPOSE_SOURCE, "_has_adjacent_reaction", '"adjacent reaction" in (ins.note or "").lower()'),
        (COMPOSE_SOURCE, "_has_context_energy", 'kind in (ins.note or "")'),
        (COMPOSE_SOURCE, "_has_context_energy", 'marker in (ins.note or "")'),
        (COMPOSE_SOURCE, "_has_surface_tension", '"surface tension restored" in (ins.note or "")'),
        (COMPOSE_SOURCE, "_has_compensating_accent", '"quiet expression accent restored" in (ins.note or "")'),
        (COMPOSE_SOURCE, "_with_color_cycle_delivery", '"small focal mark kept compact" in (data.get("note") or "")'),
        (COMPOSE_SOURCE, "_score_contains_motif", 'motif in (ins.note or "")'),
    ],
)
def test_the_20_readback_guard_locations_use_their_ruled_field(
    source_path: Path, function_name: str, required: str
) -> None:
    source = source_path.read_text()
    function = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    assert required in ast.get_source_segment(source, function)
