"""T-86: the CLI sends its session when it asks for the color catalogs.

I-086 moved `GET /api/color-catalogs` behind the authorization guard, so the
one CLI caller that had opted out of sending credentials (`auth=False`) has to
stop opting out or every `inku-cli` run that resolves a catalog turns into a
401.

The check runs the request and reads what arrived, rather than grepping the
source for the absence of `auth=False`: a string that is not there says nothing
about what the client puts on the wire, and the flag could come back by a
different name or from a caller further up. A stub server records the request
headers, so what is asserted is the credential the request actually carried.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inku_cli.cli import ApiClient, _fetch_color_catalogs  # noqa: E402

_TOKEN = "a-session-the-cli-stored"

_CATALOGS = {
    "default_catalog_id": "default",
    "catalogs": [{"id": "default", "name": "Default"}],
}


class _Recorder(BaseHTTPRequestHandler):
    """Answers any GET with a catalog list and files the headers it was sent."""

    seen: list[dict[str, str]] = []

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        type(self).seen.append({key.lower(): value for key, value in self.headers.items()})
        body = json.dumps(_CATALOGS).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # keep the test output quiet
        return


@pytest.fixture
def recording_server():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    _Recorder.seen = []
    server = HTTPServer(("127.0.0.1", port), _Recorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", _Recorder.seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_t86_fetching_the_catalogs_carries_the_session(recording_server) -> None:
    base, seen = recording_server
    client = ApiClient(base, token=_TOKEN)

    result = _fetch_color_catalogs(client)

    assert result["default_catalog_id"] == "default"
    assert len(seen) == 1, "the helper should have made exactly one request"
    assert seen[0].get("authorization") == f"Bearer {_TOKEN}", (
        "the catalog list is behind the guard now, so the request has to carry "
        "the stored session"
    )


def test_t86_control_the_recorder_would_notice_an_unauthenticated_request(
    recording_server,
) -> None:
    """The control for the check above.

    A stub that reported the header no matter what was sent would pass the
    first test against the very `auth=False` this contract removed. Send one
    request each way through the same client and recorder: the header has to be
    there in one and absent in the other, or the recorder is measuring nothing.
    """
    base, seen = recording_server
    client = ApiClient(base, token=_TOKEN)

    client.request("GET", "/api/color-catalogs")
    client.request("GET", "/api/color-catalogs", auth=False)

    assert len(seen) == 2
    assert seen[0].get("authorization") == f"Bearer {_TOKEN}"
    assert "authorization" not in seen[1]
