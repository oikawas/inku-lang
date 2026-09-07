import json
from pathlib import Path

from inku_server.schema import Score


_ARTIFACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "core"
    / "crates"
    / "inku-score"
    / "schema"
    / "score.schema.json"
)


def _canonical_score_schema_bytes() -> bytes:
    return json.dumps(
        Score.model_json_schema(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_checked_in_score_schema_matches_the_live_pydantic_model() -> None:
    artifact = _ARTIFACT_PATH.read_bytes()
    assert artifact == _canonical_score_schema_bytes()

    schema = json.loads(artifact)
    assert isinstance(schema, dict)
    properties = schema.get("properties")
    assert isinstance(properties, dict)
    assert {"version", "canvas", "background", "presence", "instructions"} <= properties.keys()

    instruction = schema["$defs"]["Instruction"]["properties"]
    assert "point" in instruction["primitive"]["enum"]
    assert "semantic anchor" in instruction["position"]["description"]
    relation = schema["$defs"]["Relation"]["properties"]
    assert "connected" in relation["type"]["enum"]
    assert "target_instruction_index" in relation
    assert "position_authority" in relation
    assert "touching_constraints" in relation
    assert set(schema["$defs"]["TouchingConstraints"]["required"]) == {
        "dimensions_fixed", "direction_fixed"
    }
