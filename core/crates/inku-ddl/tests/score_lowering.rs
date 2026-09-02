use inku_ddl::{
    ExactCountFieldCandidate, ExplicitSmallSizeFieldCandidate, MacroDefinition,
    MacroExpansionLimits, MacroLock, NormalizedDdlDocument, ResolvedInstructionLanguage,
    SCORE_FIELD_CANDIDATE_SCHEMA_ID, ScoreFieldGap, ScoreLoweringCandidate, SemanticHead,
    SemanticIdentity, Stage15TransformationResult, VerifiedStage15EffectiveView, compile_typed_ddl,
    lower_verified_stage15_view, score_primitive_from_semantic_identity,
    stage15_transformation_input, transform_stage15,
};
use inku_score::{Point, Primitive};

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
        assert_eq!(instruction.explicit_small_size(), None, "{id}");
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
fn ja_and_en_meaning_have_identical_primitive_count_and_explicit_small_candidates() {
    for ((ja, en), expected_primitive, expected_count, expected_size) in [
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
            Some(ExplicitSmallSizeFieldCandidate::CircleRadius(0.038)),
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
        assert_eq!(instruction.explicit_small_size(), expected_size);
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
fn explicit_small_maps_only_circle_and_ellipse_exact_score_fields() {
    for (source, expected) in [
        (
            "small circle",
            ExplicitSmallSizeFieldCandidate::CircleRadius(0.038),
        ),
        (
            "small ellipse",
            ExplicitSmallSizeFieldCandidate::EllipseSize(Point::new(0.06, 0.032)),
        ),
    ] {
        let result = stage15(source, ResolvedInstructionLanguage::En);
        let candidate = lower_verified_stage15_view(result.verified_effective_view());
        let instruction = &candidate.instructions()[0];
        assert_eq!(
            instruction.explicit_small_size(),
            Some(expected),
            "{source}"
        );
        assert!(instruction.gaps().is_empty(), "{source}");
    }

    for (id, primitive) in [
        ("line", Primitive::Line),
        ("square", Primitive::Square),
        ("triangle", Primitive::Triangle),
        ("polygon", Primitive::Polygon),
        ("arc", Primitive::Arc),
        ("cloudform", Primitive::Cloudform),
    ] {
        let result = stage15(&format!("small {id}"), ResolvedInstructionLanguage::En);
        let candidate = lower_verified_stage15_view(result.verified_effective_view());
        let instruction = &candidate.instructions()[0];
        assert_eq!(instruction.primitive(), Some(primitive), "{id}");
        assert_eq!(instruction.explicit_small_size(), None, "{id}");
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
    assert_eq!(instruction.explicit_small_size(), None);
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

fn stage15(source: &str, language: ResolvedInstructionLanguage) -> Stage15TransformationResult {
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        None,
        LIMITS,
    );
    transform_stage15(stage15_transformation_input(&compilation).unwrap(), None).unwrap()
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
