"""FastAPI endpoints for inku-server.

POST /api/compose : 正規化DDL (or 生入力) → JSON Score + SVG
GET  /health      : liveness
"""

from __future__ import annotations

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .coerce import coerce_score
from .composer import compose
from .composer import SYSTEM_PROMPT as STAGE2_PROMPT
from .composer import SYSTEM_PROMPT_EN as STAGE2_PROMPT_EN
from .interpreter import interpret_detail
from .interpreter import SYSTEM_PROMPT as STAGE1_PROMPT
from .interpreter import SYSTEM_PROMPT_EN as STAGE1_PROMPT_EN
from .interpreter import SYSTEM_PROMPT_PREFIX as STAGE1_PREFIX
from .renderer import render
from .schema import Score
from . import snapshots as _snapshots

app = FastAPI(title="inku-server", version="0.1.0")

# ── 履歴ストレージ ──────────────────────────────────────────────────────────────
_DEFAULT_HISTORY_FILE = Path.home() / ".local" / "share" / "inku" / "history.json"
_HISTORY_FILE = Path(os.getenv("INKU_HISTORY_FILE", str(_DEFAULT_HISTORY_FILE)))
_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
_history: list[dict] = []
_history_lock = Lock()


def _load_history() -> None:
    global _history
    if not _HISTORY_FILE.exists():
        return
    try:
        _history = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        _history = []


def _save_history() -> None:
    try:
        _HISTORY_FILE.write_text(json.dumps(_history), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


_load_history()

# ── 出力ファイル保存 ────────────────────────────────────────────────────────────
_DEFAULT_OUTPUT_DIR = Path.home() / ".local" / "share" / "inku" / "outputs"
_OUTPUT_DIR = Path(os.getenv("INKU_OUTPUT_DIR", str(_DEFAULT_OUTPUT_DIR)))
_OUTPUT_PNG_SIZE = int(os.getenv("INKU_OUTPUT_PNG_SIZE", "2160"))
_save_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="inku-save")


def _save_output(item_id: str, at_ms: int, input_text: str, ddl: str | None, score: dict, svg: str) -> None:
    try:
        import cairosvg  # lazy import — optional dependency
    except ImportError:
        return

    dt = datetime.fromtimestamp(at_ms / 1000, tz=timezone.utc).astimezone()
    date_dir = _OUTPUT_DIR / dt.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    prefix = dt.strftime("%Y%m%d_%H%M%S") + "_" + item_id[:8]

    try:
        if input_text:
            (date_dir / f"{prefix}_instruction.txt").write_text(input_text, encoding="utf-8")
        if ddl:
            (date_dir / f"{prefix}_normalized.ddl").write_text(ddl, encoding="utf-8")
        (date_dir / f"{prefix}_score.json").write_text(
            json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        svg_bytes = svg.encode("utf-8")
        (date_dir / f"{prefix}_output.svg").write_bytes(svg_bytes)
        png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=_OUTPUT_PNG_SIZE)
        (date_dir / f"{prefix}_output.png").write_bytes(png_bytes)
    except Exception:  # noqa: BLE001
        pass


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
    snapshot_id: str | None = Field(default=None, description="歳時記スナップショット ID")
    lang: str = Field(default="ja", description="言語コード (ja / en)")


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
    snapshot_id: str | None = Field(default=None, description="歳時記スナップショット ID")
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


class HistoryItem(HistoryPostBody):
    id: str


class HistoryListResponse(BaseModel):
    items: list[HistoryItem]
    total: int
    offset: int
    limit: int


class SnapshotMeta(BaseModel):
    id: str
    name: str
    at: int


class SnapshotCreateBody(BaseModel):
    name: str = Field(..., min_length=1, description="スナップショット名")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/prompts", response_model=PromptsResponse)
def api_prompts(lang: str = Query(default="ja")) -> PromptsResponse:
    s1 = STAGE1_PROMPT_EN if lang == "en" else STAGE1_PROMPT
    s2 = STAGE2_PROMPT_EN if lang == "en" else STAGE2_PROMPT
    return PromptsResponse(stage1_system=s1, stage2_system=s2)


@app.post("/api/compose", response_model=ComposeResponse)
def api_compose(req: ComposeRequest) -> ComposeResponse:
    t0 = time.perf_counter()
    stage2_prompt: str | None = None
    if req.snapshot_id:
        snap = _snapshots.get_snapshot(req.snapshot_id)
        if snap:
            stage2_prompt = snap.get("stage2_prompt")
    try:
        score, tokens_in, tokens_out = compose(req.ddl, model=req.model, original_text=req.original_text, system_prompt=stage2_prompt, lang=req.lang)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    score = coerce_score(score)

    try:
        svg = render(score)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"render failed: {e}") from e

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return ComposeResponse(score=score, svg=svg, elapsed_ms=elapsed_ms, tokens_in=tokens_in, tokens_out=tokens_out)


@app.post("/api/interpret", response_model=InterpretResponse)
def api_interpret(req: InterpretRequest) -> InterpretResponse:
    stage1_prefix: str | None = None
    if req.snapshot_id:
        snap = _snapshots.get_snapshot(req.snapshot_id)
        if snap:
            stage1_prefix = snap.get("stage1_prefix")
    try:
        ddl, thinking, tokens_in, tokens_out = interpret_detail(
            req.text,
            model=req.model,
            include_thinking=req.include_thinking,
            system_prompt_prefix=stage1_prefix,
            lang=req.lang,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"interpret failed: {e}") from e
    return InterpretResponse(ddl=ddl, thinking=thinking, tokens_in=tokens_in, tokens_out=tokens_out)


@app.post("/api/paint", response_model=PaintResponse)
def api_paint(req: PaintRequest) -> PaintResponse:
    t0 = time.perf_counter()
    try:
        ddl, thinking, s1_tin, s1_tout = interpret_detail(
            req.text, model=req.stage1_model, include_thinking=req.include_thinking, lang=req.lang
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"interpret failed: {e}") from e
    t1 = time.perf_counter()
    try:
        score, s2_tin, s2_tout = compose(ddl, model=req.stage2_model, original_text=req.text, lang=req.lang)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    score = coerce_score(score)

    t2 = time.perf_counter()
    try:
        svg = render(score)
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


@app.get("/api/saijiki/snapshots", response_model=list[SnapshotMeta])
def api_snapshots_list() -> list[SnapshotMeta]:
    return [SnapshotMeta(**s) for s in _snapshots.list_snapshots()]


@app.post("/api/saijiki/snapshots", response_model=SnapshotMeta)
def api_snapshots_create(body: SnapshotCreateBody) -> SnapshotMeta:
    meta = _snapshots.create_snapshot(
        name=body.name,
        stage1_prefix=STAGE1_PREFIX,
        stage2_prompt=STAGE2_PROMPT,
    )
    return SnapshotMeta(**meta)


@app.delete("/api/saijiki/snapshots/{snapshot_id}")
def api_snapshots_delete(snapshot_id: str) -> dict[str, bool]:
    found = _snapshots.delete_snapshot(snapshot_id)
    if not found:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return {"ok": True}


@app.get("/api/history", response_model=HistoryListResponse)
def api_history_get(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
) -> HistoryListResponse:
    with _history_lock:
        items_newest_first = list(reversed(_history))
        total = len(items_newest_first)
        page = items_newest_first[offset : offset + limit]
    return HistoryListResponse(items=page, total=total, offset=offset, limit=limit)


@app.post("/api/history", response_model=HistoryItem)
def api_history_post(body: HistoryPostBody) -> HistoryItem:
    item = HistoryItem(id=str(uuid.uuid4()), **body.model_dump())
    with _history_lock:
        _history.append(item.model_dump())
        _save_history()
    _save_executor.submit(
        _save_output, item.id, item.at, item.input, item.ddl, item.score, item.svg
    )
    return item


@app.delete("/api/history")
def api_history_delete() -> dict[str, bool]:
    with _history_lock:
        _history.clear()
        _save_history()
    return {"ok": True}



def main() -> None:
    import uvicorn

    host = os.getenv("INKU_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("INKU_SERVER_PORT", "8100"))
    uvicorn.run("inku_server.api:app", host=host, port=port, reload=True)
