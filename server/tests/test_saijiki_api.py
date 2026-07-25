"""Phase 3 anti-drift: GET /api/saijiki and the web codegen snapshot both
derive from the saijiki table. Hardcoding either would diverge and fail here.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from inku_server import api as api_module
from inku_server import db, saijiki
from inku_server.api import app

client = TestClient(app)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GENERATED_TS = _REPO_ROOT / "web" / "src" / "lib" / "saijiki.generated.ts"


def _load_codegen():
    path = _REPO_ROOT / "server" / "scripts" / "gen_saijiki_ts.py"
    spec = importlib.util.spec_from_file_location("gen_saijiki_ts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _auth():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"saij-{suffix}")
    user = db.add_user(
        username=f"saij-{suffix}",
        email=f"saij-{suffix}@example.test",
        password="password-123",
        role="user",
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return {"Authorization": f"Bearer {token}"}, user, group, token


def test_api_saijiki_matches_table():
    headers, user, group, token = _auth()
    try:
        for lang in ("ja", "en"):
            response = client.get(f"/api/saijiki?lang={lang}", headers=headers)
            assert response.status_code == 200
            expected = json.loads(
                json.dumps(
                    {
                        "categories": saijiki.display_categories(lang),
                        "plugins": api_module._enabled_plugin_entries(),
                    }
                )
            )
            assert response.json() == expected
    finally:
        db.delete_session(token)
        db.delete_user(user["id"])
        db.delete_user_group(group["id"])


def test_api_saijiki_requires_auth():
    assert client.get("/api/saijiki").status_code in (401, 403)


def test_generated_ts_matches_table():
    module = _load_codegen()
    assert module.render_ts() == _GENERATED_TS.read_text(encoding="utf-8")


# 表示リストの ja↔en 対応。web へは言語別リストとして配信するため、最終表現の
# 位置対応を固定する。サーバー正本では1語が両言語表面を所有し、並べ替えによる
# 引く/埋める と draw/fill の入れ違いを構造上起こせない。
_EXPECTED_PAIRING: dict[str, tuple[tuple[str, str], ...]] = {
    "katachi": (
        ("円", "circle"), ("楕円", "ellipse"), ("三角", "triangle"), ("四角", "square"),
        ("線", "line"), ("弧", "arc"), ("雲形", "cloudform"),
    ),
    "katamuki": (
        ("水平", "horizontal"), ("垂直", "vertical"), ("斜め", "diagonal"),
        ("右上がり", "rising"), ("右下がり", "falling"), ("回転", "rotated"),
    ),
    "tezawari": (
        ("鉛筆", "pencil"), ("ペン", "pen"), ("ロットリング", "rotring"), ("クレヨン", "crayon"),
        ("チョーク", "chalk"), ("細筆", "fine-brush"), ("太筆", "thick-brush"),
        ("ビュラン", "burin"), ("ドライポイント", "drypoint"),
        ("コンピュータ", "computer"),
    ),
    "tsuranari": (
        ("実線", "solid"), ("破線", "dashed"), ("点線", "dotted"), ("一点鎖線", "dash-dot"),
    ),
    "iro": (
        ("白", "white"), ("黒", "black"), ("青", "blue"),
        ("赤", "red"), ("緑", "green"), ("灰", "gray"),
    ),
    "yuragi": (
        ("細かく", "fine"), ("大きく", "large"), ("ゆっくり", "slowly"), ("速く", "quickly"),
        ("揺れる", "swaying"), ("波打つ", "undulating"), ("震える", "trembling"), ("滲む", "blurring"),
    ),
    "basho": (
        ("上", "top"), ("下", "bottom"), ("中央", "center"), ("左端", "left-edge"),
        ("右端", "right-edge"), ("上端", "top-edge"), ("下端", "bottom-edge"),
        ("中心", "middle"), ("隅", "corner"),
    ),
    "ugoki": (
        ("置く", "place"), ("並べる", "line-up"), ("引く", "draw"),
        ("散らす", "scatter"), ("埋める", "fill"), ("敷き詰める", "tile"),
    ),
    "wariai": (
        ("縦長", "tall"), ("横長", "wide"), ("全幅", "full-width"), ("半幅", "half-width"),
        ("半円", "semicircle"), ("上弦", "waxing"), ("下弦", "waning"), ("三日月", "crescent"),
    ),
    "aida": (
        ("沿う", "along"), ("触れない", "not touching"), ("切る", "cutting"),
        ("間に", "between"), ("触れる", "touching"),
    ),
}


def test_display_lists_pair_ja_and_en_by_position():
    ja = {cat["key"]: cat["words"] for cat in saijiki.display_categories("ja")}
    en = {cat["key"]: cat["words"] for cat in saijiki.display_categories("en")}
    assert set(ja) == set(en) == set(_EXPECTED_PAIRING)
    for key, expected in _EXPECTED_PAIRING.items():
        assert tuple(zip(ja[key], en[key], strict=True)) == expected, f"pairing drift in {key}"


def test_pruned_words_absent_from_display():
    words = {w for cat in saijiki.display_categories("ja") for w in cat["words"]}
    words |= {w for cat in saijiki.display_categories("en") for w in cat["words"]}
    # P0-3 (髪/hair), P0-2b (描く), P0-1a (彫る) removed from display; aida kept.
    assert "髪" not in words and "hair" not in words
    assert "描く" not in words and "彫る" not in words
    assert any(cat["key"] == "aida" for cat in saijiki.display_categories("ja"))
    # Weight enum still carries hair for replay/rh2 compatibility.
    from inku_server import schema
    from typing import get_args

    assert "hair" in get_args(schema.Weight)
