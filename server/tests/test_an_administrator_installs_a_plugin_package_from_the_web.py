"""An administrator adds, checks, and removes a plugin package from the Web.

The package is one `inku.plugin-package.v1` JSON file. Checking it reports
every problem with its place in the file; installing it makes its words drawable
in new works and shows them in the Saijiki, with a picture drawn from each
word's example that the administrator may replace.
"""

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
from PIL import Image

from inku_server import db
from inku_server.api import app
from inku_server.plugins import PLUGIN_PACKAGE_MANAGER

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]


def _sky_stars() -> dict:
    """The worked example of PLUGIN.ja.md §2, read from the guide itself."""
    text = (ROOT / "PLUGIN.ja.md").read_text(encoding="utf-8")
    start = text.index("```json", text.index("## 2.")) + len("```json")
    return json.loads(text[start:text.index("```", start)])


def _package(**changes) -> dict:
    package = {
        "schema": "inku.plugin-package.v1",
        "namespace": "Sky",
        "name": "night",
        "version": "1.0.0",
        "description_ja": "夜空の語。",
        "words": [{
            "definition": _sky_stars(),
            "summary_ja": "空の上半分に、黄色の星を散らす。",
            "summary_en": "Scatters yellow stars over the upper half.",
            "note_ja": "夜の空に小さな星。",
            "example_ja": "5個のSky.星。",
            "example_en": "5 Sky.Stars.",
        }],
    }
    package.update(changes)
    return package


def _document(package: dict) -> str:
    return json.dumps(package, ensure_ascii=False)


@pytest.fixture(autouse=True)
def package_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(PLUGIN_PACKAGE_MANAGER, "directory", tmp_path / "plugin-packages")
    monkeypatch.setattr(PLUGIN_PACKAGE_MANAGER, "_signature", None)
    yield tmp_path / "plugin-packages"
    PLUGIN_PACKAGE_MANAGER._signature = None


def _user(groups: list[str]):
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"pkg-{suffix}")
    user = db.add_user(username=f"pkg-{suffix}", email=f"pkg-{suffix}@example.test", password="password-123",
                       permission_groups=groups, group_id=group["id"])
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


def _check(headers, package) -> dict:
    response = client.post("/api/plugins/packages/validate", json={"document": _document(package)}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _install(headers, package, **extra):
    return client.post("/api/plugins/packages", json={"document": _document(package), **extra}, headers=headers)


def _codes(report: dict) -> set[tuple[str, str]]:
    found = {(p["path"], p["code"]) for p in report["problems"]}
    for word in report["words"]:
        found |= {(p["path"], p["code"]) for p in word["problems"]}
    return found


def test_a_sound_package_checks_clean_shows_its_picture_and_installs_nothing(admin, package_directory):
    report = _check(admin, _package())
    assert report["ok"] is True, report
    assert report["id"] == "Sky.night" and report["exists"] is False
    [word] = report["words"]
    assert word["qualified_name"] == "Sky.Stars" and word["aliases"] == ["Sky.星"]
    assert word["example_ja"] == "5個のSky.星。" and word["problems"] == []
    picture = Image.open(io.BytesIO(base64.b64decode(word["preview_png"].split(",", 1)[1])))
    assert picture.size == (432, 184)
    assert not package_directory.exists()


@pytest.mark.parametrize("guide", ["PLUGIN.ja.md", "PLUGIN.md"])
def test_the_file_the_guide_shows_passes_as_it_is(admin, guide):
    """PLUGIN §5.1 says its file can be saved and added as it is."""
    text = (ROOT / guide).read_text(encoding="utf-8")
    section = text[text.index("### 5.1"):]
    start = section.index("```json") + len("```json")
    report = _check(admin, json.loads(section[start:section.index("```", start)]))
    assert report["ok"] is True, report


def test_every_shape_problem_is_named_with_its_place_in_one_answer(admin):
    word = _package()["words"][0]
    broken = _package(schema="inku.plugin-package.v0", extra=1, words=[
        {**word, "definition": {**word["definition"], "namespace": "Moon"}, "summary_ja": "", "summary_en": "",
         "colour": "red"},
    ])
    report = _check(admin, broken)
    assert report["ok"] is False
    assert {
        ("schema", "wrong_schema"),
        ("extra", "unknown_field"),
        ("words[0].colour", "unknown_field"),
        ("words[0].definition.namespace", "namespace_differs_from_package"),
        ("words[0].summary_ja", "no_summary"),
    } <= _codes(report)


def test_a_shape_problem_does_not_hide_the_definition_and_example_problems(admin):
    """Found on 5173: a missing summary used to stop the check before the core
    and the examples, so fixing one file took one upload per stage."""
    package = _package()
    word = package["words"][0]
    word.update(summary_ja="", summary_en="", example_ja="12個のSky.星。")
    report = _check(admin, package)
    assert report["ok"] is False
    assert ("words[0].summary_ja", "no_summary") in _codes(report)
    assert ("words[0].example_ja", "macro_binding_count_out_of_range") in _codes(report)
    word["definition"]["body"][0]["body"][0]["body"][0]["fields"]["color"]["id"] = "pink"
    codes = {code for _path, code in _codes(_check(admin, package))}
    assert {"no_summary", "unknown_semantic_id"} <= codes


def test_a_word_without_a_definition_keeps_the_others_checked_at_their_own_place(admin):
    package = _package()
    package["words"] = [{"summary_ja": "定義が無い"}, package["words"][0]]
    report = _check(admin, package)
    assert ("words[0].definition", "not_an_object") in _codes(report)
    [stars] = report["words"]
    assert stars["qualified_name"] == "Sky.Stars" and stars["problems"] == [] and stars["preview_png"]
    assert report["ok"] is False


def test_not_json_says_where_it_broke(admin):
    response = client.post("/api/plugins/packages/validate", json={"document": '{"schema": '}, headers=admin)
    [problem] = response.json()["problems"]
    assert problem["code"] == "invalid_json" and "line 1" in problem["detail"]


def test_a_definition_the_core_refuses_is_named_by_its_field(admin):
    package = _package()
    body = package["words"][0]["definition"]["body"]
    emit = body[0]["body"][0]["body"][0]
    emit["fields"]["color"]["id"] = "pink"
    report = _check(admin, package)
    assert report["ok"] is False
    [problem] = report["words"][0]["problems"]
    assert problem["code"] == "unknown_semantic_id"
    assert problem["path"].startswith("words[0].definition")


def test_an_example_that_does_not_draw_says_why(admin):
    package = _package()
    package["words"][0]["example_ja"] = "12個のSky.星。"
    report = _check(admin, package)
    assert report["ok"] is False
    assert ("words[0].example_ja", "macro_binding_count_out_of_range") in _codes(report)
    assert report["words"][0]["preview_png"] == ""


def test_a_word_may_not_take_a_name_another_plugin_holds(admin):
    package = _package(namespace="Nature")
    definition = copy.deepcopy(_sky_stars())
    definition.update(namespace="Nature", heading="YoungLeaves", aliases=["若葉"])
    package["words"] = [{**package["words"][0], "definition": definition, "example_ja": "Nature.若葉。",
                         "example_en": "Nature.YoungLeaves."}]
    report = _check(admin, package)
    assert ("words[0].definition", "name_taken") in _codes(report)


def test_an_installed_package_draws_in_new_works_and_shows_in_the_saijiki(admin, reader):
    installed = _install(admin, _package())
    assert installed.status_code == 200, installed.text
    assert installed.json()["kind"] == "package" and installed.json()["enabled"] is True

    listed = client.get("/api/plugins", headers=reader).json()["items"]
    assert [item["id"] for item in listed if item["kind"] == "package"] == ["Sky.night"]

    words = {entry["qualified_name"]: entry for entry in client.get("/api/saijiki", headers=reader).json()["plugins"]}
    stars = words["Sky.Stars"]
    assert stars["example_ja"] == "5個のSky.星。" and stars["note_ja"] == "夜の空に小さな星。"
    assert "v=" in stars["preview_url"] and stars["preview_url_2x"]
    picture = client.get(stars["preview_url"], headers=reader)
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(picture.content)).size == (216, 92)

    drawn = client.post("/api/compose", json={"ddl": "5個のSky.星。"}, headers=admin)
    assert drawn.status_code == 200, drawn.text
    assert len(drawn.json()["score"]["instructions"]) == 5


def test_a_switched_off_package_leaves_new_works_and_the_saijiki(admin, reader):
    assert _install(admin, _package()).status_code == 200
    off = client.put("/api/plugins/Sky.night/enabled", json={"enabled": False}, headers=admin)
    assert off.status_code == 200 and off.json()["enabled"] is False
    assert "Sky.Stars" not in {e["qualified_name"] for e in client.get("/api/saijiki", headers=reader).json()["plugins"]}
    assert client.post("/api/compose", json={"ddl": "5個のSky.星。"}, headers=admin).status_code == 422
    # The settings list still shows the switched-off word's picture.
    assert client.get("/api/saijiki/plugin-preview?name=Sky.Stars&scale=1", headers=admin).status_code == 200
    assert client.put("/api/plugins/Sky.night/enabled", json={"enabled": True}, headers=admin).status_code == 200
    assert client.post("/api/compose", json={"ddl": "5個のSky.星。"}, headers=admin).status_code == 200


def test_the_same_package_is_replaced_only_when_asked(admin):
    assert _install(admin, _package()).status_code == 200
    again = _install(admin, _package(version="1.1.0"))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "package_exists"
    assert _check(admin, _package(version="1.1.0"))["exists"] is True
    replaced = _install(admin, _package(version="1.1.0"), replace=True)
    assert replaced.status_code == 200 and replaced.json()["version"] == "1.1.0"


def test_a_failing_package_is_not_installed(admin, package_directory):
    package = _package()
    package["words"][0]["example_ja"] = "12個のSky.星。"
    response = _install(admin, package)
    assert response.status_code == 422 and response.json()["detail"]["ok"] is False
    assert not (package_directory / "Sky.night").exists()


def _png(color: tuple[int, int, int]) -> str:
    out = io.BytesIO()
    Image.new("RGB", (300, 300), color).save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode()


def test_a_word_picture_is_replaced_kept_across_a_replace_and_put_back(admin, reader):
    assert _install(admin, _package()).status_code == 200
    replaced = client.put("/api/plugins/Sky.night/words/Stars/preview", json={"png_base64": _png((200, 0, 0))},
                          headers=admin)
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["entries"][0]["custom_preview"] is True
    entry = client.get("/api/saijiki", headers=reader).json()["plugins"][-1]
    picture = Image.open(io.BytesIO(client.get(entry["preview_url"], headers=reader).content)).convert("RGB")
    assert picture.getpixel((108, 46)) == (200, 0, 0)
    # A square picture in the wide frame is padded with its own colour, not white.
    assert picture.getpixel((4, 46)) == (200, 0, 0)

    assert _install(admin, _package(version="1.0.1"), replace=True).status_code == 200
    kept = [i for i in client.get("/api/plugins", headers=admin).json()["items"] if i["id"] == "Sky.night"][0]
    assert kept["entries"][0]["custom_preview"] is True

    back = client.delete("/api/plugins/Sky.night/words/Stars/preview", headers=admin)
    assert back.status_code == 200 and back.json()["entries"][0]["custom_preview"] is False
    not_png = client.put("/api/plugins/Sky.night/words/Stars/preview",
                         json={"png_base64": base64.b64encode(b"GIF89a").decode()}, headers=admin)
    assert not_png.status_code == 422
    assert client.put("/api/plugins/Sky.night/words/Moon/preview", json={"png_base64": _png((0, 0, 0))},
                      headers=admin).status_code == 404


# --------------------------------------------------------------------------- #
# A package as a zip with its pictures, and exporting one                      #
# --------------------------------------------------------------------------- #


def _png_bytes(color: tuple[int, int, int], size=(300, 150)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def _zip(members: dict[str, bytes | str]) -> str:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return base64.b64encode(out.getvalue()).decode()


def _with_picture(path: str = "pictures/stars.png") -> dict:
    package = _package()
    package["words"][0]["preview"] = path
    return package


def _shown(headers) -> tuple[int, int, int]:
    """The colour at the middle of the Saijiki picture of Sky.Stars."""
    entry = [e for e in client.get("/api/saijiki", headers=headers).json()["plugins"] if e["qualified_name"] == "Sky.Stars"][0]
    picture = Image.open(io.BytesIO(client.get(entry["preview_url"], headers=headers).content)).convert("RGB")
    assert picture.size == (216, 92)
    return picture.getpixel((108, 46))


def test_a_zip_gives_each_word_the_picture_it_names(admin, reader):
    archive = _zip({"package.json": _document(_with_picture()), "pictures/stars.png": _png_bytes((10, 120, 200))})
    report = client.post("/api/plugins/packages/validate", json={"archive": archive}, headers=admin).json()
    assert report["ok"] is True, report
    [word] = report["words"]
    assert word["preview_source"] == "file"
    checked = Image.open(io.BytesIO(base64.b64decode(word["preview_png"].split(",", 1)[1]))).convert("RGB")
    assert checked.getpixel((216, 92)) == (10, 120, 200)

    installed = client.post("/api/plugins/packages", json={"archive": archive}, headers=admin)
    assert installed.status_code == 200, installed.text
    assert _shown(reader) == (10, 120, 200)
    # The example is still drawn as the check of the definition.
    assert client.post("/api/compose", json={"ddl": "5個のSky.星。"}, headers=admin).status_code == 200


def test_a_picture_named_where_none_can_be_read_is_a_problem_of_that_word(admin):
    assert ("words[0].preview", "preview_needs_zip") in _codes(_check(admin, _with_picture()))

    def check_zip(members):
        return client.post("/api/plugins/packages/validate", json={"archive": _zip(members)}, headers=admin).json()

    assert ("words[0].preview", "preview_not_found") in _codes(check_zip({"package.json": _document(_with_picture())}))
    climbing = check_zip({"package.json": _document(_with_picture("../stars.png")), "../stars.png": _png_bytes((0, 0, 0))})
    assert ("words[0].preview", "invalid_preview_path") in _codes(climbing)
    not_png = check_zip({"package.json": _document(_with_picture()), "pictures/stars.png": b"GIF89a not a png"})
    assert ("words[0].preview", "not_a_png") in _codes(not_png)
    # A wrong picture does not hide whether the definition and example draw.
    assert not_png["words"][0]["preview_png"]


def test_a_zip_is_read_within_its_limits(admin):
    def check(archive: str) -> dict:
        return client.post("/api/plugins/packages/validate", json={"archive": archive}, headers=admin).json()

    assert _codes(check(base64.b64encode(b"not a zip").decode())) == {("", "invalid_zip")}
    assert _codes(check(_zip({"stars.png": _png_bytes((0, 0, 0))}))) == {("", "archive_without_package_json")}
    # A member that inflates past its limit is cut off there, whatever the zip says.
    huge = _zip({"package.json": _document(_with_picture()), "pictures/stars.png": b"\x89PNG\r\n\x1a\n" + bytes(3 * 1024 * 1024)})
    assert ("words[0].preview", "image_too_large") in _codes(check(huge))
    both = client.post("/api/plugins/packages/validate", json={"document": "{}", "archive": "AA=="}, headers=admin)
    assert both.status_code == 422


def test_an_exported_package_adds_elsewhere_with_the_picture_it_showed(admin, reader, tmp_path, monkeypatch):
    assert _install(admin, _package()).status_code == 200
    green = base64.b64encode(_png_bytes((0, 160, 60))).decode()
    assert client.put("/api/plugins/Sky.night/words/Stars/preview", json={"png_base64": green}, headers=admin).status_code == 200

    exported = client.get("/api/plugins/Sky.night/export", headers=admin)
    assert exported.status_code == 200 and exported.headers["content-type"] == "application/zip"
    assert 'filename="Sky.night-1.0.0.zip"' in exported.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        package = json.loads(archive.read("package.json"))
        assert package["words"][0]["preview"] in archive.namelist()
        assert package["words"][0]["definition"] == _sky_stars()

    # Another server: an empty package directory.
    monkeypatch.setattr(PLUGIN_PACKAGE_MANAGER, "directory", tmp_path / "elsewhere")
    monkeypatch.setattr(PLUGIN_PACKAGE_MANAGER, "_signature", None)
    archive = base64.b64encode(exported.content).decode()
    added = client.post("/api/plugins/packages", json={"archive": archive}, headers=admin)
    assert added.status_code == 200, added.text
    assert added.json()["entries"][0]["custom_preview"] is False
    assert _shown(reader) == (0, 160, 60)


def test_putting_back_returns_to_the_zip_picture_not_a_drawn_one(admin, reader):
    archive = _zip({"package.json": _document(_with_picture()), "pictures/stars.png": _png_bytes((10, 120, 200))})
    assert client.post("/api/plugins/packages", json={"archive": archive}, headers=admin).status_code == 200
    red = base64.b64encode(_png_bytes((200, 0, 0))).decode()
    assert client.put("/api/plugins/Sky.night/words/Stars/preview", json={"png_base64": red}, headers=admin).status_code == 200
    assert _shown(reader) == (200, 0, 0)
    assert client.delete("/api/plugins/Sky.night/words/Stars/preview", headers=admin).status_code == 200
    assert _shown(reader) == (10, 120, 200)


def test_only_an_administrator_exports_and_only_what_is_installed(admin, reader):
    assert client.get("/api/plugins/Sky.night/export", headers=admin).status_code == 404
    assert _install(admin, _package()).status_code == 200
    assert client.get("/api/plugins/Sky.night/export", headers=reader).status_code == 403
    assert client.get("/api/plugins/nature-leaves.inku-plugin.md/export", headers=admin).status_code == 404


def test_a_deleted_package_is_gone(admin, reader, package_directory):
    assert _install(admin, _package()).status_code == 200
    assert client.delete("/api/plugins/Sky.night", headers=admin).status_code == 200
    assert not (package_directory / "Sky.night").exists()
    assert "Sky.night" not in {i["id"] for i in client.get("/api/plugins", headers=reader).json()["items"]}
    assert client.delete("/api/plugins/Sky.night", headers=admin).status_code == 404


def test_only_an_administrator_checks_installs_or_changes_packages(reader):
    document = _document(_package())
    assert client.post("/api/plugins/packages/validate", json={"document": document}, headers=reader).status_code == 403
    assert client.post("/api/plugins/packages", json={"document": document}, headers=reader).status_code == 403
    assert client.put("/api/plugins/Sky.night/words/Stars/preview", json={"png_base64": _png((0, 0, 0))},
                      headers=reader).status_code == 403
