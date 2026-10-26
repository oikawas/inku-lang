"""Read and draw (SPEC §12.6.7): the Server starts the route, sends its three
requests, draws the drawing it is corrected beside, and saves its record."""

from __future__ import annotations

import base64
import hashlib
import json
import time

import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence.schema import Base, UserAccountRow
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_api import PipelineService, pipeline_router, register_pipeline_errors
from inku_server.pipeline_candidate import PipelineBinding
from inku_server.pipeline_defaults import default_manifest
from inku_server.pipeline_product import ProductPipelineEffects, record_system_prompt


POEM = "紫のにほへる妹を憎くあらば人妻ゆゑに我恋ひめやも [大海人皇子 万葉集]"
DDL = "背景を黄で埋める。\n画面の横0.3、縦0.7の位置に、直径0.1の赤の塗りの円を1個置く。"
READING = {
    "viewpoint": {"speaker": "我（語り手）", "speaker_quote": "我", "eye": "目の高さで、隔たった先の女の姿を見ている。",
                  "addressee_quote": "妹", "speaker_seen_quote": ""},
    "core": ["目の先にひとりの女の姿があり、輪郭に紫がにじむ。"],
    "items": [
        {"kind": "scene", "quote": "紫のにほへる妹", "image": "女の輪郭に紫が重なる。"},
        {"kind": "context", "quote": "大海人皇子", "image": "野に立つ人の小さな影。"},
        {"kind": "texture", "quote": "つややかな衣", "image": "光る布の面。"},
    ],
    "reading": "紫の色が照り映える姿として読んだ。",
}
ANSWERS = {
    "read_description": ("description_read", READING),
    "write_description_ddl": ("description_ddl_written", {"ddl": DDL, "figures": [{"who": "addressee", "what": "妹"}]}),
    "review_description_ddl": ("description_ddl_reviewed", {"ddl": DDL, "figures": [{"who": "addressee", "what": "妹"}]}),
}


@pytest.fixture
def host(tmp_path, monkeypatch):
    from inku_server import model_settings
    from inku_server.api_core import common, rendering, thumbnails
    binding = PipelineBinding()
    engine = create_engine(f"sqlite:///{tmp_path / 'read.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(rendering, "_submit_history_artifact_save", lambda _: None)
    monkeypatch.setattr(thumbnails, "submit_thumbnail_build", lambda _: None)

    def offered(provider, model, settings, *, purpose):
        return provider == "openai" and (model == "fixture-vision" or (model == "fixture-text" and purpose == "llm"))

    monkeypatch.setattr(model_settings, "model_is_offered", offered)
    monkeypatch.setattr(common, "model_is_offered", offered)
    with engine.begin() as connection:
        connection.execute(UserAccountRow.__table__.insert().values(
            id="owner", username="owner", email="owner@example.test", password_hash="unused", role="user", at=1,
        ))
    effects = ProductPipelineEffects(binding, default_manifest(binding))
    sent = []

    def provider(owner, context, images=()):
        def perform(action):
            refs = action["payload"]["prompt"].get("images") or []
            assert len(images) == len(refs)
            for data_url, ref in zip(images, refs, strict=True):
                assert hashlib.sha256(base64.b64decode(data_url.split(",", 1)[1])).hexdigest() == ref["sha256"]
            sent.append({"tag": action["tag"], "images": len(refs), "message": action["payload"]["prompt"].get("message")})
            record_system_prompt(context, action)
            tag, response = ANSWERS[action["tag"]]
            return {"tag": tag, "identity": action["identity"], "response": json.dumps(response, ensure_ascii=False),
                    "elapsed_ms": "1"}
        return perform

    service = PipelineService(
        binding, VariationAuthorityStore(engine), config_for=effects.settings.config_for,
        prepare_for=effects.prepare, provider_for=lambda _: pytest.fail("provider without context"),
        provider_with_context=provider, image_provider_with_context=provider,
        image_review_options=effects.image_review_options,
        render_for=None, render_with_context=effects.render_options, project_result=effects.save_result,
        max_workers=1, max_effect_steps=32, max_retained_runs=4,
    )
    app = FastAPI()

    def actor(x_owner: str = Header(...)):
        return {"id": x_owner}

    app.include_router(pipeline_router(service, actor))
    register_pipeline_errors(app)
    with TestClient(app) as client:
        yield client, service, effects, sent
    service.close()
    engine.dispose()


def _wait(service, execution_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        view = service.execution("owner", execution_id).view()
        if not view["busy"]:
            return view
        time.sleep(0.01)
    pytest.fail("the run did not finish")


def _start(client, *, model="openai:fixture-vision", **options):
    body = {"kind": "description", "text": POEM,
            "options": {"stage1_model": model, "route": "read_and_draw", "save_artifacts": False, **options}}
    started = client.post("/api/pipeline/variations", json=body, headers={"x-owner": "owner"})
    assert started.status_code == 200, started.text
    return started.json()


def test_a_description_is_read_written_seen_and_saved_with_its_reading(host):
    client, service, _, sent = host
    view = _wait(service, _start(client, sketch="on")["execution_id"])
    assert view["phase"]["tag"] == "score_ready", view
    assert [(entry["tag"], entry["images"]) for entry in sent] == [
        ("read_description", 0), ("write_description_ddl", 0), ("review_description_ddl", 1)]
    # The labels' words reach the reading only.
    assert json.loads(sent[0]["message"])["source_label"] == "大海人皇子 万葉集"
    assert view["route"] == "read_and_draw"
    record = view["description_ddl"]
    assert record["reading_state"] == "read"
    assert record["reading_text"].startswith("読み: ")
    assert [item["quote"] for item in record["dropped_items"]] == ["つややかな衣"]
    assert view["authority"]["authority"] == "description_authoritative"
    done = service.command("owner", view["execution_id"], {"tag": "perform"})
    item = db.get_items("owner", [done["result"]["history_id"]])[0]
    assert item["description_ddl"] == record
    assert item["sketch_text"] == record["reading_text"] and item["sketch_state"] == "supplemented"
    assert item["input"] == POEM
    persisted = service.store.read_execution("owner", view["execution_id"]).state_bytes.decode()
    assert "data:image/" not in persisted and "base64" not in persisted
    prompts = client.get(f"/api/pipeline/variations/{view['variation_id']}/system-prompts", headers={"x-owner": "owner"})
    stages = prompts.json()
    assert stages["reading"]["message"] == sent[0]["message"]
    assert stages["description_ddl"]["system"] and stages["description_review"]["system"]
    assert stages["stage1"] is None and "message" not in stages["description_ddl"]


def test_without_a_sketch_the_description_is_written_without_a_reading(host):
    client, service, _, sent = host
    view = _wait(service, _start(client)["execution_id"])
    assert view["phase"]["tag"] == "score_ready", view
    assert [entry["tag"] for entry in sent] == ["write_description_ddl", "review_description_ddl"]
    assert view["description_ddl"]["reading_state"] == "off"
    done = service.command("owner", view["execution_id"], {"tag": "perform"})
    item = db.get_items("owner", [done["result"]["history_id"]])[0]
    assert item.get("sketch_text") is None and item["sketch_state"] == "off"


def test_an_edited_reading_is_written_from_without_a_request(host):
    client, service, _, sent = host
    edited = "読み: 野に立つ女を遠くから見る。\n視点: 目の高さ。\n核の像: 紫の輪郭"
    view = _wait(service, _start(client, sketch_text=edited)["execution_id"])
    assert view["phase"]["tag"] == "score_ready", view
    assert [entry["tag"] for entry in sent] == ["write_description_ddl", "review_description_ddl"]
    assert view["description_ddl"]["reading_state"] == "supplied"


def test_a_model_that_reads_no_image_commits_the_written_ddl_unseen(host):
    client, service, _, sent = host
    view = _wait(service, _start(client, model="openai:fixture-text", sketch="on")["execution_id"])
    assert view["phase"]["tag"] == "score_ready", view
    assert [entry["tag"] for entry in sent] == ["read_description", "write_description_ddl"]
    assert service.execution("owner", view["execution_id"]).config["description_ddl"] == {"review": False}


def test_a_child_takes_its_parents_route_and_the_stages_send_what_they_sent(host):
    client, service, _, sent = host
    parent = _wait(service, _start(client, sketch="on")["execution_id"])
    parent = service.command("owner", parent["execution_id"], {"tag": "perform"})
    sent.clear()
    forked = client.post(f"/api/pipeline/variations/{parent['variation_id']}/fork-description", headers={"x-owner": "owner"},
                         json={"expected_revision": parent["authority"]["revision"], "description": POEM,
                               "options": {"save_artifacts": False}})
    assert forked.status_code == 200, forked.text
    child = _wait(service, forked.json()["execution_id"])
    assert child["route"] == "read_and_draw"
    assert [entry["tag"] for entry in sent] == ["write_description_ddl", "review_description_ddl"]
    stages = service.start("owner", "description", POEM, options={"stage1_model": "openai:fixture-vision", "route": "stages"})
    run = service.execution("owner", stages["execution_id"])
    assert "description_ddl" not in run.config
    assert run.view()["route"] == "stages"


def test_read_and_draw_sends_with_the_image_tabs_limit_and_records_apart(host, monkeypatch):
    _, _, effects, _ = host
    from inku_server import pipeline_product
    from inku_server.pipeline_provider import provider_stage_record
    limits = []

    class Transport:
        def __init__(self, options, **kwargs):
            limits.append(options.max_tokens)

        def __call__(self, action):
            return {"tag": "provider_failed", "failure": "transport_unavailable", "elapsed_ms": "0"}

    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", Transport)
    context = {"host_options": {"stage1_model": "openai:fixture-vision"}}
    tags = ("read_description", "write_description_ddl", "review_description_ddl")
    for tag in tags:
        effects.provider_for("owner", context, [])({"tag": tag, "identity": {"attempt": 1}})
    assert limits == [8192, 8192, 8192]
    assert {provider_stage_record(tag) for tag in tags} == {"read_and_draw"}
    assert context["provider_failure"]["stage"] == "read_and_draw"


# --------------------------------------------------------------------------- #
# The composition and laws (step 2, 2026-10-26)                                #
# --------------------------------------------------------------------------- #

# The answers the core's own test gives (machine/description.rs): the woman on
# the golden section's upper left crossing, written 0.03 off it and fitted.
COMPOSITION = {
    "thesis": "女の姿を黄金分割の左上の交点に置き、右下を広く空ける。",
    "form": "one_corner",
    "things": [
        {"thing": 1, "what": "女の姿", "role": "focal", "kind": "cluster", "quote": "妹"},
        {"thing": 2, "what": "紫の影", "role": "accent", "kind": "cluster", "quote": "紫"},
    ],
    "main_law": "B1",
    "laws": {"B1": {"targets": [{"thing": 1, "at": "point_ul"}]}},
    "reason": "「紫のにほへる妹」の姿を画の骨にするため、黄金分割の交点に置いた。",
}
WOMAN = "画面の横0.4、縦0.4の位置に、直径0.3の紫の塗りの円を1個置く。"
FITTED = "画面の横0.381966、縦0.381966の位置に、直径0.3の紫の塗りの円を1個置く。"
SHADE = "画面の横0.6、縦0.6の位置に、幅0.2、高さ0.15の灰の薄い塗りの三角を1個置く。"


def _sentences(woman: str) -> dict:
    return {"sentences": [{"thing": 0, "text": "背景を白で埋める。"}, {"thing": 1, "text": woman},
                          {"thing": 2, "text": SHADE}], "figures": []}


@pytest.fixture
def composed(monkeypatch):
    monkeypatch.setitem(ANSWERS, "compose_description", ("description_composed", COMPOSITION))
    monkeypatch.setitem(ANSWERS, "write_description_ddl", ("description_ddl_written", _sentences(WOMAN)))
    monkeypatch.setitem(ANSWERS, "review_description_ddl", ("description_ddl_reviewed", _sentences(FITTED)))


def test_the_composition_is_decided_written_by_and_saved_with_the_work(host, composed):
    client, service, _, sent = host
    view = _wait(service, _start(client, sketch="on", composition="on")["execution_id"])
    assert view["phase"]["tag"] == "score_ready", view
    assert [(entry["tag"], entry["images"]) for entry in sent] == [
        ("read_description", 0), ("compose_description", 0), ("write_description_ddl", 0), ("review_description_ddl", 1)]
    # The composition is decided from the description and its reading.
    assert json.loads(sent[1]["message"]).get("reading") is not None
    record = view["description_ddl"]["composition"]
    assert record["state"] == "used" and record["answer"]["main_law"] == "B1"
    assert record["things"] == [0, 1, 2]
    assert len(record["measures"]) == 2
    done = service.command("owner", view["execution_id"], {"tag": "perform"})
    item = db.get_items("owner", [done["result"]["history_id"]])[0]
    assert item["description_ddl"]["composition"] == record
    assert FITTED in item["ddl"]
    prompts = client.get(f"/api/pipeline/variations/{view['variation_id']}/system-prompts", headers={"x-owner": "owner"})
    stages = prompts.json()
    assert stages["description_composition"]["system"].startswith("あなたは inku の構図の係である。")
    assert stages["description_composition"]["message"] == sent[1]["message"]


def test_without_the_composition_read_and_draw_sends_what_it_sent(host):
    client, service, _, sent = host
    view = _wait(service, _start(client, sketch="on", composition="off")["execution_id"])
    assert [entry["tag"] for entry in sent] == ["read_description", "write_description_ddl", "review_description_ddl"]
    assert "composition" not in view["description_ddl"]
    run = service.execution("owner", view["execution_id"])
    assert run.context["host_options"]["composition"] == "off"


def test_only_read_and_draw_with_the_composition_on_asks_the_core_for_it():
    from inku_server.pipeline_api import _route_fields

    def fields(**options):
        return _route_fields({"host_options": options}, POEM)

    assert fields(route="read_and_draw", composition="on")["composition"] == {"mode": "on"}
    assert "composition" not in fields(route="read_and_draw", composition="off")
    assert "composition" not in fields(route="read_and_draw")
    assert fields(route="stages", composition="on") == {}


def test_a_child_keeps_its_parents_composition(host, composed):
    client, service, _, sent = host
    parent = _wait(service, _start(client, composition="on")["execution_id"])
    parent = service.command("owner", parent["execution_id"], {"tag": "perform"})
    sent.clear()
    forked = client.post(f"/api/pipeline/variations/{parent['variation_id']}/fork-description", headers={"x-owner": "owner"},
                         json={"expected_revision": parent["authority"]["revision"], "description": POEM,
                               "options": {"save_artifacts": False}})
    assert forked.status_code == 200, forked.text
    child = _wait(service, forked.json()["execution_id"])
    assert [entry["tag"] for entry in sent] == ["compose_description", "write_description_ddl", "review_description_ddl"]
    assert child["description_ddl"]["composition"]["state"] == "used"


def test_the_composition_is_sent_with_the_limit_and_recorded_as_read_and_draw(host, monkeypatch):
    _, _, effects, _ = host
    from inku_server import chatgpt_provider, pipeline_product, provider_wire
    from inku_server.pipeline_candidate import _ACTION_STAGES
    from inku_server.pipeline_provider import provider_stage_record
    limits = []

    class Transport:
        def __init__(self, options, **kwargs):
            limits.append(options.max_tokens)

        def __call__(self, action):
            return {"tag": "provider_failed", "failure": "transport_unavailable", "elapsed_ms": "0"}

    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", Transport)
    context = {"host_options": {"stage1_model": "openai:fixture-vision"}}
    effects.provider_for("owner", context, [])({"tag": "compose_description", "identity": {"attempt": 1}})
    assert limits == [8192]
    assert provider_stage_record("compose_description") == "read_and_draw"
    assert _ACTION_STAGES["compose_description"] == "read_and_draw"
    assert "compose_description" in provider_wire.READ_AND_DRAW_EFFECTS
    assert "compose_description" in chatgpt_provider.EFFECTS
    assert "compose_description" not in provider_wire.IMAGE_EFFECTS
