//! Saijiki v3 → v4 document migration (2026-11-17, V1d): each word is rewritten by its
//! meaning at its own position, and a word v4 moves to a near word is reported.

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage,
    SaijikiMigrationError, ScoreErrorPolicy, ScoreLoweringContext, ScoreLoweringOutcome,
    compile_ddl_to_score, migrate_document_from_saijiki_v3,
};
use inku_score::Color;

const JA: ResolvedInstructionLanguage = ResolvedInstructionLanguage::Ja;
const EN: ResolvedInstructionLanguage = ResolvedInstructionLanguage::En;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 64,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

fn migrate(
    source: &str,
    language: ResolvedInstructionLanguage,
) -> Result<inku_ddl::SaijikiDocumentMigration, SaijikiMigrationError> {
    let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
    migrate_document_from_saijiki_v3(&document)
}

fn compiles_completely(source: &str, language: ResolvedInstructionLanguage) -> bool {
    let result = compile_ddl_to_score(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        Some(1),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
    );
    let complete = result.outcome() == ScoreLoweringOutcome::Complete;
    if !complete {
        eprintln!(
            "{source}: {:?} {:?}",
            result.outcome(),
            result
                .downstream_diagnostics()
                .iter()
                .map(|diagnostic| &diagnostic.reason)
                .collect::<Vec<_>>()
        );
    }
    complete
}

// Concrete failure: a v3 word stays as v3 wrote it, so the migrated document does not read
// in v4, or reads as another word.
#[test]
fn a_v3_document_is_rewritten_word_by_word_and_reads_cleanly_in_v4() {
    for (language, v3, v4, near) in [
        (
            JA,
            "中心に、黒のコンピュータの線を1本引く。",
            "中心に、黒のデジタルの線を1本引く。",
            0,
        ),
        (
            JA,
            "中心に、赤のペンのアクアチントの円を1個置く。メゾチント。",
            "中心に、赤のペンのメゾチントの円を1個置く。メゾチント。",
            0,
        ),
        (
            JA,
            "中心に、黒のペンの細かく揺れる線を1本引く。",
            "中心に、黒のペンの小さく揺れる線を1本引く。",
            0,
        ),
        (
            JA,
            "中心に、黒のペンの一点鎖線の線を1本引く。",
            "中心に、黒のペンの破線の線を1本引く。",
            1,
        ),
        (
            JA,
            "中心に、とても小さな黒の円を1個置く。上に、小さめの黒の円を1個置く。下に、巨大な黒の円を1個置く。",
            "中心に、ごく小さな黒の円を1個置く。上に、小さな黒の円を1個置く。下に、ごく大きな黒の円を1個置く。",
            2,
        ),
        (
            JA,
            "中心に、黒のペンの上弦の弧を1本引く。",
            "中心に、回転90度の黒のペンの半円の弧を1本引く。",
            0,
        ),
        (
            EN,
            "draw one black pen temperate line at the center. draw one black computer line at the top.",
            "draw one black pen moderate line at the center. draw one black digital line at the top.",
            0,
        ),
        (
            EN,
            "draw one black pen extra-fine dash-dot line at the center.",
            "draw one black pen very thin dashed line at the center.",
            1,
        ),
        (
            EN,
            "place one huge black circle at the center. place one slightly small black circle at the top.",
            "place one very large black circle at the center. place one small black circle at the top.",
            2,
        ),
        (
            EN,
            "draw one black pen waning arc at the center.",
            "draw one black pen semicircle arc rotated 270 degrees at the center.",
            0,
        ),
    ] {
        let migration = migrate(v3, language).unwrap_or_else(|error| panic!("{v3}: {error:?}"));
        assert_eq!(migration.source, v4, "{v3}");
        assert_eq!(migration.approximated_words.len(), near, "{v3}");
        for span in &migration.approximated_words {
            assert!(span.end_byte <= migration.source.len(), "{v3}");
        }
        assert!(compiles_completely(&migration.source, language), "{v4}");
    }
}

#[test]
fn a_waxing_arc_that_also_turns_is_left_for_the_author() {
    let error = migrate("中心に、黒のペンの右上がりの上弦の弧を1本引く。", JA).unwrap_err();
    assert_eq!(error.code(), "unmigratable_arc_turn");
}

fn definition(fields: serde_json::Value) -> serde_json::Value {
    let mut emit = serde_json::json!({
        "shape": {"expr": "semantic_ref", "category": "shape", "id": "line"},
        "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
    });
    emit.as_object_mut()
        .unwrap()
        .extend(fields.as_object().unwrap().clone());
    serde_json::json!({
        "schema": "inku.macro-definition.v1", "namespace": "Saved", "heading": "Mark",
        "version": "1.0.0", "parameters": {}, "components": {},
        "body": [{"op": "emit", "binding": null, "fields": emit}],
    })
}

// Concrete failure: a saved definition keeps a v3 value v4 moved to a near word, or loses
// the turn of a 上弦 arc without a word.
#[test]
fn a_v3_definition_moves_the_dash_dot_and_the_dropped_sizes_and_refuses_a_waxing_arc() {
    let migrated =
        inku_ddl::migrate_macro_definition_from_saijiki_v3(&definition(serde_json::json!({
            "continuity": {"expr": "semantic_ref", "category": "continuity", "id": "dash_dot"},
        })))
        .unwrap();
    assert!(migrated.changed);
    assert_eq!(
        migrated.definition["body"][0]["fields"]["continuity"]["id"],
        "dashed"
    );
    let error =
        inku_ddl::migrate_macro_definition_from_saijiki_v3(&definition(serde_json::json!({
            "proportion_arc_form": {"expr": "semantic_ref", "category": "ratio", "id": "waxing"},
        })))
        .unwrap_err();
    assert_eq!(error.code(), "indirect_retired_word");
    let unchanged =
        inku_ddl::migrate_macro_definition_from_saijiki_v3(&definition(serde_json::json!({
            "ink_spread": {"expr": "semantic_ref", "category": "variation", "id": "bleeding"},
        })))
        .unwrap();
    assert!(!unchanged.changed);
}
