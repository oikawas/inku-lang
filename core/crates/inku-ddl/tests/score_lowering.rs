use inku_ddl::{
    CoreModifierValue, EXPLICIT_SCORE_LOWERING_SCHEMA_ID, ExactCountFieldCandidate, FocusRegion,
    GEOMETRY_RESOLUTION_POLICY_ID, MacroDefinition, MacroExpansionLimits, MacroLock,
    NormalizedDdlDocument, ResolvedInstructionLanguage, SCORE_FIELD_CANDIDATE_SCHEMA_ID,
    ScoreFieldGap, ScoreLoweringCandidate, ScoreLoweringContext, SemanticHead, SemanticIdentity,
    Stage15TransformationResult, VerifiedStage15EffectiveView, compile_typed_ddl,
    geometry_resolution_policy_digest, lower_verified_stage15_score, lower_verified_stage15_view,
    score_primitive_from_semantic_identity, stage15_transformation_input, transform_stage15,
};
use inku_render::palette::{default_color_map, work_palette_context};
use inku_render::placement::region_in_short_side_units;
use inku_render::planning::{instruction_anchor, resolve_at_region};
use inku_render::types::CanvasSize;
use inku_score::{
    Color, LineStyle, Point, Primitive, ResolvedPaletteColor, ResolvedPaletteContext, Weight,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 16,
    max_depth: 16,
    max_evaluation_steps: 1_000,
    max_nodes_per_invocation: 100,
    max_total_nodes: 500,
};

#[test]
fn lowering_entry_requires_a_verified_stage15_effective_view() {
    fn accepts_entry_signature(
        _: for<'a> fn(VerifiedStage15EffectiveView<'a>) -> ScoreLoweringCandidate<'a>,
    ) {
    }

    accepts_entry_signature(lower_verified_stage15_view);
}

#[test]
fn lowering_context_requires_an_explicit_registry_canvas_and_background() {
    assert_eq!(
        ScoreLoweringContext::resolve("not-a-canvas", Color::Blue),
        Err(inku_ddl::ScoreLoweringContextError::UnknownCanvasFormat)
    );
    let context = ScoreLoweringContext::resolve("wide", Color::Blue).unwrap();
    assert_eq!(context.canvas_format().id, "wide");
    assert_eq!(context.background(), Color::Blue);
    assert_eq!(context.resolved_palette(), None);

    let mismatched = resolved_palette(Color::White, 0.9, 0.1, 1.0);
    assert_eq!(
        ScoreLoweringContext::resolve_with_palette("wide", Color::Blue, mismatched),
        Err(inku_ddl::ScoreLoweringContextError::ResolvedPaletteRoleMismatch)
    );
    let invalid = resolved_palette(Color::Blue, f64::NAN, 0.1, 1.0);
    assert_eq!(
        ScoreLoweringContext::resolve_with_palette("wide", Color::Blue, invalid),
        Err(inku_ddl::ScoreLoweringContextError::InvalidResolvedPaletteLightness)
    );
}

#[test]
fn omitted_count_size_and_drawing_attributes_resolve_to_an_actual_score() {
    let result = stage15(
        "place circle at horizontal 0.5, vertical 0.5.",
        ResolvedInstructionLanguage::En,
    );
    let semantic = &result.original_semantic_document().instructions[0].entity;
    assert!(semantic.quantity.is_none());
    assert!(semantic.explicit_geometry.is_none());
    assert!(semantic.color.is_none());
    assert!(semantic.touch.is_none());
    assert!(semantic.continuity.is_none());
    assert!(semantic.surface.quality.is_none());
    let color_map = default_color_map();
    let palette = work_palette_context(&color_map, None, None, Color::White).unwrap();
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve_with_palette("wide", Color::White, palette).unwrap(),
    );

    assert!(lowered.gaps().is_empty(), "{:?}", lowered.gaps());
    let instruction = &lowered.score().unwrap().instructions[0];
    assert_eq!(instruction.radius, Some(0.12));
    assert_eq!(instruction.color, Color::Black);
    assert_eq!(instruction.weight, Weight::Pen);
    assert_eq!(instruction.style, LineStyle::Solid);
    assert!(instruction.filled);
}

#[test]
fn resolved_center_focus_reaches_the_owned_actual_score_instruction() {
    let result = stage15(
        "place one red circle at the center.",
        ResolvedInstructionLanguage::En,
    );
    assert_eq!(result.targets().len(), 1);
    let expected_region = expected_focus_region(result.targets()[0].effective_focus);
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );

    assert!(lowered.gaps().is_empty(), "{:?}", lowered.gaps());
    let instruction = &lowered.score().unwrap().instructions[0];
    assert_eq!(
        instruction.at.as_ref().map(|at| at.region),
        Some(expected_region)
    );
    assert_eq!(instruction.radius, Some(0.12));
    assert_eq!(instruction.center, None);
    assert_eq!(instruction.position, None);
}

#[test]
fn named_focus_reuses_dimensions_for_all_four_supported_closed_shapes() {
    for (source, expected_radius, expected_size) in [
        ("place one small red circle at center.", Some(0.06), None),
        (
            "place one small red ellipse at center.",
            None,
            Some(Point::new(0.12, 0.072)),
        ),
        (
            "place one small red cloudform at center.",
            None,
            Some(Point::new(0.12, 0.072)),
        ),
        (
            "place one small red square at center.",
            None,
            Some(Point::new(0.12, 0.12)),
        ),
    ] {
        let result = stage15(source, ResolvedInstructionLanguage::En);
        let lowered = lower_verified_stage15_score(
            result.verified_effective_view(),
            ScoreLoweringContext::resolve("a4", Color::White).unwrap(),
        );

        assert!(lowered.gaps().is_empty(), "{source}: {:?}", lowered.gaps());
        let instruction = &lowered.score().unwrap().instructions[0];
        assert_eq!(instruction.radius, expected_radius, "{source}");
        assert_eq!(instruction.size, expected_size, "{source}");
        assert!(instruction.center.is_none(), "{source}");
        assert!(instruction.position.is_none(), "{source}");
        assert_eq!(
            instruction.at.as_ref().map(|at| at.region),
            Some(expected_focus_region(result.targets()[0].effective_focus)),
            "{source}"
        );
    }
}

#[test]
fn japanese_and_english_center_meaning_lower_to_the_same_effective_score() {
    let ja = stage15("赤い円を中心に置く。", ResolvedInstructionLanguage::Ja);
    let en = stage15(
        "place a red circle at the center.",
        ResolvedInstructionLanguage::En,
    );
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let ja_lowered = lower_verified_stage15_score(ja.verified_effective_view(), context);
    let en_lowered = lower_verified_stage15_score(en.verified_effective_view(), context);

    assert_eq!(
        ja.original_pre_expansion_digest(),
        en.original_pre_expansion_digest()
    );
    assert_eq!(
        ja.targets()[0].effective_focus,
        en.targets()[0].effective_focus
    );
    assert_eq!(ja_lowered.score(), en_lowered.score());
    assert!(ja_lowered.gaps().is_empty());
    assert!(en_lowered.gaps().is_empty());
}

#[test]
fn mixed_numeric_and_center_focus_use_their_exact_instruction_owners_in_order() {
    let result = stage15(
        concat!(
            "place one red circle at horizontal 0.3, vertical 0.5. ",
            "place one blue square at center."
        ),
        ResolvedInstructionLanguage::En,
    );
    assert_eq!(result.targets().len(), 1);
    assert!(matches!(
        result.targets()[0].path,
        inku_ddl::Stage15TargetPath::Instruction {
            instruction_index: 1
        }
    ));
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );

    assert!(lowered.gaps().is_empty(), "{:?}", lowered.gaps());
    let instructions = &lowered.score().unwrap().instructions;
    assert_eq!(instructions.len(), 2);
    assert_eq!(instructions[0].primitive, Primitive::Circle);
    assert_eq!(instructions[0].center, Some(Point::new(0.3, 0.5)));
    assert!(instructions[0].at.is_none());
    assert_eq!(instructions[1].primitive, Primitive::Square);
    assert!(instructions[1].position.is_none());
    assert_eq!(
        instructions[1].at.as_ref().map(|at| at.region),
        Some(expected_focus_region(result.targets()[0].effective_focus))
    );
}

#[test]
fn actual_named_score_reaches_existing_non_square_planning_without_shape_fit() {
    let circle_result = stage15(
        "place one red circle radius 0.9 at the center.",
        ResolvedInstructionLanguage::En,
    );
    let square_result = stage15(
        "place one blue square side length 0.9 at the center.",
        ResolvedInstructionLanguage::En,
    );
    let circle_lowered = lower_verified_stage15_score(
        circle_result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );
    let square_lowered = lower_verified_stage15_score(
        square_result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );
    assert!(
        circle_lowered.gaps().is_empty(),
        "{:?}",
        circle_lowered.gaps()
    );
    assert!(
        square_lowered.gaps().is_empty(),
        "{:?}",
        square_lowered.gaps()
    );
    let circle = &circle_lowered.score().unwrap().instructions[0];
    let square = &square_lowered.score().unwrap().instructions[0];
    let canvas = Some(CanvasSize::new(200.0, 1000.0));

    let original_region = circle.at.as_ref().unwrap().region;
    let performed_region = region_in_short_side_units(original_region, canvas);
    let planned_circle = resolve_at_region(circle, -7, 0, canvas);
    let circle_anchor = instruction_anchor(&planned_circle);
    assert!(planned_circle.at.is_none());
    assert_eq!(planned_circle.radius, Some(0.9));
    assert!((performed_region[0]..=performed_region[2]).contains(&circle_anchor.x));
    assert!((performed_region[1]..=performed_region[3]).contains(&circle_anchor.y));

    let planned_square = resolve_at_region(square, -7, 1, canvas);
    assert!(planned_square.at.is_none());
    assert_eq!(planned_square.size, Some(Point::new(0.9, 0.9)));
    let top_left = planned_square.position.unwrap();
    assert!((0.0..=1.0).contains(&top_left.x));
    assert!((0.0..=1.0).contains(&top_left.y));
}

#[test]
fn explicit_numeric_direct_ddl_is_admitted_by_the_existing_compilation_api() {
    let source =
        "place one red pen solid empty circle with radius 0.25 at horizontal 0.5, vertical 0.5.";
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new()).unwrap(),
        &[],
        None,
        LIMITS,
    );

    assert!(
        compilation.holes.is_empty()
            && compilation.conflicts.is_empty()
            && compilation.blocking_diagnostics.is_empty()
            && compilation.delivery_summary.recognized_but_ignored == 0
            && stage15_transformation_input(&compilation).is_ok(),
        "explicit numeric direct DDL must reach the verified Stage 1.5 boundary: {compilation:#?}"
    );
}

#[test]
fn ja_and_en_equivalent_decimals_lower_to_the_same_actual_score_and_keep_source_spelling() {
    let en_source =
        "place one red pen solid empty circle with radius 0.50 at horizontal 0.5, vertical 0.500.";
    let ja_source = "画面の横0.50、縦0.5の位置に、半径0.5の赤いペンの実線の空の円をひとつ置く。";
    let en = stage15(en_source, ResolvedInstructionLanguage::En);
    let ja = stage15(ja_source, ResolvedInstructionLanguage::Ja);
    assert_eq!(
        en.original_pre_expansion_digest(),
        ja.original_pre_expansion_digest(),
        "localized source and decimal spelling stay out of canonical meaning"
    );
    assert_ne!(
        en.original_semantic_document().instructions[0]
            .entity
            .explicit_geometry
            .as_ref()
            .unwrap()
            .source()
            .surface,
        ja.original_semantic_document().instructions[0]
            .entity
            .explicit_geometry
            .as_ref()
            .unwrap()
            .source()
            .surface
    );

    let context = ScoreLoweringContext::resolve("a4", Color::White).unwrap();
    let en_lowered = lower_verified_stage15_score(en.verified_effective_view(), context);
    let ja_lowered = lower_verified_stage15_score(ja.verified_effective_view(), context);
    assert_eq!(en_lowered.schema_id(), EXPLICIT_SCORE_LOWERING_SCHEMA_ID);
    assert_eq!(en_lowered.score(), ja_lowered.score());
    assert!(en_lowered.gaps().is_empty());
    let score = en_lowered.score().unwrap();
    assert_eq!(score.canvas, inku_score::Canvas::Id("a4".to_owned()));
    assert_eq!(score.background, Color::White);
    assert_eq!(score.instructions[0].center, Some(Point::new(0.5, 0.5)));
    assert_eq!(score.instructions[0].radius, Some(0.5));
    assert_eq!(score.instructions[0].color, Color::Red);
    assert_eq!(score.instructions[0].weight, Weight::Pen);
    assert_eq!(score.instructions[0].style, LineStyle::Solid);
    assert!(!score.instructions[0].filled);
    assert_eq!(en_lowered.policy_id(), GEOMETRY_RESOLUTION_POLICY_ID);
    assert_eq!(
        en_lowered.policy_digest(),
        geometry_resolution_policy_digest()
    );
    assert_eq!(
        en.verified_effective_view().geometry_policy_digest(),
        en_lowered.policy_digest()
    );
}

#[test]
fn four_explicit_primitives_use_short_edge_size_and_axis_position_geometry() {
    let cases = [
        (
            "place one red pen solid empty circle with diameter 0.4 at horizontal 0.5, vertical 0.5.",
            "wide",
            Primitive::Circle,
            Some(Point::new(0.5, 0.5)),
            Some(0.2),
            None,
            None,
            Color::Red,
            Weight::Pen,
            LineStyle::Solid,
        ),
        (
            "place one blue pencil dashed empty ellipse with width 0.4, height 0.2 at horizontal 0.5, vertical 0.5.",
            "a4",
            Primitive::Ellipse,
            Some(Point::new(0.5, 0.5)),
            None,
            None,
            Some(Point::new(0.4, 0.2)),
            Color::Blue,
            Weight::Pencil,
            LineStyle::Dashed,
        ),
        (
            "place one gray crayon dotted empty cloudform with width 0.3, height 0.2 at horizontal 0.5, vertical 0.5.",
            "vertical",
            Primitive::Cloudform,
            Some(Point::new(0.5, 0.5)),
            None,
            None,
            Some(Point::new(0.3, 0.2)),
            Color::Gray,
            Weight::Crayon,
            LineStyle::Dotted,
        ),
        (
            "place one black rotring solid empty square with side length 0.2 at horizontal 0.5, vertical 0.5.",
            "wide",
            Primitive::Square,
            None,
            None,
            Some(Point::new(0.5 - 2.0 / 47.0, 0.4)),
            Some(Point::new(0.2, 0.2)),
            Color::Black,
            Weight::Rotring,
            LineStyle::Solid,
        ),
    ];
    for (source, canvas, primitive, center, radius, position, size, color, weight, style) in cases {
        let result = stage15(source, ResolvedInstructionLanguage::En);
        assert!(
            result.targets().is_empty(),
            "numeric position must not become Stage 1.5 focus: {source}"
        );
        let lowered = lower_verified_stage15_score(
            result.verified_effective_view(),
            ScoreLoweringContext::resolve(canvas, Color::White).unwrap(),
        );
        assert!(lowered.gaps().is_empty(), "{source}: {:?}", lowered.gaps());
        let instruction = &lowered.score().unwrap().instructions[0];
        assert_eq!(instruction.primitive, primitive, "{source}");
        assert_eq!(instruction.center, center, "{source}");
        assert_eq!(instruction.radius, radius, "{source}");
        if let Some(expected) = position {
            let actual = instruction.position.unwrap();
            assert!((actual.x - expected.x).abs() < 1.0e-15, "{source}");
            assert!((actual.y - expected.y).abs() < 1.0e-15, "{source}");
        } else {
            assert_eq!(instruction.position, None, "{source}");
        }
        assert_eq!(instruction.size, size, "{source}");
        assert_eq!(instruction.color, color, "{source}");
        assert_eq!(instruction.weight, weight, "{source}");
        assert_eq!(instruction.style, style, "{source}");
        assert!(!instruction.filled, "{source}");
    }
}

#[test]
fn multiple_independent_count_one_instructions_preserve_count_and_source_order() {
    let source = concat!(
        "place one red pen solid empty circle with radius 0.1 at horizontal 0.3, vertical 0.5. ",
        "place one blue pencil dashed empty square with side length 0.2 at horizontal 0.7, vertical 0.5."
    );
    let result = stage15(source, ResolvedInstructionLanguage::En);
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
    );
    let score = lowered.score().unwrap();
    assert_eq!(score.instructions.len(), 2);
    assert_eq!(score.instructions[0].primitive, Primitive::Circle);
    assert_eq!(score.instructions[1].primitive, Primitive::Square);
    assert_eq!(score.instructions[0].color, Color::Red);
    assert_eq!(score.instructions[1].color, Color::Blue);
}

#[test]
fn inline_and_continuation_explicit_geometry_share_one_score_meaning() {
    let inline = stage15(
        "place one red pen solid empty circle with radius 0.25 at horizontal 0.5, vertical 0.5.",
        ResolvedInstructionLanguage::En,
    );
    let continuation = stage15(
        "one red pen solid empty circle. the circle radius 0.25 horizontal 0.5 vertical 0.5 place.",
        ResolvedInstructionLanguage::En,
    );
    assert_eq!(
        inline.original_pre_expansion_digest(),
        continuation.original_pre_expansion_digest(),
        "inline={:#?}\ncontinuation={:#?}",
        inline.original_semantic_document(),
        continuation.original_semantic_document()
    );
    let context = ScoreLoweringContext::resolve("square", Color::White).unwrap();
    assert_eq!(
        lower_verified_stage15_score(inline.verified_effective_view(), context).score(),
        lower_verified_stage15_score(continuation.verified_effective_view(), context).score()
    );
}

#[test]
fn normal_geometry_uses_short_edge_aspect_and_center_for_the_closed_subset() {
    for (source, primitive, radius, size) in [
        (
            "place one red pen solid empty circle at horizontal 0.5, vertical 0.5.",
            Primitive::Circle,
            Some(0.12),
            None,
        ),
        (
            "place one red pen solid empty ellipse at horizontal 0.5, vertical 0.5.",
            Primitive::Ellipse,
            None,
            Some(Point::new(0.24, 0.144)),
        ),
        (
            "place one red pen solid empty cloudform at horizontal 0.5, vertical 0.5.",
            Primitive::Cloudform,
            None,
            Some(Point::new(0.24, 0.144)),
        ),
        (
            "place one red pen solid empty square at horizontal 0.5, vertical 0.5.",
            Primitive::Square,
            None,
            Some(Point::new(0.24, 0.24)),
        ),
    ] {
        let result = stage15(source, ResolvedInstructionLanguage::En);
        let lowered = lower_verified_stage15_score(
            result.verified_effective_view(),
            ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
        );
        assert!(lowered.gaps().is_empty(), "{source}: {:?}", lowered.gaps());
        let instruction = &lowered.score().unwrap().instructions[0];
        assert_eq!(instruction.primitive, primitive, "{source}");
        assert_eq!(instruction.radius, radius, "{source}");
        assert_eq!(instruction.size, size, "{source}");
        if primitive == Primitive::Square {
            let position = instruction.position.unwrap();
            assert!((position.x - (0.5 - 2.4 / 47.0)).abs() < 1.0e-15);
            assert!((position.y - 0.38).abs() < 1.0e-15);
        } else {
            assert_eq!(instruction.center, Some(Point::new(0.5, 0.5)));
        }
    }
}

#[test]
fn seven_size_classes_apply_table_b_once_and_explicit_normal_remains_source_fact() {
    for (surface, value, factor) in [
        ("slightly small", CoreModifierValue::SlightlySmall, 0.75),
        ("small", CoreModifierValue::Small, 0.50),
        ("very small", CoreModifierValue::VerySmall, 0.375),
        ("normal-sized", CoreModifierValue::Normal, 1.0),
        ("slightly large", CoreModifierValue::SlightlyLarge, 1.25),
        ("large", CoreModifierValue::Large, 1.50),
        ("very large", CoreModifierValue::VeryLarge, 1.75),
    ] {
        let source = format!(
            "place one red pen solid empty {surface} circle at horizontal 0.5, vertical 0.5."
        );
        let result = stage15(&source, ResolvedInstructionLanguage::En);
        assert_eq!(
            result.original_semantic_document().instructions[0]
                .entity
                .relative_scale
                .as_ref()
                .map(|scale| scale.value),
            Some(value),
            "{source}"
        );
        let lowered = lower_verified_stage15_score(
            result.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        );
        assert_eq!(
            lowered.score().unwrap().instructions[0].radius,
            Some(0.12 * factor),
            "{source}"
        );
    }

    let omitted = stage15(
        "place one red pen solid empty circle at horizontal 0.5, vertical 0.5.",
        ResolvedInstructionLanguage::En,
    );
    let explicit = stage15(
        "place one red pen solid empty normal-sized circle at horizontal 0.5, vertical 0.5.",
        ResolvedInstructionLanguage::En,
    );
    assert!(
        omitted.original_semantic_document().instructions[0]
            .entity
            .relative_scale
            .is_none()
    );
    assert_eq!(
        explicit.original_semantic_document().instructions[0]
            .entity
            .relative_scale
            .as_ref()
            .map(|scale| scale.value),
        Some(CoreModifierValue::Normal)
    );
    let context = ScoreLoweringContext::resolve("square", Color::White).unwrap();
    assert_eq!(
        lower_verified_stage15_score(omitted.verified_effective_view(), context).score(),
        lower_verified_stage15_score(explicit.verified_effective_view(), context).score()
    );
}

#[test]
fn japanese_size_with_intervening_drawing_modifiers_reaches_the_same_score() {
    let ja = stage15(
        "画面の横0.5、縦0.5の位置に、とても小さな赤いペンの実線の空の円をひとつ置く。",
        ResolvedInstructionLanguage::Ja,
    );
    let en = stage15(
        "place one very small red pen solid empty circle at horizontal 0.5, vertical 0.5.",
        ResolvedInstructionLanguage::En,
    );
    let context = ScoreLoweringContext::resolve("square", Color::White).unwrap();
    assert_eq!(
        lower_verified_stage15_score(ja.verified_effective_view(), context).score(),
        lower_verified_stage15_score(en.verified_effective_view(), context).score()
    );
    assert_eq!(
        lower_verified_stage15_score(en.verified_effective_view(), context)
            .score()
            .unwrap()
            .instructions[0]
            .radius,
        Some(0.045)
    );
}

#[test]
fn omission_color_uses_actual_palette_contrast_with_black_tie_and_explicit_values_win() {
    for (background, expected) in [(Color::White, Color::Black), (Color::Black, Color::White)] {
        let color_map = default_color_map();
        let palette = work_palette_context(&color_map, None, None, background).unwrap();
        let result = stage15(
            "place one pen solid flat circle at horizontal 0.5, vertical 0.5.",
            ResolvedInstructionLanguage::En,
        );
        let lowered = lower_verified_stage15_score(
            result.verified_effective_view(),
            ScoreLoweringContext::resolve_with_palette("square", background, palette).unwrap(),
        );
        assert_eq!(lowered.score().unwrap().instructions[0].color, expected);
    }

    let mut tie_map = default_color_map();
    tie_map.insert("black".to_owned(), "#777777".to_owned());
    tie_map.insert("white".to_owned(), "#777777".to_owned());
    let tie_palette = work_palette_context(&tie_map, None, None, Color::Gray).unwrap();
    let omitted = stage15(
        "place circle at horizontal 0.5, vertical 0.5.",
        ResolvedInstructionLanguage::En,
    );
    let tie = lower_verified_stage15_score(
        omitted.verified_effective_view(),
        ScoreLoweringContext::resolve_with_palette("square", Color::Gray, tie_palette).unwrap(),
    );
    assert_eq!(tie.score().unwrap().instructions[0].color, Color::Black);

    for (surface, filled) in [("empty", false), ("flat", true), ("", true)] {
        let source = format!("place one red {surface} circle at horizontal 0.5, vertical 0.5.");
        let explicit = stage15(&source, ResolvedInstructionLanguage::En);
        let lowered = lower_verified_stage15_score(
            explicit.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        );
        let instruction = &lowered.score().unwrap().instructions[0];
        assert_eq!(instruction.color, Color::Red, "{source}");
        assert_eq!(instruction.weight, Weight::Pen, "{source}");
        assert_eq!(instruction.style, LineStyle::Solid, "{source}");
        assert_eq!(instruction.filled, filled, "{source}");
    }
}

#[test]
fn unsupported_instruction_among_independent_instructions_never_yields_partial_score() {
    let result = stage15(
        concat!(
            "place red circle at center. ",
            "place two blue square at horizontal 0.7, vertical 0.5."
        ),
        ResolvedInstructionLanguage::En,
    );
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
    );
    assert!(lowered.score().is_none());
    assert!(
        lowered
            .gaps()
            .contains(&ScoreFieldGap::RepeatedCountUnsupported { value: 2 })
    );
}

#[test]
fn qualitative_count_remains_a_typed_hole_instead_of_becoming_one() {
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(
            "place many red circle at horizontal 0.5, vertical 0.5.",
            ResolvedInstructionLanguage::En,
            Vec::new(),
        )
        .unwrap(),
        &[],
        None,
        LIMITS,
    );
    assert!(!compilation.holes.is_empty());
    assert!(stage15_transformation_input(&compilation).is_err());
}

#[test]
fn incomplete_conflicting_and_relative_numeric_geometry_fail_as_typed_compiler_issues() {
    for (source, expected_kind) in [
        (
            "place one red pen solid empty circle with radius 0.1 diameter 0.2 at horizontal 0.5, vertical 0.5.",
            "conflicting_explicit_geometries",
        ),
        (
            "place one red pen solid empty ellipse with width 0.2 at horizontal 0.5, vertical 0.5.",
            "incomplete_numeric_geometry",
        ),
        (
            "place one red pen solid empty circle with radius 0.1 at horizontal 0.5.",
            "incomplete_numeric_position",
        ),
        (
            "place one small red pen solid empty circle with radius 0.1 at horizontal 0.5, vertical 0.5.",
            "conflicting_relative_and_explicit_geometry",
        ),
        (
            "circle square radius 0.1 horizontal 0.5 vertical 0.5.",
            "ambiguous_entity_ownership",
        ),
        ("circle 0.5.", "unowned_exact_decimal"),
    ] {
        let compilation = compile_typed_ddl(
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .unwrap(),
            &[],
            None,
            LIMITS,
        );
        assert!(
            compilation
                .conflicts
                .iter()
                .any(|conflict| conflict.kind == expected_kind)
                || compilation
                    .blocking_diagnostics
                    .iter()
                    .any(|diagnostic| diagnostic.kind == expected_kind),
            "{source}: conflicts={:?}; blocking={:?}",
            compilation.conflicts,
            compilation.blocking_diagnostics
        );
        assert!(
            stage15_transformation_input(&compilation).is_err(),
            "{source}"
        );
    }
}

#[test]
fn eligibility_rejects_partial_repeated_and_invalid_geometry_without_partial_score() {
    for (source, expected_primitive, expected_gap) in [
        (
            "place one red pen solid empty triangle at horizontal 0.5, vertical 0.5.",
            Primitive::Triangle,
            ScoreFieldGap::MissingExplicitGeometry,
        ),
        (
            "place one pen solid empty circle with radius 0.1 at horizontal 0.5, vertical 0.5.",
            Primitive::Circle,
            ScoreFieldGap::MissingResolvedPaletteContext,
        ),
        (
            "place zero red pen solid empty circle at horizontal 0.5, vertical 0.5.",
            Primitive::Circle,
            ScoreFieldGap::ExactCountZero { value: 0 },
        ),
        (
            "place 4294967295 red pen solid empty circle with radius 0.1 at horizontal 0.5, vertical 0.5.",
            Primitive::Circle,
            ScoreFieldGap::RepeatedCountUnsupported { value: u32::MAX },
        ),
        (
            "place one red pen solid empty circle with radius 0.1 at horizontal 1.1, vertical 0.5.",
            Primitive::Circle,
            ScoreFieldGap::PositionOutOfRange,
        ),
        (
            "place one red pen solid empty circle with radius 0.0 at horizontal 0.5, vertical 0.5.",
            Primitive::Circle,
            ScoreFieldGap::NonPositiveDimension,
        ),
        (
            "place one red pen solid empty circle with radius -1 at horizontal 0.5, vertical 0.5.",
            Primitive::Circle,
            ScoreFieldGap::NonPositiveDimension,
        ),
        (
            "place one red pen solid empty circle with radius 0.2 at horizontal 0.1, vertical 0.5.",
            Primitive::Circle,
            ScoreFieldGap::GeometryExtentOutOfBounds,
        ),
        (
            "place one red pen solid empty circle radius 0.1 at left-edge.",
            Primitive::Circle,
            ScoreFieldGap::UnsupportedNamedPosition,
        ),
        (
            "place one red pen solid empty circle with radius 0.0000000000000000000000000000000000000001 at horizontal 0.5, vertical 0.5.",
            Primitive::Circle,
            ScoreFieldGap::GeometryRepresentationLimit,
        ),
    ] {
        let result = stage15(source, ResolvedInstructionLanguage::En);
        let lowered = lower_verified_stage15_score(
            result.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        );
        assert!(lowered.score().is_none(), "{source}");
        assert_eq!(
            lowered.candidate().instructions()[0].primitive(),
            Some(expected_primitive),
            "{source}"
        );
        if matches!(&expected_gap, ScoreFieldGap::ExactCountZero { .. }) {
            assert_eq!(
                result.original_semantic_document().instructions[0]
                    .entity
                    .quantity
                    .as_ref()
                    .map(|quantity| quantity.value),
                Some(0),
                "{source}: explicit zero must remain semantic evidence"
            );
            assert_eq!(
                lowered.candidate().instructions()[0].exact_count(),
                None,
                "{source}: zero must remain a typed candidate gap"
            );
        } else {
            assert!(
                lowered.candidate().instructions()[0]
                    .exact_count()
                    .is_some(),
                "{source}: existing count evidence must survive failed actual lowering"
            );
        }
        assert!(
            lowered.gaps().contains(&expected_gap),
            "{source}: {:?}",
            lowered.gaps()
        );
    }
}

#[test]
fn canonical_eight_primitives_map_one_to_one_and_unknown_identity_fails_closed() {
    for (id, expected) in [
        ("line", Primitive::Line),
        ("circle", Primitive::Circle),
        ("ellipse", Primitive::Ellipse),
        ("triangle", Primitive::Triangle),
        ("square", Primitive::Square),
        ("polygon", Primitive::Polygon),
        ("arc", Primitive::Arc),
        ("cloudform", Primitive::Cloudform),
    ] {
        let result = stage15(id, ResolvedInstructionLanguage::En);
        let candidate = lower_verified_stage15_view(result.verified_effective_view());
        assert_eq!(candidate.schema_id(), SCORE_FIELD_CANDIDATE_SCHEMA_ID);
        assert_eq!(candidate.instructions().len(), 1, "{id}");
        let instruction = &candidate.instructions()[0];
        assert_eq!(instruction.source_instruction_index(), 0, "{id}");
        assert_eq!(instruction.primitive(), Some(expected), "{id}");
        assert_eq!(instruction.exact_count(), None, "{id}");
        assert_eq!(instruction.relative_scale(), None, "{id}");
        assert!(instruction.gaps().is_empty(), "{id}");
    }

    for identity in [
        SemanticIdentity {
            category: "shape".to_owned(),
            id: "unknown".to_owned(),
        },
        SemanticIdentity {
            category: "place".to_owned(),
            id: "circle".to_owned(),
        },
    ] {
        let error = score_primitive_from_semantic_identity(&identity).unwrap_err();
        assert_eq!(error.category(), identity.category);
        assert_eq!(error.id(), identity.id);
    }
}

#[test]
fn ja_and_en_meaning_have_identical_primitive_count_and_symbolic_size_candidates() {
    for ((ja, en), expected_primitive, expected_count, expected_scale) in [
        (("円", "circle"), Primitive::Circle, None, None),
        (
            ("八つ 円", "eight circle"),
            Primitive::Circle,
            Some(ExactCountFieldCandidate::Repeated(8)),
            None,
        ),
        (
            ("小さな円", "small circle"),
            Primitive::Circle,
            None,
            Some(CoreModifierValue::Small),
        ),
    ] {
        let ja_result = stage15(ja, ResolvedInstructionLanguage::Ja);
        let en_result = stage15(en, ResolvedInstructionLanguage::En);
        let ja_candidate = lower_verified_stage15_view(ja_result.verified_effective_view());
        let en_candidate = lower_verified_stage15_view(en_result.verified_effective_view());

        assert_eq!(ja_candidate.instructions(), en_candidate.instructions());
        let instruction = &ja_candidate.instructions()[0];
        assert_eq!(instruction.primitive(), Some(expected_primitive));
        assert_eq!(instruction.exact_count(), expected_count);
        assert_eq!(instruction.relative_scale(), expected_scale);
        assert!(instruction.gaps().is_empty());
    }
}

#[test]
fn exact_count_boundaries_are_lossless_and_never_clamped() {
    for (value, expected) in [
        (1_u64, ExactCountFieldCandidate::Single),
        (8, ExactCountFieldCandidate::Repeated(8)),
        (233, ExactCountFieldCandidate::Repeated(233)),
        (240, ExactCountFieldCandidate::Repeated(240)),
        (
            u64::from(u32::MAX),
            ExactCountFieldCandidate::Repeated(u32::MAX),
        ),
    ] {
        let result = stage15(&format!("{value} circle"), ResolvedInstructionLanguage::En);
        let candidate = lower_verified_stage15_view(result.verified_effective_view());
        let instruction = &candidate.instructions()[0];
        assert_eq!(instruction.exact_count(), Some(expected), "{value}");
        assert_eq!(instruction.exact_count().unwrap().value(), value as u32);
        assert!(instruction.gaps().is_empty(), "{value}");
    }

    for (value, expected_gap) in [
        (0_u64, ScoreFieldGap::ExactCountZero { value: 0 }),
        (
            u64::from(u32::MAX) + 1,
            ScoreFieldGap::ExactCountExceedsScoreRange {
                value: u64::from(u32::MAX) + 1,
            },
        ),
    ] {
        let result = stage15(&format!("{value} circle"), ResolvedInstructionLanguage::En);
        let candidate = lower_verified_stage15_view(result.verified_effective_view());
        let instruction = &candidate.instructions()[0];
        assert_eq!(instruction.primitive(), Some(Primitive::Circle));
        assert_eq!(instruction.exact_count(), None, "{value}");
        assert_eq!(instruction.gaps(), [expected_gap], "{value}");
    }
}

#[test]
fn finite_relative_size_intent_is_symbolic_for_the_supported_closed_primitives() {
    for source in [
        "small circle",
        "small ellipse",
        "small square",
        "small cloudform",
    ] {
        let result = stage15(source, ResolvedInstructionLanguage::En);
        let candidate = lower_verified_stage15_view(result.verified_effective_view());
        let instruction = &candidate.instructions()[0];
        assert_eq!(
            instruction.relative_scale(),
            Some(CoreModifierValue::Small),
            "{source}"
        );
        assert!(instruction.gaps().is_empty(), "{source}");
    }

    for (id, primitive) in [
        ("line", Primitive::Line),
        ("triangle", Primitive::Triangle),
        ("polygon", Primitive::Polygon),
        ("arc", Primitive::Arc),
    ] {
        let result = stage15(&format!("small {id}"), ResolvedInstructionLanguage::En);
        let candidate = lower_verified_stage15_view(result.verified_effective_view());
        let instruction = &candidate.instructions()[0];
        assert_eq!(instruction.primitive(), Some(primitive), "{id}");
        assert_eq!(instruction.relative_scale(), None, "{id}");
        assert_eq!(
            instruction.gaps(),
            [ScoreFieldGap::UnsupportedRelativeScalePrimitive { primitive }],
            "{id}"
        );
    }
}

#[test]
fn absent_count_and_size_remain_unspecified() {
    let result = stage15("circle", ResolvedInstructionLanguage::En);
    let candidate = lower_verified_stage15_view(result.verified_effective_view());
    let instruction = &candidate.instructions()[0];

    assert_eq!(instruction.exact_count(), None);
    assert_eq!(instruction.relative_scale(), None);
    assert!(instruction.gaps().is_empty());
}

#[test]
fn mixed_owner_view_keeps_expansion_and_focus_overlay_pending_with_exact_identity_and_order() {
    let definition = center_emit_definition();
    let result = stage15_locked(
        "place one thin pencil line at the center. place circle and Focus.Center at center.",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let original_view = result.verified_effective_view();
    let candidate = lower_verified_stage15_view(original_view);
    let retained_view = candidate.verified_effective_view();

    assert_eq!(
        retained_view.original_semantic_document(),
        result.original_semantic_document()
    );
    assert_eq!(
        retained_view.original_expanded_invocations(),
        result.original_expanded_invocations()
    );
    assert_eq!(
        retained_view.effective_canonical_bytes(),
        result.effective_canonical_bytes()
    );
    assert_eq!(
        retained_view.effective_canonical_digest(),
        result.effective_canonical_digest()
    );
    assert_eq!(retained_view.pending_focus_targets(), result.targets());
    assert_eq!(retained_view.pending_focus_targets().len(), 4);
    assert_eq!(
        candidate.instructions().len(),
        result.original_semantic_document().instructions.len()
    );
    assert!(
        candidate.instructions().iter().any(|instruction| {
            matches!(instruction.gaps(), [ScoreFieldGap::MacroInvocationHead])
        })
    );
    assert!(matches!(
        result.original_semantic_document().instructions[2]
            .entity
            .head,
        SemanticHead::MacroInvocation(_)
    ));
}

fn resolved_palette(
    background: Color,
    background_lightness: f64,
    black_lightness: f64,
    white_lightness: f64,
) -> ResolvedPaletteContext {
    ResolvedPaletteContext::new(
        ResolvedPaletteColor::new(background, [128, 128, 128], background_lightness),
        ResolvedPaletteColor::new(Color::Black, [17, 17, 17], black_lightness),
        ResolvedPaletteColor::new(Color::White, [255, 255, 255], white_lightness),
    )
}

fn stage15(source: &str, language: ResolvedInstructionLanguage) -> Stage15TransformationResult {
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        None,
        LIMITS,
    );
    let input = stage15_transformation_input(&compilation).unwrap_or_else(|error| {
        panic!(
            "{source}: {error:?}; holes={:?}; conflicts={:?}; blocking={:?}",
            compilation.holes, compilation.conflicts, compilation.blocking_diagnostics
        )
    });
    transform_stage15(input, None).unwrap()
}

fn stage15_locked(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> Stage15TransformationResult {
    let locks = definitions.iter().map(lock_for).collect::<Vec<_>>();
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, locks).unwrap(),
        definitions,
        Some(19),
        LIMITS,
    );
    transform_stage15(stage15_transformation_input(&compilation).unwrap(), None).unwrap()
}

fn lock_for(definition: &MacroDefinition) -> MacroLock {
    let identity = definition.identity().unwrap();
    MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap()
}

fn center_emit_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Focus","heading":"Center","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"left_edge"}}}]}"#,
    )
    .unwrap()
}

fn expected_focus_region(focus: FocusRegion) -> [f64; 4] {
    match focus {
        FocusRegion::UpperRight => [0.60, 0.18, 0.82, 0.40],
        FocusRegion::UpperLeft => [0.18, 0.18, 0.40, 0.40],
        FocusRegion::LowerRight => [0.60, 0.60, 0.82, 0.82],
        FocusRegion::LowerLeft => [0.18, 0.60, 0.40, 0.82],
        FocusRegion::UpperEdge => [0.39, 0.07, 0.61, 0.29],
        FocusRegion::RightHalf => [0.61, 0.39, 0.83, 0.61],
    }
}
