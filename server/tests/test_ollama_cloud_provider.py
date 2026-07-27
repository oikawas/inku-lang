"""Ollama Cloud as a provider, and the concurrency ceiling it is listed under.

The provider was added on the condition that four things hold (2026-07-27 ruling):
the description being sent off the machine is stated, the cloud model is not
confused with the local one of the same name, concurrency stays at 1-2, and
Stage 2 keeps using tool calling here. The first two live in the tooltip text,
the third in `max_concurrency`, and the fourth is what the OpenAI path already
does — these tests are what keeps any of them from quietly lapsing.
"""

from __future__ import annotations

import threading
import time

from inku_server.model_settings import (
    PROVIDER_DEFINITIONS,
    default_model_settings,
    provider_concurrency_limit,
)
from inku_server.provider_limits import provider_slot
from inku_server.verified_model_catalog import VERIFIED_OLLAMA_CLOUD_MODELS

_BY_ID = {str(provider["id"]): provider for provider in PROVIDER_DEFINITIONS}


def test_provider_is_listed_and_separate_from_local_ollama() -> None:
    cloud = _BY_ID["ollama-cloud"]
    local = _BY_ID["ollama"]
    assert cloud["default_base_url"] == "https://ollama.com/v1"
    assert cloud["requires_api_key"] is True
    # The local one must stay keyless; that is the whole point of it.
    assert local["requires_api_key"] is False
    assert cloud["api_key_env"] != local["api_key_env"]
    assert cloud["base_url_env"] != local["base_url_env"]


def test_every_model_says_the_description_leaves_the_machine() -> None:
    assert VERIFIED_OLLAMA_CLOUD_MODELS, "catalog is empty"
    for model in VERIFIED_OLLAMA_CLOUD_MODELS:
        assert "ollama.com" in str(model["comment_ja"])
        assert "ollama.com" in str(model["comment_en"])
        # ...and that it is not the local model wearing the same name.
        assert "ローカル" in str(model["comment_ja"])
        assert "local" in str(model["comment_en"]).lower()


def test_catalog_reaches_the_settings_the_ui_reads() -> None:
    providers = default_model_settings()["providers"]
    assert "ollama-cloud" in providers
    models = providers["ollama-cloud"]["models"]
    ids = {str(model["id"]) for model in models}
    assert "gemma4:31b" in ids
    assert len(ids) == len(VERIFIED_OLLAMA_CLOUD_MODELS)
    # The tooltip reads these four; normalisation drops keys it does not know, so a
    # renamed field would show as an em dash rather than fail anywhere.
    measured = next(model for model in models if model["id"] == "gemma4:31b")
    for key in ("purposes", "speed_label", "comment_ja", "comment_en"):
        assert key in measured


def test_concurrency_is_capped_for_the_cloud_and_free_elsewhere() -> None:
    assert provider_concurrency_limit("ollama-cloud") == 2
    for provider_id in ("ollama", "nvidia", "openai", "anthropic", "gemini", "ovms"):
        assert provider_concurrency_limit(provider_id) == 0
    assert provider_concurrency_limit("no-such-provider") == 0


def test_slot_admits_two_at_once_and_makes_the_third_wait() -> None:
    started = threading.Semaphore(0)
    release = threading.Event()
    inside: list[int] = []
    peak = 0
    guard = threading.Lock()

    def worker() -> None:
        nonlocal peak
        with provider_slot("ollama-cloud"):
            with guard:
                inside.append(1)
                peak = max(peak, len(inside))
            started.release()
            release.wait(timeout=5)
            with guard:
                inside.pop()

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for thread in threads:
        thread.start()
    # Two get in immediately; the third must not.
    assert started.acquire(timeout=5)
    assert started.acquire(timeout=5)
    assert not started.acquire(timeout=0.3), "a third request entered while two were in flight"
    release.set()
    for thread in threads:
        thread.join(timeout=5)
    assert peak == 2


def test_slot_is_free_for_providers_without_a_limit() -> None:
    entered = threading.Event()

    def worker() -> None:
        with provider_slot("ollama"):
            entered.set()
            time.sleep(0.05)

    with provider_slot("ollama"):
        thread = threading.Thread(target=worker)
        thread.start()
        # An unlimited provider must not serialise on itself.
        assert entered.wait(timeout=2)
        thread.join(timeout=2)


def test_slot_releases_on_failure() -> None:
    for _ in range(4):
        try:
            with provider_slot("ollama-cloud"):
                raise RuntimeError("request failed")
        except RuntimeError:
            pass
    # If the slot leaked, the ceiling of 2 would be exhausted by now. Take both.
    with provider_slot("ollama-cloud"), provider_slot("ollama-cloud"):
        pass
