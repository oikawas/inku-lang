"""What the product hands the Anthropic SDK, and what it reads back.

Measured 2026-08-02, before raising `anthropic` from 0.96.0: breaking all eleven
SDK call sites turned 14 of 2011 tests red, and every one of those 14 was on the
OpenAI-compatible side.  Breaking only the four `client.messages.create` calls
turned nothing red at all.  Twenty-four minor versions were about to move under a
path with no test on it, where the first sign of a broken call would have been a
drawing that did not come out.

This does not test the SDK.  It freezes the request the product builds and the
response attributes it reads, so that a rename on either side has to pass through
a visible edit here instead of arriving silently.  The stub goes in with
`monkeypatch.setattr(anthropic, "Anthropic", ...)`: all four call sites import
inside the function body, so they resolve the name off the module at call time.

Enter through `compose()` and `interpret_detail()` rather than the private
`_compose_anthropic` / `_interpret_anthropic`, so provider dispatch is part of
what is covered -- a helper called directly would skip the branch that chooses
Anthropic in the first place.
"""

from __future__ import annotations

import pytest

from inku_server.model_settings import default_model_settings

_ANTHROPIC_MODEL = "claude-opus-4-7"
_SCORE_INPUT = {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}


class _ReadRecorder:
    """Wraps a value and records which attribute names were asked for."""

    def __init__(self, values: dict, log: list[str], prefix: str) -> None:
        object.__setattr__(self, "_values", values)
        object.__setattr__(self, "_log", log)
        object.__setattr__(self, "_prefix", prefix)

    def __getattr__(self, name: str):
        values = object.__getattribute__(self, "_values")
        log = object.__getattribute__(self, "_log")
        prefix = object.__getattribute__(self, "_prefix")
        log.append(f"{prefix}{name}")
        if name not in values:
            raise AttributeError(name)
        return values[name]


class _Call:
    """One captured request plus the reads the product made off the response."""

    def __init__(self) -> None:
        self.client_kwargs: dict = {}
        self.request: dict = {}
        self.reads: list[str] = []


def _install(monkeypatch, call: _Call, *, blocks: list[dict]) -> None:
    import anthropic

    def _response() -> object:
        wrapped = [
            _ReadRecorder(block, call.reads, f"content[].") for block in blocks
        ]
        return _ReadRecorder(
            {
                "usage": _ReadRecorder(
                    {"input_tokens": 11, "output_tokens": 22}, call.reads, "usage."
                ),
                "content": wrapped,
            },
            call.reads,
            "",
        )

    class _Messages:
        def create(self, **kwargs):
            call.request.update(kwargs)
            return _response()

    class _FakeAnthropic:
        def __init__(self, **kwargs) -> None:
            call.client_kwargs.update(kwargs)
            self.messages = _Messages()

    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)


def _text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def _tool_block() -> dict:
    return {"type": "tool_use", "name": "submit_score", "input": _SCORE_INPUT}


@pytest.fixture
def call() -> _Call:
    return _Call()


# --- Stage 2 (composer.py) -------------------------------------------------


def _run_stage2(monkeypatch, call: _Call):
    from inku_server import composer

    _install(monkeypatch, call, blocks=[_tool_block()])
    monkeypatch.setattr(composer, "_current_model_settings", default_model_settings)
    return composer.compose("中心に円を置く。", model=_ANTHROPIC_MODEL)


def test_stage2_sends_exactly_these_keys(monkeypatch, call) -> None:
    _run_stage2(monkeypatch, call)
    assert set(call.request) == {
        "model",
        "max_tokens",
        "system",
        "tools",
        "tool_choice",
        "messages",
    }
    assert call.request["model"] == _ANTHROPIC_MODEL
    assert isinstance(call.request["max_tokens"], int)
    assert isinstance(call.request["system"], str) and call.request["system"]
    assert call.request["messages"][0]["role"] == "user"
    assert isinstance(call.request["messages"][0]["content"], str)


def test_stage2_asks_for_the_submit_score_tool_by_name(monkeypatch, call) -> None:
    # Stage 2 is a tool call here, not free text; the name is what the reader below
    # matches on, so the two have to agree.
    _run_stage2(monkeypatch, call)
    assert call.request["tool_choice"] == {"type": "tool", "name": "submit_score"}
    assert call.request["tools"][0]["name"] == "submit_score"


def test_stage2_reads_these_response_attributes(monkeypatch, call) -> None:
    _run_stage2(monkeypatch, call)
    assert set(call.reads) == {
        "usage",
        "usage.input_tokens",
        "usage.output_tokens",
        "content",
        "content[].type",
        "content[].name",
        "content[].input",
    }


def test_stage2_carries_the_token_counts_out(monkeypatch, call) -> None:
    _score, tokens_in, tokens_out = _run_stage2(monkeypatch, call)
    assert (tokens_in, tokens_out) == (11, 22)


# --- Stage 1 (interpreter.py) ----------------------------------------------


def _run_stage1(monkeypatch, call: _Call):
    from inku_server import interpreter

    _install(monkeypatch, call, blocks=[_text_block("地: 白い紙。中心に円を置く。")])
    monkeypatch.setattr(interpreter, "_current_model_settings", default_model_settings)
    return interpreter.interpret_detail("中心に円を置く。", model=_ANTHROPIC_MODEL)


def test_stage1_sends_exactly_these_keys(monkeypatch, call) -> None:
    _run_stage1(monkeypatch, call)
    # No tools here: Stage 1 answers in prose.
    assert set(call.request) == {"model", "max_tokens", "system", "messages"}
    assert call.request["model"] == _ANTHROPIC_MODEL
    assert isinstance(call.request["max_tokens"], int)
    assert call.request["messages"] == [
        {"role": "user", "content": "中心に円を置く。"}
    ]


def test_stage1_reads_these_response_attributes(monkeypatch, call) -> None:
    _run_stage1(monkeypatch, call)
    assert set(call.reads) == {
        "usage",
        "usage.input_tokens",
        "usage.output_tokens",
        "content",
        "content[].type",
        "content[].text",
    }


def test_stage1_carries_the_token_counts_out(monkeypatch, call) -> None:
    _ddl, _thinking, tokens_in, tokens_out = _run_stage1(monkeypatch, call)
    assert (tokens_in, tokens_out) == (11, 22)


# --- the demo instruction endpoint (api_core/routers/public.py) -------------


def test_demo_instruction_sends_exactly_these_keys(monkeypatch, call) -> None:
    from inku_server.api_core.routers import public

    _install(monkeypatch, call, blocks=[_text_block("枯れ枝に鴉。")])
    monkeypatch.setattr(
        public._db, "get_model_settings", default_model_settings, raising=False
    )
    public._generate_demo_instruction("枯れ枝", model=_ANTHROPIC_MODEL, lang="ja")
    # This one is the only caller that sets temperature, and it sets its own much
    # smaller max_tokens; both are part of what the endpoint is.
    assert set(call.request) == {
        "model",
        "max_tokens",
        "temperature",
        "system",
        "messages",
    }
    assert call.request["max_tokens"] == 180
    assert call.request["temperature"] == 0.9


def test_demo_instruction_reads_only_text_blocks(monkeypatch, call) -> None:
    from inku_server.api_core.routers import public

    _install(monkeypatch, call, blocks=[_text_block("枯れ枝に鴉。")])
    monkeypatch.setattr(
        public._db, "get_model_settings", default_model_settings, raising=False
    )
    public._generate_demo_instruction("枯れ枝", model=_ANTHROPIC_MODEL, lang="ja")
    # No usage read here -- this path does not report tokens.
    assert set(call.reads) == {"content", "content[].text", "content[].type"}


# --- the sample generator (trainer.py) -------------------------------------


def test_trainer_sends_exactly_these_keys_and_builds_a_bare_client(
    monkeypatch, call
) -> None:
    from inku_server import trainer

    _install(monkeypatch, call, blocks=[_text_block("霧の中の橋。")])
    trainer._generate_anthropic("素朴", _ANTHROPIC_MODEL)
    assert set(call.request) == {"model", "max_tokens", "system", "messages"}
    assert call.request["max_tokens"] == 256
    # Unlike the other three, this one reads no stored connection: it constructs
    # Anthropic() with nothing and lets the SDK find the key in the environment.
    assert call.client_kwargs == {}


# --- how the client itself is built ----------------------------------------


def test_stored_connection_reaches_the_client_constructor(monkeypatch, call) -> None:
    from inku_server import composer

    settings = default_model_settings()
    settings["providers"]["anthropic"]["api_key"] = "test-key-not-real"
    settings["providers"]["anthropic"]["base_url"] = "https://example.invalid/v1"

    _install(monkeypatch, call, blocks=[_tool_block()])
    monkeypatch.setattr(composer, "_current_model_settings", lambda: settings)
    composer.compose("中心に円を置く。", model=_ANTHROPIC_MODEL)

    assert call.client_kwargs == {
        "api_key": "test-key-not-real",
        "base_url": "https://example.invalid/v1",
    }


def test_with_nothing_configured_only_the_default_base_url_is_passed(
    monkeypatch, call
) -> None:
    from inku_server import composer
    from inku_server.model_settings import PROVIDER_DEFINITIONS

    definition = next(p for p in PROVIDER_DEFINITIONS if p["id"] == "anthropic")
    monkeypatch.delenv(str(definition["api_key_env"]), raising=False)

    settings = default_model_settings()
    settings["providers"]["anthropic"]["api_key"] = ""
    settings["providers"]["anthropic"]["base_url"] = ""

    _install(monkeypatch, call, blocks=[_tool_block()])
    monkeypatch.setattr(composer, "_current_model_settings", lambda: settings)
    composer.compose("中心に円を置く。", model=_ANTHROPIC_MODEL)

    # api_key is omitted rather than passed as "", which is what lets the SDK fall
    # back to its own environment lookup.  base_url is never omitted: connection_for
    # substitutes the provider's default, so the client is always told where to go.
    assert call.client_kwargs == {"base_url": definition["default_base_url"]}


def test_a_stored_key_beats_the_environment(monkeypatch, call) -> None:
    from inku_server import composer
    from inku_server.model_settings import PROVIDER_DEFINITIONS
    from inku_server.secrets import encrypt_secret

    definition = next(p for p in PROVIDER_DEFINITIONS if p["id"] == "anthropic")
    monkeypatch.setenv(str(definition["api_key_env"]), "from-the-environment")

    settings = default_model_settings()
    settings["providers"]["anthropic"]["api_key"] = encrypt_secret("from-the-database")

    _install(monkeypatch, call, blocks=[_tool_block()])
    monkeypatch.setattr(composer, "_current_model_settings", lambda: settings)
    composer.compose("中心に円を置く。", model=_ANTHROPIC_MODEL)

    # The stored value is decrypted on the way through; the environment is only the
    # fallback.  Getting this backwards would send requests with the wrong account.
    assert call.client_kwargs["api_key"] == "from-the-database"
