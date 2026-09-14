use inku_ddl::{
    CompilerResourceExecutionResult, MacroDefinition, MacroExpansionLimits, MacroLock,
    NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext,
    ScoreLoweringOutcome, SemanticRelationKind, associate_semantic_document,
    compile_ddl_to_score_with_resources,
};
use inku_score::{
    Color, HardResourcePolicy, MirrorBodyRef, OperationalResourceBudget, ResolvedPaletteColor,
    ResolvedPaletteContext, ResourceBudget, ResourceDemand,
};
use serde_json::json;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 128,
    max_nodes_per_invocation: 64,
    max_total_nodes: 128,
};

#[test]
fn ordinary_mirror_is_bilingual_and_delivers_fixed_binary_refs() {
    let ja = "左端に斜めの赤い弧を置く。右端に前の形と鏡写しの青い弧を置く。";
    let en = "Place a diagonal red arc at left-edge. Place a blue arc at right-edge, mirrored with the previous shape.";
    assert_eq!(
        canonical(ja, ResolvedInstructionLanguage::Ja),
        canonical(en, ResolvedInstructionLanguage::En)
    );

    let result = execute(ja, ResolvedInstructionLanguage::Ja, &[], Vec::new());
    let score = complete_score(&result);
    assert_eq!(score.version, "0.15.0");
    assert_eq!(score.mirror_relations.len(), 1);
    let relation = &score.mirror_relations[0];
    assert_eq!(
        relation.target,
        MirrorBodyRef::Instruction {
            instruction_index: 0
        }
    );
    assert_eq!(
        relation.follower,
        MirrorBodyRef::Instruction {
            instruction_index: 1
        }
    );
    assert_eq!(relation.follower_facts.direction_degrees, None);
    assert!(!relation.follower_facts.dimensions_fixed);
}

#[test]
fn mirror_preserves_whole_macro_and_ordinary_group_boundaries() {
    let definition = pair_of_arcs();
    let macro_result = execute(
        "Mirror.Pair!. mirrored with the previous shape Mirror.Pair!",
        ResolvedInstructionLanguage::En,
        &[definition.clone()],
        vec![macro_lock(&definition)],
    );
    let macro_score = complete_score(&macro_result);
    assert_eq!(macro_score.mirror_relations.len(), 1);
    assert_eq!(
        macro_score.mirror_relations[0].target,
        MirrorBodyRef::RepetitionGroup {
            repetition_group_index: 0
        }
    );
    assert_eq!(
        macro_score.mirror_relations[0].follower,
        MirrorBodyRef::RepetitionGroup {
            repetition_group_index: 1
        }
    );
    assert!(
        macro_score.mirror_relations[0]
            .follower_facts
            .dimensions_fixed
    );

    let group_source = concat!(
        "赤い弧と青い縦の線の組を上に並べる。",
        "灰の弧と黒い縦の線の組を下に並べる、前の形と鏡写し。"
    );
    let semantic = associate_semantic_document(
        &NormalizedDdlDocument::new(group_source, ResolvedInstructionLanguage::Ja, Vec::new())
            .unwrap(),
    )
    .unwrap();
    assert!(
        semantic.ast.group_predicates.iter().any(|predicate| {
            predicate
                .relation
                .as_ref()
                .is_some_and(|relation| relation.kind == SemanticRelationKind::Mirrored)
        }),
        "predicates={:?} instruction_issues={:?} relation_issues={:?}",
        semantic.ast.group_predicates,
        semantic.instruction_association.issues,
        semantic.instruction_association.relation_issues,
    );
    let grouped = execute(
        group_source,
        ResolvedInstructionLanguage::Ja,
        &[],
        Vec::new(),
    );
    let grouped_score = complete_score(&grouped);
    assert_eq!(grouped_score.mirror_relations.len(), 1);
    assert!(matches!(
        grouped_score.mirror_relations[0].target,
        MirrorBodyRef::PlacementGroup { .. }
    ));
    assert!(matches!(
        grouped_score.mirror_relations[0].follower,
        MirrorBodyRef::PlacementGroup { .. }
    ));
}

#[test]
fn incompatible_mirror_drops_only_relation_and_keeps_later_sibling() {
    let result = execute(
        "左端に赤い円を置く。右端に前の形と鏡写しの青い線を置く。中央に緑の正方形を置く。",
        ResolvedInstructionLanguage::Ja,
        &[],
        Vec::new(),
    );
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    let score = result.score().expect("independent drawings survive");
    assert_eq!(score.instructions.len(), 3);
    assert!(score.mirror_relations.is_empty());
    assert_eq!(result.downstream_diagnostics().len(), 1);
}

fn execute(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    locks: Vec<MacroLock>,
) -> CompilerResourceExecutionResult {
    compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, language, locks).unwrap(),
        definitions,
        Some(37),
        LIMITS,
        ScoreLoweringContext::resolve_with_palette(
            "wide",
            Color::White,
            ResolvedPaletteContext::new(
                ResolvedPaletteColor::new(Color::White, [255; 3], 1.0),
                ResolvedPaletteColor::new(Color::Black, [0; 3], 0.0),
                ResolvedPaletteColor::new(Color::White, [255; 3], 1.0),
            ),
        )
        .unwrap(),
        None,
        ScoreErrorPolicy::OmitAndContinue,
        HardResourcePolicy {
            identity: "mirror-relation-test.v1".into(),
            budget: budget(),
        },
        OperationalResourceBudget(budget()),
    )
}

fn complete_score(result: &CompilerResourceExecutionResult) -> &inku_score::Score {
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::Complete,
        "upstream={:?} downstream={:?} failure={:?}",
        result.upstream_diagnostics(),
        result.downstream_diagnostics(),
        result.failure()
    );
    result.score().expect("complete result has Score")
}

fn canonical(source: &str, language: ResolvedInstructionLanguage) -> Vec<u8> {
    let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
    let result = associate_semantic_document(&document).unwrap();
    result.canonical_bytes.unwrap_or_else(|| {
        panic!(
            "{source}: {:?} {:?}",
            result.instruction_association.association.issues,
            result.instruction_association.relation_issues
        )
    })
}

fn pair_of_arcs() -> MacroDefinition {
    MacroDefinition::from_json(
        &json!({
            "schema": "inku.macro-definition.v1",
            "namespace": "Mirror",
            "heading": "Pair",
            "version": "1.0.0",
            "parameters": {},
            "components": {},
            "body": [
                {"op":"emit", "binding":null, "fields":{
                    "shape":{"expr":"semantic_ref","category":"shape","id":"arc"},
                    "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
                    "color":{"expr":"semantic_ref","category":"color","id":"red"},
                    "position_x":{"expr":"exact_decimal","value":"0.35"},
                    "position_y":{"expr":"exact_decimal","value":"0.42"},
                    "count":{"expr":"integer","value":1}
                }},
                {"op":"emit", "binding":null, "fields":{
                    "shape":{"expr":"semantic_ref","category":"shape","id":"arc"},
                    "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
                    "color":{"expr":"semantic_ref","category":"color","id":"blue"},
                    "position_x":{"expr":"exact_decimal","value":"0.65"},
                    "position_y":{"expr":"exact_decimal","value":"0.58"},
                    "count":{"expr":"integer","value":1}
                }}
            ]
        })
        .to_string(),
    )
    .unwrap()
}

fn macro_lock(definition: &MacroDefinition) -> MacroLock {
    let identity = definition.identity().unwrap();
    MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap()
}

fn budget() -> ResourceBudget {
    ResourceBudget {
        maximum: ResourceDemand {
            logical_objects: 400,
            primitive_marks: 400,
            object_templates: 64,
            maximum_per_template_primitive_marks: 240,
            maximum_resolved_count: 2000,
            template_nodes: 512,
            anchor_instances: 400,
            transform_instances: 400,
            placement_instances: 400,
            fill_instances: 400,
        },
    }
}
