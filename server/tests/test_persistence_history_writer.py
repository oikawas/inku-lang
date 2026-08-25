"""Direct ownership and branch checks for the atomic persistence history writer."""

from __future__ import annotations

import ast
import inspect
import json
from hashlib import sha256
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from inku_server import db
from inku_server.persistence import history
from inku_server.persistence.schema import (
    CoerceTraceCatalogRow,
    HistoryRow,
    LineageEdgeRow,
    LineageNodeRow,
)


class FakeQuery:
    def __init__(self, session: FakeSession, model: object) -> None:
        self.session = session
        self.model = model

    def filter(self, *clauses: object) -> FakeQuery:
        self.session.filter_calls.append((self.model, clauses))
        return self

    def first(self) -> object | None:
        results = self.session.query_results.setdefault(self.model, [])
        return results.pop(0) if results else None


class FakeSession:
    def __init__(
        self,
        *,
        query_results: dict[object, list[object | None]] | None = None,
        get_results: dict[tuple[object, object], object | None] | None = None,
        flush_error: BaseException | None = None,
        commit_error: BaseException | None = None,
    ) -> None:
        self.query_results = {
            model: list(results) for model, results in (query_results or {}).items()
        }
        self.get_results = dict(get_results or {})
        self.flush_error = flush_error
        self.commit_error = commit_error
        self.entered = False
        self.exited = False
        self.added: list[object] = []
        self.query_calls: list[object] = []
        self.filter_calls: list[tuple[object, tuple[object, ...]]] = []
        self.get_calls: list[tuple[object, object]] = []
        self.flush_calls = 0
        self.rollback_calls = 0
        self.commit_calls = 0
        self.refresh_calls: list[object] = []

    def __enter__(self) -> FakeSession:
        self.entered = True
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self.exited = True
        return False

    def query(self, model: object) -> FakeQuery:
        self.query_calls.append(model)
        return FakeQuery(self, model)

    def get(self, model: object, key: object) -> object | None:
        self.get_calls.append((model, key))
        return self.get_results.get((model, key))

    def add(self, row: object) -> None:
        self.added.append(row)

    def flush(self) -> None:
        self.flush_calls += 1
        if self.flush_error is not None:
            raise self.flush_error

    def rollback(self) -> None:
        self.rollback_calls += 1

    def commit(self) -> None:
        self.commit_calls += 1
        if self.commit_error is not None:
            raise self.commit_error

    def refresh(self, row: object) -> None:
        self.refresh_calls.append(row)


def _item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": "history-1",
        "user_id": "user-1",
        "at": 1_777_777_777,
        "input": "input text",
    }
    item.update(overrides)
    return item


def _writer(
    session: FakeSession,
    *,
    calls: list[tuple[str, object]] | None = None,
    projection: Any = None,
) -> tuple[history.HistoryWriter, list[tuple[str, object]]]:
    active_calls = calls if calls is not None else []

    def actor_of(user_id: str) -> dict:
        actor = {"id": user_id}
        active_calls.append(("actor", user_id))
        return actor

    def owned_by(actor: dict, column: object) -> object:
        active_calls.append(("owned", (actor, column)))
        return "owned-clause"

    def readable_node(actor: dict) -> object:
        active_calls.append(("readable", actor))
        return "readable-clause"

    def row_to_dict(row: HistoryRow) -> dict:
        active_calls.append(("project", row))
        if projection is not None:
            return projection(row)
        return {"id": row.id}

    def render_hash_for_item(item: dict) -> str:
        active_calls.append(("render_hash", dict(item)))
        return "rh3:test"

    def description_hash(source_text: str) -> str:
        active_calls.append(("description_hash", source_text))
        return "dh1:test"

    def normalize_canvas_aspect_id(value: str) -> str:
        active_calls.append(("normalize", value))
        return f"normalized:{value}"

    def canvas_aspect_ratio_for_aspect(value: str) -> float:
        active_calls.append(("aspect_ratio", value))
        return 1.25

    def canonical_json(value: dict) -> str:
        active_calls.append(("canonical", value))
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    return (
        history.HistoryWriter(
            session_factory=lambda: session,
            actor_of_fn=actor_of,
            owned_by_fn=owned_by,
            readable_node_fn=readable_node,
            row_to_dict_fn=row_to_dict,
            render_hash_for_item_fn=render_hash_for_item,
            description_hash_fn=description_hash,
            normalize_canvas_aspect_id_fn=normalize_canvas_aspect_id,
            canvas_aspect_ratio_for_aspect_fn=canvas_aspect_ratio_for_aspect,
            canonical_json_fn=canonical_json,
        ),
        active_calls,
    )


def test_history_writer_owns_add_item_and_db_delegates() -> None:
    assert history.HistoryWriter.__dataclass_params__.frozen is True
    assert db.LINEAGE_DERIVATION_KINDS is history.LINEAGE_DERIVATION_KINDS
    assert inspect.signature(db.add_item) == inspect.Signature(
        [
            inspect.Parameter(
                "item",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation="dict",
            )
        ],
        return_annotation="dict",
    )

    tree = ast.parse(inspect.getsource(db.add_item))
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    assert len(function.body) == 1
    assert isinstance(function.body[0], ast.Return)
    facade_source = inspect.getsource(db.add_item)
    assert "_history.HistoryWriter(" in facade_source
    assert ").add_item(item)" in facade_source
    assert "HistoryRow(" not in facade_source
    assert "session.flush" not in facade_source


def test_db_facade_resolves_all_writer_dependencies_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    delegated_item = _item()
    expected_result = {"delegated": True}

    class RecordingWriter:
        def __init__(self, **dependencies: object) -> None:
            captured.update(dependencies)

        def add_item(self, item: dict) -> dict:
            captured["item"] = item
            return expected_result

    dependencies = {
        "session_factory": object(),
        "actor_of_fn": object(),
        "owned_by_fn": object(),
        "readable_node_fn": object(),
        "row_to_dict_fn": object(),
        "render_hash_for_item_fn": object(),
        "description_hash_fn": object(),
        "normalize_canvas_aspect_id_fn": object(),
        "canvas_aspect_ratio_for_aspect_fn": object(),
        "canonical_json_fn": object(),
    }
    db_names = {
        "session_factory": "SessionLocal",
        "actor_of_fn": "_actor_of",
        "owned_by_fn": "_owned_by",
        "readable_node_fn": "_readable_node",
        "row_to_dict_fn": "_row_to_dict",
        "render_hash_for_item_fn": "render_hash_for_item",
        "description_hash_fn": "description_hash",
        "normalize_canvas_aspect_id_fn": "normalize_canvas_aspect_id",
        "canvas_aspect_ratio_for_aspect_fn": "canvas_aspect_ratio_for_aspect",
        "canonical_json_fn": "_canonical_json",
    }
    monkeypatch.setattr(db._history, "HistoryWriter", RecordingWriter)
    for writer_name, db_name in db_names.items():
        monkeypatch.setattr(db, db_name, dependencies[writer_name])

    assert db.add_item(delegated_item) is expected_result
    assert captured.pop("item") is delegated_item
    assert captured == dependencies


def test_root_save_maps_every_history_field_and_creates_root_and_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(history.uuid, "uuid4", lambda: "root-node")
    snapshot = {"catalog": "青", "version": 1}
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    digest = sha256(snapshot_json.encode("utf-8")).hexdigest()
    session = FakeSession()
    writer, calls = _writer(session)
    item = _item(
        ddl="ddl",
        expanded_ddl="expanded",
        score={"objects": [1]},
        svg="<svg/>",
        output_path="output.svg",
        elapsed_ms=12,
        stage1_model="stage-1",
        stage2_model="stage-2",
        stage1_prompt_digest="prompt-1",
        stage1_prompt_base_digest="prompt-base",
        stage2_prompt_digest="prompt-2",
        tokens_in=3,
        tokens_out=5,
        catalog_id="catalog-id",
        catalog_mode="auto",
        ddl_version=3,
        ddl_engine_version=20,
        render_build_number=986,
        render_color_profile={"profile": "warm"},
        render_engine_id="default",
        render_engine_version="41",
        render_color_catalog_id="color-id",
        render_color_catalog_name="Color",
        render_color_catalog_sub="sub",
        render_color_map={"black": "#111"},
        render_canvas_aspect="legacy-aspect",
        render_canvas_aspect_id="portrait-alias",
        render_canvas_aspect_ratio=1.75,
        instruction_lang_requested="ja",
        instruction_lang_resolved="en",
        ui_lang="ja",
        render_seed=19,
        render_wild=False,
        composition_seed=23,
        tenkei="tenkei",
        focus="focus",
        variation_amplitude="high",
        variation_seed=29,
        interpret_fallback="fallback",
        compose_fallback="none",
        interpretation_seed=31,
        seed_text="seed text",
        sketch_text="sketch text",
        sketch_grain="fine",
        sketch_state="off",
        render_limits={"objects": 8},
        note="note",
        score_pre_coerce={"before": True},
        coerce_trace_version=1,
        coerce_catalog_digest=digest,
        coerce_catalog_snapshot=snapshot,
        coerce_trace=[{"event": "drop"}],
        display_label="label",
        batch_line_number=4,
        batch_run_id="batch-1",
    )
    before = dict(item)

    result = writer.add_item(item)

    assert item == before | {"render_canvas_aspect_id": "normalized:portrait-alias"}
    row = next(row for row in session.added if isinstance(row, HistoryRow))
    expected_row = {
        "id": "history-1",
        "user_id": "user-1",
        "at": 1_777_777_777,
        "input": "input text",
        "ddl": "ddl",
        "expanded_ddl": "expanded",
        "score": json.dumps({"objects": [1]}),
        "svg": "<svg/>",
        "output_path": "output.svg",
        "elapsed_ms": 12,
        "stage1_model": "stage-1",
        "stage2_model": "stage-2",
        "stage1_prompt_digest": "prompt-1",
        "stage1_prompt_base_digest": "prompt-base",
        "stage2_prompt_digest": "prompt-2",
        "tokens_in": 3,
        "tokens_out": 5,
        "catalog_id": "catalog-id",
        "catalog_mode": "auto",
        "ddl_version": 3,
        "ddl_engine_version": 20,
        "render_build_number": 986,
        "render_color_profile": json.dumps({"profile": "warm"}, ensure_ascii=False),
        "render_engine_id": "default",
        "render_engine_version": "41",
        "render_color_catalog_id": "color-id",
        "render_color_catalog_name": "Color",
        "render_color_catalog_sub": "sub",
        "render_color_catalog": None,
        "render_color_map": json.dumps({"black": "#111"}, ensure_ascii=False),
        "render_canvas_aspect": "legacy-aspect",
        "render_canvas_aspect_id": "normalized:portrait-alias",
        "render_canvas_aspect_ratio": 1.75,
        "instruction_lang_requested": "ja",
        "instruction_lang_resolved": "en",
        "ui_lang": "ja",
        "render_seed": "19",
        "render_wild": "0",
        "composition_seed": "23",
        "tenkei": "tenkei",
        "focus": "focus",
        "variation_amplitude": "high",
        "variation_seed": "29",
        "interpret_fallback": "fallback",
        "compose_fallback": "none",
        "interpretation_seed": "31",
        "seed_text": "seed text",
        "sketch_text": "sketch text",
        "sketch_grain": "fine",
        "sketch_state": "off",
        "render_limits": json.dumps({"objects": 8}, ensure_ascii=False, sort_keys=True),
        "render_hash": "rh3:test",
        "trashed": 0,
        "starred": 0,
        "for_revision": 0,
        "for_share": 0,
        "share_group_id": None,
        "note": "note",
        "source_text": "input text",
        "display_label": "label",
        "batch_line_number": 4,
        "batch_run_id": "batch-1",
        "description_hash": "dh1:test",
        "history_visibility": "normal",
        "lineage_node_id": "root-node",
        "idempotency_key": None,
        "score_pre_coerce": json.dumps({"before": True}, ensure_ascii=False),
        "coerce_trace_version": 1,
        "coerce_catalog_digest": digest,
        "coerce_trace": json.dumps([{"event": "drop"}], ensure_ascii=False),
    }
    assert {
        column.name: getattr(row, column.name) for column in HistoryRow.__table__.columns
    } == expected_row

    node = next(row for row in session.added if isinstance(row, LineageNodeRow))
    assert (
        node.id,
        node.user_id,
        node.history_id,
        node.state,
        node.description_hash,
        node.render_hash,
        node.at,
        node.root_node_id,
    ) == (
        "root-node",
        "user-1",
        "history-1",
        "active",
        "dh1:test",
        "rh3:test",
        1_777_777_777,
        "root-node",
    )
    catalog = next(row for row in session.added if isinstance(row, CoerceTraceCatalogRow))
    assert (catalog.digest, catalog.trace_version, catalog.snapshot_json) == (
        digest,
        1,
        snapshot_json,
    )
    assert session.get_calls == [(CoerceTraceCatalogRow, digest)]
    assert session.flush_calls == 1
    assert session.commit_calls == 1
    assert session.refresh_calls == [row]
    assert result == {"id": "history-1"}
    assert calls[:4] == [
        ("normalize", "portrait-alias"),
        ("aspect_ratio", "normalized:portrait-alias"),
        ("render_hash", item),
        ("description_hash", "input text"),
    ]
    assert calls[-1] == ("project", row)


def test_child_save_reads_parent_inherits_root_and_writes_canonical_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = iter(("child-node", "edge-id"))
    monkeypatch.setattr(history.uuid, "uuid4", lambda: next(ids))
    parent = SimpleNamespace(id="parent-node", root_node_id="root-node")
    session = FakeSession(query_results={LineageNodeRow: [parent]})
    writer, calls = _writer(session)
    metadata = {"z": 1, "a": "青"}

    result = writer.add_item(
        _item(
            id="child-history",
            lineage_parent_node_id="parent-node",
            derivation_kind="ddl_edit",
            derivation_metadata=metadata,
        )
    )

    node = next(row for row in session.added if isinstance(row, LineageNodeRow))
    edge = next(row for row in session.added if isinstance(row, LineageEdgeRow))
    assert node.root_node_id == "root-node"
    assert (
        edge.id,
        edge.user_id,
        edge.parent_node_id,
        edge.child_node_id,
        edge.derivation_kind,
        edge.metadata_json,
        edge.at,
    ) == (
        "edge-id",
        "user-1",
        "parent-node",
        "child-node",
        "ddl_edit",
        '{"a":"青","z":1}',
        1_777_777_777,
    )
    assert any(name == "readable" and value == {"id": "user-1"} for name, value in calls)
    assert ("canonical", metadata) in calls
    assert result == {
        "id": "child-history",
        "lineage_parent_node_id": "parent-node",
        "derivation_kind": "ddl_edit",
        "derivation_metadata": metadata,
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "history_visibility": "hidden",
                "lineage_parent_node_id": "parent",
                "derivation_kind": "invalid",
                "derivation_metadata": ["invalid"],
            },
            "invalid history visibility",
        ),
        (
            {
                "lineage_parent_node_id": "parent",
                "derivation_kind": "invalid",
                "derivation_metadata": ["invalid"],
            },
            "invalid lineage derivation kind",
        ),
        (
            {"derivation_kind": "ddl_edit", "derivation_metadata": ["invalid"]},
            "lineage parent is required for a derivation",
        ),
        (
            {"derivation_metadata": ["invalid"]},
            "lineage derivation metadata must be an object",
        ),
    ],
)
def test_validation_order_and_text_are_exact(
    overrides: dict[str, object],
    message: str,
) -> None:
    session = FakeSession()
    writer, _ = _writer(session)

    with pytest.raises(ValueError, match=f"^{message}$"):
        writer.add_item(_item(**overrides))

    assert session.entered is False


def test_parent_not_found_is_exact_and_uses_readability() -> None:
    session = FakeSession(query_results={LineageNodeRow: [None]})
    writer, calls = _writer(session)

    with pytest.raises(ValueError, match="^lineage parent not found$"):
        writer.add_item(
            _item(lineage_parent_node_id="missing", derivation_kind="ddl_edit")
        )

    assert ("readable", {"id": "user-1"}) in calls
    assert session.added == []
    assert session.flush_calls == 0
    assert session.commit_calls == 0


def test_early_idempotency_replay_returns_before_writes() -> None:
    existing = SimpleNamespace(id="existing-history")
    session = FakeSession(query_results={HistoryRow: [existing]})
    writer, calls = _writer(session)

    result = writer.add_item(_item(idempotency_key="request-1"))

    assert result == {"id": "existing-history", "_idempotent_replay": True}
    assert session.added == []
    assert session.flush_calls == 0
    assert session.commit_calls == 0
    assert [name for name, _ in calls].count("owned") == 1


@pytest.mark.parametrize(
    ("idempotency_key", "replay_row", "expect_replay"),
    [
        (None, None, False),
        ("request-1", None, False),
        ("request-1", SimpleNamespace(id="winner"), True),
    ],
)
def test_flush_race_rolls_back_and_only_replays_an_existing_idempotent_row(
    idempotency_key: str | None,
    replay_row: object | None,
    expect_replay: bool,
) -> None:
    race = IntegrityError("insert history", {}, RuntimeError("duplicate"))
    query_results = (
        {HistoryRow: [None, replay_row]} if idempotency_key is not None else None
    )
    session = FakeSession(query_results=query_results, flush_error=race)
    writer, _ = _writer(session)
    item = _item()
    if idempotency_key is not None:
        item["idempotency_key"] = idempotency_key

    if expect_replay:
        assert writer.add_item(item) == {"id": "winner", "_idempotent_replay": True}
    else:
        with pytest.raises(IntegrityError) as raised:
            writer.add_item(item)
        assert raised.value is race

    assert session.flush_calls == 1
    assert session.rollback_calls == 1
    assert session.commit_calls == 0


@pytest.mark.parametrize(
    ("catalog", "message"),
    [
        (None, "coerce catalog digest does not match its snapshot bytes"),
        (
            "immutable",
            "coerce catalog digest does not match its immutable snapshot",
        ),
    ],
)
def test_catalog_digest_and_immutable_snapshot_mismatches_are_exact(
    catalog: str | None,
    message: str,
) -> None:
    snapshot = {"catalog": "青"}
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    valid_digest = sha256(snapshot_json.encode("utf-8")).hexdigest()
    digest = "not-the-byte-digest" if catalog is None else valid_digest
    get_results = {}
    if catalog == "immutable":
        get_results[(CoerceTraceCatalogRow, digest)] = SimpleNamespace(
            trace_version=2,
            snapshot_json=snapshot_json,
        )
    session = FakeSession(get_results=get_results)
    writer, _ = _writer(session)

    with pytest.raises(ValueError, match=f"^{message}$"):
        writer.add_item(
            _item(
                coerce_catalog_digest=digest,
                coerce_catalog_snapshot=snapshot,
                coerce_trace_version=1,
            )
        )

    assert session.added == []
    assert session.flush_calls == 0
    assert session.commit_calls == 0


def test_commit_and_projection_exception_boundaries_are_unchanged() -> None:
    commit_error = RuntimeError("commit failed")
    commit_session = FakeSession(commit_error=commit_error)
    commit_writer, commit_calls = _writer(commit_session)

    with pytest.raises(RuntimeError, match="^commit failed$"):
        commit_writer.add_item(_item())

    assert commit_session.flush_calls == 1
    assert commit_session.commit_calls == 1
    assert commit_session.refresh_calls == []
    assert not any(name == "project" for name, _ in commit_calls)

    projection_error = RuntimeError("projection failed")
    projection_session = FakeSession()

    def fail_projection(row: HistoryRow) -> dict:
        raise projection_error

    projection_writer, _ = _writer(projection_session, projection=fail_projection)
    with pytest.raises(RuntimeError) as raised:
        projection_writer.add_item(_item())

    assert raised.value is projection_error
    assert projection_session.flush_calls == 1
    assert projection_session.commit_calls == 1
    assert len(projection_session.refresh_calls) == 1
