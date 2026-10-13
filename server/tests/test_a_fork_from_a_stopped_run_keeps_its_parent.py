"""A description fork from a run stopped before its first save (5173, 2026-10-13).

The stopped run has no saved authority, so a fork that named it as the parent
was accepted, spent a Stage 1 call, and failed at its own first save ("The
authoring operation could not finish."). The fork takes the stopped run's own
parent instead: the saved work it came from, or none.
"""

from __future__ import annotations

import json
import runpy
import threading
import time
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from inku_server.persistence.schema import Base
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_api import PipelineService, pipeline_router, register_pipeline_errors
from inku_server.pipeline_candidate import PipelineBinding
from inku_server.pipeline_product import RunOptions
from inku_server.pipeline_settings import select_canvas

_fixture_config = runpy.run_path(
    str(Path(__file__).with_name("test_pipeline_candidate.py"))
)["_fixture_config"]

OWNER = {"X-Owner": "author-1"}
DESCRIPTION = "One quiet black circle"


def _actor(x_owner: str = Header(...)) -> dict[str, str]:
    return {"id": x_owner}


class _Provider:
    """Answers Stage 1 at once, or holds one call until the test has stopped its run."""

    def __init__(self) -> None:
        self.hold = False
        self.called = threading.Event()
        self.release = threading.Event()

    def __call__(self, action: dict) -> dict:
        assert action["tag"] == "generate_normalized_ddl", action["tag"]
        if self.hold:
            self.hold = False
            self.called.set()
            self.release.wait(5)
        return {
            "tag": "normalized_ddl_generated",
            "identity": action["identity"],
            "response": json.dumps({"normalized_ddl": "place one black circle at center."}),
            "elapsed_ms": "1",
        }


def _client(tmp_path, provider: _Provider):
    binding = PipelineBinding()
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline-api.db'}")
    Base.metadata.create_all(engine)
    store = VariationAuthorityStore(engine, now_ms=lambda: 1_777_777_777)

    def prepare(_owner, _kind, _text, options, source):
        selected = {
            "canvas_aspect": "square", "wild": False,
            **(source or {}).get("host_options", {}),
            **RunOptions.model_validate(options).model_dump(exclude_unset=True),
        }
        config = deepcopy((source or {}).get("saved_config") or _fixture_config())
        config = select_canvas(config, binding.canvas_registry, selected["canvas_aspect"])
        return config, {"host_options": selected}

    service = PipelineService(
        binding,
        store,
        config_for=lambda _owner, source: (source or {}).get("saved_config") or _fixture_config(),
        provider_for=lambda _owner: provider,
        render_for=None,
        max_workers=1,
        max_effect_steps=16,
        max_retained_runs=4,
        prepare_for=prepare,
    )

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            service.close()

    application = FastAPI(lifespan=lifespan)
    register_pipeline_errors(application)
    application.include_router(pipeline_router(service, _actor))
    return TestClient(application), store


def _settled(client: TestClient, variation_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/pipeline/variations/{variation_id}", headers=OWNER)
        assert response.status_code == 200, response.text
        view = response.json()
        if not view["busy"]:
            return view
        time.sleep(0.01)
    raise AssertionError(f"variation {variation_id} did not settle")


def _stopped_fork(client: TestClient, provider: _Provider, variation_id: str, revision: str) -> dict:
    """Fork from a description and stop the fork while its Stage 1 is out."""
    provider.hold = True
    forked = client.post(
        f"/api/pipeline/variations/{variation_id}/fork-description", headers=OWNER,
        json={"expected_revision": revision, "description": DESCRIPTION},
    )
    assert forked.status_code == 200, forked.text
    assert provider.called.wait(5)
    stopped = client.post(
        f"/api/pipeline/executions/{forked.json()['execution_id']}/commands", headers=OWNER,
        json={"tag": "cancel"},
    )
    assert stopped.status_code == 200, stopped.text
    provider.release.set()
    view = _settled(client, forked.json()["variation_id"])
    assert view["phase"]["tag"] == "cancelled"
    assert view["authority"]["revision"] == "0"
    return view


def _context(store: VariationAuthorityStore, view: dict) -> dict:
    return json.loads(store.read_execution("author-1", view["execution_id"]).state_bytes)["context"]


def test_a_fork_from_a_run_stopped_before_its_first_save_takes_the_saved_parent(tmp_path) -> None:
    provider = _Provider()
    client, store = _client(tmp_path, provider)
    with client:
        first = client.post(
            "/api/pipeline/variations", headers=OWNER,
            json={"kind": "description", "text": DESCRIPTION},
        ).json()
        saved = _settled(client, first["variation_id"])
        assert saved["phase"]["tag"] == "score_ready"
        assert saved["authority"]["revision"] == "1"

        stopped = _stopped_fork(client, provider, saved["variation_id"], "1")
        assert store.read("author-1", stopped["variation_id"]) is None

        again = client.post(
            f"/api/pipeline/variations/{stopped['variation_id']}/fork-description", headers=OWNER,
            json={"expected_revision": "0", "description": DESCRIPTION},
        )
        assert again.status_code == 200, again.text
        drawn = _settled(client, again.json()["variation_id"])
        assert drawn["phase"]["tag"] == "score_ready"
        assert drawn["authority"]["revision"] == "1"
        assert store.read("author-1", drawn["variation_id"]) is not None
        context = _context(store, drawn)
        assert context["parent"] == {"kind": "variation", "id": saved["variation_id"]}
        assert context["parent_variation_id"] == saved["variation_id"]
        assert context["derivation_kind"] == "description_fork"


def test_a_fork_from_a_stopped_first_run_starts_without_a_parent(tmp_path) -> None:
    provider = _Provider()
    client, store = _client(tmp_path, provider)
    with client:
        provider.hold = True
        first = client.post(
            "/api/pipeline/variations", headers=OWNER,
            json={"kind": "description", "text": DESCRIPTION},
        ).json()
        assert provider.called.wait(5)
        stopped = client.post(
            f"/api/pipeline/executions/{first['execution_id']}/commands", headers=OWNER,
            json={"tag": "cancel"},
        )
        assert stopped.status_code == 200, stopped.text
        provider.release.set()
        view = _settled(client, first["variation_id"])
        assert view["phase"]["tag"] == "cancelled"
        assert store.read("author-1", first["variation_id"]) is None

        again = client.post(
            f"/api/pipeline/variations/{first['variation_id']}/fork-description", headers=OWNER,
            json={"expected_revision": "0", "description": DESCRIPTION},
        )
        assert again.status_code == 200, again.text
        drawn = _settled(client, again.json()["variation_id"])
        assert drawn["phase"]["tag"] == "score_ready"
        context = _context(store, drawn)
        assert context["parent"] is None
        assert "parent_variation_id" not in context
        assert context["derivation_kind"] == "new"
