use inku_ddl::{
    CompilerResourceExecutionResult, MacroExpansionLimits, NormalizedDdlDocument,
    PlanResourceFailure, ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext,
    ScoreLoweringOutcome, SemanticSequenceIssueKind, associate_semantic_document,
    compile_ddl_to_score_with_resources,
};
use inku_score::{
    Color, CountOrigin, HardResourcePolicy, OperationalResourceBudget, Primitive, ResourceBudget,
    ResourceDemand, ResourceDimension,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 128,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

#[test]
fn ordinary_bilingual_sequences_preserve_order_duplicates_and_total_count() {
    for (language, source, colors, count) in [
        (
            ResolvedInstructionLanguage::Ja,
            "赤と灰を交互にして、円を五つ並べる。",
            vec![Color::Red, Color::Gray],
            5,
        ),
        (
            ResolvedInstructionLanguage::En,
            "line up five circles, alternating red and gray.",
            vec![Color::Red, Color::Gray],
            5,
        ),
        (
            ResolvedInstructionLanguage::Ja,
            "赤・赤・青の順に繰り返して、円を八つ並べる。",
            vec![Color::Red, Color::Red, Color::Blue],
            8,
        ),
        (
            ResolvedInstructionLanguage::En,
            "line up eight circles, repeating red, red, and blue in order.",
            vec![Color::Red, Color::Red, Color::Blue],
            8,
        ),
    ] {
        let result = execute(source, language);
        assert_eq!(
            result.outcome(),
            ScoreLoweringOutcome::Complete,
            "{source}: {:?} {:?}",
            result.upstream_diagnostics(),
            result.downstream_diagnostics()
        );
        let instruction = &result.score().unwrap().instructions[0];
        let arrangement = instruction
            .arrangement
            .as_ref()
            .expect("finite arrangement");
        assert_eq!(arrangement.count, count, "{source}");
        assert_eq!(
            arrangement.resolved.as_ref().unwrap().count_origin,
            CountOrigin::Explicit,
            "{source}"
        );
        assert_eq!(arrangement.color_cycle, colors, "{source}");
        assert_eq!(instruction.color, colors[0], "{source}");
    }

    let alternating_ja = canonical(
        "赤と灰を交互にして、円を五つ並べる。",
        ResolvedInstructionLanguage::Ja,
    );
    let alternating_en = canonical(
        "line up five circles, alternating red and gray.",
        ResolvedInstructionLanguage::En,
    );
    assert_eq!(alternating_ja, alternating_en);
    let in_order = canonical(
        "line up five circles, repeating red and gray in order.",
        ResolvedInstructionLanguage::En,
    );
    assert_ne!(alternating_en, in_order);
}

#[test]
fn sequence_count_omission_and_count_one_keep_existing_cardinality_rules() {
    let omitted = execute(
        "line up circles, alternating red and gray.",
        ResolvedInstructionLanguage::En,
    );
    let arrangement = omitted.score().unwrap().instructions[0]
        .arrangement
        .as_ref()
        .unwrap();
    assert_eq!(arrangement.count, 8);
    assert_eq!(
        arrangement.resolved.as_ref().unwrap().count_origin,
        CountOrigin::OmittedDefault
    );
    assert_eq!(arrangement.color_cycle, [Color::Red, Color::Gray]);

    let one = execute(
        "line up one circle, repeating red, gray, and blue in order.",
        ResolvedInstructionLanguage::En,
    );
    let instruction = &one.score().unwrap().instructions[0];
    assert_eq!(instruction.color, Color::Red);
    assert_eq!(instruction.arrangement.as_ref().unwrap().count, 1);
    assert_eq!(
        instruction.arrangement.as_ref().unwrap().color_cycle,
        [Color::Red, Color::Gray, Color::Blue]
    );
}

#[test]
fn known_invalid_sequence_is_local_and_plain_multiple_colors_do_not_imply_a_cycle() {
    let invalid_source = "赤・灰・青を交互にして、円を五つ並べる。";
    let invalid_document =
        NormalizedDdlDocument::new(invalid_source, ResolvedInstructionLanguage::Ja, Vec::new())
            .unwrap();
    let invalid = associate_semantic_document(&invalid_document).unwrap();
    let issue = &invalid.instruction_association.association.sequence_issues[0];
    assert_eq!(
        issue.kind,
        SemanticSequenceIssueKind::InvalidAlternatingCardinality
    );
    assert_eq!(
        &invalid_source[issue.operator.provenance.source.span.start_byte
            ..issue.operator.provenance.source.span.end_byte],
        "交互に"
    );
    let recovered = execute_with_policy(
        "赤・灰・青を交互にして、円を五つ並べる。青い正方形を中央に置く。",
        ResolvedInstructionLanguage::Ja,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        recovered.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "upstream={:?} downstream={:?} failure={:?}",
        recovered.upstream_diagnostics(),
        recovered.downstream_diagnostics(),
        recovered.failure()
    );
    let recovered_score = recovered
        .score()
        .expect("independent later drawing survives");
    assert_eq!(recovered_score.instructions.len(), 1);
    assert_eq!(recovered_score.instructions[0].primitive, Primitive::Square);
    assert_eq!(recovered_score.instructions[0].color, Color::Blue);

    let plain_source = "赤い灰の円を五つ並べる。";
    let plain_document =
        NormalizedDdlDocument::new(plain_source, ResolvedInstructionLanguage::Ja, Vec::new())
            .unwrap();
    let plain = associate_semantic_document(&plain_document).unwrap();
    assert!(
        plain
            .instruction_association
            .association
            .ast
            .sequences
            .is_empty()
    );
    assert!(
        plain
            .instruction_association
            .association
            .sequence_issues
            .is_empty()
    );
    assert!(!plain.instruction_association.association.issues.is_empty());

    let mixed_document = NormalizedDdlDocument::new(
        "line up five circles, alternating red pen and blue.",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let mixed = associate_semantic_document(&mixed_document).unwrap();
    assert_eq!(
        mixed.instruction_association.association.sequence_issues[0].kind,
        SemanticSequenceIssueKind::InvalidConnectors
    );

    let duplicate_operator_document = NormalizedDdlDocument::new(
        "赤と灰を交互にして、円を五つ並べる、順に。",
        ResolvedInstructionLanguage::Ja,
        Vec::new(),
    )
    .unwrap();
    let duplicate_operator = associate_semantic_document(&duplicate_operator_document).unwrap();
    let association = &duplicate_operator.instruction_association.association;
    assert_eq!(
        association.owned_occurrence_count,
        association.delivered_occurrence_count
    );
    assert_eq!(association.sequence_issues.len(), 2);
    assert!(
        association
            .sequence_issues
            .iter()
            .all(|issue| issue.kind == SemanticSequenceIssueKind::MultipleOperators)
    );
}

#[test]
fn over_budget_sequence_draws_the_safe_prefix_and_keeps_the_later_drawing() {
    let budget = ResourceBudget {
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
    };
    let document = NormalizedDdlDocument::new(
        "line up 241 circles, alternating red and gray. place one blue square at center.",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = compile_ddl_to_score_with_resources(
        document,
        &[],
        Some(17),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        ScoreErrorPolicy::OmitAndContinue,
        HardResourcePolicy {
            identity: "color-sequence-test.v1".into(),
            budget,
        },
        OperationalResourceBudget(budget),
    );
    assert!(result.failure().is_none(), "{:?}", result.failure());
    assert_eq!(result.resource_omissions().len(), 1);
    let PlanResourceFailure::BudgetExceeded(exceeded) =
        &result.resource_omissions()[0].cause.reason
    else {
        panic!("expected local budget refusal")
    };
    assert_eq!(
        exceeded.dimension,
        ResourceDimension::MaximumPerTemplatePrimitiveMarks
    );
    assert_eq!((exceeded.required, exceeded.maximum), (241, 240));
    assert_eq!(
        result.resource_omissions()[0].partial_execution,
        Some(inku_ddl::PlanResourcePartialExecution {
            requested_count: 241,
            executed_count: 240,
        })
    );
    let score = result
        .score()
        .expect("safe repeated prefix and later drawing survive");
    assert_eq!(score.instructions.len(), 2);
    assert_eq!(
        score.instructions[0].arrangement.as_ref().unwrap().count,
        240
    );
    assert_eq!(score.instructions[1].primitive, Primitive::Square);
    assert_eq!(score.instructions[1].sides, None);
    assert_eq!(score.instructions[1].color, Color::Blue);
}

fn execute(source: &str, language: ResolvedInstructionLanguage) -> CompilerResourceExecutionResult {
    execute_with_policy(source, language, ScoreErrorPolicy::Stop)
}

fn execute_with_policy(
    source: &str,
    language: ResolvedInstructionLanguage,
    error_policy: ScoreErrorPolicy,
) -> CompilerResourceExecutionResult {
    let budget = ResourceBudget {
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
    };
    compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        Some(17),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        error_policy,
        HardResourcePolicy {
            identity: "color-sequence-test.v1".into(),
            budget,
        },
        OperationalResourceBudget(budget),
    )
}

fn canonical(source: &str, language: ResolvedInstructionLanguage) -> Vec<u8> {
    let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
    let result = associate_semantic_document(&document).unwrap();
    result.canonical_bytes.unwrap_or_else(|| {
        panic!(
            "{source}: {:?} {:?}",
            result.instruction_association.association.sequence_issues,
            result.instruction_association.issues
        )
    })
}
