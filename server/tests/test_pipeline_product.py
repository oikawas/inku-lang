"""Actual core compilation to normal history projection, without SVG execution."""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from inku_server.persistence.schema import Base, HistoryRow, UserAccountRow
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_candidate import CandidateExecution, PipelineBinding
from inku_server.pipeline_defaults import ADDITIONAL_RESOURCE_LIMITS, default_manifest
from inku_server.pipeline_product import ProductPipelineEffects


def test_compact_delivery_preserves_authority_in_normal_history(tmp_path, monkeypatch):
    bundle = os.environ.get("INKU_PIPELINE_PYTHON_BUNDLE")
    if not bundle:
        pytest.skip("explicit generated pipeline binding bundle required")
    from inku_server import db
    from inku_server.api_core import rendering, thumbnails
    from inku_server.api_core.models import HistoryItem

    binding = PipelineBinding(Path(bundle))
    engine = create_engine(f"sqlite:///{tmp_path / 'normal-history.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(rendering, "_submit_history_artifact_save", lambda _item: None)
    monkeypatch.setattr(thumbnails, "submit_thumbnail_build", lambda _item: None)
    with engine.begin() as connection:
        connection.execute(UserAccountRow.__table__.insert().values(
            id="author", username="author", email="author@example.test",
            password_hash="unused", role="user", at=1,
        ))
    manifest = default_manifest(binding)
    manifest["pipeline"]["definitions"] = [{
        "schema": "inku.macro-definition.v1", "namespace": "Example", "heading": "Circle",
        "version": "1.0.0", "parameters": {}, "components": {}, "body": [{
            "op": "emit", "binding": None, "fields": {
                "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                "color": {"expr": "semantic_ref", "category": "color", "id": "black"},
                "position_x": {"expr": "exact_decimal", "value": "0.5"},
                "position_y": {"expr": "exact_decimal", "value": "0.5"},
                "count": {"expr": "integer", "value": 1},
            },
        }],
    }]
    manifest["pipeline"]["macro_summaries"] = ["A black circle at the center"]
    effects = ProductPipelineEffects(binding, manifest)
    source = "Example.Circle."
    options, context = effects.prepare("author", "direct_ddl", source,
                                       {"canvas_aspect": "hd_monitor", "render_seed": "71"}, None)
    context.update(description="", committed_description="", derivation_kind="new")
    assert options["definitions"][0]["heading"] == "Circle"
    lock = context["macro_catalog"]["definition_locks"][0]
    assert lock["qualified_name"] == "Example.Circle"
    assert lock["version"] == "1.0.0"
    assert len(lock["digest"]) == 64
    maximum = options["compiler"]["hard_resource_policy"]["budget"]["maximum"]
    assert {key: maximum[key] for key in ADDITIONAL_RESOURCE_LIMITS} == {
        "logical_objects": 4096, "template_nodes": 128, "anchor_instances": 4096,
        "transform_instances": 4096, "placement_instances": 64, "fill_instances": 64,
    }
    assert maximum["primitive_marks"] == 400
    assert maximum["maximum_per_template_primitive_marks"] == 240
    assert maximum["maximum_resolved_count"] == 2000
    assert maximum["object_templates"] == 64
    saved = effects.settings.config_for("author", {"saved_config": options})
    saved["compiler"]["hard_resource_policy"]["budget"]["maximum"]["logical_objects"] = 257
    restored = effects.settings.config_for("author", {"saved_config": saved})
    assert restored == saved
    assert options["compiler"]["hard_resource_policy"]["budget"]["maximum"]["logical_objects"] == 4096
    store = VariationAuthorityStore(engine)
    run = CandidateExecution(binding, store, owner_id="author", config=options,
                             context=context, provider=lambda _action: pytest.fail("complete DDL called a provider"))
    run.start_new({"tag": "direct_ddl", "source": source})
    run.run_effect()
    snapshot = run.snapshot()
    assert snapshot["phase"]["tag"] == "score_ready"
    assert snapshot["delivery"]["score"]["version"] == "0.10.0"
    render = effects.render_options(snapshot, run.context, {"tag": "perform"})
    assert render["options"]["canvas"] == {"width": 1778, "height": 1000}
    # Only history projection is exercised here. Native SVG execution belongs
    # to the Linux check, and artifact/thumbnail workers above are disconnected.
    rendered = {"svg": "<svg xmlns='http://www.w3.org/2000/svg'/>",
                "metadata": {"render_engine_id": "default", "render_engine_version": "59"}}
    result = effects.save_result("author", snapshot, run.context, rendered)
    replay = effects.save_result("author", snapshot, run.context, rendered)
    assert result["history_id"] == replay["history_id"]
    item = db.get_items("author", [result["history_id"]])[0]
    response = HistoryItem.model_validate(item).model_dump()
    assert response["score"] == snapshot["delivery"]["score"]
    assert response["ddl"] == snapshot["document"]["source"]
    assert response["pipeline_variation_id"] == snapshot["variation_id"]
    assert response["pipeline_revision"] == "1"
    assert response["render_canvas_aspect_id"] == "hd_monitor"
    assert response["render_seed"] == 71
    assert store.history_link("another", result["history_id"]) is None
    assert store.read("author", snapshot["variation_id"])["authority"]["authority"] == "ddl_authoritative"
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(HistoryRow)) == 1
        assert connection.scalar(select(UserAccountRow.image_generation_count)) == 1
    engine.dispose()
