from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
import uuid

from sqlalchemy import create_engine, inspect, text

from inku_server import db
from inku_server.api_core.rendering import _add_history_item, _capture_history_coerce_observability
from inku_server.api_core.models import HistoryPostBody
from inku_server.api_core.routers.history import api_history_post
from inku_server.coerce import coerce_score
from inku_server.schema import Score


ANALYZER = Path(__file__).parents[1] / "scripts" / "analyze_coerce_trace.py"


def _actor():
    db.init_db()
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"coerce-observability-{suffix}")
    user = db.add_user(
        username=f"coerce-observability-{suffix}",
        email=f"coerce-observability-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    return user, group


def test_t316_legacy_migration_keeps_observation_unrecorded_and_private(tmp_path, monkeypatch):
    from inku_server.coerce.observability import INTERNAL_HISTORY_COLUMNS

    legacy = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with legacy.begin() as conn:
        conn.execute(text("CREATE TABLE history (id VARCHAR PRIMARY KEY, at BIGINT NOT NULL, input TEXT NOT NULL DEFAULT '', ddl TEXT, score TEXT NOT NULL DEFAULT '{}', svg TEXT NOT NULL DEFAULT '', output_path TEXT, elapsed_ms INTEGER NOT NULL DEFAULT 0)"))
        conn.execute(text("CREATE TABLE user_accounts (id VARCHAR PRIMARY KEY, username VARCHAR NOT NULL, email VARCHAR NOT NULL, password_hash TEXT NOT NULL, role VARCHAR NOT NULL, group_id VARCHAR, at BIGINT NOT NULL)"))
        conn.execute(text("INSERT INTO history (id, at, input, score, svg) VALUES ('old', 1, 'old', '{}', '')"))
    monkeypatch.setattr(db, "engine", legacy)
    db._migrate_columns()
    columns = {column["name"] for column in inspect(legacy).get_columns("history")}
    assert set(INTERNAL_HISTORY_COLUMNS) <= columns
    assert inspect(legacy).has_table("coerce_trace_catalogs")
    assert not inspect(legacy).has_table("history_fts")
    with legacy.connect() as conn:
        old = conn.execute(text("SELECT score_pre_coerce, coerce_trace_version, coerce_catalog_digest, coerce_trace FROM history WHERE id = 'old'")).one()
    assert old == (None, None, None, None)


def test_t320_migrated_legacy_row_stays_unobserved_not_complete_zero(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy-unobserved.db"
    legacy = create_engine(f"sqlite:///{legacy_path}", future=True)
    with legacy.begin() as conn:
        conn.execute(text("CREATE TABLE history (id VARCHAR PRIMARY KEY, at BIGINT NOT NULL, input TEXT NOT NULL DEFAULT '', ddl TEXT, score TEXT NOT NULL DEFAULT '{}', svg TEXT NOT NULL DEFAULT '', output_path TEXT, elapsed_ms INTEGER NOT NULL DEFAULT 0)"))
        conn.execute(text("CREATE TABLE user_accounts (id VARCHAR PRIMARY KEY, username VARCHAR NOT NULL, email VARCHAR NOT NULL, password_hash TEXT NOT NULL, role VARCHAR NOT NULL, group_id VARCHAR, at BIGINT NOT NULL)"))
        conn.execute(text("INSERT INTO history (id, at, input, score, svg) VALUES ('old', 1, 'old', '{}', '')"))
    monkeypatch.setattr(db, "engine", legacy)
    db._migrate_columns()
    result = subprocess.run(
        [sys.executable, str(ANALYZER), "--db", str(legacy_path), "--json"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(result.stdout)["global_coverage"] == {
        "total": 1,
        "observed": 0,
        "complete": 0,
        "incomplete": 0,
        "unobserved": 1,
    }


def test_t317_save_captures_hidden_trace_non_save_writes_nothing_and_replay_is_immutable():
    from inku_server.api_core.rendering import _capture_history_coerce_observability

    actor, group = _actor()
    try:
        score = Score.model_validate({"background": "white", "instructions": []})
        trace = _capture_history_coerce_observability(
            score, ddl="night", lang="en", auto_repair=True, include_trace=False,
        )
        post = coerce_score(score, ddl="night", lang="en", trace=trace)
        stored = _add_history_item(
            actor=actor, input_text="night", ddl="night", expanded_ddl="night", score=post,
            svg="<svg/>", at=1, save_artifacts=False, idempotency_key="i331-replay",
            coerce_observability=trace.persistable(),
        )
        replay = _add_history_item(
            actor=actor, input_text="changed", ddl="changed", expanded_ddl="changed", score=score,
            svg="<svg changed/>", at=2, save_artifacts=False, idempotency_key="i331-replay",
            coerce_observability={"complete": False},
        )
        assert replay["id"] == stored["id"]
        with db.SessionLocal() as session:
            row = session.get(db.HistoryRow, stored["id"])
            assert row.score_pre_coerce == json.dumps(score.model_dump(by_alias=True), ensure_ascii=False)
            assert row.coerce_trace_version == 1
            assert row.coerce_catalog_digest
            assert json.loads(row.coerce_trace)["complete"] is True
        assert "coerce_trace" not in db.get_items(actor["id"], [stored["id"]])[0]
    finally:
        db.delete_items(actor["id"], [stored["id"]] if "stored" in locals() else [])
        db.delete_user(actor["id"])
        db.delete_user_group(group["id"])

def test_t317_paint_history_capture_is_gated_only_by_save_history():
    source = Path(__file__).parents[1] / "src/inku_server/api_core/routers/render.py"
    module = ast.parse(source.read_text())
    paint_events = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_paint_events"
    )
    captures = [
        node for node in ast.walk(paint_events)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "coerce_observability" for target in node.targets)
    ]
    assert len(captures) == 1
    capture = captures[0]
    assert isinstance(capture.value, ast.IfExp)
    assert isinstance(capture.value.test, ast.Attribute)
    assert isinstance(capture.value.test.value, ast.Name)
    assert capture.value.test.value.id == "req"
    assert capture.value.test.attr == "save_history"
    assert not any(
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "req"
        and node.attr == "include_trace"
        for node in ast.walk(capture.value.test)
    )
    assert isinstance(capture.value.body, ast.Call)
    assert isinstance(capture.value.body.func, ast.Name)
    assert capture.value.body.func.id == "_capture_history_coerce_observability"
    assert isinstance(capture.value.orelse, ast.Constant)
    assert capture.value.orelse.value is None



def test_t316_history_api_output_stays_public_while_private_trace_is_saved():
    actor, group = _actor()
    saved = None
    try:
        body = HistoryPostBody(
            input="plain history",
            score={"background": "white", "instructions": []},
            at=4,
            save_artifacts=False,
        )
        expected_score = coerce_score(Score.model_validate(body.score)).model_dump(
            mode="json", by_alias=True
        )
        saved = api_history_post(body, idempotency_key=None, actor=actor)
        public = saved.model_dump()
        assert public["score"] == expected_score
        assert not set(public) & {
            "score_pre_coerce",
            "coerce_trace_version",
            "coerce_catalog_digest",
            "coerce_trace",
        }
        with db.SessionLocal() as session:
            row = session.get(db.HistoryRow, saved.id)
            assert row is not None
            assert row.score_pre_coerce is not None
            assert row.coerce_trace is not None
    finally:
        db.delete_items(actor["id"], [saved.id] if saved is not None else [])
        db.delete_user(actor["id"])
        db.delete_user_group(group["id"])


def test_t317_history_api_persists_private_capture_without_a_public_trace_field():
    actor, group = _actor()
    saved = None
    try:
        saved = api_history_post(
            HistoryPostBody(
                input="night",
                score={"background": "white", "instructions": []},
                at=3,
                save_artifacts=False,
            ),
            idempotency_key=None,
            actor=actor,
        )
        with db.SessionLocal() as session:
            row = session.get(db.HistoryRow, saved.id)
            assert row is not None
            assert row.score_pre_coerce is not None
            assert row.coerce_trace_version == 1
            assert row.coerce_catalog_digest is not None
            assert json.loads(row.coerce_trace)["complete"] is True
        assert "coerce_trace" not in saved.model_dump()
    finally:
        db.delete_items(actor["id"], [saved.id] if saved is not None else [])
        db.delete_user(actor["id"])
        db.delete_user_group(group["id"])


def test_t318_registry_covers_all_leaf_predicates_and_catalog_preserves_memberships():
    from inku_server.coerce.observability import catalog_snapshot, verify_decision_site_registry

    assert verify_decision_site_registry() == []
    markers = catalog_snapshot()["markers"]
    assert markers
    assert all({"system", "marker", "language", "decision_site", "match_mode"} <= set(event) for event in markers)
    assert all("output" not in event for event in markers)
    duplicate = [event for event in markers if event["marker"] == "right half"]
    assert len({event["system"] for event in duplicate}) > 1


def test_t319_real_coerce_records_actual_marker_and_effect_without_score_byte_change():
    from inku_server.coerce.observability import capture_context

    score = Score.model_validate({"background": "white", "instructions": [{"primitive": "circle", "color": "white", "center": [0.5, 0.5], "radius": 0.1}]})
    plain = coerce_score(score, ddl="blue", lang="en")
    trace = capture_context(score, ddl="blue", lang="en")
    observed = coerce_score(score, ddl="blue", lang="en", trace=trace)
    assert plain.model_dump_json(by_alias=True) == observed.model_dump_json(by_alias=True)
    event = trace.persistable()
    assert event["complete"] is True
    assert any(marker["marker"] == "blue" for marker in event["marker_events"])
    assert any(branch["changed_fields"] for branch in event["branch_events"])
    assert all(
        field["path"].startswith("/instructions/")
        and field["effect"] in {"add", "remove", "replace"}
        for branch in event["branch_events"]
        for field in branch["changed_fields"]
    )


def test_t320_actual_disabled_not_executed_and_incomplete_states_are_distinct(monkeypatch):
    from inku_server.coerce.observability import capture_context

    score = Score.model_validate({"background": "white", "instructions": []})
    disabled = capture_context(score, ddl="night", lang="en")
    monkeypatch.setenv("INKU_COERCE_DISABLE", "1")
    coerce_score(score, ddl="night", lang="en", trace=disabled)
    assert disabled.persistable()["disabled"] is True
    not_executed = capture_context(score, ddl="night", lang="en")
    assert not_executed.persistable()["complete"] is False
    assert not_executed.persistable()["reason_class"] == "not_executed"
    auto_repair_off = _capture_history_coerce_observability(
        score, ddl="night", lang="en", auto_repair=False, include_trace=False
    )
    assert auto_repair_off.persistable()["reason_class"] == "auto_repair_off"


def test_t318_stage_a_registry_and_catalog_are_actual_and_stable():
    from inku_server.coerce.observability import catalog_digest, catalog_snapshot
    from inku_server.coerce.observation_registry import (
        DIRECT_INPUT_SEMANTIC_LEAVES,
        DIRECT_SITE_COUNT,
        LANGUAGE_SITE_COUNT,
        OUTPUT_EXCLUSIONS,
        SEMANTIC_LEAF_COUNT,
        SITE_REGISTRY,
        SYNTAX_SITE_COUNT,
    )
    from inku_server.language_support.registry import INSTRUCTION_LANGUAGE_REGISTRY

    language_sites = [
        site
        for site in SITE_REGISTRY
        if site["source_kind"] == "language_support.COERCE_MARKERS"
    ]
    assert (SYNTAX_SITE_COUNT, SEMANTIC_LEAF_COUNT, LANGUAGE_SITE_COUNT) == (77, 89, 66)
    assert DIRECT_SITE_COUNT == 11
    assert len(OUTPUT_EXCLUSIONS) == 5
    decision_sites = [site["decision_site"] for site in language_sites]
    assert len(decision_sites) == len(set(decision_sites)) == LANGUAGE_SITE_COUNT
    assert not any(re.search(r"\.\d{3,}\.", site) for site in decision_sites)

    source = Path(__file__).parents[1] / "src/inku_server/coerce/compose.py"
    tree = ast.parse(source.read_text())
    observed_sites = {
        keyword.value.value
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        for keyword in call.keywords
        if keyword.arg == "decision_site" and isinstance(keyword.value, ast.Constant)
    }
    direct_sites = [
        site for site in SITE_REGISTRY if site["source_kind"] == "compose_direct_input"
    ]
    direct_decision_sites = {site["decision_site"] for site in direct_sites}
    assert set(decision_sites) | direct_decision_sites == observed_sites
    assert len(direct_sites) == DIRECT_SITE_COUNT == 11
    assert {site["systems"][0] for site in direct_sites} == {
        "direct.visual_event.dynamic_groups",
        "direct.visual_event.anticipatory_skip",
        "direct.presence.human", "direct.presence.creature",
        "direct.presence.group", "direct.presence.gaze",
        "direct.presence.symmetry", "direct.atmospheric_clause",
        "direct.polychrome_clause", "direct.bamboo_green",
        "direct.only_primitive.dynamic_groups",
    }
    direct_leaves = {
        leaf for site in direct_sites for leaf in site["semantic_leaves"]
    }
    assert direct_leaves == set(DIRECT_INPUT_SEMANTIC_LEAVES)
    assert len(direct_leaves) == 26

    declared_systems = set().union(
        *(set(support.coerce_markers) for support in INSTRUCTION_LANGUAGE_REGISTRY.values())
    )
    catalog_systems = {system for site in language_sites for system in site["systems"]}
    inert_systems = declared_systems - catalog_systems - {"atmospheric_effect"}
    assert inert_systems == {
        "colorful",
        "edge_light",
        "hard_edge",
        "leaf_grain",
        "playful_motion",
        "silence_layer",
        "strong_edge_light",
        "surface_tension",
        "vanishing_trace",
    }

    snapshot = catalog_snapshot()
    assert catalog_digest(snapshot) == (
        "50723ba7c66ba1de9a91a5b36559464c825886ba37ef3c1849633aee26ddb6a6"
    )
    catalog = snapshot["markers"]
    direct_catalog = [event for event in catalog if event["system"].startswith("direct.")]
    assert len({event["system"] for event in catalog}) == 73
    assert len(catalog) == 1391
    assert len(direct_catalog) == 271
    assert len({(event["language"], event["marker"]) for event in catalog}) == 776
    assert {event["decision_site"] for event in direct_catalog} == direct_decision_sites
    assert all(event["system"] != "atmospheric_effect" for event in catalog)
    assert all("output" not in event for event in catalog)


def test_t318_stage_a_declaration_inventory_is_separate_from_site_membership():
    from inku_server.coerce.observability import marker_tokens

    declarations = tuple(
        token for token in marker_tokens() if not token.system.startswith("direct.")
    )
    declaration_memberships = {
        (token.system, token.language, str(token)) for token in declarations
    }
    actual_inputs = {
        membership
        for membership in declaration_memberships
        if membership[0] != "atmospheric_effect"
    }
    assert len(declarations) == 964
    assert len(declaration_memberships) == 963
    assert len(actual_inputs) == 941
    assert len({(language, marker) for _, language, marker in actual_inputs}) == 611


def test_t319_stage_a_raw_and_marker_helper_observations_preserve_score_bytes():
    from inku_server.coerce.observability import capture_context

    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "circle",
                    "color": "white",
                    "center": [0.5, 0.5],
                    "radius": 0.1,
                }
            ],
        }
    )
    for ddl, expected_mode in (
        ("slow wave", "raw-substring"),
        ("blue", "marker_helper(word_ascii_else_substring)"),
    ):
        plain = coerce_score(score, ddl=ddl, lang="en")
        trace = capture_context(score, ddl=ddl, lang="en")
        observed = coerce_score(score, ddl=ddl, lang="en", trace=trace)
        assert plain.model_dump_json(by_alias=True) == observed.model_dump_json(by_alias=True)
        assert any(
            event["match_mode"] == expected_mode
            for event in trace.persistable()["marker_events"]
        )


def test_t319_stage_b_direct_presence_visual_and_primitive_trace_preserve_score_bytes():
    from inku_server.coerce import compose
    from inku_server.coerce.observability import capture_context

    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "circle",
                    "color": "white",
                    "center": [0.5, 0.5],
                    "radius": 0.1,
                }
            ],
        }
    )
    for ddl, expected_system in (
        ("figure face", "direct.presence.human"),
        ("two same newspaper held", "direct.visual_event.dynamic_groups"),
    ):
        plain = coerce_score(score, ddl=ddl, lang="en")
        trace = capture_context(score, ddl=ddl, lang="en")
        observed = coerce_score(score, ddl=ddl, lang="en", trace=trace)
        assert plain.model_dump_json(by_alias=True) == observed.model_dump_json(by_alias=True)
        assert any(
            event["system"] == expected_system
            for event in trace.persistable()["marker_events"]
        )

    trace = capture_context(score, ddl="circle only", lang="en")
    with trace.activate():
        assert compose._primitive_only_constraint_from_ddl("circle only") == {"circle"}
    assert any(
        event["system"] == "direct.only_primitive.dynamic_groups"
        for event in trace.persistable()["marker_events"]
    )


def test_t318_stage_b_live_visual_event_mode_is_not_the_map_raw_substring_mode():
    from inku_server.coerce.observation_registry import SITE_REGISTRY

    direct_modes = {
        site["systems"][0]: site["match_mode"]
        for site in SITE_REGISTRY
        if site["source_kind"] == "compose_direct_input"
    }
    assert direct_modes["direct.visual_event.dynamic_groups"] == (
        "marker_helper(word_ascii_else_substring)"
    )
    assert direct_modes["direct.visual_event.anticipatory_skip"] == (
        "marker_helper(word_ascii_else_substring)"
    )
