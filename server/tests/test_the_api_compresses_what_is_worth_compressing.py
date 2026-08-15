"""The API answers with gzip, and skips the bodies that are already compressed.

Measured against production on 2026-08-16: a work's SVG went out uncompressed
at 11,068,576 bytes, and a thumbnail of 115,167 bytes gzips to 115,026 -- all
of the work, none of the saving. So the gate has two halves, and neither half
alone is the claim: compressing everything and compressing nothing both pass
one of them.
"""

from __future__ import annotations

import gzip

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response
from fastapi.testclient import TestClient

from inku_server.api import app as inku_app


def _middleware_names(app: FastAPI) -> list[str]:
    return [entry.cls.__name__ for entry in app.user_middleware]


# ── T-75 ────────────────────────────────────────────────────────────────────
def test_the_app_carries_the_gzip_layer() -> None:
    assert "GZipMiddleware" in _middleware_names(inku_app)


# ── T-76 ────────────────────────────────────────────────────────────────────
def test_a_text_body_comes_back_compressed() -> None:
    # A drawing-sized body of the kind this exists for. Built here rather than
    # taken from the corpus so the gate needs no fixture and no database.
    body = ("<svg>" + "<polyline points='1.5,2.5'/>" * 4000 + "</svg>")

    probe = FastAPI()

    @probe.get("/drawing")
    def _drawing() -> Response:
        # The type the history endpoint actually sends, charset and all: it
        # begins with `image/`, and excluding that family would have turned
        # this middleware off for the one body it was added for.
        return PlainTextResponse(body, media_type="image/svg+xml; charset=utf-8")

    for entry in reversed(inku_app.user_middleware):
        probe.add_middleware(entry.cls, *entry.args, **entry.kwargs)

    with TestClient(probe) as client:
        answer = client.get("/drawing", headers={"accept-encoding": "gzip"})

    assert answer.status_code == 200
    assert answer.headers.get("content-encoding") == "gzip"
    # httpx decodes for us, so the saving is read off the wire length instead.
    on_the_wire = int(answer.headers["content-length"])
    assert on_the_wire < len(body.encode()) // 2, (
        f"{on_the_wire} bytes on the wire against {len(body.encode())} raw"
    )
    assert answer.text == body


# ── T-77 ────────────────────────────────────────────────────────────────────
def test_an_already_compressed_body_is_left_alone() -> None:
    # A PNG is incompressible: gzipping it returns almost exactly its own size,
    # which is the whole reason it must not be gzipped.
    png = gzip.compress(b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 200, 9)
    assert len(png) > 500, "the body must be over the middleware's minimum_size"

    probe = FastAPI()

    @probe.get("/thumb")
    def _thumb() -> Response:
        return Response(content=png, media_type="image/png")

    for entry in reversed(inku_app.user_middleware):
        probe.add_middleware(entry.cls, *entry.args, **entry.kwargs)

    with TestClient(probe) as client:
        answer = client.get("/thumb", headers={"accept-encoding": "gzip"})

    assert answer.status_code == 200
    assert answer.headers.get("content-encoding") is None, (
        "an image was gzipped; the exclusion list no longer covers image/"
    )
    assert answer.content == png
