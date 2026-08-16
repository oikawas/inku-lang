"""The API answers with gzip, and skips the bodies that are already compressed.

Measured against production on 2026-08-16: a work's SVG went out uncompressed
at 11,068,576 bytes, and a thumbnail of 115,167 bytes gzips to 115,026 -- all
of the work, none of the saving. So the gate has two halves, and neither half
alone is the claim: compressing everything and compressing nothing both pass
one of them.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from fastapi.testclient import TestClient

from inku_server.api import app as inku_app


def _middleware_names(app: FastAPI) -> list[str]:
    return [entry.cls.__name__ for entry in app.user_middleware]


async def _ask_and_record_each_message(
    app: FastAPI, path: str
) -> tuple[dict, list[bytes]]:
    """Drive the app as the ASGI app it is, keeping the body messages apart.

    The test client joins a body up before returning it, which is the one thing
    a gate about *when* bytes leave must not do.
    """
    start: dict = {}
    bodies: list[bytes] = []
    asked = False

    async def receive() -> dict:
        nonlocal asked
        if not asked:
            asked = True
            return {"type": "http.request", "body": b"", "more_body": False}
        # The response also waits for a disconnect. Sleeping rather than
        # answering at once leaves the loop free to run the stream; the
        # response cancels this the moment it has finished.
        await asyncio.sleep(30)
        raise AssertionError("the response never finished")

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            start.update(message)
        elif message["type"] == "http.response.body":
            bodies.append(message.get("body", b""))

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [(b"accept-encoding", b"gzip")],
            "client": ("127.0.0.1", 1234),
            "server": ("127.0.0.1", 8000),
        },
        receive,
        send,
    )
    return start, bodies


# ── T-75 ────────────────────────────────────────────────────────────────────
def test_the_app_carries_the_gzip_layer() -> None:
    assert "FlushingGZipMiddleware" in _middleware_names(inku_app)


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


# ── T-78 ────────────────────────────────────────────────────────────────────
def test_a_streamed_body_leaves_as_it_is_written() -> None:
    """The painting route reports each stage while it is still working.

    ``/api/paint/stream`` writes an event as soon as interpretation finishes so
    the page can name the stage that is running instead of guessing, and the
    page reads the stream chunk by chunk to do it.  A layer that holds those
    events back until the drawing is finished loses no bytes and raises no
    error -- nothing else here would notice -- and costs the only thing that
    event is for, which is when it arrives.  Measured on 2026-08-16 with the
    stock responder, five events put 10 / 0 / 0 / 0 / 117 bytes on the wire;
    the ten were the gzip header.
    """
    events = [
        json.dumps({"event": "stage1", "tokens_in": 1200}).encode() + b"\n",
        json.dumps({"event": "stage2", "tokens_in": 900}).encode() + b"\n",
        json.dumps({"event": "render"}).encode() + b"\n",
        json.dumps({"event": "done", "svg": "<svg>" + "x" * 4000 + "</svg>"}).encode() + b"\n",
    ]

    probe = FastAPI()

    @probe.get("/stream")
    def _stream() -> StreamingResponse:
        def lines() -> Iterator[bytes]:
            yield from events

        # The type /api/paint/stream sends. It is deliberately not in the
        # exclusion list: the done event carries the drawing, so this stream is
        # worth compressing -- it just has to leave as it is written.
        return StreamingResponse(lines(), media_type="application/x-ndjson")

    for entry in reversed(inku_app.user_middleware):
        probe.add_middleware(entry.cls, *entry.args, **entry.kwargs)

    start, bodies = asyncio.run(_ask_and_record_each_message(probe, "/stream"))

    headers = {k.decode(): v.decode() for k, v in start["headers"]}
    assert headers.get("content-encoding") == "gzip", headers

    # One body message per event, then the empty one that ends the response.
    per_event = bodies[: len(events)]
    assert len(per_event) == len(events), (
        f"{len(bodies)} body messages for {len(events)} events"
    )
    assert all(len(b) > 0 for b in per_event), (
        "an event was written and nothing left the layer: "
        f"{[len(b) for b in bodies]} bytes per message"
    )

    # And it is still one gzip stream carrying exactly what was written.
    assert gzip.decompress(b"".join(bodies)) == b"".join(events)
