use inku_ddl::{
    CompilerExecutionDisposition, CompilerExecutionOmissionUnit, CompilerLockState,
    CompilerRenderExecutionError, CompilerRenderOwner, MacroDefinition, MacroExpansionLimits,
    MacroLock, NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreDiagnosticDisposition,
    ScoreErrorPolicy, ScoreFieldGap, ScoreInstructionField, ScoreInstructionOrigin,
    ScoreLoweringContext, ScoreLoweringOutcome, ScoreOmissionUnit, SemanticPreviousReference,
    SemanticRelationKind, compile_ddl_to_score, compile_typed_ddl,
    map_compiler_render_execution, saijiki_asset, stage15_transformation_input,
};
use inku_render::checked_performance::resolve_checked_performance;
use inku_render::performance::PerformanceRequest;
use inku_score::{
    Canvas, Color, GroundMaterial, Primitive, RelationType, ScoreExecutionDiagnostic,
    ScoreExecutionDisposition, ScoreExecutionReason, ScoreExecutionSummary, canonical_score_digest,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 64,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

#[test]
fn exact_decimal_macro_geometry_and_coordinates_share_direct_score_and_recovery() {
    use serde_json::json;
    for (shape, dimensions, direct) in [
        ("circle", vec![("radius", "0.1")], "radius 0.1"),
        ("point", vec![("diameter", "0.012")], "diameter 0.012"),
        ("line", vec![("length", "0.2")], "length 0.2"),
        ("square", vec![("side", "0.2")], "side length 0.2"),
        (
            "ellipse",
            vec![("width", "0.3"), ("height", "0.2")],
            "width 0.3 height 0.2",
        ),
        (
            "arc",
            vec![("chord", "0.2"), ("sagitta", "0.05")],
            "chord 0.2 sagitta 0.05",
        ),
        (
            "circle",
            vec![("radius", "0.2"), ("diameter", "0.1")],
            "radius 0.2 diameter 0.1",
        ),
    ] {
        let mut fields = json!({"shape":{"expr":"semantic_ref","category":"shape","id":shape},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"color":{"expr":"semantic_ref","category":"color","id":"red"},"position_x":{"expr":"exact_decimal","value":"0.5"},"position_y":{"expr":"exact_decimal","value":"0.5"}});
        for (key, value) in dimensions {
            fields[key] = json!({"expr":"exact_decimal","value":value});
        }
        let definition = MacroDefinition::from_json(&json!({"schema":"inku.macro-definition.v1","namespace":"Exact","heading":"Mark","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":fields}]}).to_string()).unwrap();
        let actual = execute_locked("Exact.Mark", &[definition], LIMITS, ScoreErrorPolicy::Stop);
        let expected = execute(
            &format!("place one red {shape} {direct} at horizontal 0.5 vertical 0.5."),
            &[],
            LIMITS,
            ScoreErrorPolicy::Stop,
        );
        assert!(
            actual.score().is_some(),
            "{shape}: {:?} {:?}",
            actual.upstream_diagnostics(),
            actual.downstream_diagnostics()
        );
        assert!(
            expected.score().is_some(),
            "{shape}: {:?} {:?}",
            expected.upstream_diagnostics(),
            expected.downstream_diagnostics()
        );
        assert_eq!(actual.score(), expected.score(), "{shape}: {direct}");
        assert_eq!(
            actual.downstream_diagnostics().len(),
            expected.downstream_diagnostics().len()
        );
        assert!(matches!(
            actual.instruction_origins()[0],
            ScoreInstructionOrigin::MacroEmit { .. }
        ));
    }
}

#[test]
fn exact_decimal_declared_caller_geometry_is_consumed_once_and_numeric_place_conflicts() {
    use serde_json::json;
    let mut data = json!({"schema":"inku.macro-definition.v1","namespace":"Exact","heading":"Mark","version":"1.0.0",
        "parameters":{"r":{"type":"exact_decimal","dimension":"radius"},"y":{"type":"exact_decimal","dimension":"position_x"},"x":{"type":"exact_decimal","dimension":"position_y"}},"components":{},
        "body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"color":{"expr":"semantic_ref","category":"color","id":"red"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"radius":{"expr":"parameter","name":"r"},"position_x":{"expr":"parameter","name":"y"},"position_y":{"expr":"parameter","name":"x"}}}]});
    let definition = MacroDefinition::from_json(&data.to_string()).unwrap();
    let result = execute_locked(
        "Exact.Mark radius 0.10 horizontal 0.3 vertical 0.7",
        &[definition],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    assert!(
        result.score().is_some(),
        "{:?} {:?}",
        result.upstream_diagnostics(),
        result.downstream_diagnostics()
    );
    let expected = execute(
        "place one red circle radius 0.1 at horizontal 0.3 vertical 0.7.",
        &[],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    assert_eq!(result.score(), expected.score());
    data["body"][0]["fields"]["place"] =
        json!({"expr":"semantic_ref","category":"place","id":"center"});
    let definition = MacroDefinition::from_json(&data.to_string()).unwrap();
    let conflict = execute_locked(
        "Exact.Mark radius 0.1 horizontal 0.3 vertical 0.7",
        &[definition],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    assert!(conflict.score().is_none());
    assert!(
        conflict
            .downstream_diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                diagnostic.reason,
                ScoreFieldGap::NamedAndNumericPositionConflict
            ))
    );
}

#[test]
fn touching_full_literal_reaches_actual_score() {
    let result = execute(
        "place one red line at center. place one blue arc at center touching the previous line.",
        &[],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::Complete,
        "{:?}",
        result.downstream_diagnostics()
    );
    let score = result
        .score()
        .expect("Touching must reach the actual Score");
    assert_eq!(
        score.instructions[1].relation.as_ref().unwrap().kind,
        RelationType::Touching
    );
}

#[test]
fn touching_bilingual_targets_reach_performed_both_ends_and_reject_wrong_nouns() {
    use inku_render::planning::endpoint_geometry;
    use inku_render::types::CanvasSize;
    let sources = [
        (
            "place one red line at center. place one blue arc at center touching the previous line. place one green arc at center touching the previous arc at both ends. place one yellow line at center touching the previous arc at both ends.",
            ResolvedInstructionLanguage::En,
        ),
        (
            "赤い線を中心に置く。\n前の線に触れる\n青い弧を中心に置く。\n前の弧に両端で触れる\n緑の弧を中心に置く。\n前の弧に両端で触れる\n黄の線を中心に置く。",
            ResolvedInstructionLanguage::Ja,
        ),
    ];
    for (source, language) in sources {
        let result = execute_language(source, language, &[], ScoreErrorPolicy::Stop);
        assert_eq!(
            result.outcome(),
            ScoreLoweringOutcome::Complete,
            "{language:?}: {:?} {:?}",
            result.upstream_diagnostics(),
            result.downstream_diagnostics()
        );
        let score = result.score().unwrap();
        let canvas = Some(CanvasSize::new(1200.0, 700.0));
        let request = PerformanceRequest {
            score,
            composition_seed: Some(23),
            performance_seed: Some(23),
            canvas,
        };
        let plan = resolve_checked_performance(request, ScoreErrorPolicy::Stop).unwrap();
        assert_eq!(plan.original_instruction_indices, [0, 1, 2, 3]);
        let endpoints = endpoint_geometry(&plan.score.instructions[0], canvas).unwrap();
        for instruction in &plan.score.instructions[1..] {
            let actual = endpoint_geometry(instruction, canvas).unwrap();
            assert!((actual.0.x - endpoints.0.x).hypot(actual.0.y - endpoints.0.y) < 1e-9);
            assert!((actual.1.x - endpoints.1.x).hypot(actual.1.y - endpoints.1.y) < 1e-9);
        }
        let independent = inku_render::performance::resolve_performance(PerformanceRequest {
            score,
            composition_seed: Some(23),
            performance_seed: Some(23),
            canvas,
        });
        assert_eq!(
            plan.score.instructions[0],
            independent.score.instructions[0]
        );
        let first_center = plan.score.instructions[1].center.unwrap();
        let second_center = plan.score.instructions[2].center.unwrap();
        assert!((first_center.y - endpoints.0.y) * (second_center.y - endpoints.0.y) < 0.0);
    }
    for source in [
        "place one red arc at center. place one blue line at center touching the previous line. place one green square at center.",
        "place one red line at center. place one blue arc at center touching the previous arc at both ends. place one green square at center.",
    ] {
        let stopped = execute(source, &[], LIMITS, ScoreErrorPolicy::Stop);
        assert_eq!(
            stopped.compilation().compiler_lock.as_ref().unwrap().state,
            CompilerLockState::BlockedConflict
        );
        assert_eq!(
            stopped.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions
        );
        let stopped_score = stopped.score().unwrap();
        assert_eq!(stopped_score.instructions.len(), 3);
        assert!(stopped_score.instructions[1].relation.is_none());
        assert!(
            stopped
                .compilation()
                .semantic_document
                .as_ref()
                .unwrap()
                .instruction_association
                .relation_issues
                .iter()
                .any(|issue| issue.kind.as_str() == "relation_target_primitive_mismatch")
        );
        let continued = execute(source, &[], LIMITS, ScoreErrorPolicy::OmitAndContinue);
        assert_eq!(
            continued.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions
        );
        assert_eq!(continued.score(), Some(stopped_score));
        assert_eq!(continued.score().unwrap().instructions.len(), 3);
        assert_eq!(
            continued.instruction_origins(),
            [
                ScoreInstructionOrigin::SourceInstruction {
                    instruction_index: 0
                },
                ScoreInstructionOrigin::SourceInstruction {
                    instruction_index: 1
                },
                ScoreInstructionOrigin::SourceInstruction {
                    instruction_index: 2
                }
            ]
        );
        assert!(continued.upstream_diagnostics().iter().any(|diagnostic| {
            matches!(
                diagnostic.disposition,
                CompilerExecutionDisposition::RelationOmitted {
                    unit: CompilerExecutionOmissionUnit::RelationInstruction {
                        instruction_index: 1,
                        ..
                    }
                }
            )
        }));
    }
}

#[test]
fn relation_association_failure_keeps_valid_neighbors_under_legacy_stop() {
    let source = concat!(
        "place one red arc at center. ",
        "place one blue line at center touching the previous line. ",
        "place one green square at center."
    );
    for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
        let result = execute(source, &[], LIMITS, policy);
        assert_eq!(
            result.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions,
            "{policy:?}: {result:?}"
        );
        let score = result.score().unwrap();
        assert_eq!(score.instructions.len(), 3);
        assert!(score.instructions[1].relation.is_none());
        assert_eq!(
            result
                .compilation()
                .semantic_document
                .as_ref()
                .unwrap()
                .instruction_association
                .relation_issues[0]
                .current_owner,
            Some(inku_ddl::SemanticRelationIssueOwner::Instruction {
                instruction_index: 1
            })
        );
        assert_eq!(
            result.instruction_origins(),
            [
                ScoreInstructionOrigin::SourceInstruction {
                    instruction_index: 0
                },
                ScoreInstructionOrigin::SourceInstruction {
                    instruction_index: 1
                },
                ScoreInstructionOrigin::SourceInstruction {
                    instruction_index: 2
                }
            ]
        );
        assert!(result.upstream_diagnostics().iter().any(|diagnostic| {
            matches!(
                diagnostic.disposition,
                CompilerExecutionDisposition::RelationOmitted {
                    unit: CompilerExecutionOmissionUnit::RelationInstruction {
                        instruction_index: 1,
                        ..
                    }
                }
            )
        }));
    }

    let budget = inku_score::ResourceBudget {
        maximum: inku_score::ResourceDemand {
            logical_objects: 8,
            primitive_marks: 8,
            object_templates: 8,
            maximum_per_template_primitive_marks: 8,
            maximum_resolved_count: 8,
            template_nodes: 8,
            anchor_instances: 8,
            transform_instances: 8,
            placement_instances: 8,
            fill_instances: 8,
        },
    };
    let resource_result = inku_ddl::compile_ddl_to_score_with_resources(
        document(source, &[]),
        &[],
        Some(23),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        ScoreErrorPolicy::Stop,
        inku_score::HardResourcePolicy {
            identity: "relation-recovery-test.v1".to_owned(),
            budget,
        },
        inku_score::OperationalResourceBudget(budget),
    );
    let ordinary = execute(source, &[], LIMITS, ScoreErrorPolicy::Stop);
    assert_eq!(resource_result.outcome(), ordinary.outcome());
    assert_eq!(
        resource_result.instruction_origins(),
        ordinary.instruction_origins()
    );
    assert_eq!(
        resource_result.upstream_diagnostics(),
        ordinary.upstream_diagnostics()
    );
    assert_eq!(
        resource_result.effective_stage15_digest(),
        ordinary.effective_stage15_digest()
    );
    let resource_score = resource_result.score().unwrap();
    let ordinary_score = ordinary.score().unwrap();
    assert_eq!(
        resource_score.instructions.len(),
        ordinary_score.instructions.len()
    );
    for (compact, flat) in resource_score
        .instructions
        .iter()
        .zip(&ordinary_score.instructions)
    {
        assert_eq!(compact.primitive, flat.primitive);
        assert_eq!(compact.color, flat.color);
        assert_eq!(compact.relation, flat.relation);
        assert_eq!(compact.at, flat.at);
    }
}

#[test]
fn relation_without_an_exact_current_owner_preserves_independent_drawables() {
    for (source, policy, expected_kind, expected_indices) in [
        (
            "place one red line at center. touching the previous line. place one blue square at center.",
            ScoreErrorPolicy::Stop,
            "missing_current_instruction",
            [0, 1],
        ),
        (
            "place one red line at center. circle line touching the previous line. place one blue square at center.",
            ScoreErrorPolicy::OmitAndContinue,
            "ambiguous_current_relation_ownership",
            [0, 3],
        ),
    ] {
        let result = execute(source, &[], LIMITS, policy);
        let issues = &result
            .compilation()
            .semantic_document
            .as_ref()
            .unwrap()
            .instruction_association
            .relation_issues;
        let issue = issues
            .iter()
            .find(|issue| issue.kind.as_str() == expected_kind)
            .unwrap_or_else(|| panic!("{issues:?}"));
        assert_eq!(issue.current_owner, None);
        assert_eq!(result.compilation().document.source(), source);
        assert_eq!(
            result.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions
        );
        let score = result.score().unwrap();
        assert_eq!(score.instructions.len(), 2);
        assert_eq!(score.instructions[0].primitive, Primitive::Line);
        assert_eq!(score.instructions[1].primitive, Primitive::Square);
        assert!(
            score
                .instructions
                .iter()
                .all(|instruction| instruction.relation.is_none())
        );
        assert_eq!(
            result.instruction_origins(),
            expected_indices.map(|instruction_index| {
                ScoreInstructionOrigin::SourceInstruction { instruction_index }
            })
        );
        let occurrence = &issue.occurrences[0];
        let diagnostic = result
            .upstream_diagnostics()
            .iter()
            .find(|diagnostic| diagnostic.reason == expected_kind)
            .unwrap();
        assert_eq!(diagnostic.span, Some(occurrence.provenance.span));
        assert_eq!(
            diagnostic.disposition,
            CompilerExecutionDisposition::RelationOmitted {
                unit: CompilerExecutionOmissionUnit::Clause {
                    clause_index: occurrence.provenance.clause_index,
                },
            }
        );
    }
}

#[test]
fn relation_owner_is_remapped_after_a_continuation_is_consumed() {
    let result = execute_language(
        "円を置く。円は赤い。青い線を引く、前の線の途中につながる。灰の四角を置く。",
        ResolvedInstructionLanguage::Ja,
        &[],
        ScoreErrorPolicy::OmitAndContinue,
    );
    let semantic = result.compilation().semantic_document.as_ref().unwrap();
    assert_eq!(semantic.continuation_issues.len(), 0);
    assert_eq!(semantic.ast.continuations.len(), 1);
    assert_eq!(
        semantic.instruction_association.relation_issues[0].current_owner,
        Some(inku_ddl::SemanticRelationIssueOwner::Instruction {
            instruction_index: 1
        })
    );
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert_eq!(result.score().unwrap().instructions.len(), 3);
    assert!(result.score().unwrap().instructions[1].relation.is_none());
    assert!(
        result
            .upstream_diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                diagnostic.disposition,
                CompilerExecutionDisposition::RelationOmitted {
                    unit: CompilerExecutionOmissionUnit::RelationInstruction {
                        instruction_index: 1,
                        ..
                    }
                }
            ))
    );
}

#[test]
fn invalid_partway_target_omits_only_the_relation_and_keeps_the_following_instruction() {
    let source = "赤い円を置く。青い線を引く、前の線の途中につながる。灰の四角を置く。";
    let result = execute_language(
        source,
        ResolvedInstructionLanguage::Ja,
        &[],
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    let score = result
        .score()
        .expect("independent instructions remain drawable");
    assert_eq!(score.instructions.len(), 3);
    assert!(score.instructions[1].relation.is_none());
    assert_eq!(score.instructions[2].primitive, Primitive::Square);
    assert!(
        result
            .compilation()
            .semantic_document
            .as_ref()
            .unwrap()
            .instruction_association
            .relation_issues
            .iter()
            .any(|issue| issue.kind.as_str() == "relation_target_primitive_mismatch")
    );
    assert!(result.upstream_diagnostics().iter().any(|diagnostic| {
        matches!(
            diagnostic.disposition,
            CompilerExecutionDisposition::RelationOmitted {
                unit: CompilerExecutionOmissionUnit::RelationInstruction {
                    instruction_index: 1,
                    ..
                }
            }
        )
    }));
}

#[test]
fn touching_explicit_facts_and_omission_chain_keep_original_dependencies() {
    let source = concat!(
        "place one red horizontal line with length 0.4 at horizontal 0.5, vertical 0.5. ",
        "place one blue horizontal arc with chord 0.4, sagitta 0.05 at horizontal 0.5, vertical 0.5 touching the previous line."
    );
    let compatible = execute(source, &[], LIMITS, ScoreErrorPolicy::Stop);
    assert_eq!(
        compatible.outcome(),
        ScoreLoweringOutcome::Complete,
        "{:?} {:?}",
        compatible.upstream_diagnostics(),
        compatible.downstream_diagnostics()
    );
    let perform = |score: &inku_score::Score, policy| {
        resolve_checked_performance(
            PerformanceRequest {
                score,
                composition_seed: Some(23),
                performance_seed: Some(23),
                canvas: None,
            },
            policy,
        )
    };
    assert!(perform(compatible.score().unwrap(), ScoreErrorPolicy::Stop).is_ok());
    for (replacement, reason) in [
        (
            "place one blue line with length 0.2 at horizontal 0.5, vertical 0.5 touching the previous line.",
            ScoreExecutionReason::TouchingGeometryConflict,
        ),
        (
            "place one blue vertical line at center touching the previous line.",
            ScoreExecutionReason::TouchingDirectionConflict,
        ),
        (
            "place one blue line at horizontal 0.7, vertical 0.5 touching the previous line.",
            ScoreExecutionReason::NumericTouchingPositionConflict,
        ),
        (
            "place one blue normal-sized line at center touching the previous line.",
            ScoreExecutionReason::TouchingGeometryConflict,
        ),
    ] {
        let chain = format!(
            "place one red horizontal line with length 0.4 at horizontal 0.5, vertical 0.5. {replacement} place one green arc at center touching the previous line. place one yellow circle at center."
        );
        let execution = execute(&chain, &[], LIMITS, ScoreErrorPolicy::Stop);
        assert_eq!(
            execution.outcome(),
            ScoreLoweringOutcome::Complete,
            "{replacement}: {:?} {:?}",
            execution.upstream_diagnostics(),
            execution.downstream_diagnostics()
        );
        let score = execution.score().unwrap();
        // Legacy Stop input recovers like OmitAndContinue and reports the reason.
        let stopped = perform(score, ScoreErrorPolicy::Stop).unwrap();
        assert_eq!(
            stopped.execution.as_ref().unwrap().diagnostics[0].reason,
            reason
        );
        let plan = perform(score, ScoreErrorPolicy::OmitAndContinue).unwrap();
        assert_eq!(stopped.original_instruction_indices, plan.original_instruction_indices);
        // An unsatisfiable touch removes only that relation edge; the shapes
        // and the later chain are still drawn.
        assert_eq!(plan.original_instruction_indices, [0, 1, 2, 3]);
        assert_eq!(plan.instruction_indices, [0, 1, 2, 3]);
        let summary = plan.execution.as_ref().unwrap();
        assert_eq!(summary.diagnostics.len(), 1);
        assert_eq!(summary.diagnostics[0].instruction_index, 1);
        assert_eq!(summary.diagnostics[0].dependency_instruction_index, Some(0));
        assert_eq!(
            summary.diagnostics[0].disposition,
            inku_score::ScoreExecutionDisposition::RelationOmitted
        );
        let joined = map_compiler_render_execution(&execution, score, Some(summary)).unwrap();
        assert_eq!(
            joined.rendered_origins[1],
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 1
            }
        );
    }
}

#[test]
fn touching_flat_macro_color_binding_has_same_effective_score_and_performance() {
    use serde_json::json;
    let mut body = Vec::new();
    for (index, (shape, color)) in [
        ("line", "red"),
        ("arc", "blue"),
        ("arc", "green"),
        ("line", "yellow"),
    ]
    .iter()
    .enumerate()
    {
        let mut fields = json!({
            "shape": {"expr":"semantic_ref", "category":"shape", "id":shape},
            "movement": {"expr":"semantic_ref", "category":"movement", "id":"place"},
            "place": {"expr":"semantic_ref", "category":"place", "id":"center"},
            "color": {"expr":"semantic_ref", "category":"color", "id":color}
        });
        if index == 0 {
            fields["angle"] = json!({"expr":"semantic_ref", "category":"angle", "id":"vertical"});
        }
        if index == 1 {
            fields["color"] = json!({"expr":"parameter", "name":"tone"});
        }
        body.push(json!({"op":"emit", "binding":format!("mark{index}"), "fields":fields}));
        if index > 0 {
            body.push(json!({"op":"relation", "kind":"touching", "from":format!("mark{}", index - 1), "to":format!("mark{index}")}));
        }
    }
    let mut definition_value = json!({"schema":"inku.macro-definition.v1", "namespace":"Touch", "heading":"Chain", "version":"1.0.0", "parameters":{"tone":{"type":"semantic_ref","category":"color"}}, "components":{}, "body":body});
    let definition = definition_from(&definition_value.to_string());
    let generated = execute_locked(
        "blue Touch.Chain",
        &[definition],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    let direct = execute(
        "place one red vertical line at center. place one blue arc at center touching the previous line. place one green arc at center touching the previous arc at both ends. place one yellow line at center touching the previous arc at both ends.",
        &[],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    for execution in [&direct, &generated] {
        assert_eq!(
            execution.outcome(),
            ScoreLoweringOutcome::Complete,
            "{:?} {:?}",
            execution.upstream_diagnostics(),
            execution.downstream_diagnostics()
        );
        assert_eq!(
            execution.score().unwrap().instructions[1].color,
            Color::Blue
        );
    }
    let mut ordinary = direct.score().unwrap().clone();
    let mut expanded = generated.score().unwrap().clone();
    // The two canonical meanings select their own focus; compare at the same effective focus.
    for instruction in ordinary
        .instructions
        .iter_mut()
        .chain(&mut expanded.instructions)
    {
        assert!(instruction.at.is_some());
        instruction.at = None;
    }
    assert_eq!(ordinary, expanded);
    let perform = |score: &inku_score::Score| {
        resolve_checked_performance(
            PerformanceRequest {
                score,
                composition_seed: Some(23),
                performance_seed: Some(23),
                canvas: Some(inku_render::types::CanvasSize::new(1200.0, 700.0)),
            },
            ScoreErrorPolicy::Stop,
        )
        .unwrap()
    };
    assert_eq!(perform(&ordinary).score, perform(&expanded).score);
    assert!(
        generated
            .instruction_origins()
            .iter()
            .all(|owner| matches!(owner, ScoreInstructionOrigin::MacroEmit { .. }))
    );
    definition_value["body"][1]["fields"]["angle"] =
        json!({"expr":"semantic_ref", "category":"angle", "id":"horizontal"});
    let conflict = execute_locked(
        "blue Touch.Chain",
        &[definition_from(&definition_value.to_string())],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    let score = conflict.score().unwrap();
    let request = || PerformanceRequest {
        score,
        composition_seed: Some(23),
        performance_seed: Some(23),
        canvas: None,
    };
    let stopped = resolve_checked_performance(request(), ScoreErrorPolicy::Stop).unwrap();
    assert_eq!(
        stopped.execution.as_ref().unwrap().diagnostics[0].reason,
        ScoreExecutionReason::TouchingDirectionConflict
    );
    let omitted =
        resolve_checked_performance(request(), ScoreErrorPolicy::OmitAndContinue).unwrap();
    assert_eq!(stopped.original_instruction_indices, omitted.original_instruction_indices);
    // The conflicting touch removes only its relation edge; all four Macro
    // emits are still drawn.
    assert_eq!(omitted.original_instruction_indices, [0, 1, 2, 3]);
    assert_eq!(
        omitted.execution.as_ref().unwrap().diagnostics[0].disposition,
        inku_score::ScoreExecutionDisposition::RelationOmitted
    );
    let joined =
        map_compiler_render_execution(&conflict, score, omitted.execution.as_ref()).unwrap();
    assert!(matches!(
        joined.diagnostics[0].owner,
        CompilerRenderOwner::Instruction(ScoreInstructionOrigin::MacroEmit { .. })
    ));
}

#[test]
fn canonical_input_preserves_the_existing_score_in_both_modes() {
    let source = "place one red circle at center.";
    let stop = execute(source, &[], LIMITS, ScoreErrorPolicy::Stop);
    let continued = execute(source, &[], LIMITS, ScoreErrorPolicy::OmitAndContinue);

    assert_eq!(stop.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(continued.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(stop.score(), continued.score());
    assert!(stop.upstream_diagnostics().is_empty());
    assert!(continued.upstream_diagnostics().is_empty());
    assert_eq!(
        stop.compilation().compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady
    );
}

#[test]
fn declared_normal_scale_is_fixed_for_touching_and_preserves_omission_owner() {
    use serde_json::json;
    for first_scale in ["normal", "very_large"] {
        let fields = |scale| {
            json!({
                "shape":{"expr":"semantic_ref","category":"shape","id":"line"},
                "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
                "place":{"expr":"semantic_ref","category":"place","id":"center"},
                "angle":{"expr":"semantic_ref","category":"angle","id":"horizontal"},
                "color":{"expr":"semantic_ref","category":"color","id":"red"},
                "relative_scale":scale
            })
        };
        let definition = definition_from(&json!({
            "schema":"inku.macro-definition.v1","namespace":"Touch","heading":"Scale","version":"1.0.0",
            "parameters":{"scale":{"type":"semantic_ref","category":"relative_scale"}},"components":{},
            "body":[
                {"op":"emit","binding":"first","fields":fields(json!({"expr":"semantic_ref","category":"relative_scale","id":first_scale}))},
                {"op":"emit","binding":"second","fields":fields(json!({"expr":"parameter","name":"scale"}))},
                {"op":"relation","kind":"touching","from":"first","to":"second"}
            ]
        }).to_string());
        let execution = execute_locked(
            "normal-sized Touch.Scale",
            &[definition],
            LIMITS,
            ScoreErrorPolicy::Stop,
        );
        assert_eq!(
            execution.outcome(),
            ScoreLoweringOutcome::Complete,
            "{:?} {:?}",
            execution.upstream_diagnostics(),
            execution.downstream_diagnostics()
        );
        let score = execution.score().unwrap();
        assert!(
            score.instructions[1]
                .relation
                .as_ref()
                .unwrap()
                .touching_constraints
                .as_ref()
                .unwrap()
                .dimensions_fixed
        );
        let request = || PerformanceRequest {
            score,
            composition_seed: Some(23),
            performance_seed: Some(23),
            canvas: None,
        };
        if first_scale == "normal" {
            assert!(resolve_checked_performance(request(), ScoreErrorPolicy::Stop).is_ok());
        } else {
            let stopped =
                resolve_checked_performance(request(), ScoreErrorPolicy::Stop).unwrap();
            assert_eq!(
                stopped.execution.as_ref().unwrap().diagnostics[0].reason,
                ScoreExecutionReason::TouchingGeometryConflict
            );
            let continued =
                resolve_checked_performance(request(), ScoreErrorPolicy::OmitAndContinue).unwrap();
            // Only the touch is removed; both emits are still drawn.
            assert_eq!(continued.original_instruction_indices, [0, 1]);
            let joined =
                map_compiler_render_execution(&execution, score, continued.execution.as_ref())
                    .unwrap();
            assert!(matches!(
                joined.diagnostics[0].owner,
                CompilerRenderOwner::Instruction(ScoreInstructionOrigin::MacroEmit { .. })
            ));
        }
    }
}

#[test]
fn declared_core_binding_failure_and_unbound_caller_keep_their_policy_owners() {
    use serde_json::json;
    let mut data = json!({
        "schema":"inku.macro-definition.v1","namespace":"Core","heading":"One","version":"1.0.0",
        "parameters":{"width":{"type":"semantic_ref","category":"thinness"}},"components":{},
        "body":[{"op":"emit","binding":null,"fields":{
            "shape":{"expr":"semantic_ref","category":"shape","id":"circle"},
            "movement":{"expr":"semantic_ref","category":"movement","id":"place"},
            "place":{"expr":"semantic_ref","category":"place","id":"center"},
            "thinness":{"expr":"parameter","name":"width"}
        }}]
    });
    let definition = definition_from(&data.to_string());
    for source in [
        "place one red circle at center. Core.One",
        "place one red circle at center. thin extra-fine Core.One",
    ] {
        let stop = execute_locked(
            source,
            std::slice::from_ref(&definition),
            LIMITS,
            ScoreErrorPolicy::Stop,
        );
        let continued = execute_locked(
            source,
            std::slice::from_ref(&definition),
            LIMITS,
            ScoreErrorPolicy::OmitAndContinue,
        );
        // Legacy Stop input keeps the independent circle like OmitAndContinue.
        assert_eq!(stop.outcome(), continued.outcome());
        assert_eq!(stop.score(), continued.score());
        assert_eq!(
            continued.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions,
            "{:?}",
            continued.upstream_diagnostics()
        );
        assert_eq!(continued.score().unwrap().instructions.len(), 1);
        assert!(!continued.upstream_diagnostics().is_empty());
        assert!(continued.downstream_diagnostics().is_empty());
    }
    data["parameters"] = json!({});
    data["body"][0]["fields"]["thinness"] =
        json!({"expr":"semantic_ref","category":"thinness","id":"fine"});
    let definition = definition_from(&data.to_string());
    let source = "place one red circle at center. normal-sized Core.One";
    let stop = execute_locked(
        source,
        std::slice::from_ref(&definition),
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    let continued = execute_locked(
        source,
        &[definition],
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(stop.score(), continued.score());
    assert_eq!(continued.score().unwrap().instructions.len(), 1);
    assert!(continued.upstream_diagnostics().is_empty());
    assert!(
        continued
            .downstream_diagnostics()
            .iter()
            .any(|diagnostic| diagnostic.reason == ScoreFieldGap::UnboundMacroCallerMeaning)
    );
}

#[test]
fn ground_is_drawable_content_for_both_facade_modes_and_continue_omissions() {
    for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
        let ground_only = execute("paper.", &[], LIMITS, policy);
        assert_eq!(
            ground_only.outcome(),
            ScoreLoweringOutcome::Complete,
            "{policy:?}"
        );
        assert!(matches!(
            &ground_only.score().unwrap().canvas,
            Canvas::Spec(spec)
                if matches!(spec.ground.as_ref(), Some(ground) if ground.material == GroundMaterial::Paper)
        ));

        let ground_and_instruction = execute(
            "paper. place one red circle at center.",
            &[],
            LIMITS,
            policy,
        );
        assert_eq!(
            ground_and_instruction.outcome(),
            ScoreLoweringOutcome::Complete,
            "{policy:?}"
        );
        assert_eq!(
            ground_and_instruction.score().unwrap().instructions.len(),
            1
        );
    }

    let continued = execute(
        "paper. place many red circle at center.",
        &[],
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        continued.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert!(continued.score().unwrap().instructions.is_empty());
    assert!(matches!(
        &continued.score().unwrap().canvas,
        Canvas::Spec(spec)
            if matches!(spec.ground.as_ref(), Some(ground) if ground.material == GroundMaterial::Paper)
    ));
    assert!(!continued.upstream_diagnostics().is_empty());

    let stopped = execute(
        "paper. place many red circle at center.",
        &[],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    // The ground is drawable content, so legacy Stop input keeps it too.
    assert_eq!(stopped.outcome(), continued.outcome());
    assert_eq!(stopped.score(), continued.score());

    let all_omitted = execute(
        "paper washi. place many red circle at center.",
        &[],
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(all_omitted.outcome(), ScoreLoweringOutcome::Stopped);
    assert!(all_omitted.score().is_none());
}

#[test]
fn background_does_not_admit_an_omitted_macro_without_drawable_residual() {
    use serde_json::json;

    let definition = definition_from(
        &json!({
            "schema": "inku.macro-definition.v1",
            "namespace": "Guard",
            "heading": "Grass",
            "version": "1.0.0",
            "parameters": {},
            "components": {},
            "body": [{
                "op": "emit",
                "binding": null,
                "fields": {
                    "shape": {"expr": "semantic_ref", "category": "shape", "id": "line"},
                    "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                    "place": {"expr": "semantic_ref", "category": "place", "id": "center"},
                    "color": {"expr": "semantic_ref", "category": "color", "id": "green"}
                }
            }]
        })
        .to_string(),
    );
    let definitions = [definition];
    let locks = definitions.iter().map(lock_for).collect::<Vec<_>>();
    let budget = inku_score::ResourceBudget {
        maximum: inku_score::ResourceDemand {
            logical_objects: 8,
            primitive_marks: 8,
            object_templates: 8,
            maximum_per_template_primitive_marks: 8,
            maximum_resolved_count: 8,
            template_nodes: 8,
            anchor_instances: 8,
            transform_instances: 8,
            placement_instances: 8,
            fill_instances: 8,
        },
    };
    let resource = |source: &str| {
        inku_ddl::compile_ddl_to_score_with_resources(
            document(source, &locks),
            &definitions,
            Some(23),
            LIMITS,
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            None,
            ScoreErrorPolicy::OmitAndContinue,
            inku_score::HardResourcePolicy {
                identity: "empty-residual-test.v1".to_owned(),
                budget: budget.clone(),
            },
            inku_score::OperationalResourceBudget(budget.clone()),
        )
    };

    let omitted = "place Guard.Grass at bottom. fill background with white.";
    let ordinary = execute_locked(
        omitted,
        &definitions,
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    let compact = resource(omitted);
    for (outcome, score, diagnostics) in [
        (
            ordinary.outcome(),
            ordinary.score(),
            ordinary.downstream_diagnostics(),
        ),
        (
            compact.outcome(),
            compact.score(),
            compact.downstream_diagnostics(),
        ),
    ] {
        assert!(
            diagnostics
                .iter()
                .any(|diagnostic| diagnostic.reason == ScoreFieldGap::UnboundMacroCallerMeaning),
            "{diagnostics:?}"
        );
        assert!(
            score.is_none_or(|score| score.instructions.is_empty()),
            "{score:?}"
        );
        assert_eq!(outcome, ScoreLoweringOutcome::Stopped);
        assert!(score.is_none());
    }

    let with_ground = "paper. place Guard.Grass at bottom. fill background with white.";
    let ordinary = execute_locked(
        with_ground,
        &definitions,
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    let compact = resource(with_ground);
    for (outcome, score) in [
        (ordinary.outcome(), ordinary.score()),
        (compact.outcome(), compact.score()),
    ] {
        assert_eq!(outcome, ScoreLoweringOutcome::CompleteWithOmissions);
        assert!(matches!(&score.unwrap().canvas, Canvas::Spec(spec) if spec.ground.is_some()));
    }

    let with_instruction =
        "place one red circle at center. place Guard.Grass at bottom. fill background with white.";
    let ordinary = execute_locked(
        with_instruction,
        &definitions,
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    let compact = resource(with_instruction);
    for (outcome, score) in [
        (ordinary.outcome(), ordinary.score()),
        (compact.outcome(), compact.score()),
    ] {
        assert_eq!(outcome, ScoreLoweringOutcome::CompleteWithOmissions);
        assert_eq!(score.unwrap().instructions.len(), 1);
    }
}

#[test]
fn all_omitted_stops_under_legacy_stop() {
    let result = execute(
        "place many red circle at horizontal 0.5, vertical 0.5.",
        &[],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );

    assert_eq!(result.outcome(), ScoreLoweringOutcome::Stopped);
    assert!(result.score().is_none());
    assert!(result.instruction_origins().is_empty());
    assert!(!result.upstream_diagnostics().is_empty());
    assert!(
        result
            .upstream_diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                diagnostic.disposition,
                CompilerExecutionDisposition::Omitted { .. }
            ))
    );
}

#[test]
fn resource_overage_draws_the_safe_prefix_and_reports_the_unexecuted_suffix() {
    let budget = inku_score::ResourceBudget {
        maximum: inku_score::ResourceDemand {
            logical_objects: 4096,
            primitive_marks: 400,
            object_templates: 64,
            maximum_per_template_primitive_marks: 240,
            maximum_resolved_count: 2000,
            template_nodes: 128,
            anchor_instances: 4096,
            transform_instances: 4096,
            placement_instances: 64,
            fill_instances: 64,
        },
    };
    for (count, later, expected_outcome, expected_origins) in [
        (
            300,
            "",
            ScoreLoweringOutcome::CompleteWithOmissions,
            &[0][..],
        ),
        (240, "", ScoreLoweringOutcome::Complete, &[0][..]),
        (
            300,
            " place one blue circle at center.",
            ScoreLoweringOutcome::CompleteWithOmissions,
            &[0, 1][..],
        ),
    ] {
        let source = format!("scatter {count} red square at center.{later}");
        let result = inku_ddl::compile_ddl_to_score_with_resources(
            document(&source, &[]),
            &[],
            Some(23),
            LIMITS,
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            None,
            ScoreErrorPolicy::Stop,
            inku_score::HardResourcePolicy {
                identity: "all-resource-omitted-test.v1".to_owned(),
                budget,
            },
            inku_score::OperationalResourceBudget(budget),
        );
        assert_eq!(
            result.outcome(),
            expected_outcome,
            "count={count}, later={later}"
        );
        assert_eq!(result.compilation().document.source(), source);
        let semantic = result.compilation().semantic_document.as_ref().unwrap();
        assert_eq!(
            semantic.ast.instructions[0]
                .entity
                .quantity
                .as_ref()
                .unwrap()
                .value,
            count
        );
        assert_eq!(result.resource_omissions().len(), usize::from(count > 240));
        if count > 240 {
            let omission = &result.resource_omissions()[0];
            assert_eq!(
                omission.owner,
                inku_ddl::PlanResourceOwner::SourceInstruction {
                    source_instruction_index: 0,
                }
            );
            assert!(matches!(
                omission.cause.reason,
                inku_ddl::PlanResourceFailure::BudgetExceeded(_)
            ));
            assert_eq!(
                omission.partial_execution,
                Some(inku_ddl::PlanResourcePartialExecution {
                    requested_count: 300,
                    executed_count: 240,
                })
            );
        }
        let score = result.score().expect("the safe drawable prefix survives");
        assert_eq!(
            score.instructions[0].arrangement.as_ref().unwrap().count,
            u32::try_from(count.min(240)).unwrap()
        );
        assert_eq!(
            result.instruction_origins(),
            expected_origins
                .iter()
                .map(
                    |&instruction_index| ScoreInstructionOrigin::SourceInstruction {
                        instruction_index,
                    }
                )
                .collect::<Vec<_>>()
        );
    }
}

#[test]
fn undelivered_occurrences_preserve_accepted_drawables_in_the_same_clause() {
    let source = concat!(
        "place red circle at horizontal 0.5, vertical 0.5 many mystery. ",
        "place one red square at center."
    );
    let continued = execute(source, &[], LIMITS, ScoreErrorPolicy::OmitAndContinue);
    let stopped_policy = execute(source, &[], LIMITS, ScoreErrorPolicy::Stop);
    for result in [&continued, &stopped_policy] {
        assert_eq!(result.compilation().document.source(), source);
        assert_eq!(
            result.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions,
            "{:?} {:?}",
            result.upstream_diagnostics(),
            result.downstream_diagnostics()
        );
        let score = result.score().unwrap();
        assert_eq!(
            score.instructions.len(),
            2,
            "{:?}",
            result.downstream_diagnostics()
        );
        assert_eq!(score.instructions[0].primitive, Primitive::Circle);
        assert_eq!(score.instructions[1].primitive, Primitive::Square);
        assert_eq!(
            result.instruction_origins(),
            [0, 1].map(|instruction_index| {
                ScoreInstructionOrigin::SourceInstruction { instruction_index }
            })
        );
        let semantic = result.compilation().semantic_document.as_ref().unwrap();
        assert_eq!(semantic.ast.instructions[0].entity.quantity, None);
        // The undelivered words are reported once as the clause hole they sit
        // in; the accepted circle in that clause is still drawn.
        let [diagnostic] = result.upstream_diagnostics() else {
            panic!("{:?}", result.upstream_diagnostics());
        };
        assert_eq!(diagnostic.reason, "unresolved_clause");
        let span = diagnostic.span.unwrap();
        assert_eq!(
            &source[span.start_byte..span.end_byte],
            "place red circle at horizontal 0.5, vertical 0.5 many mystery"
        );
        assert_eq!(
            diagnostic.disposition,
            CompilerExecutionDisposition::Omitted {
                unit: CompilerExecutionOmissionUnit::SourceOccurrence { span }
            }
        );
    }
    assert_eq!(continued.score(), stopped_policy.score());
    assert_eq!(
        continued.upstream_diagnostics(),
        stopped_policy.upstream_diagnostics()
    );
    let budget = inku_score::ResourceBudget {
        maximum: inku_score::ResourceDemand {
            logical_objects: 8,
            primitive_marks: 8,
            object_templates: 8,
            maximum_per_template_primitive_marks: 8,
            maximum_resolved_count: 8,
            template_nodes: 8,
            anchor_instances: 8,
            transform_instances: 8,
            placement_instances: 8,
            fill_instances: 8,
        },
    };
    let resource_result = inku_ddl::compile_ddl_to_score_with_resources(
        document(source, &[]),
        &[],
        Some(23),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        ScoreErrorPolicy::Stop,
        inku_score::HardResourcePolicy {
            identity: "occurrence-recovery-test.v1".to_owned(),
            budget,
        },
        inku_score::OperationalResourceBudget(budget),
    );
    assert_eq!(resource_result.outcome(), continued.outcome());
    assert_eq!(resource_result.score().unwrap().instructions.len(), 2);
    assert_eq!(
        resource_result.instruction_origins(),
        continued.instruction_origins()
    );
    assert_eq!(
        resource_result.upstream_diagnostics(),
        continued.upstream_diagnostics()
    );
    assert_eq!(
        resource_result.effective_stage15_digest(),
        continued.effective_stage15_digest()
    );
}

#[test]
fn ja_unresolved_predicate_fragment_preserves_typed_drawing_in_both_resource_modes() {
    let source = "黒いロットリングの小さな四角を左から右へ横に二十四個並べる。";
    let budget = inku_score::ResourceBudget {
        maximum: inku_score::ResourceDemand {
            logical_objects: 64,
            primitive_marks: 64,
            object_templates: 8,
            maximum_per_template_primitive_marks: 64,
            maximum_resolved_count: 64,
            template_nodes: 8,
            anchor_instances: 64,
            transform_instances: 64,
            placement_instances: 8,
            fill_instances: 8,
        },
    };

    let mut scores = Vec::new();
    for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
        let result = inku_ddl::compile_ddl_to_score_with_resources(
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new())
                .unwrap(),
            &[],
            Some(23),
            LIMITS,
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            None,
            policy,
            inku_score::HardResourcePolicy {
                identity: "ja-predicate-recovery-test.v1".to_owned(),
                budget,
            },
            inku_score::OperationalResourceBudget(budget),
        );
        assert_eq!(
            result.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions
        );
        assert_eq!(result.upstream_diagnostics().len(), 1);
        let diagnostic = &result.upstream_diagnostics()[0];
        assert_eq!(diagnostic.reason, "unresolved_clause");
        let span = diagnostic.span.unwrap();
        assert_eq!(
            &source[span.start_byte..span.end_byte],
            "黒いロットリングの小さな四角を左から右へ横に二十四個並べる"
        );
        let score = result.score().expect("the typed drawing survives");
        assert_eq!(score.instructions.len(), 1);
        let arrangement = score.instructions[0].arrangement.as_ref().unwrap();
        assert_eq!(arrangement.count, 24);
        assert_eq!(arrangement.layout, inku_score::Layout::Horizontal);
        scores.push(score.clone());
    }
    assert_eq!(scores[0], scores[1]);
}

#[test]
fn ja_unresolved_entity_fragment_preserves_typed_drawing() {
    let source = "中央付近に黒いクレヨンの楕円を一つ置く。";
    let result = execute_language(
        source,
        ResolvedInstructionLanguage::Ja,
        &[],
        ScoreErrorPolicy::OmitAndContinue,
    );

    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{result:#?}"
    );
    assert_eq!(result.upstream_diagnostics().len(), 1);
    let diagnostic = &result.upstream_diagnostics()[0];
    assert_eq!(diagnostic.reason, "unresolved_clause");
    let span = diagnostic.span.unwrap();
    // The unresolved part is reported as the whole clause hole it belongs to.
    assert_eq!(
        &source[span.start_byte..span.end_byte],
        "中央付近に黒いクレヨンの楕円を一つ置く"
    );
    assert_eq!(result.score().unwrap().instructions.len(), 1);
}

#[test]
fn ja_unresolved_layout_modifier_keeps_the_typed_line_up() {
    let source = "背景を黒で埋める。白いロットリングの横線を全幅に三十本並べる。等間隔に配置する。";
    let budget = inku_score::ResourceBudget {
        maximum: inku_score::ResourceDemand {
            logical_objects: 64,
            primitive_marks: 64,
            object_templates: 8,
            maximum_per_template_primitive_marks: 64,
            maximum_resolved_count: 64,
            template_nodes: 8,
            anchor_instances: 64,
            transform_instances: 64,
            placement_instances: 8,
            fill_instances: 8,
        },
    };
    let result = inku_ddl::compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new()).unwrap(),
        &[],
        Some(23),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        ScoreErrorPolicy::OmitAndContinue,
        inku_score::HardResourcePolicy {
            identity: "ja-unresolved-layout-recovery-test.v1".to_owned(),
            budget,
        },
        inku_score::OperationalResourceBudget(budget),
    );

    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{result:#?}"
    );
    let score = result.score().expect("the typed line-up survives");
    assert_eq!(score.instructions.len(), 1, "{result:#?}");
    assert_eq!(
        score.instructions[0].arrangement.as_ref().unwrap().count,
        30
    );
}

#[test]
fn ja_unknown_fragment_and_unsupported_layout_keep_line_and_count() {
    let source = "黒いペンの実線の細い線を10本、右下がりにとばらして置く。";
    let budget = inku_score::ResourceBudget {
        maximum: inku_score::ResourceDemand {
            logical_objects: 64,
            primitive_marks: 64,
            object_templates: 8,
            maximum_per_template_primitive_marks: 64,
            maximum_resolved_count: 64,
            template_nodes: 8,
            anchor_instances: 64,
            transform_instances: 64,
            placement_instances: 8,
            fill_instances: 8,
        },
    };
    let result = inku_ddl::compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new()).unwrap(),
        &[],
        Some(23),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        ScoreErrorPolicy::OmitAndContinue,
        inku_score::HardResourcePolicy {
            identity: "ja-local-field-recovery-test.v1".to_owned(),
            budget,
        },
        inku_score::OperationalResourceBudget(budget),
    );

    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{result:#?}"
    );
    let unknown = result
        .upstream_diagnostics()
        .iter()
        .find(|diagnostic| diagnostic.reason == "unresolved_clause")
        .expect("the unsupported fragment keeps one clause diagnostic");
    assert!(unknown.span.is_some());
    assert!(
        result
            .upstream_diagnostics()
            .iter()
            .all(|diagnostic| diagnostic.reason != "missing_right_coordination_head")
    );
    let layout = result
        .downstream_diagnostics()
        .iter()
        .find(|diagnostic| {
            matches!(
                diagnostic.reason,
                ScoreFieldGap::UnsupportedLayoutDirection { .. }
            )
        })
        .expect("the unsupported layout field keeps one diagnostic");
    assert_eq!(
        layout.disposition,
        ScoreDiagnosticDisposition::Omitted {
            unit: ScoreOmissionUnit::InstructionField {
                field: ScoreInstructionField::LayoutDirection,
            },
            appearance_resolution: None,
        }
    );
    let score = result.score().expect("the line body survives local omissions");
    assert_eq!(score.instructions.len(), 1);
    assert_eq!(score.instructions[0].primitive, Primitive::Line);
    assert_eq!(score.instructions[0].arrangement.as_ref().unwrap().count, 10);
}

#[test]
fn unknown_clause_and_conflicting_ground_candidates_are_locally_omitted() {
    for source in [
        "mystery. place one red square at center.",
        "paper washi. place one red square at center.",
    ] {
        let result = execute(source, &[], LIMITS, ScoreErrorPolicy::OmitAndContinue);
        assert_eq!(
            result.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions,
            "{source}: {:?}",
            result
        );
        assert_eq!(result.score().unwrap().instructions.len(), 1, "{source}");
    }
    let grounds = execute(
        "paper washi. place one red square at center.",
        &[],
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert!(
        grounds
            .upstream_diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                diagnostic.disposition,
                CompilerExecutionDisposition::Omitted {
                    unit: CompilerExecutionOmissionUnit::GroundCandidates
                }
            ))
    );
}

#[test]
fn incomplete_macro_parameters_omit_the_owning_clause_and_failed_continuation_is_local() {
    let parameterized = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Param","heading":"Mark","version":"1.0.0","parameters":{"tone":{"type":"semantic_ref","category":"color"}},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"parameter","name":"tone"}}}]}"#,
    );
    let parameter_result = execute_locked(
        "Param.Mark; place one square at center",
        std::slice::from_ref(&parameterized),
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(parameter_result.outcome(), ScoreLoweringOutcome::Stopped);
    assert!(parameter_result.score().is_none());
    assert!(
        parameter_result
            .upstream_diagnostics()
            .iter()
            .any(|diagnostic| {
                diagnostic.reason == "macro_binding_missing_compatible_fact"
                    && matches!(
                        diagnostic.disposition,
                        CompilerExecutionDisposition::Omitted { .. }
                    )
            })
    );

    let continuation_result = execute(
        "place one red circle at center. place the circle.",
        &[],
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        continuation_result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{:?}",
        continuation_result
    );
    assert_eq!(continuation_result.score().unwrap().instructions.len(), 1);
}

#[test]
fn group_and_relation_dependencies_follow_an_omitted_source_owner() {
    let grouped = execute(
        "place many red circle and square at center. place one blue ellipse at center.",
        &[],
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        grouped.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{:?}",
        grouped
    );
    assert_eq!(grouped.score().unwrap().instructions.len(), 1);
    assert!(grouped.downstream_diagnostics().iter().any(|diagnostic| {
        diagnostic.reason == ScoreFieldGap::UnsupportedCoordinatedGroup
            && matches!(
                &diagnostic.disposition,
                ScoreDiagnosticDisposition::Omitted {
                    unit: ScoreOmissionUnit::CoordinatedGroup {
                        group_index: 0,
                        member_instruction_indices,
                    },
                    ..
                } if member_instruction_indices == &[0, 1]
            )
    }));

    let relation = saijiki_asset()
        .relations
        .iter()
        .find_map(|entry| entry.literals_en.first())
        .expect("the accepted asset has an English relation literal");
    let source = format!(
        "place one yellow square at center. place 0 red circle at center. place one blue circle at center {relation}. place one green square at center."
    );
    let related = execute(&source, &[], LIMITS, ScoreErrorPolicy::OmitAndContinue);
    assert_eq!(
        related.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{:?}",
        related
    );
    let score = related.score().unwrap();
    assert_eq!(related.compilation().document.source(), source);
    assert_eq!(score.instructions.len(), 3);
    assert!(score.instructions[1].relation.is_none());
    assert_eq!(
        related.instruction_origins(),
        &[
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 0
            },
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 2
            },
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 3
            },
        ]
    );
    let diagnostic = related
        .downstream_diagnostics()
        .iter()
        .find(|diagnostic| {
            matches!(
                &diagnostic.reason,
                ScoreFieldGap::UnavailableRelationReference { dependency_instruction_indices, .. }
                    if dependency_instruction_indices == &[1]
            )
        })
        .expect("missing target keeps an explicit relation omission diagnostic");
    assert_eq!(
        diagnostic.disposition,
        ScoreDiagnosticDisposition::RelationOmitted
    );
    assert!(matches!(
        &diagnostic.owner,
        inku_ddl::ScoreDiagnosticOwner::SourceInstruction { instruction_index: 2, spans, .. }
            if !spans.is_empty()
    ));
    let value = serde_json::to_value(diagnostic).unwrap();
    assert_eq!(value["disposition"]["kind"], "relation_omitted");
    assert_eq!(value["owner"]["instruction_index"], 2);

    let blocked_current = execute(
        &format!(
            "place one red circle at center. place 0 blue circle at center {relation}. place one green square at center."
        ),
        &[],
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        blocked_current.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert_eq!(
        blocked_current.instruction_origins(),
        &[
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 0
            },
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 2
            },
        ]
    );
}

#[test]
fn group_relation_without_a_previous_target_keeps_its_exact_group_owner() {
    let source = concat!(
        "place one gray circle and black square at bottom mirrored with the previous shape. ",
        "place one yellow ellipse at center."
    );
    let result = execute(source, &[], LIMITS, ScoreErrorPolicy::Stop);
    let semantic = result.compilation().semantic_document.as_ref().unwrap();
    assert_eq!(result.compilation().document.source(), source);
    assert_eq!(semantic.instruction_association.relation_issues.len(), 1);
    let issue = &semantic.instruction_association.relation_issues[0];
    assert_eq!(issue.kind.as_str(), "missing_previous_one");
    assert_eq!(
        issue.current_owner,
        Some(inku_ddl::SemanticRelationIssueOwner::CoordinatedGroup { group_index: 0 })
    );
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    let score = result.score().unwrap();
    assert_eq!(score.instructions.len(), 3);
    assert_eq!(score.placement_groups.len(), 1);
    assert!(score.mirror_relations.is_empty());
    assert_eq!(
        result.instruction_origins(),
        [0, 1, 2].map(
            |instruction_index| ScoreInstructionOrigin::SourceInstruction { instruction_index }
        )
    );
    assert!(
        result
            .upstream_diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                &diagnostic.disposition,
                CompilerExecutionDisposition::RelationOmitted {
                    unit: CompilerExecutionOmissionUnit::CoordinatedGroup {
                        group_index: 0,
                        member_instruction_indices,
                    }
                } if member_instruction_indices == &[0, 1]
            ))
    );
}

#[test]
fn group_relation_does_not_retarget_an_earlier_surviving_group() {
    let result = execute(
        concat!(
            "place one blue circle and green square at top. ",
            "place many red circle and white square at center. ",
            "place one gray circle and black square at bottom mirrored with the previous shape. ",
            "place one yellow ellipse at center."
        ),
        &[],
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert!(
        result
            .compilation()
            .semantic_document
            .as_ref()
            .unwrap()
            .ast
            .group_predicates
            .iter()
            .any(|edge| edge.group_index == 2 && edge.relation.is_some())
    );
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    let score = result.score().unwrap();
    assert_eq!(score.instructions.len(), 5);
    assert_eq!(score.placement_groups.len(), 2);
    assert!(score.mirror_relations.is_empty());
    assert_eq!(
        result.instruction_origins(),
        [0, 1, 4, 5, 6].map(
            |instruction_index| ScoreInstructionOrigin::SourceInstruction { instruction_index }
        )
    );
    assert!(
        result
            .downstream_diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                (&diagnostic.owner, &diagnostic.disposition),
                (
                    // The group's follower is its last member, as on the
                    // materialized path; the omitted group is its target.
                    inku_ddl::ScoreDiagnosticOwner::SourceInstruction {
                        instruction_index: 5,
                        ..
                    },
                    ScoreDiagnosticDisposition::RelationOmitted
                )
            ))
    );
}

#[test]
fn canonical_ready_lowering_omits_a_relation_whose_direct_referent_is_a_macro_slot() {
    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Good","heading":"Mark","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}}]}"#,
    );
    let result = execute_locked(
        "Good.Mark! place one green square at center not touching the previous shape.",
        std::slice::from_ref(&definition),
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );

    assert_eq!(
        result.compilation().compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady
    );
    assert!(result.upstream_diagnostics().is_empty());
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    // The Macro circle and the square are both drawn; only the square's
    // relation to the Macro slot is removed.
    assert_eq!(result.score().unwrap().instructions.len(), 2);
    assert!(
        result
            .downstream_diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                (&diagnostic.reason, &diagnostic.disposition),
                (
                    ScoreFieldGap::UnavailableRelationReference {
                        kind: SemanticRelationKind::NotTouching,
                        reference: SemanticPreviousReference::PreviousOne,
                        dependency_instruction_indices,
                    },
                    ScoreDiagnosticDisposition::RelationOmitted
                ) if dependency_instruction_indices == &[0]
            ))
    );
}

#[test]
fn projected_lowering_keeps_original_direct_referents_after_an_older_omission() {
    let result = execute(
        concat!(
            "place many red circle at center. ",
            "place one blue circle at center. ",
            "place one green ellipse at center. ",
            "place one gray square at center between the previous two."
        ),
        &[],
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );

    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions
    );
    assert!(!result.upstream_diagnostics().is_empty());
    assert!(result.downstream_diagnostics().iter().any(|diagnostic| {
        diagnostic.reason == ScoreFieldGap::MissingPlaceAction
            && matches!(
                diagnostic.disposition,
                ScoreDiagnosticDisposition::Omitted {
                    unit: ScoreOmissionUnit::SourceInstruction {
                        instruction_index: 0
                    },
                    ..
                }
            )
    }));
    assert_eq!(
        result.instruction_origins(),
        &[
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 1
            },
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 2
            },
            ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 3
            },
        ]
    );
    let score = result.score().unwrap();
    assert_eq!(score.instructions.len(), 3);
    assert_eq!(
        score.instructions[2].relation.as_ref().unwrap().kind,
        RelationType::Between
    );
}

#[test]
fn one_failed_macro_keeps_the_successful_expansion_with_original_seed_provenance() {
    let good = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Good","heading":"Mark","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}}]}"#,
    );
    let bad = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Bad","heading":"Pair","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"square"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"square"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"}}}]}"#,
    );
    let definitions = [good, bad];
    let limits = MacroExpansionLimits {
        max_nodes_per_invocation: 1,
        ..LIMITS
    };
    let result = execute_locked(
        "Good.Mark Bad.Pair",
        &definitions,
        limits,
        ScoreErrorPolicy::OmitAndContinue,
    );

    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{:?}",
        result
    );
    assert_eq!(result.score().unwrap().instructions.len(), 1);
    let ScoreInstructionOrigin::MacroEmit { provenance, .. } = &result.instruction_origins()[0]
    else {
        panic!("successful macro retains generated origin")
    };
    let original = &result
        .compilation()
        .macro_expansion
        .as_ref()
        .unwrap()
        .expanded[0]
        .provenance;
    assert_eq!(provenance.invocation, *original);
    assert_eq!(provenance.invocation.invocation_ordinal, 0);
}

#[test]
fn global_macro_budget_stops_both_modes() {
    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Good","heading":"Mark","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"}}}]}"#,
    );
    let limits = MacroExpansionLimits {
        max_invocations: 1,
        ..LIMITS
    };
    for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
        let result = execute_locked(
            "Good.Mark Good.Mark",
            std::slice::from_ref(&definition),
            limits,
            policy,
        );
        assert_eq!(result.outcome(), ScoreLoweringOutcome::Stopped);
        assert!(result.score().is_none());
        assert!(
            result
                .upstream_diagnostics()
                .iter()
                .any(|diagnostic| diagnostic.reason == "expansion_invocation_budget"),
            "{:?}",
            result
        );
    }
}

#[test]
fn connected_full_literal_reaches_the_actual_score() {
    let result = execute(
        concat!(
            "place one red line at center. ",
            "place one blue line at center connected to the previous shape."
        ),
        &[],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );

    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::Complete,
        "{result:?}"
    );
    let score = serde_json::to_value(result.score().expect("connected score"))
        .expect("Score remains serializable");
    assert_eq!(score["instructions"].as_array().unwrap().len(), 2);
    assert_eq!(score["instructions"][1]["relation"]["type"], "connected");
}

#[test]
fn connected_full_literals_are_bilingual_and_macro_uses_the_same_score_consumer() {
    let english = execute_language(
        concat!(
            "place one red line at center. ",
            "place one blue line at center connected to the previous shape."
        ),
        ResolvedInstructionLanguage::En,
        &[],
        ScoreErrorPolicy::Stop,
    );
    let japanese = execute_language(
        "赤い線を中心に置く。\n前の形につながる\n青い線を中心に置く。",
        ResolvedInstructionLanguage::Ja,
        &[],
        ScoreErrorPolicy::Stop,
    );
    assert_eq!(english.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(japanese.outcome(), ScoreLoweringOutcome::Complete);
    for result in [&english, &japanese] {
        let score = result.score().unwrap();
        assert_eq!(score.instructions.len(), 2);
        assert_eq!(score.instructions[0].primitive, Primitive::Line);
        assert_eq!(score.instructions[1].primitive, Primitive::Line);
        assert_eq!(
            score.instructions[1].relation.as_ref().unwrap().kind,
            RelationType::Connected
        );
    }

    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Path","heading":"Pair","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":"first","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"line"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}},{"op":"emit","binding":"second","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"line"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"blue"}}},{"op":"relation","kind":"connected","from":"first","to":"second"}]}"#,
    );
    let macro_result = execute_locked(
        "Path.Pair",
        std::slice::from_ref(&definition),
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    assert_eq!(macro_result.outcome(), ScoreLoweringOutcome::Complete);
    let mut ordinary_effective = english.score().unwrap().clone();
    let mut macro_effective = macro_result.score().unwrap().clone();
    assert!(
        ordinary_effective
            .instructions
            .iter()
            .chain(&macro_effective.instructions)
            .all(|instruction| instruction.at.is_some())
    );
    for instruction in ordinary_effective
        .instructions
        .iter_mut()
        .chain(&mut macro_effective.instructions)
    {
        instruction.at = None;
    }
    assert_eq!(macro_effective, ordinary_effective);
    assert!(matches!(
        macro_result.instruction_origins(),
        [
            ScoreInstructionOrigin::MacroEmit { .. },
            ScoreInstructionOrigin::MacroEmit { .. }
        ]
    ));
}

#[test]
fn not_touching_full_literal_and_macro_use_the_same_score_consumer() {
    let ordinary = execute_language(
        concat!(
            "place one red circle at center. ",
            "place one blue square at center not touching the previous shape."
        ),
        ResolvedInstructionLanguage::En,
        &[],
        ScoreErrorPolicy::Stop,
    );
    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Path","heading":"Separate","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":"first","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}},{"op":"emit","binding":"second","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"square"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"blue"}}},{"op":"relation","kind":"not_touching","from":"first","to":"second"}]}"#,
    );
    let macro_result = execute_locked(
        "Path.Separate",
        std::slice::from_ref(&definition),
        LIMITS,
        ScoreErrorPolicy::Stop,
    );

    assert_eq!(ordinary.outcome(), ScoreLoweringOutcome::Complete);
    assert_eq!(macro_result.outcome(), ScoreLoweringOutcome::Complete);
    let mut ordinary_effective = ordinary.score().unwrap().clone();
    let mut macro_effective = macro_result.score().unwrap().clone();
    for instruction in ordinary_effective
        .instructions
        .iter_mut()
        .chain(&mut macro_effective.instructions)
    {
        instruction.at = None;
    }
    assert_eq!(macro_effective, ordinary_effective);
    assert_eq!(
        macro_result.score().unwrap().instructions[1]
            .relation
            .as_ref()
            .unwrap()
            .kind,
        RelationType::NotTouching
    );
}

#[test]
fn macro_not_touching_preserves_emit_adjacency_and_omission_dependencies() {
    let unbound_between = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Path","heading":"UnboundBetween","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":"first","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}},{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"green"}}},{"op":"emit","binding":"second","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"square"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"blue"}}},{"op":"relation","kind":"not_touching","from":"first","to":"second"}]}"#,
    );
    let continued = execute_locked(
        "Path.UnboundBetween",
        std::slice::from_ref(&unbound_between),
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        continued.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{continued:?}"
    );
    assert_eq!(continued.score().unwrap().instructions.len(), 3);
    assert!(
        continued
            .score()
            .unwrap()
            .instructions
            .iter()
            .all(|instruction| instruction.relation.is_none())
    );
    assert!(continued.downstream_diagnostics().iter().any(|diagnostic| {
        matches!(
            (&diagnostic.reason, &diagnostic.disposition),
            (
                ScoreFieldGap::UnsupportedMacroRelation,
                ScoreDiagnosticDisposition::RelationOmitted
            )
        )
    }));

    let omitted_predecessor = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Path","heading":"OmittedPredecessor","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"green"}}},{"op":"emit","binding":"first","fields":{"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}},{"op":"emit","binding":"second","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"square"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"blue"}}},{"op":"relation","kind":"not_touching","from":"first","to":"second"}]}"#,
    );
    let missing = execute_locked(
        "Path.OmittedPredecessor",
        std::slice::from_ref(&omitted_predecessor),
        LIMITS,
        ScoreErrorPolicy::OmitAndContinue,
    );
    assert_eq!(
        missing.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{missing:?}"
    );
    assert_eq!(missing.score().unwrap().instructions.len(), 2);
    assert!(missing.score().unwrap().instructions[0].relation.is_none());
    assert!(missing.downstream_diagnostics().iter().any(|diagnostic| {
        matches!(
            (&diagnostic.reason, &diagnostic.disposition),
            (
                ScoreFieldGap::UnavailableMacroRelationReference,
                ScoreDiagnosticDisposition::RelationOmitted
            )
        )
    }));
}

#[test]
fn nonadjacent_macro_connected_keeps_emits_and_reports_relation_omission_in_both_policies() {
    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Path","heading":"NonAdjacent","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":"first","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"line"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}},{"op":"emit","binding":"middle","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"point"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"blue"}}},{"op":"emit","binding":"last","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"arc"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"green"}}},{"op":"relation","kind":"connected","from":"first","to":"last"}]}"#,
    );
    for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
        let result = execute_locked("Path.NonAdjacent", &[definition.clone()], LIMITS, policy);
        assert_eq!(
            result.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions,
            "{policy:?}: {result:?}"
        );
        let score = result.score().unwrap();
        assert_eq!(score.instructions.len(), 3);
        assert!(
            score
                .instructions
                .iter()
                .all(|instruction| instruction.relation.is_none())
        );
        assert!(result.downstream_diagnostics().iter().any(|diagnostic| {
            matches!(
                (
                    &diagnostic.owner,
                    &diagnostic.reason,
                    &diagnostic.disposition
                ),
                (
                    inku_ddl::ScoreDiagnosticOwner::GeneratedNode {
                        generated_ordinal: 2,
                        ..
                    },
                    ScoreFieldGap::UnsupportedMacroRelation,
                    ScoreDiagnosticDisposition::RelationOmitted,
                )
            )
        }));
    }
}

#[test]
fn checked_render_indices_join_only_to_the_exact_compiler_score_and_owner() {
    let result = execute(
        concat!(
            "place one red line at center. ",
            "place one blue line at center connected to the previous shape."
        ),
        &[],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    let score = result.score().unwrap();
    let summary = ScoreExecutionSummary {
        input_score_digest: canonical_score_digest(score).unwrap(),
        diagnostics: vec![ScoreExecutionDiagnostic {
            instruction_index: 1,
            anchor_index: None,
            dependency_instruction_index: Some(0),
            reason: ScoreExecutionReason::NumericConnectedPositionConflict,
            disposition: ScoreExecutionDisposition::Omitted,
        }],
        rendered_instruction_indices: vec![0],
    };
    let joined = map_compiler_render_execution(&result, score, Some(&summary)).unwrap();
    assert_eq!(
        joined.rendered_origins,
        [ScoreInstructionOrigin::SourceInstruction {
            instruction_index: 0
        }]
    );
    assert_eq!(
        joined.diagnostics[0].owner,
        CompilerRenderOwner::Instruction(ScoreInstructionOrigin::SourceInstruction {
            instruction_index: 1
        })
    );

    let mut different = score.clone();
    different.background = Color::Black;
    assert!(map_compiler_render_execution(&result, &different, Some(&summary)).is_err());

    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Path","heading":"OwnerPair","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":"first","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"line"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}},{"op":"emit","binding":"second","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"line"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"blue"}}},{"op":"relation","kind":"connected","from":"first","to":"second"}]}"#,
    );
    let macro_result = execute_locked(
        "Path.OwnerPair",
        &[definition],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    let macro_score = macro_result.score().unwrap();
    let macro_summary = ScoreExecutionSummary {
        input_score_digest: canonical_score_digest(macro_score).unwrap(),
        ..summary
    };
    let macro_joined =
        map_compiler_render_execution(&macro_result, macro_score, Some(&macro_summary)).unwrap();
    assert!(matches!(
        &macro_joined.diagnostics[0].owner,
        CompilerRenderOwner::Instruction(ScoreInstructionOrigin::MacroEmit {
            binding: Some(binding),
            ..
        }) if binding.local_name == "second"
    ));

    let anchor_definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Path","heading":"AnchorOwner","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":"mark","fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"line"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"},"color":{"expr":"semantic_ref","category":"color","id":"red"}}},{"op":"anchor","name":"origin","fields":{"place":{"expr":"semantic_ref","category":"place","id":"center"}}}]}"#,
    );
    let anchor_result = execute_locked(
        "Path.AnchorOwner",
        &[anchor_definition],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    let anchor_score = anchor_result.score().unwrap();
    assert_eq!(anchor_result.anchor_origins().len(), 1);
    let anchor_summary = ScoreExecutionSummary {
        input_score_digest: canonical_score_digest(anchor_score).unwrap(),
        diagnostics: vec![ScoreExecutionDiagnostic {
            instruction_index: 0,
            anchor_index: Some(0),
            dependency_instruction_index: None,
            reason: ScoreExecutionReason::InvalidTransformGroup,
            disposition: ScoreExecutionDisposition::Omitted,
        }],
        rendered_instruction_indices: vec![0],
    };
    let anchor_joined =
        map_compiler_render_execution(&anchor_result, anchor_score, Some(&anchor_summary)).unwrap();
    assert!(matches!(
        &anchor_joined.diagnostics[0].owner,
        CompilerRenderOwner::Anchor(inku_ddl::ScoreAnchorOrigin::MacroAnchor { target, .. })
            if target.local_name == "origin"
    ));
}

#[test]
fn checked_render_owner_join_rejects_a_summary_produced_from_another_score() {
    let compilation_a = execute(
        concat!(
            "place one red line at center. ",
            "place one blue line at center connected to the previous shape."
        ),
        &[],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    let compilation_b = execute(
        concat!(
            "place one green line at center. ",
            "place one yellow line at center connected to the previous shape."
        ),
        &[],
        LIMITS,
        ScoreErrorPolicy::Stop,
    );
    let mut score_b = compilation_b.score().unwrap().clone();
    score_b.instructions[1]
        .relation
        .as_mut()
        .unwrap()
        .position_authority = None;
    let rendered_b = resolve_checked_performance(
        PerformanceRequest {
            score: &score_b,
            performance_seed: None,
            composition_seed: None,
            canvas: None,
        },
        ScoreErrorPolicy::OmitAndContinue,
    )
    .expect("B retains its independent first instruction");
    let summary_b = rendered_b
        .execution
        .as_ref()
        .expect("B records its omission");

    assert_eq!(
        map_compiler_render_execution(
            &compilation_a,
            compilation_a.score().unwrap(),
            Some(summary_b),
        ),
        Err(CompilerRenderExecutionError::ScoreIdentityMismatch)
    );
}

#[test]
fn strict_stage15_api_still_rejects_a_noncanonical_compilation() {
    let document = document("mystery. place one red square at center.", &[]);
    let compilation = compile_typed_ddl(document, &[], Some(23), LIMITS);
    assert!(stage15_transformation_input(&compilation).is_err());
}

#[test]
fn declared_macro_width_and_relative_scale_conflict_recovers_like_ordinary_ddl() {
    let definition = MacroDefinition::from_json(
        &serde_json::json!({
            "schema": "inku.macro-definition.v1",
            "namespace": "Size",
            "heading": "RecoveredCircle",
            "version": "1.0.0",
            "parameters": {},
            "components": {},
            "body": [{
                "op": "emit",
                "binding": null,
                "fields": {
                    "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                    "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                    "place": {"expr": "semantic_ref", "category": "place", "id": "center"},
                    "color": {"expr": "semantic_ref", "category": "color", "id": "red"},
                    "relative_scale": {"expr": "semantic_ref", "category": "relative_scale", "id": "small"},
                    "proportion_width_extent": {"expr": "semantic_ref", "category": "ratio", "id": "full_width"}
                }
            }]
        })
        .to_string(),
    )
    .unwrap();
    let ordinary_source = "place one small red full-width circle at center.";
    for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
        let ordinary = execute(ordinary_source, &[], LIMITS, policy);
        let declared = execute_locked(
            "Size.RecoveredCircle",
            &[definition.clone()],
            LIMITS,
            policy,
        );
        for result in [&ordinary, &declared] {
            assert_eq!(
                result.outcome(),
                ScoreLoweringOutcome::Complete,
                "{:?} {:?}",
                result.upstream_diagnostics(),
                result.downstream_diagnostics()
            );
            assert!(matches!(
                result.downstream_diagnostics(),
                [inku_ddl::ScoreLoweringDiagnostic {
                    reason: ScoreFieldGap::ConflictingSizeSpecifications { .. },
                    disposition: ScoreDiagnosticDisposition::Recovered,
                    ..
                }]
            ));
        }
        let ordinary_radius = ordinary.score().unwrap().instructions[0].radius.unwrap();
        let declared_radius = declared.score().unwrap().instructions[0].radius.unwrap();
        assert!((ordinary_radius - declared_radius).abs() < 1e-12);
        assert!((declared_radius - 0.06).abs() < 1e-12);
    }
}

#[test]
fn unsupported_surface_clause_preserves_the_independent_completed_drawing() {
    let source = "背景を黒で埋める。太筆の黒い四角を中央に置く。面: 粗く塗りつぶす。";
    let continued = execute_language(
        source,
        ResolvedInstructionLanguage::Ja,
        &[],
        ScoreErrorPolicy::OmitAndContinue,
    );
    let stopped_policy = execute_language(
        source,
        ResolvedInstructionLanguage::Ja,
        &[],
        ScoreErrorPolicy::Stop,
    );
    for result in [&continued, &stopped_policy] {
        assert_eq!(
            result.compilation().compiler_lock.as_ref().unwrap().state,
            CompilerLockState::BlockedDiagnostic
        );
        assert_eq!(
            result.outcome(),
            ScoreLoweringOutcome::CompleteWithOmissions
        );
        assert!(
            result
                .upstream_diagnostics()
                .iter()
                .any(|diagnostic| diagnostic.reason == "upstream_unknown"),
            "the unsupported surface clause remains visible as a diagnostic: {:?}",
            result.upstream_diagnostics()
        );
        assert_eq!(
            result
                .score()
                .map(|score| score.instructions.len())
                .unwrap_or_default(),
            1,
            "outcome={:?}; upstream={:?}; downstream={:?}",
            result.outcome(),
            result.upstream_diagnostics(),
            result.downstream_diagnostics()
        );
    }
    assert_eq!(continued.score(), stopped_policy.score());
    assert_eq!(
        continued.upstream_diagnostics(),
        stopped_policy.upstream_diagnostics()
    );
}

fn execute(
    source: &str,
    definitions: &[MacroDefinition],
    limits: MacroExpansionLimits,
    policy: ScoreErrorPolicy,
) -> inku_ddl::CompilerExecutionResult {
    compile_ddl_to_score(
        document(source, &[]),
        definitions,
        Some(23),
        limits,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        policy,
    )
}

fn execute_language(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    policy: ScoreErrorPolicy,
) -> inku_ddl::CompilerExecutionResult {
    compile_ddl_to_score(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        definitions,
        Some(23),
        LIMITS,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        policy,
    )
}

fn execute_locked(
    source: &str,
    definitions: &[MacroDefinition],
    limits: MacroExpansionLimits,
    policy: ScoreErrorPolicy,
) -> inku_ddl::CompilerExecutionResult {
    let locks = definitions.iter().map(lock_for).collect::<Vec<_>>();
    compile_ddl_to_score(
        document(source, &locks),
        definitions,
        Some(23),
        limits,
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        policy,
    )
}

fn document(source: &str, locks: &[MacroLock]) -> NormalizedDdlDocument {
    NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, locks.to_vec()).unwrap()
}

fn definition_from(value: &str) -> MacroDefinition {
    MacroDefinition::from_json(value).unwrap()
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
