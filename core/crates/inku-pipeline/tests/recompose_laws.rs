//! "Change the layout" on a work the laws stage placed (the author's decisions
//! of 2026-10-20): the record of the layers the laws placed keeps them where
//! they are drawn, and the other layers are placed again around them. The
//! works are two the 5173 laws stage made with gpt-6-luna (stage B-5, ja-08
//! and ja-02), with the record the stage keeps.

use inku_ddl::{MacroExpansionLimits, ResolvedInstructionLanguage};
use inku_pipeline::laws_record::{LAWS_LAYERS_SCHEMA_ID, LawsLayerRecord};
use inku_pipeline::recompose::{RecomposeMode, Recomposition, recompose_with_laws};
use serde_json::json;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 64,
    max_depth: 16,
    max_evaluation_steps: 8_192,
    max_nodes_per_invocation: 128,
    max_total_nodes: 128,
};

/// B1 put the ellipse on the golden section's point; the dots and the arcs
/// keep the composition's ranges.
const ONE_LAWS_LAYER: &str = "背景を白で埋める。\n画面の横0.618034、縦0.618034の位置に、灰の細い細筆の程よい空の縦長の小さな楕円を1個置く。\n中央の縦（横1/3〜2/3、縦0〜1）に、半径0.001769の紫の細筆の薄い点を24個散らす。\n中心（横1/3〜2/3、縦1/3〜2/3）に、細かくゆるやかに波打つ黄の細筆の薄い空の小さな弧を5個引く。\n";
const ELLIPSE: &str =
    "画面の横0.618034、縦0.618034の位置に、灰の細い細筆の程よい空の縦長の小さな楕円を1個置く。";

/// B1 drew both lines on the golden section's lines: nothing else is there.
const ONLY_LAWS_LAYERS: &str = "画面の横0.522、縦0.381966から横0.882、縦0.381966まで、細かく波打つ緑の太い細筆の実線の程よい刷きの線を1個引く。\n画面の横0.498034、縦0.618034から横0.738034、縦0.618034まで、灰の細い細筆の実線の薄い刷きの線を1個引く。\n";

fn record(sentences: &[&str]) -> LawsLayerRecord {
    serde_json::from_value(json!({
        "schema": LAWS_LAYERS_SCHEMA_ID,
        "layers": sentences
            .iter()
            .map(|sentence| json!({"sentences": [sentence], "kind": "laws", "laws": ["B1"]}))
            .collect::<Vec<_>>(),
    }))
    .expect("a laws layers record")
}

fn recomposed(source: &str, mode: RecomposeMode, laws: Option<&LawsLayerRecord>) -> Recomposition {
    recompose_with_laws(
        source,
        ResolvedInstructionLanguage::Ja,
        &[],
        LIMITS,
        mode,
        1,
        "laws-test",
        laws,
    )
}

#[test]
fn a_recorded_laws_layer_stays_and_the_others_move() {
    let laws = record(&[ELLIPSE]);
    for mode in [RecomposeMode::Principled, RecomposeMode::Chance] {
        let Recomposition::Recomposed { source, moves, .. } =
            recomposed(ONE_LAWS_LAYER, mode, Some(&laws))
        else {
            panic!("{mode:?}: the work recomposes around the laws layer");
        };
        assert!(
            source.contains(ELLIPSE),
            "{mode:?}: the laws sentence stays as written"
        );
        assert!(!moves.is_empty(), "{mode:?}");
        // The moves are the dots' and the arcs' (layers 1 and 2), never the ellipse's.
        assert!(
            moves.iter().all(|range| range.layer != 0),
            "{mode:?}: {moves:?}"
        );
    }
}

#[test]
fn without_a_record_a_laws_work_stays_as_it_is() {
    assert_eq!(
        recomposed(ONE_LAWS_LAYER, RecomposeMode::Principled, None),
        Recomposition::Unchanged {
            reason: "unsupported_sentence"
        }
    );
}

#[test]
fn a_sentence_the_author_changed_is_no_longer_the_laws() {
    // The author made the ellipse large: the record no longer matches it, and a
    // numeric point the record does not keep is not read, as before.
    let changed = ONE_LAWS_LAYER.replace("縦長の小さな楕円", "縦長の大きな楕円");
    assert_eq!(
        recomposed(
            &changed,
            RecomposeMode::Principled,
            Some(&record(&[ELLIPSE]))
        ),
        Recomposition::Unchanged {
            reason: "unsupported_sentence"
        }
    );
}

#[test]
fn a_work_the_laws_placed_whole_has_nothing_to_move() {
    let sentences: Vec<&str> = ONLY_LAWS_LAYERS.lines().collect();
    assert_eq!(
        recomposed(
            ONLY_LAWS_LAYERS,
            RecomposeMode::Principled,
            Some(&record(&sentences))
        ),
        Recomposition::Unchanged {
            reason: "laws_placed"
        }
    );
}

#[test]
fn a_record_of_another_schema_is_refused() {
    let wrong = json!({"schema": "inku.laws-layers.v0", "layers": []});
    assert!(serde_json::from_value::<LawsLayerRecord>(wrong).is_err());
    let empty_sentence = json!({
        "schema": LAWS_LAYERS_SCHEMA_ID,
        "layers": [{"sentences": [" "], "kind": "laws"}],
    });
    assert!(serde_json::from_value::<LawsLayerRecord>(empty_sentence).is_err());
}
