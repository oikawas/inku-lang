import asyncio
import threading

from starlette.requests import Request

from inku_server.api_core.routers import history
from inku_server.compression import _FlushingGZipResponder


def _request(etag=None):
    headers = [] if etag is None else [(b"if-none-match", etag.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_display_conditional_get_skips_svg_and_other_profiles_have_no_etag(monkeypatch):
    item = {"svg": "<svg/>", "score": {}, "render_hash": "rh2:abc"}
    monkeypatch.setattr(history._db, "get_items", lambda *_: [item])
    first = history.api_history_svg("work", profile="display", actor={"id": "u"}, request=_request())
    assert first.headers["etag"] == '"rh2:abc-display"'
    assert first.headers["cache-control"] == history._THUMB_CACHE_CONTROL
    monkeypatch.setattr(history._db, "readable_history_render_hash", lambda *_: "rh2:abc")
    monkeypatch.setattr(history._db, "get_items", lambda *_: (_ for _ in ()).throw(AssertionError("SVG read")))
    second = history.api_history_svg("work", profile="display", actor={"id": "u"}, request=_request(first.headers["etag"]))
    assert second.status_code == 304
    monkeypatch.setattr(history._db, "get_items", lambda *_: [item])
    monkeypatch.setattr(history, "_render_score_svg", lambda *args, **kwargs: ("<svg/>", None, None, None))
    other = history.api_history_svg("work", profile="editable", actor={"id": "u"}, request=_request(first.headers["etag"]))
    assert "etag" not in other.headers


def test_large_gzip_matches_previous_bytes_and_runs_in_worker(monkeypatch):
    monkeypatch.setattr("gzip.time.time", lambda: 1234567890)
    body = bytes(range(256)) * 5000
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body})
    original = _FlushingGZipResponder(app, 500, compresslevel=9)
    expected = original.apply_compression(body, more_body=False)
    responder = _FlushingGZipResponder(app, 500, compresslevel=9)
    worker_ids = []
    method = responder.apply_compression
    def record(*args, **kwargs):
        worker_ids.append(threading.get_ident())
        return method(*args, **kwargs)
    responder.apply_compression = record
    messages = []
    async def send(message):
        messages.append(message)
    async def run():
        await responder({"type": "http"}, lambda: None, send)
    asyncio.run(run())
    assert messages[-1]["body"] == expected
    assert worker_ids and worker_ids[0] != threading.get_ident()
