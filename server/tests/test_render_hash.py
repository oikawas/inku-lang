from __future__ import annotations

import json

from sqlalchemy import create_engine, text

from inku_server import db


SCORE_A = {
    "version": "0.1.0",
    "canvas": {"aspect": "square", "ground": None},
    "background": "white",
    "presence": None,
    "instructions": [
        {
            "primitive": "circle",
            "from": None,
            "to": None,
            "center": [0.5, 0.5],
            "radius": 0.24,
            "sides": None,
            "position": None,
            "size": None,
            "angle_start": None,
            "angle_end": None,
            "rotation": None,
            "filled": False,
            "style": "solid",
            "weight": "pencil",
            "mode": "additive",
            "carve_depth": None,
            "color": "black",
            "color_hint": None,
            "variation": None,
            "arrangement": None,
            "at": None,
            "relation": None,
            "surface": None,
        }
    ],
}

BASE_ITEM = {
    "score": SCORE_A,
    "render_seed": 12345,
    "vary_seed": None,
    "render_build_number": "693",
    "render_engine_id": "default",
    "render_engine_version": "10",
    "render_color_catalog_id": "default",
}

BASE_RH3 = "rh3:1f28ff5586ca604740f227cce0f81cee7ddd83d6632fe59f2763f5af08d8a551"
BASE_RH2 = "rh2:bda92f348f2cf37760f187748575dbf6a1f7ddc58452d6e1fcfb130ff293e3f2"


def test_render_hash_v3_matches_fixed_reference() -> None:
    assert db.render_hash_for_item(BASE_ITEM) == BASE_RH3


def test_render_hash_v3_excludes_build_and_score_generation_seeds() -> None:
    variants = (
        {**BASE_ITEM, "render_build_number": "694"},
        {**BASE_ITEM, "render_build_number": "700"},
        {**BASE_ITEM, "vary_seed": 999},
        {**BASE_ITEM, "vary_seed": 2**63 + 1},
        {**BASE_ITEM, "render_build_number": "700", "vary_seed": 999},
        {**BASE_ITEM, "render_seed": "12345"},
    )

    assert {db.render_hash_for_item(item) for item in variants} == {BASE_RH3}


def test_render_hash_v3_retained_fields_match_fixed_references() -> None:
    variants = (
        (
            {**BASE_ITEM, "render_seed": 12346},
            "rh3:15dfce980c311dc9da4efd936fb211d5ccec0475fe79cc14fe4064958d0ca5cb",
        ),
        (
            {**BASE_ITEM, "render_color_catalog_id": "vivid_material"},
            "rh3:3002bdecbda9f0fb0dfb6005475bda62227b5cd92ce30536d17dfcc3f1f219ff",
        ),
        (
            {**BASE_ITEM, "render_engine_version": "11"},
            "rh3:fbc0144a419b947f0d4988927d7697f427e9a68c9db4d5ea02c4bf811fd1ab42",
        ),
        (
            {**BASE_ITEM, "render_seed": 2**63 + 1},
            "rh3:59ed7227cab4da9aff9c8b1c0e637e29c22078fefef0751dea0e2b555394f6e6",
        ),
    )

    for item, expected in variants:
        assert db.render_hash_for_item(item) == expected


def test_legacy_render_hash_v2_calculation_remains_available() -> None:
    assert db._legacy_render_hash_for_item(BASE_ITEM) == BASE_RH2


def test_render_hash_backfill_writes_rh3_without_touching_rh2(monkeypatch) -> None:
    test_engine = create_engine("sqlite:///:memory:", future=True)
    monkeypatch.setattr(db, "engine", test_engine)
    db.Base.metadata.create_all(test_engine)

    with test_engine.begin() as conn:
        values = {
            "score": json.dumps(SCORE_A),
            "render_seed": "12345",
            "render_build_number": "693",
            "render_engine_id": "default",
            "render_engine_version": "10",
            "render_color_catalog_id": "default",
        }
        conn.execute(
            text("""
                INSERT INTO history (
                    id, at, input, score, svg, elapsed_ms, render_seed,
                    render_build_number, render_engine_id,
                    render_engine_version, render_color_catalog_id,
                    render_hash, trashed, starred, history_visibility
                ) VALUES (
                    :id, 1, '', :score, '', 0, :render_seed,
                    :render_build_number, :render_engine_id,
                    :render_engine_version, :render_color_catalog_id,
                    :render_hash, 0, 0, 'normal'
                )
            """),
            [
                {**values, "id": "legacy", "render_hash": BASE_RH2},
                {**values, "id": "missing", "render_hash": None},
            ],
        )

    db._migrate_columns()

    with test_engine.connect() as conn:
        hashes = {
            row.id: row.render_hash
            for row in conn.execute(text("SELECT id, render_hash FROM history"))
        }

    assert hashes == {"legacy": BASE_RH2, "missing": BASE_RH3}
