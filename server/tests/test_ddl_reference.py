"""Structural and discriminator checks for the frozen DDL-layer corpus."""
from __future__ import annotations
import hashlib
import importlib.util
import inspect
import json
import pathlib
from inku_server.coerce import coerce_score
from inku_server.ddl_expander import expand_intermediate_ddl
from inku_server.layer_versions import DDL_ENGINE_VERSION, DDL_VERSION
from inku_server.schema import Arrangement, CanvasSpec, Instruction, Presence, Relation, Score

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_ddl_reference.py"
MANIFEST_PATH = (
    SERVER_ROOT / "reference" / f"ddl-engine-{DDL_ENGINE_VERSION}" / "manifest.json"
)

def _generator():
    spec = importlib.util.spec_from_file_location("gen_ddl_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

def _aliases(model) -> set[str]:
    return {field.alias or name for name, field in model.model_fields.items()}

def test_ddl_reference_versions_and_parts() -> None:
    manifest = _manifest()
    assert DDL_VERSION == "3"
    # engine 2 (2026-07-28): `Instruction` が `thinness` を得たので、この層の
    # 凍結出力は振る舞いが変わらないまま dump の形だけが変わった。凍結済みの
    # ディレクトリは書き換えないという規約に従い、次の版へ焼いた。
    # engine 3 (2026-07-29): `thinness` の宣言を末尾へ移した。Stage 2 の tool schema は
    # 並び順ごと LLM へ渡るので、この層の出力は 1 バイトも動かないまま、書かれる Score が
    # 変わる。**このコーパスが 1 件も動かないことが、この版が何をした版かの説明である**
    # （manifest の `changed_from_previous` は空）。
    # Engine 4 (2026-07-30): coerce learns the yellow, orange, and purple DDL markers,
    # so four new cases move and the twenty-nine older ones stay byte-identical.
    assert DDL_ENGINE_VERSION == "4"
    assert manifest["ddl_version"] == DDL_VERSION
    assert manifest["engine_version"] == DDL_ENGINE_VERSION
    assert manifest["schema_version"] == "0.1.0"
    assert len(manifest["cases"]) == 33
    assert sum(case["part"] == "a_expand" for case in manifest["cases"].values()) == 15
    assert sum(case["part"] == "b_coerce" for case in manifest["cases"].values()) == 18
    assert manifest["changed_from_previous"] == [
        "B-orange-from-ddl",
        "B-purple-from-ddl",
        "B-yellow-from-ddl",
        "B-yellow-from-ddl-en",
    ]

def test_ddl_reference_inputs_are_fully_explicit_and_independent() -> None:
    generator = _generator()
    assert set(generator.BASE_SCORE) == set(Score.model_fields)
    assert set(generator.BASE_SCORE["canvas"]) == set(CanvasSpec.model_fields)
    assert set(generator.BASE_INSTRUCTION) == _aliases(Instruction) - {"note"}
    assert set(generator.BASE_ARRANGEMENT) == set(Arrangement.model_fields)
    assert set(generator.BASE_RELATION) == set(Relation.model_fields)
    assert set(generator.BASE_PRESENCE) == set(Presence.model_fields)

    expand_fields = set(inspect.signature(expand_intermediate_ddl).parameters) - {"variation_report"}
    for case in generator.build_expand_inputs().values():
        assert set(case) == expand_fields

    coerce_fields = set(inspect.signature(coerce_score).parameters) - {"branch_report"}
    for case in generator.build_coerce_inputs().values():
        assert set(case) == coerce_fields
        score = case["score"]
        assert set(score) == set(Score.model_fields)
        assert set(score["canvas"]) == set(CanvasSpec.model_fields)
        for instruction in score["instructions"]:
            assert set(instruction) == _aliases(Instruction) - {"note"}
            if instruction["arrangement"] is not None:
                assert set(instruction["arrangement"]) == set(Arrangement.model_fields)
            if instruction["relation"] is not None:
                assert set(instruction["relation"]) == set(Relation.model_fields)
        if score["presence"] is not None:
            assert set(score["presence"]) == set(Presence.model_fields)

    source = inspect.getsource(generator.build_coerce_inputs)
    assert "build_expand_inputs" not in source
    assert "expand_intermediate_ddl" not in source

def test_ddl_reference_expand_discriminators() -> None:
    cases = _manifest()["cases"]
    base = cases["A-base-ja"]["digest"]
    for amplitude in ("small", "medium", "large"):
        for seed in (1, 12345):
            assert cases[f"A-variation-{amplitude}-{seed}"]["digest"] != base
    assert cases["A-variation-amplitude-only"]["digest"] == base
    assert cases["A-variation-seed-only"]["digest"] == base
    assert cases["A-base-ja"]["input"]["lang"] == "ja"
    assert cases["A-base-en"]["input"]["lang"] == "en"
    assert cases["A-plugin-enabled"]["digest"] != cases["A-plugin-disabled"]["digest"]
    assert cases["A-tenkei-auto"]["digest"] != cases["A-tenkei-none"]["digest"]
    assert {cases[f"A-tenkei-{level}"]["input"]["tenkei"] for level in ("auto", "sparse", "none")} == {"auto", "sparse", "none"}

def test_ddl_reference_coerce_discriminators() -> None:
    cases = _manifest()["cases"]
    expected = {
        "B-baseline-no-ddl": set(),
        "B-white-line": {"coerce_and_repair_instruction"},
        "B-white-filled-circle": {"coerce_and_repair_instruction"},
        "B-invalid-touching": {"drop_invalid_relations"},
        "B-dedupe-three": {"dedupe_instructions"},
        "B-trigger-auto": {"coerce_and_repair_instruction", "with_color_delivery_repair", "with_composition_diversity_repair", "with_existing_event_counterweight", "with_motion_energy", "with_motion_floor"},
        "B-trigger-sparse": {"coerce_and_repair_instruction", "with_color_delivery_repair", "with_composition_diversity_repair", "with_motion_energy"},
        "B-trigger-none": {"coerce_and_repair_instruction", "with_color_delivery_repair", "with_motion_energy"},
        "B-quiet-water": {"with_color_delivery_repair"},
        "B-presence-from-ddl": {"presence_from_ddl", "with_color_delivery_repair", "with_composition_diversity_repair"},
        "B-grid": {"with_composition_diversity_repair", "with_literal_grid_fidelity"},
        "B-dense-forty": set(),
        "B-cloudform": set(),
        "B-presence-no-ddl": set(),
        "B-yellow-from-ddl": {
            "with_color_delivery_repair",
            "with_composition_diversity_repair",
        },
        "B-orange-from-ddl": {
            "with_color_delivery_repair",
            "with_composition_diversity_repair",
            "with_existing_event_counterweight",
            "with_motion_energy",
            "with_motion_floor",
        },
        "B-purple-from-ddl": {
            "with_color_delivery_repair",
            "with_composition_diversity_repair",
        },
        "B-yellow-from-ddl-en": {
            "with_color_delivery_repair",
            "with_composition_diversity_repair",
        },
    }
    for case_id, fired in expected.items():
        assert set(cases[case_id]["fired_branches"]) == fired
    assert [cases[f"B-trigger-{level}"]["instruction_count"] for level in ("auto", "sparse", "none")] == [3, 2, 1]
    assert [len(cases[f"B-trigger-{level}"]["fired_branches"]) for level in ("auto", "sparse", "none")] == [6, 4, 3]
    assert cases["B-baseline-no-ddl"]["instruction_count"] == 1
    assert cases["B-dense-forty"]["instruction_count"] == 40

def test_ddl_reference_output_files_match_manifest() -> None:
    for case in _manifest()["cases"].values():
        data = (MANIFEST_PATH.parent / case["output_path"]).read_bytes()
        assert len(data) == case["bytes"]
        assert hashlib.sha256(data).hexdigest()[:32] == case["digest"]
