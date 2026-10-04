//! A composed placement prints as the prototype printed it, and the printed DDL
//! compiles with no diagnostic: a range replaces a guessed place, a stated place
//! keeps its word, and every composition range and corner reads in both languages.
//! The expected lines write the size 特大の with one の (I-709); the prototype's
//! output, printed before that fix, had 特大のの.

mod common;

use inku_ddl::ResolvedInstructionLanguage;
use inku_ddl::work_plan::{
    WorkPlan, WorkPlanLayer, print_work_plan_composed, work_plan_source_compiles_cleanly,
};
use inku_pipeline::composition;
use serde::Deserialize;

/// The works of the measurements, and the works whose reading names a corner (I-712).
const FIXTURES: [&str; 2] = [
    include_str!("data/composition-port-v1.json"),
    include_str!("data/composition-port-corners-v1.json"),
];

fn fixture_cases() -> Vec<Case> {
    FIXTURES
        .iter()
        .flat_map(|text| {
            let fixture: Fixture = serde_json::from_str(text).expect("the fixture is JSON");
            fixture.cases
        })
        .collect()
}

#[derive(Deserialize)]
struct Fixture {
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    id: String,
    lang: String,
    layers: Vec<WorkPlanLayer>,
    solve: Solve,
}

#[derive(Deserialize)]
struct Solve {
    #[serde(default)]
    s1: Option<Seeded>,
    #[serde(default)]
    s2: Option<Seeded>,
}

#[derive(Deserialize)]
struct Seeded {
    regions: Vec<String>,
    ddl_layers: Vec<String>,
}

fn language(lang: &str) -> ResolvedInstructionLanguage {
    match lang {
        "ja" => ResolvedInstructionLanguage::Ja,
        _ => ResolvedInstructionLanguage::En,
    }
}

fn composed_source(
    layers: &[WorkPlanLayer],
    regions: &[String],
    language: ResolvedInstructionLanguage,
) -> String {
    let plan = WorkPlan {
        layers: layers.to_vec(),
        ..WorkPlan::default()
    };
    let chosen: Vec<usize> = regions
        .iter()
        .map(|key| composition::region_index(key).unwrap_or_else(|| panic!("unknown range {key}")))
        .collect();
    let (plan, ranges) = composition::composed_plan(&plan, &chosen);
    print_work_plan_composed(&plan, language, &[], &ranges)
}

#[test]
fn composed_placements_print_as_the_prototype_and_compile_cleanly() {
    let cases = fixture_cases();
    let checked = common::par_map(&cases, |case| {
        let language = language(&case.lang);
        let (mut printed, mut failures) = (0, Vec::new());
        for (seed, solved) in [("s1", &case.solve.s1), ("s2", &case.solve.s2)] {
            let Some(solved) = solved else { continue };
            let source = composed_source(&case.layers, &solved.regions, language);
            let lines: Vec<&str> = source.lines().collect();
            if lines != solved.ddl_layers {
                failures.push(format!(
                    "{} {seed}: printed\n{}\nexpected\n{}",
                    case.id,
                    source,
                    solved.ddl_layers.join("\n")
                ));
            } else if !work_plan_source_compiles_cleanly(&source, language) {
                failures.push(format!(
                    "{} {seed}: does not compile cleanly\n{source}",
                    case.id
                ));
            }
            printed += 1;
        }
        (printed, failures)
    });
    let printed: usize = checked.iter().map(|(printed, _)| printed).sum();
    let failures: Vec<String> = checked
        .into_iter()
        .flat_map(|(_, failures)| failures)
        .collect();
    println!("{printed} composed placements printed");
    assert!(
        failures.is_empty(),
        "{} of {printed} differ:\n{}",
        failures.len(),
        failures.join("\n\n")
    );
    assert!(printed >= 2 * 240, "only {printed} placements printed");
}

/// Every composition range and corner, written for a layer of each action the
/// fixture holds, compiles with no diagnostic in both languages.
#[test]
fn every_range_and_corner_compiles_cleanly_for_each_action() {
    let cases = fixture_cases();
    let mut examples: Vec<WorkPlanLayer> = Vec::new();
    for case in &cases {
        for layer in &case.layers {
            if !examples.iter().any(|seen| seen.action == layer.action) {
                examples.push(layer.clone());
            }
        }
    }
    examples.sort_by(|a, b| a.action.cmp(&b.action));
    let actions: Vec<&str> = examples.iter().map(|layer| layer.action.as_str()).collect();
    assert_eq!(
        actions,
        ["draw", "fill", "line_up", "place", "scatter", "tile"]
    );
    let keys: Vec<String> = composition::placement_keys()
        .into_iter()
        .map(str::to_owned)
        .collect();
    assert_eq!(keys.len(), 32, "{keys:?}");
    let placements: Vec<(&WorkPlanLayer, &String)> = examples
        .iter()
        .flat_map(|layer| keys.iter().map(move |key| (layer, key)))
        .collect();
    let failures: Vec<String> = common::par_map(&placements, |&(layer, key)| {
        let mut failures = Vec::new();
        for language in [
            ResolvedInstructionLanguage::Ja,
            ResolvedInstructionLanguage::En,
        ] {
            let source = composed_source(
                std::slice::from_ref(layer),
                std::slice::from_ref(key),
                language,
            );
            if !work_plan_source_compiles_cleanly(&source, language) {
                failures.push(source);
            }
        }
        failures
    })
    .into_iter()
    .flatten()
    .collect();
    let compiled = 2 * placements.len();
    println!("{compiled} sentences compiled");
    assert!(
        failures.is_empty(),
        "{} of {compiled} do not compile cleanly:\n{}",
        failures.len(),
        failures.join("\n")
    );
}
