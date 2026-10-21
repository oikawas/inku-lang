"""The laws records a work keeps (2026-10-20), without native drawing or model calls.

The laws stage leaves the layers record and the basis (the composed document and answer the laws were applied by)
in the snapshot; the Server keeps them in the work's fork context and gives them back to a direct-DDL fork of the
work. "Change the layout" adds the layers record to its request, whose `laws_placed` answer reads.
"""

from __future__ import annotations

import hashlib
import json
import runpy
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select

from inku_server import pipeline_compat
from inku_server.persistence.schema import Base, HistoryRow, PipelineHistoryLinkRow
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_api import PipelineService

_action = runpy.run_path(str(Path(__file__).with_name("test_persistence_variation_authority.py")))["_action"]

LAWS = {"schema": "inku.laws-layers.v1", "layers": [{
    "sentences": ["画面の横0.618034、縦0.618034の位置に、灰の細い細筆の程よい空の縦長の小さな楕円を1個置く。"],
    "kind": "laws", "laws": ["B1"],
}]}
SOURCE = "背景を白で埋める。\n画面の横0.618034、縦0.618034の位置に、灰の細い細筆の程よい空の縦長の小さな楕円を1個置く。\n"
BASIS = {"schema": "inku.laws-basis.v1",
         "composed": "背景を白で埋める。\n画面の中ほどに、灰の細い細筆の程よい空の縦長の小さな楕円を1個置く。\n",
         "committed_digest": hashlib.sha256(SOURCE.encode()).hexdigest(), "main_layer": None, "main_law": "B1",
         "laws": {"B1": {"targets": [{"layer": 0, "at": "point_lr"}]}}, "reason": "The grey ellipse leads."}
CONFIG = {"saved_setting": "this performance"}
DIAGNOSTICS = {"upstream_diagnostics": [], "downstream_diagnostics": [],
               "resource_omissions": [], "relation_omissions": [],
               "render_diagnostics": None, "resource_execution": None}


@pytest.fixture(params=[None, 0], ids=["no-main-layer", "saved-main-layer"])
def saved_work(tmp_path, request):
    basis = {**BASIS, "main_layer": request.param}
    engine = create_engine(f"sqlite:///{tmp_path / 'laws.db'}")
    Base.metadata.create_all(engine)
    store = VariationAuthorityStore(engine)
    with engine.begin() as connection:
        connection.execute(HistoryRow.__table__.insert().values(
            id="work", user_id="owner", at=1, input="a grey ellipse", ddl=SOURCE,
            score='{}', svg="<svg/>", elapsed_ms=0,
        ))
    store.commit_effect("owner", _action(action_digit="8", source=SOURCE,
                        expected_revision="0", next_revision="1"), create_if_missing=True)
    snapshot = {"variation_id": "variation-1", "authority": {"revision": "1"},
                "document": {"source": SOURCE}, "config": CONFIG,
                "delivery": {"source_digest": hashlib.sha256(SOURCE.encode()).hexdigest()},
                "phase": {"tag": "score_ready"}, "laws_layers": deepcopy(LAWS), "laws_basis": deepcopy(basis)}
    store.link_history("owner", "work", "variation-1", "1", snapshot["delivery"]["source_digest"],
                       snapshot=snapshot, context={"host_options": {"render_seed": 7}, "macro_catalog": {}},
                       pipeline_diagnostics=DIAGNOSTICS)
    yield store, basis
    engine.dispose()


def test_the_fork_context_keeps_the_records_and_a_context_without_them_reads_none(saved_work):
    store, basis = saved_work
    linked = store.read_linked_history("owner", "work")
    assert (linked.laws_layers, linked.laws_basis) == (LAWS, basis)
    with store.engine.connect() as connection:
        row = connection.execute(select(PipelineHistoryLinkRow)).mappings().one()
        payload = json.loads(bytes(row["fork_context_bytes"]))
    assert (payload["laws_layers"], payload["laws_basis"]) == (LAWS, basis)
    del payload["laws_layers"], payload["laws_basis"]
    encoded = json.dumps(payload, ensure_ascii=False).encode()
    with store.engine.begin() as connection:
        connection.execute(PipelineHistoryLinkRow.__table__.update().values(
            fork_context_bytes=encoded, fork_context_digest=hashlib.sha256(encoded).hexdigest()))
    linked = store.read_linked_history("owner", "work")
    assert (linked.laws_layers, linked.laws_basis) == (None, None)
    assert linked.saved_config == CONFIG


def test_a_fork_and_change_the_layout_carry_the_records(saved_work, monkeypatch):
    store, basis = saved_work
    starts, requests = [], []

    def recompose(request_bytes):
        requests.append(json.loads(request_bytes))
        return json.dumps({"schema": "inku.composition-recompose.v1", "outcome": "unchanged",
                           "reason": "laws_placed"}).encode()

    binding = SimpleNamespace(canvas_registry={"registry": {"formats": []}}, recompose=recompose)
    service = PipelineService(binding, store,
                              config_for=lambda _owner, work: (work or {}).get("saved_config", CONFIG),
                              provider_for=lambda _owner: pytest.fail("no model call"), render_for=None,
                              max_workers=1, max_effect_steps=1, max_retained_runs=16,
                              prepare_for=lambda _owner, _kind, _source, _options, work: (
                                  {"compiler": {"composition_seed": None}, "saved": (work or {}).get("saved_config")},
                                  {"host_options": {"render_seed": 7}}))

    class Run:
        def __init__(self, config, context):
            self.config, self.context = config, context

        def start_new(self, authoring):
            starts.append(deepcopy(authoring))
            self.shown = {"execution_id": str(len(starts)), "variation_id": "variation-2",
                          "authority": {"revision": "1"}, "document": {"source": authoring.get("source", "")},
                          "busy": False, "phase": {"tag": "score_ready"}, "result": {"svg": "<svg/>"}}

        def view(self):
            return self.shown

        def snapshot(self):
            return {"config": self.config}

    monkeypatch.setattr(service, "_host", lambda _owner, config, context: Run(config, context))
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)
    monkeypatch.setattr(pipeline_compat, "_settled", lambda _owner, view, **_: view)
    composed = pipeline_compat.compose("owner", {"work_id": "work", "ddl": SOURCE, "recompose_mode": "principled"})
    assert requests[-1]["laws_layers"] == LAWS
    assert requests[-1]["source"] == SOURCE
    assert "laws_basis" not in requests[-1]
    assert composed["recomposition"]["reason"] == "laws_placed"
    # The run that draws the answer keeps the records for the next fork.
    assert starts[-1] == {"tag": "direct_ddl", "source": SOURCE, "laws_layers": LAWS, "laws_basis": basis}
    service.start("owner", "direct_ddl", SOURCE)
    assert starts[-1] == {"tag": "direct_ddl", "source": SOURCE}
    service.close()
