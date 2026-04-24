"""FastAPI endpoints for inku-server.

POST /api/compose : 正規化DDL (or 生入力) → JSON Score + SVG
GET  /health      : liveness
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .composer import compose
from .interpreter import interpret_detail
from .renderer import render
from .schema import Score

app = FastAPI(title="inku-server", version="0.1.0")

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


class ComposeResponse(BaseModel):
    score: Score
    svg: str


class InterpretRequest(BaseModel):
    text: str = Field(..., min_length=1, description="自由な自然言語の記述")
    model: str | None = Field(
        default=None, description="Stage 1 モデル名 (未指定時は OPENAI_MODEL_STAGE1 既定)"
    )
    include_thinking: bool = Field(
        default=False, description="qwen3 の <think> 内容を別フィールドで返すか"
    )


class InterpretResponse(BaseModel):
    ddl: str
    thinking: str | None = None


class PaintRequest(BaseModel):
    text: str = Field(..., min_length=1, description="自由な自然言語の記述")
    stage1_model: str | None = Field(default=None, description="Stage 1 モデル名")
    stage2_model: str | None = Field(default=None, description="Stage 2 モデル名")
    include_thinking: bool = Field(default=False, description="Stage 1 の思考を返すか")


class PaintResponse(BaseModel):
    text: str
    ddl: str
    thinking: str | None = None
    score: Score
    svg: str


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/compose", response_model=ComposeResponse)
def api_compose(req: ComposeRequest) -> ComposeResponse:
    try:
        score = compose(req.ddl, model=req.model)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e

    try:
        svg = render(score)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"render failed: {e}") from e

    return ComposeResponse(score=score, svg=svg)


@app.post("/api/interpret", response_model=InterpretResponse)
def api_interpret(req: InterpretRequest) -> InterpretResponse:
    try:
        ddl, thinking = interpret_detail(
            req.text, model=req.model, include_thinking=req.include_thinking
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"interpret failed: {e}") from e
    return InterpretResponse(ddl=ddl, thinking=thinking)


@app.post("/api/paint", response_model=PaintResponse)
def api_paint(req: PaintRequest) -> PaintResponse:
    try:
        ddl, thinking = interpret_detail(
            req.text, model=req.stage1_model, include_thinking=req.include_thinking
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"interpret failed: {e}") from e
    try:
        score = compose(ddl, model=req.stage2_model)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e
    try:
        svg = render(score)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"render failed: {e}") from e
    return PaintResponse(text=req.text, ddl=ddl, thinking=thinking, score=score, svg=svg)


def main() -> None:
    import uvicorn

    host = os.getenv("INKU_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("INKU_SERVER_PORT", "8100"))
    uvicorn.run("inku_server.api:app", host=host, port=port, reload=True)
