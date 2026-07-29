"""Ollama Cloud の一覧は、無料枠で叩けないモデルを選べない印つきで残す。

2026-07-29 に 18 本すべてへ 14 トークンの要求を投げたところ、10 本が
HTTP 403 "this model requires a subscription" を返した。一覧から消すのではなく
印を付けて残すのは作者裁定 (2026-07-29)。消すと存在が見えなくなり、契約が変わった
日に戻す作業が要る。**選べるまま残すと、利用者は描こうとしてエラーで初めて知る。**

この印は `eol` と同じ「選べない」だが理由が違うので、別の鍵にしてある。
"""

from __future__ import annotations

from inku_server.model_settings import (
    PROVIDER_DEFINITIONS,
    default_model_settings,
    normalize_model_settings,
)
from inku_server.verified_model_catalog import (
    MODEL_CONFIG_VERSION,
    VERIFIED_OLLAMA_CLOUD_MODELS,
)

_BY_ID = {str(provider["id"]): provider for provider in PROVIDER_DEFINITIONS}

# 2026-07-29 実測。`cli/out2/766-v2.9.7-ollama-cloud-bench/probe.json` が生ログ。
SUBSCRIPTION_ONLY = {
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "glm-5.1",
    "glm-5.2",
    "kimi-k2.5",
    "kimi-k2.6",
    "kimi-k2.7-code",
    "minimax-m2.7",
    "mistral-large-3:675b",
    "qwen3.5:397b",
}
FREE_TIER_REACHABLE = {
    "gemma4:31b",
    "gpt-oss:20b",
    "gpt-oss:120b",
    "minimax-m2.5",
    "minimax-m3",
    "nemotron-3-nano:30b",
    "nemotron-3-super",
    "nemotron-3-ultra",
}


def _by_id() -> dict[str, dict]:
    return {str(model["id"]): model for model in VERIFIED_OLLAMA_CLOUD_MODELS}


def test_the_measured_split_covers_the_whole_list() -> None:
    """18 本は「叩ける 8」と「有料 10」に尽きる。片方に足すともう片方が減る。"""
    shipped = set(_by_id())
    assert shipped == SUBSCRIPTION_ONLY | FREE_TIER_REACHABLE
    assert not (SUBSCRIPTION_ONLY & FREE_TIER_REACHABLE)
    assert len(shipped) == 18


def test_every_paid_model_is_marked_and_no_free_one_is() -> None:
    models = _by_id()
    marked = {model_id for model_id, model in models.items() if model.get("requires_subscription")}
    assert marked == SUBSCRIPTION_ONLY


def test_the_paid_models_say_why_in_both_languages() -> None:
    """印だけでは読み手に理由が届かない。ツールチップの本文が唯一の説明。"""
    for model_id in SUBSCRIPTION_ONLY:
        model = _by_id()[model_id]
        assert "403" in str(model["comment_ja"]), model_id
        assert "有料プラン" in str(model["comment_ja"]), model_id
        assert "403" in str(model["comment_en"]), model_id
        assert "paid plan" in str(model["comment_en"]).lower(), model_id


def test_paid_models_carry_no_recommendation() -> None:
    """叩けないものに推奨度は付けられない。SCORING-DESIGN §3-1 の「掲載しない」相当。"""
    for model_id in SUBSCRIPTION_ONLY:
        model = _by_id()[model_id]
        assert model.get("recommendation_llm") is None, model_id
        assert model.get("recommendation_level") is None, model_id


def test_the_provider_definition_carries_the_flag_through() -> None:
    """カタログに書いても provider 定義を通らなければ UI へ届かない。"""
    models = {str(model["id"]): model for model in _BY_ID["ollama-cloud"]["models"]}
    assert {m for m, v in models.items() if v.get("requires_subscription")} == SUBSCRIPTION_ONLY


def test_the_default_settings_surface_the_flag() -> None:
    provider = default_model_settings()["providers"]["ollama-cloud"]
    marked = {str(m["id"]) for m in provider["models"] if m.get("requires_subscription")}
    assert marked == SUBSCRIPTION_ONLY


def test_a_stored_catalog_keeps_the_flag() -> None:
    """保存済み設定は provider の models を丸ごと置き換える。印が落ちれば選べてしまう。"""
    stored = {
        "model_catalog_version": MODEL_CONFIG_VERSION,
        "providers": {
            "ollama-cloud": {
                "id": "ollama-cloud",
                "models": [
                    {"id": "glm-5.2", "label": "glm-5.2", "purposes": ["llm"], "requires_subscription": True},
                    {"id": "gemma4:31b", "label": "gemma4:31b", "purposes": ["llm"]},
                ],
            }
        },
    }
    provider = normalize_model_settings(stored)["providers"]["ollama-cloud"]
    models = {str(m["id"]): m for m in provider["models"]}
    assert models["glm-5.2"].get("requires_subscription") is True
    assert models["gemma4:31b"].get("requires_subscription") is None


def test_a_bare_stored_entry_still_inherits_the_flag() -> None:
    """取得ボタンが作り直した一覧 (id と label だけ) でも印は残る。

    印は `metadata_keys` の貼り直しには乗っていない。乗せる必要が無いからで、
    統合が `{**builtin, **stored}` と組み込みを土台にしており、保存済みが
    この鍵を持たないかぎり組み込みの値がそのまま残る。**逆に、保存済みが
    True を持ったまま組み込みから印が消えた場合は貼り直しでも直らない** —
    その日は版を上げるのではなく、保存済みを migration で洗う必要がある。
    """
    stored = {
        "model_catalog_version": "0.0.1",  # 現行と違えば貼り直しが走る
        "providers": {
            "ollama-cloud": {
                "id": "ollama-cloud",
                "models": [{"id": "glm-5.2", "label": "glm-5.2", "purposes": ["llm"]}],
            }
        },
    }
    provider = normalize_model_settings(stored)["providers"]["ollama-cloud"]
    models = {str(m["id"]): m for m in provider["models"]}
    assert models["glm-5.2"].get("requires_subscription") is True
