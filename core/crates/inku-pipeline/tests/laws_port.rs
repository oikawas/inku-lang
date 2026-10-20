//! The laws stage (stages B-2c, B-3 and B-4b of the laws port) answers as its
//! prototype did.
//!
//! The fixture holds, for each work of a replayed run, the run's compiler
//! options and the composed plan the laws stage waits with, the colour-stripped
//! answer narrowed to this stage's laws and the DDL the Python reference printed
//! from it; made cases for the forms the works do not have (a moved grid or
//! scatter, a pair and a turned pair, a triangle, a joint dropped, beat groups,
//! a progression of sizes, a grid the core tiles otherwise than the prototype
//! counted, and each card: the five patterns, dense places, voices, motifs,
//! jo-ha-kyu and shin-gyo-so); and wide cases on the wide canvas. The requests
//! are the reference's, in both languages. It holds no description text and no
//! reason.

mod common;

use std::collections::BTreeMap;

use inku_ddl::work_plan::WorkPlanPlugin;
use inku_ddl::{
    MacroDefinition, MacroLock, NATURE_LEAVES_V1_JSON, NormalizedDdlDocument,
    ResolvedInstructionLanguage, ScoreLoweringOutcome,
};
use inku_pipeline::core_boundary::{CompilerOptions, compile_committed};
use inku_pipeline::laws::{
    ComposedPlan, LAWS_PROMPT_ID, LawsContext, apply_laws_without_count_rule, build_laws_prompt,
    choose_laws, off_canvas,
};
use inku_pipeline::prompts::{LlmStage, PromptLimits, work_plan_plugins};
use serde::Deserialize;
use serde_json::{Value, json};

const FIXTURE: &str = include_str!("data/laws-port-v1.json");

const LIMITS: PromptLimits = PromptLimits {
    max_catalog_entries: 64,
    max_summary_bytes: 8192,
    max_catalog_serialized_bytes: 1024 * 1024,
    max_source_bytes: 400_000,
    max_response_bytes: 1024 * 1024,
};

#[derive(Deserialize)]
struct Fixture {
    schema: String,
    placeholder: BTreeMap<String, String>,
    system: BTreeMap<String, String>,
    cases: Vec<Case>,
}

#[derive(Clone, Deserialize)]
struct Case {
    id: String,
    kind: String,
    lang: String,
    compiler: Value,
    composed: ComposedPlan,
    source: String,
    #[serde(default)]
    message: Option<BTreeMap<String, String>>,
    #[serde(default)]
    schema: Option<Value>,
    answer: Option<Value>,
    laws: Option<String>,
    /// The layer the stage refuses because the canvas cannot hold the print.
    #[serde(default)]
    off_canvas: Option<usize>,
}

fn fixture() -> Fixture {
    let fixture: Fixture = serde_json::from_str(FIXTURE).expect("the fixture is JSON");
    assert_eq!(fixture.schema, "inku.laws-port-fixture.v1");
    fixture
}

fn language(lang: &str) -> ResolvedInstructionLanguage {
    match lang {
        "ja" => ResolvedInstructionLanguage::Ja,
        _ => ResolvedInstructionLanguage::En,
    }
}

/// The bundled Nature words, which one work draws beside its layers.
fn definitions() -> Vec<MacroDefinition> {
    let package: Value = serde_json::from_str(NATURE_LEAVES_V1_JSON).expect("the asset is JSON");
    package["entries"]
        .as_array()
        .expect("the asset has entries")
        .iter()
        .map(|entry| {
            MacroDefinition::from_json(&entry["definition"].to_string())
                .expect("a bundled definition reads")
        })
        .collect()
}

/// A visible source as a document, with the locks of the definitions.
fn document(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> NormalizedDdlDocument {
    let locks = definitions
        .iter()
        .map(|definition| {
            let identity = definition.identity().expect("a definition's identity");
            MacroLock::new(
                identity.qualified_name(),
                identity.version(),
                format!("sha256:{}", identity.full_digest_hex()),
            )
            .and_then(|lock| lock.with_aliases(definition.alias_qualified_names()))
            .expect("a definition's lock")
        })
        .collect();
    NormalizedDdlDocument::new(source, language, locks).expect("a visible document")
}

/// What the laws read of a case: its composed source compiled with the run's
/// options, on the canvas the options name (or another one).
fn context(
    case: &Case,
    canvas: Option<&str>,
    definitions: &[MacroDefinition],
) -> (LawsContext, Vec<WorkPlanPlugin>, CompilerOptions) {
    let mut compiler = case.compiler.clone();
    if let Some(canvas) = canvas {
        compiler["host"]["canvas_format_id"] = json!(canvas);
    }
    let compiler: CompilerOptions =
        serde_json::from_value(compiler).unwrap_or_else(|error| panic!("{}: {error}", case.id));
    let delivery = compile_committed(
        document(&case.source, language(&case.lang), definitions),
        definitions,
        &compiler,
    )
    .unwrap_or_else(|error| panic!("{}: {error:?}", case.id));
    let score = delivery
        .score
        .unwrap_or_else(|| panic!("{}: the composed source has no Score", case.id));
    let context = LawsContext::new(
        score,
        &case.composed,
        compiler.host.palette(),
        compiler.host.canvas_format_id(),
    )
    .unwrap_or_else(|| panic!("{}: the Score has no layer per sentence", case.id));
    (context, work_plan_plugins(definitions), compiler)
}

fn first_difference(left: &str, right: &str) -> String {
    let at = left
        .lines()
        .zip(right.lines())
        .position(|(a, b)| a != b)
        .unwrap_or(left.lines().count().min(right.lines().count()));
    format!(
        "line {at}:\n  got  {}\n  want {}",
        left.lines().nth(at).unwrap_or(""),
        right.lines().nth(at).unwrap_or("")
    )
}

#[test]
fn the_composed_plans_print_the_composed_sources() {
    let fixture = fixture();
    let definitions = definitions();
    let plugins = work_plan_plugins(&definitions);
    for case in &fixture.cases {
        assert_eq!(
            case.composed.source(language(&case.lang), &plugins),
            case.source,
            "{}",
            case.id
        );
    }
}

/// The laws are applied and printed as the prototype applied and printed them:
/// byte for byte, works, made cases and wide cases, each on its run's canvas.
/// The works measured with one law are applied as the prototype applied them,
/// without the request's count rule.
#[test]
fn the_laws_print_as_the_prototype_printed_them() {
    let fixture = fixture();
    let definitions = definitions();
    let cases: Vec<&Case> = fixture
        .cases
        .iter()
        .filter(|case| case.answer.is_some())
        .collect();
    assert_eq!(cases.len(), 68);
    assert_eq!(cases.iter().filter(|case| case.kind == "made").count(), 35);
    assert_eq!(cases.iter().filter(|case| case.kind == "wide").count(), 10);
    let failures: Vec<String> = common::par_map(&cases, |case| {
        let (context, plugins, _) = context(case, None, &definitions);
        let answer = case.answer.as_ref().expect("an answer");
        let chosen = apply_laws_without_count_rule(answer, &context, &case.composed)
            .unwrap_or_else(|refusal| panic!("{}: refused {refusal:?}", case.id));
        let printed = chosen.print.source(language(&case.lang), &plugins);
        let want = case.laws.as_deref().expect("the prototype's DDL");
        (printed != want).then(|| format!("{}: {}", case.id, first_difference(&printed, want)))
    })
    .into_iter()
    .flatten()
    .collect();
    assert!(
        failures.is_empty(),
        "{} of {} cases differ:\n{}",
        failures.len(),
        cases.len(),
        failures.join("\n")
    );
}

/// Every printed document compiles with its run's options as cleanly as a
/// committed document must: a Score whose lowering did not stop, no resource
/// failure, no diagnostic and nothing left out. A mark at a numeric point the
/// canvas cannot hold reads canonically and has no diagnostic, but no Score
/// (the cases that say so are the next test's).
#[test]
fn the_printed_documents_compile_to_a_score() {
    let fixture = fixture();
    let definitions = definitions();
    let cases: Vec<&Case> = fixture
        .cases
        .iter()
        .filter(|case| case.answer.is_some() && case.off_canvas.is_none())
        .collect();
    let failures: Vec<String> = common::par_map(&cases, |case| {
        let (context, plugins, compiler) = context(case, None, &definitions);
        let answer = case.answer.as_ref().expect("an answer");
        let chosen = apply_laws_without_count_rule(answer, &context, &case.composed)
            .unwrap_or_else(|refusal| panic!("{}: refused {refusal:?}", case.id));
        let printed = chosen.print.source(language(&case.lang), &plugins);
        let delivery = compile_committed(
            document(&printed, language(&case.lang), &definitions),
            &definitions,
            &compiler,
        )
        .unwrap_or_else(|error| panic!("{}: {error:?}", case.id));
        let clean = delivery.score.is_some()
            && delivery.outcome != ScoreLoweringOutcome::Stopped
            && delivery.resource_failure.is_none()
            && delivery.upstream_diagnostics.is_empty()
            && delivery.downstream_diagnostics.is_empty()
            && delivery.resource_omissions.is_empty()
            && delivery.relation_omissions.is_empty();
        (!clean).then(|| {
            format!(
                "{}: {:?} {:?} {:?} {:?}",
                case.id,
                delivery.outcome,
                delivery.resource_failure,
                delivery.upstream_diagnostics,
                delivery.downstream_diagnostics
            )
        })
    })
    .into_iter()
    .flatten()
    .collect();
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

/// A layer opened into marks that leave the canvas is refused with the layer
/// the request numbered, though the printed document's instruction is one of
/// the opened layer's marks.
#[test]
fn a_print_the_canvas_cannot_hold_names_the_requested_layer() {
    let fixture = fixture();
    let definitions = definitions();
    let cases: Vec<&Case> = fixture
        .cases
        .iter()
        .filter(|case| case.off_canvas.is_some())
        .collect();
    assert_eq!(cases.len(), 3);
    for case in cases {
        let (context, plugins, compiler) = context(case, None, &definitions);
        let chosen = apply_laws_without_count_rule(
            case.answer.as_ref().expect("an answer"),
            &context,
            &case.composed,
        )
        .unwrap_or_else(|refusal| panic!("{}: refused {refusal:?}", case.id));
        let printed = chosen.print.source(language(&case.lang), &plugins);
        let delivery = compile_committed(
            document(&printed, language(&case.lang), &definitions),
            &definitions,
            &compiler,
        )
        .unwrap_or_else(|error| panic!("{}: {error:?}", case.id));
        assert!(delivery.score.is_none(), "{}", case.id);
        let failure = delivery.resource_failure.expect("a resource failure");
        let owner = &failure["value"]["value"]["owner"];
        assert_eq!(
            owner["kind"], "source_instruction",
            "{}: {failure}",
            case.id
        );
        let instruction = owner["instruction_index"]
            .as_u64()
            .and_then(|index| usize::try_from(index).ok())
            .expect("an instruction index");
        let layer = case.off_canvas.expect("the refused layer");
        let refusal = off_canvas(&chosen, &context, instruction)
            .unwrap_or_else(|| panic!("{}: instruction {instruction} is not refused", case.id));
        assert_eq!(refusal.code, "off_canvas");
        assert!(
            refusal.ja.starts_with(&format!("layer {layer} は")),
            "{}: {}",
            case.id,
            refusal.ja
        );
        assert!(
            refusal
                .en
                .starts_with(&format!("layer {layer} does not fit")),
            "{}: {}",
            case.id,
            refusal.en
        );
        // The refused layer is printed as one sentence per mark.
        let k = layer - case.composed.plan.plugins.len();
        let marks = chosen
            .print
            .composed
            .iter()
            .filter(|composed| **composed == k)
            .count();
        assert!(marks > 1, "{}: layer {layer} is opened into marks", case.id);
    }
}

/// The request is the prototype's: its system text and message in both
/// languages (the description a placeholder) and its schema.
#[test]
fn the_laws_request_is_built_as_the_prototype_builds_it() {
    let fixture = fixture();
    let definitions = definitions();
    let works: Vec<&Case> = fixture
        .cases
        .iter()
        .filter(|case| case.kind == "work")
        .collect();
    assert_eq!(works.len(), 25);
    let failures: Vec<String> = common::par_map(&works, |case| {
        let (context, _, _) = context(case, None, &definitions);
        let mut failures = Vec::new();
        for lang in ["ja", "en"] {
            let prompt =
                build_laws_prompt(&fixture.placeholder[lang], &context, language(lang), LIMITS)
                    .unwrap_or_else(|error| panic!("{} {lang}: {error:?}", case.id));
            assert_eq!(prompt.stage, LlmStage::ChooseLaws);
            assert_eq!(prompt.prompt_id, LAWS_PROMPT_ID);
            if prompt.system != fixture.system[lang] {
                failures.push(format!(
                    "{} {lang}: system {}",
                    case.id,
                    first_difference(&prompt.system, &fixture.system[lang])
                ));
            }
            let message = &case.message.as_ref().expect("a work's messages")[lang];
            if &prompt.message != message {
                failures.push(format!(
                    "{} {lang}: message {}",
                    case.id,
                    first_difference(&prompt.message, message)
                ));
            }
            if Some(&prompt.response_schema) != case.schema.as_ref() {
                failures.push(format!("{} {lang}: schema", case.id));
            }
        }
        failures
    })
    .into_iter()
    .flatten()
    .collect();
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

/// On a wide canvas a law keeps its places in canvas fractions and its sizes in
/// short-edge units. These works lay their rows on the armature's diagonals and
/// on a vertical guide line, shrink by a fixed ratio and fit a horizontal row to
/// a spacing the canvas widens as much as the row's own, so they print as on the
/// square canvas; and the printed document compiles cleanly on the wide one.
#[test]
fn on_a_wide_canvas_the_laws_keep_their_places_and_sizes() {
    let fixture = fixture();
    let definitions = definitions();
    for id in ["ja-11", "ja-19", "en-01-rows", "ja-05-rectangle"] {
        let case = fixture
            .cases
            .iter()
            .find(|case| case.id == id)
            .expect("the case");
        let (context, plugins, compiler) = context(case, Some("wide"), &definitions);
        let chosen = apply_laws_without_count_rule(
            case.answer.as_ref().expect("an answer"),
            &context,
            &case.composed,
        )
        .unwrap_or_else(|refusal| panic!("{id}: refused {refusal:?}"));
        let printed = chosen.print.source(language(&case.lang), &plugins);
        let want = case.laws.as_deref().expect("the square canvas's DDL");
        assert_eq!(printed, want, "{id}: {}", first_difference(&printed, want));
        let delivery = compile_committed(
            document(&printed, language(&case.lang), &definitions),
            &definitions,
            &compiler,
        )
        .expect("the printed document compiles");
        assert!(delivery.score.is_some(), "{id}");
        assert!(
            delivery.upstream_diagnostics.is_empty() && delivery.downstream_diagnostics.is_empty(),
            "{id}: {:?} {:?}",
            delivery.upstream_diagnostics,
            delivery.downstream_diagnostics
        );
    }
}

/// The tool refuses an answer that breaks the request's rules, with a code and
/// the reason in both languages.
#[test]
fn the_tool_refuses_answers_that_break_the_rules() {
    let fixture = fixture();
    let definitions = definitions();
    let case = fixture
        .cases
        .iter()
        .find(|case| case.id == "ja-11")
        .expect("ja-11");
    let (context, _, _) = context(case, None, &definitions);
    let answer = |laws: Value, main_law: &str, main_layer: u64| {
        json!({"main_layer": main_layer, "main_law": main_law, "description_counts": [],
               "laws": laws, "reason": "（理由）"})
        .to_string()
    };
    let diagonal = json!({"targets": [{"layer": 0, "path": "diagonal_down"}]});
    let still = json!({"targets": [{"layer": 1, "hand": "still"}]});
    for (response, code) in [
        ("not json".to_owned(), "not_json"),
        (json!({"main_layer": 0}).to_string(), "missing"),
        (
            answer(json!({"B5": diagonal, "B21": still}), "B21", 0),
            "not_a_choice",
        ),
        (answer(json!({"B5": diagonal}), "B5", 0), "law_count"),
        (
            answer(
                json!({"B5": diagonal, "B21": still, "B1": {"targets": [{"layer": 0, "at": "line_left"}]}}),
                "B5",
                0,
            ),
            "two_placements",
        ),
        (
            answer(json!({"B5": diagonal, "B6": {"secondary": [1]}}), "B5", 0),
            "subordination_main",
        ),
        (
            answer(
                json!({"B5": diagonal, "B11": {"targets": [{"layer": 0, "colors": ["white", "orange"]}]}}),
                "B5",
                0,
            ),
            "unknown_law",
        ),
        (
            answer(json!({"B5": diagonal, "B7": {"layer": 1}}), "B5", 1),
            "balance_main",
        ),
        (
            answer(
                json!({"B5": {"targets": [{"layer": 7, "path": "diagonal_down"}]}, "B21": still}),
                "B5",
                0,
            ),
            "not_a_choice",
        ),
    ] {
        let refusal = choose_laws(&response, &context, &case.composed, LIMITS)
            .expect_err(&format!("{response} is refused"));
        assert_eq!(refusal.code, code, "{response}: {refusal:?}");
        assert!(!refusal.ja.is_empty() && !refusal.en.is_empty());
    }
    let chosen = choose_laws(
        &answer(json!({"B5": diagonal, "B21": still}), "B5", 0),
        &context,
        &case.composed,
        LIMITS,
    )
    .expect("two laws are chosen");
    assert_eq!(chosen.laws, ["B5", "B21"]);
    // Layer 1 has no fluctuation to still, so only the row the armature lays changes.
    assert_eq!(chosen.print.changed, [0]);
}

/// The arrangement laws' refusals, with the prototype's reasons: two of them on
/// one layer, a progression toward a side its row does not run to, a
/// progression of spacing or beat groups with too few things, an arrangement of
/// a pair B8 opened, and a Score past the limit of instructions.
#[test]
fn the_tool_refuses_arrangements_it_cannot_lay() {
    let fixture = fixture();
    let definitions = definitions();
    let answer = |laws: Value, main_law: &str, main_layer: u64| {
        json!({"main_layer": main_layer, "main_law": main_law, "description_counts": [],
               "laws": laws, "reason": "（理由）"})
        .to_string()
    };
    let case = fixture
        .cases
        .iter()
        .find(|case| case.id == "ja-04")
        .expect("ja-04");
    let (context, _, _) = context(case, None, &definitions);
    let still = json!({"targets": [{"layer": 2, "hand": "still"}]});
    for (response, code, ja) in [
        (
            answer(
                json!({"B9": {"targets": [{"layer": 1, "form": "row"}]},
                       "B12": {"targets": [{"layer": 1, "group": "3", "strong": "first"}]}}),
                "B9",
                1,
            ),
            "arrangement_twice",
            "layer 1 に並びの法則が二つ（B9・B12）。一つにする",
        ),
        (
            answer(
                json!({"B10": {"targets": [{"layer": 1, "change": "size", "ratio": "0.618", "toward": "left"}]},
                       "B21": still}),
                "B10",
                1,
            ),
            "row_direction",
            "B10: 列の向きに left が無い（横の列には left・right、縦の列には top・bottom）",
        ),
        (
            answer(
                json!({"B10": {"targets": [{"layer": 0, "change": "spacing", "ratio": "0.618", "toward": "right"}]},
                       "B21": still}),
                "B10",
                0,
            ),
            "progression_count",
            "B10: layer 0 は 2 個で、間隔の漸進には3個以上要る",
        ),
        (
            answer(
                json!({"B12": {"targets": [{"layer": 0, "group": "2", "strong": "first"}]},
                       "B21": still}),
                "B12",
                0,
            ),
            "beat_count",
            "B12: layer 0 は 2 個で、2 個ずつの群が二つできない",
        ),
        (
            answer(
                json!({"B8": {"targets": [{"layer": 0, "axis": "vertical"}]},
                       "B9": {"targets": [{"layer": 0, "form": "row"}]}}),
                "B8",
                0,
            ),
            "layer_split",
            "B9: layer 0 はすでに 2 個の指示に分かれていて、この法則を当てられない",
        ),
    ] {
        let refusal = choose_laws(&response, &context, &case.composed, LIMITS)
            .expect_err(&format!("{response} is refused"));
        assert_eq!(refusal.code, code, "{response}: {refusal:?}");
        assert_eq!(refusal.ja, ja, "{response}");
        assert!(!refusal.en.is_empty());
    }
    // Seventy points opened one by one leave seventy-one instructions.
    let mut many = fixture
        .cases
        .iter()
        .find(|case| case.id == "ja-05")
        .expect("ja-05")
        .clone();
    assert_eq!(many.source.matches("点を24個散らす").count(), 1);
    many.source = many.source.replace("点を24個散らす", "点を70個散らす");
    many.composed.plan.layers[1].count = 70;
    let (crowded, _, _) = self::context(&many, None, &definitions);
    let refusal = choose_laws(
        &answer(
            json!({"B10": {"targets": [{"layer": 1, "change": "spacing", "ratio": "0.618", "toward": "right"}]},
                   "B21": {"targets": [{"layer": 1, "hand": "still"}]}}),
            "B10",
            1,
        ),
        &crowded,
        &many.composed,
        LIMITS,
    )
    .expect_err("seventy-one instructions are refused");
    assert_eq!(refusal.code, "too_many_instructions", "{refusal:?}");
    assert_eq!(
        refusal.ja,
        "指示が 71 になり上限 60 を超える。数や回数を小さくするか法則を減らす"
    );
}

/// The cards' refusals, with the prototype's reasons: the recorded answer of
/// ja-01, whose pattern color the black ground hides; a card sharing its layer
/// with another placement, arrangement or card law; a hand on C6's layer; a
/// count the description writes changed by a pattern or voices or by C1; C1's
/// six times; C4's repeats; a value past its schema's bound; and a layer of
/// more marks than C6 opens.
#[test]
fn the_tool_refuses_cards_it_cannot_lay() {
    let fixture = fixture();
    let definitions = definitions();
    let answer = |laws: Value, main_law: &str, main_layer: u64, counts: Value| {
        json!({"main_layer": main_layer, "main_law": main_law, "description_counts": counts,
               "laws": laws, "reason": "（理由）"})
        .to_string()
    };
    let case = |id: &str| {
        fixture
            .cases
            .iter()
            .find(|case| case.id == id)
            .expect("the case")
            .clone()
    };
    let refused = |case: &Case, response: String| {
        let (context, _, _) = context(case, None, &definitions);
        choose_laws(&response, &context, &case.composed, LIMITS)
            .expect_err(&format!("{response} is refused"))
    };
    let ichimatsu = json!({"layer": 0, "pattern": "ichimatsu", "area": "whole", "unit": "1/8",
                           "colors": ["white", "blue"]});
    let still = |layer: u64| json!({"targets": [{"layer": layer, "hand": "still"}]});
    let spiral = |layer: u64, repeats: u64| json!({"layer": layer, "repeats": repeats, "sequence": ["rotate"], "path": "golden_spiral"});
    for (id, response, code, ja) in [
        (
            "ja-01",
            answer(
                json!({"C2": ichimatsu,
                       "B21": {"targets": [{"layer": 1, "hand": "keep"}, {"layer": 2, "hand": "fine"}]}}),
                "C2",
                0,
                json!([]),
            ),
            "invisible_color",
            "文様の色 blue は地 black と明るさが 0.15 未満しか違わず見えない".to_owned(),
        ),
        (
            "ja-12",
            answer(
                json!({"C2": {"layer": 0, "pattern": "shippo", "area": "whole", "unit": "1/8", "colors": ["white"]},
                       "B9": {"targets": [{"layer": 0, "form": "grid"}]}}),
                "C2",
                0,
                json!([]),
            ),
            "rebuild_shared",
            "layer 0 は C1〜C6 が置き場と並びを作り直すので、ほかの置き場・並びの法則や C1〜C6 と重ねられない（B9・C2）".to_owned(),
        ),
        (
            "ja-12",
            answer(
                json!({"C6": {"layer": 0, "split": "three_bands", "order": "shin_gyo_so", "so_degree": "small"},
                       "B21": still(0)}),
                "C6",
                0,
                json!([]),
            ),
            "hand_on_c6",
            "C6 の層の手は C6 が決めるので、B21 を重ねない".to_owned(),
        ),
        (
            "ja-13",
            answer(
                json!({"C3": {"voices": [0, 1], "ratio": "2:3", "base": 4, "axis": "horizontal", "band": "0.5"},
                       "B15": {"layers": [1]}}),
                "C3",
                0,
                json!([0]),
            ),
            "counted_layer",
            "layer 0 は記述が数を書いた物なので、数の変わる声部にできない".to_owned(),
        ),
        (
            "ja-08",
            answer(
                json!({"C1": {"targets": [{"layer": 2, "count": 30}], "spot": "center", "extent": "0.25"},
                       "B21": still(0)}),
                "C1",
                2,
                json!([2]),
            ),
            "count_kept",
            "layer 2 は記述が数を書いた物なので 24 のまま".to_owned(),
        ),
        (
            "ja-08",
            answer(
                json!({"C1": {"targets": [{"layer": 2, "count": 200}], "spot": "center", "extent": "0.25"},
                       "B21": still(0)}),
                "C1",
                2,
                json!([]),
            ),
            "count_six_times",
            "layer 2 の数は今の6倍（144）まで".to_owned(),
        ),
        (
            "ja-12",
            answer(json!({"C4": spiral(1, 5), "B21": still(0)}), "C4", 1, json!([1])),
            "repeats_kept",
            "layer 1 の数は記述が書いた数 9 のままにする".to_owned(),
        ),
        (
            "ja-12",
            answer(json!({"C4": spiral(1, 12), "B21": still(0)}), "C4", 1, json!([])),
            "repeats_most",
            "layer 1 の回数は 9 まで（今の数と 9 の大きいほう）".to_owned(),
        ),
        (
            "ja-12",
            answer(json!({"C4": spiral(0, 10), "B21": still(1)}), "C4", 0, json!([])),
            "repeats_least",
            "layer 0 は今 16 個。記述が数を書いていない層は減らさない（回数は 16〜16）".to_owned(),
        ),
        (
            "ja-13",
            answer(
                json!({"C3": {"voices": [0, 1], "ratio": "2:3", "base": 9, "axis": "horizontal", "band": "0.5"},
                       "B15": {"layers": [1]}}),
                "C3",
                0,
                json!([]),
            ),
            "out_of_range",
            "answer.laws.C3.base = 9 は 2〜8 の外".to_owned(),
        ),
    ] {
        let refusal = refused(&case(id), response.clone());
        assert_eq!(refusal.code, code, "{id} {response}: {refusal:?}");
        assert_eq!(refusal.ja, ja, "{id} {response}");
        assert!(!refusal.en.is_empty());
    }
    // Sixty squares tiled are more than C6 opens one by one.
    let mut many = case("ja-12");
    assert_eq!(many.source.matches("四角を16個敷き詰める").count(), 1);
    many.source = many
        .source
        .replace("四角を16個敷き詰める", "四角を60個敷き詰める");
    many.composed.plan.layers[0].count = 60;
    let refusal = refused(
        &many,
        answer(
            json!({"C6": {"layer": 0, "split": "sequence", "order": "so_gyo_shin", "so_degree": "large"},
                   "B21": still(1)}),
            "C6",
            0,
            json!([]),
        ),
    );
    assert_eq!(refusal.code, "c6_unopenable", "{refusal:?}");
    assert_eq!(
        refusal.ja,
        "layer 0 は並べ方（散らす・60 個）のため一つずつに分けられない。別の層を選ぶか C6 を外す"
    );
}
