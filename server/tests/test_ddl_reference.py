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
    assert DDL_ENGINE_VERSION == "8"
    assert manifest["ddl_version"] == DDL_VERSION
    assert manifest["engine_version"] == DDL_ENGINE_VERSION
    assert manifest["schema_version"] == "0.1.0"
    # Engine 7 (2026-08-05): the staffage level was folded away, so Stage 1.5
    # appends nothing of its own and coerce runs no branch that invents. The six
    # cases that existed only to separate the three levels became copies of one
    # another and were replaced by one each (`A-scatter`, `B-trigger`); two new
    # coerce cases freeze the silence of words that used to summon an invention.
    # 32 of the 34 entries are listed as changed, which is expected and is NOT
    # 32 cases whose Score moved: 9 of the b_coerce digests moved only because
    # the branch report lost a name. The Score itself moved in 10 expand cases
    # and 9 coerce ones (plus the merged-away B-trigger-auto / -sparse).
    # Engine 8 (2026-08-09): the color cycle stops inventing an order. coerce no
    # longer doubles a color that is already in a cycle, and `_color_repair_order`
    # no longer drops yellow, orange, or purple when an older color is present.
    # Two cases move and neither is an expand case: this change lives entirely
    # inside coerce, so all 13 a_expand digests are byte-identical. The two are
    # one per half -- `B-production-fill-clause` loses the duplicated white, and
    # `B-presence-from-ddl` keeps a yellow the six-word table used to drop.
    # **19 of the 21 coerce cases not moving is the measurement, not a gap**:
    # the corpus reaches this layer 14 times through a cycle, and only these two
    # carry the shapes -- a base color already in the cycle, and old and new
    # color words in one description.
    assert len(manifest["cases"]) == 34
    assert sum(case["part"] == "a_expand" for case in manifest["cases"].values()) == 13
    assert sum(case["part"] == "b_coerce" for case in manifest["cases"].values()) == 21
    assert manifest["changed_from_previous"] == ["B-presence-from-ddl", "B-production-fill-clause"]
    assert not any(
        manifest["cases"][case]["part"] == "a_expand" for case in manifest["changed_from_previous"]
    )

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

    # `branch_report` and `limit_notes` are out-parameters and `limits` is the
    # injection seam the settings contract writes through -- none of the three
    # describes a case, so none belongs in a per-case input record.
    coerce_fields = set(inspect.signature(coerce_score).parameters) - {
        "branch_report",
        "limits",
        "limit_notes",
    }
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
    # No two inputs may be identical. The three A-tenkei-* cases differed in the
    # staffage level alone, so folding the axis away turned them into copies of
    # one another; one survives as A-scatter (v2.11.0).
    seen: dict[str, str] = {}
    for case_id, case in sorted(cases.items()):
        key = json.dumps(case["input"], ensure_ascii=False, sort_keys=True)
        assert key not in seen, f"{case_id} has the same input as {seen.get(key)}"
        seen[key] = case_id
    assert "A-scatter" in cases
    assert not [case_id for case_id in cases if case_id.startswith("A-tenkei-")]

def test_ddl_reference_coerce_discriminators() -> None:
    cases = _manifest()["cases"]
    expected = {
        "B-baseline-no-ddl": set(),
        "B-white-line": {"coerce_and_repair_instruction"},
        "B-white-filled-circle": {"coerce_and_repair_instruction"},
        "B-invalid-touching": {"drop_invalid_relations"},
        "B-dedupe-three": {"dedupe_instructions"},
        # The three B-trigger-* cases separated the staffage levels; with the axis
        # folded away (v2.11.0) they are one case, and what fires on it is repair
        # and delivery alone -- no composition anchor, no motion floor.
        "B-trigger": {"coerce_and_repair_instruction", "with_color_delivery_repair", "with_motion_energy"},
        "B-quiet-water": {"with_color_delivery_repair"},
        "B-presence-from-ddl": {"presence_from_ddl", "with_color_delivery_repair"},
        "B-grid": {"with_literal_grid_fidelity"},
        "B-dense-forty": set(),
        "B-cloudform": set(),
        "B-presence-no-ddl": set(),
        # 布 / 影 / 沈む used to summon a surface-tension mark of coerce's own.
        # Nothing fires now: the description asked for one line and gets one line.
        "B-surface-tension-words": set(),
        # 落ち葉 / 森 used to summon a leaf-grain energy instruction AND a motif.
        # The energy was invention and is gone; the motif is what the DDL asked
        # for, so `with_complex_motif_repair` still delivers it.
        "B-leaf-grain-words": {"with_color_delivery_repair", "with_complex_motif_repair"},
        "B-yellow-from-ddl": {"with_color_delivery_repair"},
        "B-orange-from-ddl": {"with_color_delivery_repair", "with_motion_energy"},
        "B-purple-from-ddl": {"with_color_delivery_repair"},
        "B-yellow-from-ddl-en": {"with_color_delivery_repair"},
    }
    for case_id, fired in expected.items():
        assert set(cases[case_id]["fired_branches"]) == fired, case_id
    # The description hands coerce one line and leaves with one line.
    assert cases["B-trigger"]["instruction_count"] == 1
    assert cases["B-surface-tension-words"]["instruction_count"] == 1
    assert cases["B-baseline-no-ddl"]["instruction_count"] == 1
    assert cases["B-dense-forty"]["instruction_count"] == 40
    # No branch that invents may fire anywhere in the corpus.
    gone = {
        "with_visual_event",
        "with_composition_diversity_repair",
        "with_context_energy_repair",
        "with_motion_floor",
        "with_surface_tension",
        "with_focal_event_floor",
    }
    for case_id, case in cases.items():
        if case["part"] != "b_coerce":
            continue
        assert not (set(case["fired_branches"]) & gone), case_id

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
