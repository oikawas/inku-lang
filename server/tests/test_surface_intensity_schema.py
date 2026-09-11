import json

import pytest
from pydantic import ValidationError

from inku_server.schema import Instruction, Score


def test_surface_intensity_wire_defaults_and_supported_fill_domain() -> None:
    old = {"instructions": [{"primitive": "circle", "filled": True}]}
    original = Score.model_validate(old).model_dump_json(by_alias=True)
    for level in ("normal", "dense", "faint"):
        wire = {"instructions": [{**old["instructions"][0], "surface_intensity": level}]}
        score = Score.model_validate(wire)
        encoded = score.model_dump_json(by_alias=True)
        assert score.instructions[0].surface_intensity == level
        if level == "normal":
            assert encoded == original
            assert "surface_intensity" not in json.loads(encoded)["instructions"][0]
        else:
            assert json.loads(encoded)["instructions"][0]["surface_intensity"] == level
    assert list(Instruction.model_fields)[-2:] == ["thinness", "surface"]
    assert Instruction(primitive="point", filled=True, surface_intensity="dense").surface_intensity == "dense"
    assert Instruction(primitive="circle", surface={"texture": "solid"}, surface_intensity="faint").surface_intensity == "faint"
    for instruction in (
        {"primitive": "line", "filled": True},
        {"primitive": "circle"},
        {"primitive": "circle", "filled": True, "surface": {"texture": "wash"}},
    ):
        with pytest.raises(ValidationError, match="surface_intensity requires a closed solid fill"):
            Instruction.model_validate({**instruction, "surface_intensity": "dense"})
    with pytest.raises(ValidationError):
        Instruction(primitive="circle", filled=True, surface_intensity="unknown")
