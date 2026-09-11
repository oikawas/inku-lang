use inku_ddl::{
    CoreModifierValue, EXPLICIT_SCORE_LOWERING_SCHEMA_ID, ExactCountFieldCandidate, FocusRegion,
    GEOMETRY_RESOLUTION_POLICY_ID, MacroDefinition, MacroExpansionLimits, MacroLock,
    NormalizedDdlDocument, ResolvedInstructionLanguage, SCORE_FIELD_CANDIDATE_SCHEMA_ID,
    ScoreAppearanceField, ScoreAppearanceResolution, ScoreDiagnosticDisposition,
    ScoreDiagnosticOwner, ScoreErrorPolicy, ScoreFieldGap, ScoreInstructionOrigin,
    ScoreLoweringCandidate, ScoreLoweringContext, ScoreLoweringOutcome, ScoreOmissionUnit,
    SemanticHead, SemanticIdentity, SemanticPreviousReference, SemanticRelationKind,
    Stage15TransformationResult, Stage15Variation, Stage15VariationAmplitude,
    VerifiedStage15EffectiveView, compile_typed_ddl, geometry_resolution_policy_digest,
    lower_verified_stage15_score, lower_verified_stage15_score_with_policy,
    lower_verified_stage15_view, score_primitive_from_semantic_identity,
    stage15_transformation_input, transform_stage15,
};
use inku_render::palette::{default_color_map, work_palette_context};
use inku_render::placement::region_in_short_side_units;
use inku_render::planning::{instruction_anchor, resolve_at_region};
use inku_render::types::CanvasSize;

#[test]
fn actual_score_never_drops_layout_direction_on_place() {
    let transformed = stage15(
        "place one red point vertically at center.",
        ResolvedInstructionLanguage::En,
    );
    for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
        let result = lower_verified_stage15_score_with_policy(
            transformed.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            policy,
        );
        assert!(result.score().is_none());
        assert!(result.diagnostics().iter().any(|diagnostic| matches!(
            diagnostic.reason,
            ScoreFieldGap::UnsupportedLayoutDirection { .. }
        )));
    }
}
use inku_score::{
    Canvas, Color, ConnectedPositionAuthority, GroundMaterial, LineStyle, Point, Primitive,
    RelationGap, RelationType, ResolvedPaletteColor, ResolvedPaletteContext, SurfaceTexture,
    Thinness, Weight,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 16,
    max_depth: 16,
    max_evaluation_steps: 1_000,
    max_nodes_per_invocation: 100,
    max_total_nodes: 500,
};

#[test]
fn width_extent_uses_canvas_horizontal_axis_before_rotation() {
    for format in ["square", "wide", "vertical"] {
        let context = ScoreLoweringContext::resolve(format, Color::White).unwrap();
        let (cw, ch) = context.canvas_format().integer_ratio();
        let canvas_width = f64::from(cw) / f64::from(cw.min(ch));
        for (word, fraction) in [("full-width", 1.0), ("half-width", 0.5)] {
            for angle in ["horizontal", "diagonal"] {
                let source = format!("place one red {word} {angle} line at center.");
                let transformed = stage15(&source, ResolvedInstructionLanguage::En);
                let lowered =
                    lower_verified_stage15_score(transformed.verified_effective_view(), context);
                let instruction = &lowered
                    .score()
                    .unwrap_or_else(|| panic!("{source}: {:?}", lowered.diagnostics()))
                    .instructions[0];
                let length =
                    (instruction.to.unwrap().x - instruction.from_.unwrap().x) * canvas_width;
                assert!(
                    (length - canvas_width * fraction).abs() < 1e-10,
                    "{format} {source}"
                );
                assert_eq!(
                    instruction.rotation.unwrap_or(0.0).rem_euclid(90.0),
                    if angle == "diagonal" { 45.0 } else { 0.0 }
                );
            }
            let source = format!("place one red tall {word} ellipse at center.");
            let transformed = stage15(&source, ResolvedInstructionLanguage::En);
            let lowered =
                lower_verified_stage15_score(transformed.verified_effective_view(), context);
            let size = lowered.score().unwrap().instructions[0].size.unwrap();
            assert!((size.x - canvas_width * fraction).abs() < 1e-10);
            assert!((size.y / size.x - 2.0).abs() < 1e-10);
        }
    }
}

#[test]
fn width_extent_measures_each_primitive_reference_contour() {
    for format in ["wide", "vertical"] {
        let context = ScoreLoweringContext::resolve(format, Color::White).unwrap();
        let (cw, ch) = context.canvas_format().integer_ratio();
        let canvas_width = f64::from(cw) / f64::from(cw.min(ch));
        for shape in [
            "circle",
            "point",
            "ellipse",
            "cloudform",
            "square",
            "triangle",
            "pentagon",
            "hexagon",
            "heptagon",
            "octagon",
            "arc",
            "crescent arc",
        ] {
            let source = format!("place one red half-width {shape} at center.");
            let transformed = stage15(&source, ResolvedInstructionLanguage::En);
            let lowered =
                lower_verified_stage15_score(transformed.verified_effective_view(), context);
            let instruction = &lowered
                .score()
                .unwrap_or_else(|| panic!("{source}: {:?}", lowered.diagnostics()))
                .instructions[0];
            let extent = match instruction.primitive {
                Primitive::Circle | Primitive::Point => instruction.radius.unwrap() * 2.0,
                Primitive::Polygon => {
                    let sides = instruction.sides.unwrap();
                    let xs = (0..sides)
                        .map(|i| {
                            (-std::f64::consts::FRAC_PI_2
                                + std::f64::consts::TAU * f64::from(i) / f64::from(sides))
                            .cos()
                        })
                        .collect::<Vec<_>>();
                    (xs.iter().copied().fold(f64::NEG_INFINITY, f64::max)
                        - xs.iter().copied().fold(f64::INFINITY, f64::min))
                        * instruction.radius.unwrap()
                }
                Primitive::Arc if instruction.arc_form.is_none() => {
                    2.0 * instruction.radius.unwrap()
                        * ((instruction.angle_start.unwrap() - instruction.angle_end.unwrap())
                            / 2.0)
                            .to_radians()
                            .sin()
                }
                _ => instruction.size.unwrap().x,
            };
            assert!(
                (extent - canvas_width * 0.5).abs() < 1e-10,
                "{source} on {format}: {extent}"
            );
        }
    }
}

#[test]
fn moon_forms_preserve_semicircle_direction_and_filled_reference_crescent() {
    for (form, rotation) in [("semicircle", 0.0), ("waxing", 90.0), ("waning", 270.0)] {
        let source = format!("place one red half-width {form} arc at center.");
        let transformed = stage15(&source, ResolvedInstructionLanguage::En);
        let lowered = lower_verified_stage15_score(
            transformed.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        );
        let instruction = &lowered
            .score()
            .unwrap_or_else(|| panic!("{source}: {:?}", lowered.diagnostics()))
            .instructions[0];
        assert_eq!(instruction.radius, Some(0.25));
        assert!(
            (instruction.angle_start.unwrap() - instruction.angle_end.unwrap() - 180.0).abs()
                < 1e-10
        );
        assert_eq!(instruction.rotation.unwrap_or(0.0), rotation);
        assert!(!instruction.filled);
        assert!(instruction.arc_form.is_none());
    }
    for source in [
        "place one red crescent arc at center.",
        "赤い三日月の弧を中央に置く。",
    ] {
        let language = if source.starts_with("place") {
            ResolvedInstructionLanguage::En
        } else {
            ResolvedInstructionLanguage::Ja
        };
        let transformed = stage15(source, language);
        let lowered = lower_verified_stage15_score(
            transformed.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        );
        let instruction = &lowered
            .score()
            .unwrap_or_else(|| panic!("{source}: {:?}", lowered.diagnostics()))
            .instructions[0];
        assert_eq!(instruction.arc_form, Some(inku_score::ArcForm::Crescent));
        assert!(instruction.filled);
        assert!(
            instruction.radius.is_none()
                && instruction.angle_start.is_none()
                && instruction.position.is_none()
        );
        let size = instruction.size.unwrap();
        assert!((size.x / size.y - inku_score::crescent_reference_aspect_ratio()).abs() < 1e-10);
    }
}

#[test]
fn conflicting_sizes_report_error_and_render_minimum_under_both_policies() {
    for (source, expected_radius, candidate_count) in [
        ("place one small red full-width circle at center.", 0.06, 2),
        (
            "place one red full-width half-width circle at center.",
            0.25,
            2,
        ),
        (
            "place one red circle with radius 0.2 diameter 0.1 at center.",
            0.05,
            2,
        ),
        (
            "place one small red circle with radius 0.2 at center.",
            0.06,
            2,
        ),
        ("place one small large red circle at center.", 0.06, 2),
    ] {
        let transformed = stage15(source, ResolvedInstructionLanguage::En);
        for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
            let lowered = lower_verified_stage15_score_with_policy(
                transformed.verified_effective_view(),
                ScoreLoweringContext::resolve("square", Color::White).unwrap(),
                policy,
            );
            let score = lowered
                .score()
                .unwrap_or_else(|| panic!("{source}: {:?}", lowered.diagnostics()));
            assert!(
                (score.instructions[0].radius.unwrap() - expected_radius).abs() < 1e-10,
                "{source}"
            );
            assert_eq!(lowered.diagnostics().len(), 1, "{source}");
            let diagnostic = &lowered.diagnostics()[0];
            assert_eq!(
                diagnostic.disposition,
                ScoreDiagnosticDisposition::Recovered
            );
            let ScoreDiagnosticOwner::SourceInstruction { spans, .. } = &diagnostic.owner else {
                panic!("unexpected recovery owner")
            };
            assert_eq!(spans.len(), candidate_count);
            let ScoreFieldGap::ConflictingSizeSpecifications {
                candidate_extents,
                effective_extent,
            } = &diagnostic.reason
            else {
                panic!("{:?}", diagnostic.reason)
            };
            assert_eq!(candidate_extents.len(), candidate_count);
            let effective =
                effective_extent.numerator() as f64 / effective_extent.denominator() as f64;
            assert!((effective - expected_radius * 2.0).abs() < 1e-10);
        }
    }
}

#[test]
fn recovered_composition_keeps_original_sizes_and_preserves_explicit_shape_aspect() {
    let source = "place one red large triangle width 0.4 height 0.2 at center.";
    let transformed = stage15(source, ResolvedInstructionLanguage::En);
    for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
        let planned = inku_ddl::plan_verified_stage15_with_policy(
            transformed.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            policy,
        );
        let object = &planned.objects().unwrap()[0];
        assert!(object.explicit_geometry().is_some());
        assert_eq!(object.relative_scale(), Some(CoreModifierValue::Large));
        let inku_ddl::ResolvedGeometryDimensions::Bbox { width, height } = object.dimensions()
        else {
            panic!()
        };
        let value =
            |number: inku_ddl::Rational| number.numerator() as f64 / number.denominator() as f64;
        assert!((value(width) - 0.36).abs() < 1e-10);
        assert!((value(height) - 0.18).abs() < 1e-10);
        assert_eq!(
            planned.diagnostics()[0].disposition,
            ScoreDiagnosticDisposition::Recovered
        );
    }
}

#[test]
fn crescent_numeric_bounds_and_non_size_errors_keep_their_authority() {
    for (source, fits) in [
        (
            "place one red diagonal crescent arc at horizontal 0.5 vertical 0.5.",
            true,
        ),
        (
            "place one red diagonal crescent arc at horizontal 0.01 vertical 0.01.",
            false,
        ),
    ] {
        let transformed = stage15(source, ResolvedInstructionLanguage::En);
        for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
            let lowered = lower_verified_stage15_score_with_policy(
                transformed.verified_effective_view(),
                ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
                policy,
            );
            assert_eq!(
                lowered.score().is_some(),
                fits,
                "{source}: {:?}",
                lowered.diagnostics()
            );
            if fits {
                let instruction = &lowered.score().unwrap().instructions[0];
                assert_eq!(instruction.center, Some(Point::new(0.5, 0.5)));
                assert!(instruction.filled && instruction.arc_form.is_some());
            } else {
                assert!(
                    lowered
                        .diagnostics()
                        .iter()
                        .all(|diagnostic| diagnostic.disposition
                            != ScoreDiagnosticDisposition::Recovered)
                );
            }
        }
    }
    for modifier in ["tall", "regular", "empty", "hatch"] {
        let source = format!("place one red {modifier} crescent arc at center.");
        let transformed = stage15(&source, ResolvedInstructionLanguage::En);
        let lowered = lower_verified_stage15_score(
            transformed.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        );
        assert!(lowered.score().is_none(), "{source}");
        assert!(
            lowered
                .diagnostics()
                .iter()
                .all(|diagnostic| diagnostic.disposition != ScoreDiagnosticDisposition::Recovered)
        );
    }
}

#[test]
fn shared_shape_constraints_reach_actual_score() {
    for (source, language) in [
        (
            "place one red triangle at center.",
            ResolvedInstructionLanguage::En,
        ),
        (
            "横長の赤い四角を中央に置く。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "place one red polygon at center.",
            ResolvedInstructionLanguage::En,
        ),
        (
            "place one red equilateral triangle at center.",
            ResolvedInstructionLanguage::En,
        ),
        (
            "赤い正三角形を中央に置く。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "place one red hexagon at center.",
            ResolvedInstructionLanguage::En,
        ),
        ("赤い六角形を中央に置く。", ResolvedInstructionLanguage::Ja),
        (
            "place one red sides 6 polygon at center.",
            ResolvedInstructionLanguage::En,
        ),
    ] {
        let transformed = stage15(source, language);
        let lowered = lower_verified_stage15_score(
            transformed.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        );
        assert_eq!(
            lowered.outcome(),
            ScoreLoweringOutcome::Complete,
            "{source}: {:?}",
            lowered.gaps()
        );
        assert_eq!(lowered.score().unwrap().instructions.len(), 1);
    }
}

#[test]
fn repeated_placement_policy_keeps_object_size_and_defaults_eight() {
    let policy: serde_json::Value =
        serde_json::from_slice(inku_ddl::geometry_resolution_policy_canonical_bytes()).unwrap();
    assert_eq!(policy["object_placement"]["repeated_default_count"], 8);
    assert_eq!(
        policy["object_placement"]["size_basis"],
        "canvas_short_edge_independent_of_count"
    );
}

#[test]
fn shared_shape_geometry_preserves_physical_extents_and_exact_rules() {
    for (source, language, primitive, width, height) in [
        (
            "place one red wide rectangle at center.",
            ResolvedInstructionLanguage::En,
            Primitive::Square,
            0.24,
            0.12,
        ),
        (
            "横に長い赤い四角形を中央に置く。",
            ResolvedInstructionLanguage::Ja,
            Primitive::Square,
            0.24,
            0.12,
        ),
        (
            "細長い赤い三角形を中央に置く。",
            ResolvedInstructionLanguage::Ja,
            Primitive::Triangle,
            0.12,
            0.24,
        ),
        (
            "place one red equilateral triangle side length 0.24 at center.",
            ResolvedInstructionLanguage::En,
            Primitive::Triangle,
            0.24,
            0.24 * 3.0_f64.sqrt() / 2.0,
        ),
        (
            "一辺0.24の赤い正三角形を中央に置く。",
            ResolvedInstructionLanguage::Ja,
            Primitive::Triangle,
            0.24,
            0.24 * 3.0_f64.sqrt() / 2.0,
        ),
        (
            "place one large red equilateral triangle at center.",
            ResolvedInstructionLanguage::En,
            Primitive::Triangle,
            0.36,
            0.36 * 3.0_f64.sqrt() / 2.0,
        ),
        (
            "赤い正方形を中央に置く。",
            ResolvedInstructionLanguage::Ja,
            Primitive::Square,
            0.24,
            0.24,
        ),
        (
            "place one red tall ellipse at center.",
            ResolvedInstructionLanguage::En,
            Primitive::Ellipse,
            0.12,
            0.24,
        ),
    ] {
        let transformed = stage15(source, language);
        for canvas in ["square", "wide", "oban"] {
            let lowered = lower_verified_stage15_score(
                transformed.verified_effective_view(),
                ScoreLoweringContext::resolve(canvas, Color::White).unwrap(),
            );
            let instruction = &lowered
                .score()
                .unwrap_or_else(|| panic!("{source}: {:?}", lowered.gaps()))
                .instructions[0];
            assert_eq!(instruction.primitive, primitive);
            let size = instruction.size.unwrap();
            assert!(
                (size.x - width).abs() < 1e-12 && (size.y - height).abs() < 1e-12,
                "{source}: {size:?}"
            );
            assert!(instruction.filled);
        }
    }
    for (word, sides) in [
        ("polygon", 5),
        ("pentagon", 5),
        ("hexagon", 6),
        ("heptagon", 7),
        ("octagon", 8),
    ] {
        let transformed = stage15(
            &format!("place one red {word} radius 0.1 at center."),
            ResolvedInstructionLanguage::En,
        );
        let lowered = lower_verified_stage15_score(
            transformed.verified_effective_view(),
            ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
        );
        let instruction = &lowered.score().unwrap().instructions[0];
        assert_eq!(instruction.primitive, Primitive::Polygon);
        assert_eq!(instruction.sides, Some(sides));
        assert_eq!(instruction.radius, Some(0.1));
    }
}

#[test]
fn shared_shape_macro_parameters_and_locals_use_the_same_consumer() {
    use serde_json::json;
    for (shape, field, schema, value, caller, ordinary) in [
        (
            "triangle",
            "shape_form",
            json!({"type":"semantic_ref","category":"shape_form"}),
            json!({"expr":"semantic_ref","category":"shape_form","id":"regular"}),
            "regular",
            "equilateral triangle",
        ),
        (
            "square",
            "proportion_aspect",
            json!({"type":"semantic_ref","category":"ratio"}),
            json!({"expr":"semantic_ref","category":"ratio","id":"wide"}),
            "wide",
            "wide rectangle",
        ),
        (
            "polygon",
            "sides",
            json!({"type":"integer"}),
            json!({"expr":"integer","value":6}),
            "sides 6",
            "hexagon",
        ),
    ] {
        for route in ["literal", "parameter", "local"] {
            let mut fields = json!({
                "shape":{"expr":"semantic_ref","category":"shape","id":shape},
                "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
                "place":{"expr":"semantic_ref","category":"place","id":"center"},
                "color":{"expr":"semantic_ref","category":"color","id":"red"}
            });
            fields[field] = match route {
                "parameter" => json!({"expr":"parameter","name":"input"}),
                "local" => json!({"expr":"local","name":"input"}),
                _ => value.clone(),
            };
            let emit = json!({"op":"emit","binding":null,"fields":fields});
            let body = if route == "local" {
                json!([{"op":"vary","binding":"input","domain":"constraint","choices":[value],"range":null,"body":[emit]}])
            } else {
                json!([emit])
            };
            let definition = MacroDefinition::from_json(&json!({"schema":"inku.macro-definition.v1","namespace":"Shape","heading":"Mark","version":"1.0.0","parameters": if route == "parameter" { json!({"input":schema}) } else {json!({})},"components":{},"body":body}).to_string()).unwrap();
            let source = if route == "parameter" {
                format!("Shape.Mark {caller}")
            } else {
                "Shape.Mark".to_owned()
            };
            for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
                let invalid_source = if route == "parameter" {
                    "Shape.Mark".to_owned()
                } else {
                    format!("Shape.Mark {caller}")
                };
                let execution = inku_ddl::compile_ddl_to_score(
                    NormalizedDdlDocument::new(
                        &invalid_source,
                        ResolvedInstructionLanguage::En,
                        vec![lock_for(&definition)],
                    )
                    .unwrap(),
                    &[definition.clone()],
                    Some(19),
                    LIMITS,
                    ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
                    None,
                    policy,
                );
                assert!(
                    execution.score().is_none(),
                    "missing/undeclared {field}/{route}: {invalid_source}"
                );
            }
            let generated = stage15_locked(&source, ResolvedInstructionLanguage::En, &[definition]);
            let ordinary = stage15(
                &format!("place one red {ordinary} at center."),
                ResolvedInstructionLanguage::En,
            );
            let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
            let generated =
                lower_verified_stage15_score(generated.verified_effective_view(), context);
            let ordinary =
                lower_verified_stage15_score(ordinary.verified_effective_view(), context);
            let mut left = generated
                .score()
                .unwrap_or_else(|| panic!("{field}/{route}: {:?}", generated.gaps()))
                .instructions[0]
                .clone();
            let mut right = ordinary.score().unwrap().instructions[0].clone();
            left.at = None;
            right.at = None;
            assert_eq!(left, right, "{field}/{route}");
        }
    }
}

#[test]
fn shared_shape_numeric_anchors_and_conflicts_are_never_repaired() {
    let source = "place one red triangle width 0.4 height 0.2 at horizontal 0.5 vertical 0.5.";
    let transformed = stage15(source, ResolvedInstructionLanguage::En);
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let lowered = lower_verified_stage15_score(transformed.verified_effective_view(), context);
    let instruction = &lowered.score().unwrap().instructions[0];
    assert_eq!(instruction.size, Some(Point::new(0.4, 0.2)));
    let (w, h) = context.canvas_format().integer_ratio();
    let short = f64::from(w.min(h));
    let position = instruction.position.unwrap();
    assert!((position.x + 0.2 * short / f64::from(w) - 0.5).abs() < 1e-12);
    assert!((position.y + 0.1 * short / f64::from(h) - 0.5).abs() < 1e-12);
    for body in ["triangle width 0.4 height 0.2", "hexagon radius 0.1"] {
        let source = format!("place one red vertical {body} at horizontal 0.5 vertical 0.5.");
        let transformed = stage15(&source, ResolvedInstructionLanguage::En);
        let lowered = lower_verified_stage15_score(transformed.verified_effective_view(), context);
        assert_eq!(
            lowered.score().unwrap().instructions[0].rotation,
            Some(90.0)
        );
    }
    for body in [
        "wide equilateral triangle",
        "regular square width 0.4 height 0.2",
        "tall rectangle width 0.4 height 0.2",
        "sides 9 polygon",
        "equilateral triangle width 0.24 height 0.2078460969",
        "triangle width 0.4 height 0.2 at horizontal 0.01 vertical 0.01",
        "vertical triangle width 0.4 height 0.2 at horizontal 0.01 vertical 0.01",
        "hexagon radius 0.4 at horizontal 0.01 vertical 0.01",
        "vertical hexagon radius 0.4 at horizontal 0.01 vertical 0.01",
    ] {
        let source = format!(
            "place one red {body}{}.",
            if body.contains(" at ") {
                ""
            } else {
                " at center"
            }
        );
        for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
            let result = inku_ddl::compile_ddl_to_score(
                NormalizedDdlDocument::new(&source, ResolvedInstructionLanguage::En, vec![])
                    .unwrap(),
                &[],
                None,
                LIMITS,
                context,
                None,
                policy,
            );
            assert!(result.score().is_none(), "{source}: {policy:?}");
            assert!(
                !result.upstream_diagnostics().is_empty()
                    || !result.downstream_diagnostics().is_empty()
            );
        }
    }
}

#[test]
fn explicit_left_edge_reaches_actual_score() {
    let result = stage15(
        "place one red pen solid empty circle radius 0.1 at left-edge.",
        ResolvedInstructionLanguage::En,
    );
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
    );
    assert_eq!(lowered.outcome(), ScoreLoweringOutcome::Complete);
    let score = lowered
        .score()
        .expect("explicit left-edge must reach Score");
    assert_eq!(
        score.instructions[0].at.as_ref().unwrap().region,
        [0.0, 0.0, 0.1, 1.0]
    );
}

#[test]
fn natural_japanese_named_positions_reach_actual_score() {
    for source in ["上に、赤い円をひとつ置く。", "隅に、赤い円をひとつ置く。"]
    {
        let result = stage15(source, ResolvedInstructionLanguage::Ja);
        let lowered = lower_verified_stage15_score(
            result.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        );
        assert_eq!(
            lowered.outcome(),
            ScoreLoweringOutcome::Complete,
            "{source}: {:?}",
            lowered.gaps()
        );
    }
}

#[test]
fn explicit_named_table_and_seven_shape_geometry_share_one_builder() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    for (place, expected) in [
        ("top", [0.0, 0.0, 1.0, 1.0 / 3.0]),
        ("bottom", [0.0, 2.0 / 3.0, 1.0, 1.0]),
        ("left-edge", [0.0, 0.0, 0.1, 1.0]),
        ("right-edge", [0.9, 0.0, 1.0, 1.0]),
        ("top-edge", [0.0, 0.0, 1.0, 0.1]),
        ("bottom-edge", [0.0, 0.9, 1.0, 1.0]),
    ] {
        let source = format!("place one red circle at {place}.");
        let result = stage15(&source, ResolvedInstructionLanguage::En);
        assert!(result.targets().is_empty());
        let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
        assert_eq!(
            lowered.outcome(),
            ScoreLoweringOutcome::Complete,
            "{source}: {:?}",
            lowered.gaps()
        );
        assert_eq!(
            lowered.score().unwrap().instructions[0]
                .at
                .as_ref()
                .unwrap()
                .region,
            expected
        );
    }
    for (body, place) in [
        ("circle radius 0.8", "left-edge"),
        ("large ellipse", "top"),
        ("cloudform width 0.4, height 0.2", "bottom"),
        ("vertical square", "right-edge"),
        ("line length 0.4", "top-edge"),
        ("arc chord 0.4, sagitta 0.1", "bottom-edge"),
        ("point", "corner"),
    ] {
        let mut instructions = Vec::new();
        for location in ["center", place] {
            let source = format!("place one red {body} at {location}.");
            let result = stage15(&source, ResolvedInstructionLanguage::En);
            let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
            assert_eq!(
                lowered.outcome(),
                ScoreLoweringOutcome::Complete,
                "{source}: {:?}",
                lowered.gaps()
            );
            let mut instruction = lowered.score().unwrap().instructions[0].clone();
            instruction.at = None;
            instructions.push(instruction);
        }
        assert_eq!(
            instructions[0], instructions[1],
            "{body}: dimensions and angle remain authored"
        );
    }
}

#[test]
fn declared_and_literal_macro_positions_match_ordinary_and_keep_generated_owners() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    for (word, identity) in [
        ("top", "top"),
        ("left-edge", "left_edge"),
        ("corner", "corner"),
    ] {
        let parameter = parameter_bound_definition();
        let generated = stage15_locked(
            &format!("Param.One red place {word} pencil"),
            ResolvedInstructionLanguage::En,
            &[parameter.clone()],
        );
        let mut literal = serde_json::to_value(&parameter).unwrap();
        literal["parameters"] = serde_json::json!({});
        let fields = &mut literal["body"][0]["fields"];
        for (key, category, id) in [
            ("color", "color", "red"),
            ("movement", "movement", "place"),
            ("place", "place", identity),
        ] {
            fields[key] = serde_json::json!({"expr":"semantic_ref", "category":category, "id":id});
        }
        let literal = MacroDefinition::from_json(&literal.to_string()).unwrap();
        let literal = stage15_locked("Param.One", ResolvedInstructionLanguage::En, &[literal]);
        let direct = stage15_seeded(
            &format!("place one red circle at {word}."),
            ResolvedInstructionLanguage::En,
            Some(19),
        );
        let mut scores = Vec::new();
        for result in [&generated, &literal, &direct] {
            assert!(
                result.targets().is_empty(),
                "noncenter must never get a synthetic focus"
            );
            let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
            assert_eq!(
                lowered.outcome(),
                ScoreLoweringOutcome::Complete,
                "{word}: {:?}",
                lowered.gaps()
            );
            let again = lower_verified_stage15_score(result.verified_effective_view(), context);
            assert_eq!(lowered.score(), again.score());
            if !std::ptr::eq(result, &direct) {
                assert!(matches!(
                    &lowered.instruction_origins()[0],
                    ScoreInstructionOrigin::MacroEmit { .. }
                ));
            }
            let mut instruction = lowered.score().unwrap().instructions[0].clone();
            if identity == "corner" {
                assert_corner_region(instruction.at.as_ref().unwrap().region);
                instruction.at = None; // Different logical occurrence kinds need not select the same corner.
            }
            scores.push(instruction);
        }
        assert_eq!(scores[0], scores[1]);
        assert_eq!(scores[1], scores[2]);
    }
}

fn assert_corner_region(region: [f64; 4]) {
    assert!(
        [
            [0.0, 0.0, 0.2, 0.2],
            [0.8, 0.0, 1.0, 0.2],
            [0.0, 0.8, 0.2, 1.0],
            [0.8, 0.8, 1.0, 1.0],
        ]
        .contains(&region)
    );
}

#[test]
fn noncenter_macro_relation_stays_unsupported_in_both_modes() {
    let context = ScoreLoweringContext::resolve("square", Color::White).unwrap();
    for kind in ["connected", "touching"] {
        for noncenter_index in [0, 1] {
            let mut definition = serde_json::to_value(complete_flat_emit_definition()).unwrap();
            for (index, binding) in ["first", "second"].into_iter().enumerate() {
                definition["body"][index]["binding"] = serde_json::json!(binding);
                definition["body"][index]["fields"]["shape"]["id"] = serde_json::json!("line");
            }
            definition["body"][noncenter_index]["fields"]["place"]["id"] = serde_json::json!("top");
            definition["body"].as_array_mut().unwrap().push(
                serde_json::json!({"op":"relation", "kind":kind, "from":"first", "to":"second"}),
            );
            let definition = MacroDefinition::from_json(&definition.to_string()).unwrap();
            let result =
                stage15_locked("Draw.Pair", ResolvedInstructionLanguage::En, &[definition]);
            for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
                let lowered = lower_verified_stage15_score_with_policy(
                    result.verified_effective_view(),
                    context,
                    policy,
                );
                assert!(
                    lowered
                        .gaps()
                        .contains(&ScoreFieldGap::UnsupportedMacroRelation)
                );
                if policy == ScoreErrorPolicy::Stop {
                    assert!(lowered.score().is_none());
                } else {
                    assert_eq!(lowered.score().unwrap().instructions.len(), 1);
                    assert!(
                        matches!(&lowered.instruction_origins()[0], ScoreInstructionOrigin::MacroEmit { provenance, .. } if provenance.generated_ordinal == 0)
                    );
                    assert!(lowered.diagnostics().iter().any(|d| matches!(
                        &d.disposition,
                        ScoreDiagnosticDisposition::Omitted {
                            unit: ScoreOmissionUnit::MacroEmit {
                                generated_ordinal: 1,
                                ..
                            },
                            ..
                        }
                    )));
                }
            }
        }
    }
}

#[test]
fn corner_uses_original_meaning_and_occurrence_not_source_or_variation() {
    let context = ScoreLoweringContext::resolve("square", Color::White).unwrap();
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(
            "place one red circle at center. place one blue circle at corner.",
            ResolvedInstructionLanguage::En,
            Vec::new(),
        )
        .unwrap(),
        &[],
        Some(41),
        LIMITS,
    );
    let baseline =
        transform_stage15(stage15_transformation_input(&compilation).unwrap(), None).unwrap();
    let varied = transform_stage15(
        stage15_transformation_input(&compilation).unwrap(),
        Some(Stage15Variation {
            amplitude: Stage15VariationAmplitude::Large,
            seed: 99,
        }),
    )
    .unwrap();
    let a = lower_verified_stage15_score(baseline.verified_effective_view(), context);
    let b = lower_verified_stage15_score(varied.verified_effective_view(), context);
    assert_eq!(
        a.score().unwrap().instructions[1],
        b.score().unwrap().instructions[1]
    );
    for seed in [None, Some(0), Some(1), Some(19)] {
        let inline = stage15_seeded("赤い円を隅に置く。", ResolvedInstructionLanguage::Ja, seed);
        let continued = stage15_seeded(
            "円を隅に置く。円は赤い。",
            ResolvedInstructionLanguage::Ja,
            seed,
        );
        assert_eq!(
            inline.original_pre_expansion_digest(),
            continued.original_pre_expansion_digest()
        );
        let a = lower_verified_stage15_score(inline.verified_effective_view(), context);
        let b = lower_verified_stage15_score(continued.verified_effective_view(), context);
        assert_eq!(a.outcome(), ScoreLoweringOutcome::Complete);
        assert_eq!(a.score(), b.score());
        assert_corner_region(
            a.score().unwrap().instructions[0]
                .at
                .as_ref()
                .unwrap()
                .region,
        );
    }
    let result = stage15(
        "place two red circle at top. place one red circle at corner.",
        ResolvedInstructionLanguage::En,
    );
    let lowered = lower_verified_stage15_score_with_policy(
        result.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(lowered.score().unwrap().instructions.len(), 1);
    assert!(matches!(
        &lowered.instruction_origins()[0],
        ScoreInstructionOrigin::SourceInstruction {
            instruction_index: 1
        }
    ));
    assert_corner_region(
        lowered.score().unwrap().instructions[0]
            .at
            .as_ref()
            .unwrap()
            .region,
    );
}

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
fn endpoint_family_normal_line_reaches_actual_score() {
    let result = stage15(
        "place one red pen solid line at horizontal 0.5, vertical 0.5.",
        ResolvedInstructionLanguage::En,
    );
    let compilation = result.original_semantic_document();
    assert_eq!(compilation.instructions.len(), 1);
    assert!(matches!(
        compilation.instructions[0].entity.head,
        SemanticHead::Primitive(_)
    ));

    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );
    let score = lowered
        .score()
        .expect("a valid normal Line must reach an actual Score");
    assert_eq!(lowered.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(score.instructions.len(), 1);
    assert_eq!(score.instructions[0].primitive, Primitive::Line);
    let line = &score.instructions[0];
    let from = line.from_.unwrap();
    let to = line.to.unwrap();
    assert!((from.x - (0.5 - 0.12 * 20.0 / 47.0)).abs() < 1.0e-15);
    assert!((to.x - (0.5 + 0.12 * 20.0 / 47.0)).abs() < 1.0e-15);
    assert_eq!(from.y, 0.5);
    assert_eq!(to.y, 0.5);
    assert!(!line.filled);
}

#[test]
fn endpoint_family_normal_arc_and_point_reach_independent_actual_score_geometry() {
    let result = stage15(
        concat!(
            "place one blue pen solid arc at horizontal 0.5, vertical 0.5. ",
            "place one black pen solid point at horizontal 0.7, vertical 0.5."
        ),
        ResolvedInstructionLanguage::En,
    );
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );
    assert_eq!(lowered.outcome(), ScoreLoweringOutcome::Complete);
    let instructions = &lowered.score().unwrap().instructions;
    assert_eq!(instructions.len(), 2);

    let arc = &instructions[0];
    assert_eq!(arc.primitive, Primitive::Arc);
    assert_eq!(arc.position, Some(Point::new(0.5, 0.5)));
    assert!((arc.center.unwrap().y - 0.59).abs() < 1.0e-15);
    assert!((arc.radius.unwrap() - 0.15).abs() < 1.0e-15);
    assert!((arc.angle_start.unwrap() - 143.13010235415598).abs() < 1.0e-12);
    assert!((arc.angle_end.unwrap() - 36.86989764584402).abs() < 1.0e-12);
    assert!(!arc.filled);

    let point = &instructions[1];
    assert_eq!(point.primitive, Primitive::Point);
    assert_eq!(point.center, Some(Point::new(0.7, 0.5)));
    assert!((point.radius.unwrap() - 0.006).abs() < 1.0e-15);
    assert!(point.filled);
}

#[test]
fn connected_lowering_carries_named_and_numeric_position_authority_explicitly() {
    for (source, expected) in [
        (
            "place one red line at center. place one blue line at center connected to the previous shape.",
            ConnectedPositionAuthority::NamedMovable,
        ),
        (
            "place one red line at horizontal 0.2, vertical 0.3. place one blue line at horizontal 0.4, vertical 0.3 connected to the previous shape.",
            ConnectedPositionAuthority::NumericFixed,
        ),
    ] {
        let result = stage15(source, ResolvedInstructionLanguage::En);
        let lowered = lower_verified_stage15_score(
            result.verified_effective_view(),
            ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
        );
        assert_eq!(
            lowered.outcome(),
            ScoreLoweringOutcome::Complete,
            "{source}"
        );
        let relation = lowered.score().unwrap().instructions[1]
            .relation
            .as_ref()
            .expect("Connected reaches Score");
        assert_eq!(relation.kind, RelationType::Connected);
        assert_eq!(relation.target_instruction_index, Some(0));
        assert_eq!(relation.position_authority, Some(expected));
    }
}

#[test]
fn endpoint_family_explicit_geometry_and_japanese_point_reach_the_same_typed_lowerer() {
    let en = stage15(
        concat!(
            "place one red line with length 0.4 at horizontal 0.5, vertical 0.3. ",
            "place one blue arc with chord 0.4, sagitta 0.1 at horizontal 0.5, vertical 0.5. ",
            "place one black point with diameter 0.02 at horizontal 0.7, vertical 0.7."
        ),
        ResolvedInstructionLanguage::En,
    );
    let ja = stage15(
        concat!(
            "画面の横0.5、縦0.3の位置に、長さ0.4の赤い線をひとつ置く。",
            "画面の横0.5、縦0.5の位置に、弦長0.4、矢高0.1の青い弧をひとつ置く。",
            "画面の横0.7、縦0.7の位置に、直径0.02の黒い点をひとつ置く。"
        ),
        ResolvedInstructionLanguage::Ja,
    );
    assert_eq!(
        en.original_pre_expansion_digest(),
        ja.original_pre_expansion_digest()
    );
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let en = lower_verified_stage15_score(en.verified_effective_view(), context);
    let ja = lower_verified_stage15_score(ja.verified_effective_view(), context);
    assert_eq!(en.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(en.score(), ja.score());
    let score = en.score().unwrap();
    assert_eq!(score.instructions[0].primitive, Primitive::Line);
    assert_eq!(score.instructions[1].primitive, Primitive::Arc);
    assert_eq!(score.instructions[2].primitive, Primitive::Point);
    assert!((score.instructions[2].radius.unwrap() - 0.01).abs() < 1.0e-15);
}

#[test]
fn endpoint_family_normal_flat_macro_emit_uses_the_same_effective_defaults() {
    let definition = endpoint_family_emit_definition();
    let macro_result = stage15_locked(
        "Endpoint.Normal!",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let direct_result = stage15(
        concat!(
            "place one red line at center. ",
            "place one blue arc at center. ",
            "place one black point at center."
        ),
        ResolvedInstructionLanguage::En,
    );
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let macro_score = lower_verified_stage15_score(macro_result.verified_effective_view(), context);
    let direct_score =
        lower_verified_stage15_score(direct_result.verified_effective_view(), context);
    assert_eq!(
        macro_score.outcome(),
        ScoreLoweringOutcome::Complete,
        "gaps={:?}; diagnostics={:?}",
        macro_score.gaps(),
        macro_score.diagnostics()
    );
    assert_eq!(direct_score.outcome(), ScoreLoweringOutcome::Complete);
    let macro_instructions = &macro_score.score().unwrap().instructions;
    let direct_instructions = &direct_score.score().unwrap().instructions;
    assert_eq!(macro_instructions.len(), 3);
    for (macro_instruction, direct_instruction) in
        macro_instructions.iter().zip(direct_instructions)
    {
        assert_eq!(macro_instruction.primitive, direct_instruction.primitive);
        assert_eq!(macro_instruction.radius, direct_instruction.radius);
        assert_eq!(macro_instruction.size, direct_instruction.size);
        assert_eq!(
            macro_instruction.angle_start,
            direct_instruction.angle_start
        );
        assert_eq!(macro_instruction.angle_end, direct_instruction.angle_end);
        assert_eq!(macro_instruction.filled, direct_instruction.filled);
        assert_eq!(macro_instruction.style, direct_instruction.style);
        assert_eq!(macro_instruction.weight, direct_instruction.weight);
        assert_eq!(macro_instruction.color, direct_instruction.color);
    }
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
    assert_eq!(instruction.thinness, None);
}

#[test]
fn direct_fine_reaches_actual_score_thinness() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    for (source, language, expected) in [
        (
            "place one thin red circle at center.",
            ResolvedInstructionLanguage::En,
            Thinness::Fine,
        ),
        (
            "中心に細い赤い円をひとつ置く。",
            ResolvedInstructionLanguage::Ja,
            Thinness::Fine,
        ),
        (
            "place one extra-fine red circle at center.",
            ResolvedInstructionLanguage::En,
            Thinness::ExtraFine,
        ),
        (
            "中心にごく細い赤い円をひとつ置く。",
            ResolvedInstructionLanguage::Ja,
            Thinness::ExtraFine,
        ),
    ] {
        let result = stage15(source, language);
        let stop = lower_verified_stage15_score(result.verified_effective_view(), context);
        let continued = lower_verified_stage15_score_with_policy(
            result.verified_effective_view(),
            context,
            ScoreErrorPolicy::OmitAndContinue,
        );

        assert_eq!(stop.outcome(), ScoreLoweringOutcome::Complete, "{source}");
        assert!(
            stop.diagnostics().is_empty(),
            "{source}: {:?}",
            stop.diagnostics()
        );
        assert_eq!(stop.score(), continued.score(), "{source}");
        assert_eq!(
            stop.score().unwrap().instructions[0].thinness,
            Some(expected),
            "{source}"
        );
    }
}

#[test]
fn direct_horizontal_angle_reaches_actual_score_rotation() {
    let result = stage15(
        "place one red horizontal circle at center.",
        ResolvedInstructionLanguage::En,
    );
    assert_eq!(
        result.original_semantic_document().instructions[0]
            .entity
            .angle
            .as_ref()
            .map(|angle| angle.identity.id.as_str()),
        Some("horizontal")
    );

    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );

    assert_eq!(lowered.outcome(), ScoreLoweringOutcome::Complete);
    assert!(lowered.gaps().is_empty(), "{:?}", lowered.gaps());
    assert_eq!(lowered.score().unwrap().instructions[0].rotation, Some(0.0));
}

#[test]
fn seeded_angles_are_reproducible_bilingual_and_stage15_variation_invariant() {
    let source = "place one red diagonal circle at center.";
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new()).unwrap(),
        &[],
        Some(41),
        LIMITS,
    );
    let baseline =
        transform_stage15(stage15_transformation_input(&compilation).unwrap(), None).unwrap();
    let varied = transform_stage15(
        stage15_transformation_input(&compilation).unwrap(),
        Some(Stage15Variation {
            amplitude: Stage15VariationAmplitude::Large,
            seed: 99,
        }),
    )
    .unwrap();
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let baseline_lowered =
        lower_verified_stage15_score(baseline.verified_effective_view(), context);
    let varied_lowered = lower_verified_stage15_score(varied.verified_effective_view(), context);
    let baseline_score = baseline_lowered.score().unwrap();
    let varied_score = varied_lowered.score().unwrap();
    let rotation = baseline_score.instructions[0].rotation.unwrap();
    assert!([45.0, 135.0, 225.0, 315.0].contains(&rotation));
    assert_eq!(varied_score.instructions[0].rotation, Some(rotation));

    let japanese = stage15_seeded(
        "赤い左上がりの円を中心に置く。",
        ResolvedInstructionLanguage::Ja,
        Some(41),
    );
    let japanese = lower_verified_stage15_score(japanese.verified_effective_view(), context);
    assert_eq!(japanese.outcome(), ScoreLoweringOutcome::Complete);
    assert!((203.0..=217.0).contains(&japanese.score().unwrap().instructions[0].rotation.unwrap()));

    let english = stage15_seeded(
        "place one red left-falling circle at center.",
        ResolvedInstructionLanguage::En,
        Some(41),
    );
    assert_eq!(
        english.original_semantic_document().instructions[0]
            .entity
            .angle
            .as_ref()
            .map(|angle| angle.identity.id.as_str()),
        Some("left_falling")
    );
    let english = lower_verified_stage15_score(english.verified_effective_view(), context);
    assert_eq!(english.outcome(), ScoreLoweringOutcome::Complete);
    assert!((143.0..=157.0).contains(&english.score().unwrap().instructions[0].rotation.unwrap()));
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
fn direct_not_touching_relation_reaches_the_actual_score() {
    for (source, language) in [
        (
            concat!(
                "place one red circle at center. ",
                "place one blue square at center not touching the previous shape."
            ),
            ResolvedInstructionLanguage::En,
        ),
        (
            "赤い円を中心に置く。\n前の形に触れない\n青い四角を中心に置く。",
            ResolvedInstructionLanguage::Ja,
        ),
    ] {
        let result = stage15(source, language);
        let current = &result.original_semantic_document().instructions[1];
        assert_eq!(
            current
                .position
                .as_ref()
                .map(|position| position.identity.id.as_str()),
            Some("center")
        );
        assert!(current.relation.is_some());

        let lowered = lower_verified_stage15_score(
            result.verified_effective_view(),
            ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
        );

        assert_eq!(
            lowered.outcome(),
            ScoreLoweringOutcome::Complete,
            "{source}"
        );
        let score = lowered
            .score()
            .expect("supported direct relation reaches Score");
        assert_eq!(score.instructions.len(), 2);
        assert!(score.instructions[1].at.is_some());
        let relation = score.instructions[1]
            .relation
            .as_ref()
            .expect("current instruction keeps its explicit relation");
        assert_eq!(relation.kind, RelationType::NotTouching);
        assert_eq!(relation.gap, RelationGap::Medium);
    }
}

#[test]
fn direct_between_relation_preserves_focus_geometry_and_origins() {
    let source = concat!(
        "place one red circle at horizontal 0.2, vertical 0.3. ",
        "place one blue ellipse at center. ",
        "place one small green square at center between the previous two."
    );
    let result = stage15(source, ResolvedInstructionLanguage::En);
    let expected_region = expected_focus_region(result.targets()[1].effective_focus);
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );

    assert_eq!(lowered.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(
        lowered.instruction_origins(),
        &[
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 0
            },
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 1
            },
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 2
            },
        ]
    );
    let score = lowered.score().unwrap();
    assert_eq!(score.instructions[0].center, Some(Point::new(0.2, 0.3)));
    let current = &score.instructions[2];
    assert_eq!(current.center, None);
    assert_eq!(current.position, None);
    assert_eq!(current.size, Some(Point::new(0.12, 0.12)));
    assert_eq!(
        current.at.as_ref().map(|at| at.region),
        Some(expected_region)
    );
    let relation = current.relation.as_ref().unwrap();
    assert_eq!(relation.kind, RelationType::Between);
    assert_eq!(relation.gap, RelationGap::Medium);

    let ja_source = concat!(
        "赤い円を中心に置く。\n",
        "青い四角を中心に置く。\n",
        "前の二つの間に\n",
        "黒い円を中心に置く。"
    );
    let ja = stage15(ja_source, ResolvedInstructionLanguage::Ja);
    let ja_current = &ja.original_semantic_document().instructions[2];
    assert_eq!(
        ja_current
            .position
            .as_ref()
            .map(|position| position.identity.id.as_str()),
        Some("center")
    );
    assert!(matches!(
        ja_current.relation.as_ref(),
        Some(relation)
            if relation.kind == SemanticRelationKind::Between
                && relation.reference == SemanticPreviousReference::PreviousTwo
    ));
    let ja_lowered = lower_verified_stage15_score(
        ja.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );
    assert_eq!(ja_lowered.outcome(), ScoreLoweringOutcome::Complete);
    let ja_score = ja_lowered.score().unwrap();
    assert_eq!(ja_score.instructions.len(), 3);
    assert!(ja_score.instructions[2].at.is_some());
    assert_eq!(
        ja_score.instructions[2].relation.as_ref().unwrap().kind,
        RelationType::Between
    );
}

#[test]
fn relation_requires_original_surviving_direct_referents_and_omits_dependents() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let definition = complete_flat_emit_definition();

    let macro_before_direct_referents = stage15_locked(
        concat!(
            "Draw.Pair! ",
            "place one red circle at center. ",
            "place one blue ellipse at center. ",
            "place one green square at center between the previous two."
        ),
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let delivered = lower_verified_stage15_score(
        macro_before_direct_referents.verified_effective_view(),
        context,
    );
    assert_eq!(delivered.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(delivered.score().unwrap().instructions.len(), 5);
    assert_eq!(
        delivered.score().unwrap().instructions[4]
            .relation
            .as_ref()
            .unwrap()
            .kind,
        RelationType::Between
    );

    let macro_referent = stage15_locked(
        "Draw.Pair! place one green square at center not touching the previous shape.",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let stopped = lower_verified_stage15_score(macro_referent.verified_effective_view(), context);
    assert_eq!(stopped.outcome(), ScoreLoweringOutcome::Stopped);
    assert!(stopped.score().is_none());
    let macro_referent = lower_verified_stage15_score_with_policy(
        macro_referent.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        macro_referent.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert_eq!(macro_referent.score().unwrap().instructions.len(), 2);
    assert!(
        macro_referent
            .diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                (&diagnostic.reason, &diagnostic.disposition),
                (
                    ScoreFieldGap::UnavailableRelationReference {
                        kind: SemanticRelationKind::NotTouching,
                        reference: SemanticPreviousReference::PreviousOne,
                        dependency_instruction_indices,
                    },
                    ScoreDiagnosticDisposition::Omitted {
                        unit: ScoreOmissionUnit::RelationInstruction {
                            instruction_index: 1
                        },
                        ..
                    }
                ) if dependency_instruction_indices == &[0]
            ))
    );

    let cascading = stage15(
        concat!(
            "paper. ",
            "place two red circle at center. ",
            "place one blue circle at center not touching the previous shape. ",
            "place one green square at center not touching the previous shape. ",
            "place one gray ellipse at horizontal 0.8, vertical 0.8."
        ),
        ResolvedInstructionLanguage::En,
    );
    let cascading = lower_verified_stage15_score_with_policy(
        cascading.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        cascading.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    let score = cascading.score().unwrap();
    assert_eq!(score.instructions.len(), 1);
    assert_eq!(score.instructions[0].primitive, Primitive::Ellipse);
    assert!(matches!(
        &score.canvas,
        Canvas::Spec(spec)
            if matches!(spec.ground.as_ref(), Some(ground) if ground.material == GroundMaterial::Paper)
    ));
    assert_eq!(
        cascading.instruction_origins(),
        &[ScoreInstructionOrigin::SourceInstruction {
            instruction_index: 3
        }]
    );
    let unavailable = cascading
        .diagnostics()
        .iter()
        .filter_map(|diagnostic| match &diagnostic.reason {
            ScoreFieldGap::UnavailableRelationReference {
                dependency_instruction_indices,
                ..
            } => Some(dependency_instruction_indices.clone()),
            _ => None,
        })
        .collect::<Vec<_>>();
    assert_eq!(unavailable, vec![vec![0], vec![1]]);
}

#[test]
fn relation_accepts_a_numeric_prior_but_rejects_numeric_or_noncenter_current_position() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let numeric_prior = stage15(
        concat!(
            "place one red circle at horizontal 0.2, vertical 0.3. ",
            "place one blue square at center not touching the previous shape."
        ),
        ResolvedInstructionLanguage::En,
    );
    let numeric_prior =
        lower_verified_stage15_score(numeric_prior.verified_effective_view(), context);
    assert_eq!(numeric_prior.outcome(), ScoreLoweringOutcome::Complete);
    assert!(
        numeric_prior.score().unwrap().instructions[1]
            .relation
            .is_some()
    );

    for source in [
        concat!(
            "place one red circle at center. ",
            "place one blue square at horizontal 0.7, vertical 0.7 not touching the previous shape."
        ),
        concat!(
            "place one red circle at center. ",
            "place one blue square at left-edge not touching the previous shape."
        ),
        concat!(
            "place one red circle at center. ",
            "blue square not touching the previous shape."
        ),
    ] {
        let result = stage15(source, ResolvedInstructionLanguage::En);
        let lowered = lower_verified_stage15_score_with_policy(
            result.verified_effective_view(),
            context,
            ScoreErrorPolicy::OmitAndContinue,
        );
        assert_eq!(
            lowered.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions
        );
        assert_eq!(lowered.score().unwrap().instructions.len(), 1);
        assert!(lowered.diagnostics().iter().any(|diagnostic| matches!(
            (&diagnostic.reason, &diagnostic.disposition),
            (
                ScoreFieldGap::UnsupportedRelation {
                    kind: SemanticRelationKind::NotTouching,
                    reference: SemanticPreviousReference::PreviousOne,
                    dependency_instruction_indices,
                },
                ScoreDiagnosticDisposition::Omitted {
                    unit: ScoreOmissionUnit::RelationInstruction {
                        instruction_index: 1
                    },
                    ..
                }
            ) if dependency_instruction_indices == &[0]
        )));
    }
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
        (
            "place one red oil paint solid empty circle with diameter 0.2 at horizontal 0.5, vertical 0.5.",
            "square",
            Primitive::Circle,
            Some(Point::new(0.5, 0.5)),
            Some(0.1),
            None,
            None,
            Color::Red,
            Weight::OilPaint,
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
        "place one red pen solid empty diagonal circle with radius 0.25 at horizontal 0.5, vertical 0.5.",
        ResolvedInstructionLanguage::En,
    );
    let continuation = stage15(
        "one red pen solid empty diagonal circle. the circle radius 0.25 horizontal 0.5 vertical 0.5 place.",
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
fn rotated_numeric_bounds_use_the_physical_declared_envelope() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let unrotated = stage15(
        "place one red ellipse with width 0.2 height 0.8 at horizontal 0.5, vertical 0.2.",
        ResolvedInstructionLanguage::En,
    );
    let vertical = stage15(
        "place one red vertical ellipse with width 0.2 height 0.8 at horizontal 0.5, vertical 0.2.",
        ResolvedInstructionLanguage::En,
    );
    assert!(
        lower_verified_stage15_score(unrotated.verified_effective_view(), context)
            .gaps()
            .contains(&ScoreFieldGap::GeometryExtentOutOfBounds)
    );
    let vertical = lower_verified_stage15_score(vertical.verified_effective_view(), context);
    assert_eq!(vertical.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(
        vertical.score().unwrap().instructions[0].rotation,
        Some(90.0)
    );

    let circle = stage15(
        "place one red diagonal circle with radius 0.2 at horizontal 0.2, vertical 0.5.",
        ResolvedInstructionLanguage::En,
    );
    let circle = lower_verified_stage15_score(circle.verified_effective_view(), context);
    assert_eq!(circle.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(circle.score().unwrap().instructions[0].radius, Some(0.2));

    let ideal_ellipse = stage15(
        "place one red diagonal ellipse with width 0.8 height 0.2 at horizontal 0.5, vertical 0.3.",
        ResolvedInstructionLanguage::En,
    );
    assert_eq!(
        lower_verified_stage15_score(ideal_ellipse.verified_effective_view(), context).outcome(),
        ScoreLoweringOutcome::Complete,
        "the ideal ellipse extent must not be replaced by its rectangular envelope"
    );

    let unrotated_cloud = stage15(
        "place one red cloudform with width 0.8 height 0.2 at horizontal 0.5, vertical 0.2.",
        ResolvedInstructionLanguage::En,
    );
    assert_eq!(
        lower_verified_stage15_score(unrotated_cloud.verified_effective_view(), context).outcome(),
        ScoreLoweringOutcome::Complete
    );

    let cloud = stage15(
        concat!(
            "place one red diagonal cloudform with width 0.8 height 0.2 at horizontal 0.5, vertical 0.2. ",
            "place one blue circle at horizontal 0.7, vertical 0.7."
        ),
        ResolvedInstructionLanguage::En,
    );
    let stop = lower_verified_stage15_score(cloud.verified_effective_view(), context);
    assert_eq!(stop.outcome(), ScoreLoweringOutcome::Stopped);
    assert!(stop.score().is_none());
    let continued = lower_verified_stage15_score_with_policy(
        cloud.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        continued.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert_eq!(continued.score().unwrap().instructions.len(), 1);
    assert_eq!(
        continued.score().unwrap().instructions[0].primitive,
        Primitive::Circle
    );
    assert!(
        continued
            .gaps()
            .contains(&ScoreFieldGap::GeometryExtentOutOfBounds)
    );

    let named = stage15(
        "place one red diagonal ellipse at center.",
        ResolvedInstructionLanguage::En,
    );
    let named = lower_verified_stage15_score(named.verified_effective_view(), context);
    let named = &named.score().unwrap().instructions[0];
    assert_eq!(named.size, Some(Point::new(0.24, 0.144)));
    assert!(named.at.is_some());
    assert!(named.rotation.is_some());
}

#[test]
fn square_angle_is_delivered_in_both_modes_and_numeric_rotation_must_fit() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let result = stage15(
        concat!(
            "place one red horizontal square at center. ",
            "place one blue circle at horizontal 0.7, vertical 0.7."
        ),
        ResolvedInstructionLanguage::En,
    );
    let stop = lower_verified_stage15_score(result.verified_effective_view(), context);
    assert_eq!(stop.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(stop.score().unwrap().instructions.len(), 2);
    assert_eq!(stop.score().unwrap().instructions[0].rotation, Some(0.0));
    let continued = lower_verified_stage15_score_with_policy(
        result.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(continued.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(continued.score(), stop.score());

    let out_of_bounds = stage15(
        concat!(
            "place one red diagonal square with side length 0.4 at horizontal 0.5, vertical 0.25. ",
            "place one blue circle at horizontal 0.7, vertical 0.7."
        ),
        ResolvedInstructionLanguage::En,
    );
    let stopped = lower_verified_stage15_score(out_of_bounds.verified_effective_view(), context);
    assert!(stopped.score().is_none());
    assert!(
        stopped
            .gaps()
            .contains(&ScoreFieldGap::GeometryExtentOutOfBounds)
    );
    let continued = lower_verified_stage15_score_with_policy(
        out_of_bounds.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(continued.score().unwrap().instructions.len(), 1);
    assert_eq!(
        continued.score().unwrap().instructions[0].primitive,
        Primitive::Circle
    );

    let plain = stage15(
        "place one red square at center.",
        ResolvedInstructionLanguage::En,
    );
    assert_eq!(
        lower_verified_stage15_score(plain.verified_effective_view(), context).outcome(),
        ScoreLoweringOutcome::Complete
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
fn omit_and_continue_keeps_supported_instruction_when_a_sibling_cannot_lower() {
    let result = stage15(
        concat!(
            "place red circle at center. ",
            "place two blue square at horizontal 0.7, vertical 0.5."
        ),
        ResolvedInstructionLanguage::En,
    );
    let lowered = lower_verified_stage15_score_with_policy(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
    );

    assert_eq!(
        lowered.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    let instructions = &lowered
        .score()
        .expect("OmitAndContinue should preserve the supported sibling")
        .instructions;
    assert_eq!(instructions.len(), 1);
    assert_eq!(instructions[0].primitive, Primitive::Circle);
    assert_eq!(
        lowered.instruction_origins(),
        [ScoreInstructionOrigin::SourceInstruction {
            instruction_index: 0
        }]
    );
    assert!(matches!(
        lowered.diagnostics(),
        [inku_ddl::ScoreLoweringDiagnostic {
            reason: ScoreFieldGap::RepeatedCountUnsupported { value: 2 },
            owner: ScoreDiagnosticOwner::SourceInstruction {
                instruction_index: 1,
                spans,
                ..
            },
            disposition: ScoreDiagnosticDisposition::Omitted {
                unit: ScoreOmissionUnit::SourceInstruction {
                    instruction_index: 1
                },
                appearance_resolution: None,
            },
        }] if spans.len() == 1
    ));
}

#[test]
fn supported_input_is_identical_under_both_error_modes() {
    let result = stage15(
        "place one red circle at center.",
        ResolvedInstructionLanguage::En,
    );
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let stop = lower_verified_stage15_score(result.verified_effective_view(), context);
    let continued = lower_verified_stage15_score_with_policy(
        result.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );

    assert_eq!(stop.error_policy(), ScoreErrorPolicy::Stop);
    assert_eq!(stop.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(continued.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(stop.score(), continued.score());
    assert_eq!(stop.instruction_origins(), continued.instruction_origins());
    assert_eq!(stop.policy_digest(), continued.policy_digest());
    assert!(stop.diagnostics().is_empty());
    assert!(continued.diagnostics().is_empty());
}

#[test]
fn ordinary_non_solid_surface_intensity_omits_only_that_field_and_keeps_quality() {
    let result = stage15(
        "place one red bleeding dense circle at center.",
        ResolvedInstructionLanguage::En,
    );
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let stop = lower_verified_stage15_score(result.verified_effective_view(), context);
    let continued = lower_verified_stage15_score_with_policy(
        result.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );

    assert_eq!(stop.outcome(), ScoreLoweringOutcome::Stopped);
    assert!(stop.score().is_none());
    assert_eq!(
        continued.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert!(continued.score().unwrap().instructions[0].filled);
    assert_eq!(
        continued.score().unwrap().instructions[0]
            .surface
            .as_ref()
            .unwrap()
            .texture,
        SurfaceTexture::Bleed
    );
    assert!(matches!(
        continued.diagnostics(),
        [inku_ddl::ScoreLoweringDiagnostic {
            owner: ScoreDiagnosticOwner::SourceInstruction {
                instruction_index: 0,
                field: Some(ScoreAppearanceField::SurfaceIntensity),
                spans,
            },
            disposition: ScoreDiagnosticDisposition::Omitted {
                unit: ScoreOmissionUnit::AppearanceField {
                    field: ScoreAppearanceField::SurfaceIntensity
                },
                appearance_resolution: Some(
                    ScoreAppearanceResolution::PreserveExplicitSurfaceQuality
                ),
            },
            ..
        }] if spans.len() == 1
    ));
}

#[test]
fn surface_intensity_reaches_direct_and_macro_scores_with_owned_provenance() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    for (level, expected) in [
        ("dense", inku_score::SurfaceIntensity::Dense),
        ("faint", inku_score::SurfaceIntensity::Faint),
    ] {
        let definition = MacroDefinition::from_json(&serde_json::json!({
            "schema":"inku.macro-definition.v1", "namespace":"Draw", "heading":"Intensity", "version":"1.0.0",
            "parameters":{}, "components":{}, "body":[{"op":"emit", "binding":null, "fields":{
                "shape":{"expr":"semantic_ref","category":"shape","id":"circle"},
                "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
                "place":{"expr":"semantic_ref","category":"place","id":"center"},
                "color":{"expr":"semantic_ref","category":"color","id":"red"},
                "surface":{"expr":"semantic_ref","category":"surface","id":"solid"},
                "surface_intensity":{"expr":"semantic_ref","category":"surface","id":level}
            }}]
        }).to_string()).unwrap();
        let transformed = stage15_locked(
            &format!("place one red flat {level} circle at center. Draw.Intensity"),
            ResolvedInstructionLanguage::En,
            &[definition],
        );
        let result = lower_verified_stage15_score(transformed.verified_effective_view(), context);
        assert!(
            result.diagnostics().is_empty(),
            "{:?}",
            result.diagnostics()
        );
        let instructions = &result.score().unwrap().instructions;
        assert_eq!(instructions[0], instructions[1]);
        assert_eq!(instructions[0].surface_intensity, expected);
        assert!(instructions[0].filled);
        assert!(instructions[0].surface.is_none());
        assert!(matches!(
            result.instruction_origins(),
            [
                ScoreInstructionOrigin::SourceInstruction { .. },
                ScoreInstructionOrigin::MacroEmit { .. }
            ]
        ));
    }
    for shape in ["line", "point"] {
        let transformed = stage15(
            &format!("place one red dense {shape} at center."),
            ResolvedInstructionLanguage::En,
        );
        let result = lower_verified_stage15_score(transformed.verified_effective_view(), context);
        assert!(result.diagnostics().iter().any(|diagnostic| matches!(
            diagnostic.reason,
            ScoreFieldGap::UnsupportedSurfaceIntensity { .. }
        )));
    }
}

#[test]
fn explicit_surface_and_ground_reach_the_actual_score() {
    let result = stage15(
        "paper. place one red bleeding circle at center.",
        ResolvedInstructionLanguage::En,
    );
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );

    assert_eq!(lowered.outcome(), ScoreLoweringOutcome::Complete);
    assert!(
        lowered.diagnostics().is_empty(),
        "{:?}",
        lowered.diagnostics()
    );
    let score = lowered.score().unwrap();
    assert!(matches!(
        &score.canvas,
        Canvas::Spec(spec)
            if spec.aspect == "wide"
                && matches!(spec.ground.as_ref(), Some(ground) if ground.material == GroundMaterial::Paper && ground.seed.is_none())
    ));
    assert_eq!(
        score.instructions[0].surface.as_ref().unwrap().texture,
        SurfaceTexture::Bleed
    );
    assert!(
        score.instructions[0]
            .surface
            .as_ref()
            .unwrap()
            .seed
            .is_none()
    );
}

#[test]
fn delivered_surface_ids_use_shared_defaults_and_flat_macro_parity() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    for (surface, expected_texture) in [
        ("wash", SurfaceTexture::Wash),
        ("grain", SurfaceTexture::Grain),
        ("stipple", SurfaceTexture::Stipple),
        ("hatch", SurfaceTexture::Hatch),
        ("crosshatch", SurfaceTexture::Crosshatch),
        ("bleed", SurfaceTexture::Bleed),
        ("aquatint", SurfaceTexture::Aquatint),
    ] {
        let definition = surface_emit_definition(surface);
        let result = stage15_locked(
            "Draw.Surface",
            ResolvedInstructionLanguage::En,
            std::slice::from_ref(&definition),
        );
        let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
        assert_eq!(
            lowered.outcome(),
            ScoreLoweringOutcome::Complete,
            "{surface}"
        );
        assert!(
            lowered.diagnostics().is_empty(),
            "{surface}: {:?}",
            lowered.diagnostics()
        );
        let spec = lowered.score().unwrap().instructions[0]
            .surface
            .as_ref()
            .unwrap();
        assert_eq!(spec.texture, expected_texture, "{surface}");
        assert!(spec.seed.is_none(), "{surface}");
    }

    let definition = surface_emit_definition("bleed");
    let paired = stage15_locked(
        "place one red bleeding circle at center; Draw.Surface",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let paired = lower_verified_stage15_score(paired.verified_effective_view(), context);
    let instructions = &paired.score().unwrap().instructions;
    assert_eq!(instructions[0], instructions[1]);
    assert!(matches!(
        paired.instruction_origins(),
        [
            ScoreInstructionOrigin::SourceInstruction { .. },
            ScoreInstructionOrigin::MacroEmit { .. }
        ]
    ));
}

#[test]
fn flat_macro_thinness_uses_literal_and_component_parameter_through_the_shared_lowerer() {
    let definition = thinness_pair_definition();
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let paired = stage15_locked(
        "place one thin red circle at center. Draw.ThinnessPair",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let paired = lower_verified_stage15_score(paired.verified_effective_view(), context);

    assert_eq!(paired.outcome(), ScoreLoweringOutcome::Complete);
    assert!(
        paired.diagnostics().is_empty(),
        "{:?}",
        paired.diagnostics()
    );
    let instructions = &paired.score().unwrap().instructions;
    assert_eq!(instructions.len(), 3);
    assert_eq!(instructions[0], instructions[1]);
    assert_eq!(instructions[1].thinness, Some(Thinness::Fine));
    assert_eq!(instructions[2].thinness, Some(Thinness::ExtraFine));
    assert!(matches!(
        paired.instruction_origins(),
        [
            ScoreInstructionOrigin::SourceInstruction { .. },
            ScoreInstructionOrigin::MacroEmit { .. },
            ScoreInstructionOrigin::MacroEmit { .. }
        ]
    ));

    let caller = stage15_locked(
        "place one green circle at center. extra-fine Draw.ThinnessPair",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let stop = lower_verified_stage15_score(caller.verified_effective_view(), context);
    let continued = lower_verified_stage15_score_with_policy(
        caller.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(stop.outcome(), ScoreLoweringOutcome::Stopped);
    assert!(
        stop.gaps()
            .contains(&ScoreFieldGap::UnboundMacroCallerMeaning)
    );
    assert_eq!(continued.score().unwrap().instructions.len(), 1);
    assert_eq!(continued.score().unwrap().instructions[0].thinness, None);
    assert!(matches!(
        continued.instruction_origins(),
        [ScoreInstructionOrigin::SourceInstruction { .. }]
    ));
}

#[test]
fn delivered_ground_ids_use_shared_defaults_in_english_and_japanese() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    for (source, material) in [
        ("paper.", GroundMaterial::Paper),
        ("washi.", GroundMaterial::Washi),
        ("ink wash ground.", GroundMaterial::InkWash),
        ("charcoal ground.", GroundMaterial::CharcoalGround),
        ("canvas.", GroundMaterial::Canvas),
        ("drawing paper.", GroundMaterial::DrawingPaper),
        ("mezzotint.", GroundMaterial::Mezzotint),
    ] {
        let result = stage15(source, ResolvedInstructionLanguage::En);
        let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
        assert_eq!(
            lowered.outcome(),
            ScoreLoweringOutcome::Complete,
            "{source}"
        );
        assert!(matches!(
            &lowered.score().unwrap().canvas,
            Canvas::Spec(spec)
                if spec.aspect == "wide"
                    && matches!(spec.ground.as_ref(), Some(ground) if ground.material == material && ground.seed.is_none())
        ));
    }

    let japanese = stage15("和紙。", ResolvedInstructionLanguage::Ja);
    let japanese = lower_verified_stage15_score(japanese.verified_effective_view(), context);
    assert!(matches!(
        &japanese.score().unwrap().canvas,
        Canvas::Spec(spec)
            if matches!(spec.ground.as_ref(), Some(ground) if ground.material == GroundMaterial::Washi)
    ));
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
fn incomplete_and_unowned_numeric_geometry_fail_as_typed_compiler_issues() {
    for (source, expected_kind) in [
        (
            "place one red pen solid empty ellipse with width 0.2 at horizontal 0.5, vertical 0.5.",
            "incomplete_numeric_geometry",
        ),
        (
            "place one red pen solid empty circle with radius 0.1 at horizontal 0.5.",
            "incomplete_numeric_position",
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
            "place one red pen solid empty triangle radius 0.1 at horizontal 0.5, vertical 0.5.",
            Primitive::Triangle,
            ScoreFieldGap::ShapeConstraintMismatch {
                primitive: Primitive::Triangle,
            },
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
fn canonical_nine_primitives_map_one_to_one_and_unknown_identity_fails_closed() {
    for (id, expected) in [
        ("line", Primitive::Line),
        ("circle", Primitive::Circle),
        ("ellipse", Primitive::Ellipse),
        ("triangle", Primitive::Triangle),
        ("square", Primitive::Square),
        ("polygon", Primitive::Polygon),
        ("arc", Primitive::Arc),
        ("point", Primitive::Point),
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
        "small line",
        "small arc",
        "small point",
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
        ("triangle", Primitive::Triangle),
        ("polygon", Primitive::Polygon),
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

#[test]
fn complete_flat_macro_sequence_reaches_actual_score() {
    let definition = complete_flat_emit_definition();
    let result = stage15_locked(
        "one Draw.Pair",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );

    assert_eq!(result.original_expanded_invocations().len(), 1);
    assert_eq!(result.original_expanded_invocations()[0].nodes.len(), 2);
    assert_eq!(result.targets().len(), 2);
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );

    assert!(lowered.gaps().is_empty(), "{:?}", lowered.gaps());
    let instructions = &lowered.score().unwrap().instructions;
    assert_eq!(instructions.len(), 2);
    assert_eq!(instructions[0].primitive, Primitive::Circle);
    assert_eq!(instructions[0].color, Color::Red);
    assert_eq!(instructions[1].primitive, Primitive::Square);
    assert_eq!(instructions[1].color, Color::Blue);
    assert!(lowered.instruction_origins().iter().enumerate().all(
        |(expected_generated_ordinal, origin)| matches!(
            origin,
            ScoreInstructionOrigin::MacroEmit {
                source_instruction_index: 0,
                binding: None,
                provenance,
            } if provenance.invocation.invocation_ordinal == 0
                && provenance.generated_ordinal == expected_generated_ordinal as u64
        )
    ));

    let empty_definition = MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Draw","heading":"Empty","version":"1.0.0","parameters":{},"components":{},"body":[]}"#,
    )
    .unwrap();
    let empty = stage15_locked(
        "Draw.Empty",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&empty_definition),
    );
    let empty_lowered = lower_verified_stage15_score(
        empty.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );
    assert!(empty_lowered.gaps().is_empty());
    assert_eq!(empty_lowered.outcome(), ScoreLoweringOutcome::Complete);
    assert!(empty_lowered.score().unwrap().instructions.is_empty());
    assert!(empty_lowered.instruction_origins().is_empty());
}

#[test]
fn macro_continuation_executes_once_and_keeps_source_ordinal_at_no_score_boundary() {
    let definition = complete_focus_emit_definition();
    let result = stage15_locked(
        "a Focus.Center; the red Focus.Center; a Focus.Center",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );

    assert_eq!(result.original_semantic_document().instructions.len(), 2);
    assert_eq!(result.original_semantic_document().continuations.len(), 1);
    assert_eq!(result.original_expanded_invocations().len(), 2);
    assert_eq!(
        result
            .original_expanded_invocations()
            .iter()
            .map(|invocation| invocation.provenance.invocation_ordinal)
            .collect::<Vec<_>>(),
        [0, 2]
    );
    assert!(
        result
            .original_expanded_invocations()
            .iter()
            .all(|invocation| invocation.nodes.len() == 2)
    );

    let resolved_focus = result.resolved_focus().unwrap();
    let generated_focus = result
        .targets()
        .iter()
        .map(|target| match &target.path {
            inku_ddl::Stage15TargetPath::MacroEmit {
                invocation_ordinal,
                generated_ordinal,
                field,
                ..
            } if field == "place" => (
                *invocation_ordinal,
                *generated_ordinal,
                target.effective_focus,
            ),
            other => panic!("unexpected Focus.Center target: {other:?}"),
        })
        .collect::<Vec<_>>();
    assert_eq!(
        generated_focus,
        [
            (0, 0, resolved_focus),
            (0, 1, resolved_focus),
            (2, 0, resolved_focus),
            (2, 1, resolved_focus),
        ]
    );

    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );
    assert_eq!(lowered.gaps(), [ScoreFieldGap::UnboundMacroCallerMeaning]);
    assert!(lowered.score().is_none());
    assert!(lowered.instruction_origins().is_empty());

    let continued = lower_verified_stage15_score_with_policy(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        continued.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert_eq!(
        continued
            .score()
            .unwrap()
            .instructions
            .iter()
            .map(|instruction| instruction.color)
            .collect::<Vec<_>>(),
        [Color::Red, Color::Blue, Color::Red, Color::Blue]
    );
    assert_eq!(
        continued
            .instruction_origins()
            .iter()
            .map(|origin| match origin {
                ScoreInstructionOrigin::MacroEmit { provenance, .. } => {
                    provenance.invocation.invocation_ordinal
                }
                other => panic!("unexpected direct origin: {other:?}"),
            })
            .collect::<Vec<_>>(),
        [0, 0, 2, 2]
    );
    assert!(matches!(
        continued.diagnostics(),
        [inku_ddl::ScoreLoweringDiagnostic {
            owner: ScoreDiagnosticOwner::MacroInvocation {
                invocation_ordinal: 0,
                field: Some(ScoreAppearanceField::Color),
                spans,
                ..
            },
            disposition: ScoreDiagnosticDisposition::Omitted {
                unit: ScoreOmissionUnit::AppearanceField {
                    field: ScoreAppearanceField::Color
                },
                appearance_resolution: Some(ScoreAppearanceResolution::PreserveGeneratedValue),
            },
            ..
        }] if spans.len() == 1
    ));
}

#[test]
fn direct_macro_direct_order_and_same_effective_input_share_the_lowerer() {
    let definition = complete_flat_emit_definition();
    let result = stage15_locked(
        concat!(
            "place one red circle at center; ",
            "Draw.Pair; ",
            "place one blue square at center"
        ),
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );

    assert!(lowered.gaps().is_empty(), "{:?}", lowered.gaps());
    let instructions = &lowered.score().unwrap().instructions;
    assert_eq!(instructions.len(), 4);
    assert_eq!(instructions[0], instructions[1]);
    assert_eq!(instructions[2], instructions[3]);
    assert!(matches!(
        lowered.instruction_origins(),
        [
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 0
            },
            ScoreInstructionOrigin::MacroEmit {
                source_instruction_index: 1,
                ..
            },
            ScoreInstructionOrigin::MacroEmit {
                source_instruction_index: 1,
                ..
            },
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 2
            }
        ]
    ));
    for origin in &lowered.instruction_origins()[1..3] {
        assert!(matches!(
            origin,
            ScoreInstructionOrigin::MacroEmit {
                source_instruction_index: 1,
                provenance,
                ..
            } if provenance.invocation.invocation_ordinal == 0
        ));
    }
}

#[test]
fn japanese_and_english_four_shape_macro_uses_shared_defaults_and_geometry() {
    let definition = four_shape_default_definition();
    let color_map = default_color_map();
    let palette = work_palette_context(&color_map, None, None, Color::White).unwrap();
    let context =
        ScoreLoweringContext::resolve_with_palette("wide", Color::White, palette).unwrap();
    let ja = stage15_locked(
        "Draw.Defaults",
        ResolvedInstructionLanguage::Ja,
        std::slice::from_ref(&definition),
    );
    let en = stage15_locked(
        "Draw.Defaults",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let ja_lowered = lower_verified_stage15_score(ja.verified_effective_view(), context);
    let en_lowered = lower_verified_stage15_score(en.verified_effective_view(), context);

    assert!(ja_lowered.gaps().is_empty(), "{:?}", ja_lowered.gaps());
    assert_eq!(ja_lowered.score(), en_lowered.score());
    let instructions = &ja_lowered.score().unwrap().instructions;
    assert_eq!(instructions.len(), 4);
    for (instruction, expected_primitive, expected_radius, expected_size) in instructions
        .iter()
        .zip([
            (Primitive::Circle, Some(0.12), None),
            (Primitive::Ellipse, None, Some(Point::new(0.24, 0.144))),
            (Primitive::Cloudform, None, Some(Point::new(0.24, 0.144))),
            (Primitive::Square, None, Some(Point::new(0.24, 0.24))),
        ])
        .map(|(instruction, expected)| (instruction, expected.0, expected.1, expected.2))
    {
        assert_eq!(instruction.primitive, expected_primitive);
        assert_eq!(instruction.radius, expected_radius);
        assert_eq!(instruction.size, expected_size);
        assert_eq!(instruction.color, Color::Black);
        assert_eq!(instruction.weight, Weight::Pen);
        assert_eq!(instruction.style, LineStyle::Solid);
        assert!(instruction.filled);
    }
}

#[test]
fn flat_macro_angle_uses_the_shared_resolver_for_square() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let horizontal = angle_emit_definition("circle", "horizontal");
    let macro_horizontal = stage15_locked(
        "Angle.Mark",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&horizontal),
    );
    let direct_horizontal = stage15(
        "place one red horizontal circle at center.",
        ResolvedInstructionLanguage::En,
    );
    for lowered in [
        lower_verified_stage15_score(macro_horizontal.verified_effective_view(), context),
        lower_verified_stage15_score(direct_horizontal.verified_effective_view(), context),
    ] {
        let instruction = &lowered.score().unwrap().instructions[0];
        assert_eq!(instruction.primitive, Primitive::Circle);
        assert_eq!(instruction.color, Color::Red);
        assert_eq!(instruction.rotation, Some(0.0));
    }

    let circle = angle_emit_definition("circle", "rotated");
    let result = stage15_locked(
        "Angle.Mark",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&circle),
    );
    let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
    let rotation = lowered
        .score()
        .unwrap_or_else(|| {
            panic!(
                "gaps={:#?}; expanded={:#?}",
                lowered.gaps(),
                result.original_expanded_invocations()
            )
        })
        .instructions[0]
        .rotation
        .unwrap_or_else(|| panic!("expanded={:#?}", result.original_expanded_invocations()));
    let circular_distance = (0..8)
        .map(|multiple| (rotation - f64::from(multiple * 45)).abs())
        .map(|distance| distance.min(360.0 - distance))
        .fold(f64::INFINITY, f64::min);
    assert!(circular_distance > 5.0);

    let left_facing = angle_emit_definition("circle", "left_rising");
    let result = stage15_locked(
        "Angle.Mark",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&left_facing),
    );
    let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
    assert_eq!(lowered.outcome(), ScoreLoweringOutcome::Complete);
    assert!((203.0..=217.0).contains(&lowered.score().unwrap().instructions[0].rotation.unwrap()));

    let square = angle_emit_definition("square", "horizontal");
    let result = stage15_locked(
        "place one green circle at center. Angle.Mark",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&square),
    );
    let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
    assert_eq!(lowered.outcome(), ScoreLoweringOutcome::Complete);
    assert!(lowered.diagnostics().is_empty());
    assert_eq!(lowered.score().unwrap().instructions.len(), 2);
    let instruction = &lowered.score().unwrap().instructions[1];
    assert_eq!(instruction.primitive, Primitive::Square);
    assert_eq!(instruction.rotation, Some(0.0));
}

#[test]
fn parameter_bound_fields_and_an_unused_parameter_lower_once() {
    let definition = parameter_bound_definition();
    let result = stage15_locked(
        "Param.One red place center pencil",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );

    assert!(lowered.gaps().is_empty(), "{:?}", lowered.gaps());
    let instruction = &lowered.score().unwrap().instructions[0];
    assert_eq!(instruction.primitive, Primitive::Circle);
    assert_eq!(instruction.color, Color::Red);
    assert_eq!(instruction.weight, Weight::Pen);
}

#[test]
fn declared_core_thinness_source_reaches_actual_score() {
    let definition = MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Core","heading":"Mark","version":"1.0.0","parameters":{"width":{"type":"semantic_ref","category":"thinness"}},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"},"thinness":{"expr":"parameter","name":"width"}}}]}"#,
    ).unwrap();
    let result = stage15_locked(
        "Core.Mark thin",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );
    assert_eq!(
        lowered.outcome(),
        ScoreLoweringOutcome::Complete,
        "{:?}",
        lowered.diagnostics()
    );
    assert_eq!(
        lowered.score().unwrap().instructions[0].thinness,
        Some(Thinness::Fine)
    );
}

#[test]
fn declared_core_fields_and_literals_share_ordinary_effective_score() {
    let definition = MacroDefinition::from_json(&serde_json::json!({
        "schema":"inku.macro-definition.v1", "namespace":"Core", "heading":"Fields", "version":"1.0.0",
        "parameters":{"width":{"type":"semantic_ref","category":"thinness"},"scale":{"type":"semantic_ref","category":"relative_scale"}},
        "components":{}, "body":[{"op":"emit","binding":null,"fields":{
            "shape":{"expr":"semantic_ref","category":"shape","id":"circle"},
            "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
            "place":{"expr":"semantic_ref","category":"place","id":"center"},
            "color":{"expr":"semantic_ref","category":"color","id":"red"},
            "thinness":{"expr":"parameter","name":"width"},
            "relative_scale":{"expr":"parameter","name":"scale"}
        }}]
    }).to_string()).unwrap();
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    for (language, source, ordinary, width, scale) in [
        (
            ResolvedInstructionLanguage::En,
            "thin normal-sized Core.Fields",
            "place one thin normal-sized red circle at center.",
            "fine",
            "normal",
        ),
        (
            ResolvedInstructionLanguage::En,
            "very large Core.Fields extra-fine",
            "place one extra-fine very large red circle at center.",
            "extra_fine",
            "very_large",
        ),
        (
            ResolvedInstructionLanguage::Ja,
            "細い普通の大きさCore.Fields",
            "細い普通の大きさ赤い円を中心に置く。",
            "fine",
            "normal",
        ),
        (
            ResolvedInstructionLanguage::Ja,
            "ごく細いとても大きいCore.Fields",
            "ごく細いとても大きい赤い円を中心に置く。",
            "extra_fine",
            "very_large",
        ),
    ] {
        let generated = stage15_locked(source, language, std::slice::from_ref(&definition));
        let direct = stage15(ordinary, language);
        let mut literal = serde_json::to_value(&definition).unwrap();
        literal["parameters"] = serde_json::json!({});
        literal["body"][0]["fields"]["thinness"] =
            serde_json::json!({"expr":"semantic_ref","category":"thinness","id":width});
        literal["body"][0]["fields"]["relative_scale"] =
            serde_json::json!({"expr":"semantic_ref","category":"relative_scale","id":scale});
        let literal = MacroDefinition::from_json(&literal.to_string()).unwrap();
        let literal = stage15_locked("Core.Fields", language, &[literal]);
        let mut scores = Vec::new();
        for result in [&generated, &direct, &literal] {
            let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
            assert_eq!(
                lowered.outcome(),
                ScoreLoweringOutcome::Complete,
                "{source}: {:?}",
                lowered.diagnostics()
            );
            let mut score = lowered.score().unwrap().clone();
            // Different definition/meaning identities may choose different effective focus.
            score.instructions[0].at = None;
            scores.push(score);
        }
        assert_eq!(scores[0], scores[1], "{source}");
        assert_eq!(scores[0], scores[2], "{source}");
    }
}

#[test]
fn flat_use_repeat_and_vary_emits_are_consumed_without_origin_rejection() {
    let definition = flat_operator_definition();
    let result = stage15_locked(
        "Flat.Operators",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    assert_eq!(result.original_expanded_invocations()[0].nodes.len(), 3);
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
    );

    assert!(lowered.gaps().is_empty(), "{:?}", lowered.gaps());
    assert_eq!(lowered.score().unwrap().instructions.len(), 3);
    let paths = lowered
        .instruction_origins()
        .iter()
        .map(|origin| match origin {
            ScoreInstructionOrigin::MacroEmit { provenance, .. } => {
                provenance.expansion_path.as_slice()
            }
            other => panic!("unexpected source instruction: {other:?}"),
        })
        .collect::<Vec<_>>();
    assert!(
        paths[0]
            .iter()
            .any(|segment| matches!(segment, inku_ddl::ExpansionPathSegment::ComponentUse { .. }))
    );
    assert!(
        paths[1]
            .iter()
            .any(|segment| matches!(segment, inku_ddl::ExpansionPathSegment::Repeat { .. }))
    );
    assert!(
        paths[2]
            .iter()
            .any(|segment| matches!(segment, inku_ddl::ExpansionPathSegment::Vary { .. }))
    );
}

#[test]
fn macro_group_delivery_keeps_unsupported_emit_and_caller_stop_policy() {
    let cases = [
        (
            missing_movement_definition(),
            "Bad.MissingMovement",
            ScoreFieldGap::MissingMacroEmitField {
                key: "movement".to_owned(),
            },
        ),
        (
            structural_definition(),
            "Bad.Structure",
            ScoreFieldGap::UnsupportedMacroStructure,
        ),
        (
            complete_flat_emit_definition(),
            "red Draw.Pair",
            ScoreFieldGap::UnboundMacroCallerMeaning,
        ),
    ];

    for (definition, macro_source, expected_gap) in cases {
        let source = format!("place one green circle at center. {macro_source}");
        let result = stage15_locked(
            &source,
            ResolvedInstructionLanguage::En,
            std::slice::from_ref(&definition),
        );
        let lowered = lower_verified_stage15_score(
            result.verified_effective_view(),
            ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
        );
        assert!(lowered.score().is_none(), "{macro_source}");
        assert!(lowered.instruction_origins().is_empty(), "{macro_source}");
        assert!(
            lowered.gaps().contains(&expected_gap),
            "{macro_source}: {:?}",
            lowered.gaps()
        );
    }
}

fn macro_group_emit(binding: &str, color: &str) -> serde_json::Value {
    serde_json::json!({"op":"emit", "binding":binding, "fields":{
        "shape":{"expr":"semantic_ref","category":"shape","id":"line"},
        "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
        "place":{"expr":"semantic_ref","category":"place","id":"center"},
        "color":{"expr":"semantic_ref","category":"color","id":color}
    }})
}

fn macro_group_definition(body: serde_json::Value) -> MacroDefinition {
    let mut value = serde_json::to_value(complete_flat_emit_definition()).unwrap();
    value["body"] = body;
    MacroDefinition::from_json(&value.to_string()).unwrap()
}

#[test]
fn macro_group_delivery_keeps_nested_order_scope_ids_and_relation_targets() {
    use inku_ddl::ExpandedMacroNode;
    use serde_json::json;
    let definition = macro_group_definition(json!([
        macro_group_emit("outer", "black"),
        {"op":"group","body":[
            macro_group_emit("local", "red"),
            {"op":"relation","kind":"connected","from":"outer","to":"local"},
            {"op":"group","body":[
                macro_group_emit("nested", "blue"),
                {"op":"relation","kind":"touching","from":"local","to":"nested"}
            ]}
        ]},
        {"op":"group","body":[
            macro_group_emit("local", "green"),
            macro_group_emit("next", "red"),
            {"op":"relation","kind":"not_touching","from":"local","to":"next"}
        ]}
    ]));
    assert!(definition.validate().is_valid());
    let transformed = stage15_locked(
        "place one yellow circle at center; Draw.Pair; place one blue circle at center.",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let view = transformed.verified_effective_view();
    let nodes = &view.original_expanded_invocations()[0].nodes;
    let ExpandedMacroNode::Group { body: left, .. } = &nodes[1] else {
        panic!("left group")
    };
    let ExpandedMacroNode::Group { body: nested, .. } = &left[2] else {
        panic!("nested group")
    };
    let ExpandedMacroNode::Group { body: right, .. } = &nodes[2] else {
        panic!("right group")
    };
    let originals = [&nodes[0], &left[0], &nested[0], &right[0], &right[1]];
    let context = ScoreLoweringContext::resolve("square", Color::White).unwrap();
    for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
        let result = lower_verified_stage15_score_with_policy(view, context, policy);
        assert!(
            result.diagnostics().is_empty(),
            "{:?}",
            result.diagnostics()
        );
        let instructions = &result.score().unwrap().instructions;
        assert_eq!(instructions.len(), 7);
        assert_eq!(
            instructions
                .iter()
                .map(|instruction| instruction.color)
                .collect::<Vec<_>>(),
            [
                Color::Yellow,
                Color::Black,
                Color::Red,
                Color::Blue,
                Color::Green,
                Color::Red,
                Color::Blue
            ]
        );
        assert_eq!(
            instructions[2]
                .relation
                .as_ref()
                .unwrap()
                .target_instruction_index,
            Some(1)
        );
        assert_eq!(
            instructions[3]
                .relation
                .as_ref()
                .unwrap()
                .target_instruction_index,
            Some(2)
        );
        assert!(instructions[4].relation.is_none());
        assert_eq!(
            instructions[5].relation.as_ref().unwrap().kind,
            RelationType::NotTouching
        );
        let mut locals = Vec::new();
        for (origin, original) in result.instruction_origins()[1..6].iter().zip(originals) {
            let ScoreInstructionOrigin::MacroEmit {
                source_instruction_index,
                binding,
                provenance,
            } = origin
            else {
                panic!("Macro origin")
            };
            let ExpandedMacroNode::Emit {
                binding: expected_binding,
                provenance: expected_provenance,
                ..
            } = original
            else {
                panic!("Emit")
            };
            assert_eq!(*source_instruction_index, 1);
            assert_eq!(binding, expected_binding);
            assert_eq!(provenance, expected_provenance);
            if binding.as_ref().unwrap().local_name == "local" {
                locals.push(binding.as_ref().unwrap());
            }
        }
        assert_eq!(locals.len(), 2);
        assert_ne!(locals[0], locals[1]);
    }
    // A child declaration does not become visible to the caller's lexical scope.
    let mut invalid = serde_json::to_value(definition).unwrap();
    invalid["body"].as_array_mut().unwrap().push(json!({
        "op":"relation","kind":"connected","from":"local","to":"outer"
    }));
    assert!(
        MacroDefinition::from_json(&invalid.to_string())
            .unwrap()
            .validate()
            .has_code("undefined_anchor")
    );
}

#[test]
fn macro_group_delivery_never_rebinds_across_failed_emit_or_structural_subtree() {
    use serde_json::json;
    let context = ScoreLoweringContext::resolve("square", Color::White).unwrap();
    for obstruction in ["failed_between", "failed_source", "transform", "anchor"] {
        let mut first = macro_group_emit("first", "red");
        let mut failed = macro_group_emit("failed", "black");
        failed["fields"].as_object_mut().unwrap().remove("movement");
        let mut body = Vec::new();
        if obstruction == "failed_source" {
            first["fields"].as_object_mut().unwrap().remove("movement");
        }
        body.push(first);
        match obstruction {
            "failed_between" => body.push(json!({"op":"group","body":[failed]})),
            "transform" => body.push(json!({"op":"group","body":[{
                "op":"transform","transform":{"translate_x":{"expr":"number","value":0.1}},
                "body":[macro_group_emit("hidden", "black")]
            }]})),
            "anchor" => body.push(json!({"op":"group","body":[{"op":"anchor","name":"pivot"}]})),
            _ => {}
        }
        body.extend([
            macro_group_emit("second", "blue"),
            json!({"op":"relation","kind":"connected","from":"first","to":"second"}),
            macro_group_emit("tail", "green"),
        ]);
        let definition = macro_group_definition(json!([{"op":"group","body":body}]));
        let transformed =
            stage15_locked("Draw.Pair", ResolvedInstructionLanguage::En, &[definition]);
        for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
            let result = lower_verified_stage15_score_with_policy(
                transformed.verified_effective_view(),
                context,
                policy,
            );
            let expected = if obstruction == "failed_source" {
                ScoreFieldGap::UnavailableMacroRelationReference
            } else {
                ScoreFieldGap::UnsupportedMacroRelation
            };
            assert!(
                result.gaps().contains(&expected),
                "{obstruction}: {:?}",
                result.gaps()
            );
            assert!(result.diagnostics().iter().any(|diagnostic| diagnostic.reason == expected && matches!(
                &diagnostic.owner, ScoreDiagnosticOwner::GeneratedNode { expansion_path, .. }
                    if expansion_path.iter().any(|segment| matches!(segment, inku_ddl::ExpansionPathSegment::Group { .. }))
            )));
            if policy == ScoreErrorPolicy::Stop {
                assert!(result.score().is_none());
                continue;
            }
            let instructions = &result.score().unwrap().instructions;
            let expected_colors = if obstruction == "failed_source" {
                vec![Color::Green]
            } else {
                vec![Color::Red, Color::Green]
            };
            assert_eq!(
                instructions
                    .iter()
                    .map(|instruction| instruction.color)
                    .collect::<Vec<_>>(),
                expected_colors
            );
            assert!(
                instructions
                    .iter()
                    .all(|instruction| instruction.relation.is_none())
            );
        }
    }
}

#[test]
fn macro_group_delivery_keeps_transform_subtree_and_emit_omission_units() {
    let definition = mixed_omission_definition();
    let result = stage15_locked(
        "Mixed.Omissions",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let stop = lower_verified_stage15_score(result.verified_effective_view(), context);
    let continued = lower_verified_stage15_score_with_policy(
        result.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );

    assert_eq!(stop.outcome(), ScoreLoweringOutcome::Stopped);
    assert!(stop.score().is_none());
    assert_eq!(
        continued.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert_eq!(
        continued
            .score()
            .unwrap()
            .instructions
            .iter()
            .map(|instruction| instruction.primitive)
            .collect::<Vec<_>>(),
        [Primitive::Circle, Primitive::Square]
    );
    assert!(continued.diagnostics().iter().any(|diagnostic| matches!(
        (&diagnostic.owner, &diagnostic.disposition),
        (
            ScoreDiagnosticOwner::GeneratedNode {
                invocation_ordinal: 0,
                key: None,
                spans,
                ..
            },
            ScoreDiagnosticDisposition::Omitted {
                unit: ScoreOmissionUnit::MacroStructuralSubtree { .. },
                ..
            }
        ) if spans.len() == 1
    )));
    assert!(continued.diagnostics().iter().any(|diagnostic| matches!(
        (&diagnostic.owner, &diagnostic.disposition),
        (
            ScoreDiagnosticOwner::GeneratedNode {
                invocation_ordinal: 0,
                key: Some(key),
                spans,
                ..
            },
            ScoreDiagnosticDisposition::Omitted {
                unit: ScoreOmissionUnit::MacroEmit { .. },
                ..
            }
        ) if key == "movement" && spans.len() == 1
    )));
}

#[test]
fn flat_macro_surface_uses_the_same_shared_lowerer() {
    let definition = surface_emit_definition("bleed");
    let result = stage15_locked(
        "Draw.Surface",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let stop = lower_verified_stage15_score(result.verified_effective_view(), context);
    let continued = lower_verified_stage15_score_with_policy(
        result.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(stop.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(stop.score(), continued.score());
    assert!(stop.diagnostics().is_empty());
    assert_eq!(
        stop.score().unwrap().instructions[0]
            .surface
            .as_ref()
            .unwrap()
            .texture,
        SurfaceTexture::Bleed
    );
}

#[test]
fn continue_uses_root_group_and_full_typed_relation_omission_units() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();

    let grounded = stage15(
        "paper. place one red circle at center.",
        ResolvedInstructionLanguage::En,
    );
    let grounded = lower_verified_stage15_score_with_policy(
        grounded.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(grounded.score().unwrap().instructions.len(), 1);
    assert!(matches!(
        &grounded.score().unwrap().canvas,
        Canvas::Spec(spec)
            if matches!(spec.ground.as_ref(), Some(ground) if ground.material == GroundMaterial::Paper)
    ));
    assert!(grounded.diagnostics().is_empty());

    let grouped = stage15(
        concat!(
            "place one green circle at center. ",
            "place a red circle and a blue square at the center."
        ),
        ResolvedInstructionLanguage::En,
    );
    let grouped = lower_verified_stage15_score_with_policy(
        grouped.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(grouped.score().unwrap().instructions.len(), 1);
    assert!(grouped.diagnostics().iter().any(|diagnostic| matches!(
        (&diagnostic.owner, &diagnostic.disposition),
        (
            ScoreDiagnosticOwner::CoordinatedGroup {
                group_index: 0,
                member_instruction_indices,
                spans,
            },
            ScoreDiagnosticDisposition::Omitted {
                unit: ScoreOmissionUnit::CoordinatedGroup { .. },
                ..
            }
        ) if member_instruction_indices == &[1, 2] && !spans.is_empty()
    )));

    let related = stage15(
        concat!(
            "place one green circle at center. ",
            "line. circle along the previous line."
        ),
        ResolvedInstructionLanguage::En,
    );
    assert!(
        related.original_semantic_document().instructions[2]
            .relation
            .is_some()
    );
    let related = lower_verified_stage15_score_with_policy(
        related.verified_effective_view(),
        context,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(related.score().unwrap().instructions.len(), 1);
    assert!(related.diagnostics().iter().any(|diagnostic| matches!(
        (&diagnostic.owner, &diagnostic.disposition),
        (
            ScoreDiagnosticOwner::SourceInstruction {
                instruction_index: 2,
                spans,
                ..
            },
            ScoreDiagnosticDisposition::Omitted {
                unit: ScoreOmissionUnit::RelationInstruction {
                    instruction_index: 2
                },
                ..
            }
        ) if spans.len() == 1
    )));
}

#[test]
fn ground_only_is_a_complete_canvas_score() {
    let result = stage15("paper.", ResolvedInstructionLanguage::En);
    let lowered = lower_verified_stage15_score_with_policy(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("wide", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
    );

    assert_eq!(lowered.outcome(), ScoreLoweringOutcome::Complete);
    assert!(lowered.score().is_some());
    assert!(lowered.instruction_origins().is_empty());
    assert!(lowered.diagnostics().is_empty());
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

#[test]
fn explicit_fluctuation_reaches_actual_score() {
    let result = stage15(
        "place one red fine slowly blurring circle at center.",
        ResolvedInstructionLanguage::En,
    );
    let lowered = lower_verified_stage15_score(
        result.verified_effective_view(),
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
    );
    assert_eq!(
        lowered.outcome(),
        ScoreLoweringOutcome::Complete,
        "{:?}",
        lowered.gaps()
    );
    let variation = lowered.score().unwrap().instructions[0]
        .variation
        .as_ref()
        .unwrap();
    assert_eq!(
        serde_json::to_value(variation).unwrap(),
        serde_json::json!({
            "amplitude": "fine", "frequency": "slow", "quality": "pink",
            "dimensions": ["position_x", "position_y"]
        })
    );
}

fn fluctuation_definition(slots: &[(&str, &str)], declared: bool, shape: &str) -> MacroDefinition {
    let mut data = serde_json::to_value(complete_flat_emit_definition()).unwrap();
    data["body"].as_array_mut().unwrap().truncate(1);
    data["body"][0]["fields"]["shape"]["id"] = serde_json::json!(shape);
    data["body"][0]["fields"]["place"]["id"] = serde_json::json!("left_edge");
    for (index, (dimension, id)) in slots.iter().enumerate() {
        let name = format!("token{index}");
        let expression = if declared {
            data["parameters"][&name] = serde_json::json!({"type":"semantic_ref","category":"variation","dimension":dimension});
            serde_json::json!({"expr":"parameter","name":name})
        } else {
            serde_json::json!({"expr":"semantic_ref","category":"variation","id":id})
        };
        data["body"][0]["fields"][format!("fluctuation_{dimension}")] = expression;
    }
    MacroDefinition::from_json(&data.to_string()).unwrap()
}

#[test]
fn fluctuation_closed_words_defaults_and_six_consumers_reach_score() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    for (dimension, id, amplitude, frequency, quality) in [
        ("amplitude", "fine", "fine", "medium", "perlin"),
        ("amplitude", "large", "broad", "medium", "perlin"),
        ("frequency", "slowly", "medium", "slow", "perlin"),
        ("frequency", "quickly", "medium", "high", "perlin"),
        ("quality", "swaying", "medium", "medium", "perlin"),
        ("quality", "trembling", "medium", "medium", "perlin"),
        ("quality", "undulating", "medium", "medium", "wave"),
        ("quality", "blurring", "medium", "medium", "pink"),
    ] {
        let definition = fluctuation_definition(&[(dimension, id)], false, "circle");
        let result = stage15_locked("Draw.Pair", ResolvedInstructionLanguage::En, &[definition]);
        let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
        assert_eq!(
            lowered.outcome(),
            ScoreLoweringOutcome::Complete,
            "{id}: {:?}",
            lowered.gaps()
        );
        assert_eq!(
            serde_json::to_value(&lowered.score().unwrap().instructions[0].variation).unwrap(),
            serde_json::json!({
                "amplitude":amplitude, "frequency":frequency, "quality":quality, "dimensions":["position_x","position_y"]
            })
        );
    }
    for shape in ["line", "arc", "circle", "ellipse", "square", "cloudform"] {
        let definition = fluctuation_definition(&[("quality", "undulating")], false, shape);
        let result = stage15_locked("Draw.Pair", ResolvedInstructionLanguage::En, &[definition]);
        let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
        assert_eq!(
            lowered.outcome(),
            ScoreLoweringOutcome::Complete,
            "{shape}: {:?}",
            lowered.gaps()
        );
        assert_eq!(lowered.score().unwrap().instructions.len(), 1);
        assert!(lowered.score().unwrap().instructions[0].variation.is_some());
    }
    let absent = stage15(
        "place one red circle at left-edge.",
        ResolvedInstructionLanguage::En,
    );
    let absent = lower_verified_stage15_score(absent.verified_effective_view(), context);
    assert!(absent.score().unwrap().instructions[0].variation.is_none());
    let old_default: inku_score::Variation = serde_json::from_str("{}").unwrap();
    assert_eq!(
        serde_json::to_value(old_default).unwrap(),
        serde_json::json!({"amplitude":"medium","frequency":"medium","quality":"none","dimensions":[]})
    );
}

#[test]
fn fluctuation_ordinary_literal_and_declared_macro_share_effective_score_and_owners() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    for (language, ordinary, caller, slots) in [
        (
            ResolvedInstructionLanguage::En,
            "place one red fine slowly blurring circle at left-edge.",
            "Draw.Pair fine slowly blurring",
            vec![
                ("amplitude", "fine"),
                ("frequency", "slowly"),
                ("quality", "blurring"),
            ],
        ),
        (
            ResolvedInstructionLanguage::Ja,
            "左端に、赤い円をひとつ置く。円は細かくゆっくり滲む。",
            "Draw.Pair 細かくゆっくり滲む",
            vec![
                ("amplitude", "fine"),
                ("frequency", "slowly"),
                ("quality", "blurring"),
            ],
        ),
        (
            ResolvedInstructionLanguage::En,
            "place one red fine circle at left-edge.",
            "Draw.Pair fine",
            vec![("amplitude", "fine")],
        ),
    ] {
        let direct = stage15(ordinary, language);
        let declared = stage15_locked(
            caller,
            language,
            &[fluctuation_definition(&slots, true, "circle")],
        );
        let literal = stage15_locked(
            "Draw.Pair",
            language,
            &[fluctuation_definition(&slots, false, "circle")],
        );
        let mut scores = Vec::new();
        for (index, result) in [&direct, &declared, &literal].into_iter().enumerate() {
            let lowered = lower_verified_stage15_score(result.verified_effective_view(), context);
            assert_eq!(
                lowered.outcome(),
                ScoreLoweringOutcome::Complete,
                "{ordinary}: {:?}",
                lowered.gaps()
            );
            assert_eq!(lowered.instruction_origins().len(), 1);
            assert_eq!(
                matches!(
                    &lowered.instruction_origins()[0],
                    ScoreInstructionOrigin::MacroEmit { .. }
                ),
                index != 0
            );
            scores.push(lowered.score().unwrap().clone());
        }
        assert_eq!(scores[0], scores[1], "{ordinary}");
        assert_eq!(scores[0], scores[2], "{ordinary}");
    }
}

#[test]
fn fluctuation_rejections_preserve_instruction_invocation_and_emit_units() {
    let context = ScoreLoweringContext::resolve("wide", Color::White).unwrap();
    let point = stage15(
        "place one red trembling point at left-edge. place one blue circle at left-edge.",
        ResolvedInstructionLanguage::En,
    );
    let point_emit = stage15_locked(
        "place one blue circle at left-edge. Draw.Pair",
        ResolvedInstructionLanguage::En,
        &[fluctuation_definition(
            &[("quality", "trembling")],
            false,
            "point",
        )],
    );
    let unbound = stage15_locked(
        "place one blue circle at left-edge. trembling Draw.Pair",
        ResolvedInstructionLanguage::En,
        &[fluctuation_definition(&[], false, "circle")],
    );
    // A broad legacy parameter has no known dimension until its caller value arrives.
    let mut malformed = serde_json::to_value(fluctuation_definition(
        &[("quality", "trembling")],
        true,
        "circle",
    ))
    .unwrap();
    malformed["parameters"]["token0"]
        .as_object_mut()
        .unwrap()
        .remove("dimension");
    let malformed = MacroDefinition::from_json(&malformed.to_string()).unwrap();
    let malformed = stage15_locked(
        "place one blue circle at left-edge. Draw.Pair fine",
        ResolvedInstructionLanguage::En,
        &[malformed],
    );
    for (result, unit, survivors) in [
        (&point, "instruction", 1),
        (&point_emit, "emit", 1),
        (&unbound, "invocation", 1),
        (&malformed, "emit", 1),
    ] {
        let stopped = lower_verified_stage15_score(result.verified_effective_view(), context);
        assert_eq!(stopped.outcome(), ScoreLoweringOutcome::Stopped);
        assert!(stopped.score().is_none());
        let continued = lower_verified_stage15_score_with_policy(
            result.verified_effective_view(),
            context,
            ScoreErrorPolicy::OmitAndContinue,
        );
        assert_eq!(
            continued.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions
        );
        assert_eq!(continued.score().unwrap().instructions.len(), survivors);
        assert!(
            continued.diagnostics().iter().any(|diagnostic| {
                match (&diagnostic.owner, &diagnostic.disposition, unit) {
                    (
                        _,
                        ScoreDiagnosticDisposition::Omitted {
                            unit: ScoreOmissionUnit::SourceInstruction { .. },
                            ..
                        },
                        "instruction",
                    ) => true,
                    (
                        ScoreDiagnosticOwner::GeneratedNode { .. },
                        ScoreDiagnosticDisposition::Omitted {
                            unit: ScoreOmissionUnit::MacroEmit { .. },
                            ..
                        },
                        "emit",
                    ) => true,
                    (
                        ScoreDiagnosticOwner::MacroInvocation { .. },
                        ScoreDiagnosticDisposition::Omitted {
                            unit: ScoreOmissionUnit::MacroInvocation { .. },
                            ..
                        },
                        "invocation",
                    ) => true,
                    _ => false,
                }
            }),
            "{unit}: {:?}",
            continued.diagnostics()
        );
    }
}

fn stage15(source: &str, language: ResolvedInstructionLanguage) -> Stage15TransformationResult {
    stage15_seeded(source, language, None)
}

fn stage15_seeded(
    source: &str,
    language: ResolvedInstructionLanguage,
    composition_seed: Option<u64>,
) -> Stage15TransformationResult {
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        composition_seed,
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
    let input = stage15_transformation_input(&compilation).unwrap_or_else(|error| {
        panic!(
            "{source}: {error:?}; holes={:?}; conflicts={:?}; blocking={:?}",
            compilation.holes, compilation.conflicts, compilation.blocking_diagnostics
        )
    });
    transform_stage15(input, None).unwrap()
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

fn complete_flat_emit_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Draw","heading":"Pair","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}},{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"square"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"blue"}}}]}"#,
    )
    .unwrap()
}

fn endpoint_family_emit_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Endpoint","heading":"Normal","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"line"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}},{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"arc"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"blue"}}},{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"point"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"black"}}}]}"#,
    )
    .unwrap()
}

fn thinness_pair_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Draw","heading":"ThinnessPair","version":"1.0.0","parameters":{},"components":{"mark":{"parameters":{"width":{"type":"semantic_ref","category":"thinness"}},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"},"thinness":{"expr":"parameter","name":"width"}}}]}},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"},"thinness":{"expr":"semantic_ref","category":"thinness","id":"fine"}}},{"op":"use","component":"mark","arguments":{"width":{"expr":"semantic_ref","category":"thinness","id":"extra_fine"}}}]}"#,
    )
    .unwrap()
}

fn complete_focus_emit_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Focus","heading":"Center","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}},{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"square"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"blue"}}}]}"#,
    )
    .unwrap()
}

fn four_shape_default_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Draw","heading":"Defaults","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"ellipse"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"cloudform"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"square"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"}}}]}"#,
    )
    .unwrap()
}

fn parameter_bound_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Param","heading":"One","version":"1.0.0","parameters":{"tone":{"type":"semantic_ref","category":"color"},"action":{"type":"semantic_ref","category":"movement"},"target":{"type":"semantic_ref","category":"place"},"unused":{"type":"semantic_ref","category":"touch"}},"components":{},"body":[{"op":"emit","binding":"mark","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"parameter","name":"action"},"place":{"expr":"parameter","name":"target"},"color":{"expr":"parameter","name":"tone"}}}]}"#,
    )
    .unwrap()
}

fn flat_operator_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Flat","heading":"Operators","version":"1.0.0","parameters":{},"components":{"mark":{"parameters":{},"body":[{"op":"emit","binding":"unused_id","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}}]}},"body":[{"op":"use","component":"mark","arguments":{}},{"op":"repeat","count":{"expr":"integer","value":1},"maximum":1,"index":"ordinal","body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"square"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"blue"}}}]},{"op":"vary","binding":"tone","domain":"tone","choices":[{"expr":"semantic_ref","category":"color","id":"green"},{"expr":"semantic_ref","category":"color","id":"gray"}],"range":null,"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"cloudform"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"local","name":"tone"}}}]}]}"#,
    )
    .unwrap()
}

fn missing_movement_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Bad","heading":"MissingMovement","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}}]}"#,
    )
    .unwrap()
}

fn angle_emit_definition(shape: &str, angle: &str) -> MacroDefinition {
    MacroDefinition::from_json(&format!(
        r#"{{"schema":"inku.macro-definition.v1","namespace":"Angle","heading":"Mark","version":"1.0.0","parameters":{{}},"components":{{}},"body":[{{"op":"emit","binding":null,"fields":{{"shape":{{"expr":"semantic_ref","category":"shape","id":"{shape}"}},"movement":{{"expr":"semantic_ref","category":"movement","id":"place"}},"place":{{"expr":"semantic_ref","category":"place","id":"center"}},"color":{{"expr":"semantic_ref","category":"color","id":"red"}},"angle":{{"expr":"semantic_ref","category":"angle","id":"{angle}"}}}}}}]}}"#,
    ))
    .unwrap()
}

fn structural_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Bad","heading":"Structure","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"transform","transform":{"translate_x":{"expr":"number","value":0.1}},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"}}}]}]}"#,
    )
    .unwrap()
}

fn mixed_omission_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Mixed","heading":"Omissions","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}},{"op":"transform","transform":{"translate_x":{"expr":"number","value":0.1}},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"cloudform"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"}}}]},{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"ellipse"},"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"square"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"blue"}}}]}"#,
    )
    .unwrap()
}

fn surface_emit_definition(surface: &str) -> MacroDefinition {
    MacroDefinition::from_json(&format!(
        r#"{{"schema":"inku.macro-definition.v1","namespace":"Draw","heading":"Surface","version":"1.0.0","parameters":{{}},"components":{{}},"body":[{{"op":"emit","binding":null,"fields":{{"shape":{{"expr":"semantic_ref","category":"shape","id":"circle"}},"movement":{{"expr":"semantic_ref","category":"movement","id":"place"}},"place":{{"expr":"semantic_ref","category":"place","id":"center"}},"color":{{"expr":"semantic_ref","category":"color","id":"red"}},"surface":{{"expr":"semantic_ref","category":"surface","id":"{surface}"}}}}}}]}}"#
    ))
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
