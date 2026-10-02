"""Transport boundary only: exact prompt, no host retry, one whole-attempt deadline."""

import asyncio
import json

import httpx

from inku_server.pipeline_provider import ProviderOptions, SingleAttemptProvider


def _action() -> dict:
    return {
        "tag": "generate_normalized_ddl",
        "identity": {"action_id": "a", "attempt": 1, "request_digest": "b"},
        "timeout_ms": "1000",
        "payload": {
            "prompt": {
                "system": "exact bounded system",
                "message": "exact visible input",
                "action_name": "generate_normalized_ddl",
                "response_schema": {
                    "type": "object",
                    "required": ["normalized_ddl"],
                    "properties": {"normalized_ddl": {"type": "string"}},
                },
            }
        },
    }


def test_single_attempt_preserves_core_prompt_and_reports_rate_limit_and_deadline(monkeypatch):
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model", lambda *args, **kwargs: ("fixture", "fixture-model"))
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "fixture", "kind": "openai_compatible", "base_url": "https://provider.invalid/v1",
        "api_key": "test-only", "requires_api_key": True,
    })
    seen = []

    async def request(value):
        seen.append(value)
        if len(seen) == 2:
            return httpx.Response(429, json={"error": "fixture rate limit"})
        if len(seen) == 3:
            await asyncio.sleep(0.2)
        return httpx.Response(200, json={"choices": [{"message": {
            "content": None, "tool_calls": [{"type": "function", "function": {
                "name": "submit_pipeline_response", "arguments": ' {"normalized_ddl":"keep these bytes"} ',
            }}],
        }}]})

    provider = SingleAttemptProvider(
        ProviderOptions({}, "fixture-model", "fixture-model", 256, 8192),
        transport=httpx.MockTransport(request),
    )
    action = _action()
    result = provider(action)
    assert result["tag"] == "normalized_ddl_generated"
    assert result["identity"] == action["identity"]
    assert result["response"] == ' {"normalized_ddl":"keep these bytes"} '
    assert json.loads(seen[0].content)["messages"] == [
        {"role": "system", "content": "exact bounded system"}, {"role": "user", "content": "exact visible input"},
    ]
    request_body = json.loads(seen[0].content)
    assert request_body["tools"][0]["function"]["parameters"] == action["payload"]["prompt"]["response_schema"]
    assert request_body["tool_choice"]["function"]["name"] == "submit_pipeline_response"
    assert request_body["temperature"] == 0.3
    assert provider(action)["failure"] == "rate_limited"
    assert len(seen) == 2  # The host has not retried the rejected attempt.
    assert provider({**action, "timeout_ms": "20"})["failure"] == "transport_timeout"
    assert len(seen) == 3


def test_openai_gets_its_own_length_field_and_a_refusal_says_why(monkeypatch, caplog):
    """gpt-5.6 on api.openai.com was refused before any answer: it takes
    max_completion_tokens and only the default temperature. The refusal's own
    reason now reaches the log, with anything shaped like a key masked."""
    target = {"model": "gpt-5.6-luna"}
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model",
                        lambda *args, **kwargs: ("openai", target["model"]))
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "openai", "kind": "openai_compatible", "base_url": "https://api.openai.com/v1",
        "api_key": "test-only", "requires_api_key": True,
    })
    seen = []

    async def request(value):
        seen.append(json.loads(value.content))
        if len(seen) == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"normalized_ddl":"x"}'}}]})
        return httpx.Response(400, json={"error": {
            "message": "Incorrect API key provided: sk-proj-abcdef123456.", "type": "invalid_request_error",
            "param": "max_tokens", "code": "unsupported_parameter",
        }})

    provider = SingleAttemptProvider(ProviderOptions({}, "m", "m", 256, 8192), transport=httpx.MockTransport(request))
    assert provider(_action())["tag"] == "normalized_ddl_generated"
    assert seen[0]["max_completion_tokens"] == 256
    assert "max_tokens" not in seen[0] and "temperature" not in seen[0]
    # Function tools are refused while gpt-5.6 reasons (Pentala, 2026-09-28).
    assert seen[0]["reasoning_effort"] == "none"

    target["model"] = "gpt-4.1"
    with caplog.at_level("WARNING", logger="inku_server.pipeline_provider"):
        assert provider(_action())["failure"] == "provider_rejected"
    assert seen[1]["temperature"] == 0.3 and seen[1]["max_completion_tokens"] == 256
    assert "reasoning_effort" not in seen[1]
    logged = json.loads(caplog.records[-1].getMessage().split(" ", 1)[1])
    assert logged["status"] == 400 and logged["param"] == "max_tokens" and logged["code"] == "unsupported_parameter"
    assert logged["provider"] == "openai" and logged["model"] == "gpt-4.1"
    assert "sk-proj" not in logged["message"]


def test_mlx_profile_survives_settings_and_requests_core_schema_without_tools(monkeypatch):
    """Forced tools made Gemma 4 repeat thought markers up to max_tokens.
    A stored MLX profile must reach constrained JSON decoding, even under a
    custom provider ID, without changing the prompt or losing its credentials.
    """
    from inku_server.model_settings import connection_for, update_model_settings

    settings = update_model_settings({}, {"providers": {"mac-models": {
        "kind": "openai_compatible", "base_url": "http://mlx.invalid/v1",
        "api_key": "test-only", "requires_api_key": True,
        "models": [{"id": "fixture-model"}],
    }}})
    settings = update_model_settings(settings, {"providers": {"mac-models": {"kind": "mlx"}}})
    connection = connection_for("mac-models", settings)
    assert connection["kind"] == "openai_compatible"  # list and Vision endpoints
    assert connection["api_key"] == "test-only"
    assert connection["base_url"] == "http://mlx.invalid/v1"
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model",
                        lambda *args, **kwargs: ("mac-models", "fixture-model"))
    seen = []

    async def request(value):
        seen.append(json.loads(value.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "content": '{"normalized_ddl":"keep these bytes"}',
        }, "finish_reason": "stop"}]})

    provider = SingleAttemptProvider(
        ProviderOptions(settings, "fixture-model", "fixture-model", 256, 8192),
        transport=httpx.MockTransport(request),
    )
    action = _action()
    result = provider(action)
    assert result["response"] == '{"normalized_ddl":"keep these bytes"}'
    assert len(seen) == 1
    body = seen[0]
    assert body["messages"] == [
        {"role": "system", "content": action["payload"]["prompt"]["system"]},
        {"role": "user", "content": action["payload"]["prompt"]["message"]},
    ]
    assert body["response_format"]["json_schema"]["schema"] == action["payload"]["prompt"]["response_schema"]
    assert body["enable_thinking"] is False
    assert body["max_tokens"] == 256
    assert "tools" not in body and "tool_choice" not in body


def test_mlx_gemma4_sampling_reaches_request_without_changing_core_contract(monkeypatch):
    """A supplied sketch made Gemma 4 repeat the same layer at temperature 0.3.
    Its recommended sampler must reach the wire only for the MLX Gemma 4 model.
    """
    target = {"model": "mlx-community/gemma-4-12B-it-4bit", "profile": "mlx"}
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model",
                        lambda *args, **kwargs: ("mac-models", target["model"]))
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "mac-models", "kind": "openai_compatible", "api_profile": target["profile"],
        "base_url": "http://model.invalid/v1", "api_key": "test-only", "requires_api_key": True,
    })
    seen = []

    async def request(value):
        seen.append(json.loads(value.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "content": '{"normalized_ddl":"keep these bytes"}',
        }, "finish_reason": "stop"}]})

    provider = SingleAttemptProvider(
        ProviderOptions({}, "fixture-model", "fixture-model", 256, 8192),
        transport=httpx.MockTransport(request),
    )
    action = _action()
    assert provider(action)["response"] == '{"normalized_ddl":"keep these bytes"}'
    body = seen[0]
    assert (body["temperature"], body["top_p"], body["top_k"]) == (1.0, 0.95, 64)
    assert body["max_tokens"] == 256 and body["enable_thinking"] is False
    assert body["messages"] == [
        {"role": "system", "content": action["payload"]["prompt"]["system"]},
        {"role": "user", "content": action["payload"]["prompt"]["message"]},
    ]
    assert body["response_format"]["json_schema"]["schema"] == action["payload"]["prompt"]["response_schema"]
    assert "tools" not in body and "tool_choice" not in body
    for model, profile in [
        ("mlx-community/Qwen3.6-35B-A3B-4bit", "mlx"),
        ("google/gemma-4-31b-it", "openai_compatible"),
    ]:
        target.update(model=model, profile=profile)
        assert provider(action)["tag"] == "normalized_ddl_generated"
        assert seen[-1]["temperature"] == 0.3
        assert "top_p" not in seen[-1] and "top_k" not in seen[-1]
    assert len(seen) == 3  # One send per call, with no transport retry.


def test_missing_credentials_keep_only_safe_failure_detail(monkeypatch):
    monkeypatch.setattr(
        "inku_server.pipeline_provider.provider_for_model",
        lambda *args, **kwargs: ("ollama-cloud", "gemma4:31b"),
    )
    monkeypatch.setattr(
        "inku_server.pipeline_provider.connection_for",
        lambda *args: {
            "id": "ollama-cloud",
            "kind": "openai_compatible",
            "base_url": "https://ollama.invalid/v1",
            "api_key": "",
            "requires_api_key": True,
        },
    )
    provider = SingleAttemptProvider(
        ProviderOptions({}, "ollama-cloud:gemma4:31b", "fixture", 256, 8192)
    )
    action = _action()
    action["payload"]["prompt"]["message"] = "raw secret marker"

    result = provider(action)

    assert result["failure"] == "provider_rejected"
    assert provider.failure_detail == "credentials_unavailable"
    assert "raw secret marker" not in repr(result)


def test_anthropic_offers_the_core_schema_tool_and_extracts_its_input(monkeypatch):
    monkeypatch.setattr(
        "inku_server.pipeline_provider.provider_for_model",
        lambda *args, **kwargs: ("anthropic", "claude-fixture"),
    )
    monkeypatch.setattr(
        "inku_server.pipeline_provider.connection_for",
        lambda *args: {
            "id": "anthropic",
            "kind": "anthropic",
            "base_url": "https://api.anthropic.invalid",
            "api_key": "test-only",
            "requires_api_key": True,
        },
    )
    seen = []

    async def request(value):
        seen.append(value)
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "tool_use",
                        "name": "submit_pipeline_response",
                        "input": {"normalized_ddl": "keep these bytes"},
                    }
                ]
            },
        )

    provider = SingleAttemptProvider(
        ProviderOptions({}, "fixture", "anthropic:claude-fixture", 256, 8192),
        transport=httpx.MockTransport(request),
    )
    action = _action()

    result = provider(action)

    assert result["tag"] == "normalized_ddl_generated"
    assert json.loads(result["response"]) == {"normalized_ddl": "keep these bytes"}
    request_body = json.loads(seen[0].content)
    assert request_body["tools"] == [
        {
            "name": "submit_pipeline_response",
            "description": "Submit the requested pipeline response.",
            "input_schema": action["payload"]["prompt"]["response_schema"],
        }
    ]
    # claude-opus-5-5 refuses a forced tool, so the choice is left to the model.
    assert request_body["tool_choice"] == {"type": "auto"}


def test_anthropic_answer_given_as_text_is_read_as_the_response_object(monkeypatch):
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model",
                        lambda *args, **kwargs: ("anthropic", "claude-opus-5-5"))
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "anthropic", "kind": "anthropic", "base_url": "https://api.anthropic.invalid",
        "api_key": "test-only", "requires_api_key": True,
    })
    answers = iter([
        {"content": [{"type": "thinking", "thinking": "..."},
                     {"type": "text", "text": 'Here it is:\n```json\n{"normalized_ddl": "keep"}\n```'}]},
        {"content": [{"type": "text", "text": "I cannot help with that."}]},
    ])

    async def request(_value):
        return httpx.Response(200, json=next(answers))

    provider = SingleAttemptProvider(ProviderOptions({}, "m", "m", 256, 8192), transport=httpx.MockTransport(request))
    assert json.loads(provider(_action())["response"]) == {"normalized_ddl": "keep"}
    assert provider(_action())["failure"] == "malformed_payload"


def test_gemini_forces_one_schema_bound_function_call_with_minimal_thinking(monkeypatch):
    monkeypatch.setattr(
        "inku_server.pipeline_provider.provider_for_model",
        lambda *args, **kwargs: ("gemini", "gemma-4-31b-it"),
    )
    monkeypatch.setattr(
        "inku_server.pipeline_provider.connection_for",
        lambda *args: {
            "id": "gemini",
            "kind": "gemini",
            "base_url": "https://generativelanguage.invalid",
            "api_key": "test-only",
            "requires_api_key": True,
        },
    )
    seen = []

    async def request(value):
        seen.append(value)
        return httpx.Response(
            200,
            json={
                "candidates": [{
                    "content": {"parts": [{"functionCall": {
                        "name": "submit_pipeline_response",
                        "args": {
                            "results": [
                                {
                                    "id": "h1",
                                    "status": "proposed",
                                    "replacement": "青い円を描く。",
                                },
                                {
                                    "id": "h2",
                                    "status": "unresolved",
                                    "reason": "ambiguous",
                                },
                            ],
                        },
                    }}]}
                }]
            },
        )

    provider = SingleAttemptProvider(
        ProviderOptions({}, "gemini:gemma-4-31b-it", "fixture", 256, 8192),
        transport=httpx.MockTransport(request),
    )
    action = _action()
    action["tag"] = "complete_visible_ddl_holes"
    action["payload"]["prompt"]["action_name"] = "complete_visible_ddl_holes"
    action["payload"]["prompt"]["response_schema"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["results"],
        "properties": {
            "results": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {
                    "oneOf": [
                        {
                            "type": "object",
                            "required": ["id", "status", "replacement"],
                            "properties": {
                                "id": {"const": "h1"},
                                "status": {"const": "proposed"},
                                "replacement": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": 4096,
                                },
                            },
                        },
                        {
                            "type": "object",
                            "required": ["id", "status", "reason"],
                            "properties": {
                                "id": {"const": "h2"},
                                "status": {"const": "unresolved"},
                                "reason": {"const": "ambiguous"},
                            },
                        },
                    ]
                },
            },
        },
    }

    result = provider(action)

    assert result["tag"] == "visible_ddl_hole_patch_generated"
    assert json.loads(result["response"]) == {
        "results": [
            {
                "id": "h1",
                "status": "proposed",
                "replacement": "青い円を描く。",
            },
            {
                "id": "h2",
                "status": "unresolved",
                "reason": "ambiguous",
            },
        ],
    }
    assert len(seen) == 1
    request_body = json.loads(seen[0].content)
    declaration = request_body["tools"][0]["functionDeclarations"][0]
    assert declaration["name"] == "submit_pipeline_response"
    projected = declaration["parametersJsonSchema"]
    projected_items = projected["properties"]["results"]["items"]
    assert "oneOf" not in projected_items
    assert projected_items["properties"]["id"] == {
        "enum": ["h1", "h2"]
    }
    assert projected_items["properties"]["status"] == {
        "enum": ["proposed", "unresolved"]
    }
    assert projected_items["properties"]["replacement"] == {
        "type": "string"
    }
    assert projected_items["properties"]["reason"] == {
        "enum": ["ambiguous"],
    }
    assert request_body["toolConfig"] == {
        "functionCallingConfig": {
            "mode": "ANY",
            "allowedFunctionNames": ["submit_pipeline_response"],
        }
    }
    assert request_body["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "minimal"
    }


def _reading_action() -> dict:
    # Keys arrive in name order, as the core's JSON writes them; the order that
    # matters is named in propertyOrdering.
    schema = {
        "properties": {
            "relations": {"type": "array", "items": {
                "properties": {"layers": {"type": "array", "items": {"type": "integer"}},
                               "type": {"type": "string", "enum": ["near"]}},
                "propertyOrdering": ["type", "layers"],
                "required": ["type", "layers"],
                "type": "object",
            }},
            "roles": {"type": "array", "items": {"type": "string", "enum": ["focal"]}},
            "thesis": {"type": "string"},
        },
        "propertyOrdering": ["thesis", "roles", "relations"],
        "required": ["thesis", "roles", "relations"],
        "type": "object",
    }
    action = _action()
    action["tag"] = "read_composition"
    action["payload"]["prompt"]["action_name"] = "read_composition"
    action["payload"]["prompt"]["response_schema"] = schema
    return action


def test_the_composition_reading_is_sent_as_stage1_with_the_schema_order(monkeypatch):
    """The reading goes out as the prototype measured it: Stage 1's model and
    sampling, and the properties in the order the schema names (thesis first)."""
    models = []

    def provider_for_model(model_ref, **kwargs):
        models.append((model_ref, kwargs.get("stage")))
        return "gemini", "gemma-4-31b-it"

    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model", provider_for_model)
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "gemini", "kind": "gemini", "base_url": "https://generativelanguage.invalid",
        "api_key": "test-only", "requires_api_key": True,
    })
    seen = []

    async def request(value):
        seen.append(value)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"functionCall": {
            "name": "submit_pipeline_response",
            "args": {"thesis": "t", "roles": ["focal"], "relations": []},
        }}]}}]})

    provider = SingleAttemptProvider(
        ProviderOptions({}, "gemini:stage1-model", "gemini:stage2-model", 256, 8192),
        transport=httpx.MockTransport(request),
    )
    action = _reading_action()
    result = provider(action)
    assert result["tag"] == "composition_read"
    assert json.loads(result["response"]) == {"thesis": "t", "roles": ["focal"], "relations": []}
    assert models == [("gemini:stage1-model", "stage1")]
    parameters = json.loads(seen[0].content)["tools"][0]["functionDeclarations"][0]["parametersJsonSchema"]
    assert list(parameters["properties"]) == ["thesis", "roles", "relations"]
    assert list(parameters["properties"]["relations"]["items"]["properties"]) == ["type", "layers"]

    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model", lambda *args, **kwargs: ("fixture", "fixture-model"))
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "fixture", "kind": "openai_compatible", "base_url": "https://provider.invalid/v1",
        "api_key": "test-only", "requires_api_key": True,
    })
    sent = []

    async def openai_request(value):
        sent.append(value)
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [{
            "type": "function", "function": {"name": "submit_pipeline_response", "arguments": "{}"},
        }]}}]})

    openai = SingleAttemptProvider(
        ProviderOptions({}, "fixture-model", "fixture-model", 256, 8192),
        transport=httpx.MockTransport(openai_request),
    )
    assert openai(_reading_action())["tag"] == "composition_read"
    assert json.loads(sent[0].content)["temperature"] == 0.3


def test_each_provider_action_is_recorded_under_its_stage():
    from inku_server.pipeline_provider import provider_stage_record

    assert provider_stage_record("generate_normalized_ddl") == "stage1"
    assert provider_stage_record("read_composition") == "composition"
    assert provider_stage_record("complete_visible_ddl_holes") == "stage2"
