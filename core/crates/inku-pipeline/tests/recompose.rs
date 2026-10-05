//! Another composition read from the visible instructions alone (draw-system05,
//! the author's decisions of 2026-10-04).
//!
//! On the composition acceptance works the instructions give back the layers the
//! composition reads, and both modes give the prototype's answers
//! (`tools/recompose_fixture.py`, seed 1, the case as the work). Only the numeric
//! ranges change, whoever wrote them; a stated place and a corner stay, and a work
//! the instructions cannot recompose stays as it is.

mod common;

use std::collections::BTreeMap;

use inku_ddl::{MacroDefinition, MacroExpansionLimits, ResolvedInstructionLanguage};
use inku_pipeline::recompose::{RecomposeMode, Recomposition, composition_layers, recompose};
use serde_json::Value;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 64,
    max_depth: 16,
    max_evaluation_steps: 8_192,
    max_nodes_per_invocation: 128,
    max_total_nodes: 128,
};

/// The bundled Nature words: three works draw a plugin word beside their layers,
/// and a host recomposes with the definitions it draws with.
fn definitions() -> Vec<MacroDefinition> {
    let package: Value =
        serde_json::from_str(include_str!("../../inku-ddl/assets/nature-leaves-v1.json"))
            .expect("the Nature package is JSON");
    package["entries"]
        .as_array()
        .expect("package entries")
        .iter()
        .map(|entry| {
            MacroDefinition::from_json(&entry["definition"].to_string())
                .expect("a bundled definition")
        })
        .collect()
}

fn fixture() -> Value {
    serde_json::from_str(include_str!("data/recompose-v1.json")).expect("the fixture is JSON")
}

fn language(case: &Value) -> ResolvedInstructionLanguage {
    match case["lang"].as_str() {
        Some("ja") => ResolvedInstructionLanguage::Ja,
        _ => ResolvedInstructionLanguage::En,
    }
}

fn text<'a>(value: &'a Value, key: &str) -> &'a str {
    value[key]
        .as_str()
        .unwrap_or_else(|| panic!("{key} is text"))
}

#[test]
fn the_instructions_give_back_the_layers_the_composition_reads() {
    let data = fixture();
    let cases = data["cases"].as_array().expect("cases");
    assert_eq!(cases.len(), 49);
    let definitions = definitions();
    common::par_map(cases, |case| {
        let id = text(case, "id");
        let (layers, background) =
            composition_layers(text(case, "source"), language(case), &definitions, LIMITS)
                .unwrap_or_else(|reason| panic!("{id}: {reason}"));
        assert_eq!(background, text(case, "background"), "{id}");
        let expected = case["layers"].as_array().expect("layers");
        assert_eq!(layers.len(), expected.len(), "{id}");
        for (index, (layer, want)) in layers.iter().zip(expected).enumerate() {
            assert_eq!(layer.shape, text(want, "shape"), "{id} layer {index}");
            assert_eq!(
                layer.proportion.as_deref(),
                want["proportion"].as_str(),
                "{id} layer {index}"
            );
            assert_eq!(layer.action, text(want, "action"), "{id} layer {index}");
            assert_eq!(
                u64::from(layer.count),
                want["count"].as_u64().expect("count"),
                "{id} layer {index}"
            );
            let attributes: BTreeMap<&str, &str> = layer
                .attributes
                .iter()
                .map(|(slot, value)| (slot.field(), value.as_str()))
                .collect();
            let wanted: BTreeMap<&str, &str> = want["attributes"]
                .as_object()
                .expect("attributes")
                .iter()
                .map(|(key, value)| (key.as_str(), value.as_str().expect("a word")))
                .collect();
            assert_eq!(attributes, wanted, "{id} layer {index}");
        }
    });
}

fn check(case: &Value, definitions: &[MacroDefinition], mode: RecomposeMode, key: &str) {
    let id = text(case, "id");
    let want = &case[key];
    let got = recompose(
        text(case, "source"),
        language(case),
        definitions,
        LIMITS,
        mode,
        1,
        id,
    );
    match (text(want, "outcome"), got) {
        (
            "recomposed",
            Recomposition::Recomposed {
                source,
                moves,
                answer,
            },
        ) => {
            assert_eq!(answer, text(want, "answer"), "{id} {key}");
            assert_eq!(source, text(want, "source"), "{id} {key}");
            let got: Vec<(usize, Option<String>, String)> = moves
                .iter()
                .map(|step| (step.layer, step.from_key.clone(), step.to_key.clone()))
                .collect();
            let wanted: Vec<(usize, Option<String>, String)> = want["moves"]
                .as_array()
                .expect("moves")
                .iter()
                .map(|step| {
                    (
                        usize::try_from(step["layer"].as_u64().expect("layer")).expect("index"),
                        step["from_key"].as_str().map(str::to_owned),
                        text(step, "to_key").to_owned(),
                    )
                })
                .collect();
            assert_eq!(got, wanted, "{id} {key}");
        }
        ("unchanged", Recomposition::Unchanged { reason }) => {
            assert_eq!(reason, text(want, "reason"), "{id} {key}");
        }
        (expected, other) => panic!("{id} {key}: expected {expected}, got {other:?}"),
    }
}

#[test]
fn a_principled_recomposition_gives_the_prototypes_other_answer() {
    let definitions = definitions();
    common::par_map(fixture()["cases"].as_array().expect("cases"), |case| {
        check(case, &definitions, RecomposeMode::Principled, "principled");
    });
}

#[test]
fn a_chance_recomposition_gives_the_prototypes_chance_ranges() {
    let definitions = definitions();
    common::par_map(fixture()["cases"].as_array().expect("cases"), |case| {
        check(case, &definitions, RecomposeMode::Chance, "chance");
    });
}

/// A line without its range: a Japanese range opens the line and ends at its
/// closing parenthesis; an English range follows ` at ` and ends the sentence.
fn without_range(line: &str, language: ResolvedInstructionLanguage) -> String {
    match language {
        ResolvedInstructionLanguage::Ja => line.find('）').map_or(line.to_owned(), |at| {
            line[at + '）'.len_utf8()..].to_owned()
        }),
        ResolvedInstructionLanguage::En => match (line.rfind(" at the "), line.rfind(')')) {
            (Some(start), Some(end)) if start < end => {
                format!("{}{}", &line[..start], &line[end + 1..])
            }
            _ => line.to_owned(),
        },
    }
}

#[test]
fn only_the_ranges_change() {
    let definitions = definitions();
    let recomposed: usize =
        common::par_map(fixture()["cases"].as_array().expect("cases"), |case| {
            let id = text(case, "id");
            let source = text(case, "source");
            let language = language(case);
            let mut recomposed = 0;
            for mode in [RecomposeMode::Principled, RecomposeMode::Chance] {
                let Recomposition::Recomposed {
                    source: after,
                    moves,
                    ..
                } = recompose(source, language, &definitions, LIMITS, mode, 1, id)
                else {
                    continue;
                };
                recomposed += 1;
                let (before, after): (Vec<&str>, Vec<&str>) =
                    (source.lines().collect(), after.lines().collect());
                assert_eq!(before.len(), after.len(), "{id}");
                for (old, new) in before.iter().zip(&after) {
                    // Outside the range nothing changes.
                    assert_eq!(
                        without_range(old, language),
                        without_range(new, language),
                        "{id}"
                    );
                }
                for step in &moves {
                    assert!(source.contains(&step.from), "{id}: {}", step.from);
                    assert!(
                        after.iter().any(|line| line.contains(&step.to)),
                        "{id}: {}",
                        step.to
                    );
                }
            }
            recomposed
        })
        .into_iter()
        .sum();
    assert!(recomposed >= 80, "{recomposed} recompositions");
}

#[test]
fn a_work_the_instructions_cannot_recompose_stays_as_it_is() {
    let unchanged = |source: &str| {
        recompose(
            source,
            ResolvedInstructionLanguage::Ja,
            &[],
            LIMITS,
            RecomposeMode::Principled,
            1,
            "w",
        )
    };
    // A place written as a word is a place the description states: nothing moves.
    assert_eq!(
        unchanged("上に、細かくゆるやかに波打つ赤い鉛筆の刷きの薄い円を1個置く。"),
        Recomposition::Unchanged {
            reason: "nothing_to_move"
        }
    );
    let composed =
        "左上（横0〜1/3、縦0〜1/3）に、細かくゆるやかに波打つ赤い鉛筆の刷きの薄い円を1個置く。";
    // A sentence a plan does not write: a relation to the previous shape.
    assert_eq!(
        unchanged(&format!(
            "{composed}\n前の形に触れない\n青い四角を中心に置く。"
        )),
        Recomposition::Unchanged {
            reason: "unsupported_sentence"
        }
    );
}

const CIRCLE: &str = "細かくゆるやかに波打つ赤い鉛筆の刷きの薄い円を1個置く。";

fn by_chance(source: &str, seed: u64) -> Recomposition {
    recompose(
        source,
        ResolvedInstructionLanguage::Ja,
        &[],
        LIMITS,
        RecomposeMode::Chance,
        seed,
        "w",
    )
}

/// "Change the layout" asks for the places to change: a range the author wrote
/// moves too, even when its words say another place than its numbers (the
/// author's decision of 2026-10-05). The new range writes its words and numbers
/// together.
#[test]
fn every_numeric_range_moves_whoever_wrote_it() {
    let source = format!("右下（横0.9〜1、縦0.1〜0.2）に、{CIRCLE}");
    let Recomposition::Recomposed {
        source: after,
        moves,
        ..
    } = by_chance(&source, 1)
    else {
        panic!("the author's range moves");
    };
    assert_eq!(moves.len(), 1, "{moves:?}");
    assert_eq!(moves[0].from, "右下（横0.9〜1、縦0.1〜0.2）");
    assert_eq!(moves[0].from_key, None);
    assert_eq!(after, format!("{}に、{CIRCLE}", moves[0].to));
}

/// A corner keeps its corner and a stated place keeps its place; the range
/// beside them moves.
#[test]
fn a_corner_and_a_stated_place_stay() {
    let source = format!(
        "右上の隅（横4/5〜1、縦0〜1/5）に、{CIRCLE}\n下に、{CIRCLE}\n左上（横0〜1/3、縦0〜1/3）に、{CIRCLE}"
    );
    let moved = (1..=8)
        .find_map(|seed| match by_chance(&source, seed) {
            Recomposition::Recomposed {
                source: after,
                moves,
                ..
            } => Some((after, moves)),
            Recomposition::Unchanged { .. } => None,
        })
        .expect("the third range moves for some seed");
    let (after, moves) = moved;
    assert!(moves.iter().all(|step| step.layer == 2), "{moves:?}");
    let lines: Vec<&str> = after.lines().collect();
    assert_eq!(
        lines[0],
        format!("右上の隅（横4/5〜1、縦0〜1/5）に、{CIRCLE}")
    );
    assert_eq!(lines[1], format!("下に、{CIRCLE}"));
}

/// A work printed with the mark (Build 1155 to 1163) still moves; the mark goes
/// with the range it stood before.
#[test]
fn an_old_mark_goes_with_its_range() {
    let source = format!("［構図］左上（横0〜1/3、縦0〜1/3）に、{CIRCLE}");
    let (after, moves) = (1..=8)
        .find_map(|seed| match by_chance(&source, seed) {
            Recomposition::Recomposed {
                source: after,
                moves,
                ..
            } => Some((after, moves)),
            Recomposition::Unchanged { .. } => None,
        })
        .expect("the range moves for some seed");
    assert_eq!(moves[0].from, "左上（横0〜1/3、縦0〜1/3）");
    assert_eq!(moves[0].from_key.as_deref(), Some("cell-00"));
    assert!(!after.contains("［構図］"), "{after}");
    assert_eq!(after, format!("{}に、{CIRCLE}", moves[0].to));
}

/// The range the author typed with a hyphen (`横1/3-2/3`, 2026-10-05) compiles
/// and is the bottom center the composition writes; another composition moves it.
#[test]
fn a_range_joined_with_a_hyphen_moves() {
    let source = format!("下中央（横1/3-2/3、縦2/3〜1）に、{CIRCLE}");
    let moves = (1..=8)
        .find_map(|seed| match by_chance(&source, seed) {
            Recomposition::Recomposed { moves, .. } => Some(moves),
            Recomposition::Unchanged { .. } => None,
        })
        .expect("the hyphenated range compiles and moves for some seed");
    assert_eq!(moves[0].from, "下中央（横1/3-2/3、縦2/3〜1）");
    assert_eq!(moves[0].from_key.as_deref(), Some("cell-12"));
}
