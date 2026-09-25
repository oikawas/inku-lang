from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from inku_server.plugins import CANVAS_ASPECTS, canvas_size_for_aspect


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    PROJECT_ROOT
    / "core/crates/inku-score/tests/fixtures/canvas-format-registry-v1.json"
)


def _fixture() -> dict[str, object]:
    raw = FIXTURE_PATH.read_bytes()
    assert raw.endswith(b"\n")
    return json.loads(raw)


def _legacy_formats(fixture: dict[str, object]) -> list[dict[str, object]]:
    projection = fixture["legacy_server_projection"]
    assert isinstance(projection, dict)
    formats = projection["formats"]
    assert isinstance(formats, list)
    return formats


def test_fixture_identity_is_independently_framed_and_complete() -> None:
    fixture = _fixture()
    assert fixture["schema"] == "inku.canvas-format-registry-fixture.v1"
    assert fixture["version"] == 1
    assert fixture["registry_id"] == "inku.canvas-format-registry.v1"
    assert fixture["default"] == "square"

    formats = fixture["formats"]
    assert isinstance(formats, list)
    assert [item["id"] for item in formats] == [
        "square",
        "golden",
        "a4",
        "b4",
        "pillar",
        "oban",
        "wide",
        "byobu",
        "vertical",
        "sd_monitor",
        "hd_monitor",
    ]
    assert len({item["id"] for item in formats}) == 11
    for item in formats:
        width = item["width_units"]
        height = item["height_units"]
        assert isinstance(width, int) and width > 0
        assert isinstance(height, int) and height > 0
        assert math.gcd(width, height) == 1

    canonical_json = json.dumps(
        {"schema": fixture["registry_id"], "formats": formats},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert canonical_json == fixture["expected_canonical_json"]
    assert not canonical_json.endswith("\n")
    canonical_bytes = canonical_json.encode("utf-8")
    domain = b"inku.canvas-format-registry.v1"
    framed = domain + b"\0" + len(canonical_bytes).to_bytes(8, "big") + canonical_bytes
    digest = hashlib.sha256(framed).hexdigest()
    assert digest == fixture["expected_digest"]
    assert re.fullmatch(r"[0-9a-f]{64}", digest)

    assert fixture["new_presentations"] == [
        {"id": "sd_monitor", "label": "4:3 SD Monitor"},
        {"id": "hd_monitor", "label": "16:9 HD Monitor"},
    ]
    assert "pixel9_landscape_safe" not in {item["id"] for item in formats}


def test_server_offers_the_canonical_registry_and_keeps_every_legacy_paper() -> None:
    """Since the shared cutover the Server projects the Rust registry itself.

    The nine papers it offered before keep their ratio and pixels, so a saved
    work still performs on the paper it was drawn on.
    """
    fixture = _fixture()
    canonical = fixture["formats"]
    assert [aspect.id for aspect in CANVAS_ASPECTS] == [item["id"] for item in canonical]
    for aspect, item in zip(CANVAS_ASPECTS, canonical, strict=True):
        assert (aspect.ratio_w, aspect.ratio_h) == (
            float(item["width_units"]),
            float(item["height_units"]),
        )

    offered = {aspect.id: aspect for aspect in CANVAS_ASPECTS}
    for expected in _legacy_formats(fixture):
        aspect = offered[expected["id"]]
        assert math.isclose(
            aspect.ratio_w / aspect.ratio_h,
            expected["ratio_w"] / expected["ratio_h"],
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        size = canvas_size_for_aspect(aspect.id)
        assert (size.width, size.height) == (
            expected["expected_width_px"],
            expected["expected_height_px"],
        )


def test_web_and_android_project_the_shared_registry_instead_of_a_list() -> None:
    """Neither host keeps its own list of papers; both read the shared registry.

    Android's device-only 9:5 paper stays readable for saved works and is never
    offered as new paper.
    """
    web_source = (
        PROJECT_ROOT / "web/src/lib/plugins/system/canvas-aspect/index.ts"
    ).read_text(encoding="utf-8")
    assert "payload.registry.formats" in web_source
    assert not re.search(r"\{ id: '[a-z0-9_]+', category: '", web_source)

    android_source = (
        PROJECT_ROOT
        / "android/app/src/main/java/app/inku/mobile/data/model/CanvasAspects.kt"
    ).read_text(encoding="utf-8")
    assert "get() = registry().formats" in android_source
    literals = re.findall(r'CanvasAspect\(\s*id = ([A-Z_0-9]+)', android_source)
    assert literals == ["LEGACY_PIXEL9_LANDSCAPE_SAFE_ID"]
