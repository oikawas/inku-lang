import copy
import hashlib
import json
import struct
from xml.etree import ElementTree

import pytest

from inku_server.render_engines.default import determinism
from inku_server.render_engines.default.determinism import _seed_for_instruction
from inku_server.renderer import render
from inku_server.schema import Arrangement, Instruction, Score
from inku_server.render_engines.default import planning


EXPECTED_SEED_INSTRUCTION_FIELDS = {
    "primitive",
    "weight",
    "thinness",
    "style",
    "filled",
    "mode",
    "carve_depth",
    "from_",
    "to",
    "center",
    "radius",
    "sides",
    "position",
    "size",
    "angle_start",
    "angle_end",
    "rotation",
    "variation",
    "surface",
    "arrangement",
}
EXPECTED_NON_SEED_INSTRUCTION_FIELDS = {
    "color",
    "color_hint",
    "note",
    "at",
    "relation",
}
EXPECTED_SEED_ARRANGEMENT_FIELDS = {"jitter"}
EXPECTED_NON_SEED_ARRANGEMENT_FIELDS = {
    "count",
    "group_size",
    "layout",
    "rows",
    "cols",
    "path",
    "color_cycle",
    "margin",
    "center",
    "radius",
    "density",
    "cluster_count",
    "fade",
    "preserve_space",
    "rhythm_spacing",
}


def _all_field_instruction_payload() -> dict:
    return {
        "primitive": "line",
        "from": [0.1, 0.2],
        "to": [0.8, 0.7],
        "center": [0.4, 0.4],
        "radius": 0.2,
        "sides": 5,
        "position": [0.2, 0.3],
        "size": [0.4, 0.3],
        "angle_start": 10.0,
        "angle_end": 170.0,
        "rotation": 5.0,
        "filled": False,
        "style": "solid",
        "weight": "pen",
        "mode": "additive",
        "carve_depth": None,
        "color": "black",
        "color_hint": "annotation one",
        "note": "machine annotation one",
        "variation": {
            "amplitude": "fine",
            "frequency": "slow",
            "quality": "perlin",
            "dimensions": ["position_y"],
        },
        "arrangement": {
            "count": 12,
            "layout": "scatter",
            "rows": 2,
            "cols": 3,
            "jitter": 0.2,
            "path": "diagonal",
            "color_cycle": ["black", "red"],
            "margin": 0.1,
            "center": [0.5, 0.5],
            "radius": 0.2,
            "density": "low",
            "cluster_count": 3,
            "fade": "outward",
            "preserve_space": False,
            "rhythm_spacing": "none",
        },
        "at": {"region": [0.1, 0.1, 0.9, 0.9]},
        "relation": {"type": "along", "gap": "narrow"},
        "surface": {
            "texture": "hatch",
            "density": 0.3,
            "scale": 0.4,
            "opacity": 0.2,
            "bleed": 0.1,
            "direction": "horizontal",
            "spacing_gradient": "coarse_to_dense",
            "tone_steps": 2,
            "seed": 7,
        },
    }


def _mutated_instruction(path: str, value: object) -> Instruction:
    payload = copy.deepcopy(_all_field_instruction_payload())
    target = payload
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    return Instruction.model_validate(payload)


SEED_SENSITIVE_FIELDS = [
    ("primitive", "circle"),
    ("weight", "pencil"),
    ("style", "dashed"),
    ("filled", True),
    ("mode", "carve"),
    ("carve_depth", "light"),
    ("from", [0.12, 0.2]),
    ("to", [0.78, 0.7]),
    ("center", [0.42, 0.4]),
    ("radius", 0.25),
    ("sides", 6),
    ("position", [0.22, 0.3]),
    ("size", [0.35, 0.3]),
    ("angle_start", 15.0),
    ("angle_end", 165.0),
    ("rotation", 15.0),
    ("variation.amplitude", "medium"),
    ("variation.frequency", "high"),
    ("variation.quality", "wave"),
    ("variation.dimensions", ["position_x"]),
    ("surface.texture", "crosshatch"),
    ("surface.density", 0.45),
    ("surface.scale", 0.55),
    ("surface.opacity", 0.35),
    ("surface.bleed", 0.25),
    ("surface.direction", "vertical"),
    ("surface.spacing_gradient", "dense_to_coarse"),
    ("surface.tone_steps", 4),
    ("surface.seed", 11),
    ("arrangement.jitter", 0.65),
]

SEED_INSENSITIVE_FIELDS = [
    ("color", "red"),
    ("color_hint", "annotation two"),
    ("at", {"region": [0.2, 0.1, 0.8, 0.9]}),
    ("relation.type", "cutting"),
    ("relation.gap", "wide"),
    ("arrangement.count", 13),
    ("arrangement.layout", "vertical"),
    ("arrangement.rows", 3),
    ("arrangement.cols", 4),
    ("arrangement.path", "wave"),
    ("arrangement.color_cycle", ["green"]),
    ("arrangement.margin", 0.2),
    ("arrangement.center", [0.6, 0.6]),
    ("arrangement.radius", 0.25),
    ("arrangement.density", "high"),
    ("arrangement.cluster_count", 4),
    ("arrangement.fade", "directional"),
    ("arrangement.preserve_space", True),
    ("arrangement.rhythm_spacing", "loose"),
]


def test_seed_allowlists_match_the_renderer_contract():
    assert set(determinism._SEED_INSTRUCTION_FIELDS) == EXPECTED_SEED_INSTRUCTION_FIELDS
    assert set(determinism._SEED_ARRANGEMENT_FIELDS) == EXPECTED_SEED_ARRANGEMENT_FIELDS


def test_every_instruction_and_arrangement_field_is_classified():
    assert EXPECTED_SEED_INSTRUCTION_FIELDS.isdisjoint(
        EXPECTED_NON_SEED_INSTRUCTION_FIELDS
    )
    assert (
        EXPECTED_SEED_INSTRUCTION_FIELDS | EXPECTED_NON_SEED_INSTRUCTION_FIELDS
    ) == set(Instruction.model_fields)
    assert EXPECTED_SEED_ARRANGEMENT_FIELDS.isdisjoint(
        EXPECTED_NON_SEED_ARRANGEMENT_FIELDS
    )
    assert (
        EXPECTED_SEED_ARRANGEMENT_FIELDS | EXPECTED_NON_SEED_ARRANGEMENT_FIELDS
    ) == set(Arrangement.model_fields)


def test_seed_payload_keeps_the_four_existing_default_normalizations():
    instruction = Instruction.model_validate(
        {
            "primitive": "line",
            "from": [0.1, 0.2],
            "to": [0.8, 0.7],
            "surface": {
                "texture": "hatch",
                "spacing_gradient": "none",
                "tone_steps": 3,
            },
        }
    )
    payload = {
        "primitive": "line",
        "from_": [0.1, 0.2],
        "to": [0.8, 0.7],
        "center": None,
        "radius": None,
        "sides": None,
        "position": None,
        "size": None,
        "angle_start": None,
        "angle_end": None,
        "rotation": None,
        "filled": False,
        "style": "solid",
        "weight": "pen",
        "thinness": None,
        "variation": None,
        "arrangement": None,
        "surface": {
            "texture": "hatch",
            "density": 0.35,
            "scale": 0.35,
            "opacity": 0.28,
            "bleed": 0.0,
            "direction": "none",
            "seed": None,
        },
    }
    key = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    expected = struct.unpack("<Q", hashlib.sha256(key).digest()[:8])[0]

    assert _seed_for_instruction(instruction) == expected


@pytest.mark.parametrize(
    ("field", "value"),
    SEED_SENSITIVE_FIELDS,
    ids=[field for field, _ in SEED_SENSITIVE_FIELDS],
)
def test_seed_sensitivity_included_fields_change(field: str, value: object):
    baseline = Instruction.model_validate(_all_field_instruction_payload())

    assert _seed_for_instruction(_mutated_instruction(field, value)) != (
        _seed_for_instruction(baseline)
    )


@pytest.mark.parametrize(
    ("field", "value"),
    SEED_INSENSITIVE_FIELDS,
    ids=[field for field, _ in SEED_INSENSITIVE_FIELDS],
)
def test_seed_sensitivity_excluded_fields_do_not_change(field: str, value: object):
    baseline = Instruction.model_validate(_all_field_instruction_payload())

    assert _seed_for_instruction(_mutated_instruction(field, value)) == (
        _seed_for_instruction(baseline)
    )


def _performance_line(**overrides: object) -> dict:
    payload = {
        "primitive": "line",
        "from": [0.1, 0.45],
        "to": [0.25, 0.55],
        "weight": "pencil",
        "variation": {
            "amplitude": "medium",
            "frequency": "high",
            "quality": "perlin",
            "dimensions": ["position_x", "position_y"],
        },
    }
    payload.update(overrides)
    return payload


def _mark_xml(svg: str) -> list[bytes]:
    root = ElementTree.fromstring(svg)
    return [
        ElementTree.tostring(node)
        for node in root.iter()
        if node.attrib.get("id", "").startswith("mark_")
    ]


def test_color_hint_does_not_change_the_performed_svg():
    first = Score.model_validate(
        {"instructions": [_performance_line(color_hint="annotation one")]}
    )
    second = Score.model_validate(
        {"instructions": [_performance_line(color_hint="annotation two")]}
    )

    assert render(first, svg_profile="editable", render_seed=431) == render(
        second, svg_profile="editable", render_seed=431
    )


def test_count_adds_one_mark_without_reshuffling_the_first_twelve():
    first = Score.model_validate(
        {
            "instructions": [
                _performance_line(
                    arrangement={"count": 12, "layout": "scatter", "jitter": 0.2}
                )
            ]
        }
    )
    second = Score.model_validate(
        {
            "instructions": [
                _performance_line(
                    arrangement={"count": 13, "layout": "scatter", "jitter": 0.2}
                )
            ]
        }
    )

    first_marks = _mark_xml(render(first, svg_profile="editable", render_seed=431))
    second_marks = _mark_xml(render(second, svg_profile="editable", render_seed=431))

    assert len(first_marks) == 12
    assert len(second_marks) == 13

    # `count` is not in the seed payload, so the thirteenth mark is an addition
    # and not a reshuffle: the layout stage hands back the same twelve targets.
    first_instruction = first.instructions[0]
    second_instruction = second.instructions[0]
    assert _seed_for_instruction(first_instruction, 431) == _seed_for_instruction(
        second_instruction, 431
    )
    laid_out = [
        [planning._anchor(item) for item in planning._expand_arrangement_layout(ins, 431)]
        for ins in (first_instruction, second_instruction)
    ]
    assert laid_out[0] == laid_out[1][:12]

    # engine 20: placement is a second stage, and it reads the whole group --
    # the group is moved onto the declared anchor and shrunk where it leaves the
    # frame. A thirteenth target changes the group's centroid and extent, so the
    # first twelve marks are re-placed and therefore re-performed. Their XML is
    # no longer a prefix; what holds still is the layout above and the seed.
    assert first_marks != second_marks[:12]


def test_preserve_space_changes_only_its_arrangement_effect():
    compact_instruction = Instruction.model_validate(
        _performance_line(
            arrangement={
                "count": 12,
                "layout": "scatter",
                "margin": 0.05,
                "preserve_space": False,
            }
        )
    )
    spacious_instruction = Instruction.model_validate(
        _performance_line(
            arrangement={
                "count": 12,
                "layout": "scatter",
                "margin": 0.05,
                "preserve_space": True,
            }
        )
    )
    compact = Score(instructions=[compact_instruction])
    spacious = Score(instructions=[spacious_instruction])

    assert _seed_for_instruction(compact_instruction, 431) == _seed_for_instruction(
        spacious_instruction, 431
    )
    assert render(compact, svg_profile="editable", render_seed=431) != render(
        spacious, svg_profile="editable", render_seed=431
    )


def test_weight_still_changes_the_performed_svg():
    pen = Score.model_validate(
        {"instructions": [_performance_line(weight="pen")]}
    )
    pencil = Score.model_validate(
        {"instructions": [_performance_line(weight="pencil")]}
    )

    assert render(pen, svg_profile="editable", render_seed=431) != render(
        pencil, svg_profile="editable", render_seed=431
    )


def test_arrangement_jitter_still_changes_the_performed_svg():
    steady = Score.model_validate(
        {
            "instructions": [
                _performance_line(
                    arrangement={
                        "count": 12,
                        "layout": "grid",
                        "rows": 3,
                        "cols": 4,
                        "jitter": 0.0,
                    }
                )
            ]
        }
    )
    jittered = Score.model_validate(
        {
            "instructions": [
                _performance_line(
                    arrangement={
                        "count": 12,
                        "layout": "grid",
                        "rows": 3,
                        "cols": 4,
                        "jitter": 0.8,
                    }
                )
            ]
        }
    )

    assert render(steady, svg_profile="editable", render_seed=431) != render(
        jittered, svg_profile="editable", render_seed=431
    )
