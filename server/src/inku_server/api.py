"""FastAPI endpoints for inku-server.

POST /api/compose : 正規化DDL (or 生入力) → JSON Score + SVG
GET  /health      : liveness
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore, Lock

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .coerce import coerce_score, ensure_renderable_score
from .composer import compose
from .composer import SYSTEM_PROMPT as STAGE2_PROMPT
from .composer import SYSTEM_PROMPT_EN as STAGE2_PROMPT_EN
from .ddl_expander import expand_intermediate_ddl
from .interpreter import _sanitize_placement_words, interpret_detail
from .interpreter import SYSTEM_PROMPT as STAGE1_PROMPT
from .interpreter import SYSTEM_PROMPT_EN as STAGE1_PROMPT_EN
from .renderer import render
from .schema import Score
from . import db as _db

app = FastAPI(title="inku-server", version="0.1.0")

_db.init_db()

# ── 出力ファイル保存 ────────────────────────────────────────────────────────────
# DB の履歴レコードを正本とし、ここで作る SVG/JSON/PNG 等は再生成可能な副産物として扱う。
_DEFAULT_OUTPUT_DIR = Path.home() / ".local" / "share" / "inku" / "outputs"
_OUTPUT_DIR = Path(os.getenv("INKU_OUTPUT_DIR", str(_DEFAULT_OUTPUT_DIR)))
_OUTPUT_PNG_SIZE = int(os.getenv("INKU_OUTPUT_PNG_SIZE", "2160"))
_SAVE_WORKERS = max(1, int(os.getenv("INKU_OUTPUT_SAVE_WORKERS", "2")))
_SAVE_QUEUE_LIMIT = max(_SAVE_WORKERS, int(os.getenv("INKU_OUTPUT_SAVE_QUEUE_LIMIT", "32")))
_save_executor = ThreadPoolExecutor(max_workers=_SAVE_WORKERS, thread_name_prefix="inku-save")
_save_slots = BoundedSemaphore(_SAVE_QUEUE_LIMIT)
_save_stats_lock = Lock()
_save_stats = {
    "submitted": 0,
    "completed": 0,
    "failed": 0,
    "skipped": 0,
}
_logger = logging.getLogger(__name__)
_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
_SESSION_COOKIE_NAME = "inku_session"
_SESSION_COOKIE_MAX_AGE = int(os.getenv("INKU_SESSION_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30)))
_SESSION_COOKIE_SECURE = os.getenv("INKU_SESSION_COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes"}


def _output_prefix(user_id: str, item_id: str, at_ms: int) -> Path:
    dt = datetime.fromtimestamp(at_ms / 1000, tz=timezone.utc).astimezone()
    date_dir = _OUTPUT_DIR / user_id / dt.strftime("%Y-%m-%d")
    return date_dir / (dt.strftime("%Y%m%d_%H%M%S") + "_" + item_id[:8])


def _save_output_files(prefix: Path, input_text: str, ddl: str | None, score: dict, svg: str) -> None:
    try:
        prefix.parent.mkdir(parents=True, exist_ok=True)
        if input_text:
            Path(f"{prefix}_instruction.txt").write_text(input_text, encoding="utf-8")
        if ddl:
            Path(f"{prefix}_normalized.ddl").write_text(ddl, encoding="utf-8")
        Path(f"{prefix}_score.json").write_text(
            json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        svg_bytes = svg.encode("utf-8")
        Path(f"{prefix}_output.svg").write_bytes(svg_bytes)
    except Exception:
        _logger.exception("failed to save output files: prefix=%s", prefix)
        return

    try:
        import cairosvg  # lazy import — optional dependency
    except ImportError:
        _logger.warning("cairosvg is not installed; skipped PNG output: prefix=%s", prefix)
        return

    try:
        png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=_OUTPUT_PNG_SIZE)
        Path(f"{prefix}_output.png").write_bytes(png_bytes)
    except Exception:
        _logger.exception("failed to save PNG output: prefix=%s", prefix)


def _history_output_prefix(item: dict) -> Path:
    output_path = item.get("output_path")
    if output_path:
        return Path(output_path)
    return _output_prefix(item["user_id"], item["id"], item["at"])


def _save_history_artifacts(item: dict) -> None:
    _save_output_files(
        _history_output_prefix(item),
        item.get("input", ""),
        item.get("ddl"),
        item.get("score", {}),
        item.get("svg", ""),
    )


def _increment_save_stat(name: str) -> None:
    with _save_stats_lock:
        _save_stats[name] = _save_stats.get(name, 0) + 1


def _artifact_save_stats() -> dict[str, int]:
    with _save_stats_lock:
        return dict(_save_stats)


def _run_history_artifact_save(item: dict) -> None:
    try:
        _save_history_artifacts(item)
        _increment_save_stat("completed")
    except Exception:
        _increment_save_stat("failed")
        _logger.exception("unexpected artifact save failure: history_id=%s", item.get("id"))
    finally:
        _save_slots.release()


def _submit_history_artifact_save(item: dict) -> bool:
    if not _save_slots.acquire(blocking=False):
        _increment_save_stat("skipped")
        _logger.warning(
            "artifact save queue is full; skipped background save: history_id=%s queue_limit=%s",
            item.get("id"),
            _SAVE_QUEUE_LIMIT,
        )
        return False
    _increment_save_stat("submitted")
    try:
        _save_executor.submit(_run_history_artifact_save, item)
    except Exception:
        _increment_save_stat("failed")
        _save_slots.release()
        _logger.exception("failed to submit artifact save job: history_id=%s", item.get("id"))
        return False
    return True


def _validated_color_map(color_map: dict[str, str] | None) -> dict[str, str] | None:
    if color_map is None:
        return None
    clean: dict[str, str] = {}
    for key, value in color_map.items():
        if not isinstance(key, str) or not isinstance(value, str) or not _HEX_COLOR_RE.fullmatch(value):
            raise HTTPException(status_code=422, detail="color_map values must be #RRGGBB hex colors")
        clean[key] = value
    return clean


app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ComposeRequest(BaseModel):
    ddl: str = Field(..., min_length=1, description="正規化DDL テキスト")
    model: str | None = Field(
        default=None, description="Stage 2 モデル名 (未指定時は OPENAI_MODEL 既定)"
    )
    original_text: str | None = Field(default=None, description="元のユーザー記述 (省略可)")
    lang: str = Field(default="ja", description="言語コード (ja / en)")
    color_map: dict[str, str] | None = Field(default=None, description="色カタログ (white/black/blue/red/green/gray → hex)")


class ComposeResponse(BaseModel):
    score: Score
    svg: str
    elapsed_ms: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None


class InterpretRequest(BaseModel):
    text: str = Field(..., min_length=1, description="自由な自然言語の記述")
    model: str | None = Field(
        default=None, description="Stage 1 モデル名 (未指定時は OPENAI_MODEL_STAGE1 既定)"
    )
    include_thinking: bool = Field(
        default=False, description="qwen3 の <think> 内容を別フィールドで返すか"
    )
    lang: str = Field(default="ja", description="言語コード (ja / en)")


class InterpretResponse(BaseModel):
    ddl: str
    thinking: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


class PaintRequest(BaseModel):
    text: str = Field(..., min_length=1, description="自由な自然言語の記述")
    original_text: str | None = Field(default=None, description="元のユーザー記述")
    stage1_model: str | None = Field(default=None, description="Stage 1 モデル名")
    stage2_model: str | None = Field(default=None, description="Stage 2 モデル名")
    include_thinking: bool = Field(default=False, description="Stage 1 の思考を返すか")
    lang: str = Field(default="ja", description="言語コード (ja / en)")
    color_map: dict[str, str] | None = Field(default=None, description="色カタログ")
    save_history: bool = Field(default=False, description="描画結果を履歴に保存するか")
    save_artifacts: bool | None = Field(default=None, description="SVG/JSON/PNG などの副産物ファイルを保存するか")
    history_input: str | None = Field(default=None, description="履歴に表示するユーザー記述")
    history_at: int | None = Field(default=None, description="履歴保存時刻")
    catalog_id: str | None = Field(default=None, description="使用した色カタログID")


class PaintResponse(BaseModel):
    text: str
    ddl: str
    thinking: str | None = None
    score: Score
    svg: str
    history_id: str | None = None
    history_at: int | None = None
    elapsed_stage1_ms: int = 0
    elapsed_stage2_ms: int = 0
    elapsed_total_ms: int = 0
    tokens_in_stage1: int | None = None
    tokens_out_stage1: int | None = None
    tokens_in_stage2: int | None = None
    tokens_out_stage2: int | None = None


class PromptsResponse(BaseModel):
    stage1_system: str
    stage2_system: str


class HistoryPostBody(BaseModel):
    input: str
    ddl: str | None = None
    score: dict
    svg: str = ""
    at: int
    elapsed_ms: int = 0
    stage1_model: str | None = None
    stage2_model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    catalog_id: str | None = None
    save_artifacts: bool = True
    color_map: dict[str, str] | None = Field(default=None, exclude=True)


class HistoryItem(HistoryPostBody):
    id: str
    output_path: str | None = None
    trashed: bool = False
    starred: bool = False


class HistoryListResponse(BaseModel):
    items: list[HistoryItem]
    total: int
    offset: int
    limit: int


class HistoryIdsBody(BaseModel):
    ids: list[str] = Field(default_factory=list)


class HistoryStarBody(BaseModel):
    starred: bool = False


class UserGroupItem(BaseModel):
    id: str
    name: str
    at: int


class UserGroupCreateBody(BaseModel):
    name: str = Field(..., min_length=1, description="ユーザーグループ名")


class UserAccountItem(BaseModel):
    id: str
    username: str
    email: str
    role: str
    role_label: str
    group_id: str | None = None
    group_name: str | None = None
    ui_theme: str = "light"
    at: int


class UserAccountCreateBody(BaseModel):
    username: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)
    role: str = Field(default="user")
    group_id: str | None = None


class UserAccountUpdateBody(BaseModel):
    username: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=1)
    password: str | None = Field(default=None, min_length=8)
    role: str | None = None
    group_id: str | None = None


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    user: UserAccountItem


class UserSettingsBody(BaseModel):
    ui_theme: str = Field(default="light")


class BatchPromptHistoryBody(BaseModel):
    items: list[str] = Field(default_factory=list)


class BatchPromptHistoryResponse(BaseModel):
    items: list[str] = Field(default_factory=list)


class DemoSettingsBody(BaseModel):
    save_db: bool = False
    save_files: bool = False
    prompt_model: str = Field(default="google/gemma-4-31b-it", min_length=1)
    seed_phrase: str = Field(default="日本の四季を感じさせる文章を40語以内で生成", min_length=1, max_length=1000)
    interval_seconds: int = Field(default=30, ge=1, le=3600)


class DemoInstructionBody(BaseModel):
    seed_phrase: str = Field(..., min_length=1, max_length=1000)
    model: str | None = Field(default=None)
    lang: str = Field(default="ja")


class DemoInstructionResponse(BaseModel):
    instruction: str


class DatabaseSettingsStatus(BaseModel):
    backend: str
    driver: str
    url: str
    database: str | None = None
    is_default: bool
    runtime_editable: bool = False
    note: str


class PluginSettingsStatus(BaseModel):
    enabled: bool = False
    loaded: list[dict[str, str]] = Field(default_factory=list)
    runtime_editable: bool = False
    note: str


class OutputSaveStatus(BaseModel):
    workers: int
    queue_limit: int
    submitted: int
    completed: int
    failed: int
    skipped: int
    note: str


class SettingsStatusResponse(BaseModel):
    database: DatabaseSettingsStatus
    plugins: PluginSettingsStatus
    output_save: OutputSaveStatus


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        _SESSION_COOKIE_NAME,
        token,
        max_age=_SESSION_COOKIE_MAX_AGE,
        httponly=True,
        secure=_SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(_SESSION_COOKIE_NAME, path="/", samesite="lax")


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _session_token(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=_SESSION_COOKIE_NAME),
) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    if session_cookie:
        return session_cookie
    raise HTTPException(status_code=401, detail="authentication required")


def _bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="authentication required")
    return authorization.removeprefix("Bearer ").strip()


def _current_user(token: str = Depends(_session_token)) -> dict:
    user = _db.get_session_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


def _user_manager(actor: dict = Depends(_current_user)) -> dict:
    if actor["role"] not in {"admin", "group_lead"}:
        raise HTTPException(status_code=403, detail="user management is not permitted")
    return actor


def _admin_user(actor: dict = Depends(_current_user)) -> dict:
    if actor["role"] != "admin":
        raise HTTPException(status_code=403, detail="administrator permission is required")
    return actor


def _can_manage_user(actor: dict, target: dict) -> bool:
    if actor["role"] == "admin":
        return True
    return (
        actor["role"] == "group_lead"
        and actor.get("group_id")
        and target.get("group_id") == actor.get("group_id")
        and target.get("role") == "user"
    )


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/auth/login", response_model=LoginResponse)
def api_auth_login(body: LoginBody, response: Response) -> LoginResponse:
    user = _db.authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid username or password")
    token = _db.create_session(user["id"])
    _set_session_cookie(response, token)
    return LoginResponse(user=UserAccountItem(**user))


@app.get("/api/auth/me", response_model=UserAccountItem)
def api_auth_me(actor: dict = Depends(_current_user)) -> UserAccountItem:
    return UserAccountItem(**actor)


@app.patch("/api/auth/me/settings", response_model=UserAccountItem)
def api_auth_me_settings(body: UserSettingsBody, actor: dict = Depends(_current_user)) -> UserAccountItem:
    try:
        user = _db.update_user_theme(actor["id"], body.ui_theme)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@app.get("/api/auth/me/batch-prompt-history", response_model=BatchPromptHistoryResponse)
def api_auth_me_batch_prompt_history(actor: dict = Depends(_current_user)) -> BatchPromptHistoryResponse:
    return BatchPromptHistoryResponse(items=_db.get_user_batch_prompt_history(actor["id"]))


@app.put("/api/auth/me/batch-prompt-history", response_model=BatchPromptHistoryResponse)
def api_auth_me_update_batch_prompt_history(
    body: BatchPromptHistoryBody,
    actor: dict = Depends(_current_user),
) -> BatchPromptHistoryResponse:
    try:
        items = _db.update_user_batch_prompt_history(actor["id"], body.items)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if items is None:
        raise HTTPException(status_code=404, detail="user not found")
    return BatchPromptHistoryResponse(items=items)


@app.get("/api/auth/me/demo-settings", response_model=DemoSettingsBody)
def api_auth_me_demo_settings(actor: dict = Depends(_current_user)) -> DemoSettingsBody:
    return DemoSettingsBody(**_db.get_user_demo_settings(actor["id"]))


@app.put("/api/auth/me/demo-settings", response_model=DemoSettingsBody)
def api_auth_me_update_demo_settings(
    body: DemoSettingsBody,
    actor: dict = Depends(_current_user),
) -> DemoSettingsBody:
    try:
        settings = _db.update_user_demo_settings(actor["id"], body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if settings is None:
        raise HTTPException(status_code=404, detail="user not found")
    return DemoSettingsBody(**settings)


@app.get("/api/settings/status", response_model=SettingsStatusResponse)
def api_settings_status(actor: dict = Depends(_admin_user)) -> SettingsStatusResponse:
    db_info = _db.database_info()
    return SettingsStatusResponse(
        database=DatabaseSettingsStatus(
            **db_info,
            note="DB connection is selected at server startup by INKU_DB_URL. Restart the server after changing it.",
        ),
        plugins=PluginSettingsStatus(
            note="Plugin loading is not implemented in this reference server yet. The UI is read-only until a loader API exists.",
        ),
        output_save=OutputSaveStatus(
            workers=_SAVE_WORKERS,
            queue_limit=_SAVE_QUEUE_LIMIT,
            **_artifact_save_stats(),
            note="History DB is the source of truth. Output files are background artifacts and may be rebuilt from DB.",
        ),
    )


@app.post("/api/auth/logout")
def api_auth_logout(response: Response, token: str = Depends(_session_token)) -> dict[str, bool]:
    _db.delete_session(token)
    _clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/prompts", response_model=PromptsResponse)
def api_prompts(lang: str = Query(default="ja")) -> PromptsResponse:
    s1 = STAGE1_PROMPT_EN if lang == "en" else STAGE1_PROMPT
    s2 = STAGE2_PROMPT_EN if lang == "en" else STAGE2_PROMPT
    return PromptsResponse(stage1_system=s1, stage2_system=s2)


def _fallback_score_from_ddl(ddl: str, *, lang: str) -> Score:
    """Build a minimal visible score when Stage 2 returns empty twice."""
    lower = ddl.lower()

    if ("背景を黒" in ddl) or ("fill background with black" in lower):
        background = "black"
        color = "white"
    elif ("背景を赤" in ddl) or ("fill background with red" in lower):
        background = "red"
        color = "black"
    elif ("背景を青" in ddl) or ("fill background with blue" in lower):
        background = "blue"
        color = "white"
    elif ("背景を緑" in ddl) or ("fill background with green" in lower):
        background = "green"
        color = "black"
    else:
        background = "white"
        color = "black"

    if (("白" in ddl) or ("white" in lower)) and background != "white":
        color = "white"
    elif (("青" in ddl) or ("blue" in lower)) and background != "blue":
        color = "blue"
    elif (("赤" in ddl) or ("red" in lower)) and background != "red":
        color = "red"
    elif (("緑" in ddl) or ("green" in lower)) and background != "green":
        color = "green"
    elif (("灰" in ddl) or ("gray" in lower) or ("grey" in lower)) and background != "gray":
        color = "gray"

    if color == background:
        color = "white" if background in {"black", "blue"} else "black"

    if ("四角" in ddl) or ("square" in lower) or ("rectangle" in lower):
        instruction = {
            "primitive": "square",
            "position": [0.62, 0.28],
            "size": [0.18, 0.12],
            "rotation": -12,
            "color": color,
            "filled": "塗" in ddl or "fill" in lower,
            "color_hint": "fallback from DDL",
        }
    elif ("円" in ddl) or ("circle" in lower) or ("moon" in lower) or ("月" in ddl):
        instruction = {
            "primitive": "ellipse",
            "center": [0.72, 0.32],
            "size": [0.18, 0.11],
            "rotation": -18,
            "color": color,
            "filled": "塗" in ddl or "fill" in lower,
            "color_hint": "fallback from DDL",
        }
    elif ("弧" in ddl) or ("arc" in lower) or ("crescent" in lower):
        instruction = {
            "primitive": "arc",
            "center": [0.72, 0.32],
            "radius": 0.16,
            "angle_start": 210,
            "angle_end": 330,
            "color": color,
            "color_hint": "fallback from DDL",
        }
    else:
        instruction = {
            "primitive": "line",
            "from": [0.16, 0.78],
            "to": [0.84, 0.28],
            "rotation": -8,
            "color": color,
            "color_hint": "fallback from DDL",
        }

    if (("散らす" in ddl) or ("点々" in ddl) or ("scatter" in lower) or ("dotted" in lower)) and instruction["primitive"] != "line":
        instruction["arrangement"] = {"count": 7, "layout": "scatter", "margin": 0.18}

    return Score.model_validate({"background": background, "instructions": [instruction]})


def _call_compose_detail(
    ddl: str,
    *,
    model: str | None = None,
    original_text: str | None = None,
    system_prompt: str | None = None,
    lang: str = "ja",
) -> tuple[Score, int | None, int | None]:
    ddl = expand_intermediate_ddl(ddl, lang=lang, context_text=original_text)

    def invoke(prompt: str | None) -> tuple[Score, int | None, int | None]:
        try:
            value = compose(
                ddl,
                model=model,
                original_text=original_text,
                system_prompt=prompt,
                lang=lang,
            )
        except TypeError as e:
            if "unexpected keyword argument" not in str(e):
                raise
            value = compose(ddl, model=model)
        if isinstance(value, tuple):
            return value
        return value, None, None

    score, tokens_in, tokens_out = invoke(system_prompt)
    if score.instructions:
        return score, tokens_in, tokens_out

    base_prompt = system_prompt or (STAGE2_PROMPT_EN if lang == "en" else STAGE2_PROMPT)
    rescue_note = (
        "\n\n# Empty result retry\n"
        "The previous output had no drawable instructions. This is invalid. "
        "Return at least one visible line, ellipse, square, triangle, circle, or arc derived from the normalized DDL. "
        "Do not return an empty instructions array."
        if lang == "en"
        else "\n\n# 空描画リトライ\n"
        "直前の出力は描画命令が空であり無効。正規化DDLから、見える線・楕円・四角・三角・円・弧のうち少なくとも一つを必ず返す。"
        "instructions を空配列にしてはいけない。"
    )
    retry_score, retry_tokens_in, retry_tokens_out = invoke(base_prompt + rescue_note)
    if retry_tokens_in is not None:
        tokens_in = (tokens_in or 0) + retry_tokens_in
    if retry_tokens_out is not None:
        tokens_out = (tokens_out or 0) + retry_tokens_out
    if not retry_score.instructions:
        return _fallback_score_from_ddl(ddl, lang=lang), tokens_in, tokens_out
    return retry_score, tokens_in, tokens_out


def _call_interpret_detail(
    text: str,
    *,
    model: str | None = None,
    include_thinking: bool = False,
    system_prompt_prefix: str | None = None,
    lang: str = "ja",
) -> tuple[str, str | None, int | None, int | None]:
    try:
        value = interpret_detail(
            text,
            model=model,
            include_thinking=include_thinking,
            system_prompt_prefix=system_prompt_prefix,
            lang=lang,
        )
    except TypeError as e:
        if "unexpected keyword argument" not in str(e):
            raise
        value = interpret_detail(text, model=model, include_thinking=include_thinking)
    if len(value) == 4:
        ddl, thinking, tokens_in, tokens_out = value
        return _sanitize_placement_words(ddl), thinking, tokens_in, tokens_out
    ddl, thinking = value
    return _sanitize_placement_words(ddl), thinking, None, None


@app.post("/api/compose", response_model=ComposeResponse, response_model_exclude_none=True)
def api_compose(req: ComposeRequest, _actor: dict = Depends(_current_user)) -> ComposeResponse:
    t0 = time.perf_counter()
    try:
        score, tokens_in, tokens_out = _call_compose_detail(
            req.ddl,
            model=req.model,
            original_text=req.original_text,
            system_prompt=None,
            lang=req.lang,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    try:
        ensure_renderable_score(score)
        score = coerce_score(score)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    try:
        svg = render(score, color_map=req.color_map)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"render failed: {e}") from e

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return ComposeResponse(score=score, svg=svg, elapsed_ms=elapsed_ms, tokens_in=tokens_in, tokens_out=tokens_out)


@app.post("/api/interpret")
def api_interpret(req: InterpretRequest, _actor: dict = Depends(_current_user)) -> dict:
    try:
        ddl, thinking, tokens_in, tokens_out = _call_interpret_detail(
            req.text,
            model=req.model,
            include_thinking=req.include_thinking,
            system_prompt_prefix=None,
            lang=req.lang,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"interpret failed: {e}") from e
    data: dict = {"ddl": ddl, "thinking": thinking}
    if tokens_in is not None:
        data["tokens_in"] = tokens_in
    if tokens_out is not None:
        data["tokens_out"] = tokens_out
    return data


def _strip_anthropic_prefix(model: str) -> str:
    return model.removeprefix("anthropic:")


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
    model_name = model or os.getenv("OPENAI_MODEL_STAGE1") or os.getenv("OPENAI_MODEL") or "qwen-api"
    if model_name.startswith("anthropic:"):
        import anthropic

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=_strip_anthropic_prefix(model_name),
            max_tokens=180,
            temperature=0.9,
            system=_demo_instruction_system(lang),
            messages=[{"role": "user", "content": seed_phrase}],
        )
        parts = [getattr(block, "text", "") for block in resp.content if getattr(block, "type", "") == "text"]
        text = "\n".join(parts).strip()
    else:
        from openai import OpenAI

        if "/" in model_name:
            base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
            api_key = os.getenv("NVIDIA_API_KEY", "")
        else:
            base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v3")
            api_key = os.getenv("OPENAI_API_KEY", "dummy")
        client = OpenAI(base_url=base_url, api_key=api_key)
        resp = client.chat.completions.create(
            model=model_name,
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


@app.post("/api/demo/instruction", response_model=DemoInstructionResponse)
def api_demo_instruction(req: DemoInstructionBody, _actor: dict = Depends(_current_user)) -> DemoInstructionResponse:
    try:
        instruction = _generate_demo_instruction(req.seed_phrase, model=req.model, lang=req.lang)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"demo instruction failed: {e}") from e
    return DemoInstructionResponse(instruction=instruction)


def _add_history_item(
    *,
    actor: dict,
    input_text: str,
    ddl: str | None,
    score: Score,
    svg: str,
    at: int,
    elapsed_ms: int = 0,
    stage1_model: str | None = None,
    stage2_model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    catalog_id: str | None = None,
    save_artifacts: bool = True,
) -> dict:
    item_id = str(uuid.uuid4())
    score_dict = score.model_dump(by_alias=True)
    prefix = _output_prefix(actor["id"], item_id, at)
    item_dict = _db.add_item({
        "id": item_id,
        "user_id": actor["id"],
        "output_path": str(prefix),
        "input": input_text,
        "ddl": _sanitize_placement_words(ddl) if ddl else ddl,
        "score": score_dict,
        "svg": svg,
        "at": at,
        "elapsed_ms": elapsed_ms,
        "stage1_model": stage1_model,
        "stage2_model": stage2_model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "catalog_id": catalog_id,
    })
    if save_artifacts:
        _submit_history_artifact_save(item_dict)
    return item_dict


@app.post("/api/paint", response_model=PaintResponse, response_model_exclude_none=True)
def api_paint(req: PaintRequest, actor: dict = Depends(_current_user)) -> PaintResponse:
    t0 = time.perf_counter()
    source_text = req.original_text or req.text
    try:
        ddl, thinking, s1_tin, s1_tout = _call_interpret_detail(
            req.text, model=req.stage1_model, include_thinking=req.include_thinking, lang=req.lang
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"interpret failed: {e}") from e
    ddl = expand_intermediate_ddl(ddl, lang=req.lang, context_text=source_text)
    t1 = time.perf_counter()
    try:
        score, s2_tin, s2_tout = _call_compose_detail(
            ddl, model=req.stage2_model, original_text=source_text, lang=req.lang
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    try:
        ensure_renderable_score(score)
        score = coerce_score(score)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    t2 = time.perf_counter()
    try:
        svg = render(score, color_map=req.color_map)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"render failed: {e}") from e
    elapsed_stage1_ms = int((t1 - t0) * 1000)
    elapsed_stage2_ms = int((t2 - t1) * 1000)
    elapsed_total_ms = int((time.perf_counter() - t0) * 1000)
    history_id = None
    history_at = None
    save_artifacts = req.save_artifacts if req.save_artifacts is not None else req.save_history
    if req.save_history:
        history_at = req.history_at or int(time.time() * 1000)
        item = _add_history_item(
            actor=actor,
            input_text=req.history_input or source_text,
            ddl=ddl,
            score=score,
            svg=svg,
            at=history_at,
            elapsed_ms=elapsed_total_ms,
            stage1_model=req.stage1_model,
            stage2_model=req.stage2_model,
            tokens_in=(s1_tin or 0) + (s2_tin or 0) or None,
            tokens_out=(s1_tout or 0) + (s2_tout or 0) or None,
            catalog_id=req.catalog_id,
            save_artifacts=save_artifacts,
        )
        history_id = item["id"]
    elif save_artifacts:
        history_at = req.history_at or int(time.time() * 1000)
        item_id = str(uuid.uuid4())
        score_dict = score.model_dump(by_alias=True)
        _submit_history_artifact_save({
            "id": item_id,
            "user_id": actor["id"],
            "output_path": str(_output_prefix(actor["id"], item_id, history_at)),
            "input": req.history_input or source_text,
            "ddl": _sanitize_placement_words(ddl) if ddl else ddl,
            "score": score_dict,
            "svg": svg,
            "at": history_at,
        })
    return PaintResponse(
        text=source_text,
        ddl=ddl,
        thinking=thinking,
        score=score,
        svg=svg,
        history_id=history_id,
        history_at=history_at,
        elapsed_stage1_ms=elapsed_stage1_ms,
        elapsed_stage2_ms=elapsed_stage2_ms,
        elapsed_total_ms=elapsed_total_ms,
        tokens_in_stage1=s1_tin,
        tokens_out_stage1=s1_tout,
        tokens_in_stage2=s2_tin,
        tokens_out_stage2=s2_tout,
    )


@app.get("/api/user-groups", response_model=list[UserGroupItem])
def api_user_groups_list(actor: dict = Depends(_user_manager)) -> list[UserGroupItem]:
    groups = _db.list_user_groups()
    if actor["role"] == "group_lead":
        groups = [group for group in groups if group["id"] == actor.get("group_id")]
    return [UserGroupItem(**group) for group in groups]


@app.post("/api/user-groups", response_model=UserGroupItem)
def api_user_groups_create(body: UserGroupCreateBody, actor: dict = Depends(_user_manager)) -> UserGroupItem:
    if actor["role"] != "admin":
        raise HTTPException(status_code=403, detail="only administrators can create groups")
    try:
        return UserGroupItem(**_db.add_user_group(body.name))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=409, detail=f"group create failed: {e}") from e


@app.delete("/api/user-groups/{group_id}")
def api_user_groups_delete(group_id: str, actor: dict = Depends(_user_manager)) -> dict[str, bool]:
    if actor["role"] != "admin":
        raise HTTPException(status_code=403, detail="only administrators can delete groups")
    try:
        found = _db.delete_user_group(group_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail="group not found")
    return {"ok": True}


@app.get("/api/users", response_model=list[UserAccountItem])
def api_users_list(actor: dict = Depends(_user_manager)) -> list[UserAccountItem]:
    return [UserAccountItem(**user) for user in _db.list_users_for_actor(actor)]


@app.post("/api/users", response_model=UserAccountItem)
def api_users_create(body: UserAccountCreateBody, actor: dict = Depends(_user_manager)) -> UserAccountItem:
    if actor["role"] == "group_lead":
        if body.role != "user" or body.group_id != actor.get("group_id"):
            raise HTTPException(status_code=403, detail="group leads can create users only in their own group")
    try:
        user = _db.add_user(
            username=body.username,
            email=body.email,
            password=body.password,
            role=body.role,
            group_id=body.group_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=409, detail=f"user create failed: {e}") from e
    return UserAccountItem(**user)


@app.patch("/api/users/{user_id}", response_model=UserAccountItem)
def api_users_update(
    user_id: str,
    body: UserAccountUpdateBody,
    actor: dict = Depends(_user_manager),
) -> UserAccountItem:
    target = _db.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user not found")
    if not _can_manage_user(actor, target):
        raise HTTPException(status_code=403, detail="user update is not permitted")
    if actor["role"] == "group_lead":
        if body.role and body.role != "user":
            raise HTTPException(status_code=403, detail="group leads cannot change user roles")
        if body.group_id is not None and body.group_id != actor.get("group_id"):
            raise HTTPException(status_code=403, detail="group leads cannot move users outside their group")
    try:
        user = _db.update_user(user_id, **body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=409, detail=f"user update failed: {e}") from e
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return UserAccountItem(**user)


@app.delete("/api/users/{user_id}")
def api_users_delete(user_id: str, actor: dict = Depends(_user_manager)) -> dict[str, bool]:
    target = _db.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user not found")
    if not _can_manage_user(actor, target):
        raise HTTPException(status_code=403, detail="user delete is not permitted")
    try:
        found = _db.delete_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True}


@app.get("/api/history", response_model=HistoryListResponse)
def api_history_get(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    trashed: bool = Query(default=False),
    starred: bool = Query(default=False),
    q: str = Query(default="", max_length=200),
    actor: dict = Depends(_current_user),
) -> HistoryListResponse:
    items, total = _db.list_items(
        actor["id"],
        offset=offset,
        limit=limit,
        trashed=trashed,
        query_text=q,
        starred=starred,
    )
    return HistoryListResponse(items=items, total=total, offset=offset, limit=limit)


@app.post("/api/history", response_model=HistoryItem)
def api_history_post(body: HistoryPostBody, actor: dict = Depends(_current_user)) -> HistoryItem:
    try:
        score = coerce_score(Score.model_validate(body.score))
        svg = render(score, color_map=_validated_color_map(body.color_map))
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"history score render failed: {e}") from e
    item_dict = _add_history_item(
        actor=actor,
        input_text=body.input,
        ddl=body.ddl,
        score=score,
        svg=svg,
        at=body.at,
        elapsed_ms=body.elapsed_ms,
        stage1_model=body.stage1_model,
        stage2_model=body.stage2_model,
        tokens_in=body.tokens_in,
        tokens_out=body.tokens_out,
        catalog_id=body.catalog_id,
        save_artifacts=body.save_artifacts,
    )
    return HistoryItem(**item_dict)


@app.delete("/api/history")
def api_history_delete(actor: dict = Depends(_current_user)) -> dict[str, bool]:
    _db.delete_all(actor["id"])
    return {"ok": True}


@app.post("/api/history/trash")
def api_history_trash(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    count = _db.trash_items(actor["id"], body.ids)
    return {"ok": True, "count": count}


@app.post("/api/history/restore")
def api_history_restore(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    count = _db.restore_items(actor["id"], body.ids)
    return {"ok": True, "count": count}


@app.patch("/api/history/{item_id}/star", response_model=HistoryItem)
def api_history_star(item_id: str, body: HistoryStarBody, actor: dict = Depends(_current_user)) -> HistoryItem:
    item = _db.set_item_starred(actor["id"], item_id, body.starred)
    if not item:
        raise HTTPException(status_code=404, detail="history item not found")
    return HistoryItem(**item)


@app.post("/api/history/rebuild-output-files")
def api_history_rebuild_output_files(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    items = _db.get_items(actor["id"], body.ids)
    for item in items:
        _save_history_artifacts(item)
    return {"ok": True, "count": len(items)}


@app.post("/api/history/permanent-delete")
def api_history_permanent_delete(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    count = _db.delete_items(actor["id"], body.ids)
    return {"ok": True, "count": count}



def main() -> None:
    import uvicorn

    host = os.getenv("INKU_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("INKU_SERVER_PORT", "8100"))
    reload = _env_flag("INKU_SERVER_RELOAD", default=False)
    uvicorn.run("inku_server.api:app", host=host, port=port, reload=reload)
