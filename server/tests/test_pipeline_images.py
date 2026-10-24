"""Image input stays transient while the real core authors and saves its DDL."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from io import BytesIO

import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence.schema import Base, UserAccountRow
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_api import PipelineService, pipeline_router, register_pipeline_errors
from inku_server.pipeline_candidate import CandidateHostError, PipelineBinding
from inku_server.pipeline_defaults import default_manifest
from inku_server.pipeline_images import PendingImages, prepare_image
from inku_server.pipeline_product import ProductPipelineEffects


def _file(format="PNG", size=(80, 40), *, exif=None):
    data = BytesIO()
    Image.new("RGB", size, (210, 30, 40)).save(data, format=format, **({"exif": exif} if exif else {}))
    return data.getvalue()


@pytest.mark.parametrize("format", ["JPEG", "PNG", "GIF", "TIFF"])
def test_inputs_become_small_metadata_free_jpegs(format):
    binding = PipelineBinding()
    prepared = prepare_image(binding, _file(format, (1600, 800)))
    assert (prepared.original_width, prepared.original_height) == (1600, 800)
    canvas = json.loads(binding.image_canvas(b'{"original":[1600,800]}'))
    assert (prepared.reference["width"], prepared.reference["height"]) == tuple(canvas["sent"])
    assert prepared.nearest_format_id == canvas["nearest_format_id"]
    assert prepared.reference["sha256"] == hashlib.sha256(prepared.jpeg).hexdigest()
    with Image.open(BytesIO(prepared.jpeg)) as image:
        assert image.format == "JPEG" and image.mode == "RGB"
        assert not image.getexif()
    assert prepared.thumbnail.startswith("data:image/jpeg;base64,")


def test_orientation_and_first_gif_frame_are_the_input_seen():
    binding = PipelineBinding()
    exif = Image.Exif()
    exif[274] = 6
    oriented = prepare_image(binding, _file("JPEG", (80, 40), exif=exif))
    assert (oriented.original_width, oriented.original_height) == (40, 80)
    data = BytesIO()
    Image.new("RGB", (20, 10), "red").save(
        data, format="GIF", save_all=True, append_images=[Image.new("RGB", (20, 10), "blue")],
    )
    first = prepare_image(binding, data.getvalue())
    with Image.open(BytesIO(first.jpeg)) as image:
        red, _, blue = image.getpixel((0, 0))
        assert red > 200 and blue < 20
    with pytest.raises(CandidateHostError, match="image_invalid"):
        prepare_image(binding, b"not an image")
    policy = json.loads(binding.image_input_policy())
    policy["policy"]["max_bytes"] = 1
    binding.image_input_policy = lambda: json.dumps(policy)
    with pytest.raises(CandidateHostError, match="image_too_large"):
        prepare_image(binding, _file())


def test_waiting_uploads_are_owner_scoped_bounded_and_expire():
    clock = [0]
    pending = PendingImages(1, clock=lambda: clock[0])
    image = prepare_image(PipelineBinding(), _file())
    try:
        first = pending.add("owner", image)
        with pytest.raises(CandidateHostError, match="image_missing"):
            pending.get("other", first["image_id"])
        second = pending.add("owner", image)
        with pytest.raises(CandidateHostError, match="image_missing"):
            pending.get("owner", first["image_id"])
        clock[0] = 901
        with pytest.raises(CandidateHostError, match="image_missing"):
            pending.get("owner", second["image_id"])
    finally:
        pending.clear()


@pytest.fixture
def image_host(tmp_path, monkeypatch):
    from inku_server import model_settings
    from inku_server.api_core import rendering, thumbnails
    binding = PipelineBinding()
    engine = create_engine(f"sqlite:///{tmp_path / 'image.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(rendering, "_submit_history_artifact_save", lambda _: None)
    monkeypatch.setattr(thumbnails, "submit_thumbnail_build", lambda _: None)
    admission = []

    def offered(provider, model, settings, *, purpose):
        admission.append((provider, model, purpose))
        return provider == "openai" and model == "fixture-vision" and purpose == "vision"

    monkeypatch.setattr(model_settings, "model_is_offered", offered)
    with engine.begin() as connection:
        connection.execute(UserAccountRow.__table__.insert().values(
            id="owner", username="owner", email="owner@example.test", password_hash="unused", role="user", at=1,
        ))
    manifest = default_manifest(binding)
    effects = ProductPipelineEffects(binding, manifest)
    store = VariationAuthorityStore(engine)
    sent = []

    def provider(owner, context, images):
        def perform(action):
            assert owner == "owner"
            refs = action["payload"]["prompt"]["images"]
            assert len(images) == len(refs)
            for data_url, ref in zip(images, refs, strict=True):
                assert hashlib.sha256(base64.b64decode(data_url.split(",", 1)[1])).hexdigest() == ref["sha256"]
            sent.append((action["tag"], list(refs)))
            if action["tag"] == "select_image_catalog":
                response = {"catalog_id": "default"}
                tag = "image_catalog_selected"
            else:
                response = {"ddl": "画面比2:1。\n背景を黄で埋める。\n画面の横0.3、縦0.7の位置に、直径0.1の赤の塗りの円を1個置く。"}
                tag = {"write_image_ddl": "image_ddl_written", "review_image_ddl": "image_ddl_reviewed"}[action["tag"]]
            return {"tag": tag, "identity": action["identity"], "response": json.dumps(response, ensure_ascii=False),
                    "elapsed_ms": "1"}
        return perform

    service = PipelineService(
        binding, store, config_for=effects.settings.config_for,
        prepare_for=effects.prepare, provider_for=lambda _: pytest.fail("non-image provider"),
        image_provider_with_context=provider, image_review_options=effects.image_review_options,
        render_for=None, render_with_context=effects.render_options, project_result=effects.save_result,
        max_workers=1, max_effect_steps=32, max_retained_runs=2,
    )
    app = FastAPI()

    def actor(x_owner: str = Header(...)):
        return {"id": x_owner}

    app.include_router(pipeline_router(service, actor))
    register_pipeline_errors(app)
    with TestClient(app) as client:
        yield client, service, effects, sent, admission
    service.close()
    engine.dispose()


def _wait(service, execution_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = service.execution("owner", execution_id)
        view = run.view()
        if not view["busy"]:
            # The worker clears transient images after the core's final state.
            service._jobs[("owner", execution_id)].result(timeout=max(0.001, deadline - time.monotonic()))
            return run, view
        time.sleep(0.01)
    pytest.fail("image run did not finish")


def test_image_http_to_review_commit_and_saved_history_keeps_no_input_bytes(image_host):
    client, service, effects, sent, admission = image_host
    headers = {"x-owner": "owner", "content-type": "application/octet-stream"}
    uploaded = client.post("/api/pipeline/images", content=_file("TIFF"), headers=headers)
    assert uploaded.status_code == 200, uploaded.text
    image = uploaded.json()
    assert image["thumbnail"].startswith("data:image/jpeg;base64,")
    options = {"stage1_model": "openai:fixture-vision", "catalog_mode": "auto", "wild": True,
               "sketch": "on", "save_artifacts": False}
    body = {"kind": "image", "text": "test data: 海辺で撮った写真。", "image_id": image["image_id"],
            "canvas_format_id": "image", "options": options}
    refused = client.post("/api/pipeline/variations", json=body, headers={"x-owner": "other"})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "image_missing"
    started = client.post("/api/pipeline/variations", json=body, headers={"x-owner": "owner"})
    assert started.status_code == 200, started.text
    run, view = _wait(service, started.json()["execution_id"])
    assert view["phase"]["tag"] == "score_ready", view
    assert [tag for tag, _ in sent] == ["select_image_catalog", "write_image_ddl", "review_image_ddl"]
    assert [len(refs) for _, refs in sent] == [1, 1, 2]
    assert admission == [("openai", "fixture-vision", "vision")]
    assert view["authority"]["authority"] == "ddl_authoritative"
    assert view["description"] == ""
    assert run.config["compiler"]["host"]["canvas_format_id"] == image["nearest_format_id"]
    assert run.config["compiler"]["host"]["canvas_fit"] == "contain"
    assert run.context["host_options"]["wild"] is False
    assert run.context["sketch_request"] == {"mode": "off"}
    assert run.image_data == {}
    assert view["image_ddl"]["drawing"]["media_type"] == "image/png"
    assert view["image_provenance"] == body["text"]
    done = service.command("owner", view["execution_id"], {"tag": "perform"})
    item = db.get_items("owner", [done["result"]["history_id"]])[0]
    assert item["input"] == item["source_text"] == ""
    assert item["image_provenance"] == body["text"]
    assert item["image_ddl"] == view["image_ddl"]
    assert item["description_locked"] is True
    persisted = service.store.read_execution("owner", view["execution_id"]).state_bytes.decode()
    assert "data:image/" not in persisted
    assert "base64" not in persisted
    assert "data:image/" not in json.dumps(run.transcript)
    assert effects.image_review_options(run.snapshot(), run.context)["options"]["render_seed"] == run.context["host_options"]["render_seed"]
    with pytest.raises(CandidateHostError, match="image_missing"):
        service.start("owner", "image", "", image_id=image["image_id"], options=options)


def test_worker_replacement_stops_before_sending_lost_image(image_host, monkeypatch):
    _, service, _, sent, _ = image_host
    monkeypatch.setattr(service, "_schedule", lambda *args: None)
    image = service.prepare_image("owner", _file())
    view = service.start("owner", "image", "private provenance", image_id=image["image_id"],
                         options={"stage1_model": "openai:fixture-vision"})
    run = service._runs.pop(("owner", view["execution_id"]))
    run.image_data.clear()
    restored = service.execution("owner", view["execution_id"])
    assert restored.view()["busy"] is False
    assert restored.view()["image_failure"]["code"] == "image_missing"
    assert sent == []


def test_review_render_failure_commits_written_ddl_without_logging_pixels(image_host, monkeypatch, caplog):
    _, service, _, sent, _ = image_host
    image = service.prepare_image("owner", _file())

    def unavailable(*args):
        raise RuntimeError("data:image/png;base64,private-bytes <svg>private</svg>")

    monkeypatch.setattr(service, "image_review_options", unavailable)
    view = service.start("owner", "image", "", image_id=image["image_id"],
                         options={"stage1_model": "openai:fixture-vision"})
    run, finished = _wait(service, view["execution_id"])
    assert finished["phase"]["tag"] == "score_ready"
    assert [tag for tag, _ in sent] == ["write_image_ddl"]
    assert "赤の塗りの円" in finished["document"]["source"]
    assert finished["image_ddl"].get("drawing") is None
    assert run.image_data == {}
    assert "private-bytes" not in caplog.text and "<svg>" not in caplog.text


def test_image_requires_vision_and_8192_tokens_for_write_review(image_host, monkeypatch):
    _, _, effects, _, _ = image_host
    with pytest.raises(CandidateHostError, match="image_model_not_vision"):
        effects.prepare("owner", "image", "", {"stage1_model": "openai:text-only"}, None)
    from inku_server import pipeline_product
    limits = []

    class Transport:
        def __init__(self, options, **kwargs):
            limits.append(options.max_tokens)
        def __call__(self, action):
            return {"tag": "provider_failed", "failure": "transport_unavailable", "elapsed_ms": "0"}

    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", Transport)
    context = {"host_options": {"stage1_model": "openai:fixture-vision"}}
    for tag in ("select_image_catalog", "write_image_ddl", "review_image_ddl"):
        effects.provider_for("owner", context, [])({"tag": tag, "identity": {"attempt": 1}})
    assert limits == [2048, 8192, 8192]
