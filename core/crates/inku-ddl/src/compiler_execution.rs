//! Compile-once facade from one source-owned normalized document to an actual Score.

use inku_score::{Canvas, Score};

use crate::{
    CompilerExecutionDiagnostic, CompilerLockState, MacroDefinition, MacroExpansionLimits,
    NormalizedDdlDocument, ScoreAnchorOrigin, ScoreErrorPolicy, ScoreInstructionOrigin,
    ScoreLoweringContext, ScoreLoweringDiagnostic, ScoreLoweringOutcome, Stage15Variation,
    TypedDdlCompilation, compile_typed_ddl,
    execution_projection::{
        ExecutionProjectionResult, project_compilation_for_execution, stopped_diagnostics,
    },
    lower_verified_stage15_score_with_policy,
    stage15_transform::stage15_execution_projection_input,
    stage15_transformation_input, transform_stage15,
};

/// Stable identity for the compile-once execution envelope.
pub const COMPILER_EXECUTION_SCHEMA_ID: &str = "inku.compiler-execution.v1";

/// Original compilation evidence plus the selected execution result.
#[derive(Clone, Debug)]
pub struct CompilerExecutionResult {
    compilation: TypedDdlCompilation,
    error_policy: ScoreErrorPolicy,
    outcome: ScoreLoweringOutcome,
    score: Option<Score>,
    anchor_origins: Vec<ScoreAnchorOrigin>,
    instruction_origins: Vec<ScoreInstructionOrigin>,
    upstream_diagnostics: Vec<CompilerExecutionDiagnostic>,
    downstream_diagnostics: Vec<ScoreLoweringDiagnostic>,
    execution_pre_expansion_digest: Option<String>,
    effective_stage15_digest: Option<String>,
}

impl CompilerExecutionResult {
    pub const fn schema_id(&self) -> &'static str {
        COMPILER_EXECUTION_SCHEMA_ID
    }

    pub const fn compilation(&self) -> &TypedDdlCompilation {
        &self.compilation
    }

    pub const fn error_policy(&self) -> ScoreErrorPolicy {
        self.error_policy
    }

    pub const fn outcome(&self) -> ScoreLoweringOutcome {
        self.outcome
    }

    pub const fn score(&self) -> Option<&Score> {
        self.score.as_ref()
    }

    pub fn instruction_origins(&self) -> &[ScoreInstructionOrigin] {
        &self.instruction_origins
    }

    /// Provenance for each non-drawing Anchor in the retained Score.
    pub fn anchor_origins(&self) -> &[ScoreAnchorOrigin] {
        &self.anchor_origins
    }

    pub fn upstream_diagnostics(&self) -> &[CompilerExecutionDiagnostic] {
        &self.upstream_diagnostics
    }

    pub fn downstream_diagnostics(&self) -> &[ScoreLoweringDiagnostic] {
        &self.downstream_diagnostics
    }

    pub fn execution_pre_expansion_digest(&self) -> Option<&str> {
        self.execution_pre_expansion_digest.as_deref()
    }

    pub fn effective_stage15_digest(&self) -> Option<&str> {
        self.effective_stage15_digest.as_deref()
    }
}

/// Compile the original document exactly once and apply the selected shared Score policy.
pub fn compile_ddl_to_score(
    document: NormalizedDdlDocument,
    definitions: &[MacroDefinition],
    composition_seed: Option<u64>,
    limits: MacroExpansionLimits,
    context: ScoreLoweringContext,
    variation: Option<Stage15Variation>,
    error_policy: ScoreErrorPolicy,
) -> CompilerExecutionResult {
    let compilation = compile_typed_ddl(document, definitions, composition_seed, limits);
    execute_compilation(
        compilation,
        definitions,
        composition_seed,
        limits,
        context,
        variation,
        error_policy,
    )
}

#[allow(clippy::too_many_arguments)]
fn execute_compilation(
    compilation: TypedDdlCompilation,
    definitions: &[MacroDefinition],
    composition_seed: Option<u64>,
    limits: MacroExpansionLimits,
    context: ScoreLoweringContext,
    variation: Option<Stage15Variation>,
    error_policy: ScoreErrorPolicy,
) -> CompilerExecutionResult {
    let canonical_ready = compilation
        .compiler_lock
        .as_ref()
        .is_some_and(|lock| lock.state == CompilerLockState::CanonicalReady);

    if canonical_ready {
        let input = match stage15_transformation_input(&compilation) {
            Ok(input) => input,
            Err(_) => return stopped(compilation, error_policy),
        };
        let execution_pre_expansion_digest = Some(input.pre_expansion_digest().to_owned());
        let transformed = match transform_stage15(input, variation) {
            Ok(value) => value,
            Err(_) => return stopped(compilation, error_policy),
        };
        let effective_stage15_digest = Some(transformed.effective_canonical_digest().to_owned());
        let lowered = lower_verified_stage15_score_with_policy(
            transformed.verified_effective_view(),
            context,
            error_policy,
        );
        return CompilerExecutionResult {
            compilation,
            error_policy,
            outcome: lowered.outcome(),
            score: lowered.score().cloned(),
            anchor_origins: lowered.anchor_origins().to_vec(),
            instruction_origins: lowered.instruction_origins().to_vec(),
            upstream_diagnostics: Vec::new(),
            downstream_diagnostics: lowered.diagnostics().to_vec(),
            execution_pre_expansion_digest,
            effective_stage15_digest,
        };
    }

    match project_compilation_for_execution(
        &compilation,
        definitions,
        composition_seed,
        limits,
        context,
        variation,
    ) {
        ExecutionProjectionResult::Stopped(upstream_diagnostics) => CompilerExecutionResult {
            compilation,
            error_policy,
            outcome: ScoreLoweringOutcome::Stopped,
            score: None,
            anchor_origins: Vec::new(),
            instruction_origins: Vec::new(),
            upstream_diagnostics,
            downstream_diagnostics: Vec::new(),
            execution_pre_expansion_digest: None,
            effective_stage15_digest: None,
        },
        ExecutionProjectionResult::Ready(ready) => {
            let execution_pre_expansion_digest =
                Some(ready.projection.pre_expansion_digest.clone());
            let transformed = match transform_stage15(
                stage15_execution_projection_input(ready.projection),
                variation,
            ) {
                Ok(value) => value,
                Err(_) => return stopped(compilation, error_policy),
            };
            let effective_stage15_digest =
                Some(transformed.effective_canonical_digest().to_owned());
            let lowered = lower_verified_stage15_score_with_policy(
                transformed.verified_effective_view(),
                context,
                error_policy,
            );
            let upstream_omitted = !ready.diagnostics.is_empty();
            let score_has_drawable_content = lowered.score().is_some_and(|score| {
                !score.instructions.is_empty()
                    || transformed
                        .verified_effective_view()
                        .original_semantic_document()
                        .background
                        .is_some()
                    || matches!(
                        &score.canvas,
                        Canvas::Spec(spec) if spec.ground.is_some()
                    )
            });
            let outcome = if lowered.outcome() == ScoreLoweringOutcome::Stopped
                || (upstream_omitted && !score_has_drawable_content)
            {
                ScoreLoweringOutcome::Stopped
            } else if upstream_omitted
                || lowered.outcome() == ScoreLoweringOutcome::CompleteWithOmissions
            {
                ScoreLoweringOutcome::CompleteWithOmissions
            } else {
                ScoreLoweringOutcome::Complete
            };
            CompilerExecutionResult {
                compilation,
                error_policy,
                outcome,
                score: (outcome != ScoreLoweringOutcome::Stopped)
                    .then(|| lowered.score().cloned())
                    .flatten(),
                anchor_origins: if outcome == ScoreLoweringOutcome::Stopped {
                    Vec::new()
                } else {
                    lowered.anchor_origins().to_vec()
                },
                instruction_origins: if outcome == ScoreLoweringOutcome::Stopped {
                    Vec::new()
                } else {
                    lowered.instruction_origins().to_vec()
                },
                upstream_diagnostics: ready.diagnostics,
                downstream_diagnostics: lowered.diagnostics().to_vec(),
                execution_pre_expansion_digest,
                effective_stage15_digest,
            }
        }
    }
}

fn stopped(
    compilation: TypedDdlCompilation,
    error_policy: ScoreErrorPolicy,
) -> CompilerExecutionResult {
    let upstream_diagnostics = stopped_diagnostics(&compilation);
    CompilerExecutionResult {
        compilation,
        error_policy,
        outcome: ScoreLoweringOutcome::Stopped,
        score: None,
        anchor_origins: Vec::new(),
        instruction_origins: Vec::new(),
        upstream_diagnostics,
        downstream_diagnostics: Vec::new(),
        execution_pre_expansion_digest: None,
        effective_stage15_digest: None,
    }
}

#[cfg(test)]
mod tests {
    use sha2::{Digest, Sha256};

    use super::*;
    use crate::{MacroLock, ResolvedInstructionLanguage};
    use inku_score::Color;

    const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
        max_invocations: 4,
        max_depth: 4,
        max_evaluation_steps: 32,
        max_nodes_per_invocation: 8,
        max_total_nodes: 16,
    };

    #[test]
    fn internal_macro_owner_integrity_rejects_both_policies() {
        let definition = MacroDefinition::from_json(
            r#"{"schema":"inku.macro-definition.v1","namespace":"Guard","heading":"Mark","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"place":{"expr":"semantic_ref","category":"place","id":"center"}}}]}"#,
        )
        .unwrap();
        let identity = definition.identity().unwrap();
        let lock = MacroLock::new(
            identity.qualified_name(),
            identity.version(),
            format!("sha256:{}", identity.full_digest_hex()),
        )
        .unwrap();
        let document =
            NormalizedDdlDocument::new("Guard.Mark", ResolvedInstructionLanguage::En, vec![lock])
                .unwrap();
        let mut compilation =
            compile_typed_ddl(document, std::slice::from_ref(&definition), Some(5), LIMITS);
        compilation.macro_expansion.as_mut().unwrap().expanded[0]
            .provenance
            .invocation_ordinal += 1;
        let compiler_lock = compilation.compiler_lock.as_mut().unwrap();
        compiler_lock.state = CompilerLockState::IncompleteKnownHole;
        compiler_lock.full_digest = Sha256::digest(crate::compiler_lock_hash_input(compiler_lock))
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect();

        for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
            let result = execute_compilation(
                compilation.clone(),
                std::slice::from_ref(&definition),
                Some(5),
                LIMITS,
                ScoreLoweringContext::resolve("square", Color::White).unwrap(),
                None,
                policy,
            );
            assert_eq!(result.outcome(), ScoreLoweringOutcome::Stopped);
            assert!(result.score().is_none());
            assert!(result.instruction_origins().is_empty());
        }
    }
}
