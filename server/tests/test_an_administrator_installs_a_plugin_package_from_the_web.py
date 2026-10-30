"""V2 plugin packages pass three checks before becoming new-work vocabulary."""

from __future__ import annotations

import base64
import copy
import io
import json
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inku_server import db
from inku_server.api import app
from inku_server.plugins import PLUGIN_PACKAGE_MANAGER
from inku_server.plugins.packages import package_core

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _guide(guide: str = "PLUGIN.ja.md") -> dict:
    text = (ROOT / guide).read_text(encoding="utf-8")
    section = text[text.index("### 5.1"):]
    start = section.index("```json") + 7
    return json.loads(section[start:section.index("```", start)])


def _guide_object_definition(guide: str) -> dict:
    text = (ROOT / guide).read_text(encoding="utf-8")
    section = text[text.index("## 2."):text.index("## 3.")]
    start = section.index("```json") + 7
    return json.loads(section[start:section.index("```", start)])


@pytest.fixture(autouse=True)
def package_directory(tmp_path, monkeypatch):
    directory = tmp_path / "plugin-packages"
    monkeypatch.setattr(PLUGIN_PACKAGE_MANAGER, "directory", directory)
    monkeypatch.setattr(PLUGIN_PACKAGE_MANAGER, "_signature", None)
    yield directory
    PLUGIN_PACKAGE_MANAGER._signature = None


def _user(groups):
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"pkg-{suffix}")
    user = db.add_user(username=f"pkg-{suffix}", email=f"pkg-{suffix}@example.test",
                       password="password-123", permission_groups=groups, group_id=group["id"])
    token = db.create_session(user["id"])
    return {"Authorization": f"Bearer {token}"}, user, group, token


@pytest.fixture
def admin():
    headers, user, group, token = _user(["admins"])
    yield headers
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


@pytest.fixture
def reader():
    headers, user, group, token = _user(["users"])
    yield headers
    db.delete_session(token)
    db.delete_user(user["id"])
    db.delete_user_group(group["id"])


def _check(headers, package):
    response = client.post("/api/plugins/packages/validate", headers=headers,
                           json={"document": json.dumps(package, ensure_ascii=False)})
    assert response.status_code == 200, response.text
    return response.json()


def _codes(report):
    return {(item["path"], item["code"]) for item in
            [*report.get("problems", []), *(p for word in report.get("words", []) for p in word["problems"])]}


@pytest.mark.parametrize("guide", ["PLUGIN.ja.md", "PLUGIN.md"])
def test_the_guide_file_passes_as_it_is(admin, guide):
    report = _check(admin, _guide(guide))
    assert report["ok"] is True, report
    assert report["words"][0]["qualified_name"] == "Sky.Stars"
    assert report["words"][0]["aliases"] == []
    assert report["words"][0]["note_ja"] == "夜空に黄色い星を描く。"
    assert "summary_ja" not in report["words"][0]


@pytest.mark.parametrize("guide, language, example", [
    ("PLUGIN.ja.md", "ja", "中心に、｛星｝を3個置く。"),
    ("PLUGIN.md", "en", "Place 3 {stars} at the center."),
])
def test_the_guide_object_example_compiles_without_diagnostics(admin, guide, language, example):
    text = (ROOT / guide).read_text(encoding="utf-8")
    assert f"`{example}`" in text[text.index("## 2."):text.index("## 3.")]
    package = _guide(guide)
    package["words"][0]["definition"] = _guide_object_definition(guide)
    package["words"][0][f"example_{language}"] = example
    report = _check(admin, package)
    assert report["ok"] is True, _codes(report)
    assert not _codes(report), _codes(report)


def test_bundled_v2_leaves_pass_shape_definition_and_real_example_drawings(admin):
    bundle = package_core({"action": "bundled_nature"})
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("package.json", bundle["text"])
        for name, encoded in bundle["pictures"].items():
            zipped.writestr(name, base64.b64decode(encoded))
    response = client.post("/api/plugins/packages/validate", headers=admin,
                           json={"archive": base64.b64encode(archive.getvalue()).decode("ascii")})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["ok"] is True, report
    assert len(report["words"]) == 7
    assert all(not word["problems"] for word in report["words"])


def test_v1_file_is_refused_and_a_stored_copy_is_listed_rejected(admin, package_directory):
    package = _guide()
    package["schema"] = "inku.plugin-package.v1"
    report = _check(admin, package)
    assert ("schema", "rewrite_as_v2") in _codes(report)
    target = package_directory / "Sky.night"
    target.mkdir(parents=True)
    (target / "package.json").write_text(json.dumps(package), encoding="utf-8")
    listed = client.get("/api/plugins", headers=admin).json()["items"]
    rejected = next(item for item in listed if item["id"] == "Sky.night")
    assert rejected["status"] == "rejected"
    assert "rewrite_as_v2" in " ".join(rejected["reasons"])
    assert (target / "package.json").is_file()


def test_note_definition_and_example_errors_are_named(admin):
    package = _guide()
    word = package["words"][0]
    word.pop("note_ja")
    word.pop("note_en")
    word["definition"]["schema"] = "inku.macro-definition.v1"
    word["example_ja"] = "Sky.星を置く。"
    report = _check(admin, package)
    codes = _codes(report)
    assert ("words[0].note_ja", "no_note") in codes
    assert ("words[0].definition.schema", "definition_requires_v2") in codes
    assert ("words[0].example_ja", "example_without_name") in codes


def test_visible_names_are_checked_even_when_an_installed_package_is_disabled(admin):
    package = _guide()
    assert client.post("/api/plugins/packages", headers=admin, json={"document": json.dumps(package)}).status_code == 200
    assert client.put("/api/plugins/Sky.night/enabled", headers=admin, json={"enabled": False}).status_code == 200
    other = copy.deepcopy(package)
    other["name"] = "other"
    other["words"][0]["definition"]["id"] = "OtherStars"
    report = _check(admin, other)
    assert any(code == "name_taken" for _path, code in _codes(report))


def test_install_replace_disable_enable_and_delete(admin, reader, package_directory):
    package = _guide()
    body = {"document": json.dumps(package, ensure_ascii=False)}
    installed = client.post("/api/plugins/packages", headers=admin, json=body)
    assert installed.status_code == 200, installed.text
    assert installed.json()["id"] == "Sky.night"
    assert client.post("/api/plugins/packages", headers=admin, json=body).status_code == 409
    assert client.post("/api/plugins/packages", headers=admin, json={**body, "replace": True}).status_code == 200
    entries = client.get("/api/saijiki", headers=reader).json()["plugins"]
    word = next(entry for entry in entries if entry["qualified_name"] == "Sky.Stars")
    assert word["surface_ja"] == ["星"] and word["word_kind"] == "object"
    assert word["written_ja"] == "｛星｝"
    assert word["preview_url"]
    assert client.get(word["preview_url"], headers=reader).headers["content-type"] == "image/png"
    assert client.put("/api/plugins/Sky.night/enabled", headers=admin, json={"enabled": False}).json()["status"] == "disabled"
    assert all(item["qualified_name"] != "Sky.Stars" for item in
               client.get("/api/saijiki", headers=reader).json()["plugins"])
    assert client.put("/api/plugins/Sky.night/enabled", headers=admin, json={"enabled": True}).status_code == 200
    assert client.delete("/api/plugins/Sky.night", headers=admin).status_code == 200
    assert not (package_directory / "Sky.night").exists()


def test_exported_zip_passes_v2_check(admin):
    package = _guide()
    assert client.post("/api/plugins/packages", headers=admin,
                       json={"document": json.dumps(package, ensure_ascii=False)}).status_code == 200
    exported = client.get("/api/plugins/Sky.night/export", headers=admin)
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        stored = json.loads(archive.read("package.json"))
    assert stored["schema"] == "inku.plugin-package.v2"
    assert stored["words"][0]["preview"].endswith(".png")
    checked = client.post("/api/plugins/packages/validate", headers=admin,
                          json={"archive": base64.b64encode(exported.content).decode()})
    assert checked.status_code == 200 and checked.json()["ok"], checked.text


def test_both_example_packages_pass_the_full_check(admin):
    for name in ("sky-nihonga", "water-nihonga"):
        data = (ROOT / "docs/plugins" / f"{name}.zip").read_bytes()
        checked = client.post("/api/plugins/packages/validate", headers=admin,
                              json={"archive": base64.b64encode(data).decode()})
        assert checked.status_code == 200 and checked.json()["ok"], (name, checked.text)


def test_only_an_administrator_may_change_packages(reader):
    body = {"document": json.dumps(_guide(), ensure_ascii=False)}
    assert client.post("/api/plugins/packages/validate", headers=reader, json=body).status_code == 403
    assert client.post("/api/plugins/packages", headers=reader, json=body).status_code == 403
    assert client.delete("/api/plugins/Sky.night", headers=reader).status_code == 403
