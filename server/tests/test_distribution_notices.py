"""The About reader can fetch the exact bundled UniDic notice, not arbitrary files."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from inku_server import distribution_notices as notices
from inku_server.api_core.routers.public import router


def test_bundled_notices_are_public_exact_and_fixed(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    monkeypatch.setattr(notices, "_CONTAINER_LICENSES", tmp_path / "sqlite")
    monkeypatch.setattr(notices, "_RUST_NOTICES", tmp_path / "rust.txt")

    catalog = client.get("/api/notices")
    assert catalog.status_code == 200
    items = {item["id"]: item for item in catalog.json()["components"]}
    assert set(items) == {"server", "sudachidict-small", "cmudict", "noto-serif-jp"}
    assert client.get("/api/notices/server").content == (Path(__file__).parents[1] / "THIRD_PARTY_NOTICES.md").read_bytes()
    assert items["sudachidict-small"]["version"] == "20260723.1"
    assert "UniDic" in items["sudachidict-small"]["name"]
    expected = Path(__file__).parents[1] / "src/inku_server/notices/sudachidict-small-20260723.1-LEGAL.txt"
    response = client.get("/api/notices/sudachidict-small")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.content == expected.read_bytes()
    assert b"The UniDic Consortium" in response.content
    assert b"THIS SOFTWARE IS PROVIDED" in response.content
    assert client.get("/api/notices/unknown").status_code == 404
    assert client.get("/api/notices/..%2F..%2F.env").status_code == 404
    assert client.get("/api/notices/rust").status_code == 404

    (tmp_path / "sqlite").mkdir()
    (tmp_path / "sqlite/Ubuntu-libsqlite3-copyright.txt").write_bytes(b"SQLite copyright\n")
    (tmp_path / "sqlite/CPython-LICENSE.txt").write_bytes(b"CPython license\n")
    (tmp_path / "rust.txt").write_bytes(b"Rust crate notices\n")
    packaged = {item["id"] for item in client.get("/api/notices").json()["components"]}
    assert packaged == set(items) | {"sqlite", "cpython", "rust"}
    assert client.get("/api/notices/rust").content == b"Rust crate notices\n"
