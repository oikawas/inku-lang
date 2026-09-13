"""One non-render compatibility flow for the normal compose URL."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from inku_server import pipeline_compat
from inku_server.api_core.routers.render import ComposeResponse


def test_compose_projects_opaque_score_and_never_approves_a_hole(monkeypatch) -> None:
    commands: list[dict] = []

    class Service:
        def __init__(self):
            self.view: dict = {}

        def start(self, owner, kind, text, **kwargs):
            assert owner == "author-1"
            assert kind == "direct_ddl"
            assert kwargs["options"]["save_history"] is False
            assert kwargs["options"]["count_generation"] is False
            patch = "many circle" in text
            self.view = {
                "execution_id": "execution-1",
                "variation_id": "variation-1",
                "authority": {"revision": "1"},
                "document": {"source": text, "language": "en"},
                "delivery": None if patch else {"score": {"schema": "inku.score.v0.10"}},
                "phase": {
                    "tag": "awaiting_patch_approval" if patch else "score_ready",
                    "proposal_digest": "proposal-1" if patch else None,
                },
                "busy": False,
                "result": None,
            }
            return self.view

        def get(self, owner, variation_id):
            return self.view

        def command(self, owner, execution_id, command):
            commands.append(command)
            assert command == {"tag": "perform"}
            self.view["result"] = {
                "ddl": self.view["document"]["source"],
                "score": {
                    "schema": "inku.score.v0.10",
                    "future_field": {"kept": True},
                },
                "svg": "<svg/>",
            }
            return self.view

    service = Service()
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)

    result = pipeline_compat.compose(
        "author-1",
        {"ddl": "one circle", "description": "circle", "model": "stage2"},
    )
    projected = ComposeResponse.model_validate(result).model_dump()
    assert projected["score"]["future_field"] == {"kept": True}
    assert projected["pipeline_variation_id"] == "variation-1"
    assert commands == [{"tag": "perform"}]

    with pytest.raises(HTTPException) as raised:
        pipeline_compat.compose(
            "author-1",
            {"ddl": "many circle", "description": "circles"},
        )
    assert raised.value.status_code == 409
    assert raised.value.detail["current_view"]["phase"]["tag"] == (
        "awaiting_patch_approval"
    )
    assert raised.value.detail["pipeline_execution_id"] == "execution-1"
    assert commands == [{"tag": "perform"}]
