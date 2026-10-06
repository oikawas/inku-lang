import pytest

from inku_server.limits import DEFAULT_LIMITS
from inku_server.saved_score_compat import coerce_saved_score
from inku_server.schema import Score


@pytest.mark.parametrize("version", [None, "0.1.0"])
def test_saved_score_keeps_region_bounds_without_host_clamping(version) -> None:
    region = [0.0, 0.7, 1.0, 1.0001]
    payload = {
        "instructions": [
            {
                "primitive": "circle",
                "center": [0.5, 0.8],
                "radius": 0.08,
                "at": {"region": region},
            }
        ]
    }
    if version is not None:
        payload["version"] = version

    validated = Score.model_validate(payload)
    compatible = coerce_saved_score(payload, limits=DEFAULT_LIMITS)

    assert validated.instructions[0].at.region == tuple(region)
    assert compatible.instructions[0].at.region == tuple(region)
    assert payload["instructions"][0]["at"]["region"] == region


def test_versionless_saved_score_keeps_explicit_geometry_and_count() -> None:
    score = coerce_saved_score(
        {
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.23, 0.67],
                    "radius": 0.04,
                    "arrangement": {"count": 7, "layout": "scatter"},
                }
            ]
        },
        limits=DEFAULT_LIMITS,
    )

    instruction = score.instructions[0]
    assert instruction.center == (0.23, 0.67)
    assert instruction.radius == 0.04
    assert instruction.arrangement is not None
    assert instruction.arrangement.count == 7


def test_versionless_saved_score_applies_the_existing_resource_budget() -> None:
    notes: list[str] = []
    score = coerce_saved_score(
        {
            "instructions": [
                {
                    "primitive": "ellipse",
                    "center": [0.5, 0.5],
                    "size": [0.01, 0.01],
                    "arrangement": {"count": 600, "layout": "scatter"},
                }
            ]
        },
        limits=DEFAULT_LIMITS,
        limit_notes=notes,
    )

    arrangement = score.instructions[0].arrangement
    assert arrangement is not None
    assert arrangement.count == 120
    assert any(note.startswith("represented_count_max: ") for note in notes)


def test_versionless_saved_score_repairs_only_structural_legacy_fields() -> None:
    score = coerce_saved_score(
        {
            "instructions": [
                {"primitive": "circle", "filled": True},
                {
                    "primitive": "line",
                    "relation": {"type": "between"},
                },
            ]
        },
        limits=DEFAULT_LIMITS,
    )

    circle, line = score.instructions
    assert circle.center == (0.5, 0.5)
    assert circle.radius == 0.15
    assert circle.surface is not None and circle.surface.texture == "solid"
    assert line.from_ == (0.1, 0.5)
    assert line.to == (0.9, 0.5)
    assert line.relation is None
