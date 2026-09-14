use inku_ddl::{
    CompilerResourceExecutionResult, MacroDefinition, MacroExpansionLimits, MacroLock,
    NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext,
    ScoreLoweringOutcome, SemanticSequenceIssueKind, associate_semantic_document,
    compile_ddl_to_score_with_resources,
};
use inku_score::{
    Color, HardResourcePolicy, OperationalResourceBudget, Primitive, ResolvedPaletteColor,
    ResolvedPaletteContext, ResourceBudget, ResourceDemand, ResourceDimension, ScoreSourceOwner,
    SymbolicMemberKind, Weight,
};
use serde_json::{Value, json};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 128,
    max_nodes_per_invocation: 64,
    max_total_nodes: 128,
};

#[test]
fn ordinary_sequences_deliver_field_shape_group_and_bilingual_identity() {
    let field = execute(
        "鉛筆と太筆を交互にして、線を五本並べる。",
        ResolvedInstructionLanguage::Ja,
        &[],
        Vec::new(),
        standard_budget(),
        ScoreErrorPolicy::Stop,
    );
    let field_score = complete_score(&field);
    let field_group = &field_score.placement_groups[0];
    assert_eq!(field_score.version, "0.14.0");
    assert_eq!(
        field_group.cycle_members.as_ref().unwrap().occurrence_count,
        5
    );
    assert_eq!(
        field_score
            .instructions
            .iter()
            .map(|instruction| instruction.weight)
            .collect::<Vec<_>>(),
        [Weight::Pencil, Weight::BrushThick]
    );
    assert_eq!(field_group.members.len(), 2);
    assert!(field_group.members.iter().all(|member| {
        matches!(
            member.symbolic.as_ref(),
            Some(symbolic)
                if symbolic.kind == SymbolicMemberKind::Primitive
                    && symbolic.owner
                        == ScoreSourceOwner::SourceInstruction { instruction_index: 0 }
        )
    }));

    let shapes = execute(
        "赤い小さな円・青い小さな線・灰の小さな弧の順に繰り返して、八つ並べる。",
        ResolvedInstructionLanguage::Ja,
        &[],
        Vec::new(),
        standard_budget(),
        ScoreErrorPolicy::Stop,
    );
    let shape_score = complete_score(&shapes);
    assert_eq!(
        shape_score
            .instructions
            .iter()
            .map(|instruction| instruction.primitive)
            .collect::<Vec<_>>(),
        [Primitive::Circle, Primitive::Line, Primitive::Arc]
    );
    assert_eq!(
        shape_score.placement_groups[0]
            .cycle_members
            .as_ref()
            .unwrap()
            .occurrence_count,
        8
    );

    let group_ja = "赤い円と青い線の組を、灰の弧と交互に5つ並べる。";
    let group_en =
        "Line up five, alternating a group of a red circle and a blue line with a gray arc.";
    assert_eq!(
        canonical(group_ja, ResolvedInstructionLanguage::Ja),
        canonical(group_en, ResolvedInstructionLanguage::En)
    );
    let grouped = execute(
        group_ja,
        ResolvedInstructionLanguage::Ja,
        &[],
        Vec::new(),
        standard_budget(),
        ScoreErrorPolicy::Stop,
    );
    let grouped_score = complete_score(&grouped);
    assert_eq!(grouped_score.instructions.len(), 3);
    let group = &grouped_score.placement_groups[0];
    assert_eq!(group.cycle_members.as_ref().unwrap().occurrence_count, 5);
    assert_eq!(group.members.len(), 2);
    let symbolic = group.members[0].symbolic.as_ref().unwrap();
    assert_eq!(symbolic.kind, SymbolicMemberKind::OrdinaryGroup);
    assert_eq!(
        symbolic.owner,
        ScoreSourceOwner::OrdinaryGroup {
            source_instruction_indices: vec![0, 1],
        }
    );
    assert_eq!((group.members[0].start, group.members[0].end), (0, 2));
    grouped_score.validate_schema_edition().unwrap();
}

#[test]
fn natural_japanese_count_boundaries_reach_the_outer_occurrence_count() {
    for (source, count) in [
        ("赤い円と青い線を交互にして、1個並べる。", 1),
        ("赤い円と青い線を交互にして、９つ並べる。", 9),
        ("赤い円と青い線を交互にして、10並べる。", 10),
        ("赤い円と青い線を交互にして、11個並べる。", 11),
    ] {
        let result = execute(
            source,
            ResolvedInstructionLanguage::Ja,
            &[],
            Vec::new(),
            standard_budget(),
            ScoreErrorPolicy::Stop,
        );
        assert_eq!(
            complete_score(&result).placement_groups[0]
                .cycle_members
                .as_ref()
                .unwrap()
                .occurrence_count,
            count,
            "{source}"
        );
    }
    let unnatural = execute(
        "赤い円と青い線を交互にして、10つ並べる。",
        ResolvedInstructionLanguage::Ja,
        &[],
        Vec::new(),
        standard_budget(),
        ScoreErrorPolicy::Stop,
    );
    assert!(unnatural.score().is_none());
}

#[test]
fn macro_inside_anonymous_group_keeps_real_source_ownership() {
    let definition = pair_definition();
    let identity = definition.identity().unwrap();
    let lock = MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap();
    let result = execute(
        "Line up five, alternating a group of Draw.Pair and a red circle with a gray arc.",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
        vec![lock],
        standard_budget(),
        ScoreErrorPolicy::Stop,
    );
    let score = complete_score(&result);
    let group = &score.placement_groups[0];
    assert_eq!(group.cycle_members.as_ref().unwrap().occurrence_count, 5);
    assert_eq!(group.members.len(), 2);
    assert_eq!(
        group.members[0].symbolic.as_ref().unwrap().owner,
        ScoreSourceOwner::OrdinaryGroup {
            source_instruction_indices: vec![0, 1],
        }
    );
    assert!(group.members[0].end - group.members[0].start >= 3);
    score.validate_schema_edition().unwrap();
}

#[test]
fn invalid_and_over_budget_member_cycles_omit_only_their_placement() {
    let invalid_source = "赤い円・青い線・灰の弧を交互にして、五つ並べる。緑の正方形を中央に置く。";
    let document =
        NormalizedDdlDocument::new(invalid_source, ResolvedInstructionLanguage::Ja, Vec::new())
            .unwrap();
    let semantic = associate_semantic_document(&document).unwrap();
    assert_eq!(
        semantic.instruction_association.association.sequence_issues[0].kind,
        SemanticSequenceIssueKind::InvalidAlternatingCardinality
    );
    let invalid = execute(
        invalid_source,
        ResolvedInstructionLanguage::Ja,
        &[],
        Vec::new(),
        standard_budget(),
        ScoreErrorPolicy::OmitAndContinue,
    );
    let invalid_score = invalid.score().expect("later instruction survives");
    assert_eq!(
        invalid.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert_eq!(invalid_score.instructions.len(), 1);
    assert_eq!(invalid_score.instructions[0].primitive, Primitive::Square);

    let budgeted = execute(
        "赤い円と青い線の組を、灰の弧と交互に5つ並べる。緑の正方形を中央に置く。",
        ResolvedInstructionLanguage::Ja,
        &[],
        Vec::new(),
        budget_with_primitive_marks(7),
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert!(budgeted.failure().is_none(), "{:?}", budgeted.failure());
    assert_eq!(budgeted.resource_omissions().len(), 1);
    let exceeded = match &budgeted.resource_omissions()[0].cause.reason {
        inku_ddl::PlanResourceFailure::BudgetExceeded(exceeded) => exceeded,
        reason => panic!("unexpected resource omission: {reason:?}"),
    };
    assert_eq!(exceeded.dimension, ResourceDimension::PrimitiveMarks);
    assert_eq!((exceeded.required, exceeded.maximum), (8, 7));
    let score = budgeted.score().expect("independent sibling survives");
    assert_eq!(score.instructions.len(), 1);
    assert_eq!(score.instructions[0].primitive, Primitive::Square);
}

#[test]
fn fill_cycle_delivers_and_u64_count_reaches_local_resource_omission() {
    let fill = execute(
        "赤い円と青い線を交互にして、五つで埋める。",
        ResolvedInstructionLanguage::Ja,
        &[],
        Vec::new(),
        standard_budget(),
        ScoreErrorPolicy::Stop,
    );
    let fill_score = complete_score(&fill);
    assert!(fill_score.placement_groups.is_empty());
    assert_eq!(fill_score.fill_groups.len(), 1);
    let fill_group = &fill_score.fill_groups[0];
    assert_eq!(fill_group.logical_count, 5);
    assert_eq!(fill_group.members.len(), 2);
    assert_eq!(
        fill_group.cycle_members.as_ref().unwrap().occurrence_count,
        5
    );

    let huge = execute(
        "Line up 4294967296, alternating a red circle and a blue line. Place one green square at center.",
        ResolvedInstructionLanguage::En,
        &[],
        Vec::new(),
        standard_budget(),
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert!(huge.failure().is_none(), "{:?}", huge.failure());
    assert_eq!(huge.resource_omissions().len(), 1);
    assert!(matches!(
        huge.resource_omissions()[0].cause.reason,
        inku_ddl::PlanResourceFailure::BudgetExceeded(_)
    ));
    let score = huge.score().expect("independent sibling survives");
    assert_eq!(score.instructions.len(), 1);
    assert_eq!(score.instructions[0].primitive, Primitive::Square);
}

fn execute(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    locks: Vec<MacroLock>,
    operational: ResourceBudget,
    policy: ScoreErrorPolicy,
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
        policy,
        HardResourcePolicy {
            identity: "ordinary-member-sequence-test.v1".into(),
            budget: standard_budget(),
        },
        OperationalResourceBudget(operational),
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
            result.instruction_association.association.sequence_issues,
            result.instruction_association.issues
        )
    })
}

fn standard_budget() -> ResourceBudget {
    budget_with_primitive_marks(400)
}

fn budget_with_primitive_marks(primitive_marks: u64) -> ResourceBudget {
    ResourceBudget {
        maximum: ResourceDemand {
            logical_objects: 400,
            primitive_marks,
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

fn pair_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        &json!({
            "schema": "inku.macro-definition.v1",
            "namespace": "Draw",
            "heading": "Pair",
            "version": "1.0.0",
            "parameters": {},
            "components": {},
            "body": [
                emit("circle", "red", "0.35"),
                emit("line", "blue", "0.65")
            ]
        })
        .to_string(),
    )
    .unwrap()
}

fn emit(shape: &str, color: &str, x: &str) -> Value {
    json!({
        "op": "emit",
        "binding": null,
        "fields": {
            "shape": {"expr": "semantic_ref", "category": "shape", "id": shape},
            "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
            "color": {"expr": "semantic_ref", "category": "color", "id": color},
            "position_x": {"expr": "exact_decimal", "value": x},
            "position_y": {"expr": "exact_decimal", "value": "0.5"},
            "count": {"expr": "integer", "value": 1}
        }
    })
}
