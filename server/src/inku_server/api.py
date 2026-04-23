"""FastAPI endpoints for inku-server.

POST /api/compose : 正規化DDL (or 生入力) → JSON Score + SVG
GET  /health      : liveness
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .composer import compose
from .interpreter import interpret
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


class ComposeResponse(BaseModel):
    score: Score
    svg: str


class InterpretRequest(BaseModel):
    text: str = Field(..., min_length=1, description="自由な自然言語の記述")


class InterpretResponse(BaseModel):
    ddl: str


class PaintRequest(BaseModel):
    text: str = Field(..., min_length=1, description="自由な自然言語の記述")


class PaintResponse(BaseModel):
    text: str
    ddl: str
    score: Score
    svg: str


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/compose", response_model=ComposeResponse)
def api_compose(req: ComposeRequest) -> ComposeResponse:
    try:
        score = compose(req.ddl)
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
        ddl = interpret(req.text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"interpret failed: {e}") from e
    return InterpretResponse(ddl=ddl)


@app.post("/api/paint", response_model=PaintResponse)
def api_paint(req: PaintRequest) -> PaintResponse:
    try:
        ddl = interpret(req.text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"interpret failed: {e}") from e
    try:
        score = compose(ddl)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"compose failed: {e}") from e
    try:
        svg = render(score)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"render failed: {e}") from e
    return PaintResponse(text=req.text, ddl=ddl, score=score, svg=svg)


def main() -> None:
    import uvicorn

    uvicorn.run("inku_server.api:app", host="127.0.0.1", port=8000, reload=True)
