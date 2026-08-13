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
    # Engine 11 (2026-08-10): a count stated in plain words is repaired to the
    # group its clause names. All 21 coerce entries are listed as changed and NOT
    # ONE of their Scores moved: the branch report gained a 30th key, which every
    # case carries whether or not the branch fired, and no case in this corpus
    # states a count in the 1..11 band beside a group a clause pairs with. The
    # witness for the new branch is in the coerce golden set, which is where
    # `test_every_branch_coerce_reaches_has_a_witness` demands one.
    # Engine 12 (2026-08-10): the same repair stops at `literal_count_threshold`
    # instead of at eleven, and declines a number the work has no room for.
    # `changed_from_previous` is TWO, and both are new: no branch was added, so no
    # digest moved for a report key this time, and **not one of the 21 carried-over
    # cases states a count above eleven** -- which is exactly why the two were
    # written. Freezing the 21 alone would have recorded a version of a layer this
    # change never traversed.
    # Engine 13 (2026-08-11): a plugin hands over one unit and the count stated in
    # the phrase naming it says how many of those to place. **Part C is new and is
    # the whole of `changed_from_previous`**: parts A and B never reach the
    # document plugin layer -- A's plugin work is the `Nature.` macro regex in
    # `ddl_expander`, and the manager is called from the render route alone -- so
    # this layer carried a version number from the start and never a frozen
    # output. Freezing A and B alone would have recorded a version of a layer the
    # change never traversed, which is what engine 12 wrote two cases to avoid.
    # Engine 15 (2026-08-12): a shape can say how its surface is. The saijiki and
    # both prompt tables move, and this corpus sees none of that -- it calls no
    # LLM. What it sees is the one deterministic branch: a surface attached to a
    # primitive with no interior moves to the nearest closed shape before it.
    # **THREE cases are new and 26 are listed as changed**, and the 23 carried
    # over did not move a Score: adding a branch adds its name to every
    # `branch_report`, exactly as engine 11 records above. Not one of the 42
    # inputs frozen at engine 14 held a 「面:」 clause -- the two files that hold
    # one are `c_plugin_expand` output written by a plugin -- so freezing without
    # the three would have recorded a version whose change the corpus never
    # traversed, which is the mistake engines 12 and 13 both wrote cases to avoid.
    # Engine 16 (2026-08-13): a mark the description called small is small whoever
    # wrote it. **FOUR cases are new and they are the whole of
    # `changed_from_previous`** -- the opposite of engines 11 and 15, which listed
    # every coerce case because they added a branch name every report carries.
    # Nothing was added to the report here, so the 45 carried-over entries are
    # byte-identical, which is asserted below rather than described. Not one of the
    # 26 inputs frozen at engine 15 hands coerce a circle or an ellipse with its
    # size left empty, so freezing without the four would again have recorded a
    # version whose change the corpus never traversed. **Two of the four are
    # controls** -- a description with no size word, and a size the model did state
    # -- because a corpus holding only the two that move would record a layer that
    # shrinks marks rather than one that reads a description.
    assert DDL_ENGINE_VERSION == "16"
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
    # Engine 9 (2026-08-09): coerce becomes a fixed point for a color it delivers.
    # The promotion to a primary stroke ran before the repair that puts a color in
    # a cycle, and it can only promote what a cycle already carries, so a delivered
    # color waited for a second pass over the same DDL. 8 coerce cases move and no
    # expand case does. **The eight are the whole of it, and they are all the same
    # shape**: a DDL names a color, this layer delivers it into a cycle, and the
    # instruction's own `color` was left at the black it started with. Engine 8 is
    # why five of them are new -- until the six-word table stopped dropping yellow,
    # orange, and purple, those cases could not reach either stage.
    # Engine 10 (2026-08-10): a description that names one color is drawn in one
    # color. The cycle hands `cycle[i % len(cycle)]` to each member, so a
    # two-color cycle gave the named color half the group. **`changed_from_previous`
    # lists all 21 coerce cases and the Score moved in 8**: every case carries the
    # new branch's key in its branch report whether or not the branch fired, so
    # the digest moves everywhere and the transform moves in eight. No expand case
    # moves; the change lives entirely inside coerce, like engines 8 and 9.
    # Engine 14 (2026-08-12): every reader counts the same way (ledger I-212 to
    # I-216). C gained the two cases the widened rules needed -- a count stated
    # outside the naming phrase, and a bare numeral inside one -- so the part is
    # six. A and B do not move: the readers this version widened are reached by
    # the plugin layer, and the count a coerce case states was already read.
    # Engine 16 (2026-08-13): B gains the four cases the size rule needed -- two it
    # moves and two it must leave alone -- so the part is thirty. A and C do not
    # move: the rule lives inside coerce and reads a clause the expander never
    # writes.
    assert len(manifest["cases"]) == 49
    assert sum(case["part"] == "a_expand" for case in manifest["cases"].values()) == 13
    assert sum(case["part"] == "b_coerce" for case in manifest["cases"].values()) == 30
    assert sum(case["part"] == "c_plugin_expand" for case in manifest["cases"].values()) == 6
    # Three entries, and they are two different quantities: `beside-cjk` is the
    # one case whose judgement moved (one unit to twelve, because the exclusion is
    # now cut by the body's language), and the other two are new files, which the
    # manifest also calls changed. Reading the length alone would say "three cases
    # moved" for a version that moved one.
    # Engine 16 lists four entries and every one of them is a new file. Engine 15
    # listed all 26 because it added a branch name every report carries; this
    # version added no name, so the claim to measure is the other one -- that not
    # one carried-over case moved by a byte. Reading the length alone would say
    # "four cases moved" without saying that the other 45 did not.
    new_cases = {
        "B-no-size-word-keeps-the-default",
        "B-small-circle-with-no-radius",
        "B-small-ellipse-with-no-size",
        "B-stated-size-outranks-the-word",
    }
    assert manifest["changed_from_previous"] == sorted(new_cases)
    previous = json.loads(
        (MANIFEST_PATH.parent.parent / "ddl-engine-15" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )["cases"]
    carried = 0
    for case_id, case in manifest["cases"].items():
        if case_id in new_cases:
            continue
        assert case_id in previous, case_id
        assert case["digest"] == previous[case_id]["digest"], case_id
        assert case["bytes"] == previous[case_id]["bytes"], case_id
        carried += 1
    assert carried == 45
    assert sorted(
        case_id
        for case_id, case in manifest["cases"].items()
        if "without_unrequested_color_cycle" in case.get("fired_branches", {})
    ) == [
        "B-leaf-grain-words", "B-orange-from-ddl", "B-production-multiline", "B-purple-from-ddl",
        "B-quiet-water", "B-trigger", "B-yellow-from-ddl", "B-yellow-from-ddl-en",
    ]
    assert not any(
        manifest["cases"][case]["part"] == "a_expand" for case in manifest["changed_from_previous"]
    )

def test_ddl_reference_inputs_are_fully_explicit_and_independent() -> None:
    generator = _generator()
    assert set(generator.BASE_SCORE) == set(Score.model_fields)
    assert set(generator.BASE_SCORE["canvas"]) == set(CanvasSpec.model_fields)
    assert set(generator.BASE_INSTRUCTION) == _aliases(Instruction) - {"note"}
    # group_size=1 is intentionally omitted so engine-15 legacy inputs remain stable.
    assert set(generator.BASE_ARRANGEMENT) == set(Arrangement.model_fields) - {
        "group_size"
    }
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
                assert set(instruction["arrangement"]) == set(
                    Arrangement.model_fields
                ) - {"group_size"}
            if instruction["relation"] is not None:
                assert set(instruction["relation"]) == set(Relation.model_fields)
        if score["presence"] is not None:
            assert set(score["presence"]) == set(Presence.model_fields)

    # Part C hands its input straight to the document plugin manager, so the case
    # record has to name every argument that manager takes -- a default left out
    # of the record is a knob the corpus is not freezing.
    plugin_fields = set(
        inspect.signature(generator.PluginDocumentManager.expand).parameters
    ) - {"self"}
    for case in generator.build_plugin_expand_inputs().values():
        assert set(case) == plugin_fields

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

def test_ddl_reference_plugin_expand_discriminators() -> None:
    """The six C cases measure two quantities, not one.

    `units` is how many whole units the body asked for; `declined` is whether the
    layer refused to deliver them.  A change that trims an over-budget count
    instead of declining it keeps `units` at one and turns `declined` off, so the
    pair has to be read together.
    """
    cases = _manifest()["cases"]
    assert cases["C-plugin-count-in-the-phrase"]["units"] == [3]
    assert cases["C-plugin-count-in-an-english-body"]["units"] == [12]
    # ddl engine 14: the numeral sits within twelve characters of the CJK in
    # `Nature.青葉`, and until then the reader left every such numeral to the
    # Japanese path -- in an English body it read nothing at all and the case
    # froze at one unit.  The exclusion is now cut by the language of the body
    # (ledger I-216), so an English body reads the twelve it states.
    assert cases["C-plugin-count-as-a-numeral-beside-cjk"]["units"] == [12]
    assert cases["C-plugin-count-over-the-ceiling"]["units"] == [1]
    # The count a phrase does not carry is read from the sentence (I-215), and a
    # bare numeral inside a phrase that names a plugin is a count (I-213).
    assert cases["C-plugin-count-outside-the-phrase"]["units"] == [20]
    assert cases["C-plugin-count-as-a-bare-numeral"]["units"] == [50]
    declined = sorted(cid for cid, case in cases.items()
                      if case["part"] == "c_plugin_expand" and case["declined"])
    assert declined == ["C-plugin-count-over-the-ceiling"]
    # The pair whose only difference is `twelve` against `12`. Until ddl engine
    # 14 they had to differ: the numeral sat within twelve characters of the CJK
    # in `Nature.青葉` and the reader dropped it whatever language the body was
    # in, so the spelled-out case asked for twelve and the numeral case for one.
    # The ruling cuts that exclusion by the language of the body (ledger I-216),
    # and the two spellings now mean the same thing -- which is the claim, so the
    # gate is the equality. Re-introducing the exclusion in an English body pulls
    # the digests apart again and turns this red.
    assert (cases["C-plugin-count-in-an-english-body"]["digest"]
            == cases["C-plugin-count-as-a-numeral-beside-cjk"]["digest"])
    assert cases["C-plugin-count-in-an-english-body"]["units"] == \
        cases["C-plugin-count-as-a-numeral-beside-cjk"]["units"]

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
        # `with_primary_color_delivery` joins the delivery cases at ddl-engine 9.
        # It is the same eight everywhere -- these entries, and the manifest's
        # `changed_from_previous` above. The promotion always could have fired on
        # them; it ran before the repair that puts the color in a cycle, and it
        # can only promote what a cycle already carries, so it found nothing and
        # the work waited for a second pass that production never made.
        # `without_unrequested_color_cycle` joins them at ddl-engine 10, and it is
        # the same set again: a DDL that names one color, delivered into a cycle
        # that also carries another. Delivery puts the color there, the promotion
        # moves it to the primary stroke, and this branch takes the cycle away so
        # the color the description named reaches every member and not half.
        "B-trigger": {
            "coerce_and_repair_instruction", "with_color_delivery_repair",
            "with_primary_color_delivery", "with_motion_energy",
            "without_unrequested_color_cycle",
        },
        "B-quiet-water": {
            "with_color_delivery_repair", "with_primary_color_delivery",
            "without_unrequested_color_cycle",
        },
        "B-presence-from-ddl": {
            "presence_from_ddl", "with_color_delivery_repair", "with_primary_color_delivery",
        },
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
        "B-leaf-grain-words": {
            "with_color_delivery_repair", "with_primary_color_delivery", "with_complex_motif_repair",
            "without_unrequested_color_cycle",
        },
        "B-yellow-from-ddl": {
            "with_color_delivery_repair", "with_primary_color_delivery",
            "without_unrequested_color_cycle",
        },
        "B-orange-from-ddl": {
            "with_color_delivery_repair", "with_primary_color_delivery", "with_motion_energy",
            "without_unrequested_color_cycle",
        },
        "B-purple-from-ddl": {
            "with_color_delivery_repair", "with_primary_color_delivery",
            "without_unrequested_color_cycle",
        },
        "B-yellow-from-ddl-en": {
            "with_color_delivery_repair", "with_primary_color_delivery",
            "without_unrequested_color_cycle",
        },
        # The pair added at ddl-engine 12, and they are asserted here rather than
        # left to the frozen bytes on purpose: a corpus is a record that gets
        # regenerated, so a case can quietly stop exercising what it was added
        # for and the files still match. These two say it out loud -- one where a
        # stated count above the old band is written, one where the same branch
        # declines because the work has no room for it.
        "B-stated-count-in-the-wide-band": {"with_stated_count_fidelity"},
        "B-stated-count-over-the-work-budget": set(),
        # The four added at ddl-engine 16, and they are asserted here for the same
        # reason the pair above is. `coerce_and_repair_instruction` covers both the
        # defaults going in and the size rule filling one, so it cannot separate
        # them by itself -- what separates them is the last case: the model stated
        # 0.3, nothing else in the instruction needed repairing, and the pass that
        # would have moved it does not fire at all. The count branch fires on all
        # four because each description states how many.
        "B-small-circle-with-no-radius": {
            "coerce_and_repair_instruction", "with_stated_count_fidelity",
        },
        "B-small-ellipse-with-no-size": {
            "coerce_and_repair_instruction", "with_stated_count_fidelity",
        },
        "B-no-size-word-keeps-the-default": {
            "coerce_and_repair_instruction", "with_stated_count_fidelity",
        },
        "B-stated-size-outranks-the-word": {"with_stated_count_fidelity"},
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
    # exactly like a gate that passed. 15 at ddl-engine 12, which added two coerce
    # cases that carry a DDL; 18 at ddl-engine 15, whose three surface cases each
    # carry one; 22 at ddl-engine 16, whose four size cases each carry one too.
    assert checked == 22


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


def test_the_corpus_holds_a_stated_count_above_the_band_engine_eleven_stopped_at() -> None:
    """Read from the generator, not from the frozen manifest.

    The manifest is written by this generator, so a case deleted from
    `build_coerce_inputs()` leaves the frozen files -- and every test that reads
    them -- untouched until somebody regenerates. Until ddl-engine 12 the corpus
    held no stated count above eleven at all, which is the state this guards
    against returning to.
    """
    from inku_server.counts import _explicit_counts_from_ddl
    from inku_server.limits import DEFAULT_LIMITS

    cases = _generator().build_coerce_inputs()
    band = DEFAULT_LIMITS.literal_count_threshold - 1

    written = cases["B-stated-count-in-the-wide-band"]
    stated = _explicit_counts_from_ddl(written["ddl"])
    assert any(11 < value <= band for value in stated), stated
    counts = [
        (ins.get("arrangement") or {}).get("count") or 1
        for ins in written["score"]["instructions"]
    ]
    assert not (set(counts) & stated), "Stage 2 must have missed the count, or nothing is repaired"

    declined = cases["B-stated-count-over-the-work-budget"]
    stated = _explicit_counts_from_ddl(declined["ddl"])
    assert any(11 < value <= band for value in stated), stated
    standing = sum(
        (ins.get("arrangement") or {}).get("count") or 1
        for ins in declined["score"]["instructions"]
    )
    assert standing <= DEFAULT_LIMITS.max_expanded_primitives, "the case must be legal before the repair"
    assert any(
        standing - (
            (declined["score"]["instructions"][-1].get("arrangement") or {}).get("count") or 1
        ) + value > DEFAULT_LIMITS.max_expanded_primitives
        for value in stated
    ), "and over the budget only once the stated count is written"
