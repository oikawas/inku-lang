"""Labels and folds of the model catalog (inku.model-catalog.v2; the author, 2026-10-13).

A model carries labels. The catalog's label table names each one in Japanese and English, in
order, and says whether a model carrying it can be published. A model is filed in the fold of
whichever of its labels comes last in that table, and can be published only when every one of
its labels allows it; a model with no label stays in the list.

Where the labels come from:
- written in the catalog: older model, paid plan only (what the free plan cannot call), not
  supported, end of life;
- corrected by an installation for its own key: paid plan only (its key's probe) and end of life
  (a refetched list that no longer offers the model);
- worked out from the model: no response (it has no purpose left) and not measured (it carries
  no measurement, and nothing else keeps it from being published).

The same rules are written down as cases in server/tests/data/model-catalog-cases.json, which
the Web, macOS and Android check themselves against, so that a model is filed the same way
everywhere and a new label needs only a new row in the table.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .verified_model_catalog import MODEL_CATALOG, STORED_LABEL_KEYS, internal_model

MODEL_LABELS: list[dict[str, Any]] = MODEL_CATALOG["labels"]
_ORDER = {label["id"]: index for index, label in enumerate(MODEL_LABELS)}
_PUBLISHABLE = {label["id"]: bool(label["publishable"]) for label in MODEL_LABELS}

# Any of these says the model was measured: a level, a measured number, a comment written from a
# measurement, or a purpose it was measured not to answer.
MEASUREMENT_KEYS = (
    "recommendation_llm", "recommendation_vision", "recommendation_stage1", "recommendation_stage2",
    "recommendation_level", "speed_class", "speed_label", "speed_llm_seconds", "speed_vision_seconds",
    "cost_usd_llm", "cost_usd_vision", "comment_ja", "comment_en", "unsupported_purposes",
)
_RECORD_KEYS = {"id", "label", "notes", "purposes", "labels", "eol_date", *MEASUREMENT_KEYS}


def catalog_models(provider_id: str) -> dict[str, dict[str, Any]]:
    """The catalog's entries for one provider in the Server's form, by model id."""
    provider = MODEL_CATALOG["providers"].get(provider_id) or {"models": []}
    return {record["id"]: internal_model(deepcopy(record)) for record in provider["models"]}


def model_labels(model: dict[str, Any]) -> list[str]:
    """Every label of a model in the Server's form, in the table's order."""
    labels = {label for label, key in STORED_LABEL_KEYS.items() if model.get(key) is True}
    # Measured to answer no purpose it is offered for: a purpose an administrator
    # chose against the measurement (2026-10-26) does not make it answer.
    unsupported = model.get("unsupported_purposes") or []
    if not [purpose for purpose in model.get("purposes", ["llm"]) if purpose not in unsupported]:
        labels.add("no_response")
    if not any(key in model for key in MEASUREMENT_KEYS) and all(_PUBLISHABLE[label] for label in labels):
        labels.add("unmeasured")
    return sorted(labels, key=_ORDER.__getitem__)


def model_fold(labels: list[str]) -> str | None:
    return max(labels, key=_ORDER.__getitem__) if labels else None


def labelled(model: dict[str, Any]) -> dict[str, Any]:
    """The model with its labels and fold, as every model list hands it out."""
    labels = model_labels(model)
    return {**model, "labels": labels, "fold": model_fold(labels)}


def catalog_problems(catalog: dict[str, Any] = MODEL_CATALOG) -> list[str]:
    """What is wrong with a catalog, or an empty list."""
    problems = []
    if catalog.get("schema") != "inku.model-catalog.v2":
        problems.append(f"schema {catalog.get('schema')!r}")
    ids = [label.get("id") for label in catalog.get("labels", [])]
    if len(ids) != len(set(ids)) or not all(isinstance(label.get("publishable"), bool)
                                            and label.get("ja") and label.get("en") for label in catalog.get("labels", [])):
        problems.append("label table")
    for label in STORED_LABEL_KEYS:
        if label not in ids:
            problems.append(f"stored label {label} missing from the table")
    for provider_id, provider in catalog.get("providers", {}).items():
        records = provider.get("models", [])
        record_ids = [record.get("id") for record in records]
        if len(record_ids) != len(set(record_ids)) or not all(isinstance(i, str) and i for i in record_ids):
            problems.append(f"{provider_id}: model ids")
        for model_id in provider.get("defaults", []):
            if model_id not in record_ids:
                problems.append(f"{provider_id}: default {model_id} has no entry")
        for record in records:
            unknown = set(record) - _RECORD_KEYS
            if unknown:
                problems.append(f"{provider_id}/{record.get('id')}: unknown keys {sorted(unknown)}")
            for label in record.get("labels", []):
                if label not in STORED_LABEL_KEYS:
                    problems.append(f"{provider_id}/{record.get('id')}: label {label} is not written in the catalog")
            for key in ("purposes", "unsupported_purposes"):
                if key in record and not set(record[key]) <= {"llm", "vision"}:
                    problems.append(f"{provider_id}/{record.get('id')}: {key}")
    return problems
