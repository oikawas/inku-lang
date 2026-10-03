//! The composition step answers exactly as the prototype it was ported from.
//!
//! The fixture holds, for every work of five readings of fifty production
//! descriptions, the work-plan layers, the reading values, the checked reading
//! and the prototype's chosen ranges and scores for seeds 1 and 2. It holds no
//! description text, quote or thesis: a stated place keeps only whether the
//! description holds its words and whether they name a position.

use std::collections::BTreeMap;

use inku_ddl::work_plan::WorkPlanLayer;
use inku_pipeline::composition::{
    self, CheckedReading, RawReading, RawRelation, RawStatedPlace, Relation, Role, Searched,
    Unsolved,
};
use serde::Deserialize;
use serde_json::Value;

/// The works of the measurements, and the works whose reading names a corner
/// (I-712, one reading of 2026-10-03).
const FIXTURES: [&str; 2] = [
    include_str!("data/composition-port-v1.json"),
    include_str!("data/composition-port-corners-v1.json"),
];

/// Works with more combinations are solved only by the full run, which is slow
/// without optimisation.
const QUICK_LIMIT: u64 = 20_000;

#[derive(Deserialize)]
struct Fixture {
    schema: String,
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    id: String,
    case: String,
    layers: Vec<WorkPlanLayer>,
    background: String,
    reading: Option<FixtureReading>,
    checked: Checked,
    solve: Solve,
}

#[derive(Deserialize)]
struct FixtureReading {
    roles: Vec<String>,
    relations: Vec<RawRelation>,
    tension: Vec<(String, Value)>,
    stated_places: Vec<(String, FixtureStated)>,
}

#[derive(Deserialize)]
struct FixtureStated {
    words: String,
    quoted: bool,
    #[serde(default)]
    place: Option<String>,
}

#[derive(Deserialize)]
struct Checked {
    roles: Vec<Role>,
    relations: Vec<Relation>,
    tension: BTreeMap<String, String>,
    fixed: BTreeMap<String, String>,
    findings: Vec<String>,
}

#[derive(Deserialize)]
struct Solve {
    #[serde(default)]
    skipped: Option<String>,
    #[serde(default)]
    combinations: Option<u64>,
    #[serde(default)]
    s1: Option<Seeded>,
    #[serde(default)]
    s2: Option<Seeded>,
}

#[derive(Deserialize)]
struct Seeded {
    regions: Vec<String>,
    total: f64,
    terms: Vec<(String, f64)>,
    best: f64,
    near_best: usize,
}

#[derive(Default)]
struct Outcome {
    cases: usize,
    checked: usize,
    solved: usize,
    skipped_as_expected: usize,
    left_for_the_full_run: usize,
    failures: Vec<String>,
}

fn checked_reading(case: &Case) -> Result<(CheckedReading, Vec<String>), String> {
    let Some(reading) = &case.reading else {
        return Ok((composition::default_reading(&case.layers), Vec::new()));
    };
    let raw = RawReading {
        roles: reading.roles.clone(),
        relations: reading.relations.clone(),
        tension: reading.tension.clone(),
        stated_places: reading
            .stated_places
            .iter()
            .map(|(key, stated)| {
                (
                    key.clone(),
                    RawStatedPlace {
                        words: Some(stated.words.clone()),
                        place: stated.place.clone(),
                    },
                )
            })
            .collect(),
    };
    let quoted: Vec<bool> = reading
        .stated_places
        .iter()
        .map(|(_, stated)| stated.quoted)
        .collect();
    let quoted = |index: usize, _: &str| quoted[index];
    composition::check(&raw, &case.layers, Some(&quoted))
        .map(|(checked, findings)| {
            (
                checked,
                findings.iter().map(|f| f.code.to_owned()).collect(),
            )
        })
        .map_err(|error| format!("check failed: {error:?}"))
}

fn compare_check(case: &Case, checked: &CheckedReading, findings: &[String]) -> Vec<String> {
    let mut differences = Vec::new();
    let expected = &case.checked;
    if checked.roles != expected.roles {
        differences.push(format!("roles {:?} != {:?}", checked.roles, expected.roles));
    }
    if checked.relations != expected.relations {
        differences.push(format!(
            "relations {:?} != {:?}",
            checked.relations, expected.relations
        ));
    }
    if checked.tension != expected.tension {
        differences.push(format!(
            "tension {:?} != {:?}",
            checked.tension, expected.tension
        ));
    }
    let fixed: BTreeMap<String, String> = checked
        .fixed
        .iter()
        .map(|(k, v)| (k.to_string(), v.clone()))
        .collect();
    if fixed != expected.fixed {
        differences.push(format!("fixed {fixed:?} != {:?}", expected.fixed));
    }
    if findings != expected.findings.as_slice() {
        differences.push(format!("findings {findings:?} != {:?}", expected.findings));
    }
    differences
}

fn compare_seed(
    case: &Case,
    checked: &CheckedReading,
    searched: &Searched,
    seed: u64,
    expected: &Seeded,
) -> Vec<String> {
    let mut differences = Vec::new();
    if searched.best != expected.best {
        differences.push(format!("best {} != {}", searched.best, expected.best));
    }
    if searched.near.len() != expected.near_best {
        differences.push(format!(
            "near-best {} != {}",
            searched.near.len(),
            expected.near_best
        ));
    }
    match composition::solve(
        &case.layers,
        checked,
        &case.background,
        searched,
        seed,
        &case.case,
    ) {
        Ok(solution) => {
            let regions: Vec<&str> = solution
                .regions
                .iter()
                .map(|i| composition::region_key(*i))
                .collect();
            if regions != expected.regions {
                differences.push(format!(
                    "s{seed} regions {regions:?} != {:?}",
                    expected.regions
                ));
            }
            if solution.score.total != expected.total {
                differences.push(format!(
                    "s{seed} total {} != {}",
                    solution.score.total, expected.total
                ));
            }
            if solution.terms != expected.terms {
                differences.push(format!(
                    "s{seed} terms {:?} != {:?}",
                    solution.terms, expected.terms
                ));
            }
        }
        Err(unsolved) => differences.push(format!("s{seed} unsolved {unsolved:?}")),
    }
    differences
}

fn fixture_cases() -> Vec<Case> {
    FIXTURES
        .iter()
        .flat_map(|text| {
            let fixture: Fixture = serde_json::from_str(text).expect("the fixture is JSON");
            assert_eq!(fixture.schema, "inku.composition-port-fixture.v1");
            fixture.cases
        })
        .collect()
}

fn run(limit: Option<u64>) -> Outcome {
    let cases = fixture_cases();
    let mut outcome = Outcome {
        cases: cases.len(),
        ..Outcome::default()
    };
    for case in &cases {
        let (checked, findings) = match checked_reading(case) {
            Ok(value) => value,
            Err(error) => {
                outcome.failures.push(format!("{}: {error}", case.id));
                continue;
            }
        };
        let mut differences = compare_check(case, &checked, &findings);
        outcome.checked += 1;
        // Larger works are searched only by the full run: an unoptimised exhaustive
        // search of every work takes minutes.
        if case.solve.skipped.is_none()
            && limit.is_some_and(|limit| case.solve.combinations.unwrap_or(0) > limit)
        {
            outcome.left_for_the_full_run += 1;
            if !differences.is_empty() {
                outcome
                    .failures
                    .push(format!("{}: {}", case.id, differences.join("; ")));
            }
            continue;
        }
        match (
            &case.solve.skipped,
            composition::search(&case.layers, &checked, &case.background),
        ) {
            (Some(reason), Err(Unsolved::Combinations(n))) if reason == "combinations" => {
                if Some(n) == case.solve.combinations {
                    outcome.skipped_as_expected += 1;
                } else {
                    differences.push(format!("combinations {n} != {:?}", case.solve.combinations));
                }
            }
            (None, Ok(searched)) => {
                if Some(searched.combinations) != case.solve.combinations {
                    differences.push(format!(
                        "combinations {} != {:?}",
                        searched.combinations, case.solve.combinations
                    ));
                }
                for (seed, expected) in [(1, &case.solve.s1), (2, &case.solve.s2)] {
                    let expected = expected.as_ref().expect("a solved case has both seeds");
                    differences.extend(compare_seed(case, &checked, &searched, seed, expected));
                }
                outcome.solved += 1;
            }
            (expected, got) => differences.push(format!(
                "solve {expected:?} but {:?}",
                got.map(|s| s.combinations)
            )),
        }
        if !differences.is_empty() {
            outcome
                .failures
                .push(format!("{}: {}", case.id, differences.join("; ")));
        }
    }
    outcome
}

fn report(outcome: &Outcome) -> String {
    format!(
        "{} cases, {} checked, {} solved, {} skipped as the prototype skipped them (too many combinations), {} left for the full run, {} differ:\n{}",
        outcome.cases,
        outcome.checked,
        outcome.solved,
        outcome.skipped_as_expected,
        outcome.left_for_the_full_run,
        outcome.failures.len(),
        outcome.failures.join("\n")
    )
}

#[test]
fn the_check_and_the_solver_answer_as_the_prototype_on_small_works() {
    let outcome = run(Some(QUICK_LIMIT));
    println!("{}", report(&outcome));
    assert!(outcome.failures.is_empty(), "{}", report(&outcome));
    assert_eq!(outcome.checked, outcome.cases, "{}", report(&outcome));
    assert!(outcome.solved >= 200, "{}", report(&outcome));
}

#[test]
#[ignore = "solves every work exhaustively; run with --release -- --ignored"]
fn the_solver_answers_as_the_prototype_on_every_work() {
    let outcome = run(None);
    println!("{}", report(&outcome));
    assert!(outcome.failures.is_empty(), "{}", report(&outcome));
    assert_eq!(outcome.checked, outcome.cases, "{}", report(&outcome));
    assert_eq!(
        outcome.solved + outcome.skipped_as_expected,
        outcome.cases,
        "{}",
        report(&outcome)
    );
}
