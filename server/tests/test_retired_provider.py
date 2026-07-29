"""A withdrawn provider has to be dropped on the way in, not just deleted.

Deleting a definition from PROVIDER_DEFINITIONS does not remove the provider from
an installation. An id the builtin list does not know is kept as though the
operator had added it by hand, and the metadata refresh MODEL_CONFIG_VERSION
triggers sits inside `if builtin`, so it never reaches it either. Both halves are
pinned here, because a test that only checks the catalog would pass while every
installed copy still offered ovms.

The other half of the arrangement -- that the retired ids still name the artworks
made on them -- is asserted in web/scripts/model-ref-check.mjs. The server has no
path that turns a model id into a label.
"""

from __future__ import annotations

import pytest

from inku_server.model_settings import (
    BUILTIN_PROVIDER_IDS,
    RETIRED_PROVIDER_IDS,
    connection_for,
    default_model_settings,
    normalize_model_settings,
    provider_for_model,
    split_model_ref,
)

_STORED_OVMS = {
    "id": "ovms",
    "label": "Intel OVMS",
    "kind": "openai_compatible",
    "base_url": "http://192.168.0.89:18000/v3",
    "active": True,
    "models": [
        {"id": "gemma3-4b-api", "label": "Google Gemma 3 4B Instruct"},
        {"id": "gemma3-12b-api", "label": "Google Gemma 3 12B Instruct"},
    ],
    "enabled_models": {"gemma3-4b-api": True, "gemma3-12b-api": True},
}


def test_a_retired_id_is_not_a_builtin_one():
    assert RETIRED_PROVIDER_IDS
    assert not (RETIRED_PROVIDER_IDS & BUILTIN_PROVIDER_IDS)
    assert "ovms" not in default_model_settings()["providers"]


@pytest.mark.parametrize(
    "stored_catalog_version",
    ["2.4.1", "2.2.0", ""],
    ids=["current", "older", "absent"],
)
def test_a_stored_retired_provider_is_dropped_whatever_version_wrote_it(stored_catalog_version):
    """The drop must not depend on MODEL_CONFIG_VERSION moving.

    pentala's stored copy said 2.2.0, and an installation that has already been
    re-read once would say the current version. Neither may keep ovms, so the
    version is varied here rather than assumed.
    """
    clean = normalize_model_settings(
        {
            "model_catalog_version": stored_catalog_version,
            "providers": {"ovms": dict(_STORED_OVMS)},
        }
    )
    assert "ovms" not in clean["providers"]


def test_the_drop_is_the_retired_id_and_not_every_unknown_one():
    """A provider the operator added by hand is not a withdrawn one."""
    clean = normalize_model_settings(
        {
            "providers": {
                "ovms": dict(_STORED_OVMS),
                "my-local": {
                    "kind": "openai_compatible",
                    "base_url": "http://127.0.0.1:9000/v1",
                    "models": [{"id": "my-model", "label": "My Model"}],
                },
            }
        }
    )
    assert "ovms" not in clean["providers"]
    assert clean["providers"]["my-local"]["builtin"] is False
    assert clean["providers"]["my-local"]["base_url"] == "http://127.0.0.1:9000/v1"


def test_asking_for_a_retired_provider_says_so():
    """Unknown means unknown. It used to mean "use ovms", which is how a typo
    reached a real endpoint and came back with a real-looking answer."""
    settings = default_model_settings()
    with pytest.raises(ValueError, match="unknown model provider: ovms"):
        connection_for("ovms", settings)
    with pytest.raises(ValueError, match="unknown model provider: no-such-provider"):
        connection_for("no-such-provider", settings)


def test_a_retired_reference_splits_but_does_not_resolve_to_a_connection():
    """Five artworks carry "ovms:gemma3-4b-api". Splitting it is what makes the
    withdrawal legible: the alternative is asking NVIDIA for a model whose name is
    "ovms:gemma3-4b-api"."""
    settings = default_model_settings()
    settings.update({"stage1_provider": "nvidia", "stage1_model": "google/gemma-4-31b-it"})
    assert split_model_ref("ovms:gemma3-4b-api", settings) == ("ovms", "gemma3-4b-api")
    assert provider_for_model("ovms:gemma3-4b-api", stage="stage1", settings=settings) == (
        "ovms",
        "gemma3-4b-api",
    )
    with pytest.raises(ValueError, match="unknown model provider: ovms"):
        connection_for("ovms", settings)


def test_a_bare_retired_model_is_not_routed_to_the_retired_provider():
    """Rule 2 reads live ownership only. The retired entry names, it does not route
    -- otherwise redrawing an old artwork would aim at a stopped endpoint."""
    settings = default_model_settings()
    settings.update({"stage1_provider": "nvidia", "stage1_model": "google/gemma-4-31b-it"})
    provider, model = provider_for_model("gemma3-4b-api", stage="stage1", settings=settings)
    assert (provider, model) == ("nvidia", "gemma3-4b-api")
