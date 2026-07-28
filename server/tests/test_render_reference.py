"""Structural checks for the frozen render-engine reference corpus."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re

from inku_server.master_grid import MASTER_GRID_DECIMALS
from inku_server.render_engines import current_render_engine
from inku_server.schema import CanvasGroundSpec, Instruction, Score, SurfaceSpec

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"
ENGINE_VERSION = current_render_engine().version
CORPUS_DIR = SERVER_ROOT / "reference" / f"render-engine-{ENGINE_VERSION}"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"


def _generator():
    spec = importlib.util.spec_from_file_location("gen_render_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_render_reference_case_counts() -> None:
    cases = _manifest()["cases"]
    # engine 15 で C 群が 40 → 43。`ground.seed` を明示しない 4 件を足し
    # (それまでコーパスは `_texture_seed` を一度も呼んでいなかった)、
    # `absorbency` の退役でその判別ケースが `C-ground-paper` の重複になったので外した。
    # engine 16 で C 群が 43 -> 51。コーパスは 350 件すべてが `editable` で、
    # 本番既定の `display` 固有の分岐を一度も実行していなかったので `display` を
    # 通す 4 件 (`C-display-surface-*`) を足し、微小な塗りの機構が切り替わる
    # 境界の両側を留める 4 件 (`C-tinyfill-*`) を足した。
    # 段 3 で C 群が 51 -> 58。太さの軸 (`thinness`) は道具 3 種 × 2 段の 6 件と、
    # 既定を明示した 1 件 (`C-thinness-default-pen`) で留める。
    assert len(cases) == 365
    assert {
        prefix: sum(case_id.startswith(f"{prefix}-") for case_id in cases)
        for prefix in ("A", "B", "C", "D", "E")
    } == {"A": 88, "B": 72, "C": 58, "D": 28, "E": 119}


def test_render_reference_inputs_are_fully_explicit() -> None:
    generator = _generator()
    instruction_fields = set(generator.BASE_INSTRUCTION)
    score_fields = set(generator.BASE_SCORE)
    assert instruction_fields == {
        field.alias or name for name, field in Instruction.model_fields.items()
    }
    assert score_fields == set(Score.model_fields)
    assert set(generator.BASE_SURFACE) == set(SurfaceSpec.model_fields)
    assert set(generator.BASE_GROUND) == set(CanvasGroundSpec.model_fields)
    for case in generator.build_inputs().values():
        score = case["score"]
        assert set(score) == score_fields
        assert set(score["instructions"][0]) == instruction_fields
        assert set(case["color_map"]) == set(generator.DEFAULT_COLOR_MAP)
        assert case["svg_profile"] in ("editable", "display")
        assert isinstance(case["render_seed"], int)
        assert isinstance(case["wild"], bool)


def test_render_reference_keeps_the_display_profile_covered() -> None:
    """本番既定の `display` を通るケースが消えないように数で留める。

    engine 15 までコーパスは 100% `editable` で、作者が見ている経路 (フィルタ・
    clip) を 1 件も実行していなかった。
    """
    cases = _generator().build_inputs()
    display = sorted(
        case_id for case_id, case in cases.items() if case["svg_profile"] == "display"
    )
    assert display == [
        "C-display-surface-bleed-pen",
        "C-display-surface-grain-pen",
        "C-display-surface-hatch-pen",
        "C-display-surface-wash-pen",
    ]


def test_engine_15_left_only_the_machine_poles_untouched() -> None:
    """engine 15 が動かさなかったのは機械の極だけである。

    本版は演奏 seed の作り方を変えたので、手の演奏を持つ道具は全部動く。動かない
    のは、幾何のまま描かれる `rotring` と、誤差なく反復する `computer` だけ。
    **ただし cloudform は両極とも動く** — 段 3 でその図形が共通の閉輪郭経路に
    載り、`rotring` は class から偽りの `stroke-engine-touch` を落とし、`computer`
    は raster-bleed を得たからである。

    契約は「段 1 で 347 件すべてが動くので、不変の側が版の説明になるという読み方は
    失われる」と書いていたが、**実際には失われていない**。32 件が engine 14 と
    バイト一致で残り、その内訳がそのまま「本版が触れなかったもの」を語る。
    """
    manifest = _manifest()
    unchanged = set(manifest["cases"]) - set(manifest["changed_from_previous"])
    shapes_without_cloudform = (
        "arc", "circle", "ellipse", "line", "polygon", "square", "triangle",
    )
    assert unchanged == {
        f"{prefix}-{tool}-{primitive}"
        for prefix in ("A", "E-wild")
        for tool in ("computer", "rotring")
        for primitive in shapes_without_cloudform
    } | {
        f"D-canvas-{aspect}-filled-square-rotring"
        for aspect in ("square", "wide", "pillar", "vertical")
    }
    for tool in ("computer", "rotring"):
        assert f"A-{tool}-cloudform" in manifest["changed_from_previous"]


def test_render_reference_discriminator_cases() -> None:
    cases = _manifest()["cases"]
    square = cases["D-canvas-square-arc-brush-thick"]
    pillar = cases["D-canvas-pillar-arc-brush-thick"]
    assert square["digest"] != pillar["digest"]

    ordinary = cases["D-seed-12345"]
    for seed in (2**63 + 1, 2**64 - 1):
        high = cases[f"D-unsigned-seed-{seed}"]
        assert high["input"]["render_seed"] > 2**63
        assert high["digest"] != ordinary["digest"]

    # engine 16 段 2。engine 15 では「走査線で埋めていない」としか言えなかったが
    # (縮退先が領域 fill だったので class が出なかった)、いまは打点であることまで
    # 言える。境界の上側は走査のままであることと対にして留める。
    tiny = cases["D-size-tiny-filled-circle"]
    assert not any("fill-stroke-v1" in name for name in tiny["classes"])
    assert "fill-dab-v1" in tiny["classes"]
    boundary = cases["C-tinyfill-boundary-pen"]
    assert any(name.startswith("fill-stroke-v1") for name in boundary["classes"])
    assert "fill-dab-v1" not in boundary["classes"]
    # 機械の極は大きさに依らず領域 fill のまま (class を 1 つも出さない)。
    assert cases["C-tinyfill-circle-rotring"]["classes"] == []

    # engine 16 段 1。本番既定の display が筆致を通ること。
    display = cases["C-display-surface-wash-pen"]
    assert "surface-stroke-v1" in display["classes"]

    # engine 16 段 3。太さは絵を変えるが、銀筆は下限にいるので幅が変わらない
    # (それでも演奏 seed には入っているので手は変わる = C-7 の帰結)。
    thin = {
        key: cases[f"C-thinness-{key}"]
        for key in (
            "default-pen", "fine-pen", "extra_fine-pen",
            "fine-silverpoint", "extra_fine-silverpoint",
        )
    }
    assert len({case["digest"] for case in thin.values()}) == 5
    assert thin["fine-silverpoint"]["bytes"] == thin["extra_fine-silverpoint"]["bytes"]


def _resolve_svg(case_id: str) -> pathlib.Path:
    """ケースの実物を、最後にそれが動いた版まで遡って探す。

    動かなかったケースの SVG は現在の版のディレクトリには無い。前の版のものが
    そのまま最新であり、それを辿れることがこの構造の要点である (SPEC §15.7)。
    """
    reference_root = MANIFEST_PATH.parent.parent
    versions = sorted(
        (int(path.name.rsplit("-", 1)[-1]), path)
        for path in reference_root.glob("render-engine-*")
        if path.name.rsplit("-", 1)[-1].isdigit()
        and int(path.name.rsplit("-", 1)[-1]) <= int(ENGINE_VERSION)
    )
    for _, directory in reversed(versions):
        candidate = directory / f"{case_id}.svg"
        if candidate.exists():
            return candidate
    raise AssertionError(f"no frozen SVG for {case_id} in any version up to {ENGINE_VERSION}")


def test_render_reference_svg_files_match_manifest() -> None:
    manifest = _manifest()
    generator = _generator()
    for case_id, case in manifest["cases"].items():
        svg = _resolve_svg(case_id).read_text(encoding="utf-8")
        assert len(svg.encode("utf-8")) == case["bytes"]
        assert generator._normalized_digest(svg) == case["digest"]


def test_unchanged_cases_keep_the_previous_version_body() -> None:
    """変わらなかったケースは本文を持たず、前の版の実物がそのまま最新である。

    版のディレクトリに並ぶファイルが「その版が何を動かしたか」を意味するための
    条件。全件を書き写すと、この一覧が意味を失う。
    """
    manifest = _manifest()
    changed = set(manifest["changed_from_previous"])
    bodies = {path.stem for path in MANIFEST_PATH.parent.glob("*.svg")}
    assert bodies == changed
    unchanged = set(manifest["cases"]) - changed
    assert unchanged, "この版は全件を動かしている。遡りの検査が空振りしていないか確認する"
    for case_id in unchanged:
        assert _resolve_svg(case_id).parent != MANIFEST_PATH.parent


def test_every_corpus_number_sits_on_the_master_grid() -> None:
    """凍結物のどの数値も 6 桁固定で書かれている。

    グリッドに載っていることを成果物そのものから読めるようにするための検査。
    桁を詰めると 695.45787 が 6 桁グリッドの産物か生の float かを見分けられず、
    「丸めてから詰めた」という手順を信じる形になる (2026-07-24 作者裁定)。

    除外は 2 つだけ。SVG 文書の version="1.1" と、識別子である class / id。
    """
    off_grid = []
    checked = 0
    files = sorted(CORPUS_DIR.glob("*.svg"))
    for path in files:
        for name, value in re.findall(r'([\w:-]+)="([^"]*)"', path.read_text()):
            if name in ("class", "id", "version"):
                continue
            for decimals in re.findall(r"\d+\.(\d+)", value):
                checked += 1
                if len(decimals) != MASTER_GRID_DECIMALS:
                    off_grid.append((path.name, name, decimals))
    assert len(files) == len(_manifest()["changed_from_previous"])
    assert checked > 2_400, checked
    assert off_grid == []
