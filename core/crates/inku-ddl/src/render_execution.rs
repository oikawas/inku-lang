//! Exact compiler-owner join for one checked renderer result.

use inku_score::{Score, ScoreExecutionDiagnostic, ScoreExecutionSummary, canonical_score_digest};

use crate::{CompilerExecutionResult, ScoreInstructionOrigin};

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CompilerRenderExecutionError {
    CompilationHasNoScore,
    ScoreIdentityMismatch,
    InstructionOriginCountMismatch,
    DiagnosticInstructionIndexOutOfRange { instruction_index: usize },
    RenderedInstructionIndexOutOfRange { instruction_index: usize },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompilerRenderDiagnostic {
    pub diagnostic: ScoreExecutionDiagnostic,
    pub owner: ScoreInstructionOrigin,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompilerRenderExecution {
    pub score_digest: String,
    pub diagnostics: Vec<CompilerRenderDiagnostic>,
    pub rendered_origins: Vec<ScoreInstructionOrigin>,
}

/// Join renderer indices only to the exact Score retained by this compilation.
pub fn map_compiler_render_execution(
    execution: &CompilerExecutionResult,
    rendered_score: &Score,
    summary: Option<&ScoreExecutionSummary>,
) -> Result<CompilerRenderExecution, CompilerRenderExecutionError> {
    let compiled_score = execution
        .score()
        .ok_or(CompilerRenderExecutionError::CompilationHasNoScore)?;
    let compiled_digest = canonical_score_digest(compiled_score)
        .map_err(|_| CompilerRenderExecutionError::ScoreIdentityMismatch)?;
    let rendered_digest = canonical_score_digest(rendered_score)
        .map_err(|_| CompilerRenderExecutionError::ScoreIdentityMismatch)?;
    if compiled_digest != rendered_digest {
        return Err(CompilerRenderExecutionError::ScoreIdentityMismatch);
    }
    if execution.instruction_origins().len() != rendered_score.instructions.len() {
        return Err(CompilerRenderExecutionError::InstructionOriginCountMismatch);
    }

    let rendered_indices = summary.map_or_else(
        || (0..rendered_score.instructions.len()).collect::<Vec<_>>(),
        |summary| summary.rendered_instruction_indices.clone(),
    );
    let rendered_origins = rendered_indices
        .iter()
        .map(|&instruction_index| {
            execution
                .instruction_origins()
                .get(instruction_index)
                .cloned()
                .ok_or(
                    CompilerRenderExecutionError::RenderedInstructionIndexOutOfRange {
                        instruction_index,
                    },
                )
        })
        .collect::<Result<Vec<_>, _>>()?;
    let diagnostics = summary
        .into_iter()
        .flat_map(|summary| &summary.diagnostics)
        .map(|diagnostic| {
            let owner = execution
                .instruction_origins()
                .get(diagnostic.instruction_index)
                .cloned()
                .ok_or(
                    CompilerRenderExecutionError::DiagnosticInstructionIndexOutOfRange {
                        instruction_index: diagnostic.instruction_index,
                    },
                )?;
            Ok(CompilerRenderDiagnostic {
                diagnostic: diagnostic.clone(),
                owner,
            })
        })
        .collect::<Result<Vec<_>, _>>()?;
    Ok(CompilerRenderExecution {
        score_digest: compiled_digest,
        diagnostics,
        rendered_origins,
    })
}
