"""Helpers shared by more than one router group: language, build and model naming."""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
from fastapi import HTTPException
from ..okugaki import DEFAULT_MODEL as DEFAULT_OKUGAKI_MODEL
from ..languages import SUPPORTED_INSTRUCTION_LANGS, normalize_instruction_lang, resolve_instruction_lang
from ..model_settings import model_is_offered, provider_for_model, split_model_ref
from .. import db as _db
from .deps import _logger


def _app_version() -> str:
    """Read the application version from web/APP_VERSION, the single source.

    The same file feeds the UI (through the vite define) and the CLI, so the
    version shown on screen and the version reported by /api/info cannot drift.
    This is the development version of the running tree; the released
    distribution version is a different thing and lives in _release_version.
    """
    # Same depth as _build_number: api_core/common.py -> inku_server -> src ->
    # server -> repository root.
    path = Path(__file__).resolve().parents[4] / "web" / "APP_VERSION"
    try:
        return path.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


def _release_version() -> str:
    """Report the installed distribution version, which pyproject.toml owns.

    This moves only when a release is tagged, so it lags the application version
    on purpose while releases are on hold.
    """
    try:
        return importlib.metadata.version("inku-server")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+unknown"


_APP_VERSION = _app_version()
_RELEASE_VERSION = _release_version()


def _unexpected_http_error(operation: str, status_code: int) -> HTTPException:
    _logger.exception("%s failed", operation)
    detail = f"{operation} failed"
    if os.getenv("INKU_ENV") == "development":
        import sys
        import traceback
        exc_type, exc_value, _ = sys.exc_info()
        if exc_value:
            detail = f"{operation} failed: {exc_type.__name__}: {exc_value}\n{traceback.format_exc()}"
    return HTTPException(status_code=status_code, detail=detail)


def _normalize_instruction_lang(value: str | None, *, default: str = "ja") -> str:
    try:
        return normalize_instruction_lang(value, default=default)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unsupported instruction language: {value}")


def _resolve_instruction_lang(text: str, requested: str, *, ui_lang: str | None = None) -> str:
    fallback = ui_lang if ui_lang in SUPPORTED_INSTRUCTION_LANGS else "ja"
    return resolve_instruction_lang(text, requested, fallback=fallback)


def _normalize_ui_lang(value: str | None) -> str | None:
    lang = (value or "").strip().lower()
    if not lang:
        return None
    return lang[:32]


def _build_number() -> str | None:
    # One level deeper than api.py: api_core/common.py -> inku_server -> src ->
    # server -> repository root.
    path = Path(__file__).resolve().parents[4] / "web" / "BUILD_NUMBER"
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _is_qualified_model_id(model: str) -> bool:
    provider, _ = split_model_ref(model, _db.get_model_settings())
    return provider is not None


def _resolved_vision_model(model: str | None, actor: dict | None = None) -> str:
    settings = (actor or {}).get("model_settings") or {}
    provider = str(settings.get("vision_provider", "nvidia") or "nvidia")
    model_id = str(settings.get("vision_model", DEFAULT_OKUGAKI_MODEL) or DEFAULT_OKUGAKI_MODEL)
    if model:
        requested = str(model).strip()
        if _is_qualified_model_id(requested):
            return requested
        if requested == model_id:
            return f"{provider}:{requested}"
        return requested
    return model_id if _is_qualified_model_id(model_id) else f"{provider}:{model_id}"


def _model_metadata(*, stage1_model: str | None = None, stage2_model: str | None = None) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if stage1_model:
        metadata["stage1_model"] = stage1_model
    if stage2_model:
        metadata["stage2_model"] = stage2_model
    return metadata


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# What every route that calls a model answers when the model is withheld; the
# Web says it in the page's language.
MODEL_NOT_OFFERED_DETAIL = "model is not offered on this server"


def _model_offered_to(actor: dict | None, model_ref: str | None, *, stage: str, purpose: str, settings: dict) -> bool:
    """Whether the server will call this model with its own credentials for `actor`.

    Administrators may name any configured model: they choose what to offer
    and try a model before offering it. Everyone else gets the models an
    active provider lists and the administrator has left switched on. Switching
    a model off used to take it out of the menus only, so a request that named
    it -- or named a model no provider lists -- still reached the provider, on
    the server's account.
    """
    if actor is not None and _db.has_permission_group(actor, "admins"):
        return True
    provider_id, model_id = provider_for_model(model_ref or None, stage=stage, settings=settings)
    return model_is_offered(provider_id, model_id, settings, purpose=purpose)
