"""The account text-size setting remains a valid step when user settings merge."""

from inku_server.model_settings import (
    default_user_model_settings,
    normalize_user_model_settings,
    update_user_model_settings,
)


def test_user_text_size_defaults_normalizes_and_merges() -> None:
    assert default_user_model_settings()["ui_text_size"] == 1
    assert normalize_user_model_settings({})["ui_text_size"] == 1
    assert normalize_user_model_settings({"ui_text_size": 4})["ui_text_size"] == 4
    assert normalize_user_model_settings({"ui_text_size": 5})["ui_text_size"] == 1
    assert normalize_user_model_settings({"ui_text_size": True})["ui_text_size"] == 1

    merged = update_user_model_settings({"ui_text_size": 4, "color_catalog_id": "auto"}, {"ui_text_size": 0})
    assert merged["ui_text_size"] == 0
    assert merged["color_catalog_id"] == "auto"
