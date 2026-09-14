use inku_ddl::*;
use inku_score::{
    Color, Endpoint, InkSpread, Quality, Score, SurfaceTexture, TargetPathPosition,
    TargetPathSelection,
};
use serde_json::json;

#[test]
fn old_surface_aliases_use_current_meaning_and_self_endpoint_is_not_retargeted() {
    let spread = compile(
        "place red blurring circle at middle.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    let spread_score = compact(&spread);
    assert_eq!(
        spread_score.instructions[0].ink_spread,
        Some(InkSpread::Bleed)
    );
    assert_eq!(spread_score.instructions[0].variation, None);

    let aliases = compile(
        "中央に赤い震える点の円を置く。",
        ResolvedInstructionLanguage::Ja,
        &[],
    );
    let alias_score = compact(&aliases);
    assert_eq!(
        alias_score.instructions[0]
            .variation
            .as_ref()
            .unwrap()
            .quality,
        Quality::Perlin
    );
    assert_eq!(
        alias_score.instructions[0]
            .surface
            .as_ref()
            .unwrap()
            .texture,
        SurfaceTexture::Stipple
    );

    let source = "赤い線を引く。青い弧の終点を引く、前の線の始点につながる。";
    let compiled = compile_typed_ddl(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new()).unwrap(),
        &[],
        Some(19),
        MacroExpansionLimits {
            max_invocations: 8,
            max_depth: 8,
            max_evaluation_steps: 512,
            max_nodes_per_invocation: 64,
            max_total_nodes: 128,
        },
    );
    if let Ok(input) = stage15_transformation_input(&compiled) {
        let transformed = transform_stage15(input, None).unwrap();
        let lowered = lower_verified_stage15_score(
            transformed.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        );
        assert!(
            !lowered.diagnostics().is_empty(),
            "unsupported self endpoint must be diagnosed"
        );
    } else {
        assert!(
            !compiled.holes.is_empty()
                || !compiled.conflicts.is_empty()
                || !compiled.blocking_diagnostics.is_empty()
        );
    }
}

fn compile(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> Stage15TransformationResult {
    let compiled = typed_compilation(source, language, definitions);
    let input = stage15_transformation_input(&compiled).unwrap_or_else(|error| {
        panic!(
            "{source}: {error:?}; holes={:?}; conflicts={:?}; blocking={:?}; lexemes={:?}",
            compiled.holes,
            compiled.conflicts,
            compiled.blocking_diagnostics,
            parse_neutral_lexemes(
                &NormalizedDdlDocument::new(source, language, Vec::new()).unwrap()
            )
        )
    });
    transform_stage15(input, None).unwrap()
}

fn typed_compilation(
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
        MacroExpansionLimits {
            max_invocations: 8,
            max_depth: 8,
            max_evaluation_steps: 512,
            max_nodes_per_invocation: 64,
            max_total_nodes: 128,
        },
    )
}

fn compact(transformed: &Stage15TransformationResult) -> Score {
    use inku_score::{
        HardResourcePolicy, OperationalResourceBudget, ResourceBudget, ResourceDemand,
    };
    let plan = plan_verified_stage15(
        transformed.verified_effective_view(),
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
    );
    let budget = ResourceBudget {
        maximum: ResourceDemand {
            logical_objects: 128,
            primitive_marks: 128,
            object_templates: 64,
            maximum_per_template_primitive_marks: 128,
            maximum_resolved_count: 128,
            template_nodes: 128,
            anchor_instances: 128,
            transform_instances: 128,
            placement_instances: 128,
            fill_instances: 128,
        },
    };
    let selected = select_composition_plan_resources(
        &plan,
        HardResourcePolicy {
            identity: "endpoint-spread-test.v1".to_owned(),
            budget,
        },
        OperationalResourceBudget(budget),
    )
    .unwrap_or_else(|error| panic!("{error:?}: {:?}", plan.diagnostics()));
    materialize_selected_composition(&selected).unwrap().score
}

#[test]
fn target_endpoints_preserve_reference_and_endpoint_in_direct_and_compact_scores() {
    for (source, language, endpoint) in [
        (
            "赤い線を引く。青い弧を引く、前の線の始点につながる。",
            ResolvedInstructionLanguage::Ja,
            Endpoint::Start,
        ),
        (
            "place red arc. place blue line connected to the end of the previous arc.",
            ResolvedInstructionLanguage::En,
            Endpoint::End,
        ),
    ] {
        let transformed = compile(source, language, &[]);
        let lowered = lower_verified_stage15_score(
            transformed.verified_effective_view(),
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        );
        assert_eq!(
            lowered.outcome(),
            ScoreLoweringOutcome::Complete,
            "{:?}",
            lowered.diagnostics()
        );
        let compact = compact(&transformed);
        for score in [lowered.score().unwrap(), &compact] {
            assert_eq!(score.version, "0.12.0");
            let relation = score.instructions[1].relation.as_ref().unwrap();
            assert_eq!(relation.target_instruction_index, Some(0));
            assert_eq!(relation.target_endpoint, Some(endpoint));
            assert_eq!(relation.target_path_position, None);
        }
    }
    let legacy = compile(
        "place red line. place blue arc connected to the previous shape.",
        ResolvedInstructionLanguage::En,
        &[],
    );
    let score = compact(&legacy);
    assert_eq!(score.version, "0.10.0");
    assert_eq!(
        score.instructions[1]
            .relation
            .as_ref()
            .unwrap()
            .target_endpoint,
        None
    );
}

#[test]
fn partway_connections_preserve_line_and_arc_targets_in_canonical_direct_and_compact_delivery() {
    for (ja, en) in [
        (
            "赤い波打つ線を引く。斜めの小さな青い弧を引く、前の線の途中につながる。",
            "draw a red undulating line. draw a small diagonal blue arc connected partway along the previous line.",
        ),
        (
            "赤い揺れる弧を引く。小さな青い垂直の線を引く、前の弧の途中につながる。",
            "draw a red swaying arc. draw a small blue vertical line connected partway along the previous arc.",
        ),
    ] {
        let ja_compiled = typed_compilation(ja, ResolvedInstructionLanguage::Ja, &[]);
        let en_compiled = typed_compilation(en, ResolvedInstructionLanguage::En, &[]);
        assert_eq!(
            ja_compiled.pre_expansion_canonical_bytes(),
            en_compiled.pre_expansion_canonical_bytes()
        );
        assert!(
            std::str::from_utf8(ja_compiled.pre_expansion_canonical_bytes().unwrap())
                .unwrap()
                .contains("\"target_path_position\":\"interior\"")
        );

        for (source, language) in [
            (ja, ResolvedInstructionLanguage::Ja),
            (en, ResolvedInstructionLanguage::En),
        ] {
            let transformed = compile(source, language, &[]);
            let lowered = lower_verified_stage15_score(
                transformed.verified_effective_view(),
                ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            );
            assert_eq!(
                lowered.outcome(),
                ScoreLoweringOutcome::Complete,
                "{source}: {:?}",
                lowered.diagnostics()
            );
            let compact = compact(&transformed);
            for score in [lowered.score().unwrap(), &compact] {
                assert_eq!(score.version, "0.13.0");
                let relation = score.instructions[1].relation.as_ref().unwrap();
                assert_eq!(relation.target_instruction_index, Some(0));
                assert_eq!(relation.target_endpoint, None);
                assert_eq!(
                    relation.target_path_position,
                    Some(TargetPathPosition::Selection(TargetPathSelection::Interior))
                );
            }
        }
    }
}

#[test]
fn independent_spread_keeps_wave_perlin_and_stipple_without_implicit_motion() {
    let transformed = compile(
        "にじみの赤い円を置く。波打つにじみの青い線を引く。揺れる点描にじみの灰の円を置く。",
        ResolvedInstructionLanguage::Ja,
        &[],
    );
    let lowered = lower_verified_stage15_score(
        transformed.verified_effective_view(),
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
    );
    assert_eq!(
        lowered.outcome(),
        ScoreLoweringOutcome::Complete,
        "{:?}",
        lowered.diagnostics()
    );
    let compact = compact(&transformed);
    for score in [lowered.score().unwrap(), &compact] {
        assert_eq!(score.version, "0.12.0");
        assert!(
            score
                .instructions
                .iter()
                .all(|instruction| instruction.ink_spread == Some(InkSpread::Bleed))
        );
        assert_eq!(score.instructions[0].variation, None);
        assert_eq!(
            score.instructions[1].variation.as_ref().unwrap().quality,
            Quality::Wave
        );
        assert_eq!(
            score.instructions[2].variation.as_ref().unwrap().quality,
            Quality::Perlin
        );
        assert_eq!(
            score.instructions[2].surface.as_ref().unwrap().texture,
            SurfaceTexture::Stipple
        );
    }
}

#[test]
fn macro_endpoint_and_spread_survive_shared_transform_and_compact_materialization() {
    let emit = |name: &str, shape: &str| {
        json!({"op":"emit", "binding":name, "fields":{
            "shape":{"expr":"semantic_ref","category":"shape","id":shape},
            "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
            "color":{"expr":"semantic_ref","category":"color","id":"red"},
            "ink_spread":{"expr":"semantic_ref","category":"variation","id":"bleeding"}
        }})
    };
    let mut value = json!({"schema":"inku.macro-definition.v1", "namespace":"Test", "heading":"Endpoints", "version":"1.0.0", "parameters":{},"components":{}, "body":[
        {"op":"transform","transform":{"rotate_degrees":{"expr":"number","value":135},"scale_x":{"expr":"number","value":-1}},"body":[
            emit("host", "arc"), emit("follower", "line"),
            {"op":"relation","kind":"connected","from":"host","to":"follower","target_endpoint":"start"}
        ]}
    ]});
    let definition = MacroDefinition::from_json(&value.to_string()).unwrap();
    let transformed = compile(
        "Test.Endpoints",
        ResolvedInstructionLanguage::En,
        &[definition],
    );
    let score = compact(&transformed);
    assert_eq!(score.version, "0.12.0");
    assert!(
        score
            .instructions
            .iter()
            .all(
                |instruction| instruction.ink_spread == Some(InkSpread::Bleed)
                    && instruction.variation.is_none()
            )
    );
    assert_eq!(
        score.instructions[1]
            .relation
            .as_ref()
            .unwrap()
            .target_endpoint,
        Some(Endpoint::Start)
    );
    assert_eq!(score.transform_groups.len(), 1);
    value["body"][0]["body"][2]["target_path_position"] = json!({"expr":"number","value":0.5});
    let conflict = MacroDefinition::from_json(&value.to_string()).unwrap();
    assert!(conflict.identity().is_err());
}
