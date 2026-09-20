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


def test_anthropic_forces_the_core_schema_tool_and_extracts_its_input(monkeypatch):
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
    assert request_body["tool_choice"] == {
        "type": "tool",
        "name": "submit_pipeline_response",
    }


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
