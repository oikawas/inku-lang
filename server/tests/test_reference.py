"""Anti-drift tests for the reference dump.

Each check imports the implementation table directly and compares it against
the reference output. If a value were hardcoded into ``reference.py`` instead of
imported, it would diverge from the implementation and these tests would fail.
"""

from __future__ import annotations

from typing import get_args

from inku_server import reference, schema
from inku_server.color_catalogs import COLOR_CATALOGS, COLOR_KEYS, color_catalogs
from inku_server.composer import _PRIMITIVE_TERMS, _RELATION_LITERAL_MARKERS
from inku_server.geometry_thresholds import (
    CLOSURE_LIMIT,
    CUSP_LIMIT_DEGREES,
    SAGITTA_RELATIVE_LIMIT,
)
from inku_server.plugins import CANVAS_ASPECTS, plugin_status_items
from inku_server.plugins.document_format import _CORE_MARKERS, _REGIONS
from inku_server.renderer import AMPLITUDE_PX, SVG_PROFILES, WEIGHT_TO_STROKE_WIDTH


def _ref() -> dict:
    return reference.build_reference()


def test_sections_are_stable() -> None:
    assert list(_ref().keys()) == [
        "meta",
        "saijiki",
        "normalized_ddl_phrases",
        "expansion_layer",
        "score_schema",
        "color_resolution",
        "weight_properties",
        "performance",
        "verification",
    ]


def test_meta_reports_score_version_and_plugins() -> None:
    meta = _ref()["meta"]
    assert meta["score_version"] == get_args(schema.ScoreVersion)[0]
    assert meta["plugins"] == [
        {
            "namespace": item.get("namespace"),
            "name": item.get("name"),
            "version": item.get("version"),
            "status": item.get("status"),
        }
        for item in plugin_status_items()
    ]


def test_saijiki_enums_match_schema() -> None:
    enums = _ref()["saijiki"]["backing_enums"]
    assert enums["primitive"] == list(get_args(schema.Primitive))
    assert enums["weight"] == list(get_args(schema.Weight))
    assert enums["color"] == list(get_args(schema.Color))


def test_saijiki_prose_categories_track_enum_sizes() -> None:
    saijiki = _ref()["saijiki"]
    # てざわり (touches) is a full surface list of the Weight enum.
    assert len(saijiki["core_categories_ja"]["てざわり"]) == len(get_args(schema.Weight))
    # en form surfaces are Primitive values, minus polygon (collected in schema).
    forms_en = set(saijiki["core_categories_en"]["forms"])
    primitives = set(get_args(schema.Primitive))
    assert forms_en <= primitives
    assert primitives - forms_en <= {"polygon"}
    assert set(saijiki["core_categories_ja"]) == {
        "かたち",
        "かたむき",
        "てざわり",
        "つらなり",
        "いろ",
        "ゆらぎ",
        "ばしょ",
        "うごき",
        "わりあい",
    }


def test_relation_literals_match_composer() -> None:
    literals = _ref()["normalized_ddl_phrases"]["relation_literals"]
    assert literals == {
        key: list(value) for key, value in _RELATION_LITERAL_MARKERS.items()
    }
    assert _ref()["normalized_ddl_phrases"]["relation_enums"]["type"] == list(
        get_args(schema.RelationType)
    )


def test_core_markers_and_regions_match_document_format() -> None:
    expansion = _ref()["expansion_layer"]
    for lang in ("ja", "en"):
        markers = [item["marker"] for item in expansion["core_markers"][lang]]
        assert markers == list(_CORE_MARKERS[lang])
    assert expansion["regions"] == {
        key: list(value) for key, value in _REGIONS.items()
    }
    assert len(expansion["regions"]) == 7


def test_marker_classes_use_known_buckets() -> None:
    expansion = _ref()["expansion_layer"]
    primitive_surfaces = {
        term.lower() for terms in _PRIMITIVE_TERMS.values() for term in terms
    }
    for lang in ("ja", "en"):
        for item in expansion["core_markers"][lang]:
            assert item["class"] in {"structural", "shape", "operation"}
            if item["marker"].lower() in primitive_surfaces:
                assert item["class"] == "shape"


def test_score_schema_enums_match_get_args() -> None:
    enums = _ref()["score_schema"]["enums"]
    for name in reference._ENUM_ALIASES:
        assert enums[name] == list(get_args(getattr(schema, name)))
    assert "properties" in _ref()["score_schema"]["json_schema"]


def test_color_resolution_hex_matches_catalogs() -> None:
    color = _ref()["color_resolution"]
    assert color["core_keys"] == list(COLOR_KEYS)
    assert len(color["catalogs"]) == len(COLOR_CATALOGS)
    source = {catalog["id"]: catalog["map"] for catalog in color_catalogs()}
    for catalog in color["catalogs"]:
        for key in COLOR_KEYS:
            assert catalog["map"][key] == source[catalog["id"]][key]


def test_weight_properties_stroke_width_matches_renderer() -> None:
    weights = _ref()["weight_properties"]["weights"]
    assert {w["weight"]: w["stroke_width"] for w in weights} == dict(
        WEIGHT_TO_STROKE_WIDTH
    )
    assert [w["weight"] for w in weights] == list(get_args(schema.Weight))


def test_performance_tables_match_sources() -> None:
    performance = _ref()["performance"]
    assert [a["id"] for a in performance["canvas_aspects"]] == [
        aspect.id for aspect in CANVAS_ASPECTS
    ]
    assert performance["amplitude_px"] == dict(AMPLITUDE_PX)
    assert performance["svg_profiles"] == sorted(SVG_PROFILES)


def test_verification_thresholds_match_geometry_module() -> None:
    thresholds = _ref()["verification"]["geometry_thresholds"]
    assert thresholds == {
        "closure_limit": CLOSURE_LIMIT,
        "cusp_limit_degrees": CUSP_LIMIT_DEGREES,
        "sagitta_relative_limit": SAGITTA_RELATIVE_LIMIT,
    }


def test_markdown_renders_all_sections() -> None:
    md = reference.render_markdown()
    for heading in (
        "## 1. Saijiki",
        "## 2. Normalized DDL phrases",
        "## 3. Expansion layer",
        "## 4. Score schema",
        "## 5. Color resolution",
        "## 6. Weight properties",
        "## 7. Performance",
        "## 8. Verification",
    ):
        assert heading in md
    # A representative implementation value must survive into the rendered page.
    assert COLOR_CATALOGS[0]["map"]["blue"] in md
