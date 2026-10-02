//! The composition reading request is built as the prototype built the requests it
//! measured: for every work of a Stage 1 run, the same system text, message and
//! response schema.
//!
//! The fixture holds the normalized plans of the run and the prototype's message for
//! each, with a placeholder for the description (the message holds the description
//! verbatim at its head). It holds no description text.

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
        if prompt.system != fixture.system[&case.lang] {
            failures.push(format!("{}: system differs", case.id));
        }
        if prompt.message != case.message {
            failures.push(format!(
                "{}: message\n{}\nexpected\n{}",
                case.id, prompt.message, case.message
            ));
        }
        let expected = &fixture.response_schemas[&case.plan.layers.len().to_string()];
        if &prompt.response_schema != expected {
            failures.push(format!(
                "{}: response schema\n{}\nexpected\n{}",
                case.id, prompt.response_schema, expected
            ));
        }
        compared += 1;
    }
    println!("{compared} reading requests compared");
    assert!(
        failures.is_empty(),
        "{} of {compared} differ:\n{}",
        failures.len(),
        failures.join("\n\n")
    );
    assert_eq!(compared, 49);
}
