"""Direct ownership coverage for persisted history render hashes."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from hashlib import sha256

import pytest

from inku_server import db
from inku_server.persistence import history


def test_history_owns_frozen_render_hash_service() -> None:
    service_type = getattr(history, "HistoryRenderHashService", None)
    assert service_type is not None
    assert is_dataclass(service_type) and service_type.__dataclass_params__.frozen

    payloads = []

    def canonical_json(payload):
        payloads.append(payload)
        return f"canonical-{payload['version']}-雪"

    service = service_type(canonical_json)
    with pytest.raises(FrozenInstanceError):
        service.canonical_json_fn = None

    assert service.legacy_render_hash_for_item({}) == "rh2:" + sha256(
        "canonical-rh2-雪".encode("utf-8")
    ).hexdigest()
    assert service.render_hash_for_item({}) == "rh3:" + sha256(
        "canonical-rh3-雪".encode("utf-8")
    ).hexdigest()
    assert [payload["version"] for payload in payloads] == ["rh2", "rh3"]


def test_db_render_hash_facades_construct_and_delegate_at_call_time(monkeypatch) -> None:
    created = []
    calls = []
    canonical_json = object()
    legacy_item = object()
    current_item = object()
    legacy_result = object()
    current_result = object()

    class Recording:
        def __init__(self, *args):
            created.append(args)

        def legacy_render_hash_for_item(self, item):
            calls.append(("legacy", item))
            return legacy_result

        def render_hash_for_item(self, item):
            calls.append(("current", item))
            return current_result

    monkeypatch.setattr(history, "HistoryRenderHashService", Recording, raising=False)
    monkeypatch.setattr(db, "_canonical_json", canonical_json)

    assert db._legacy_render_hash_for_item(legacy_item) is legacy_result
    assert db.render_hash_for_item(current_item) is current_result
    assert created == [(canonical_json,), (canonical_json,)]
    assert calls == [("legacy", legacy_item), ("current", current_item)]
