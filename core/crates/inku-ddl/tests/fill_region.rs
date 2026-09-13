use inku_ddl::*;
use inku_score::{Color, Primitive};
use serde_json::json;

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 128,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

fn stage(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> Stage15TransformationResult {
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
    let compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, locks).unwrap(),
        definitions,
        Some(19),
        LIMITS,
    );
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

fn fill(object: &ObjectPlacementPlan) -> (&ResolvedFillRegion, &FillCountResolution) {
    match object.recipe() {
        PlacementRecipe::FillUniformInRegionAndClip {
            region,
            count_resolution,
        } => (region, count_resolution),
        other => panic!("fill recipe required: {other:?}"),
    }
}

#[test]
fn omitted_fill_count_tracks_region_and_declared_extent_not_appearance() {
    for (source, count) in [
        ("fill red circle.", 18),
        ("fill red empty circle.", 18),
        ("fill red pencil circle.", 18),
        ("fill red circle diameter 0.12.", 70),
        ("fill red point.", 6945),
        ("fill with points.", 6945),
    ] {
        let transformed = stage(source, ResolvedInstructionLanguage::En, &[]);
        let plan = plan_verified_stage15(transformed.verified_effective_view(), context("square"));
        let objects = plan
            .objects()
            .unwrap_or_else(|| panic!("{source}: {:?}", plan.diagnostics()));
        assert_eq!(objects.len(), 1);
        assert_eq!(objects[0].count(), count, "{source}");
        assert!(objects[0].count_was_omitted());
        let (region, resolution) = fill(&objects[0]);
        assert_eq!(region.owner, FillRegionOwner::OmittedCanvas);
        assert!(matches!(
            resolution,
            FillCountResolution::FromRegionAndExtent { .. }
        ));
    }
    let transformed = stage("点で埋める。", ResolvedInstructionLanguage::Ja, &[]);
    let plan = plan_verified_stage15(transformed.verified_effective_view(), context("wide"));
    assert!(plan.objects().unwrap()[0].count() > 6945);
}

#[test]
fn named_fill_is_an_area_and_explicit_count_stays_lossless() {
    let transformed = stage(
        "fill red point at corner.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    let plan = plan_verified_stage15(transformed.verified_effective_view(), context("square"));
    let object = &plan.objects().unwrap()[0];
    assert_eq!(object.count(), 278);
    assert!(matches!(fill(object).0.owner, FillRegionOwner::Named(_)));
    for count in [1, 12, u32::MAX] {
        let transformed = stage(
            &format!("fill {count} red arc at corner."),
            ResolvedInstructionLanguage::En,
            &[],
        );
        let plan = plan_verified_stage15(transformed.verified_effective_view(), context("square"));
        let object = &plan.objects().unwrap()[0];
        assert_eq!(object.count(), count);
        assert_eq!(fill(object).1, &FillCountResolution::Explicit);
        assert!(!object.count_was_omitted());
        let actual =
            lower_verified_stage15_score(transformed.verified_effective_view(), context("square"));
        assert!(actual.score().is_none());
        assert!(
            actual
                .diagnostics()
                .iter()
                .any(|d| d.reason == ScoreFieldGap::FillRequiresRegionMaterialization)
        );
    }
}

#[test]
fn inline_nonrectangular_regions_keep_target_geometry_and_source_owner() {
    for (shape, expected) in [
        ("circle", Primitive::Circle),
        ("ellipse", Primitive::Ellipse),
        ("triangle", Primitive::Triangle),
        ("hexagon", Primitive::Polygon),
        ("crescent arc", Primitive::Arc),
        ("cloudform", Primitive::Cloudform),
    ] {
        let source = format!("fill a {shape} with red points.");
        let transformed = stage(&source, ResolvedInstructionLanguage::En, &[]);
        let plan = plan_verified_stage15(transformed.verified_effective_view(), context("square"));
        let objects = plan
            .objects()
            .unwrap_or_else(|| panic!("{source}: {:?}", plan.diagnostics()));
        assert_eq!(objects.len(), 1, "target must not become another drawing");
        let object = &objects[0];
        assert_eq!(object.primitive(), Primitive::Point);
        let (region, _) = fill(object);
        assert!(matches!(
            region.owner,
            FillRegionOwner::InlineShape {
                source_instruction_index: 0,
                ..
            }
        ));
        assert!(
            matches!(region.geometry, FillRegionGeometry::Shape { primitive, .. } if primitive == expected)
        );
        assert!(object.count() > 1 && object.count() < 6945);
        if expected == Primitive::Circle {
            assert_eq!(object.count(), 315);
        }
    }
    let transformed = stage(
        "fill a circle diameter 0.5 at horizontal 0.5 vertical 0.5 with red points.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    let plan = plan_verified_stage15(transformed.verified_effective_view(), context("square"));
    let object = &plan
        .objects()
        .unwrap_or_else(|| panic!("{:?}", plan.diagnostics()))[0];
    assert_eq!(object.count(), 1364);
    assert!(matches!(
        fill(object).0.geometry,
        FillRegionGeometry::Shape {
            anchor: ObjectAnchor::Numeric(_),
            ..
        }
    ));
    let transformed = stage(
        "fill a small circle diameter 0.5 with red points.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    // An inline target needs no color/palette resolution of its own.
    let plan = plan_verified_stage15(
        transformed.verified_effective_view(),
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
    );
    assert_eq!(plan.objects().unwrap()[0].count(), 79);
    assert!(plan.diagnostics().iter().any(|diagnostic| matches!(
        diagnostic.reason,
        ScoreFieldGap::ConflictingSizeSpecifications { .. }
    ) && matches!(
        diagnostic.owner,
        ScoreDiagnosticOwner::SourceInstruction {
            instruction_index: 0,
            ..
        }
    ) && diagnostic.disposition
        == ScoreDiagnosticDisposition::Recovered));
}

#[test]
fn declared_macro_and_direct_fill_share_count_geometry_and_clip_recipe() {
    let definition = MacroDefinition::from_json(&json!({
        "schema":"inku.macro-definition.v1", "namespace":"Fill", "heading":"Dots", "version":"1.0.0",
        "parameters":{}, "components":{}, "body":[{"op":"emit", "binding":null, "fields":{
            "shape":{"expr":"semantic_ref","category":"shape","id":"point"},
            "movement":{"expr":"semantic_ref","category":"movement","id":"fill"},
            "color":{"expr":"semantic_ref","category":"color","id":"red"}
        }}]
    }).to_string()).unwrap();
    let generated = stage("Fill.Dots", ResolvedInstructionLanguage::En, &[definition]);
    let direct = stage("fill red point.", ResolvedInstructionLanguage::En, &[]);
    let generated = plan_verified_stage15(generated.verified_effective_view(), context("square"));
    let direct = plan_verified_stage15(direct.verified_effective_view(), context("square"));
    let g = &generated
        .objects()
        .unwrap_or_else(|| panic!("{:?}", generated.diagnostics()))[0];
    let d = &direct.objects().unwrap()[0];
    assert_eq!(g.count(), d.count());
    assert_eq!(g.dimensions(), d.dimensions());
    assert_eq!(g.recipe(), d.recipe());
    assert!(matches!(
        g.origin(),
        ScoreInstructionOrigin::MacroEmit { .. }
    ));
}

#[test]
fn coordinated_fill_uses_one_density_budget_and_one_region_owner() {
    for (source, counts) in [
        ("赤い円と青い点で埋める。", vec![18, 17]),
        ("三つの赤い円と青い点で埋める。", vec![3, 5745]),
        ("三つの赤い円と四つの青い点で埋める。", vec![3, 4]),
        ("隅を赤い円と青い点で埋める。", vec![1, 1]),
        ("円を赤い点と青い点で埋める。", vec![158, 157]),
    ] {
        let transformed = stage(source, ResolvedInstructionLanguage::Ja, &[]);
        let plan = plan_verified_stage15(transformed.verified_effective_view(), context("square"));
        let objects = plan
            .objects()
            .unwrap_or_else(|| panic!("{source}: {:?}", plan.diagnostics()));
        assert_eq!(
            objects
                .iter()
                .map(ObjectPlacementPlan::count)
                .collect::<Vec<_>>(),
            counts,
            "{source}"
        );
        assert!(
            plan.placement_groups().is_empty(),
            "fill is not a scatter layout alias"
        );
        assert_eq!(plan.fill_groups().len(), 1, "{source}");
        let group = &plan.fill_groups()[0];
        assert_eq!(
            group.logical_count,
            counts.iter().map(|count| u64::from(*count)).sum::<u64>()
        );
        assert_eq!(group.members.len(), 2);
        assert!(matches!(
            group.recipe,
            PlacementRecipe::FillUniformInRegionAndClip {
                count_resolution: FillCountResolution::BalancedGroup { .. },
                ..
            }
        ));
        assert!(
            objects
                .iter()
                .all(|object| object.recipe() == &PlacementRecipe::Place)
        );
        let score =
            lower_verified_stage15_score(transformed.verified_effective_view(), context("square"));
        assert!(score.score().is_none());
        assert!(score.diagnostics().iter().any(
            |diagnostic| diagnostic.reason == ScoreFieldGap::FillRequiresRegionMaterialization
        ));
    }
}

#[test]
fn macro_motifs_keep_complete_body_and_share_density_resolution() {
    let emit = |shape: &str, x: &str| {
        json!({"op":"emit","binding":null,"fields":{
            "shape":{"expr":"semantic_ref","category":"shape","id":shape},
            "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
            "color":{"expr":"semantic_ref","category":"color","id":"red"},
            "position_x":{"expr":"exact_decimal","value":x},
            "position_y":{"expr":"exact_decimal","value":"0.5"}
        }})
    };
    let mut diagonal_square = emit("square", "0.5");
    diagonal_square["fields"]["angle"] =
        json!({"expr":"semantic_ref","category":"angle","id":"diagonal"});
    let direct = stage(
        "fill red diagonal square.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    let direct = plan_verified_stage15(direct.verified_effective_view(), context("square"));
    assert_eq!(direct.objects().unwrap()[0].count(), 18);
    let single = emit("circle", "0.5");
    let rotated = json!({"op":"transform","transform":{"rotate_degrees":{"expr":"number","value":45.0}},"body":[single.clone()]});
    let pair = json!([emit("circle", "0.3"), emit("circle", "0.7")]);
    let scaled = json!([{"op":"transform","transform":{"scale_x":{"expr":"number","value":2.0},"scale_y":{"expr":"number","value":2.0}},"body":pair.clone()}]);
    for (body, expected, object_count, transform_count) in [
        (json!([single]), 18, 1, 0),
        (json!([diagonal_square]), 18, 1, 0),
        (json!([rotated]), 18, 1, 1),
        (pair, 3, 2, 0),
        (scaled, 1, 2, 1),
    ] {
        let definition = MacroDefinition::from_json(&json!({
            "schema":"inku.macro-definition.v1","namespace":"Fill","heading":"Motif","version":"1.0.0",
            "parameters":{},"components":{},"body":body
        }).to_string()).unwrap();
        let transformed = stage(
            "fill with Fill.Motif.",
            ResolvedInstructionLanguage::En,
            &[definition],
        );
        let plan = plan_verified_stage15(transformed.verified_effective_view(), context("square"));
        assert_eq!(
            plan.objects()
                .unwrap_or_else(|| panic!("{:?}", plan.diagnostics()))
                .len(),
            object_count
        );
        assert_eq!(plan.transform_groups().len(), transform_count);
        assert_eq!(plan.fill_groups().len(), 1, "{:?}", plan.diagnostics());
        let group = &plan.fill_groups()[0];
        assert_eq!(
            group.owner,
            FillPlanOwner::Instruction {
                source_instruction_index: 0
            }
        );
        assert_eq!(group.logical_count, expected);
        assert_eq!(u64::from(group.members[0].logical_count()), expected);
        assert!(group.members[0].count_was_omitted());
        assert!(
            plan.objects()
                .unwrap()
                .iter()
                .all(|object| object.count() == 1)
        );
    }
    let mut repeated = emit("circle", "0.5");
    repeated["fields"]["movement"] =
        json!({"expr":"semantic_ref","category":"movement","id":"scatter"});
    repeated["fields"]["count"] = json!({"expr":"integer","value":1000000});
    let definition = MacroDefinition::from_json(&json!({
        "schema":"inku.macro-definition.v1","namespace":"Fill","heading":"Motif","version":"1.0.0",
        "parameters":{},"components":{},"body":[repeated]
    }).to_string()).unwrap();
    let transformed = stage(
        "fill with Fill.Motif and blue points.",
        ResolvedInstructionLanguage::En,
        &[definition],
    );
    let plan = plan_verified_stage15(transformed.verified_effective_view(), context("square"));
    assert_eq!(
        plan.objects()
            .unwrap_or_else(|| panic!("{:?}", plan.diagnostics()))
            .len(),
        2
    );
    assert_eq!(plan.objects().unwrap()[0].count(), 1000000);
    assert_eq!(plan.fill_groups().len(), 1);
    assert_eq!(plan.fill_groups()[0].members.len(), 2);
    assert_eq!(
        plan.fill_groups()[0].members[0].kind(),
        PlacementMemberKind::Macro
    );
    assert!(matches!(
        plan.fill_groups()[0].owner,
        FillPlanOwner::CoordinatedGroup { .. }
    ));
}

#[test]
fn invalid_area_numeric_motif_and_overflow_recover_without_losing_other_drawings() {
    for (source, reason) in [
        (
            "fill two circles with red points. place one blue circle.",
            ScoreFieldGap::InvalidFillTarget,
        ),
        (
            "fill a line with red points. place one blue circle.",
            ScoreFieldGap::FillRegionHasNoArea,
        ),
        (
            "fill red point at horizontal 0.5 vertical 0.5. place one blue circle.",
            ScoreFieldGap::InvalidFillTarget,
        ),
        (
            "fill red point diameter 0.000001. place one blue circle.",
            ScoreFieldGap::FillCountExceedsScoreRange,
        ),
    ] {
        let transformed = stage(source, ResolvedInstructionLanguage::En, &[]);
        let plan = plan_verified_stage15(transformed.verified_effective_view(), context("square"));
        let objects = plan
            .objects()
            .unwrap_or_else(|| panic!("{source}: {:?}", plan.diagnostics()));
        assert_eq!(objects.len(), 1);
        assert_eq!(objects[0].primitive(), Primitive::Circle);
        assert!(
            plan.diagnostics().iter().any(|d| d.reason == reason),
            "{source}: {:?}",
            plan.diagnostics()
        );
    }
}
