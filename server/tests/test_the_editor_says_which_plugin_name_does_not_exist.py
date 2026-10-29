"""The editor can only name the word behind a wrong qualified name if the
server hands it the firing phrases.

`Nature.菖蒲` is not an unknown word: `菖蒲` is a real firing phrase of
`Nature.下草`, and only the qualified name is wrong. The expansion layer drops
such a reference silently, so the client has to be able to say "drop the
`Nature.` and it fires as 下草" -- which it cannot do unless `fires_on_*`
travels with the entry list.

Two transports carry that list and both are checked here: `/api/plugins`
(the admin-facing list named by the contract) and `/api/saijiki` (the list the
DDL editor actually holds -- `+page.svelte` hydrates `pluginEntries` from it).
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app

client = TestClient(app)

_LOADER_KEYS = ("qualified_name", "surface_ja", "surface_en", "note_ja", "note_en")


def _auth() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"plug-{suffix}")
    user = db.add_user(
        username=f"plug-{suffix}",
        email=f"plug-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return {"Authorization": f"Bearer {token}"}


def _plugins_entries(headers: dict[str, str]) -> list[dict]:
    response = client.get("/api/plugins", headers=headers)
    assert response.status_code == 200, response.text
    entries: list[dict] = []
    for item in response.json()["items"]:
        entries.extend(item.get("entries", []))
    return entries


def _saijiki_entries(headers: dict[str, str]) -> list[dict]:
    response = client.get("/api/saijiki?lang=ja", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["plugins"]


def _by_name(entries: list[dict]) -> dict[str, dict]:
    return {entry["qualified_name"]: entry for entry in entries}


def test_the_list_api_carries_v2_names_without_document_firing_phrases():
    """The v2 word names its own visible spellings; the document triggers retired."""
    headers = _auth()
    entries = _by_name(_plugins_entries(headers))
    assert entries, "no plugin entries were served"
    for entry in entries.values():
        assert not {"aliases", "fires_on_ja", "fires_on_en"} & entry.keys()
    undergrowth = entries.get("Nature.Undergrowth")
    assert undergrowth is not None, sorted(entries)
    assert undergrowth["word_kind"] == "scene"
    assert undergrowth["surface_ja"][0] == "下草"
    assert undergrowth["written_ja"] == "｛下草｝"


def test_the_editors_own_list_carries_v2_names_too():
    """The editor hydrates from /api/saijiki, not /api/plugins."""
    headers = _auth()
    entries = _by_name(_saijiki_entries(headers))
    undergrowth = entries.get("Nature.Undergrowth")
    assert undergrowth is not None, sorted(entries)
    assert not {"aliases", "fires_on_ja", "fires_on_en"} & undergrowth.keys()
    assert undergrowth["written_ja"] == "｛下草｝"


def test_no_existing_key_was_dropped_or_renamed():
    """T-2: the addition is additive on both transports."""
    headers = _auth()
    for entries in (_plugins_entries(headers), _saijiki_entries(headers)):
        assert entries
        for entry in entries:
            for key in _LOADER_KEYS:
                assert key in entry, f"{key} missing from {sorted(entry)}"
            assert isinstance(entry["surface_ja"], list)
            assert isinstance(entry["surface_en"], list)
            assert isinstance(entry["note_ja"], str)
            assert isinstance(entry["note_en"], str)


_WEB_PLUGIN_NAMES = (
    Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "plugin-names.ts"
)


@pytest.mark.skipif(
    not _WEB_PLUGIN_NAMES.exists(),
    reason="web sources are not deployed beside the server",
)
def test_the_editor_reads_the_keys_this_server_writes():
    """The reader and the writer are in different languages and repositories
    halves; only the key names hold them together. A rename on either side
    would leave the editor silently unable to name the word."""
    source = _WEB_PLUGIN_NAMES.read_text(encoding="utf-8")
    assert not re.findall(r"fires_on_[a-z]{2}", source)
    keys = ["surface_ja", "surface_en", "written_ja", "written_en"]
    headers = _auth()
    for entries in (_plugins_entries(headers), _saijiki_entries(headers)):
        for entry in entries:
            for key in keys:
                assert key in entry, f"{key} missing from {sorted(entry)}"


def test_both_transports_agree_on_the_visible_names():
    """The settings and editor use the same names and kind."""
    headers = _auth()
    from_plugins = _by_name(_plugins_entries(headers))
    from_saijiki = _by_name(_saijiki_entries(headers))
    assert set(from_saijiki) <= set(from_plugins)
    for name, entry in from_saijiki.items():
        for field in ("surface_ja", "surface_en", "written_ja", "written_en", "word_kind"):
            assert entry[field] == from_plugins[name][field], name


def test_editor_uses_the_shared_core_for_braced_and_legacy_calls():
    headers = _auth()
    source = "｛若葉｝。Nature.YoungLeaves。｛若刃｝。{}。{\"x\":1}。"
    response = client.post("/api/pipeline/plugin-calls", headers=headers, json={"source": source, "language": "ja"})
    assert response.status_code == 200, response.text
    calls = response.json()["calls"]
    assert [(call["text"], call["status"]) for call in calls] == [
        ("｛若葉｝", "resolved"), ("Nature.YoungLeaves", "resolved"), ("｛若刃｝", "plugin_name_mismatch")]
    assert calls[0]["qualified_name"] == "Nature.YoungLeaves"
    count = client.post("/api/pipeline/plugin-calls", headers=headers,
                        json={"source": "13枚の｛若葉｝。", "language": "ja"})
    assert count.status_code == 200, count.text
    assert [call["status"] for call in count.json()["calls"]] == ["plugin_count_out_of_range"]
