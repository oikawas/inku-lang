import json

import pytest
from pydantic import ValidationError

from inku_server.schema import Instruction, Score


def test_surface_intensity_wire_defaults_and_supported_fill_domain() -> None:
    old = {"version": "0.3.0", "instructions": [{"primitive": "circle", "filled": True}]}
    original = Score.model_validate(old).model_dump_json(by_alias=True)
    for level in ("normal", "dense", "faint"):
        wire = {**old, "instructions": [{**old["instructions"][0], "surface_intensity": level}]}
        score = Score.model_validate(wire)
        encoded = score.model_dump_json(by_alias=True)
        assert score.instructions[0].surface_intensity == level
        if level == "normal":
            assert encoded == original
            assert "surface_intensity" not in json.loads(encoded)["instructions"][0]
        else:
            assert json.loads(encoded)["instructions"][0]["surface_intensity"] == level
    # A new flat Score defaults to 0.9, the flat compatibility edition (SPEC
    # §4.6); a saved Score without a version still reads as 0.1.
    assert Score.model_fields["version"].default == "0.9.0"
    assert Score.model_validate({"instructions": []}).version == "0.1.0"
    for edition in ("0.1.0", "0.2.0", "0.3.0"):
        wire = {**old, "version": edition}
        saved = Score.model_validate(wire)
        canonical = saved.model_dump_json(by_alias=True)
        assert saved.version == edition
        assert Score.model_validate_json(canonical).model_dump_json(by_alias=True) == canonical
        for level in ("normal", "dense", "faint"):
            marked = {**wire, "instructions": [{**old["instructions"][0], "surface_intensity": level}]}
            if level != "normal" and edition != "0.3.0":
                with pytest.raises(ValidationError, match="surface_intensity requires Score version 0.3.0"):
                    Score.model_validate(marked)
            elif level == "normal":
                assert Score.model_validate(marked).model_dump_json(by_alias=True) == canonical
            else:
                assert Score.model_validate(marked).instructions[0].surface_intensity == level
    for edition in ("0.2.0", "0.3.0"):
        crescent = {"primitive": "arc", "arc_form": "crescent", "center": [0.5, 0.5],
                    "size": [0.2, 0.2572564393705176], "filled": True}
        assert Score.model_validate({"version": edition, "instructions": [crescent]}).version == edition
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
