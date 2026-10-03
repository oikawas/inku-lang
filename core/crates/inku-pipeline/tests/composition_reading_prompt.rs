//! The composition reading request is built as the prototype built the requests it
//! measured: for every work of a Stage 1 run, the same system text, message and
//! response schema.
//!
//! The fixture holds the normalized plans of the run and the prototype's message for
//! each, with a placeholder for the description (the message holds the description
//! verbatim at its head). It holds no description text. The expected messages
//! write the size 特大の with one の (I-709); the measured requests had 特大のの.

use std::collections::BTreeMap;

use inku_ddl::work_plan::WorkPlan;
use inku_ddl::{MacroDefinition, NATURE_LEAVES_V1_JSON, ResolvedInstructionLanguage};
use inku_pipeline::composition_reading::{
    COMPOSITION_READING_PROMPT_ID, build_composition_reading_prompt,
};
use inku_pipeline::prompts::{LlmStage, PromptLimits, work_plan_plugins};
use serde::Deserialize;
use serde_json::Value;

const FIXTURE: &str = include_str!("data/composition-reading-prompt-v1.json");

#[derive(Deserialize)]
struct Fixture {
    schema: String,
    placeholder: BTreeMap<String, String>,
    system: BTreeMap<String, String>,
    response_schemas: BTreeMap<String, Value>,
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    id: String,
    lang: String,
    plan: WorkPlan,
    message: String,
}

fn language(lang: &str) -> ResolvedInstructionLanguage {
    match lang {
        "ja" => ResolvedInstructionLanguage::Ja,
        _ => ResolvedInstructionLanguage::En,
    }
}

/// The bundled nature plugins, which the plans of the run name.
fn nature_definitions() -> Vec<MacroDefinition> {
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

fn first_difference(left: &str, right: &str) -> usize {
    left.bytes()
        .zip(right.bytes())
        .position(|(a, b)| a != b)
        .unwrap_or(left.len().min(right.len()))
}

/// A few hundred bytes around `at`, cut on character boundaries.
fn excerpt(text: &str, at: usize) -> &str {
    let mut start = at.saturating_sub(120);
    while !text.is_char_boundary(start) {
        start -= 1;
    }
    let mut end = (at + 240).min(text.len());
    while !text.is_char_boundary(end) {
        end += 1;
    }
    &text[start..end]
}

#[test]
fn the_reading_request_is_built_as_the_prototype_built_it() {
    let fixture: Fixture = serde_json::from_str(FIXTURE).expect("the fixture is JSON");
    assert_eq!(fixture.schema, "inku.composition-reading-prompt-fixture.v1");
    let definitions = nature_definitions();
    let plugins = work_plan_plugins(&definitions);
    let limits = PromptLimits {
        max_catalog_entries: 64,
        max_summary_bytes: 8192,
        max_catalog_serialized_bytes: 1024 * 1024,
        max_source_bytes: 400_000,
        max_response_bytes: 1024 * 1024,
    };
    let (mut compared, mut failures) = (0, Vec::new());
    let mut differing: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    for case in &fixture.cases {
        let prompt = build_composition_reading_prompt(
            &fixture.placeholder[&case.lang],
            &case.plan,
            &plugins,
            language(&case.lang),
            limits,
        )
        .unwrap_or_else(|error| panic!("{}: {error:?}", case.id));
        assert_eq!(prompt.stage, LlmStage::ReadComposition);
        assert_eq!(prompt.prompt_id, COMPOSITION_READING_PROMPT_ID);
        let expected_system = &fixture.system[&case.lang];
        if &prompt.system != expected_system {
            differing.entry("system").or_default().push(&case.id);
            let at = first_difference(&prompt.system, expected_system);
            failures.push(format!(
                "{}: system from byte {at}\n{}\nexpected\n{}",
                case.id,
                excerpt(&prompt.system, at),
                excerpt(expected_system, at)
            ));
        }
        if prompt.message != case.message {
            differing.entry("message").or_default().push(&case.id);
            failures.push(format!(
                "{}: message\n{}\nexpected\n{}",
                case.id, prompt.message, case.message
            ));
        }
        let expected = &fixture.response_schemas[&case.plan.layers.len().to_string()];
        if &prompt.response_schema != expected {
            differing
                .entry("response schema")
                .or_default()
                .push(&case.id);
            failures.push(format!(
                "{}: response schema\n{}\nexpected\n{}",
                case.id, prompt.response_schema, expected
            ));
        }
        compared += 1;
    }
    println!("{compared} reading requests compared");
    // The summary comes last: a runner may keep only the tail of the output.
    let summary: Vec<String> = differing
        .iter()
        .map(|(part, ids)| format!("{part}: {} ({})", ids.len(), ids.join(", ")))
        .collect();
    assert!(
        failures.is_empty(),
        "{}\n\n{} of {compared} differ; {}",
        failures.join("\n\n"),
        failures.len(),
        summary.join("; ")
    );
    assert_eq!(compared, 49);
}
