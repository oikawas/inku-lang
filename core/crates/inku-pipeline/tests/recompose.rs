//! Another composition read from the visible instructions alone (draw-system05,
//! the author's decisions of 2026-10-04).
//!
//! On the composition acceptance works the instructions give back the layers the
//! composition reads, and both modes give the prototype's answers
//! (`tools/recompose_fixture.py`, seed 1, the case as the work). Only the marked
//! ranges change, and a work the instructions cannot recompose stays as it is.

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
const MARKS: [&str; 2] = ["［構図］", "[composition]"];

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
    for case in cases {
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
    }
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
    for case in fixture()["cases"].as_array().expect("cases") {
        check(case, &definitions, RecomposeMode::Principled, "principled");
    }
}

#[test]
fn a_chance_recomposition_gives_the_prototypes_chance_ranges() {
    let definitions = definitions();
    for case in fixture()["cases"].as_array().expect("cases") {
        check(case, &definitions, RecomposeMode::Chance, "chance");
    }
}

#[test]
fn only_the_marked_ranges_change() {
    let mut recomposed = 0;
    let definitions = definitions();
    for case in fixture()["cases"].as_array().expect("cases") {
        let id = text(case, "id");
        let source = text(case, "source");
        for mode in [RecomposeMode::Principled, RecomposeMode::Chance] {
            let Recomposition::Recomposed { source: after, .. } =
                recompose(source, language(case), &definitions, LIMITS, mode, 1, id)
            else {
                continue;
            };
            recomposed += 1;
            let (before, after): (Vec<&str>, Vec<&str>) =
                (source.lines().collect(), after.lines().collect());
            assert_eq!(before.len(), after.len(), "{id}");
            for (old, new) in before.iter().zip(&after) {
                let cut = |line: &str| {
                    MARKS
                        .iter()
                        .find_map(|mark| line.find(mark))
                        .map_or(line.len(), |at| at)
                };
                // Before the mark nothing changes; after it, only the range.
                assert_eq!(&old[..cut(old)], &new[..cut(new)], "{id}");
                let tail = |line: &str| {
                    let after_range = line.rfind(['）', ')']).map_or(line.len(), |at| at);
                    line[after_range..]
                        .trim_start_matches(['）', ')'])
                        .to_owned()
                };
                assert_eq!(tail(old), tail(new), "{id}");
            }
        }
    }
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
    // The author's own instructions: no range carries the composition mark.
    assert_eq!(
        unchanged("上に、細かくゆるやかに波打つ赤い鉛筆の刷きの薄い円を1個置く。"),
        Recomposition::Unchanged {
            reason: "nothing_to_move"
        }
    );
    let composed = "［構図］左上（横0〜1/3、縦0〜1/3）に、細かくゆるやかに波打つ赤い鉛筆の刷きの薄い円を1個置く。";
    // A range the author wrote: the mark is gone, so the range is the author's own.
    assert_eq!(
        unchanged(&format!(
            "{composed}\n右下（横2/3〜1、縦2/3〜1）に、細かくゆるやかに波打つ赤い鉛筆の刷きの薄い円を1個置く。"
        )),
        Recomposition::Unchanged {
            reason: "author_range"
        }
    );
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
