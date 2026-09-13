"""One managed HTTP flow through the real binding and synthetic persistence."""

from __future__ import annotations

import json
import os
import runpy
import time
from pathlib import Path

from fastapi import Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from inku_server.persistence.schema import Base, HistoryRow
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_api import PipelineService, create_acceptance_app
from inku_server.pipeline_candidate import PipelineBinding


_fixture_config = runpy.run_path(
    str(Path(__file__).with_name("test_pipeline_candidate.py"))
)["_fixture_config"]


def _actor(x_owner: str = Header(...)) -> dict[str, str]:
    return {"id": x_owner}


def _wait_for(
    client: TestClient,
    path: str,
    headers: dict[str, str],
    *,
    phase: str,
) -> dict:
    deadline = time.monotonic() + 5
    last: dict | None = None
    while time.monotonic() < deadline:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        last = response.json()
        if not last["busy"] and last["phase"]["tag"] == phase:
            return last
        time.sleep(0.01)
    raise AssertionError(f"pipeline did not reach {phase}: {last}")


def test_managed_api_persists_approved_patch_reload_and_legacy_fork(
    tmp_path,
) -> None:
    binding = PipelineBinding(Path(os.environ["INKU_PIPELINE_PYTHON_BUNDLE"]))
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline-api.db'}")
    Base.metadata.create_all(engine)
    store = VariationAuthorityStore(engine, now_ms=lambda: 1_777_777_777)
    legacy_values = {
        "id": "legacy-1",
        "user_id": "author-1",
        "at": 1,
        "input": "Old description",
        "ddl": "place one black circle at center.",
        "expanded_ddl": "place one black circle at center.",
        "score": '{"instructions":[{"primitive":"circle"}]}',
        "svg": "<svg>old</svg>",
        "elapsed_ms": 0,
    }
    with engine.begin() as connection:
        connection.execute(HistoryRow.__table__.insert().values(**legacy_values))

    provider_calls: list[dict] = []

    def provider(action: dict) -> dict:
        provider_calls.append(action)
        if action["tag"] == "generate_normalized_ddl":
            response = {"normalized_ddl": "place one black circle at center."}
            return {
                "tag": "normalized_ddl_generated",
                "identity": action["identity"],
                "response": json.dumps(response, separators=(",", ":")),
                "elapsed_ms": "1",
            }
        assert action["tag"] == "complete_visible_ddl_holes"
        message = json.loads(action["payload"]["prompt"]["message"])
        hole = message["selected_holes"][0]
        patch = {
            "schema_id": "inku.visible-ddl-patch.v1",
            "base_source_digest": message["base_source_digest"],
            "base_compiler_lock_digest": message[
                "base_compiler_lock_digest"
            ],
            "edits": [
                {
                    "hole_id": hole["hole_id"],
                    "allowed_span": hole["allowed_span"],
                    "expected_range_digest": hole[
                        "expected_range_digest"
                    ],
                    "replacement": "8",
                }
            ],
        }
        return {
            "tag": "visible_ddl_hole_patch_generated",
            "identity": action["identity"],
            "response": json.dumps(patch, separators=(",", ":")),
            "elapsed_ms": "1",
        }

    def service() -> PipelineService:
        return PipelineService(
            binding,
            store,
            config_for=lambda _owner, source: (
                (source or {}).get("saved_config") or _fixture_config()
            ),
            provider_for=lambda _owner: provider,
            render_for=None,
            max_workers=1,
            max_effect_steps=16,
            max_retained_runs=4,
        )

    def app(candidate_service: PipelineService):
        return create_acceptance_app(
            candidate_service,
            actor_dependency=_actor,
            max_body_bytes=100_000,
            max_requests=4,
        )

    owner = {"X-Owner": "author-1"}
    another_owner = {"X-Owner": "author-2"}
    with TestClient(app(service())) as client:
        created_response = client.post(
            "/api/pipeline/variations",
            headers=owner,
            json={"kind": "description", "text": "One quiet black circle"},
        )
        assert created_response.status_code == 200, created_response.text
        created = created_response.json()
        variation_id = created["variation_id"]
        execution_id = created["execution_id"]
        ready = _wait_for(
            client,
            f"/api/pipeline/variations/{variation_id}",
            owner,
            phase="score_ready",
        )
        assert ready["authority"]["revision"] == "1"

        edit_response = client.post(
            f"/api/pipeline/executions/{execution_id}/commands",
            headers=owner,
            json={
                "tag": "commit_user_ddl",
                "expected_revision": "1",
                "source": "place one red circle at center. many square.",
            },
        )
        assert edit_response.status_code == 200, edit_response.text
        proposal = _wait_for(
            client,
            f"/api/pipeline/variations/{variation_id}",
            owner,
            phase="awaiting_patch_approval",
        )
        assert proposal["authority"]["revision"] == "2"
        assert proposal["delivery"] is None
        assert [call["tag"] for call in provider_calls] == [
            "generate_normalized_ddl",
            "complete_visible_ddl_holes",
        ]

        approval_response = client.post(
            f"/api/pipeline/executions/{execution_id}/commands",
            headers=owner,
            json={
                "tag": "approve_patch",
                "expected_revision": "2",
                "proposal_digest": proposal["phase"]["proposal_digest"],
            },
        )
        assert approval_response.status_code == 200, approval_response.text
        approved = _wait_for(
            client,
            f"/api/pipeline/variations/{variation_id}",
            owner,
            phase="score_ready",
        )
        assert approved["authority"]["revision"] == "3"
        assert approved["document"]["source"] == (
            "place one red circle at center. 8 square."
        )

        stale_response = client.post(
            f"/api/pipeline/executions/{execution_id}/commands",
            headers=owner,
            json={
                "tag": "commit_user_ddl",
                "expected_revision": "2",
                "source": "place one blue circle at center.",
            },
        )
        assert stale_response.status_code == 409
        assert stale_response.json() == {"detail": "authority_conflict"}
        assert store.read("author-1", variation_id)["authority"]["revision"] == "3"
        assert (
            client.get(
                f"/api/pipeline/variations/{variation_id}",
                headers=another_owner,
            ).status_code
            == 404
        )

    with TestClient(app(service())) as reloaded_client:
        reloaded = reloaded_client.get(
            f"/api/pipeline/variations/{variation_id}", headers=owner
        )
        assert reloaded.status_code == 200, reloaded.text
        assert reloaded.json()["authority"]["revision"] == "3"
        assert reloaded.json()["document"]["source"] == approved["document"][
            "source"
        ]

        legacy = reloaded_client.get(
            "/api/pipeline/legacy/legacy-1", headers=owner
        )
        assert legacy.status_code == 200, legacy.text
        assert legacy.json() == {
            "history_id": "legacy-1",
            "description": "Old description",
            "source": "place one black circle at center.",
            "svg": "<svg>old</svg>",
        }
        assert (
            reloaded_client.get(
                "/api/pipeline/legacy/legacy-1", headers=another_owner
            ).status_code
            == 404
        )

        fork_response = reloaded_client.post(
            "/api/pipeline/legacy/legacy-1/fork",
            headers=owner,
            json={
                "kind": "direct_ddl",
                "text": "place one red circle at center.",
            },
        )
        assert fork_response.status_code == 200, fork_response.text
        fork = fork_response.json()
        forked = _wait_for(
            reloaded_client,
            f"/api/pipeline/variations/{fork['variation_id']}",
            owner,
            phase="score_ready",
        )
        assert forked["authority"] == {
            "protocol_version": "inku.variation-authority.v1",
            "revision": "1",
            "origin": "user_authored_ddl",
            "authority": "ddl_authoritative",
        }
        saved_fork = store.read("author-1", fork["variation_id"])
        assert saved_fork["context"] == {
            "description": "Old description",
            "derivation_kind": "legacy_ddl_fork",
            "parent_legacy_history_id": "legacy-1",
            "parent_variation_id": None,
        }

    with engine.connect() as connection:
        unchanged = connection.execute(
            select(
                HistoryRow.input,
                HistoryRow.ddl,
                HistoryRow.score,
                HistoryRow.svg,
            ).where(HistoryRow.id == "legacy-1")
        ).one()
    assert unchanged == (
        legacy_values["input"],
        legacy_values["ddl"],
        legacy_values["score"],
        legacy_values["svg"],
    )
    engine.dispose()
