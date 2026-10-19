//! The laws stage (stage B-2c of the laws port) answers as its prototype did.
//!
//! The fixture holds, for each work of a replayed run, the run's compiler
//! options and the composed plan the laws stage waits with, the colour-stripped
//! answer narrowed to this stage's laws and the DDL the Python prototype printed
//! from it; and made cases for the forms the works do not have (a moved grid or
//! scatter, a pair, a triangle, a joint dropped). The requests are the
//! prototype's, in both languages. It holds no description text and no reason.

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
    choose_laws,
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

#[derive(Deserialize)]
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
/// byte for byte, works and made cases. The works measured with one law are
/// applied as the prototype applied them, without the request's count rule.
#[test]
fn the_laws_print_as_the_prototype_printed_them() {
    let fixture = fixture();
    let definitions = definitions();
    let cases: Vec<&Case> = fixture
        .cases
        .iter()
        .filter(|case| case.answer.is_some())
        .collect();
    assert_eq!(cases.len(), 26);
    assert_eq!(cases.iter().filter(|case| case.kind == "made").count(), 8);
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
/// canvas cannot hold reads canonically and has no diagnostic, but no Score.
#[test]
fn the_printed_documents_compile_to_a_score() {
    let fixture = fixture();
    let definitions = definitions();
    let cases: Vec<&Case> = fixture
        .cases
        .iter()
        .filter(|case| case.answer.is_some())
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
                json!({"B5": diagonal, "B9": {"targets": [{"layer": 0, "form": "row"}]}}),
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
