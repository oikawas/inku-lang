"""The label and the comment reach no layer, and the work keeps them anyway.

The unit rule lives in test_description_labels.py. These gates assert on what
the shared-pipeline host actually hands the core and what it keeps for the work:
the execution is replaced by a recorder, and the service wiring is left alone.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from inku_server import pipeline_api
from inku_server.pipeline_api import PipelineService

RAW = "01. ひさかたの光のどけき春の日に [疎  紀友則 / 古今和歌集（春下）]"
CUT = "ひさかたの光のどけき春の日に"


class _Recorder:
    runs: list["_Recorder"] = []

    def __init__(self, binding, store, *, owner_id, config, provider, allow_render, context, save_snapshot):
        self.context = context
        self.config = config
        self.authoring: dict | None = None
        self.commands: list[tuple[dict, dict | None]] = []
        _Recorder.runs.append(self)

    def start_new(self, authoring: dict) -> None:
        self.authoring = authoring

    def command(self, payload: dict, *, context_updates: dict | None = None) -> None:
        self.commands.append((payload, context_updates))

    def view(self) -> dict:
        return {"execution_id": "execution-1", "variation_id": "variation-1", "busy": False}


@pytest.fixture
def service(monkeypatch):
    _Recorder.runs = []
    monkeypatch.setattr(pipeline_api, "CandidateExecution", _Recorder)
    prepared: list[str] = []

    def prepare(owner, kind, text, options, work):
        prepared.append(text)
        return {"compiler": {}}, {}

    built = PipelineService(
        binding=object(), store=object(), config_for=lambda owner, work: {},
        provider_for=lambda owner: None, render_for=None,
        max_workers=1, max_effect_steps=1, max_retained_runs=1, prepare_for=prepare,
    )
    built.prepared = prepared
    yield built
    built.close()


def test_the_core_reads_the_description_without_its_labels(service) -> None:
    service.start("author-1", "description", RAW)
    run = _Recorder.runs[-1]
    assert run.authoring["description"] == CUT
    # The language is resolved from the same text the core reads.
    assert service.prepared == [CUT]


def test_the_work_keeps_the_description_as_written(service) -> None:
    service.start("author-1", "description", RAW)
    run = _Recorder.runs[-1]
    assert run.context["description"] == RAW
    assert run.context["committed_description"] == RAW


def test_a_description_of_labels_only_is_refused_before_any_layer(service) -> None:
    with pytest.raises(HTTPException) as refused:
        service.start("author-1", "description", "01. [出典だけ]")
    assert refused.value.status_code == 400
    assert _Recorder.runs == []


def test_direct_ddl_is_not_cut(service) -> None:
    service.start("author-1", "direct_ddl", "[注記] 黒い円を中心に置く。")
    assert _Recorder.runs[-1].authoring == {"tag": "direct_ddl", "source": "[注記] 黒い円を中心に置く。"}


def test_regenerating_from_a_description_cuts_for_the_core_and_keeps_the_original(service) -> None:
    service.start("author-1", "description", "黒い円")
    run = _Recorder.runs[-1]
    service.command("author-1", "execution-1", {
        "tag": "generate_from_description", "expected_revision": "1", "description": RAW,
    })
    payload, context_updates = run.commands[-1]
    assert payload["description"] == CUT
    assert context_updates == {"description": RAW}


def test_the_execution_saves_the_written_description_while_the_core_reads_the_cut(monkeypatch) -> None:
    from inku_server.pipeline_candidate import CandidateExecution

    run = CandidateExecution(object(), object(), owner_id="author-1", config={}, provider=lambda action: {})
    run._snapshot = {"execution_id": "execution-1"}
    advanced: list[dict] = []
    monkeypatch.setattr(run, "_advance", lambda payload: advanced.append(payload) or {})
    run.command(
        {"tag": "generate_from_description", "expected_revision": "1", "description": CUT},
        context_updates={"description": RAW},
    )
    assert advanced[-1]["description"] == CUT
    assert run.context["description"] == RAW
