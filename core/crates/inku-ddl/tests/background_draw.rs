use std::collections::BTreeMap;

use inku_ddl::{
    CompilerExecutionDisposition, CompilerExecutionOmissionUnit, CompilerLockState,
    MacroDefinition, MacroExpansionLimits, MacroLock, NormalizedDdlDocument, PlacementMemberKind,
    ResolvedInstructionLanguage as Language, ScoreErrorPolicy, ScoreFieldGap, ScoreLoweringContext,
    ScoreLoweringOutcome, SemanticDeliveryOwner, compile_ddl_to_score, compile_typed_ddl,
    plan_verified_stage15, stage15_transformation_input, transform_stage15,
};
use inku_render::palette::work_palette_context;
use inku_score::{Color, Primitive, ResolvedPaletteContext};
use serde_json::json;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 64,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

#[test]
fn fill_target_roles_keep_bilingual_canonical_meaning_and_original_operand_indices() {
    let compile = |source, language| {
        compile_typed_ddl(document(source, language, &[]), &[], Some(23), LIMITS)
    };
    let ja = compile("円を赤い点で埋める。", Language::Ja);
    let en = compile("fill a circle with red points.", Language::En);
    for compilation in [&ja, &en] {
        assert_eq!(
            compilation.compiler_lock.as_ref().unwrap().state,
            CompilerLockState::CanonicalReady,
            "{:?} {:?}",
            compilation.conflicts,
            compilation.blocking_diagnostics
        );
        let ast = &compilation.semantic_document.as_ref().unwrap().ast;
        assert_eq!(ast.instructions.len(), 2);
        assert!(ast.instructions[0].action.is_none());
        assert_eq!(
            ast.instructions[1].action.as_ref().unwrap().identity.id,
            "fill"
        );
        assert_eq!(
            ast.instructions[1]
                .entity
                .color
                .as_ref()
                .unwrap()
                .identity
                .id,
            "red"
        );
        let Some(inku_ddl::SemanticFillTarget::InlineShape {
            target_instruction_index,
            markers,
        }) = &ast.instructions[1].fill_target
        else {
            panic!("inline target");
        };
        assert_eq!(*target_instruction_index, 0);
        assert!(!markers.is_empty());
        for marker in markers {
            assert_eq!(
                &compilation.document.source()[marker.span.start_byte..marker.span.end_byte],
                marker.surface
            );
        }
        assert!(
            compilation
                .deliveries
                .iter()
                .any(|delivery| delivery.identity.owner == SemanticDeliveryOwner::FillTarget)
        );
    }
    assert_eq!(
        ja.pre_expansion_canonical_bytes(),
        en.pre_expansion_canonical_bytes()
    );
    let canvas = compile("背景を点で埋める。", Language::Ja);
    let canvas_en = compile("fill the background with points.", Language::En);
    assert_eq!(
        canvas_en.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady,
        "{:?} {:?} {:?}",
        canvas_en.holes,
        canvas_en.conflicts,
        canvas_en.blocking_diagnostics
    );
    assert_eq!(
        canvas.pre_expansion_canonical_bytes(),
        canvas_en.pre_expansion_canonical_bytes()
    );
    let ast = &canvas.semantic_document.as_ref().unwrap().ast;
    assert!(ast.background.is_none());
    assert!(matches!(
        ast.instructions[0].fill_target,
        Some(inku_ddl::SemanticFillTarget::Canvas { .. })
    ));
    let named = compile("上を赤い点で埋める。", Language::Ja);
    let named_en = compile("fill top with red points.", Language::En);
    assert!(
        named.pre_expansion_canonical_bytes().is_some(),
        "{:?} {:?}",
        named.conflicts,
        named.blocking_diagnostics
    );
    assert_eq!(
        named.pre_expansion_canonical_bytes(),
        named_en.pre_expansion_canonical_bytes()
    );
    assert_eq!(
        named.semantic_document.as_ref().unwrap().ast.instructions[0]
            .position
            .as_ref()
            .unwrap()
            .identity
            .id,
        "top"
    );
    let continued = compile("線を置く。線は赤い。円を点で埋める。", Language::Ja);
    let ast = &continued.semantic_document.as_ref().unwrap().ast;
    assert!(ast.complete, "{:?}", continued.blocking_diagnostics);
    assert_eq!(ast.instructions.len(), 3);
    assert!(matches!(
        ast.instructions[2].fill_target,
        Some(inku_ddl::SemanticFillTarget::InlineShape {
            target_instruction_index: 1,
            ..
        })
    ));
    assert_eq!(ast.instructions[1].entity.head.source().surface, "円");
    let ambiguous = compile("fill a circle and a square with points.", Language::En);
    assert_ne!(
        ambiguous.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady,
        "an ambiguous target must retain a diagnostic instead of becoming omitted Canvas"
    );
    assert!(
        ambiguous
            .semantic_document
            .as_ref()
            .unwrap()
            .ast
            .instructions
            .iter()
            .all(|instruction| instruction.fill_target.is_none())
    );
    let clean = execute(
        "fill a circle with one red point.",
        Language::En,
        &[],
        context(),
    );
    let recovered = execute(
        "unknown circle. fill a circle with one red point.",
        Language::En,
        &[],
        context(),
    );
    let original = &recovered
        .compilation()
        .semantic_document
        .as_ref()
        .unwrap()
        .ast;
    assert!(matches!(
        original.instructions[2].fill_target,
        Some(inku_ddl::SemanticFillTarget::InlineShape {
            target_instruction_index: 1,
            ..
        })
    ));
    assert!(
        recovered.execution_pre_expansion_digest().is_some(),
        "{:?}",
        recovered.upstream_diagnostics()
    );
    assert_eq!(
        recovered.execution_pre_expansion_digest(),
        clean.execution_pre_expansion_digest(),
        "projection must preserve the original Circle operand after removing an earlier source instruction"
    );
}

fn context() -> ScoreLoweringContext {
    let palette = work_palette_context(&BTreeMap::new(), Some(23), None, Color::White).unwrap();
    ScoreLoweringContext::resolve_with_palette("square", Color::White, palette).unwrap()
}

#[test]
fn coordinated_fill_target_roles_are_owned_once_by_the_group() {
    for (ja, en, expected_target, expected_position) in [
        (
            "赤い円と青い点で埋める。",
            "fill with red circles and blue points.",
            false,
            None,
        ),
        (
            "隅を赤い円と青い点で埋める。",
            "fill corner with red circles and blue points.",
            false,
            Some("corner"),
        ),
        (
            "円を赤い点と青い四角で埋める。",
            "fill a circle with red points and blue squares.",
            true,
            None,
        ),
    ] {
        let ja = compile_typed_ddl(document(ja, Language::Ja, &[]), &[], Some(23), LIMITS);
        let en = compile_typed_ddl(document(en, Language::En, &[]), &[], Some(23), LIMITS);
        for compilation in [&ja, &en] {
            assert_eq!(
                compilation.compiler_lock.as_ref().unwrap().state,
                CompilerLockState::CanonicalReady,
                "{}: {:?} {:?}",
                compilation.document.source(),
                compilation.conflicts,
                compilation.blocking_diagnostics
            );
            let ast = &compilation.semantic_document.as_ref().unwrap().ast;
            assert_eq!(ast.group_predicates.len(), 1);
            let edge = &ast.group_predicates[0];
            assert_eq!(edge.action.as_ref().unwrap().identity.id, "fill");
            assert_eq!(
                edge.position.as_ref().map(|term| term.identity.id.as_str()),
                expected_position
            );
            assert_eq!(edge.fill_target.is_some(), expected_target);
            assert!(ast.instructions.iter().all(
                |instruction| instruction.action.is_none() && instruction.fill_target.is_none()
            ));
            if expected_target {
                assert!(matches!(
                    edge.fill_target,
                    Some(inku_ddl::SemanticFillTarget::InlineShape {
                        target_instruction_index: 0,
                        ..
                    })
                ));
                assert_eq!(
                    ast.coordinated_head_groups[edge.group_index].member_instruction_indices,
                    [1, 2]
                );
            }
        }
        assert_eq!(
            ja.pre_expansion_canonical_bytes(),
            en.pre_expansion_canonical_bytes()
        );
    }
}

fn document(
    source: &str,
    language: Language,
    definitions: &[MacroDefinition],
) -> NormalizedDdlDocument {
    let locks = definitions
        .iter()
        .map(|definition| {
            let identity = definition.identity().unwrap();
            MacroLock::new(
                identity.qualified_name(),
                identity.version(),
                format!("sha256:{}", identity.full_digest_hex()),
            )
            .unwrap()
        })
        .collect();
    NormalizedDdlDocument::new(source, language, locks).unwrap()
}

fn execute(
    source: &str,
    language: Language,
    definitions: &[MacroDefinition],
    context: ScoreLoweringContext,
) -> inku_ddl::CompilerExecutionResult {
    compile_ddl_to_score(
        document(source, language, definitions),
        definitions,
        Some(23),
        LIMITS,
        context,
        None,
        ScoreErrorPolicy::Stop,
    )
}

#[test]
fn stage1_background_and_draw_keep_bilingual_meaning_and_source_ownership() {
    let ja = execute(
        "背景を黒で埋める。白い横線を中央に引く。",
        Language::Ja,
        &[],
        context(),
    );
    let en = execute(
        "fill the background with black. draw a white horizontal line at center.",
        Language::En,
        &[],
        context(),
    );
    for result in [&ja, &en] {
        assert_eq!(
            result.outcome(),
            ScoreLoweringOutcome::Complete,
            "{:?} {:?}",
            result.upstream_diagnostics(),
            result.downstream_diagnostics()
        );
        assert_eq!(
            result.compilation().compiler_lock.as_ref().unwrap().state,
            CompilerLockState::CanonicalReady
        );
        let score = result.score().unwrap();
        assert_eq!(score.background, Color::Black);
        assert_eq!(score.instructions.len(), 1);
        assert_eq!(score.instructions[0].primitive, Primitive::Line);
        assert_eq!(score.instructions[0].color, Color::White);
        let semantic = result.compilation().semantic_document.as_ref().unwrap();
        let background = semantic.ast.background.as_ref().unwrap();
        assert_eq!(background.color.identity.id, "black");
        assert_eq!(background.action.identity.id, "fill");
        assert!(semantic.ast.ground.is_none());
        for source in [
            &background.head,
            &background.color.provenance.source,
            &background.action.provenance.source,
        ] {
            assert_eq!(
                &result.compilation().document.source()
                    [source.span.start_byte..source.span.end_byte],
                source.surface
            );
        }
        assert!(
            result
                .compilation()
                .deliveries
                .iter()
                .any(|delivery| delivery.identity.owner == SemanticDeliveryOwner::Background)
        );
    }
    assert_eq!(ja.score(), en.score());
    assert_eq!(
        ja.compilation()
            .semantic_document
            .as_ref()
            .unwrap()
            .canonical_bytes,
        en.compilation()
            .semantic_document
            .as_ref()
            .unwrap()
            .canonical_bytes
    );
}

#[test]
fn source_background_selects_the_work_palette_for_implicit_color_and_preserves_explicit_color() {
    let map = BTreeMap::from([("red".to_owned(), "#080000".to_owned())]);
    let palette = work_palette_context(&map, None, None, Color::White).unwrap();
    let selected = palette.select_background(Color::Red).unwrap();
    assert_eq!(selected.background().concrete_rgb(), [8, 0, 0]);
    let ctx = ScoreLoweringContext::resolve_with_palette("square", Color::White, palette).unwrap();
    let result = execute(
        "fill the background with red. draw a line length 0.2 at horizontal 0.5 vertical 0.5. place one blue circle at center.",
        Language::En,
        &[],
        ctx,
    );
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::Complete,
        "{:?} {:?}",
        result.upstream_diagnostics(),
        result.downstream_diagnostics()
    );
    let score = result.score().unwrap();
    assert_eq!(score.background, Color::Red);
    assert_eq!(score.instructions[0].color, Color::White);
    assert_eq!(score.instructions[1].color, Color::Blue);

    // Old callers retain explicit colors and source background even when their
    // three observations cannot resolve that background's implicit contrast.
    let legacy =
        ResolvedPaletteContext::new(palette.background(), palette.black(), palette.white());
    let legacy_context =
        ScoreLoweringContext::resolve_with_palette("square", Color::White, legacy).unwrap();
    let partial = execute(
        "fill background with red. draw a line at center. place one blue circle at center.",
        Language::En,
        &[],
        legacy_context,
    );
    assert_eq!(
        partial.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert_eq!(partial.score().unwrap().background, Color::Red);
    assert_eq!(partial.score().unwrap().instructions.len(), 1);
    assert!(
        partial
            .downstream_diagnostics()
            .iter()
            .any(|diagnostic| diagnostic.reason == ScoreFieldGap::MissingResolvedPaletteContext)
    );
    let fallback = execute("draw a red line at center.", Language::En, &[], context());
    assert_eq!(fallback.score().unwrap().background, Color::White);
}

#[test]
fn conflicting_backgrounds_recover_without_losing_source_candidates() {
    let result = execute(
        "背景を黒で埋める。背景を青で埋める。白い線を中央に引く。",
        Language::Ja,
        &[],
        context(),
    );
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{:?} {:?}",
        result.upstream_diagnostics(),
        result.downstream_diagnostics()
    );
    let semantic = result.compilation().semantic_document.as_ref().unwrap();
    assert_eq!(semantic.background_candidates.len(), 2);
    assert!(semantic.ast.background.is_none());
    assert_eq!(
        semantic.background_candidates[0]
            .color
            .provenance
            .source
            .surface,
        "黒"
    );
    assert_eq!(
        semantic.background_candidates[1]
            .color
            .provenance
            .source
            .surface,
        "青"
    );
    let score = result.score().unwrap();
    assert_eq!(score.background, Color::White);
    assert_eq!(score.instructions.len(), 1);
    assert_eq!(score.instructions[0].primitive, Primitive::Line);
    assert!(
        result
            .upstream_diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                diagnostic.disposition,
                CompilerExecutionDisposition::Omitted {
                    unit: CompilerExecutionOmissionUnit::BackgroundCandidates
                }
            ))
    );
    let malformed = execute(
        "fill the background with a red circle. draw a white line at center.",
        Language::En,
        &[],
        context(),
    );
    assert!(
        malformed
            .compilation()
            .semantic_document
            .as_ref()
            .unwrap()
            .ast
            .background
            .is_none()
    );
    let background_only = execute("背景を黒で埋める。未知語。", Language::Ja, &[], context());
    assert_eq!(
        background_only.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert_eq!(background_only.score().unwrap().background, Color::Black);
    assert!(background_only.score().unwrap().instructions.is_empty());
}

#[test]
fn direct_and_macro_draw_share_geometry_and_repeated_plan() {
    let definition = MacroDefinition::from_json(&json!({"schema":"inku.macro-definition.v1","namespace":"Draw","heading":"Arc","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{
        "shape":{"expr":"semantic_ref","category":"shape","id":"arc"},
        "movement":{"expr":"semantic_ref","category":"movement","id":"draw"},
        "color":{"expr":"semantic_ref","category":"color","id":"red"},
        "chord":{"expr":"exact_decimal","value":"0.2"},"sagitta":{"expr":"exact_decimal","value":"0.05"},
        "position_x":{"expr":"exact_decimal","value":"0.5"},"position_y":{"expr":"exact_decimal","value":"0.5"}
    }}]}).to_string()).unwrap();
    let source = "draw one red arc chord 0.2 sagitta 0.05 at horizontal 0.5 vertical 0.5.";
    let direct = execute(source, Language::En, &[], context());
    let macro_result = execute(
        "Draw.Arc",
        Language::En,
        std::slice::from_ref(&definition),
        context(),
    );
    assert!(
        direct.score().is_some(),
        "{:?} {:?}",
        direct.upstream_diagnostics(),
        direct.downstream_diagnostics()
    );
    assert_eq!(
        direct.score(),
        macro_result.score(),
        "{:?} {:?}",
        macro_result.upstream_diagnostics(),
        macro_result.downstream_diagnostics()
    );
    let compilation = compile_typed_ddl(
        document(
            "fill background with black. draw 3 white lines length 0.2 at horizontal 0.5 vertical 0.5.",
            Language::En,
            &[],
        ),
        &[],
        Some(23),
        LIMITS,
    );
    let stage =
        transform_stage15(stage15_transformation_input(&compilation).unwrap(), None).unwrap();
    let plan = plan_verified_stage15(stage.verified_effective_view(), context());
    let objects = plan
        .objects()
        .unwrap_or_else(|| panic!("{:?}", plan.diagnostics()));
    assert_eq!(objects.len(), 1);
    assert_eq!(objects[0].count(), 3);
    assert_eq!(plan.context().background(), Color::Black);
}

#[test]
fn omitted_position_is_a_shared_execution_default_with_explicit_position_priority() {
    let result = execute("赤い円を置く。", Language::Ja, &[], context());
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::Complete,
        "{:?} {:?}",
        result.upstream_diagnostics(),
        result.downstream_diagnostics()
    );
    let semantic = result.compilation().semantic_document.as_ref().unwrap();
    assert!(semantic.ast.instructions[0].position.is_none());
    assert!(
        semantic.ast.instructions[0]
            .entity
            .numeric_position
            .is_none()
    );
    let instruction = &result.score().unwrap().instructions[0];
    assert_eq!(
        instruction.at.as_ref().unwrap().region,
        [0.39, 0.39, 0.61, 0.61]
    );
    let definition = MacroDefinition::from_json(&json!({"schema":"inku.macro-definition.v1","namespace":"Default","heading":"Circle","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{
        "shape":{"expr":"semantic_ref","category":"shape","id":"circle"},
        "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
        "color":{"expr":"semantic_ref","category":"color","id":"red"}
    }}]}).to_string()).unwrap();
    let macro_result = execute(
        "Default.Circle",
        Language::En,
        std::slice::from_ref(&definition),
        context(),
    );
    assert_eq!(result.score(), macro_result.score());
    let explicit = execute(
        "place a red circle at horizontal 0.3 vertical 0.6.",
        Language::En,
        &[],
        context(),
    );
    assert!(explicit.score().unwrap().instructions[0].at.is_none());
    assert_eq!(
        explicit.score().unwrap().instructions[0].center.unwrap(),
        inku_score::Point::new(0.3, 0.6)
    );
    let compilation = compile_typed_ddl(
        document("draw 3 red lines.", Language::En, &[]),
        &[],
        Some(23),
        LIMITS,
    );
    let stage =
        transform_stage15(stage15_transformation_input(&compilation).unwrap(), None).unwrap();
    let plan = plan_verified_stage15(stage.verified_effective_view(), context());
    let object = &plan.objects().unwrap()[0];
    assert_eq!(object.count(), 3);
    assert_eq!(
        object.anchor(),
        &inku_ddl::ObjectAnchor::Named([0.39, 0.39, 0.61, 0.61])
    );
    let policy: serde_json::Value =
        serde_json::from_slice(inku_ddl::geometry_resolution_policy_canonical_bytes()).unwrap();
    assert_eq!(
        policy["author_resolved_omission"]["position"]["region"],
        json!([0.39, 0.39, 0.61, 0.61])
    );

    let stage = |source, definitions: &[MacroDefinition]| {
        let compilation = compile_typed_ddl(
            document(source, Language::En, definitions),
            definitions,
            Some(23),
            LIMITS,
        );
        transform_stage15(stage15_transformation_input(&compilation).unwrap(), None).unwrap()
    };
    let direct_stage = stage("tile three red circles.", &[]);
    let direct_tile = plan_verified_stage15(direct_stage.verified_effective_view(), context());
    assert!(
        direct_tile.diagnostics().is_empty(),
        "{:?}",
        direct_tile.diagnostics()
    );
    let direct_object = &direct_tile.objects().unwrap()[0];
    assert_eq!(direct_object.count(), 3);
    assert_eq!(
        direct_object.anchor(),
        &inku_ddl::ObjectAnchor::Named([0.39, 0.39, 0.61, 0.61])
    );
    let tile_definition = MacroDefinition::from_json(&json!({"schema":"inku.macro-definition.v1","namespace":"Default","heading":"Tile","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{
        "shape":{"expr":"semantic_ref","category":"shape","id":"circle"},
        "movement":{"expr":"semantic_ref","category":"movement","id":"tile"},
        "color":{"expr":"semantic_ref","category":"color","id":"red"},
        "count":{"expr":"integer","value":3}
    }}]}).to_string()).unwrap();
    let macro_stage = stage("Default.Tile", std::slice::from_ref(&tile_definition));
    let macro_tile = plan_verified_stage15(macro_stage.verified_effective_view(), context());
    assert!(
        macro_tile.diagnostics().is_empty(),
        "{:?}",
        macro_tile.diagnostics()
    );
    assert_eq!(
        macro_tile.objects().unwrap()[0].anchor(),
        direct_object.anchor()
    );
    assert_eq!(
        macro_tile.objects().unwrap()[0].recipe(),
        direct_object.recipe()
    );

    let coordinated = execute(
        "place one red circle and one blue square.",
        Language::En,
        &[],
        context(),
    );
    assert_eq!(
        coordinated.outcome(),
        ScoreLoweringOutcome::Complete,
        "{:?}",
        coordinated.downstream_diagnostics()
    );
    assert_eq!(
        coordinated.score().unwrap().placement_groups[0].at.region,
        [0.39, 0.39, 0.61, 0.61]
    );
    let mixed_stage = stage(
        "scatter three Default.Circle and one blue square.",
        std::slice::from_ref(&definition),
    );
    let mixed = plan_verified_stage15(mixed_stage.verified_effective_view(), context());
    assert!(mixed.diagnostics().is_empty(), "{:?}", mixed.diagnostics());
    let group = &mixed.placement_groups()[0];
    assert_eq!(group.placement().at.region, [0.39, 0.39, 0.61, 0.61]);
    assert_eq!(group.members()[0].kind(), PlacementMemberKind::Macro);
    assert_eq!(group.members()[0].body_repeat_count(), 3);
}
