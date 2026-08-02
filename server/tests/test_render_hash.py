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
    "composition_seed": None,
    "render_build_number": "693",
    "render_engine_id": "default",
    "render_engine_version": "10",
    "render_color_catalog_id": "default",
}

# engine 12: render_wild joined the rh3 payload (absent == False), re-baselining these.
BASE_RH3 = "rh3:60fbf6514b72503eb65a4991457274c01aa3197fa8933d78b636fd4ee7f95eb6"
BASE_RH2 = "rh2:bda92f348f2cf37760f187748575dbf6a1f7ddc58452d6e1fcfb130ff293e3f2"


def test_render_hash_v3_matches_fixed_reference() -> None:
    assert db.render_hash_for_item(BASE_ITEM) == BASE_RH3


def test_render_hash_v3_excludes_build_and_score_generation_seeds() -> None:
    variants = (
        {**BASE_ITEM, "render_build_number": "694"},
        {**BASE_ITEM, "render_build_number": "700"},
        {**BASE_ITEM, "composition_seed": 999},
        {**BASE_ITEM, "composition_seed": 2**63 + 1},
        {**BASE_ITEM, "render_build_number": "700", "composition_seed": 999},
        {**BASE_ITEM, "render_seed": "12345"},
    )

    assert {db.render_hash_for_item(item) for item in variants} == {BASE_RH3}


def test_render_hash_v3_retained_fields_match_fixed_references() -> None:
    variants = (
        (
            {**BASE_ITEM, "render_seed": 12346},
            "rh3:46079e493457812ff29f2aaea5a40df507a68b1f65d2ee5354b9184446465b81",
        ),
        (
            {**BASE_ITEM, "render_color_catalog_id": "vivid_material"},
            "rh3:40c0eb26c341d32eca753a05a4738cd55fe4d2598fc8851e0f379b7d72103f07",
        ),
        (
            {**BASE_ITEM, "render_engine_version": "11"},
            "rh3:5fe152b6cb5532282f9da28ee3ae467608b3db456cb6ac8a9f08fe5deb66ba26",
        ),
        (
            {**BASE_ITEM, "render_seed": 2**63 + 1},
            "rh3:c6b32e446ba759fd74a2b274c2713e2176f50baab02595e79cad36892db5b6a1",
        ),
    )

    for item, expected in variants:
        assert db.render_hash_for_item(item) == expected


def test_render_hash_v3_wild_changes_edition_identity() -> None:
    # engine 12: the wild (unleashed) performance changes the drawing, so it is
    # part of the edition identity. Absent is treated as False.
    off = db.render_hash_for_item({**BASE_ITEM, "render_wild": False})
    on = db.render_hash_for_item({**BASE_ITEM, "render_wild": True})
    assert off == BASE_RH3
    assert on == "rh3:5dbbc6de270ec580c49bfb969596e730a7fb627b8362f1e0ae417f6310b84159"
    assert off != on


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
                    render_hash, trashed, starred, for_revision, history_visibility
                ) VALUES (
                    :id, 1, '', :score, '', 0, :render_seed,
                    :render_build_number, :render_engine_id,
                    :render_engine_version, :render_color_catalog_id,
                    :render_hash, 0, 0, 0, 'normal'
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
