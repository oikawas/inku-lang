"""Endpoints for the public group, moved out of api.py unchanged."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from ...color_catalogs import RENAMED_COLOR_CATALOG_IDS, color_catalogs
from ...layer_versions import DDL_ENGINE_VERSION, DDL_VERSION
from ...languages import stage_prompts_for_lang
from ...plugins import DOCUMENT_PLUGIN_MANAGER, entries_with_fires_on
from ...plugins.document_format import preview_path_for_qualified_name
from ...reference import build_reference, render_markdown
from ...saijiki import display_categories
from ...render_engines import current_render_engine
from ...model_settings import connection_for, model_provider_catalog, provider_for_model
from ... import db as _db
from ..common import _APP_VERSION, _RELEASE_VERSION, _build_number, _env_flag, _normalize_instruction_lang, _normalize_ui_lang, _resolve_instruction_lang, _unexpected_http_error
from ..deps import _current_user
from ..models import ModelSettingsResponse


router = APIRouter()
authenticated_router = APIRouter(dependencies=[Depends(_current_user)])


class PromptsResponse(BaseModel):
    stage1_system: str
    stage2_system: str


class AppInfoResponse(BaseModel):
    name: str
    # The application version of the running tree, from web/APP_VERSION -- the
    # same value the UI shows. release_version is the tagged distribution and
    # lags on purpose while releases are on hold.
    version: str
    release_version: str
    build_number: str | None = None
    developer_mode: bool = False
    # Whether this server belongs to one person.  The client reads it to drop
    # the doors that lead nowhere when there is nobody else to be.
    single_user_mode: bool = False
    # Whether this server keeps the second thumbnail size. The client asks for
    # it only where both this is on and the screen is dense enough to use it;
    # asking otherwise would be a 404 per thumbnail.
    thumbnail_hidpi: bool = False
    render_engine_id: str
    render_engine_version: str
    ddl_version: str
    ddl_engine_version: str


class ColorCatalogsResponse(BaseModel):
    default_catalog_id: str
    catalogs: list[dict]
    # Old id -> the id it answers to today. A client holding a work saved
    # before a rename has no other way to name the catalog it was drawn with;
    # an id in neither `catalogs` nor here is retired.
    renamed_catalog_ids: dict[str, str]


class DemoInstructionBody(BaseModel):
    seed_phrase: str = Field(..., min_length=1, max_length=1000)
    model: str | None = Field(default=None)
    instruction_lang: str = Field(default="auto")
    ui_lang: str | None = None


class DemoInstructionResponse(BaseModel):
    instruction: str


@router.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@router.get("/api/info", response_model=AppInfoResponse)
def api_info() -> AppInfoResponse:
    engine = current_render_engine()
    return AppInfoResponse(
        name="inku-server",
        version=_APP_VERSION,
        release_version=_RELEASE_VERSION,
        build_number=_build_number(),
        developer_mode=_env_flag("INKU_DEVELOPER_MODE"),
        single_user_mode=_db.single_user_mode_enabled(),
        thumbnail_hidpi=bool(_db.get_thumbnail_settings()["hidpi"]),
        render_engine_id=engine.id,
        render_engine_version=engine.version,
        ddl_version=DDL_VERSION,
        ddl_engine_version=DDL_ENGINE_VERSION,
    )


@router.get("/api/color-catalogs", response_model=ColorCatalogsResponse)
def api_color_catalogs() -> ColorCatalogsResponse:
    return ColorCatalogsResponse(
        default_catalog_id="default",
        catalogs=color_catalogs(),
        renamed_catalog_ids=dict(RENAMED_COLOR_CATALOG_IDS),
    )


@router.get("/api/models", response_model=ModelSettingsResponse)
def api_models(actor: dict = Depends(_current_user)) -> ModelSettingsResponse:
    settings = _db.get_model_settings()
    developer_mode = _env_flag("INKU_DEVELOPER_MODE")
    return ModelSettingsResponse(
        catalog=model_provider_catalog(
            settings, include_disabled=False, include_developer=developer_mode, purpose="llm"
        ),
        llm_catalog=model_provider_catalog(
            settings, include_disabled=False, include_developer=developer_mode, purpose="llm"
        ),
        vision_catalog=model_provider_catalog(
            settings, include_disabled=False, include_developer=developer_mode, purpose="vision"
        ),
        settings={"model_settings": actor.get("model_settings") or {}},
    )


PLUGIN_PREVIEW_ROUTE = "/api/saijiki/plugin-preview"


def _preview_url(qualified_name: str, *, hidpi: bool) -> str:
    """Where the browser fetches this word's artwork.

    The name rides as a query parameter rather than in the path: a qualified
    name is `Namespace.Word` with the word in the document's own language, and
    a query value needs no decisions about what a path segment may hold.
    """
    query = urllib.parse.urlencode({"name": qualified_name, "scale": "2" if hidpi else "1"})
    return f"{PLUGIN_PREVIEW_ROUTE}?{query}"


def _enabled_plugin_entries() -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for item in DOCUMENT_PLUGIN_MANAGER.items():
        if item.status != "enabled":
            continue
        # This is the list the DDL editor holds, so it carries `fires_on_*`:
        # without it the editor can only say a qualified name is unknown, not
        # which plain word it would have fired.
        entries.extend(entries_with_fires_on(item.entries))
    # v2.14: the loader says whether a picture exists at each scale; the URL is
    # this layer's to write, since this layer owns the route. A word with no
    # picture carries "" and the panel falls back to the shared mark.
    for entry in entries:
        name = str(entry.get("qualified_name", ""))
        entry["preview_url"] = _preview_url(name, hidpi=False) if entry.get("has_preview") else ""
        entry["preview_url_2x"] = (
            _preview_url(name, hidpi=True) if entry.get("has_preview_hidpi") else ""
        )
    return entries


@authenticated_router.get("/api/saijiki")
def api_saijiki(
    lang: str = Query(default="ja", pattern="^(ja|en)$"),
) -> dict[str, object]:
    """Saijiki vocabulary for display: core categories (from the saijiki table)
    plus loaded declarative plugin words. Single delivery for web hydration."""
    return {
        "categories": display_categories(lang),
        "plugins": _enabled_plugin_entries(),
    }


@authenticated_router.get(PLUGIN_PREVIEW_ROUTE)
def api_plugin_preview(
    name: str = Query(min_length=1, max_length=200),
    scale: str = Query(default="1", pattern="^[12]$"),
) -> Response:
    """The artwork behind a plugin word in the saijiki preview.

    Served from its own route rather than inside the saijiki payload: the bake
    that prompted this came to 188 KB across seven words at 720px, which the
    browser fetches once and caches instead of carrying on every hydration.
    The lookup goes through the loaded documents, so a name that matches no
    word is a 404 whatever it spells.
    """
    path = preview_path_for_qualified_name(name, hidpi=(scale == "2"))
    if path is None:
        raise HTTPException(status_code=404, detail="no preview for that word")
    # Immutable for a day: a picture changes only when its plugin document is
    # replaced, and the panel asks for it on every hover.
    return FileResponse(
        path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"}
    )


@authenticated_router.get("/api/reference")
def api_reference(
    format: str = Query(default="json", pattern="^(json|md)$"),
) -> Response:
    """Machine-generated mirror of implementation tables (read-only)."""
    reference = build_reference()
    if format == "md":
        return Response(content=render_markdown(reference), media_type="text/markdown")
    return JSONResponse(content=reference)


@authenticated_router.get("/api/client-config")
def api_client_config() -> dict[str, object]:
    """Server-owned values every client needs. Editable by admins only."""
    return {"render_fanout_limit": int(_db.get_render_concurrency_settings()["client_limit"])}


@router.get("/api/prompts", response_model=PromptsResponse)
def api_prompts(lang: str = Query(default="ja")) -> PromptsResponse:
    try:
        requested_lang = _normalize_instruction_lang(lang)
        s1, s2 = stage_prompts_for_lang("ja" if requested_lang == "auto" else requested_lang)
    except (HTTPException, ValueError):
        s1, s2 = stage_prompts_for_lang("ja")
    return PromptsResponse(stage1_system=s1, stage2_system=s2)


def _demo_instruction_system(lang: str) -> str:
    if lang == "en":
        return (
            "Generate one short, concrete visual prompt for inku. "
            "Return only the prompt text. Keep it under 40 words. "
            "Use sensory detail and a clear scene, but do not explain."
        )
    return (
        "inkuのデモ描画に使う短い指示文を1つ生成してください。"
        "返答は指示文のみ。40語以内。"
        "情景、質感、動きが感じられる具体的な文章にし、説明は不要です。"
    )


def _generate_demo_instruction(seed_phrase: str, *, model: str | None, lang: str) -> str:
    # No env fallback and no literal: both named ovms models, so an unconfigured
    # demo asked a withdrawn provider for its instruction. provider_for_model
    # reads the Stage 1 default when the model is None, which is the same answer
    # every other caller gets.
    settings = _db.get_model_settings()
    provider, model_id = provider_for_model(model or None, stage="stage1", settings=settings)
    if provider == "anthropic":
        import anthropic

        connection = connection_for("anthropic", settings)
        kwargs = {"api_key": connection["api_key"]} if connection.get("api_key") else {}
        if connection.get("base_url"):
            kwargs["base_url"] = connection["base_url"]
        client = anthropic.Anthropic(**kwargs)
        resp = client.messages.create(
            model=model_id,
            max_tokens=180,
            temperature=0.9,
            system=_demo_instruction_system(lang),
            messages=[{"role": "user", "content": seed_phrase}],
        )
        parts = [getattr(block, "text", "") for block in resp.content if getattr(block, "type", "") == "text"]
        text = "\n".join(parts).strip()
    elif provider == "gemini":
        connection = connection_for("gemini", settings)
        api_key = connection.get("api_key") or ""
        if not api_key:
            raise RuntimeError("Gemini API key is not configured")
        base_url = str(connection.get("base_url") or "https://generativelanguage.googleapis.com").rstrip("/")
        url = f"{base_url}/v1beta/models/{model_id}:generateContent?key={api_key}"
        body = {
            "systemInstruction": {"parts": [{"text": _demo_instruction_system(lang)}]},
            "contents": [{"role": "user", "parts": [{"text": seed_phrase}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 180},
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=float(os.getenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "120"))) as response:
            payload = json.loads(response.read().decode("utf-8"))
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "\n".join(str(part.get("text", "")) for part in parts).strip()
    else:
        from openai import OpenAI

        connection = connection_for(provider, settings)
        client = OpenAI(base_url=connection["base_url"], api_key=connection.get("api_key") or "none")
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": _demo_instruction_system(lang)},
                {"role": "user", "content": seed_phrase},
            ],
            temperature=0.9,
            max_tokens=180,
        )
        text = (resp.choices[0].message.content or "").strip()
    text = text.strip().strip("\"'“”‘’")
    if not text:
        raise ValueError("empty demo instruction")
    return text


@authenticated_router.post("/api/demo/instruction", response_model=DemoInstructionResponse)
def api_demo_instruction(req: DemoInstructionBody) -> DemoInstructionResponse:
    instruction_lang = _resolve_instruction_lang(
        req.seed_phrase,
        _normalize_instruction_lang(req.instruction_lang),
        ui_lang=_normalize_ui_lang(req.ui_lang),
    )
    try:
        instruction = _generate_demo_instruction(req.seed_phrase, model=req.model, lang=instruction_lang)
    except Exception as e:  # noqa: BLE001
        raise _unexpected_http_error("demo instruction", 502) from e
    return DemoInstructionResponse(instruction=instruction)
