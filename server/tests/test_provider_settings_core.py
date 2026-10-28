import json
from pathlib import Path

from inku_server import model_settings
from inku_server.verified_model_catalog import core_catalog


def test_provider_definitions_and_references_match_server_baseline():
    cases = json.loads((Path(__file__).parent / "data/provider-settings-cases.json").read_text())
    assert model_settings.PROVIDER_DEFINITIONS == cases["definitions"]
    settings = cases["reference_settings"]
    for row in cases["references"]:
        assert list(model_settings.split_model_ref(row["ref"], settings)) == row["split"]
        for stage in ("stage1", "stage2"):
            assert list(model_settings.provider_for_model(row["ref"], stage=stage, settings=settings)) == row[stage]
    for row in cases["models_normalization"]:
        assert model_settings._normalize_models(row["input"]) == row["result"]
    for row in cases["user_normalization"]:
        assert model_settings.normalize_user_model_settings(row["input"]) == row["result"]
    for row in cases["user_updates"]:
        assert model_settings.update_user_model_settings(row["input"], row["patch"]) == row["result"]
    for row in cases["normalization"]:
        assert model_settings.normalize_model_settings(row["input"]) == row["result"]
    for row in cases["updates"]:
        assert model_settings.update_model_settings(row["input"], row["patch"]) == row["result"]
    for row in cases["catalogs"]:
        assert model_settings.model_provider_catalog(row["input"], include_disabled=row["disabled"],
            include_developer=row["developer"], purpose=row["purpose"]) == row["result"]
    for row in cases["validation_cases"]:
        answer = core_catalog("validate_settings", **row["input"])
        assert {key: answer[key] for key in row["result"]} == row["result"]
    for row in cases["resolution_cases"]:
        assert list(model_settings.provider_for_model(row["ref"], stage=row["stage"], settings=row["settings"])) == row["result"]
    for row in cases["fetch_plan_cases"]:
        answer = core_catalog("model_list_start", kind=row["kind"], base_url=row["base_url"], api_key=row["api_key"])
        assert {key: answer[key] for key in ("url", "headers", "items_key", "query")} == {key: row[key] for key in ("url", "headers", "items_key", "query")}
        assert core_catalog("model_list_next", kind=row["kind"], page=row["next_page"])["query"] == row["next_query"]


def test_validation_report_is_read_only_and_requires_an_administrator():
    from fastapi.testclient import TestClient
    from inku_server.api import app
    from inku_server.api_core.deps import _admin_user
    app.dependency_overrides[_admin_user] = lambda: {'id': 'fixture-admin'}
    try:
        response = TestClient(app).post('/api/settings/models/validate', json={
            'provider': ' My-Provider ', 'base_url': 'https://example.invalid/v1/',
            'rate_limits': {'rpm': 1, 'tpm': 2, 'rpd': 3},
            'models': [{'id': 'first'}, {'id': 'first'}],
        })
        assert response.status_code == 200
        assert response.json() == {'normalized_provider': 'my-provider',
            'normalized_url': 'https://example.invalid/v1', 'provider_valid': True,
            'url_valid': True, 'rate_limits_valid': True, 'duplicate_models': ['first']}
    finally:
        app.dependency_overrides.pop(_admin_user, None)
    assert TestClient(app).post('/api/settings/models/validate', json={}).status_code in (401, 403)


def test_android_local_provider_uses_shared_settings_and_never_disables():
    case = json.loads((Path(__file__).parent / "data/provider-settings-cases.json").read_text())["android_local"]
    android = core_catalog("providers", host="android")["providers"]
    assert android[0] == case["definition"]
    for host in ("server", "macos"):
        assert all(row["id"] != "local-litert-lm" for row in core_catalog("providers", host=host)["providers"])
    settings = {"providers": {"local-litert-lm": {"kind": case["kind"], "active": False, "models": [case["model"]]}}}
    normalized = core_catalog("normalize_settings", host="android", settings=settings, order=["local-litert-lm"], env={})
    local = normalized["settings"]["providers"]["local-litert-lm"]
    assert local["active"] and local["builtin"] and local["kind"] == case["kind"]
    assert local["base_url"] == case["url"] and not local["requires_api_key"]
    resolved = core_catalog("resolve_ref", **{"ref": case["reference"], "providers": normalized["settings"]["providers"]})
    assert (resolved["provider"], resolved["model"]) == ("local-litert-lm", "gemma-4-e2b")
    connection = core_catalog("connection", provider="local-litert-lm", settings=normalized["settings"])["connection"]
    assert (connection["kind"], connection["base_url"]) == (case["kind"], case["url"])
    updated = core_catalog("update_settings", host="android", settings=normalized["settings"],
                           order=normalized["order"], env={}, patch_order=["local-litert-lm"],
                           patch={"providers": {"local-litert-lm": {"delete": True}}})
    assert updated["settings"]["providers"]["local-litert-lm"]["active"] is True
