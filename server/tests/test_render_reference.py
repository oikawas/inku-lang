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
    assert len(cases) == 347
    assert {
        prefix: sum(case_id.startswith(f"{prefix}-") for case_id in cases)
        for prefix in ("A", "B", "C", "D", "E")
    } == {"A": 88, "B": 72, "C": 40, "D": 28, "E": 119}


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
        assert case["svg_profile"] == "editable"
        assert isinstance(case["render_seed"], int)
        assert isinstance(case["wild"], bool)


def test_engine_14_moved_only_the_quantized_tool_among_the_frozen_cases() -> None:
    """一枚の方眼は computer の 7 件しか動かさない。

    格子は `grammar.quantize > 0` の道具にしか効かないので、手の 10 道具の演奏が
    1 件でも動いていたら、目盛の変更が別の経路へ漏れている。`cloudform` が入って
    いないのは `stroke_engine` を通らないため (SPEC §15.7 の既知の穴)。
    """
    manifest = _manifest()
    moved = {
        case_id
        for case_id in manifest["changed_from_previous"]
        if not case_id.startswith("E-")
    }
    assert moved == {
        f"A-computer-{primitive}"
        for primitive in ("arc", "circle", "ellipse", "line", "polygon", "square", "triangle")
    }
    assert "A-computer-cloudform" not in manifest["changed_from_previous"]


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

    tiny = cases["D-size-tiny-filled-circle"]
    assert not any("fill-stroke-v1" in name for name in tiny["classes"])


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
