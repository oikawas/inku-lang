from threading import Event

import pytest
from fastapi import HTTPException

from inku_server.api_core import rendering
from inku_server.api_core.routers import history


def test_rebuild_returns_before_executor_finishes_and_writes_all_items(monkeypatch, tmp_path):
    entered, release, done = Event(), Event(), Event()
    items = [{"id": str(i)} for i in range(50)]
    monkeypatch.setattr(history, "_output_save_settings", lambda: {"enabled": True})
    monkeypatch.setattr(history._db, "get_items", lambda *_: items)
    def save(item):
        entered.set()
        assert release.wait(10)
        (tmp_path / item["id"]).write_text("saved")
        if item["id"] == "49":
            done.set()
    monkeypatch.setattr(rendering, "_save_history_artifacts", save)
    try:
        result = history.api_history_rebuild_output_files(history.HistoryIdsBody(ids=[x["id"] for x in items]), {"id": "u"})
        assert result == {"ok": True, "count": 50}
        assert entered.wait(5)
        assert not done.is_set()
    finally:
        release.set()
    assert done.wait(10)
    assert len(list(tmp_path.iterdir())) == 50


def test_rebuild_reports_full_queue(monkeypatch):
    monkeypatch.setattr(history, "_output_save_settings", lambda: {"enabled": True})
    monkeypatch.setattr(history._db, "get_items", lambda *_: [{"id": "one"}])
    monkeypatch.setattr(history, "_submit_history_artifact_rebuild", lambda _: False)
    with pytest.raises(HTTPException) as error:
        history.api_history_rebuild_output_files(history.HistoryIdsBody(ids=["one"]), {"id": "u"})
    assert error.value.status_code == 503
    assert error.value.headers == {"Retry-After": "1"}
