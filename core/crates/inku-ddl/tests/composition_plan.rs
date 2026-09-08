use inku_ddl::*;
use inku_score::{Color, Primitive, Thinness};
use serde_json::{Value, json};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 16,
    max_depth: 16,
    max_evaluation_steps: 1_000,
    max_nodes_per_invocation: 100,
    max_total_nodes: 500,
};

fn compile(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> TypedDdlCompilation {
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
    compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, locks).unwrap(),
        definitions,
        Some(19),
        LIMITS,
    )
}

fn stage(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> Stage15TransformationResult {
    let compilation = compile(source, language, definitions);
    let input = stage15_transformation_input(&compilation).unwrap_or_else(|error| {
        panic!(
            "{source}: {error:?}; {:?}; {:?}; {:?}",
            compilation.holes, compilation.conflicts, compilation.blocking_diagnostics
        )
    });
    transform_stage15(input, None).unwrap()
}

fn context(canvas: &str) -> ScoreLoweringContext {
    ScoreLoweringContext::resolve(canvas, Color::White).unwrap()
}

fn ratio(value: Rational, numerator: i128, denominator: i128) {
    assert_eq!(
        value.numerator() * denominator,
        numerator * value.denominator()
    );
}

#[test]
fn exact_counts_default_and_object_dimensions_are_independent() {
    for (quantity, count) in [
        ("", 8),
        ("one ", 1),
        ("four ", 4),
        ("eight ", 8),
        ("4294967295 ", u32::MAX),
    ] {
        let source = format!("scatter {quantity}large red circle at center.");
        let transformed = stage(&source, ResolvedInstructionLanguage::En, &[]);
        let view = transformed.verified_effective_view();
        let result = plan_verified_stage15(view, context("square"));
        assert_eq!(
            result.outcome(),
            CompositionPlanOutcome::Ready,
            "{:?}",
            result.diagnostics()
        );
        let objects = result.objects().unwrap();
        assert_eq!(objects.len(), 1);
        assert_eq!(objects[0].count(), count);
        assert_eq!(objects[0].count_was_omitted(), quantity.is_empty());
        assert_eq!(
            view.original_semantic_document().instructions[0]
                .entity
                .quantity
                .is_none(),
            quantity.is_empty()
        );
        let ResolvedGeometryDimensions::Circle { radius } = objects[0].dimensions() else {
            panic!()
        };
        ratio(radius, 9, 50);
        assert_eq!(
            objects[0].recipe(),
            &PlacementRecipe::ScatterUniformWithCentroidTranslation
        );
        assert!(
            lower_verified_stage15_score(view, context("square"))
                .score()
                .is_none()
        );
        assert_eq!(result.policy_digest(), geometry_resolution_policy_digest());
    }
    for quantity in ["0", "4294967296", "many", "unknown"] {
        let compilation = compile(
            &format!("scatter {quantity} red circle at center."),
            ResolvedInstructionLanguage::En,
            &[],
        );
        if let Ok(input) = stage15_transformation_input(&compilation) {
            let transformed = transform_stage15(input, None).unwrap();
            let result =
                plan_verified_stage15(transformed.verified_effective_view(), context("square"));
            assert_eq!(
                result.outcome(),
                CompositionPlanOutcome::Stopped,
                "{quantity}"
            );
        }
    }
}

#[test]
fn seven_shapes_retain_normal_aspect_and_thinness_is_separate() {
    for (word, primitive) in [
        ("line", Primitive::Line),
        ("circle", Primitive::Circle),
        ("ellipse", Primitive::Ellipse),
        ("square", Primitive::Square),
        ("arc", Primitive::Arc),
        ("cloudform", Primitive::Cloudform),
        ("point", Primitive::Point),
    ] {
        let source = format!("scatter four red {word} at left-edge.");
        let transformed = stage(&source, ResolvedInstructionLanguage::En, &[]);
        let result = plan_verified_stage15(transformed.verified_effective_view(), context("oban"));
        let object = &result
            .objects()
            .unwrap_or_else(|| panic!("{word}: {:?}", result.diagnostics()))[0];
        assert_eq!(object.primitive(), primitive);
        match object.dimensions() {
            ResolvedGeometryDimensions::Line { length } => ratio(length, 6, 25),
            ResolvedGeometryDimensions::Circle { radius } => ratio(radius, 3, 25),
            ResolvedGeometryDimensions::Point { radius } => ratio(radius, 3, 500),
            ResolvedGeometryDimensions::Square { side } => ratio(side, 6, 25),
            ResolvedGeometryDimensions::Arc { chord, sagitta } => {
                ratio(chord, 6, 25);
                ratio(sagitta, 3, 50);
            }
            ResolvedGeometryDimensions::CenteredSize { width, height } => {
                ratio(width, 6, 25);
                ratio(height, 18, 125);
            }
        }
    }
    let transformed = stage(
        "line-up four red thin line at left-edge.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    let result = plan_verified_stage15(transformed.verified_effective_view(), context("square"));
    let object = &result.objects().unwrap()[0];
    assert_eq!(object.appearance().thinness, Some(Thinness::Fine));
    let ResolvedGeometryDimensions::Line { length } = object.dimensions() else {
        panic!()
    };
    ratio(length, 6, 25);
}

#[test]
fn layouts_keep_physical_axes_numeric_centroid_and_named_domain() {
    for (canvas, expected) in [("square", (3, 3)), ("hd_monitor", (4, 2)), ("oban", (2, 4))] {
        let transformed = stage(
            "tile eight red circle at horizontal 0.5, vertical 0.5.",
            ResolvedInstructionLanguage::En,
            &[],
        );
        let result = plan_verified_stage15(transformed.verified_effective_view(), context(canvas));
        let object = &result.objects().unwrap()[0];
        let PlacementRecipe::Grid {
            columns,
            rows,
            filled_count,
            translate_to_numeric_anchor,
            centroid,
            ..
        } = object.recipe()
        else {
            panic!()
        };
        assert_eq!((*columns, *rows), expected);
        assert_eq!(*filled_count, 8);
        assert!(*translate_to_numeric_anchor);
        if canvas == "square" {
            ratio(centroid[0], 11, 24);
            ratio(centroid[1], 11, 24);
        }
        assert!(object.requires_numeric_must_fit());
        let line = stage(
            "line-up four red circle at left-edge.",
            ResolvedInstructionLanguage::En,
            &[],
        );
        let line_result = plan_verified_stage15(line.verified_effective_view(), context(canvas));
        let line_object = &line_result.objects().unwrap()[0];
        let PlacementRecipe::HorizontalLine { cell_width } = line_object.recipe() else {
            panic!()
        };
        let (w, h) = context(canvas).canvas_format().integer_ratio();
        ratio(*cell_width, w.into(), i128::from(w.min(h)) * 4);
    }
    let named = stage(
        "tile eight red circle at left-edge.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    let result = plan_verified_stage15(named.verified_effective_view(), context("square"));
    let object = &result.objects().unwrap()[0];
    ratio(object.domain()[0], 1, 10);
    assert!(matches!(
        object.recipe(),
        PlacementRecipe::Grid {
            translate_to_numeric_anchor: false,
            ..
        }
    ));
    let thirds = stage(
        "tile 12 red circle at top.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    let result = plan_verified_stage15(thirds.verified_effective_view(), context("square"));
    let object = &result.objects().unwrap()[0];
    ratio(object.domain()[1], 1, 3);
    assert!(matches!(
        object.recipe(),
        PlacementRecipe::Grid {
            columns: 6,
            rows: 2,
            ..
        }
    ));
}

fn definition(declared: bool, count: Option<Value>) -> MacroDefinition {
    let mut fields = json!({
        "shape":{"expr":"semantic_ref","category":"shape","id":"circle"},
        "movement":{"expr":"semantic_ref","category":"movement","id":"scatter"},
        "place":{"expr":"semantic_ref","category":"place","id":"left_edge"},
        "color":{"expr":"semantic_ref","category":"color","id":"red"},
        "relative_scale":{"expr":"semantic_ref","category":"relative_scale","id":"large"}
    });
    if declared {
        fields["relative_scale"] = json!({"expr":"parameter","name":"size"});
    }
    if let Some(count) = count {
        fields["count"] = count;
    }
    MacroDefinition::from_json(&json!({"schema":"inku.macro-definition.v1","namespace":"Draw","heading":"Plan","version":"1.0.0",
        "parameters": if declared { json!({"size":{"type":"semantic_ref","category":"relative_scale"}}) } else { json!({}) },
        "components":{},"body":[{"op":"emit","binding":null,"fields":fields}]}).to_string()).unwrap()
}

#[test]
fn declared_macro_explicit_integer_count_reaches_plan() {
    for count in [1_u32, 4, 8, u32::MAX] {
        let definition = definition(false, Some(json!({"expr":"integer","value":count})));
        let transformed = stage("Draw.Plan", ResolvedInstructionLanguage::En, &[definition]);
        let result =
            plan_verified_stage15(transformed.verified_effective_view(), context("square"));
        let object = &result.objects().unwrap()[0];
        assert_eq!(object.count(), count);
        assert!(!object.count_was_omitted());
    }
}

#[test]
fn bilingual_direct_and_declared_flat_macro_share_values_and_preserve_origins() {
    for (language, source, caller) in [
        (
            ResolvedInstructionLanguage::En,
            "scatter large red circle at left-edge.",
            "large Draw.Plan",
        ),
        (
            ResolvedInstructionLanguage::Ja,
            "左端に、大きい赤い円を散らす。",
            "大きいDraw.Plan",
        ),
    ] {
        let direct = stage(source, language, &[]);
        let generated = stage(caller, language, &[definition(true, None)]);
        let direct_result =
            plan_verified_stage15(direct.verified_effective_view(), context("wide"));
        let generated_result =
            plan_verified_stage15(generated.verified_effective_view(), context("wide"));
        let d = &direct_result.objects().unwrap()[0];
        let g = &generated_result
            .objects()
            .unwrap_or_else(|| panic!("{:?}", generated_result.diagnostics()))[0];
        assert_eq!(d.count(), 8);
        assert_eq!(d.dimensions(), g.dimensions());
        assert_eq!(d.appearance(), g.appearance());
        assert_eq!(d.anchor(), g.anchor());
        assert_eq!(d.recipe(), g.recipe());
        assert!(matches!(
            d.origin(),
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 0
            }
        ));
        assert!(matches!(
            g.origin(),
            ScoreInstructionOrigin::MacroEmit {
                source_instruction_index: 0,
                ..
            }
        ));
        assert!(
            lower_verified_stage15_score(generated.verified_effective_view(), context("wide"))
                .score()
                .is_none()
        );
    }
    let missing = compile(
        "Draw.Plan",
        ResolvedInstructionLanguage::En,
        &[definition(true, None)],
    );
    assert!(stage15_transformation_input(&missing).is_err());
    for count in [
        json!({"expr":"integer","value":0}),
        json!({"expr":"integer","value":-1}),
        json!({"expr":"integer","value":4294967296_u64}),
    ] {
        let definition = definition(false, Some(count));
        assert!(definition.identity().is_ok());
        let transformed = stage("Draw.Plan", ResolvedInstructionLanguage::En, &[definition]);
        let result =
            plan_verified_stage15(transformed.verified_effective_view(), context("square"));
        assert_eq!(result.outcome(), CompositionPlanOutcome::Stopped);
        let continued = plan_verified_stage15_with_policy(
            transformed.verified_effective_view(),
            context("square"),
            ScoreErrorPolicy::OmitAndContinue,
        );
        assert_eq!(continued.outcome(), CompositionPlanOutcome::Stopped);
        assert!(continued.objects().is_none());
    }
    for expression in [
        json!({"expr":"number","value":1.0}),
        json!({"expr":"boolean","value":true}),
        json!({"expr":"semantic_ref","category":"shape","id":"circle"}),
    ] {
        assert!(definition(false, Some(expression)).identity().is_err());
    }
}

#[test]
fn integer_parameter_and_local_counts_keep_existing_type_and_binding_checks() {
    let mut body = serde_json::to_value(definition(false, None)).unwrap();
    body["parameters"] = json!({"quantity":{"type":"integer"}});
    body["body"][0]["fields"]["count"] = json!({"expr":"parameter","name":"quantity"});
    let integer_parameter = MacroDefinition::from_json(&body.to_string()).unwrap();
    assert!(integer_parameter.identity().is_ok());
    assert!(
        stage15_transformation_input(&compile(
            "Draw.Plan",
            ResolvedInstructionLanguage::En,
            &[integer_parameter]
        ))
        .is_err()
    );
    body["parameters"]["quantity"]["type"] = json!("number");
    assert!(
        MacroDefinition::from_json(&body.to_string())
            .unwrap()
            .identity()
            .is_err()
    );
    body["parameters"] = json!({});
    assert!(
        MacroDefinition::from_json(&body.to_string())
            .unwrap()
            .identity()
            .is_err()
    );

    let mut local = serde_json::to_value(definition(false, None)).unwrap();
    let mut emit = local["body"][0].clone();
    emit["fields"]["count"] = json!({"expr":"local","name":"ordinal"});
    local["body"] = json!([{"op":"repeat","count":{"expr":"integer","value":1},"maximum":1,"index":"ordinal","body":[emit]}]);
    assert!(
        MacroDefinition::from_json(&local.to_string())
            .unwrap()
            .identity()
            .is_ok()
    );
}

#[test]
fn gaps_keep_owners_and_stop_continue_never_ready_all_omitted() {
    let transformed = stage(
        "scatter four red triangle at center. scatter eight red circle at center. scatter four red polygon at center.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    let view = transformed.verified_effective_view();
    let stopped = plan_verified_stage15(view, context("square"));
    assert_eq!(stopped.outcome(), CompositionPlanOutcome::Stopped);
    assert!(stopped.objects().is_none());
    let continued = plan_verified_stage15_with_policy(
        view,
        context("square"),
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        continued.outcome(),
        CompositionPlanOutcome::ReadyWithOmissions
    );
    assert_eq!(continued.objects().unwrap().len(), 1);
    assert_eq!(
        continued.objects().unwrap()[0].origin(),
        &ScoreInstructionOrigin::SourceInstruction {
            instruction_index: 1
        }
    );
    assert_eq!(continued.diagnostics().len(), 2);
    let all_gap = stage(
        "scatter four red triangle at center.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    assert_eq!(
        plan_verified_stage15_with_policy(
            all_gap.verified_effective_view(),
            context("square"),
            ScoreErrorPolicy::OmitAndContinue
        )
        .outcome(),
        CompositionPlanOutcome::Stopped
    );
    let scalar = stage(
        "place one red circle radius 0.1 at horizontal 0.5, vertical 0.5.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    assert_eq!(
        lower_verified_stage15_score(scalar.verified_effective_view(), context("square")).outcome(),
        ScoreLoweringOutcome::Complete
    );
    let exact = plan_verified_stage15(scalar.verified_effective_view(), context("square"));
    assert!(exact.objects().unwrap()[0].explicit_geometry().is_some());
    assert_eq!(exact.objects().unwrap()[0].count(), 1);
}
