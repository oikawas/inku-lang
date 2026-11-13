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

    def offered(provider, model, settings, *, purpose, normalized_settings=None):
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


@pytest.mark.parametrize("kind,mode,expected", [
    ("description", "auto", "71"), ("description", "fixed", None),
    ("description", "random", None), ("image", "auto", None),
])
def test_catalog_seed_follows_only_description_auto(host, kind, mode, expected):
    _, _, effects, _ = host
    config, _ = effects.prepare("owner", kind, POEM, {"stage1_model": "openai:fixture-vision", "render_seed": 71,
                                                      "catalog_mode": mode}, None)
    assert config.get("catalog_seed") == expected
    # A saved config cannot carry its old seed into another run.
    parent = {"saved_config": config, "host_options": {"stage1_model": "openai:fixture-vision", "catalog_mode": mode}, "metadata": {}}
    config2, _ = effects.prepare("owner", kind, POEM, {"render_seed": 93, "catalog_mode": mode}, parent)
    assert config2.get("catalog_seed") == ("93" if expected else None)


@pytest.mark.parametrize("method", ["model", "seed"])
def test_real_core_catalog_reading_is_saved_and_not_inherited(host, method):
    from inku_server.api_core.deps import _current_user
    from inku_server.api_core.routers.history import router as history_router
    client, service, _, sent = host
    client.app.include_router(history_router)
    client.app.dependency_overrides[_current_user] = lambda: {"id": "owner", "role": "user"}
    prompt_ids = []

    def provider(_owner, context, images=()):
        def perform(action):
            tag = action["tag"]
            prompt = action["payload"]["prompt"]
            record_system_prompt(context, action)
            if tag == "select_description_catalog":
                prompt_ids.append(prompt["prompt_id"])
                if prompt["prompt_id"] == "inku.description-color-reading-prompt.v1":
                    value = "none" if method == "seed" else "bright"
                    response = {"note": "", "brightness": {"value": value, "quote": "" if method == "seed" else "紫"},
                                "vividness": {"value": "none", "quote": ""}, "warmth": {"value": "none", "quote": ""}, "colors": []}
                else:
                    response = {"catalog_id": "k01"}
                result_tag = "description_catalog_selected"
            else:
                result_tag, response = ANSWERS[tag]
            return {"tag": result_tag, "identity": action["identity"], "response": json.dumps(response, ensure_ascii=False), "elapsed_ms": "1"}
        return perform

    service.provider_with_context = provider
    started = _start(client, model="openai:fixture-text", catalog_mode="auto", render_seed=71)
    view = _wait(service, started["execution_id"])
    assert view["phase"]["tag"] == "score_ready", view
    done = service.command("owner", view["execution_id"], {"tag": "perform"})
    record = done["result"]["catalog_reading"]
    assert record["method"] == method
    assert record["catalog_id"] == done["result"]["catalog_id"]
    assert len(prompt_ids) == (2 if method == "model" else 1)
    if method == "model":
        assert record["catalog_id"] == record["candidate_order"][0]
        prompts = service.system_prompts("owner", view["variation_id"])
        assert prompts["catalog_reading"]["prompt_id"] == prompt_ids[0]
        assert prompts["catalog"]["prompt_id"] == prompt_ids[1]
    response = client.get("/api/history")
    assert response.status_code == 200, response.text
    item = next(item for item in response.json()["items"] if item["id"] == done["result"]["history_id"])
    assert item["catalog_reading"] == record
    child = client.post(f"/api/pipeline/variations/{view['variation_id']}/fork-description", headers={"x-owner": "owner"},
        json={"expected_revision": done["authority"]["revision"], "description": POEM,
              "options": {"catalog_mode": "fixed", "save_artifacts": False}})
    assert child.status_code == 200, child.text
    child_view = _wait(service, child.json()["execution_id"])
    child_done = service.command("owner", child_view["execution_id"], {"tag": "perform"})
    assert "catalog_reading" not in child_done["result"]


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
    # The colors come only after a composition, so this run asks for none.
    assert service.execution("owner", view["execution_id"]).config["description_ddl"] == {"review": False, "colors": True}


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


# The colors chosen after the review (2026-10-26): the shade takes the blue.
COLORS = {"main_law": "D5", "laws": {"D5": {"hue": "blue", "layer": 1}}, "reason": "青を軸に近い色でまとめる。"}


@pytest.fixture
def composed(monkeypatch):
    monkeypatch.setitem(ANSWERS, "compose_description", ("description_composed", COMPOSITION))
    monkeypatch.setitem(ANSWERS, "write_description_ddl", ("description_ddl_written", _sentences(WOMAN)))
    monkeypatch.setitem(ANSWERS, "review_description_ddl", ("description_ddl_reviewed", _sentences(FITTED)))
    monkeypatch.setitem(ANSWERS, "choose_colors", ("colors_chosen", COLORS))


def test_the_composition_is_decided_written_by_and_saved_with_the_work(host, composed):
    client, service, _, sent = host
    view = _wait(service, _start(client, sketch="on", composition="on")["execution_id"])
    assert view["phase"]["tag"] == "score_ready", view
    assert [(entry["tag"], entry["images"]) for entry in sent] == [
        ("read_description", 0), ("compose_description", 0), ("write_description_ddl", 0), ("review_description_ddl", 1),
        ("choose_colors", 0)]
    # The composition is decided from the description and its reading.
    assert json.loads(sent[1]["message"]).get("reading") is not None
    # The colors are asked with the thing each layer draws.
    assert "## 層の物（読んで描くの構図と法則）" in sent[4]["message"]
    record = view["description_ddl"]["composition"]
    assert record["state"] == "used" and record["answer"]["main_law"] == "B1"
    assert record["things"] == [0, 1, 2]
    assert len(record["measures"]) == 2
    colors = record["colors"]
    assert colors["state"] == "used" and colors["main_law"] == "D5"
    assert [change["how"] for change in colors["changes"]] == ["color_word"]
    done = service.command("owner", view["execution_id"], {"tag": "perform"})
    item = db.get_items("owner", [done["result"]["history_id"]])[0]
    assert item["description_ddl"]["composition"] == record
    assert FITTED in item["ddl"]
    assert colors["changes"][0]["after"][0] in item["ddl"]
    prompts = client.get(f"/api/pipeline/variations/{view['variation_id']}/system-prompts", headers={"x-owner": "owner"})
    stages = prompts.json()
    assert stages["description_composition"]["system"].startswith("あなたは inku の構図の係である。")
    assert stages["description_composition"]["message"] == sent[1]["message"]
    # The color request is kept in the colors tab, as the current stages keep it.
    assert stages["colors"]["message"] == sent[4]["message"]


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
    assert fields(route="read_and_draw", composition="on", composition_form="bands")["composition"] == {"mode": "on", "form": "bands"}
    assert fields(route="read_and_draw", composition="on", composition_main_law="B10")["composition"] == {
        "mode": "on", "main_law": "B10"}
    assert fields(route="read_and_draw", composition="on", composition_thesis="女を中心に置く。")["composition"] == {
        "mode": "on", "thesis": "女を中心に置く。"}
    assert "composition" not in fields(route="read_and_draw", composition="off")
    assert "composition" not in fields(route="read_and_draw")
    assert fields(route="stages", composition="on") == {}


def test_composition_form_candidate_saves_its_actual_execution_once(host, composed, monkeypatch):
    client, service, _, sent = host
    parent = _wait(service, _start(client, composition="on")["execution_id"])
    parent = service.command("owner", parent["execution_id"], {"tag": "perform"})
    parent_result = parent["result"]
    fork = client.post(f"/api/pipeline/variations/{parent['variation_id']}/fork-description", headers={"x-owner": "owner"},
        json={"expected_revision": parent["authority"]["revision"], "description": POEM, "options": {
            "route": "read_and_draw", "composition": "on", "composition_form": "one_corner",
            "save_history": False, "save_artifacts": False, "count_generation": True,
            "lineage_parent_node_id": parent_result["lineage_node_id"], "derivation_kind": "composition_form_change"}})
    assert fork.status_code == 200, fork.text
    candidate = _wait(service, fork.json()["execution_id"])
    assert candidate["description_ddl"]["composition"]["requested_form"] == "one_corner"
    assert json.loads(next(row["message"] for row in reversed(sent) if row["tag"] == "compose_description"))["composition_form"] == "one_corner"
    done = service.command("owner", candidate["execution_id"], {"tag": "perform"})
    assert not done["result"].get("history_id")
    count = done["result"]["user_generation_count"]
    body = {"lineage_parent_node_id": parent_result["lineage_node_id"], "derivation_kind": "composition_form_change", "derivation_metadata": {}}
    path = f"/api/pipeline/executions/{candidate['execution_id']}/save"
    first = client.post(path, json=body, headers={"x-owner": "owner"})
    assert first.status_code == 200, first.text
    # A completed run may leave the in-memory pool; its stored execution can be restored.
    service._runs.pop(("owner", candidate["execution_id"]))
    second = client.post(path, json=body, headers={"x-owner": "owner"})
    assert second.status_code == 200 and first.json()["history_id"] == second.json()["history_id"]
    item = db.get_items("owner", [first.json()["history_id"]])[0]
    assert item["description_ddl"]["composition"]["requested_form"] == "one_corner"
    assert item["derivation_metadata"] == {"form_from": "one_corner", "form_to": "one_corner"}
    with db.SessionLocal() as session:
        assert session.get(UserAccountRow, "owner").image_generation_count == count
    assert client.post(path, json=body, headers={"x-owner": "other"}).status_code == 404
    assert client.post(f"/api/pipeline/executions/{parent['execution_id']}/save", json=body, headers={"x-owner": "owner"}).status_code == 409
    assert client.post(path, json={**body, "lineage_parent_node_id": "wrong"}, headers={"x-owner": "owner"}).status_code == 422
    monkeypatch.setattr(db, "history_description_locked", lambda _history_id: True)
    assert client.post(path, json=body, headers={"x-owner": "owner"}).status_code == 409


def test_main_law_candidate_saves_with_the_laws_it_changed(host, composed):
    client, service, _, sent = host
    parent = _wait(service, _start(client, composition="on")["execution_id"])
    parent = service.command("owner", parent["execution_id"], {"tag": "perform"})
    node = parent["result"]["lineage_node_id"]
    # The fixture's composer answers B1 in one_corner, so the named law is kept.
    fork = client.post(f"/api/pipeline/variations/{parent['variation_id']}/fork-description", headers={"x-owner": "owner"},
        json={"expected_revision": parent["authority"]["revision"], "description": POEM, "options": {
            "route": "read_and_draw", "composition": "on", "composition_form": "one_corner", "composition_main_law": "B1",
            "save_history": False, "save_artifacts": False, "count_generation": True,
            "lineage_parent_node_id": node, "derivation_kind": "composition_form_change"}})
    assert fork.status_code == 200, fork.text
    candidate = _wait(service, fork.json()["execution_id"])
    record = candidate["description_ddl"]["composition"]
    assert record["requested_main_law"] == "B1" and record["requested_form"] == "one_corner"
    message = json.loads(next(row["message"] for row in reversed(sent) if row["tag"] == "compose_description"))
    assert message["composition_main_law"] == "B1" and message["composition_form"] == "one_corner"
    service.command("owner", candidate["execution_id"], {"tag": "perform"})
    saved = client.post(f"/api/pipeline/executions/{candidate['execution_id']}/save", headers={"x-owner": "owner"},
                        json={"lineage_parent_node_id": node, "derivation_kind": "composition_form_change",
                              "derivation_metadata": {"ignored": True}})
    assert saved.status_code == 200, saved.text
    item = db.get_items("owner", [saved.json()["history_id"]])[0]
    assert item["derivation_kind"] == "composition_form_change"
    assert item["derivation_metadata"] == {"main_law_from": "B1", "main_law_to": "B1", "form": "one_corner"}
    assert item["description_ddl"]["composition"]["requested_main_law"] == "B1"


def test_a_moved_thing_is_a_ddl_fork_saved_as_a_layout_change_and_held(host, composed, monkeypatch):
    client, service, _, _ = host
    parent = _wait(service, _start(client, composition="on")["execution_id"])
    parent = service.command("owner", parent["execution_id"], {"tag": "perform"})
    history_id, node = parent["result"]["history_id"], parent["result"]["lineage_node_id"]
    ddl = db.get_items("owner", [history_id])[0]["ddl"]
    place = {"title": "波", "thing": 1, "at": "center", "at_from": None, "from": [0.5, 0.2], "to": [0.5, 0.5],
             "clamped": False}
    options = {"save_history": False, "save_artifacts": False, "count_generation": False,
               "lineage_parent_node_id": node, "derivation_kind": "layout_change",
               "derivation_metadata": {"place": place}}
    fork = client.post(f"/api/pipeline/history/{history_id}/fork", headers={"x-owner": "owner"},
                       json={"kind": "direct_ddl", "text": ddl, "options": options})
    assert fork.status_code == 200, fork.text
    candidate = _wait(service, fork.json()["execution_id"])
    candidate = service.command("owner", candidate["execution_id"], {"tag": "perform"})
    assert not candidate["result"].get("history_id")
    path = f"/api/pipeline/executions/{candidate['execution_id']}/save"
    body = {"lineage_parent_node_id": node, "derivation_kind": "layout_change", "derivation_metadata": {}}
    # The kind is the execution's own.
    assert client.post(path, json={**body, "derivation_kind": "model_comparison"},
                       headers={"x-owner": "owner"}).status_code == 422
    # A parent its DDL holds still takes a moved thing: the DDL is kept.
    locked = db.history_description_locked
    monkeypatch.setattr(db, "history_description_locked", lambda _history_id: True)
    saved = client.post(path, json=body, headers={"x-owner": "owner"})
    assert saved.status_code == 200, saved.text
    monkeypatch.setattr(db, "history_description_locked", locked)
    item = db.get_items("owner", [saved.json()["history_id"]])[0]
    assert item["derivation_kind"] == "layout_change"
    assert item["derivation_metadata"] == {"place": {"title": "波", "thing": 1, "at_from": None, "at": "center"}}
    # The child was drawn from its DDL, so its description is held (step 3).
    assert item["description_locked"] is True
    # It keeps the parent's composition with the moved thing's new place, and
    # the save answers it as the listing does (step 3, 2026-11-13).
    inherited = item["composition_inherited"]
    assert inherited["history_id"] == history_id and inherited["via"] == ["layout_change"]
    assert inherited["places"] == [{"thing": 1, "at": "center"}]
    assert saved.json()["composition_inherited"] == inherited


def _thesis_fork(client, service, parent, node, **thesis):
    fork = client.post(f"/api/pipeline/variations/{parent['variation_id']}/fork-description", headers={"x-owner": "owner"},
        json={"expected_revision": parent["authority"]["revision"], "description": POEM, "options": {
            "route": "read_and_draw", "composition": "on", **thesis,
            "save_history": False, "save_artifacts": False, "count_generation": True,
            "lineage_parent_node_id": node, "derivation_kind": "composition_form_change"}})
    assert fork.status_code == 200, fork.text
    candidate = _wait(service, fork.json()["execution_id"])
    service.command("owner", candidate["execution_id"], {"tag": "perform"})
    return candidate


def test_thesis_candidate_saves_with_the_thesis_it_fixed(host, composed):
    client, service, _, sent = host
    parent = _wait(service, _start(client, composition="on")["execution_id"])
    parent = service.command("owner", parent["execution_id"], {"tag": "perform"})
    node = parent["result"]["lineage_node_id"]
    fixed = "女の姿を画面の中心に大きく置き、紫の影を四隅に散らす。"
    candidate = _thesis_fork(client, service, parent, node, composition_thesis=f"  {fixed}\n")
    record = candidate["description_ddl"]["composition"]
    # The composer answered its own thesis; the fixed one is kept, and the composer's beside it.
    assert record["requested_thesis"] == fixed and record["answer"]["thesis"] == fixed
    assert record["answered_thesis"] == COMPOSITION["thesis"]
    assert "requested_form" not in record and "requested_main_law" not in record
    message = json.loads(next(row["message"] for row in reversed(sent) if row["tag"] == "compose_description"))
    assert message["composition_thesis"] == fixed and "composition_form" not in message
    saved = client.post(f"/api/pipeline/executions/{candidate['execution_id']}/save", headers={"x-owner": "owner"},
                        json={"lineage_parent_node_id": node, "derivation_kind": "composition_form_change"})
    assert saved.status_code == 200, saved.text
    item = db.get_items("owner", [saved.json()["history_id"]])[0]
    assert item["derivation_metadata"] == {"thesis_from": COMPOSITION["thesis"], "thesis_to": fixed,
                                           "thesis_source": "author"}
    # A proposed thesis names the request that proposed it.
    proposed = _thesis_fork(client, service, parent, node, composition_thesis=fixed,
                            composition_thesis_source="proposed", composition_thesis_prompt_digest="sha256:ab")
    saved = client.post(f"/api/pipeline/executions/{proposed['execution_id']}/save", headers={"x-owner": "owner"},
                        json={"lineage_parent_node_id": node, "derivation_kind": "composition_form_change"})
    assert saved.status_code == 200, saved.text
    item = db.get_items("owner", [saved.json()["history_id"]])[0]
    assert item["derivation_metadata"] == {"thesis_from": COMPOSITION["thesis"], "thesis_to": fixed,
                                           "thesis_source": "proposed", "thesis_prompt_digest": "sha256:ab"}


def test_theses_are_proposed_under_the_works_connection_and_asked_again_once(host, composed, monkeypatch):
    from inku_server import pipeline_runtime
    from inku_server.api_core.deps import _current_user
    from inku_server.api_core.routers.history import router as history_router
    from inku_server.typed_send import TYPED_SEND_ACTION

    client, service, _, _ = host
    client.app.include_router(history_router)
    client.app.dependency_overrides[_current_user] = lambda: {"id": "owner", "role": "user"}
    monkeypatch.setattr(pipeline_runtime, "get_service", lambda: service)
    parent = _wait(service, _start(client, composition="on")["execution_id"])
    parent = service.command("owner", parent["execution_id"], {"tag": "perform"})
    history_id = parent["result"]["history_id"]
    asked = []
    answers = iter([{"theses": ["一つ目。", "二つ目。", "二つ目。", "四つ目。"]},
                    {"theses": ["一つ目。", "二つ目。", "三つ目。", "四つ目。"]}])
    fallback = service.provider_with_context

    def provider(owner, context, images=()):
        if context.get("execution_id", "").startswith("theses:"):
            def perform(action):
                assert action["tag"] == TYPED_SEND_ACTION
                assert context["host_options"]["stage1_model"] == "openai:fixture-text"
                asked.append(action["payload"]["prompt"])
                return {"tag": "normalized_ddl_generated", "identity": action["identity"],
                        "response": json.dumps(next(answers), ensure_ascii=False), "elapsed_ms": "1"}
            return perform
        return fallback(owner, context, images)

    service.provider_with_context = provider
    response = client.post("/api/composition/theses", json={"history_id": history_id, "model": "openai:fixture-text"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["theses"] == ["一つ目。", "二つ目。", "三つ目。", "四つ目。"]
    assert body["current_thesis"] == COMPOSITION["thesis"] and body["model"] == "openai:fixture-text"
    assert [prompt["prompt_id"] for prompt in asked] == ["inku.description-theses-prompt.v1"] * 2
    first, again = (json.loads(prompt["message"]) for prompt in asked)
    assert first["current_thesis"] == COMPOSITION["thesis"] and first.get("reading") is None
    assert "theses_feedback" not in first
    assert again["theses_feedback"]["problems"] == ["3 つ目の命題が、2 つ目と同じである。"]
    # The digest is the accepted request's, as typed_send sent it.
    assert body["prompt_digest"] == asked[1]["prompt_digest"]
    missing = client.post("/api/composition/theses", json={"history_id": "nothing", "model": "openai:fixture-text"})
    assert missing.status_code == 404


def test_model_candidate_saves_its_execution_with_its_composition(host, composed, monkeypatch):
    client, service, _, _ = host
    parent = _wait(service, _start(client, composition="on")["execution_id"])
    parent = service.command("owner", parent["execution_id"], {"tag": "perform"})
    node = parent["result"]["lineage_node_id"]
    options = {"route": "read_and_draw", "composition": "on", "stage1_model": "openai:fixture-text",
               "stage2_model": "openai:fixture-text", "save_history": False, "save_artifacts": False,
               "count_generation": True, "lineage_parent_node_id": node, "derivation_kind": "model_comparison"}
    fork_path = f"/api/pipeline/variations/{parent['variation_id']}/fork-description"
    fork = client.post(fork_path, headers={"x-owner": "owner"},
                       json={"expected_revision": parent["authority"]["revision"], "description": POEM, "options": options})
    assert fork.status_code == 200, fork.text
    candidate = _wait(service, fork.json()["execution_id"])
    done = service.command("owner", candidate["execution_id"], {"tag": "perform"})
    assert not done["result"].get("history_id")
    path = f"/api/pipeline/executions/{candidate['execution_id']}/save"
    body = {"lineage_parent_node_id": node, "derivation_kind": "model_comparison", "derivation_metadata": {}}
    # Another kind than the execution's is refused.
    assert client.post(path, json={**body, "derivation_kind": "composition_form_change"},
                       headers={"x-owner": "owner"}).status_code == 422
    saved = client.post(path, json=body, headers={"x-owner": "owner"})
    assert saved.status_code == 200, saved.text
    item = db.get_items("owner", [saved.json()["history_id"]])[0]
    assert item["derivation_kind"] == "model_comparison"
    assert item["derivation_metadata"] == {"comparison_mode": "common", "compared_model": "openai:fixture-text",
                                           "stage1_model": "openai:fixture-text", "stage2_model": "openai:fixture-text"}
    assert item["description_ddl"]["composition"]["state"] == "used"
    assert "composition_inherited" not in item
    # A parent its DDL holds refuses another model, as it refuses changed words.
    monkeypatch.setattr(db, "history_description_locked", lambda _history_id: True)
    linked = client.post(f"/api/pipeline/history/{parent['result']['history_id']}/fork", headers={"x-owner": "owner"},
                         json={"kind": "description", "text": POEM, "options": options})
    assert linked.status_code == 409, linked.text
    assert client.post(path, json=body, headers={"x-owner": "owner"}).status_code == 409


@pytest.mark.parametrize("options", [
    {"route": "stages", "composition": "on", "composition_form": "bands"},
    {"route": "read_and_draw", "composition": "off", "composition_form": "bands"},
    {"route": "read_and_draw", "composition": "on", "composition_form": "not_a_form"},
    {"route": "stages", "composition": "on", "composition_main_law": "B10"},
    {"route": "read_and_draw", "composition": "off", "composition_main_law": "B10"},
    {"route": "read_and_draw", "composition": "on", "composition_main_law": "B21"},
    {"route": "read_and_draw", "composition": "on", "composition_main_law": "B99"},
    {"route": "stages", "composition": "on", "composition_thesis": "女を中心に置く。"},
    {"route": "read_and_draw", "composition": "off", "composition_thesis": "女を中心に置く。"},
    {"route": "read_and_draw", "composition": "on", "composition_thesis": "  "},
    {"route": "read_and_draw", "composition": "on", "composition_thesis": "命" * 401},
    {"route": "read_and_draw", "composition": "on", "composition_thesis": "女を中心に置く。", "composition_form": "bands"},
    {"route": "read_and_draw", "composition": "on", "composition_thesis": "女を中心に置く。", "composition_main_law": "B10"},
    {"route": "read_and_draw", "composition": "on", "composition_thesis_source": "author"},
    {"route": "read_and_draw", "composition": "on", "composition_thesis": "女を中心に置く。",
     "composition_thesis_source": "proposed"},
    {"route": "read_and_draw", "composition": "on", "composition_thesis": "女を中心に置く。",
     "composition_thesis_source": "author", "composition_thesis_prompt_digest": "sha256:00"},
])
def test_composition_form_rejects_invalid_route_or_value(host, options):
    client, _, _, _ = host
    response = client.post("/api/pipeline/variations", headers={"x-owner": "owner"}, json={
        "kind": "description", "text": POEM, "options": {"stage1_model": "openai:fixture-vision", **options},
    })
    assert response.status_code == 422


def test_a_child_keeps_its_parents_composition(host, composed):
    client, service, _, sent = host
    parent = _wait(service, _start(client, composition="on", composition_form="one_corner")["execution_id"])
    parent = service.command("owner", parent["execution_id"], {"tag": "perform"})
    sent.clear()
    forked = client.post(f"/api/pipeline/variations/{parent['variation_id']}/fork-description", headers={"x-owner": "owner"},
                         json={"expected_revision": parent["authority"]["revision"], "description": POEM,
                               "options": {"save_artifacts": False}})
    assert forked.status_code == 200, forked.text
    child = _wait(service, forked.json()["execution_id"])
    assert [entry["tag"] for entry in sent] == ["compose_description", "write_description_ddl", "review_description_ddl",
                                                "choose_colors"]
    assert child["description_ddl"]["composition"]["state"] == "used"
    assert "requested_form" not in child["description_ddl"]["composition"]
    assert child["description_ddl"]["composition"]["colors"]["state"] == "used"


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
