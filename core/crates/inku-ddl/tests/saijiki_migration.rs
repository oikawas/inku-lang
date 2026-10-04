use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage,
    SaijikiMigrationError, ScoreErrorPolicy, ScoreLoweringContext, ScoreLoweringOutcome,
    SourceSpan, compile_ddl_to_score, migrate_document_from_saijiki_v1,
    migrate_macro_definition_from_saijiki_v1,
};
use inku_score::{Color, SurfaceIntensity, SurfaceTexture};
use serde_json::json;

const JA: ResolvedInstructionLanguage = ResolvedInstructionLanguage::Ja;
const EN: ResolvedInstructionLanguage = ResolvedInstructionLanguage::En;

fn migrate(source: &str, language: ResolvedInstructionLanguage) -> String {
    let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
    migrate_document_from_saijiki_v1(&document)
        .unwrap_or_else(|error| panic!("{source}: {error:?}"))
        .source
}

#[test]
fn a_v1_document_is_rewritten_word_by_word_at_its_positions() {
    for (language, v1, current) in [
        // The v1 printer wrote an intensity right after a pale ink wash; v1 dropped it.
        (
            JA,
            "上に、細かくゆっくり波打つ赤い鉛筆の薄墨の濃い円を1個置く。",
            "上に、細かくゆるやかに波打つ赤い鉛筆の刷きの薄い円を1個置く。",
        ),
        (JA, "薄墨の薄い円を置く。", "刷きの薄い円を置く。"),
        (JA, "濃い薄墨の円を置く。", "薄い刷きの円を置く。"),
        (JA, "薄墨の円を置く。", "薄い刷きの円を置く。"),
        // Another mark's intensity stays where it is.
        (
            JA,
            "薄墨の円を置く。濃い塗りの線を引く。",
            "薄い刷きの円を置く。濃い塗りの線を引く。",
        ),
        (JA, "速く揺れる線を引く。", "小刻みに揺れる線を引く。"),
        // The aliases v1 kept from the rows consolidated on 2026-09-14.
        (
            JA,
            "中央に赤い震える点の円を置く。",
            "中心に赤い揺れる点描の円を置く。",
        ),
        (JA, "点を置く。", "点を置く。"),
        (
            EN,
            "place one red pale ink wash circle at center.",
            "place one red faint sweep circle at center.",
        ),
        (
            EN,
            "place one red dense pale ink wash circle at middle.",
            "place one red faint sweep circle at center.",
        ),
        (
            EN,
            "draw one largely swaying small red line at center.",
            "draw one broadly swaying small red line at center.",
        ),
        (
            EN,
            "Place one thin pencil line at the center. The line sways finely.",
            "Place one thin pencil line at the center. The line sways narrowly.",
        ),
        (
            EN,
            "circle. the circle undulates slowly.",
            "circle. the circle undulates loosely.",
        ),
        (
            EN,
            "place red blurring circle at middle.",
            "place red bleeding circle at center.",
        ),
        // A size stays a size.
        (
            EN,
            "scatter large red circle at center.",
            "scatter large red circle at center.",
        ),
    ] {
        assert_eq!(migrate(v1, language), current, "{v1}");
    }
}

#[test]
fn a_rewritten_word_keeps_the_authors_letter_case() {
    for (v1, current) in [
        ("Slowly", "Loosely"),
        ("SLOWLY", "LOOSELY"),
        ("Pale ink wash", "Faint sweep"),
    ] {
        assert_eq!(migrate(v1, EN), current);
    }
}

#[test]
fn a_sweep_without_a_named_mark_is_written_faint_and_reported() {
    for (language, v1, current) in [
        (JA, "薄墨", "薄い刷き"),
        (EN, "pale ink wash", "faint sweep"),
    ] {
        let document = NormalizedDdlDocument::new(v1, language, Vec::new()).unwrap();
        let migration = migrate_document_from_saijiki_v1(&document).unwrap();
        assert_eq!(migration.source, current);
        assert_eq!(
            migration.unassociated_sweeps,
            [SourceSpan {
                start_byte: 0,
                end_byte: current.len(),
            }]
        );
        assert_eq!(migration.edits.len(), 1);
        assert_eq!(migration.edits[0].original, v1);
    }
    let named = NormalizedDdlDocument::new("薄墨の円を置く。", JA, Vec::new()).unwrap();
    assert!(
        migrate_document_from_saijiki_v1(&named)
            .unwrap()
            .unassociated_sweeps
            .is_empty()
    );
}

#[test]
fn a_migrated_pale_ink_wash_draws_as_a_faint_sweep() {
    for (language, v1) in [
        (JA, "赤い薄墨の円を中心に置く。"),
        (JA, "赤い濃い薄墨の円を中心に置く。"),
        (EN, "place one red pale ink wash circle at center."),
        (EN, "place one red dense pale ink wash circle at center."),
    ] {
        let migrated = migrate(v1, language);
        let execution = compile_ddl_to_score(
            NormalizedDdlDocument::new(migrated.as_str(), language, Vec::new()).unwrap(),
            &[],
            Some(37),
            MacroExpansionLimits {
                max_invocations: 8,
                max_depth: 8,
                max_evaluation_steps: 512,
                max_nodes_per_invocation: 64,
                max_total_nodes: 128,
            },
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            ScoreErrorPolicy::Stop,
        );
        assert_eq!(
            execution.outcome(),
            ScoreLoweringOutcome::Complete,
            "{migrated}: {:?} {:?}",
            execution.upstream_diagnostics(),
            execution.downstream_diagnostics()
        );
        let instruction = &execution.score().unwrap().instructions[0];
        assert_eq!(
            instruction.surface.as_ref().map(|surface| surface.texture),
            Some(SurfaceTexture::Sweep),
            "{migrated}"
        );
        assert_eq!(
            instruction.surface_intensity,
            SurfaceIntensity::Faint,
            "{migrated}"
        );
    }
}

fn emit_definition(fields: serde_json::Value) -> serde_json::Value {
    json!({
        "schema": "inku.macro-definition.v1",
        "namespace": "Saved",
        "heading": "Mark",
        "version": "1.2.0",
        "parameters": {},
        "components": {},
        "body": [{"op": "emit", "binding": null, "fields": fields}]
    })
}

fn circle_fields() -> serde_json::Value {
    json!({
        "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
        "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
        "place": {"expr": "semantic_ref", "category": "place", "id": "middle"},
        "color": {"expr": "semantic_ref", "category": "color", "id": "red"}
    })
}

#[test]
fn a_v1_definition_moves_each_word_and_keeps_its_version() {
    let mut fields = circle_fields();
    fields["surface"] = json!({"expr": "semantic_ref", "category": "surface", "id": "wash"});
    fields["surface_intensity"] =
        json!({"expr": "semantic_ref", "category": "surface", "id": "dense"});
    fields["fluctuation_amplitude"] =
        json!({"expr": "semantic_ref", "category": "variation", "id": "large"});
    fields["fluctuation_frequency"] =
        json!({"expr": "semantic_ref", "category": "variation", "id": "quickly"});
    fields["fluctuation_quality"] =
        json!({"expr": "semantic_ref", "category": "variation", "id": "blurring"});
    let migration = migrate_macro_definition_from_saijiki_v1(&emit_definition(fields)).unwrap();
    assert!(migration.changed);
    assert_eq!(migration.identity.version(), "1.2.0");
    let mut expected = circle_fields();
    expected["place"] = json!({"expr": "semantic_ref", "category": "place", "id": "center"});
    expected["surface"] = json!({"expr": "semantic_ref", "category": "surface", "id": "sweep"});
    expected["surface_intensity"] =
        json!({"expr": "semantic_ref", "category": "handling", "id": "faint"});
    expected["fluctuation_amplitude"] =
        json!({"expr": "semantic_ref", "category": "variation", "id": "broadly"});
    expected["fluctuation_frequency"] =
        json!({"expr": "semantic_ref", "category": "variation", "id": "tightly"});
    expected["ink_spread"] =
        json!({"expr": "semantic_ref", "category": "variation", "id": "bleeding"});
    assert_eq!(migration.definition, emit_definition(expected));

    let again = migrate_macro_definition_from_saijiki_v1(&migration.definition).unwrap();
    assert!(!again.changed);
    assert_eq!(again.identity, migration.identity);
}

#[test]
fn a_surface_parameter_that_reaches_only_intensities_becomes_a_handling_parameter() {
    let definition = |component_field: &str| {
        json!({
            "schema": "inku.macro-definition.v1",
            "namespace": "Saved",
            "heading": "Shade",
            "version": "1.0.0",
            "parameters": {"tone": {"type": "semantic_ref", "category": "surface"}},
            "components": {"mark": {
                "parameters": {"inner": {"type": "semantic_ref", "category": "surface"}},
                "body": [{"op": "emit", "binding": null, "fields": {
                    "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                    "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                    component_field: {"expr": "parameter", "name": "inner"}
                }}]
            }},
            "body": [{"op": "use", "component": "mark", "arguments": {
                "inner": {"expr": "parameter", "name": "tone"}
            }}]
        })
    };
    let intensity = migrate_macro_definition_from_saijiki_v1(&definition("surface_intensity"))
        .unwrap()
        .definition;
    assert_eq!(intensity["parameters"]["tone"]["category"], "handling");
    assert_eq!(
        intensity["components"]["mark"]["parameters"]["inner"]["category"],
        "handling"
    );
    let quality = migrate_macro_definition_from_saijiki_v1(&definition("surface")).unwrap();
    assert!(!quality.changed);

    let mut both = definition("surface");
    both["components"]["mark"]["body"][0]["fields"]["surface_intensity"] =
        json!({"expr": "parameter", "name": "inner"});
    assert_eq!(
        migrate_macro_definition_from_saijiki_v1(&both).unwrap_err(),
        SaijikiMigrationError::AmbiguousSurfaceParameter {
            path: "$.parameters.tone".to_owned()
        }
    );
}

#[test]
fn a_wash_that_is_not_a_marks_own_field_is_refused() {
    let definition = json!({
        "schema": "inku.macro-definition.v1",
        "namespace": "Saved",
        "heading": "Either",
        "version": "1.0.0",
        "parameters": {},
        "components": {},
        "body": [{
            "op": "vary",
            "binding": "texture",
            "domain": "surface",
            "choices": [
                {"expr": "semantic_ref", "category": "surface", "id": "wash"},
                {"expr": "semantic_ref", "category": "surface", "id": "solid"}
            ],
            "range": null,
            "body": [{"op": "emit", "binding": null, "fields": {
                "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                "surface": {"expr": "local", "name": "texture"}
            }}]
        }]
    });
    let error = migrate_macro_definition_from_saijiki_v1(&definition).unwrap_err();
    assert_eq!(error.code(), "indirect_retired_word");
    assert_eq!(
        error,
        SaijikiMigrationError::IndirectRetiredWord {
            path: "$.body[0].choices[0]".to_owned(),
            category: "surface".to_owned(),
            id: "wash".to_owned(),
        }
    );
}
