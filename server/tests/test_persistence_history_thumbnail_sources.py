import inspect
from dataclasses import FrozenInstanceError

import pytest

from inku_server import db
from inku_server.persistence import history


class _Result:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[object, object]]:
        return self.rows


class _Session:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self.rows = rows
        self.statements = []
        self.entered = 0

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *args) -> None:
        return None

    def execute(self, statement: object) -> _Result:
        self.statements.append(statement)
        return _Result(self.rows)


def test_thumbnail_source_reads_have_a_history_owner_and_compatibility_facades(monkeypatch) -> None:
    owner = getattr(history, "HistoryThumbnailSourceReader", None)
    assert owner is not None
    assert getattr(owner, "__dataclass_params__").frozen
    with pytest.raises(FrozenInstanceError):
        owner(lambda: None).session_factory = lambda: None

    assert str(inspect.signature(db.history_render_hashes)) == "() -> 'list[tuple[str, str | None]]'"
    assert str(inspect.signature(db.history_svgs)) == "(ids: 'list[str]') -> 'dict[str, str]'"

    hashes_session = _Session([(123, None), ("two", "render-hash")])
    hashes_factory_calls = 0

    def hashes_factory() -> _Session:
        nonlocal hashes_factory_calls
        hashes_factory_calls += 1
        return hashes_session

    monkeypatch.setattr(db, "SessionLocal", hashes_factory)
    assert db.history_render_hashes() == [("123", None), ("two", "render-hash")]
    assert hashes_factory_calls == 1
    assert "ORDER BY" not in str(hashes_session.statements[0])
    assert "history.render_hash" in str(hashes_session.statements[0])

    svgs_session = _Session([(123, None), ("present", "<svg />"), ("empty", "")])
    monkeypatch.setattr(db, "SessionLocal", lambda: svgs_session)
    assert db.history_svgs(["123", "present", "empty", "missing"]) == {
        "123": "",
        "present": "<svg />",
        "empty": "",
    }
    assert "history.id IN" in str(svgs_session.statements[0])

    unopened_session = _Session([])
    monkeypatch.setattr(db, "SessionLocal", lambda: unopened_session)
    assert db.history_svgs([]) == {}
    assert unopened_session.entered == 0

    owner_source = inspect.getsource(owner)
    assert "from .. import db" not in owner_source
    assert "thumbnail" not in "\n".join(
        line for line in owner_source.lower().splitlines() if line.startswith("import ")
    )
    assert "session.execute(select(HistoryRow.id, HistoryRow.render_hash))" in owner_source
    assert "HistoryRow.id.in_(ids)" in owner_source
    assert "svg or \"\"" in owner_source
    hashes_facade_source = inspect.getsource(db.history_render_hashes)
    svgs_facade_source = inspect.getsource(db.history_svgs)
    assert "with SessionLocal" not in hashes_facade_source
    assert "with SessionLocal" not in svgs_facade_source
    assert "HistoryThumbnailSourceReader(SessionLocal).history_render_hashes()" in hashes_facade_source
    assert "HistoryThumbnailSourceReader(SessionLocal).history_svgs(ids)" in svgs_facade_source
