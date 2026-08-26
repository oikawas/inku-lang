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
    # Engine 18 (2026-08-14): a fill is a surface word like the other eight.
    # **`changed_from_previous` lists all 30 coerce cases and the Score moved in
    # 3** -- the same arithmetic engines 10, 11 and 15 wrote down: a new branch
    # name enters every case's report whether or not the branch fired, so the
    # digest moves everywhere while the transform moves in three. The three are
    # `B-white-filled-circle`, `B-production-fill-clause` and
    # `B-production-no-fill-clause`, and between them they hold the five
    # closed-shape instructions in this corpus that carry `filled=true` with no
    # surface of their own. No expand or plugin-expand case moves: the change
    # lives inside coerce, like engines 8, 9 and 10.
    # Engine 20 (2026-08-16): two of the nine surface words are about the mark,
    # not about an interior. 粒 and にじみ on a line or an arc stay where the
    # sentence put them now, and render engine 37 raises the sheet's own two
    # quantities for that instruction instead of drawing an interior it has not
    # got. **`changed_from_previous` is ONE**, and it is not a new case:
    # `B-surface-with-nowhere-to-move` is the only input in this corpus holding
    # a mark word on an open shape, and its 粒 used to be dropped for having no
    # closed shape to go back to. No branch was added, so the other 29 reports
    # are byte-identical -- the opposite of engines 11, 15 and 18, which listed
    # every coerce case because a new branch name enters every report whether it
    # fired or not. The seven interior words did not move: `wash` on a line is
    # still carried back or dropped, which `B-surface-on-a-line-moves-back`
    # (`hatch`) and `B-surface-already-on-a-closed-shape` (`wash`) keep saying.
    assert DDL_ENGINE_VERSION == "20"
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
    # Engine 17 lists six and not one of them is a new file: every part C case
    # moved, because the record gained the compact Score form the API consumes
    # and every one of these bodies names a plugin whose member is a pair. That
    # is the third quantity this list can hold -- new files, a judgement that
    # moved, and a record that widened -- so the two claims below are separated:
    # the six existed before and their bytes differ, and the other 43 are
    # byte-identical.
    # Engine 18 lists all 30 coerce cases and no new file at all -- the fourth
    # shape this list can hold, and the one engines 10, 11 and 15 had: a branch
    # name entered every report, so every coerce digest moved while the Score
    # moved in three. So the claims are separated again, and the one that says
    # what this version did is the SECOND: the three named below are the cases
    # holding a closed shape with `filled=true` and no surface of its own, and
    # every expand and plugin-expand case is byte-identical because the change
    # lives inside coerce.
    moved_cases = {
        case_id
        for case_id, case in json.loads(
            (MANIFEST_PATH.parent.parent / "ddl-engine-17" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )["cases"].items()
        if case["part"] == "b_coerce"
    }
    scores_that_moved = {
        "B-white-filled-circle",
        "B-production-fill-clause",
        "B-production-no-fill-clause",
    }
    assert len(moved_cases) == 30
    # ⚠ 帰属は版に紐づく。engine 18 が何を動かしたかは engine 18 の manifest で
    # 読む —— 現在版の manifest で読むと、engine 19 を焼いた日に主張の対象が
    # 黙って engine 19 の差分へ入れ替わる。
    root = MANIFEST_PATH.parent.parent
    eighteen_dir = root / "ddl-engine-18"
    eighteen = json.loads((eighteen_dir / "manifest.json").read_text(encoding="utf-8"))
    assert eighteen["engine_version"] == "18"
    assert eighteen["changed_from_previous"] == sorted(moved_cases)
    previous = json.loads(
        (root / "ddl-engine-17" / "manifest.json").read_text(encoding="utf-8")
    )["cases"]
    carried = 0
    scores = 0
    for case_id, case in eighteen["cases"].items():
        if case_id in moved_cases:
            # Not new: it was frozen before and says something different now.
            assert case_id in previous, case_id
            assert case["digest"] != previous[case_id]["digest"], case_id
            # And of those, only three say something different about the Score.
            body = json.loads(
                (eighteen_dir / case["output_path"]).read_text(encoding="utf-8")
            )
            was = json.loads(
                (root / "ddl-engine-17" / case["output_path"]).read_text(encoding="utf-8")
            )
            if body["score"] != was["score"]:
                assert case_id in scores_that_moved, case_id
                scores += 1
            continue
        assert case_id in previous, case_id
        assert case["digest"] == previous[case_id]["digest"], case_id
        assert case["bytes"] == previous[case_id]["bytes"], case_id
        carried += 1
    assert carried == 19
    assert scores == len(scores_that_moved)

    # Engine 19 (2026-08-14): the ground is a support you can name. **This corpus
    # does not move, and the empty list is the whole description of the version**
    # -- the same shape engines 3 and 5 froze in. The layer here holds no prompt,
    # and the eleventh saijiki category carries no closure marker, so nothing the
    # version added is reachable from any input this corpus states. What moved is
    # what the model is offered; the frozen record of that is the Android prompt
    # fixtures keyed by this number.
    # **Read by name from here down.** Until engine 20 this claim was made against
    # the current manifest, which meant the subject of the claim changed the day
    # the next version froze -- the same defect the render corpus carried for its
    # engine 36 attribution and which is fixed there in the same commit.
    nineteen = json.loads(
        (root / "ddl-engine-19" / "manifest.json").read_text(encoding="utf-8")
    )
    assert nineteen["changed_from_previous"] == []
    assert set(nineteen["cases"]) == set(eighteen["cases"])
    for case_id, case in nineteen["cases"].items():
        assert case["digest"] == eighteen["cases"][case_id]["digest"], case_id
        assert case["bytes"] == eighteen["cases"][case_id]["bytes"], case_id

    # Engine 20 (2026-08-16): 粒 and にじみ stay on the open shape the sentence
    # put them on. **ONE case moves and it is not new.** No branch was added, so
    # unlike engines 11, 15 and 18 the other twenty-nine reports are untouched --
    # the arithmetic engine 16 wrote down. The one that moves is the only input
    # here holding a mark word on a line: its 粒 used to be dropped for having no
    # closed shape to go back to, and the drop is what the branch report counted.
    assert manifest["changed_from_previous"] == ["B-surface-with-nowhere-to-move"]
    assert set(manifest["cases"]) == set(nineteen["cases"])
    moved_body = json.loads(
        (root / f"ddl-engine-{DDL_ENGINE_VERSION}" / "b_coerce"
         / "B-surface-with-nowhere-to-move.json").read_text(encoding="utf-8")
    )
    was_body = json.loads(
        (root / "ddl-engine-19" / "b_coerce"
         / "B-surface-with-nowhere-to-move.json").read_text(encoding="utf-8")
    )
    # The surface is kept where it was, and the repair branch stops counting it.
    assert was_body["score"]["instructions"][0]["surface"] is None
    assert moved_body["score"]["instructions"][0]["surface"]["texture"] == "grain"
    assert was_body["branch_report"]["with_surface_on_a_closed_shape"] == 1
    assert moved_body["branch_report"]["with_surface_on_a_closed_shape"] == 0
    for case_id, case in manifest["cases"].items():
        if case_id == "B-surface-with-nowhere-to-move":
            continue
        assert case["digest"] == nineteen["cases"][case_id]["digest"], case_id
        assert case["bytes"] == nineteen["cases"][case_id]["bytes"], case_id
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
    # Every field is stated except the span, which is stated only where a case
    # states one: writing `group_size: 1` into the base would move every input
    # frozen before engine 17 for a span none of them has.
    assert set(generator.BASE_ARRANGEMENT) == set(Arrangement.model_fields) - {
        "group_size"
    }
    assert set(generator.BASE_RELATION) == set(Relation.model_fields)
    assert set(generator.BASE_PRESENCE) == set(Presence.model_fields)

    expand_fields = set(inspect.signature(expand_intermediate_ddl).parameters) - {"variation_report"}
    for case in generator.build_expand_inputs().values():
        assert set(case) == expand_fields

    # `branch_report` and `limit_notes` are out-parameters; `limits` and the
    # optional internal `trace` are injection seams. None describes a reference
    # case, so none belongs in a per-case input record.
    coerce_fields = set(inspect.signature(coerce_score).parameters) - {
        "branch_report",
        "limits",
        "limit_notes",
        "trace",
    }
    for case in generator.build_coerce_inputs().values():
        assert set(case) == coerce_fields
        score = case["score"]
        assert set(score) == set(Score.model_fields)
        assert set(score["canvas"]) == set(CanvasSpec.model_fields)
        for instruction in score["instructions"]:
            assert set(instruction) == _aliases(Instruction) - {"note"}
            if instruction["arrangement"] is not None:
                assert set(instruction["arrangement"]) - {"group_size"} == set(
                    Arrangement.model_fields
                ) - {"group_size"}
            if instruction["relation"] is not None:
                assert set(instruction["relation"]) == set(Relation.model_fields)
        if score["presence"] is not None:
            assert set(score["presence"]) == set(Presence.model_fields)

    # Part C hands its input straight to the document plugin manager, so the case
    # record has to name every argument that manager takes -- a default left out
    # of the record is a knob the corpus is not freezing.
    #
    # `limits` is excluded for the reason `coerce_score`'s is, above: it is the
    # injection seam the settings contract writes through, not something that
    # describes a case. The corpus runs at the defaults by running outside a
    # request, and a case record naming a limit would make it per-install.
    plugin_fields = set(
        inspect.signature(generator.PluginDocumentManager.expand).parameters
    ) - {"self", "limits"}
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
        # ddl-engine 18: the case is a filled circle with no surface of its own,
        # which is exactly the shape the new branch fires on -- it is one of the
        # three whose Score moves in that version. That it is here and not in
        # the entries below is the discriminator: `B-white-line` carries the
        # same repair and no fill, so it does not.
        "B-white-filled-circle": {
            "coerce_and_repair_instruction", "with_fill_as_a_surface_word",
        },
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


def test_ddl_reference_publish_rejects_same_identity_before_touching_live_tree(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    generator = _generator()
    output_dir = tmp_path / f"ddl-engine-{generator.DDL_ENGINE_VERSION}"
    for part in ("a_expand", "b_coerce", "c_plugin_expand"):
        (output_dir / part).mkdir(parents=True, exist_ok=True)
    (output_dir / "a_expand" / "old.txt").write_text("old body\n", encoding="utf-8")
    manifest = {
        "corpus_format_version": generator.CORPUS_FORMAT_VERSION,
        "layer": "ddl-engine",
        "engine_version": generator.DDL_ENGINE_VERSION,
        "ddl_version": generator.DDL_VERSION,
        "schema_version": generator.SCHEMA_VERSION,
        "frozen_at": "2026-08-24",
        "commit": "old-commit",
        "reason": "old reason",
        "changed_from_previous": ["old"],
        "cases": {"old": {"digest": "old"}},
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(generator._canonical_output(manifest), encoding="utf-8")
    before = {
        path.relative_to(output_dir).as_posix(): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }

    monkeypatch.setattr(generator, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(generator, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(
        generator,
        "_render_cases",
        lambda: (
            {"new": {"digest": "new"}},
            {"a_expand/new.txt": "new body\n"},
        ),
    )

    try:
        generator.generate()
    except SystemExit as exc:
        assert "identity-field change" in str(exc)
    else:
        raise AssertionError("same-identity rewrite must be rejected")

    after = {
        path.relative_to(output_dir).as_posix(): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not list(tmp_path.glob(f".{output_dir.name}.staging-*"))
    assert not (tmp_path / f".{output_dir.name}.previous").exists()


def _ddl_publish_manifest(generator, case_id: str, output_path: str) -> dict:
    return {
        "corpus_format_version": generator.CORPUS_FORMAT_VERSION,
        "layer": "ddl-engine",
        "engine_version": generator.DDL_ENGINE_VERSION,
        "ddl_version": generator.DDL_VERSION,
        "schema_version": generator.SCHEMA_VERSION,
        "frozen_at": "2026-08-26",
        "commit": "test-commit",
        "reason": "publication test",
        "changed_from_previous": [case_id],
        "cases": {
            case_id: {
                "digest": hashlib.md5(case_id.encode()).hexdigest(),
                "output_path": output_path,
            }
        },
    }


def _write_complete_ddl_test_corpus(
    generator,
    output_dir: pathlib.Path,
    manifest: dict,
    outputs: dict[str, str],
) -> None:
    for part in ("a_expand", "b_coerce", "c_plugin_expand"):
        (output_dir / part).mkdir(parents=True, exist_ok=True)
    for relative, body in outputs.items():
        (output_dir / relative).write_text(body, encoding="utf-8")
    (output_dir / "manifest.json").write_text(
        generator._canonical_output(manifest), encoding="utf-8"
    )


def _ddl_test_tree_bytes(output_dir: pathlib.Path) -> dict[str, bytes]:
    return {
        path.relative_to(output_dir).as_posix(): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }


def test_ddl_reference_publish_replaces_one_complete_parent_directory(
    tmp_path: pathlib.Path,
) -> None:
    generator = _generator()
    output_dir = tmp_path / "ddl-engine-test"
    old_manifest = _ddl_publish_manifest(generator, "old", "a_expand/old.txt")
    _write_complete_ddl_test_corpus(
        generator, output_dir, old_manifest, {"a_expand/old.txt": "old\n"}
    )
    new_manifest = _ddl_publish_manifest(generator, "new", "b_coerce/new.json")
    new_outputs = {"b_coerce/new.json": "{\"new\": true}\n"}

    generator._publish_output_directory(
        new_manifest, new_outputs, output_dir=output_dir
    )

    assert generator._is_complete_output_directory(output_dir)
    assert not (output_dir / "a_expand" / "old.txt").exists()
    assert (output_dir / "b_coerce" / "new.json").read_text() == new_outputs[
        "b_coerce/new.json"
    ]
    assert not (tmp_path / ".ddl-engine-test.previous").exists()
    assert not list(tmp_path.glob(".ddl-engine-test.staging-*"))

    first = _ddl_test_tree_bytes(output_dir)
    generator._publish_output_directory(
        new_manifest, new_outputs, output_dir=output_dir
    )
    assert _ddl_test_tree_bytes(output_dir) == first


def test_ddl_reference_publish_creates_an_initial_complete_directory(
    tmp_path: pathlib.Path,
) -> None:
    generator = _generator()
    output_dir = tmp_path / "ddl-engine-test"
    manifest = _ddl_publish_manifest(generator, "first", "c_plugin_expand/first.json")

    generator._publish_output_directory(
        manifest,
        {"c_plugin_expand/first.json": "{\"first\": true}\n"},
        output_dir=output_dir,
    )

    assert generator._is_complete_output_directory(output_dir)
    assert not list(tmp_path.glob(".ddl-engine-test.*"))


def test_ddl_reference_publish_staging_failure_leaves_live_tree_untouched(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    generator = _generator()
    output_dir = tmp_path / "ddl-engine-test"
    old_manifest = _ddl_publish_manifest(generator, "old", "a_expand/old.txt")
    _write_complete_ddl_test_corpus(
        generator, output_dir, old_manifest, {"a_expand/old.txt": "old\n"}
    )
    before = _ddl_test_tree_bytes(output_dir)

    def fail_staging(stage, manifest, outputs):
        stage.mkdir()
        (stage / "partial").write_text("partial", encoding="utf-8")
        raise OSError("injected staging failure")

    monkeypatch.setattr(generator, "_write_output_directory", fail_staging)
    try:
        generator._publish_output_directory(
            _ddl_publish_manifest(generator, "new", "b_coerce/new.json"),
            {"b_coerce/new.json": "new\n"},
            output_dir=output_dir,
        )
    except OSError as exc:
        assert str(exc) == "injected staging failure"
    else:
        raise AssertionError("injected staging failure must propagate")

    assert _ddl_test_tree_bytes(output_dir) == before
    assert not list(tmp_path.glob(".ddl-engine-test.staging-*"))
    assert not (tmp_path / ".ddl-engine-test.previous").exists()


def test_ddl_reference_publish_rename_failure_restores_the_old_tree(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    generator = _generator()
    output_dir = tmp_path / "ddl-engine-test"
    old_manifest = _ddl_publish_manifest(generator, "old", "a_expand/old.txt")
    _write_complete_ddl_test_corpus(
        generator, output_dir, old_manifest, {"a_expand/old.txt": "old\n"}
    )
    before = _ddl_test_tree_bytes(output_dir)
    original_rename = pathlib.Path.rename

    def fail_stage_publish(path, target):
        if path.name.startswith(".ddl-engine-test.staging-") and pathlib.Path(
            target
        ) == output_dir:
            raise OSError("injected publication failure")
        return original_rename(path, target)

    monkeypatch.setattr(pathlib.Path, "rename", fail_stage_publish)
    try:
        generator._publish_output_directory(
            _ddl_publish_manifest(generator, "new", "b_coerce/new.json"),
            {"b_coerce/new.json": "new\n"},
            output_dir=output_dir,
        )
    except OSError as exc:
        assert str(exc) == "injected publication failure"
    else:
        raise AssertionError("injected publication failure must propagate")

    assert _ddl_test_tree_bytes(output_dir) == before
    assert not list(tmp_path.glob(".ddl-engine-test.staging-*"))
    assert not (tmp_path / ".ddl-engine-test.previous").exists()


def test_ddl_reference_publish_restores_interrupted_backup_before_new_staging(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    generator = _generator()
    output_dir = tmp_path / "ddl-engine-test"
    backup = tmp_path / ".ddl-engine-test.previous"
    old_manifest = _ddl_publish_manifest(generator, "old", "a_expand/old.txt")
    _write_complete_ddl_test_corpus(
        generator, backup, old_manifest, {"a_expand/old.txt": "old\n"}
    )
    before = _ddl_test_tree_bytes(backup)

    def fail_staging(stage, manifest, outputs):
        raise OSError("stop after backup recovery")

    monkeypatch.setattr(generator, "_write_output_directory", fail_staging)
    try:
        generator._publish_output_directory(
            _ddl_publish_manifest(generator, "new", "b_coerce/new.json"),
            {"b_coerce/new.json": "new\n"},
            output_dir=output_dir,
        )
    except OSError as exc:
        assert str(exc) == "stop after backup recovery"
    else:
        raise AssertionError("injected post-recovery failure must propagate")

    assert _ddl_test_tree_bytes(output_dir) == before
    assert not backup.exists()
    assert not list(tmp_path.glob(".ddl-engine-test.staging-*"))


def test_ddl_reference_publish_refuses_ambiguous_incomplete_trees(
    tmp_path: pathlib.Path,
) -> None:
    generator = _generator()
    output_dir = tmp_path / "ddl-engine-test"
    backup = tmp_path / ".ddl-engine-test.previous"
    output_dir.mkdir()
    backup.mkdir()

    try:
        generator._publish_output_directory(
            _ddl_publish_manifest(generator, "new", "b_coerce/new.json"),
            {"b_coerce/new.json": "new\n"},
            output_dir=output_dir,
        )
    except SystemExit as exc:
        assert "cannot reconcile incomplete" in str(exc)
    else:
        raise AssertionError("ambiguous incomplete trees must stop")

    assert output_dir.is_dir()
    assert backup.is_dir()
    assert not list(tmp_path.glob(".ddl-engine-test.staging-*"))
