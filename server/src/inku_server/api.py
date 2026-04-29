"""FastAPI endpoints for inku-server.

POST /api/compose : 正規化DDL (or 生入力) → JSON Score + SVG
GET  /health      : liveness
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .coerce import coerce_score
from .composer import compose
from .composer import SYSTEM_PROMPT as STAGE2_PROMPT
from .composer import SYSTEM_PROMPT_EN as STAGE2_PROMPT_EN
from .interpreter import interpret_detail
from .interpreter import SYSTEM_PROMPT as STAGE1_PROMPT
from .interpreter import SYSTEM_PROMPT_EN as STAGE1_PROMPT_EN
from .renderer import render
from .schema import Score
from . import db as _db

app = FastAPI(title="inku-server", version="0.1.0")

_db.init_db()

# ── 出力ファイル保存 ────────────────────────────────────────────────────────────
_DEFAULT_OUTPUT_DIR = Path.home() / ".local" / "share" / "inku" / "outputs"
_OUTPUT_DIR = Path(os.getenv("INKU_OUTPUT_DIR", str(_DEFAULT_OUTPUT_DIR)))
_OUTPUT_PNG_SIZE = int(os.getenv("INKU_OUTPUT_PNG_SIZE", "2160"))
_save_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="inku-save")
_logger = logging.getLogger(__name__)


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
    stage1_model: str | None = Field(default=None, description="Stage 1 モデル名")
    stage2_model: str | None = Field(default=None, description="Stage 2 モデル名")
    include_thinking: bool = Field(default=False, description="Stage 1 の思考を返すか")
    lang: str = Field(default="ja", description="言語コード (ja / en)")
    color_map: dict[str, str] | None = Field(default=None, description="色カタログ")


class PaintResponse(BaseModel):
    text: str
    ddl: str
    thinking: str | None = None
    score: Score
    svg: str
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
    svg: str
    at: int
    elapsed_ms: int = 0
    stage1_model: str | None = None
    stage2_model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    catalog_id: str | None = None


class HistoryItem(HistoryPostBody):
    id: str
    output_path: str | None = None
    trashed: bool = False


class HistoryListResponse(BaseModel):
    items: list[HistoryItem]
    total: int
    offset: int
    limit: int


class HistoryIdsBody(BaseModel):
    ids: list[str] = Field(default_factory=list)


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
    token: str
    user: UserAccountItem


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


class SettingsStatusResponse(BaseModel):
    database: DatabaseSettingsStatus
    plugins: PluginSettingsStatus


def _bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="authentication required")
    return authorization.removeprefix("Bearer ").strip()


def _current_user(token: str = Depends(_bearer_token)) -> dict:
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
def api_auth_login(body: LoginBody) -> LoginResponse:
    user = _db.authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid username or password")
    token = _db.create_session(user["id"])
    return LoginResponse(token=token, user=UserAccountItem(**user))


@app.get("/api/auth/me", response_model=UserAccountItem)
def api_auth_me(actor: dict = Depends(_current_user)) -> UserAccountItem:
    return UserAccountItem(**actor)


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
    )


@app.post("/api/auth/logout")
def api_auth_logout(token: str = Depends(_bearer_token)) -> dict[str, bool]:
    _db.delete_session(token)
    return {"ok": True}


@app.get("/api/prompts", response_model=PromptsResponse)
def api_prompts(lang: str = Query(default="ja")) -> PromptsResponse:
    s1 = STAGE1_PROMPT_EN if lang == "en" else STAGE1_PROMPT
    s2 = STAGE2_PROMPT_EN if lang == "en" else STAGE2_PROMPT
    return PromptsResponse(stage1_system=s1, stage2_system=s2)


def _call_compose_detail(
    ddl: str,
    *,
    model: str | None = None,
    original_text: str | None = None,
    system_prompt: str | None = None,
    lang: str = "ja",
) -> tuple[Score, int | None, int | None]:
    try:
        value = compose(
            ddl,
            model=model,
            original_text=original_text,
            system_prompt=system_prompt,
            lang=lang,
        )
    except TypeError as e:
        if "unexpected keyword argument" not in str(e):
            raise
        value = compose(ddl, model=model)
    if isinstance(value, tuple):
        return value
    return value, None, None


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
        return value
    ddl, thinking = value
    return ddl, thinking, None, None


@app.post("/api/compose", response_model=ComposeResponse, response_model_exclude_none=True)
def api_compose(req: ComposeRequest) -> ComposeResponse:
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

    score = coerce_score(score)

    try:
        svg = render(score, color_map=req.color_map)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"render failed: {e}") from e

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return ComposeResponse(score=score, svg=svg, elapsed_ms=elapsed_ms, tokens_in=tokens_in, tokens_out=tokens_out)


@app.post("/api/interpret")
def api_interpret(req: InterpretRequest) -> dict:
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


@app.post("/api/paint", response_model=PaintResponse, response_model_exclude_none=True)
def api_paint(req: PaintRequest) -> PaintResponse:
    t0 = time.perf_counter()
    try:
        ddl, thinking, s1_tin, s1_tout = _call_interpret_detail(
            req.text, model=req.stage1_model, include_thinking=req.include_thinking, lang=req.lang
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"interpret failed: {e}") from e
    t1 = time.perf_counter()
    try:
        score, s2_tin, s2_tout = _call_compose_detail(
            ddl, model=req.stage2_model, original_text=req.text, lang=req.lang
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    score = coerce_score(score)

    t2 = time.perf_counter()
    try:
        svg = render(score, color_map=req.color_map)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"render failed: {e}") from e
    elapsed_stage1_ms = int((t1 - t0) * 1000)
    elapsed_stage2_ms = int((t2 - t1) * 1000)
    elapsed_total_ms = int((time.perf_counter() - t0) * 1000)
    return PaintResponse(
        text=req.text,
        ddl=ddl,
        thinking=thinking,
        score=score,
        svg=svg,
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
    q: str = Query(default="", max_length=200),
    actor: dict = Depends(_current_user),
) -> HistoryListResponse:
    items, total = _db.list_items(actor["id"], offset=offset, limit=limit, trashed=trashed, query_text=q)
    return HistoryListResponse(items=items, total=total, offset=offset, limit=limit)


@app.post("/api/history", response_model=HistoryItem)
def api_history_post(body: HistoryPostBody, actor: dict = Depends(_current_user)) -> HistoryItem:
    item_id = str(uuid.uuid4())
    prefix = _output_prefix(actor["id"], item_id, body.at)
    item_dict = _db.add_item({
        "id": item_id,
        "user_id": actor["id"],
        "output_path": str(prefix),
        **body.model_dump(),
    })
    _save_executor.submit(
        _save_output_files, prefix, body.input, body.ddl, body.score, body.svg
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


@app.post("/api/history/permanent-delete")
def api_history_permanent_delete(body: HistoryIdsBody, actor: dict = Depends(_current_user)) -> dict[str, int | bool]:
    count = _db.delete_items(actor["id"], body.ids)
    return {"ok": True, "count": count}



def main() -> None:
    import uvicorn

    host = os.getenv("INKU_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("INKU_SERVER_PORT", "8100"))
    uvicorn.run("inku_server.api:app", host=host, port=port, reload=True)
