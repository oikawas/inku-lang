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
    # Engine 5 (2026-08-03): `thinness` moves off the tail to sit just before `surface`,
    # giving the last declaration slot back. Same reason as engine 3 -- the declaration
    # order reaches Stage 2, so the Score that gets written changes while this layer's
    # output does not move by a byte. **The empty list below is the whole explanation
    # of what this version did**, and it is the only thing that distinguishes it.
    # Engine 6 (2026-08-04): coerce receives the DDL alone. The three new cases are
    # the whole of `changed_from_previous`, and the thirty-three carried over are
    # byte-identical: the guard this version removed was unreachable from every
    # input the corpus already held. **That is the point of listing only three** --
    # the corpus could not have caught the behaviour this version changed, because
    # no case here ever had the shape production was passing.
    assert DDL_ENGINE_VERSION == "6"
    assert manifest["ddl_version"] == DDL_VERSION
    assert manifest["engine_version"] == DDL_ENGINE_VERSION
    assert manifest["schema_version"] == "0.1.0"
    assert len(manifest["cases"]) == 36
    assert sum(case["part"] == "a_expand" for case in manifest["cases"].values()) == 15
    assert sum(case["part"] == "b_coerce" for case in manifest["cases"].values()) == 21
    assert manifest["changed_from_previous"] == [
        "B-production-fill-clause",
        "B-production-multiline",
        "B-production-no-fill-clause",
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

    # `branch_report` is an out-parameter and `limits` is the injection seam the
    # follow-up settings contract writes through -- neither describes a case, so
    # neither belongs in a per-case input record.
    coerce_fields = set(inspect.signature(coerce_score).parameters) - {"branch_report", "limits"}
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

def test_the_corpus_carries_the_shape_production_hands_coerce(monkeypatch) -> None:
    """T-7 of 契約 description-propagation-cut, written as a property.

    A regenerated expectation table is a record, not a gate: rebaking it hides
    exactly the move it was meant to catch. What this asserts instead is the
    relation between the corpus and production -- every b_coerce input is a
    string production could hand `coerce_score`, and production hands it the
    DDL alone. Re-concatenating the description on the product side turns the
    first assertion red for every case at once, because production would then
    hand over `prose\nDDL` for the very same DDL.

    Before the cut this could not be written: 71.7% of production works passed
    a concatenation and no case in the corpus had ever carried one.
    """
    # Importing the app is what creates the schema for the test database.
    from inku_server.api import app as _app  # noqa: F401
    from inku_server.api_core.routers import render as render_routes

    cases = _generator().build_coerce_inputs()
    handed: list[str] = []

    class _Expansion:
        provenance: list = []
        warnings: list = []
        instructions: list = []

        def __init__(self, ddl: str) -> None:
            self.ddl = ddl

    def fake_expand(ddl, **kwargs):
        return _Expansion(ddl)

    def fake_compose(ddl, **kwargs):
        return Score.model_validate({"instructions": []}), 1, 2

    def fake_coerce(score, *, ddl="", **kwargs):
        handed.append(ddl)
        return score

    monkeypatch.setattr(render_routes.DOCUMENT_PLUGIN_MANAGER, "expand", fake_expand)
    monkeypatch.setattr(render_routes, "expand_intermediate_for_lang", lambda ddl, **kwargs: ddl)
    monkeypatch.setattr(render_routes, "compose", fake_compose)
    monkeypatch.setattr(render_routes, "coerce_score", fake_coerce)

    checked = 0
    for case_id, case in sorted(cases.items()):
        if not case["ddl"]:
            continue
        handed.clear()
        render_routes.api_compose(
            render_routes.ComposeRequest(
                ddl=case["ddl"],
                description="ひさかたの光のどけき春の日にしづ心なく花の散るらむ",
                sketch_text="円がある。円は黒い。",
                instruction_lang="ja",
            ),
            {"id": "test-user"},
        )
        assert handed == [case["ddl"]], (
            f"{case_id}: production hands coerce {handed!r}, the corpus freezes "
            f"{case['ddl']!r}. The corpus is no longer measuring production's input."
        )
        checked += 1
    # Say how many were looked at: a gate that silently checked nothing reads
    # exactly like a gate that passed.
    assert checked == 13


def test_the_corpus_holds_a_case_of_the_production_shape() -> None:
    """The property above is satisfied by an empty corpus too. These three cases
    are what make it say something: a single-line multi-clause DDL opening with a
    fill clause is the ordinary shape of production's input, and it is the shape
    the removed guard misfired on."""
    cases = _generator().build_coerce_inputs()
    fill_clause = cases["B-production-fill-clause"]["ddl"]

    assert "\n" not in fill_clause
    assert fill_clause.startswith("背景を")
    assert len([part for part in fill_clause.split("。") if part.strip()]) >= 4
    assert "\n" in cases["B-production-multiline"]["ddl"]
