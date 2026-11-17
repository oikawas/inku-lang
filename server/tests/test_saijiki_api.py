"""Phase 3 anti-drift: GET /api/saijiki and the web codegen snapshot both
derive from the saijiki table. Hardcoding either would diverge and fail here.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

from inku_server.api_core.routers import public as public_routes
from inku_server import db, saijiki
from inku_server.api import app

client = TestClient(app)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GENERATED_TS = _REPO_ROOT / "web" / "src" / "lib" / "saijiki.generated.ts"


def test_all_saijiki_categories_match_the_core_v4_asset():
    asset = json.loads((_REPO_ROOT / "core/crates/inku-ddl/assets/saijiki-v4.json").read_text())
    assert asset["asset_id"] == "inku.saijiki.v4"
    from inku_server.saijiki_generated import BUNDLES
    assert BUNDLES == asset["bundles"]
    assert next(c for c in saijiki.display_categories("ja") if c["key"] == "aida")["bundle"] == asset["relations_bundle"]
    assert len(asset["categories"]) == len(saijiki.SAIJIKI)
    fields = ("surface_ja", "surface_en", "score_value", "default", "prompt", "display", "marker",
              "parser_surfaces_ja", "parser_surfaces_en", "marker_surfaces_ja", "marker_surfaces_en", "id", "facet", "description")
    for expected, category in zip(asset["categories"], saijiki.SAIJIKI, strict=True):
        assert expected["key"] == category.key
        assert len(expected["words"]) == len(category.words)
        for word_asset, word in zip(expected["words"], category.words, strict=True):
            actual = json.loads(json.dumps(asdict(word), ensure_ascii=False))
            assert {field: actual[field] for field in fields} == {
                field: word_asset.get(field) for field in fields
            }
    for lang in ("ja", "en"):
        relations = {item["relation_type"]: item["description"][lang] for item in asset["relations"]}
        aida = next(category for category in saijiki.display_categories(lang) if category["key"] == "aida")
        assert list(aida["descriptions"]) == [relations[relation] for relation in aida["ids"]]


def test_generated_python_matches_asset():
    path = _REPO_ROOT / "server/scripts/gen_saijiki_py.py"
    spec = importlib.util.spec_from_file_location("gen_saijiki_py", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert module.render_py() == module.OUTPUT.read_text(encoding="utf-8")


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
        permission_groups=["users"],
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
                        "bundles": saijiki.BUNDLES,
                        "categories": saijiki.display_categories(lang),
                        "plugins": public_routes._enabled_plugin_entries(),
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
_EXPECTED_PAIRING: dict[str, tuple[tuple[str, str], ...]] = {'katachi': (('円', 'circle'),
             ('楕円', 'ellipse'),
             ('三角', 'triangle'),
             ('四角', 'square'),
             ('線', 'line'),
             ('弧', 'arc'),
             ('自由線', 'free line'),
             ('点', 'point'),
             ('雲形', 'cloudform'),
             ('多角形', 'polygon'),
             ('半円', 'semicircle'),
             ('三日月', 'crescent')),
 'katamuki': (('水平', 'horizontal'),
              ('垂直', 'vertical'),
              ('斜め', 'diagonal'),
              ('右上がり', 'rising'),
              ('右下がり', 'falling'),
              ('左上がり', 'left-rising'),
              ('左下がり', 'left-falling'),
              ('回転', 'rotated')),
 'tezawari': (('銀筆', 'silverpoint'),
              ('鉛筆', 'pencil'),
              ('ペン', 'pen'),
              ('チョーク', 'chalk'),
              ('オイルパステル', 'oil pastel'),
              ('ガッシュ', 'gouache'),
              ('水彩', 'watercolor'),
              ('油彩', 'oil paint'),
              ('ペインティングナイフ', 'painting knife'),
              ('エッチング', 'etching'),
              ('デジタル', 'digital')),
 'tsuranari': (('実線', 'solid'), ('破線', 'dashed'), ('点線', 'dotted')),
 'omote': (('空', 'empty'),
           ('塗り', 'flat'),
           ('刷き', 'sweep'),
           ('刷毛目', 'brushmarks'),
           ('粒', 'grain'),
           ('点描', 'stipple'),
           ('平行線', 'hatch'),
           ('交差線', 'crosshatch'),
           ('メゾチント', 'mezzotint')),
 'sabaki': (('濃い', 'dense'), ('程よい', 'moderate'), ('薄い', 'faint'), ('にじみ', 'bleeding')),
 'kime': (('細かい', 'fine-grained'),
          ('粗い', 'coarse-grained'),
          ('密な', 'packed'),
          ('疎な', 'sparse'),
          ('下塗り', 'underpainted')),
 'ji': (('紙', 'paper'),
        ('和紙', 'washi'),
        ('薄墨地', 'ink wash ground'),
        ('木炭地', 'charcoal ground'),
        ('カンバス', 'canvas'),
        ('画用紙', 'drawing paper'),
        ('メゾチント', 'mezzotint'),
        ('画面比', 'aspect ratio')),
 'iro': (('白', 'white'),
         ('黒', 'black'),
         ('青', 'blue'),
         ('赤', 'red'),
         ('緑', 'green'),
         ('灰', 'gray'),
         ('黄', 'yellow'),
         ('橙', 'orange'),
         ('紫', 'purple')),
 'yuragi': (('小さく', 'narrowly'),
            ('大きく', 'broadly'),
            ('ゆるやかに', 'loosely'),
            ('小刻みに', 'tightly'),
            ('揺れる', 'swaying'),
            ('波打つ', 'undulating')),
 'basho': (('上', 'top'),
           ('下', 'bottom'),
           ('中心', 'center'),
           ('左端', 'left-edge'),
           ('右端', 'right-edge'),
           ('上端', 'top-edge'),
           ('下端', 'bottom-edge'),
           ('隅', 'corner')),
 'ugoki': (('置く', 'place'),
           ('並べる', 'line-up'),
           ('引く', 'draw'),
           ('散らす', 'scatter'),
           ('埋める', 'fill'),
           ('敷き詰める', 'tile')),
 'jun': (('交互に', 'alternating'), ('順に', 'in order')),
 'wariai': (('縦長', 'tall'), ('横長', 'wide'), ('全幅', 'full-width'), ('半幅', 'half-width')),
 'futosa': (('ごく細い', 'very thin'), ('細い', 'thin'), ('太い', 'thick'), ('ごく太い', 'very thick')),
 'ookisa': (('ごく小さな', 'very small'),
            ('小さな', 'small'),
            ('普通の大きさ', 'normal-sized'),
            ('大きな', 'large'),
            ('ごく大きな', 'very large')),
 'aida': (('沿う', 'along'),
          ('触れない', 'not touching'),
          ('切る', 'cutting'),
          ('間に', 'between'),
          ('触れる', 'touching'),
          ('つながる', 'connected'),
          ('載る', 'resting on'),
          ('中に', 'inside'),
          ('重なる', 'overlaps'),
          ('横切る', 'crossing'),
          ('鏡写し', 'mirrored'))}


def test_display_lists_pair_ja_and_en_by_position():
    ja = {cat["key"]: cat["words"] for cat in saijiki.display_categories("ja")}
    en = {cat["key"]: cat["words"] for cat in saijiki.display_categories("en")}
    assert set(ja) == set(en) == set(_EXPECTED_PAIRING)
    for key, expected in _EXPECTED_PAIRING.items():
        assert tuple(zip(ja[key], en[key], strict=True)) == expected, f"pairing drift in {key}"


def test_pruned_words_absent_from_display():
    words = {w for cat in saijiki.display_categories("ja") for w in cat["words"]}
    words |= {w for cat in saijiki.display_categories("en") for w in cat["words"]}
    # P0-2b (描く), P0-1a (彫る) removed from display; aida kept.
    assert "描く" not in words and "彫る" not in words
    assert any(cat["key"] == "aida" for cat in saijiki.display_categories("ja"))
    # P0-3 pruned 髪/hair in 2026-07-18. The name was the problem, not the tool, so
    # 2026-07-27 renamed it to 銀筆/silverpoint and put it back on display. The old
    # name survives nowhere — the rename is a replacement, not a second entry.
    assert "髪" not in words and "hair" not in words
    assert "銀筆" in words and "silverpoint" in words
    from inku_server import schema
    from typing import get_args

    assert "hair" not in get_args(schema.Weight)
    assert "silverpoint" in get_args(schema.Weight)
