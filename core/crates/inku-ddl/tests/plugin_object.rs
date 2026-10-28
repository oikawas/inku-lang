//! Test-only object words: their body coordinates belong to one local box.
use inku_ddl::{
    MacroDefinition, MacroExpansionLimits, MacroLock, NormalizedDdlDocument,
    ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext, compile_ddl_to_score,
};
use inku_score::Color;
use serde_json::{Value, json};

fn arc(binding: &str, x: &str, rotation: &str) -> Value {
    let emit = json!({"op":"emit","binding":binding,"fields":{
        "shape":{"expr":"semantic_ref","category":"shape","id":"arc"},
        "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
        "color":{"expr":"semantic_ref","category":"color","id":"green"},
        "position_x":{"expr":"exact_decimal","value":x},
        "position_y":{"expr":"exact_decimal","value":"0.5"},
        "chord":{"expr":"exact_decimal","value":"0.6"},
        "sagitta":{"expr":"exact_decimal","value":"0.2"}
    }});
    if rotation == "180" {
        json!({"op":"transform","transform":{"rotate_degrees":{"expr":"number","value":180.0}},"body":[emit]})
    } else {
        emit
    }
}

fn word(id: &str, ja: &str, en: &str, aspect: &str, body: Value) -> MacroDefinition {
    let definition = MacroDefinition::from_json(
        &json!({
            "schema":"inku.macro-definition.v2", "namespace":"TestObject", "id":id,
            "names":{"ja":[ja],"en":[en]}, "kind":"object", "aspect":aspect,
            "counter":"flat", "version":"1.0.0", "parameters":{}, "components":{}, "body":body
        })
        .to_string(),
    )
    .unwrap();
    assert!(
        definition.validate().is_valid(),
        "{:?}",
        definition.validate().diagnostics()
    );
    definition
}

fn lock(definition: &MacroDefinition) -> MacroLock {
    let identity = definition.identity().unwrap();
    MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap()
}

#[test]
#[ignore = "object placement and rendering are not connected yet"]
fn object_word_draws_instead_of_being_rejected() {
    let leaf = word(
        "Leaf",
        "葉",
        "leaf",
        "1:1",
        json!([arc("upper", "0.5", "0"), arc("lower", "0.5", "180")]),
    );
    let boat = word(
        "Boat",
        "舟",
        "boat",
        "2:1",
        json!([arc("hull", "0.5", "0")]),
    );
    let definitions = [leaf, boat];
    let locks = definitions.iter().map(lock).collect::<Vec<_>>();
    for (source, language) in [
        ("上に｛葉｝を8枚散らす。", ResolvedInstructionLanguage::Ja),
        (
            "Scatter 8 {leaf} at the top.",
            ResolvedInstructionLanguage::En,
        ),
        (
            "中心に大きい｛舟｝を置く。",
            ResolvedInstructionLanguage::Ja,
        ),
    ] {
        let result = compile_ddl_to_score(
            NormalizedDdlDocument::new(source, language, locks.clone()).unwrap(),
            &definitions,
            Some(37),
            MacroExpansionLimits {
                max_invocations: 64,
                max_depth: 16,
                max_evaluation_steps: 8192,
                max_nodes_per_invocation: 128,
                max_total_nodes: 128,
            },
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            ScoreErrorPolicy::OmitAndContinue,
        );
        assert!(
            result
                .score()
                .is_some_and(|score| !score.instructions.is_empty()),
            "{source}: {:?} {:?}",
            result.upstream_diagnostics(),
            result.downstream_diagnostics()
        );
        assert!(
            result.upstream_diagnostics().is_empty(),
            "{source}: {:?}",
            result.upstream_diagnostics()
        );
    }
}
