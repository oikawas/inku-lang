//! Test-only object words: their body coordinates belong to one local box.
use inku_ddl::{
    MacroDefinition, MacroExpansionLimits, MacroLock, NormalizedDdlDocument,
    ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext,
    compile_ddl_to_score_with_resources,
};
use inku_score::{
    Color, HardResourcePolicy, OperationalResourceBudget, ResourceBudget, ResourceDemand,
};
use serde_json::{Value, json};

fn arc(binding: &str, x: &str, rotation: &str) -> Value {
    let emit = json!({"op":"emit","binding":binding,"fields":{
        "shape":{"expr":"semantic_ref","category":"shape","id":"arc"},
        "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
        "color":{"expr":"semantic_ref","category":"color","id":"green"},
        "position_x":{"expr":"exact_decimal","value":x},
        "position_y":{"expr":"exact_decimal","value":"0.5"},
        "chord":{"expr":"exact_decimal","value":"0.6"},
        "sagitta":{"expr":"exact_decimal","value":"0.2"}
    }});
    if rotation == "180" {
        json!({"op":"transform","transform":{"rotate_degrees":{"expr":"number","value":180.0}},"body":[emit]})
    } else {
        emit
    }
}

fn word(id: &str, ja: &str, en: &str, aspect: &str, body: Value) -> MacroDefinition {
    let definition = MacroDefinition::from_json(
        &json!({
            "schema":"inku.macro-definition.v2", "namespace":"TestObject", "id":id,
            "names":{"ja":[ja],"en":[en]}, "kind":"object", "aspect":aspect,
            "counter":"flat", "version":"1.0.0", "parameters":{}, "components":{}, "body":body
        })
        .to_string(),
    )
    .unwrap();
    assert!(
        definition.validate().is_valid(),
        "{:?}",
        definition.validate().diagnostics()
    );
    definition
}

fn lock(definition: &MacroDefinition) -> MacroLock {
    let identity = definition.identity().unwrap();
    MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap()
}

#[test]
fn japanese_square_accepts_an_explicit_position_without_the_canvas_prefix() {
    let result = inku_ddl::compile_ddl_to_score(
        NormalizedDdlDocument::new(
            "横0.3、縦0.7の位置に、幅0.2、高さ0.1の黒い四角を置く。",
            ResolvedInstructionLanguage::Ja,
            vec![],
        )
        .unwrap(),
        &[],
        Some(37),
        MacroExpansionLimits {
            max_invocations: 64,
            max_depth: 16,
            max_evaluation_steps: 8192,
            max_nodes_per_invocation: 128,
            max_total_nodes: 128,
        },
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert!(
        result.upstream_diagnostics().is_empty(),
        "{:?}",
        result.upstream_diagnostics()
    );
    assert!(
        result
            .score()
            .is_some_and(|score| !score.instructions.is_empty())
    );
}

#[test]
#[ignore = "object placement and rendering are not connected yet"]
fn a_declared_color_reaches_the_object_body() {
    let leaf = word(
        "Leaf",
        "葉",
        "leaf",
        "1:1",
        json!([arc("upper", "0.5", "0")]),
    );
    let mut raw = serde_json::to_value(leaf).unwrap();
    raw["parameters"]["hue"] = json!({"type":"semantic_ref", "category":"color"});
    raw["body"][0]["fields"]["color"] = json!({"expr":"parameter", "name":"hue"});
    let leaf = MacroDefinition::from_json(&raw.to_string()).unwrap();
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
    let result = compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(
            "赤い｛葉｝を置く。",
            ResolvedInstructionLanguage::Ja,
            vec![lock(&leaf)],
        )
        .unwrap(),
        &[leaf],
        Some(37),
        MacroExpansionLimits {
            max_invocations: 64,
            max_depth: 16,
            max_evaluation_steps: 8192,
            max_nodes_per_invocation: 128,
            max_total_nodes: 128,
        },
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
        HardResourcePolicy {
            identity: "object-test.v1".into(),
            budget,
        },
        OperationalResourceBudget(budget),
    );
    assert!(
        result.upstream_diagnostics().is_empty(),
        "{:?}",
        result.upstream_diagnostics()
    );
    assert!(
        result.downstream_diagnostics().is_empty(),
        "{:?}",
        result.downstream_diagnostics()
    );
    let score = result.score().unwrap();
    assert_eq!(
        score.object_templates[0].body.instructions[0].color,
        Color::Red
    );
}

#[test]
#[ignore = "object placement and rendering are not connected yet"]
fn object_box_placement_matches_a_square_with_the_same_meaning() {
    let leaf = word(
        "Leaf",
        "葉",
        "leaf",
        "1:1",
        json!([arc("upper", "0.5", "0"), arc("lower", "0.5", "180")]),
    );
    let definitions = [leaf];
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
    let compile = |source: &str, locks: Vec<MacroLock>, definitions: &[MacroDefinition]| {
        compile_ddl_to_score_with_resources(
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, locks).unwrap(),
            definitions,
            Some(37),
            MacroExpansionLimits {
                max_invocations: 64,
                max_depth: 16,
                max_evaluation_steps: 8192,
                max_nodes_per_invocation: 128,
                max_total_nodes: 128,
            },
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            ScoreErrorPolicy::OmitAndContinue,
            HardResourcePolicy {
                identity: "object-test.v1".into(),
                budget,
            },
            OperationalResourceBudget(budget),
        )
    };
    for (object, square) in [
        ("上に｛葉｝を8枚散らす。", "上に黒い四角を8個散らす。"),
        ("｛葉｝を5枚並べる。", "黒い四角を5個並べる。"),
        (
            "横0.3、縦0.7の位置に、幅0.2、高さ0.1の｛葉｝を置く。",
            "横0.3、縦0.7の位置に、幅0.2、高さ0.1の黒い四角を置く。",
        ),
    ] {
        let actual = compile(object, vec![lock(&definitions[0])], &definitions);
        let expected = compile(square, vec![], &[]);
        assert!(
            actual.upstream_diagnostics().is_empty() && actual.downstream_diagnostics().is_empty(),
            "{object}: {:?} {:?}",
            actual.upstream_diagnostics(),
            actual.downstream_diagnostics()
        );
        assert!(
            expected.upstream_diagnostics().is_empty()
                && expected.downstream_diagnostics().is_empty(),
            "{square}: {:?} {:?}",
            expected.upstream_diagnostics(),
            expected.downstream_diagnostics()
        );
        let a = &actual.score().unwrap().instructions[0];
        let b = &expected.score().unwrap().instructions[0];
        assert_eq!(
            (a.position, a.size, a.rotation, &a.arrangement),
            (b.position, b.size, b.rotation, &b.arrangement),
            "{object}"
        );
    }
}

#[test]
#[ignore = "object placement and rendering are not connected yet"]
fn object_word_draws_instead_of_being_rejected() {
    let leaf = word(
        "Leaf",
        "葉",
        "leaf",
        "1:1",
        json!([arc("upper", "0.5", "0"), arc("lower", "0.5", "180")]),
    );
    let boat = word(
        "Boat",
        "舟",
        "boat",
        "2:1",
        json!([arc("hull", "0.5", "0")]),
    );
    let definitions = [leaf, boat];
    let locks = definitions.iter().map(lock).collect::<Vec<_>>();
    for (source, language) in [
        ("上に｛葉｝を8枚散らす。", ResolvedInstructionLanguage::Ja),
        (
            "Scatter 8 {leaf} at the top.",
            ResolvedInstructionLanguage::En,
        ),
        (
            "中心に大きい｛舟｝を置く。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "横0.3、縦0.7の位置に、幅0.2、高さ0.1の｛舟｝を置く。",
            ResolvedInstructionLanguage::Ja,
        ),
        ("上に｛葉｝を60枚散らす。", ResolvedInstructionLanguage::Ja),
        ("｛葉｝を5枚並べる。", ResolvedInstructionLanguage::Ja),
        ("右上がりの｛舟｝を置く。", ResolvedInstructionLanguage::Ja),
        ("赤い｛葉｝を置く。", ResolvedInstructionLanguage::Ja),
    ] {
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
        let result = compile_ddl_to_score_with_resources(
            NormalizedDdlDocument::new(source, language, locks.clone()).unwrap(),
            &definitions,
            Some(37),
            MacroExpansionLimits {
                max_invocations: 64,
                max_depth: 16,
                max_evaluation_steps: 8192,
                max_nodes_per_invocation: 128,
                max_total_nodes: 128,
            },
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            ScoreErrorPolicy::OmitAndContinue,
            HardResourcePolicy {
                identity: "object-test.v1".into(),
                budget,
            },
            OperationalResourceBudget(budget),
        );
        assert!(
            result
                .score()
                .is_some_and(|score| !score.instructions.is_empty()),
            "{source}: {:?} {:?}",
            result.upstream_diagnostics(),
            result.downstream_diagnostics()
        );
        assert!(
            result.upstream_diagnostics().is_empty(),
            "{source}: {:?}",
            result.upstream_diagnostics()
        );
        if source.contains("赤い") {
            assert_eq!(
                result.downstream_diagnostics().len(),
                1,
                "{source}: {:?}",
                result.downstream_diagnostics()
            );
            assert_eq!(
                result.downstream_diagnostics()[0].reason,
                inku_ddl::ScoreFieldGap::UnboundMacroCallerMeaning
            );
        } else {
            assert!(
                result.downstream_diagnostics().is_empty(),
                "{source}: {:?}",
                result.downstream_diagnostics()
            );
        }
        let score = result.score().unwrap();
        if source == "上に｛葉｝を8枚散らす。" {
            let request = inku_render::types::RenderRequest {
                score: score.clone(),
                options: inku_render::types::RenderOptions {
                    resolved_color_map: Default::default(),
                    catalog_id: None,
                    canvas: inku_render::types::CanvasSize::new(1000.0, 1000.0),
                    canvas_aspect_id: "square".into(),
                    svg_profile: inku_render::types::SvgProfile::Display,
                    render_seed: Some(17),
                    composition_seed: Some(37),
                    wild: false,
                    error_policy: ScoreErrorPolicy::OmitAndContinue,
                },
            };
            let clip = inku_render::render::CompatFillClipPolicy {
                tolerance_pixels: 0.1,
                limits: inku_render::compat_clip::ClipLimits {
                    max_nodes: 50_000,
                    max_path_elements: 200_000,
                    max_flattened_points: 200_000,
                    max_work: 10_000_000,
                    max_output_vertices: 200_000,
                },
            };
            let picture = inku_render::render::render_with_resources(
                request,
                &HardResourcePolicy {
                    identity: "object-test.v1".into(),
                    budget,
                },
                OperationalResourceBudget(budget),
                clip,
            )
            .unwrap();
            assert!(
                picture.svg.matches("<path").count() >= 16,
                "{}",
                picture.svg
            );
        }
        let restored = inku_score::finalize_saved_score(
            score,
            &HardResourcePolicy {
                identity: "object-test.v1".into(),
                budget,
            },
            OperationalResourceBudget(budget),
        )
        .unwrap();
        assert_eq!(restored.demand, result.demand().unwrap(), "{source}");
        assert_eq!(restored.score.object_templates.len(), 1);
        let saved = inku_score::canonical_json_bytes(&restored.score).unwrap();
        assert_eq!(
            inku_score::read_saved_score_json(&saved).unwrap(),
            restored.score
        );
        if source.contains("8枚") || source.contains("8 {leaf}") {
            assert_eq!(result.demand().unwrap().primitive_marks, 16);
            assert_eq!(result.demand().unwrap().object_templates, 3);
        }
        assert_eq!(score.version, "0.23.0");
        assert_eq!(score.object_templates.len(), 1);
        assert_eq!(
            score.object_templates[0].body.instructions.len(),
            if source.contains("葉") || source.contains("leaf") {
                2
            } else {
                1
            }
        );
        let box_instruction = &score.instructions[score.object_templates[0].instruction_index];
        if source.contains("横0.3") {
            let anchor = &box_instruction
                .arrangement
                .as_ref()
                .unwrap()
                .resolved
                .as_ref()
                .unwrap()
                .anchor;
            assert!(
                matches!(anchor, inku_score::ResolvedPlacementAnchor::Numeric { point } if (point.x - 0.3).abs() < 1e-9 && (point.y - 0.7).abs() < 1e-9)
            );
        }
        let size = box_instruction.size.unwrap();
        if source.contains("舟") {
            let expected = if source.contains("幅0.2") {
                (0.2, 0.1)
            } else {
                (0.36, 0.18)
            };
            let expected = if source.contains("右上がり") {
                (0.24, 0.12)
            } else {
                expected
            };
            assert!(
                (size.x - expected.0).abs() < 1e-9 && (size.y - expected.1).abs() < 1e-9,
                "{size:?}"
            );
            if source.contains("右上がり") {
                assert!(box_instruction.rotation.is_some());
            }
        } else {
            assert_eq!(
                box_instruction.arrangement.as_ref().unwrap().count,
                if source.contains("60") {
                    60
                } else if source.contains("5枚") {
                    5
                } else if source.contains("赤い") {
                    1
                } else {
                    8
                }
            );
            assert!((size.x - size.y).abs() < 1e-9);
            if source.contains("赤い") {
                assert!(
                    score.object_templates[0]
                        .body
                        .instructions
                        .iter()
                        .all(|item| item.color == Color::Green)
                );
            }
        }
    }
}
