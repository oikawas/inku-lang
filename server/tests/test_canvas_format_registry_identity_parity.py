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


def test_current_server_legacy_projection_matches_ids_ratios_and_pixels() -> None:
    fixture = _fixture()
    legacy = _legacy_formats(fixture)
    assert [aspect.id for aspect in CANVAS_ASPECTS] == [item["id"] for item in legacy]

    canonical_by_id = {item["id"]: item for item in fixture["formats"]}
    for aspect, expected in zip(CANVAS_ASPECTS, legacy, strict=True):
        assert (aspect.ratio_w, aspect.ratio_h) == (
            expected["ratio_w"],
            expected["ratio_h"],
        )
        canonical = canonical_by_id[aspect.id]
        assert math.isclose(
            aspect.ratio_w / aspect.ratio_h,
            canonical["width_units"] / canonical["height_units"],
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        size = canvas_size_for_aspect(aspect.id)
        assert (size.width, size.height) == (
            expected["expected_width_px"],
            expected["expected_height_px"],
        )

    server_ids = {aspect.id for aspect in CANVAS_ASPECTS}
    assert "sd_monitor" not in server_ids
    assert "hd_monitor" not in server_ids


def test_web_and_android_sources_keep_the_legacy_host_boundary() -> None:
    fixture = _fixture()
    legacy = _legacy_formats(fixture)
    expected = [
        (item["id"], float(item["ratio_w"]), float(item["ratio_h"]))
        for item in legacy
    ]

    web_source = (
        PROJECT_ROOT / "web/src/lib/plugins/system/canvas-aspect/index.ts"
    ).read_text(encoding="utf-8")
    web_block = web_source.split(
        "export const CANVAS_ASPECT_OPTIONS: CanvasAspectOption[] = [", 1
    )[1].split("];", 1)[0]
    web_entries = [
        (identifier, float(width), float(height))
        for identifier, width, height in re.findall(
            r"\{ id: '([^']+)', category: '[^']+', label: '[^']+', "
            r"ratio: '[^']+', ratioW: ([0-9.]+), ratioH: ([0-9.]+),",
            web_block,
        )
    ]
    assert web_entries == expected

    android_source = (
        PROJECT_ROOT
        / "android/app/src/main/java/app/inku/mobile/data/model/CanvasAspects.kt"
    ).read_text(encoding="utf-8")
    android_entries = [
        (identifier, float(width), float(height))
        for identifier, width, height in re.findall(
            r'CanvasAspect\("([^"]+)", "[^"]+", "[^"]+", '
            r"([0-9.]+), ([0-9.]+),",
            android_source,
        )
    ]
    assert android_entries[:9] == expected
    assert android_entries[9:] == [("pixel9_landscape_safe", 9.0, 5.0)]
