"""A plugin word can declare the artwork its saijiki preview shows.

The panel shows the same four things for a plugin word as for a built-in one:
name, effect, example, artwork. The document already carried the first three --
the qualified name, the note, the firing phrases -- and `preview:` names the
fourth. The picture is a raster served by its own route rather than carried in
the saijiki payload: it is baked from the word's own expansion and does not
belong inside a response the browser asks for on every hydration.

Serving it as PNG in an <img> is also what keeps it inert. A document is not
trusted to put markup on screen, so the refusals below are part of the feature
rather than hardening added afterwards.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.plugins.document_format import (
    DOCUMENT_PLUGIN_MANAGER,
    MAX_PREVIEW_BYTES,
    entry_preview_path,
    parse_plugin_document,
    preview_path_for_qualified_name,
)

client = TestClient(app)

PLUGIN_DOC = Path(__file__).resolve().parents[1] / "plugins" / "nature-leaves.inku-plugin.md"

# A 1x1 PNG, so a temporary document can declare something real.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000100ffff03000006"
    "000557bfabd40000000049454e44ae426082"
)


@pytest.fixture
def auth_headers():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"preview-{suffix}")
    user = db.add_user(
        username=f"preview-{suffix}",
        email=f"preview-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    yield {"Authorization": f"Bearer {token}"}
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def _shipped_document():
    return parse_plugin_document(
        PLUGIN_DOC.read_text(encoding="utf-8"), source_path=str(PLUGIN_DOC)
    )


def _document_with_preview(tmp_path: Path, declared: str):
    """A one-word document in `tmp_path` whose entry declares `declared`."""
    text = (
        "---\n"
        "namespace: Probe\n"
        "name: probe\n"
        "version: 0.1.0\n"
        "authors: [test]\n"
        "languages: [ja]\n"
        "license: MIT\n"
        "description_ja: probe\n"
        "description_en: probe\n"
        "---\n\n"
        "## 語: 試\n\n"
        "surface_ja: 試\n"
        "fires_on_ja: 試\n"
        "note_ja: probe\n"
        f"preview: {declared}\n\n"
        "### 展開 (ja)\n\n"
        "円を置く。\n"
    )
    path = tmp_path / "probe.inku-plugin.md"
    path.write_text(text, encoding="utf-8")
    return parse_plugin_document(text, source_path=str(path))


# ------------------------------------------------- the declaration is parsed


def test_the_document_declares_a_picture_per_word():
    document = _shipped_document()
    assert document.entries, "the shipped document has no words"
    for entry in document.entries:
        assert entry.preview, f"{entry.heading} declares no preview"
        assert entry.preview.endswith(".png")


def test_a_word_without_the_key_simply_has_none(tmp_path):
    text = PLUGIN_DOC.read_text(encoding="utf-8").replace("preview: nature-leaves/wakaba.png\n", "")
    path = tmp_path / "nature-leaves.inku-plugin.md"
    path.write_text(text, encoding="utf-8")
    document = parse_plugin_document(text, source_path=str(path))
    first = next(e for e in document.entries if e.heading == "若葉")
    assert first.preview == ""
    assert entry_preview_path(document, first) is None


# ---------------------------------------------------- both scales are shipped


def test_every_shipped_word_has_artwork_at_both_scales():
    document = _shipped_document()
    for entry in document.entries:
        assert entry_preview_path(document, entry) is not None, entry.heading
        assert entry_preview_path(document, entry, hidpi=True) is not None, entry.heading


def test_the_hidpi_sibling_is_found_by_name_not_declared():
    document = _shipped_document()
    entry = document.entries[0]
    one = entry_preview_path(document, entry)
    two = entry_preview_path(document, entry, hidpi=True)
    assert one is not None and two is not None
    assert two.name == one.name.replace(".png", "@2x.png")


def test_a_word_with_no_hidpi_sibling_still_has_the_one_size(tmp_path):
    (tmp_path / "only.png").write_bytes(TINY_PNG)
    document = _document_with_preview(tmp_path, "only.png")
    entry = document.entries[0]
    assert entry_preview_path(document, entry) is not None
    # None, not the 1x file: the caller must be able to tell "no HiDPI" from
    # "no preview", or it would advertise a 2x that is really the 1x again.
    assert entry_preview_path(document, entry, hidpi=True) is None


# ------------------------------------------------------------- what is refused


@pytest.mark.parametrize(
    "declared",
    [
        "../escape.png",  # out of the document's own directory
        "nature-leaves/../../escape.png",  # traversal spelled the long way
    ],
)
def test_a_path_outside_the_document_directory_is_refused(tmp_path, declared):
    (tmp_path.parent / "escape.png").write_bytes(TINY_PNG)
    document = _document_with_preview(tmp_path, declared)
    assert entry_preview_path(document, document.entries[0]) is None


def test_an_absolute_path_is_refused_even_when_the_file_is_there(tmp_path):
    """The file has to exist, or the refusal proves nothing.

    Naming an absolute path that is not there is refused by the existence check
    instead, and the guard this is about is never the reason -- measured: with
    the traversal check removed, an absolute path to a missing file still came
    back None.
    """
    outside = tmp_path.parent / "escape.png"
    outside.write_bytes(TINY_PNG)
    document = _document_with_preview(tmp_path, str(outside))
    assert outside.is_file()
    assert entry_preview_path(document, document.entries[0]) is None


def test_a_name_that_is_not_png_is_refused(tmp_path):
    (tmp_path / "art.svg").write_bytes(b"<svg></svg>")
    document = _document_with_preview(tmp_path, "art.svg")
    assert entry_preview_path(document, document.entries[0]) is None


def test_a_file_over_the_cap_is_refused(tmp_path):
    (tmp_path / "big.png").write_bytes(TINY_PNG + b"\0" * (MAX_PREVIEW_BYTES + 1))
    document = _document_with_preview(tmp_path, "big.png")
    assert entry_preview_path(document, document.entries[0]) is None


def test_a_declared_file_that_is_not_there_is_refused(tmp_path):
    document = _document_with_preview(tmp_path, "missing.png")
    assert entry_preview_path(document, document.entries[0]) is None


def test_a_name_that_matches_no_loaded_word_finds_nothing():
    assert preview_path_for_qualified_name("Nope.Nope") is None
    assert preview_path_for_qualified_name("") is None


# ----------------------------------------------------------------- the route


def test_the_saijiki_payload_points_at_the_picture_instead_of_carrying_it(auth_headers):
    payload = client.get("/api/saijiki?lang=ja", headers=auth_headers).json()
    plugins = payload["plugins"]
    assert plugins, "no plugin words are loaded"
    for entry in plugins:
        assert entry["preview_url"], entry["qualified_name"]
        assert entry["preview_url_2x"], entry["qualified_name"]
        # The bytes must not ride along: that is the whole reason for the route.
        assert "preview_svg" not in entry
        assert not any(isinstance(v, str) and v.startswith("data:") for v in entry.values())


def test_the_route_serves_each_scale(auth_headers):
    payload = client.get("/api/saijiki?lang=ja", headers=auth_headers).json()
    entry = payload["plugins"][0]
    one = client.get(entry["preview_url"], headers=auth_headers)
    two = client.get(entry["preview_url_2x"], headers=auth_headers)
    assert one.status_code == 200 and one.headers["content-type"] == "image/png"
    assert two.status_code == 200 and two.headers["content-type"] == "image/png"
    # The HiDPI file is a different, larger picture -- not the same bytes twice.
    assert len(two.content) > len(one.content)


def test_the_route_refuses_a_word_it_does_not_have(auth_headers):
    assert client.get(
        "/api/saijiki/plugin-preview", params={"name": "Nope.Nope"}, headers=auth_headers
    ).status_code == 404


def test_the_route_refuses_a_scale_it_does_not_serve(auth_headers):
    payload = client.get("/api/saijiki?lang=ja", headers=auth_headers).json()
    name = payload["plugins"][0]["qualified_name"]
    assert client.get(
        "/api/saijiki/plugin-preview", params={"name": name, "scale": "3"}, headers=auth_headers
    ).status_code == 422


def test_the_route_needs_a_session():
    assert client.get(
        "/api/saijiki/plugin-preview", params={"name": "Nature.若葉"}
    ).status_code == 401


# ------------------------------------------- the prose that makes one expand


def test_a_plugin_expands_on_prose_and_not_on_the_ddl():
    """The reason `fires_on` exists, measured on the mechanism itself.

    Whether a plugin expands is decided by the prose (`source_text`); the DDL is
    only hashed for the seed. A DDL that spells a plugin word therefore expands
    to nothing on its own, which is what made every drawing-from-DDL bake come
    back empty before the request carried the prose.
    """
    without = DOCUMENT_PLUGIN_MANAGER.expand("落葉", source_text=None, lang="ja", seed_text="落葉")
    with_prose = DOCUMENT_PLUGIN_MANAGER.expand(
        "落葉", source_text="落葉", lang="ja", seed_text="落葉"
    )

    assert len(without.provenance) == 0
    assert [p["plugin_term"] for p in with_prose.provenance] == ["Nature.落葉"]
    # The expansion is really in the DDL, not only in the provenance.
    assert with_prose.ddl != "落葉"


def test_compose_hands_the_declared_prose_to_the_expansion():
    """The wiring, in the one region that carries it.

    Read narrowly rather than over the whole module: a match anywhere else in
    the file would satisfy a check that is meant to be about this call.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "inku_server"
        / "api_core"
        / "routers"
        / "render.py"
    ).read_text(encoding="utf-8")

    detail = source[source.index("def _call_compose_detail") :]
    detail = detail[: detail.index("\ndef ", 1)]
    assert "source_text=plugin_fires_on or original_description," in detail

    compose = source[source.index("def api_compose") :]
    compose = compose[: compose.index("\ndef ", 1)]
    assert 'plugin_fires_on=(req.fires_on or "").strip() or None,' in compose
