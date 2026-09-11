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

#[test]
fn surface_intensity_stays_one_recipe_at_maximum_repetition() {
    for (level, expected) in [
        ("dense", inku_score::SurfaceIntensity::Dense),
        ("faint", inku_score::SurfaceIntensity::Faint),
    ] {
        let transformed = stage(
            &format!("tile 4294967295 red flat {level} circle at center."),
            ResolvedInstructionLanguage::En,
            &[],
        );
        let plan = plan_verified_stage15(transformed.verified_effective_view(), context("wide"));
        let objects = plan
            .objects()
            .unwrap_or_else(|| panic!("{:?}", plan.diagnostics()));
        assert_eq!(objects.len(), 1);
        assert_eq!(objects[0].count(), u32::MAX);
        assert_eq!(objects[0].appearance().surface_intensity, expected);
        assert!(objects[0].appearance().filled);
        let definition = MacroDefinition::from_json(&json!({
            "schema":"inku.macro-definition.v1", "namespace":"Fill", "heading":"Row", "version":"1.0.0",
            "parameters":{}, "components":{}, "body":[{"op":"emit", "binding":null, "fields":{
                "shape":{"expr":"semantic_ref","category":"shape","id":"circle"},
                "movement":{"expr":"semantic_ref","category":"movement","id":"tile"},
                "place":{"expr":"semantic_ref","category":"place","id":"center"},
                "color":{"expr":"semantic_ref","category":"color","id":"red"},
                "count":{"expr":"integer","value":u32::MAX},
                "surface":{"expr":"semantic_ref","category":"surface","id":"solid"},
                "surface_intensity":{"expr":"semantic_ref","category":"surface","id":level}
            }}]
        }).to_string()).unwrap();
        let generated = stage("Fill.Row", ResolvedInstructionLanguage::En, &[definition]);
        let generated_plan =
            plan_verified_stage15(generated.verified_effective_view(), context("wide"));
        let generated_objects = generated_plan
            .objects()
            .unwrap_or_else(|| panic!("{:?}", generated_plan.diagnostics()));
        assert_eq!(generated_objects.len(), 1);
        assert_eq!(generated_objects[0].count(), u32::MAX);
        assert_eq!(generated_objects[0].appearance(), objects[0].appearance());
        assert_eq!(generated_objects[0].recipe(), objects[0].recipe());
    }
}

#[test]
fn exact_decimal_generated_repetition_plan_keeps_must_fit_anchor_and_dimensions() {
    let definition = MacroDefinition::from_json(&json!({"schema":"inku.macro-definition.v1","namespace":"Exact","heading":"Row","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{
        "shape":{"expr":"semantic_ref","category":"shape","id":"ellipse"},"movement":{"expr":"semantic_ref","category":"movement","id":"tile"},"color":{"expr":"semantic_ref","category":"color","id":"red"},"count":{"expr":"integer","value":3},"width":{"expr":"exact_decimal","value":"0.3"},"height":{"expr":"exact_decimal","value":"0.2"},"position_x":{"expr":"exact_decimal","value":"0.4"},"position_y":{"expr":"exact_decimal","value":"0.5"}
    }}]}).to_string()).unwrap();
    let generated = stage("Exact.Row", ResolvedInstructionLanguage::En, &[definition]);
    let direct = stage(
        "tile three red ellipse width 0.3 height 0.2 at horizontal 0.4 vertical 0.5.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    let generated = plan_verified_stage15(generated.verified_effective_view(), context("wide"));
    let direct = plan_verified_stage15(direct.verified_effective_view(), context("wide"));
    let actual = &generated
        .objects()
        .unwrap_or_else(|| panic!("{:?}", generated.diagnostics()))[0];
    let expected = &direct
        .objects()
        .unwrap_or_else(|| panic!("{:?}", direct.diagnostics()))[0];
    assert_eq!(actual.count(), expected.count());
    assert_eq!(actual.dimensions(), expected.dimensions());
    assert_eq!(actual.recipe(), expected.recipe());
    assert!(actual.requires_numeric_must_fit());
    assert!(matches!(actual.anchor(), ObjectAnchor::GeneratedNumeric(_)));
    assert_eq!(actual.generated_geometries().len(), 1);
}

#[test]
fn repeated_shape_constraints_keep_exact_dimensions_without_materialization() {
    for source in [
        "scatter 4294967295 red equilateral triangle at center.",
        "line-up 4294967295 red wide rectangle at center.",
        "tile 4294967295 red hexagon at center.",
    ] {
        let transformed = stage(source, ResolvedInstructionLanguage::En, &[]);
        let plan = plan_verified_stage15(transformed.verified_effective_view(), context("wide"));
        let objects = plan
            .objects()
            .unwrap_or_else(|| panic!("{source}: {:?}", plan.diagnostics()));
        assert_eq!(objects.len(), 1);
        assert_eq!(objects[0].count(), u32::MAX);
        match objects[0].dimensions() {
            ResolvedGeometryDimensions::RegularTriangle { side } => ratio(side, 6, 25),
            ResolvedGeometryDimensions::Bbox { width, height } => {
                ratio(width, 6, 25);
                ratio(height, 3, 25);
            }
            ResolvedGeometryDimensions::Polygon { radius, sides } => {
                ratio(radius, 3, 25);
                assert_eq!(sides, 6);
            }
            other => panic!("unexpected {other:?}"),
        }
        assert!(
            lower_verified_stage15_score(transformed.verified_effective_view(), context("wide"))
                .score()
                .is_none()
        );
    }
}

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
    ScoreLoweringContext::resolve_with_palette(
        canvas,
        Color::White,
        inku_score::ResolvedPaletteContext::new(
            inku_score::ResolvedPaletteColor::new(Color::White, [255; 3], 1.0),
            inku_score::ResolvedPaletteColor::new(Color::Black, [0; 3], 0.0),
            inku_score::ResolvedPaletteColor::new(Color::White, [255; 3], 1.0),
        ),
    )
    .unwrap()
}

fn ratio(value: Rational, numerator: i128, denominator: i128) {
    assert_eq!(
        value.numerator() * denominator,
        numerator * value.denominator()
    );
}

#[test]
fn explicit_layout_direction_natural_source_reaches_ready_plan() {
    for (source, language) in [
        (
            "中央に、横線を縦に三本並べる。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "arrange three horizontal lines vertically at center.",
            ResolvedInstructionLanguage::En,
        ),
        (
            "中央に、斜めの線を横に三本並べる。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "line up three diagonal lines horizontally at center.",
            ResolvedInstructionLanguage::En,
        ),
        (
            "中央に、横線を三本並べる。線は縦に。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "arrange three horizontal lines at center. the line vertically.",
            ResolvedInstructionLanguage::En,
        ),
    ] {
        let transformed = stage(source, language, &[]);
        let result =
            plan_verified_stage15(transformed.verified_effective_view(), context("square"));
        assert_eq!(
            result.outcome(),
            CompositionPlanOutcome::Ready,
            "{source}: {:?}",
            result.diagnostics()
        );
        let object = &result.objects().unwrap()[0];
        assert_eq!(object.count(), 3);
        let direction = object.layout_direction().unwrap();
        if direction.identity.id == "vertical" {
            assert_eq!(direction.axis, [0, 1]);
            assert_eq!(object.angle(), Some(0.0));
            assert!(matches!(
                object.recipe(),
                PlacementRecipe::VerticalLine { .. }
            ));
        } else {
            assert_eq!(direction.identity.id, "horizontal");
            assert_eq!(direction.axis, [1, 0]);
            assert!([45.0, 135.0, 225.0, 315.0].contains(&object.angle().unwrap()));
        }
    }
}

#[test]
fn layout_axes_preserve_rectangular_physics_shape_size_and_large_count() {
    for canvas in ["golden", "oban"] {
        for (word, axis) in [("縦", [0, 1]), ("右上がり", [1, -1]), ("右下がり", [1, 1])] {
            for n in [4, u32::MAX] {
                let source = format!("中央に、横線を{word}に{n}本並べる。");
                let transformed = stage(&source, ResolvedInstructionLanguage::Ja, &[]);
                let result =
                    plan_verified_stage15(transformed.verified_effective_view(), context(canvas));
                let objects = result
                    .objects()
                    .unwrap_or_else(|| panic!("{source}: {:?}", result.diagnostics()));
                assert_eq!(objects.len(), 1);
                let object = &objects[0];
                assert_eq!(object.count(), n);
                assert_eq!(object.layout_direction().unwrap().axis, axis);
                assert_eq!(object.angle(), Some(0.0));
                let ResolvedGeometryDimensions::Line { length } = object.dimensions() else {
                    panic!()
                };
                ratio(length, 6, 25);
                match object.recipe() {
                    PlacementRecipe::VerticalLine { cell_height } => ratio(
                        *cell_height,
                        if canvas == "golden" { 1 } else { 3 },
                        i128::from(n) * if canvas == "golden" { 1 } else { 2 },
                    ),
                    PlacementRecipe::DiagonalLine { step } => {
                        ratio(step[0], 1, n.into());
                        ratio(step[1], axis[1].into(), n.into());
                    }
                    other => panic!("{other:?}"),
                }
            }
        }
    }
}

fn direction_definition(value: Value, parameters: Value) -> MacroDefinition {
    MacroDefinition::from_json(&json!({
        "schema":"inku.macro-definition.v1", "namespace":"Draw", "heading":"Direction", "version":"1.0.0",
        "parameters":parameters, "components":{}, "body":[{"op":"emit","binding":null,"fields":{
            "shape":{"expr":"semantic_ref","category":"shape","id":"line"},
            "movement":{"expr":"semantic_ref","category":"movement","id":"line_up"},
            "place":{"expr":"semantic_ref","category":"place","id":"center"},
            "angle":{"expr":"semantic_ref","category":"angle","id":"horizontal"},
            "count":{"expr":"integer","value":3}, "layout_direction":value
        }}]
    }).to_string()).unwrap()
}

#[test]
fn macro_direction_uses_definition_binding_and_keeps_caller_roles() {
    let parameter = direction_definition(
        json!({"expr":"parameter","name":"axis"}),
        json!({"axis":{"type":"semantic_ref","category":"angle"}}),
    );
    let missing = compile(
        "Draw.Direction",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&parameter),
    );
    assert!(stage15_transformation_input(&missing).is_err());
    for (source, language) in [
        ("vertical Draw.Direction", ResolvedInstructionLanguage::En),
        ("垂直Draw.Direction", ResolvedInstructionLanguage::Ja),
    ] {
        let transformed = stage(source, language, std::slice::from_ref(&parameter));
        let result =
            plan_verified_stage15(transformed.verified_effective_view(), context("square"));
        let object = &result
            .objects()
            .unwrap_or_else(|| panic!("{:?}", result.diagnostics()))[0];
        assert_eq!(object.layout_direction().unwrap().axis, [0, 1]);
        assert_eq!(object.angle(), Some(0.0));
        assert!(matches!(
            object.origin(),
            ScoreInstructionOrigin::MacroEmit { .. }
        ));
    }
    for id in ["rising", "falling", "diagonal", "rotated"] {
        let definition = direction_definition(
            json!({"expr":"semantic_ref","category":"angle","id":id}),
            json!({}),
        );
        let transformed = stage(
            "Draw.Direction",
            ResolvedInstructionLanguage::En,
            std::slice::from_ref(&definition),
        );
        let result =
            plan_verified_stage15(transformed.verified_effective_view(), context("square"));
        if id == "rotated" {
            assert_eq!(result.outcome(), CompositionPlanOutcome::Stopped);
        } else {
            assert!(result.objects().unwrap()[0].layout_direction().is_some());
        }
        let caller = stage(
            "Draw.Direction vertically",
            ResolvedInstructionLanguage::En,
            &[definition],
        );
        for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
            let result = plan_verified_stage15_with_policy(
                caller.verified_effective_view(),
                context("square"),
                policy,
            );
            assert_eq!(result.outcome(), CompositionPlanOutcome::Stopped);
            assert!(result.diagnostics().iter().any(|diagnostic| diagnostic.reason == ScoreFieldGap::UnboundMacroCallerMeaning));
        }
    }
    let mut local = serde_json::to_value(direction_definition(
        json!({"expr":"local","name":"axis"}),
        json!({}),
    ))
    .unwrap();
    let emit = local["body"][0].clone();
    local["body"] = json!([{"op":"vary","binding":"axis","domain":"layout-axis","choices":[{"expr":"semantic_ref","category":"angle","id":"vertical"}],"range":null,"body":[emit]}]);
    let local = MacroDefinition::from_json(&local.to_string()).unwrap();
    let transformed = stage("Draw.Direction", ResolvedInstructionLanguage::En, &[local]);
    let result = plan_verified_stage15(transformed.verified_effective_view(), context("square"));
    assert_eq!(
        result.objects().unwrap()[0]
            .layout_direction()
            .unwrap()
            .axis,
        [0, 1]
    );
    let ambiguous = direction_definition(
        json!({"expr":"parameter","name":"axis"}),
        json!({"axis":{"type":"semantic_ref","category":"angle"},"shape_angle":{"type":"semantic_ref","category":"angle"}}),
    );
    assert!(
        stage15_transformation_input(&compile(
            "horizontal vertical Draw.Direction",
            ResolvedInstructionLanguage::En,
            &[ambiguous]
        ))
        .is_err()
    );
}

#[test]
fn unsupported_direction_and_conflicts_preserve_execution_boundaries() {
    for source in [
        "place one red point vertically at center.",
        "scatter three red lines vertically at center.",
        "tile three red lines diagonally at center.",
    ] {
        let transformed = stage(source, ResolvedInstructionLanguage::En, &[]);
        for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
            let result = plan_verified_stage15_with_policy(
                transformed.verified_effective_view(),
                context("square"),
                policy,
            );
            assert_eq!(result.outcome(), CompositionPlanOutcome::Stopped);
            assert!(result.diagnostics().iter().any(|diagnostic| matches!(
                diagnostic.reason,
                ScoreFieldGap::UnsupportedLayoutDirection { .. }
            )));
        }
    }
    let mixed = stage(
        "place one red point vertically at center. arrange three red lines horizontally at center.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    let continued = plan_verified_stage15_with_policy(
        mixed.verified_effective_view(),
        context("square"),
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        continued.outcome(),
        CompositionPlanOutcome::ReadyWithOmissions
    );
    assert_eq!(
        continued.objects().unwrap()[0].origin(),
        &ScoreInstructionOrigin::SourceInstruction {
            instruction_index: 1
        }
    );
    for (language, source) in [
        (
            ResolvedInstructionLanguage::En,
            "arrange three red lines horizontally vertically at center.",
        ),
        (
            ResolvedInstructionLanguage::En,
            "arrange three red lines horizontally at center. the line vertically.",
        ),
        (
            ResolvedInstructionLanguage::En,
            "arrange a line and a circle vertically at center.",
        ),
        (
            ResolvedInstructionLanguage::Ja,
            "中央に、線と円を縦に並べる。",
        ),
    ] {
        assert!(
            stage15_transformation_input(&compile(source, language, &[])).is_err(),
            "{source}"
        );
    }
    let point = stage(
        "arrange three red point vertically at center.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    assert_eq!(
        plan_verified_stage15(point.verified_effective_view(), context("square")).outcome(),
        CompositionPlanOutcome::Ready
    );
    let angled_point = stage(
        "arrange three red horizontal point vertically at center.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    assert_eq!(
        plan_verified_stage15(angled_point.verified_effective_view(), context("square")).outcome(),
        CompositionPlanOutcome::Stopped
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
        ("triangle", Primitive::Triangle),
        ("polygon", Primitive::Polygon),
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
            ResolvedGeometryDimensions::Bbox { width, height } => {
                ratio(width, 6, 25);
                ratio(height, 6, 25);
            }
            ResolvedGeometryDimensions::RegularTriangle { side } => ratio(side, 6, 25),
            ResolvedGeometryDimensions::Polygon { radius, sides } => {
                ratio(radius, 3, 25);
                assert_eq!(sides, 5);
            }
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
fn macro_group_delivery_keeps_symbolic_count_and_exact_generated_origin() {
    let flat = definition(false, Some(json!({"expr":"integer","value":u32::MAX})));
    let mut grouped = serde_json::to_value(&flat).unwrap();
    grouped["body"] = json!([{"op":"group","body":[{"op":"group","body":grouped["body"]}]}]);
    let grouped = MacroDefinition::from_json(&grouped.to_string()).unwrap();
    let flat_stage = stage("Draw.Plan", ResolvedInstructionLanguage::En, &[flat]);
    let group_stage = stage("Draw.Plan", ResolvedInstructionLanguage::En, &[grouped]);
    let flat_plan = plan_verified_stage15(flat_stage.verified_effective_view(), context("square"));
    let group_plan =
        plan_verified_stage15(group_stage.verified_effective_view(), context("square"));
    let objects = group_plan
        .objects()
        .unwrap_or_else(|| panic!("{:?}", group_plan.diagnostics()));
    assert_eq!(objects.len(), 1);
    let object = &objects[0];
    let expected = &flat_plan.objects().unwrap()[0];
    assert_eq!(object.count(), u32::MAX);
    assert_eq!(object.dimensions(), expected.dimensions());
    assert_eq!(object.appearance(), expected.appearance());
    assert_eq!(object.recipe(), expected.recipe());
    let ScoreInstructionOrigin::MacroEmit { provenance, .. } = object.origin() else {
        panic!("Macro origin")
    };
    assert_eq!(provenance.generated_ordinal, 2);
    assert_eq!(
        provenance
            .expansion_path
            .iter()
            .filter(|segment| matches!(segment, ExpansionPathSegment::Group { .. }))
            .count(),
        2
    );
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
        "scatter four red wide equilateral triangle at center. scatter eight red circle at center. scatter four red sides 9 polygon at center.",
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
        "scatter four red wide equilateral triangle at center.",
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
