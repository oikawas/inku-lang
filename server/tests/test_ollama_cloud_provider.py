"""Ollama Cloud as a provider, and the concurrency ceiling it is listed under.

The provider was added on the condition that four things hold (2026-07-27 ruling):
the description being sent off the machine is stated, the cloud model is not
confused with the local one of the same name, concurrency stays at 1-2, and
Stage 2 keeps using tool calling here. The first two live in the tooltip text,
the third in `max_concurrency`, and the fourth in the request Stage 2 builds —
these tests are what keeps any of them from quietly lapsing.

The fourth condition is the cloud's alone. Local Ollama needs the opposite, and
for a reason that does not carry over: a tool definition rides inside the prompt,
and the Score schema is large enough that Ollama drops prompt to make room
(2026-07-28). So the two providers are tested apart, not together.
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


# --------------------------------------------------------------------------
# How Stage 2 asks for structured output, per provider.
#
# The two providers need opposite things and the reasons do not transfer:
# the cloud ignores structured output and honours tools, while local Ollama
# applies structured output and drops prompt to make room for a tool schema.
# Nothing in the request shape is checked anywhere else, so without these the
# distinction would be one comment away from lapsing.
# --------------------------------------------------------------------------

_SCORE_JSON = '{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1}]}'


class _FakeMessage:
    tool_calls = None

    def __init__(self, content: str) -> None:
        self.content = content


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [type("C", (), {"message": _FakeMessage(content)})()]
        self.usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})()


def _capture_stage2_request(monkeypatch, provider: str) -> dict:
    """Run `_compose_openai` against a stub client and return the request kwargs."""
    import openai

    from inku_server import composer

    seen: dict = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            seen.update(kwargs)
            return _FakeResponse(_SCORE_JSON)

    class _FakeClient:
        def __init__(self, **_kwargs) -> None:
            self.chat = type("Chat", (), {"completions": _FakeCompletions()})()

    monkeypatch.setattr(openai, "OpenAI", _FakeClient)
    # The stage does not need a database to decide how it asks.
    monkeypatch.setattr(composer, "_current_model_settings", default_model_settings)
    composer._compose_openai(
        "中心に円を置く。", model="stub-model", provider=provider, system_prompt="SYS"
    )
    return seen


def test_local_ollama_asks_by_schema_not_by_tool(monkeypatch) -> None:
    seen = _capture_stage2_request(monkeypatch, "ollama")
    # A tool definition is prompt; the schema is not. With a 28k-character system
    # prompt the tool path made local Ollama report 8,194 prompt tokens against
    # 12,195 without it -- it had dropped three quarters of the prompt to fit.
    assert "tools" not in seen
    assert "tool_choice" not in seen
    assert seen["response_format"]["type"] == "json_schema"
    assert seen["response_format"]["json_schema"]["name"] == "submit_score"
    assert seen["response_format"]["json_schema"]["schema"]["type"] == "object"


def test_ollama_cloud_still_asks_by_tool(monkeypatch) -> None:
    seen = _capture_stage2_request(monkeypatch, "ollama-cloud")
    # The cloud ignores all three forms of structured output but does call tools.
    assert "response_format" not in seen
    assert seen["tool_choice"]["function"]["name"] == "submit_score"
    assert seen["tools"][0]["function"]["name"] == "submit_score"


def test_the_system_prompt_is_sent_whole(monkeypatch) -> None:
    # The truncation happened inside Ollama, not here; this pins that we are not
    # the ones shortening it, so a future "fix" cannot be applied in the wrong place.
    for provider in ("ollama", "ollama-cloud"):
        seen = _capture_stage2_request(monkeypatch, provider)
        assert seen["messages"][0] == {"role": "system", "content": "SYS"}
        assert seen["messages"][1]["content"] == "中心に円を置く。"
