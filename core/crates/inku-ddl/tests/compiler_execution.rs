use inku_ddl::{
    CompilerExecutionDisposition, CompilerExecutionOmissionUnit, CompilerLockState,
    MacroDefinition, MacroExpansionLimits, MacroLock, NormalizedDdlDocument,
    ResolvedInstructionLanguage, ScoreDiagnosticDisposition, ScoreErrorPolicy, ScoreFieldGap,
    ScoreInstructionOrigin, ScoreLoweringContext, ScoreLoweringOutcome, ScoreOmissionUnit,
    SemanticPreviousReference, SemanticRelationKind, compile_ddl_to_score, compile_typed_ddl,
    saijiki_asset, stage15_transformation_input,
};
use inku_score::{Canvas, Color, GroundMaterial, Primitive, RelationType};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 8,
    max_depth: 8,
    max_evaluation_steps: 64,
    max_nodes_per_invocation: 32,
    max_total_nodes: 64,
};

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
    assert_eq!(stopped.outcome(), ScoreLoweringOutcome::Stopped);
    assert!(stopped.score().is_none());

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
fn stop_retains_the_original_failure_and_returns_no_score() {
    let result = execute(
        "place many red circle at horizontal 0.5, vertical 0.5. place one red square at center.",
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
            .all(|diagnostic| { diagnostic.disposition == CompilerExecutionDisposition::Stopped })
    );
}

#[test]
fn continue_omits_a_typed_count_failure_and_keeps_an_independent_instruction() {
    let source =
        "place many red circle at horizontal 0.5, vertical 0.5. place one red square at center.";
    let result = execute(source, &[], LIMITS, ScoreErrorPolicy::OmitAndContinue);

    assert_eq!(result.compilation().document.source(), source);
    assert_eq!(
        result.compilation().compiler_lock.as_ref().unwrap().state,
        CompilerLockState::BlockedConflict
    );
    assert!(!result.compilation().holes.is_empty());
    assert_eq!(
        result.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{:?}",
        result
    );
    let score = result
        .score()
        .expect("independent instruction remains executable");
    assert_eq!(score.instructions.len(), 1);
    assert_eq!(score.instructions[0].primitive, Primitive::Square);
    assert_eq!(
        result.instruction_origins(),
        [ScoreInstructionOrigin::SourceInstruction {
            instruction_index: 1
        }]
    );
    assert!(
        result
            .upstream_diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                diagnostic.disposition,
                CompilerExecutionDisposition::Omitted { .. }
            ))
    );
    assert!(result.execution_pre_expansion_digest().is_some());
    assert!(result.effective_stage15_digest().is_some());
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
    assert!(
        grouped
            .upstream_diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                diagnostic.disposition,
                CompilerExecutionDisposition::Omitted {
                    unit: CompilerExecutionOmissionUnit::CoordinatedGroup { .. }
                }
            ))
    );

    let relation = saijiki_asset()
        .relations
        .iter()
        .find_map(|entry| entry.literals_en.first())
        .expect("the accepted asset has an English relation literal");
    let source = format!(
        "place many red circle at center. place one blue circle at center {relation}. place one green square at center."
    );
    let related = execute(&source, &[], LIMITS, ScoreErrorPolicy::OmitAndContinue);
    assert_eq!(
        related.outcome(),
        ScoreLoweringOutcome::CompleteWithOmissions,
        "{:?}",
        related
    );
    assert_eq!(related.score().unwrap().instructions.len(), 1);
    assert!(
        related
            .upstream_diagnostics()
            .iter()
            .any(|diagnostic| matches!(
                diagnostic.disposition,
                CompilerExecutionDisposition::Omitted {
                    unit: CompilerExecutionOmissionUnit::RelationInstruction { .. }
                }
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
    assert_eq!(result.score().unwrap().instructions.len(), 1);
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
                    ScoreDiagnosticDisposition::Omitted {
                        unit: ScoreOmissionUnit::RelationInstruction {
                            instruction_index: 1
                        },
                        ..
                    }
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
    assert!(result.downstream_diagnostics().is_empty());
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
fn strict_stage15_api_still_rejects_a_noncanonical_compilation() {
    let document = document("mystery. place one red square at center.", &[]);
    let compilation = compile_typed_ddl(document, &[], Some(23), LIMITS);
    assert!(stage15_transformation_input(&compilation).is_err());
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
