"""Python access to the core model catalog's labels and picker decisions."""

from copy import deepcopy
from typing import Any

from .verified_model_catalog import MODEL_CATALOG, catalog_info, core_catalog, internal_model

MODEL_LABELS: list[dict[str, Any]] = MODEL_CATALOG["labels"]
MEASUREMENT_KEYS = tuple(catalog_info()["measurement_keys"])
ASSESSMENT_KEYS = tuple(catalog_info()["assessment_keys"])


def catalog_models(provider_id: str) -> dict[str, dict[str, Any]]:
    provider = MODEL_CATALOG["providers"].get(provider_id) or {"models": []}
    return {record["id"]: internal_model(deepcopy(record)) for record in provider["models"]}


def model_labels(model: dict[str, Any]) -> list[str]:
    return core_catalog("label", model=model)["model"]["labels"]


def model_fold(labels: list[str]) -> str | None:
    return core_catalog("fold", labels=labels)["fold"]


def labelled(model: dict[str, Any]) -> dict[str, Any]:
    return core_catalog("label", model=model)["model"]


def catalog_problems(catalog: dict[str, Any] = MODEL_CATALOG) -> list[str]:
    return core_catalog("problems", catalog=catalog)["problems"]
