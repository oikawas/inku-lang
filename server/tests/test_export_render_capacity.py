import pytest
from fastapi import HTTPException

from inku_server.api_core import state
from inku_server.api_core.routers import history


@pytest.mark.parametrize("kind", ["card", "animation", "layer"])
def test_exports_refuse_full_render_capacity(monkeypatch, kind):
    monkeypatch.setattr(state, "_render_slots", state._RenderCapacity(1))
    assert state._render_slots.acquire()
    monkeypatch.setattr(history._db, "get_items", lambda user, ids: [{"id": i, "svg": "<svg/>"} for i in ids])
    try:
        with pytest.raises(HTTPException) as error:
            if kind == "card":
                history.api_history_export_card(history.CardExportBody(id="one"), {"id": "owner"})
            else:
                ids = ["one"] if kind == "layer" else ["one", "two"]
                history.api_history_export_animation(history.AnimationExportBody(ids=ids), {"id": "owner"})
        assert error.value.status_code == 503
        assert error.value.headers == {"Retry-After": "1"}
    finally:
        state._render_slots.release()
