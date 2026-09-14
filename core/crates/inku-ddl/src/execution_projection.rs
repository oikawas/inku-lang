//! Compiler-private recovery projection over one source-owned compilation.

use std::collections::BTreeSet;

use sha2::{Digest, Sha256};

use crate::{
    CompilerExecutionDiagnostic, CompilerExecutionDisposition, CompilerExecutionIssueKind,
    CompilerExecutionOmissionUnit, ExpandedMacroInvocation, MacroDefinition, MacroExpansionLimits,
    MacroInvocation, ScoreLoweringContext, SemanticDocumentAst, SemanticHead,
    SemanticPreviousReference, Stage15Variation, TypedDdlCompilation,
    compiler_lock::{
        SemanticMacroExecutionOwners, compiler_seed_identity,
        expanded_meaning_canonical_bytes_with_owners, semantic_macro_execution_owners,
        semantic_macro_execution_owners_for_projection, validate_execution_projection_boundary,
    },
    derive_macro_seed, geometry_resolution_policy_digest,
    macro_expansion::{exact_successful_expansion_subset, expand_selected_macros},
    semantic_document::canonical_ast_bytes,
};

pub(crate) struct ExecutionProjection {
    pub(crate) semantic_document: SemanticDocumentAst,
    pub(crate) expanded_invocations: Vec<ExpandedMacroInvocation>,
    pub(crate) pre_expansion_digest: String,
    pub(crate) expanded_meaning_digest: String,
    pub(crate) composition_seed: Option<u64>,
    pub(crate) geometry_policy_id: &'static str,
    pub(crate) geometry_policy_digest: String,
    pub(crate) execution_owners: SemanticMacroExecutionOwners,
    pub(crate) source_instruction_indices: Vec<usize>,
    pub(crate) source_group_indices: Vec<usize>,
}

pub(crate) struct ReadyExecutionProjection {
    pub(crate) projection: ExecutionProjection,
    pub(crate) diagnostics: Vec<CompilerExecutionDiagnostic>,
}

pub(crate) enum ExecutionProjectionResult {
    Ready(ReadyExecutionProjection),
    Stopped(Vec<CompilerExecutionDiagnostic>),
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn project_compilation_for_execution(
    compilation: &TypedDdlCompilation,
    definitions: &[MacroDefinition],
    composition_seed: Option<u64>,
    limits: MacroExpansionLimits,
    _context: ScoreLoweringContext,
    _variation: Option<Stage15Variation>,
) -> ExecutionProjectionResult {
    let Some(lock) = compilation.compiler_lock.as_ref() else {
        return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
    };
    if sha256_hex(&crate::compiler_lock_hash_input(lock)) != lock.full_digest
        || lock.geometry_policy_id != crate::GEOMETRY_RESOLUTION_POLICY_ID
        || lock.geometry_policy_digest != geometry_resolution_policy_digest()
        || compilation
            .blocking_diagnostics
            .iter()
            .any(|diagnostic| stops_all_execution(&diagnostic.kind, diagnostic.span))
    {
        return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
    }
    let Some(semantic) = compilation.semantic_document.as_ref() else {
        return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
    };

    let mut keep = vec![true; semantic.ast.instructions.len()];
    let mut omitted_clauses = BTreeSet::new();
    let mut diagnostics = Vec::new();
    for (issue_kind, issue_id, reason, span) in compiler_issues(compilation) {
        if let Some(unit) = relation_omission_unit(semantic, span) {
            diagnostics.push(CompilerExecutionDiagnostic {
                issue_kind,
                issue_id,
                reason,
                span,
                disposition: CompilerExecutionDisposition::RelationOmitted { unit },
            });
            continue;
        }
        let unit =
            if reason == "conflicting_grounds" {
                CompilerExecutionOmissionUnit::GroundCandidates
            } else if reason == "conflicting_backgrounds" {
                CompilerExecutionOmissionUnit::BackgroundCandidates
            } else if let Some(span) = span {
                let exact_macro = semantic.ast.instructions.iter().enumerate().find_map(
                    |(index, instruction)| match &instruction.entity.head {
                        SemanticHead::MacroInvocation(head)
                            if head.provenance.source.span == span =>
                        {
                            Some((index, head.provenance.ordinal))
                        }
                        SemanticHead::Primitive(_) | SemanticHead::MacroInvocation(_) => None,
                    },
                );
                if let Some((index, invocation_ordinal)) = exact_macro {
                    keep[index] = false;
                    CompilerExecutionOmissionUnit::MacroInvocation {
                        source_instruction_index: index,
                        invocation_ordinal,
                    }
                } else {
                    let clauses = clauses_for_span(compilation, span);
                    omitted_clauses.extend(clauses.iter().copied());
                    let indices = semantic
                        .ast
                        .instructions
                        .iter()
                        .enumerate()
                        .filter_map(|(index, instruction)| {
                            clauses
                                .contains(&instruction.entity.head.source().clause_index)
                                .then_some(index)
                        })
                        .collect::<Vec<_>>();
                    if indices.is_empty() {
                        CompilerExecutionOmissionUnit::Clause {
                            clause_index: clauses.first().copied().unwrap_or(0),
                        }
                    } else {
                        for index in &indices {
                            keep[*index] = false;
                        }
                        macro_or_instruction_unit(&semantic.ast, &indices)
                    }
                }
            } else {
                return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
            };
        diagnostics.push(CompilerExecutionDiagnostic {
            issue_kind,
            issue_id,
            reason,
            span,
            disposition: CompilerExecutionDisposition::Omitted { unit },
        });
    }

    omit_typed_dependencies(semantic, &omitted_clauses, &mut keep, &mut diagnostics);
    let (mut projected_ast, mut source_instruction_indices, mut source_group_indices) =
        retain_ast(&semantic.ast, &keep);
    projected_ast.ground = if !semantic
        .issues
        .iter()
        .any(|issue| issue.kind == crate::SemanticDocumentIssueKind::ConflictingGrounds)
    {
        semantic.ast.ground.clone()
    } else {
        None
    };
    projected_ast.complete = true;

    let Some(binding) = compilation.accepted_parameter_binding().cloned() else {
        return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
    };
    let original_owners = semantic
        .canonical_bytes
        .as_ref()
        .map(|_| semantic_macro_execution_owners(&semantic.ast, &binding))
        .transpose();
    let original_ordinals = match original_owners {
        Ok(Some(owners)) => Some(owners.source_semantic_ordinals()),
        Ok(None) => None,
        Err(_) => return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation)),
    };
    let mut omitted_binding_indices = omitted_bindings(&projected_ast, &binding);
    let mut owners = match semantic_macro_execution_owners_for_projection(
        &projected_ast,
        &binding,
        original_ordinals.as_ref(),
        &omitted_binding_indices,
    ) {
        Ok(owners) => owners,
        Err(_) => return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation)),
    };
    let projection_ordinals = owners.source_semantic_ordinals();

    let projected_bytes = canonical_ast_bytes(&projected_ast);
    let seed_bytes = semantic
        .canonical_bytes
        .as_deref()
        .unwrap_or(projected_bytes.as_slice());
    let seed_text = match std::str::from_utf8(seed_bytes) {
        Ok(value) => value,
        Err(_) => return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation)),
    };

    let (mut expansion, seed_identities) = if semantic.canonical_bytes.is_some() {
        let Some(existing) = compilation.macro_expansion.as_ref() else {
            return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
        };
        if existing
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.kind.stops_all_execution())
        {
            return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
        }
        let retained = owners
            .owners()
            .iter()
            .map(|owner| owner.source_ordinal)
            .collect::<BTreeSet<_>>();
        let subset = match exact_successful_expansion_subset(existing, &retained) {
            Ok(value) => value,
            Err(_) => return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation)),
        };
        let selected_seeds = owners
            .owners()
            .iter()
            .filter_map(|owner| {
                compilation
                    .derived_seeds
                    .iter()
                    .find(|seed| seed.ordinal() == owner.semantic_ordinal)
                    .cloned()
            })
            .collect::<Vec<_>>();
        if selected_seeds.len() != owners.owners().len() {
            return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
        }
        let identities = selected_seeds
            .iter()
            .map(compiler_seed_identity)
            .collect::<Vec<_>>();
        (subset, identities)
    } else {
        let selected_seeds =
            match derive_projection_seeds(seed_text, &binding, &owners, composition_seed) {
                Ok(value) => value,
                Err(_) => {
                    return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
                }
            };
        let expanded = expand_selected_macros(
            binding.clone(),
            definitions,
            &selected_seeds,
            limits,
            owners.expansion_selection(),
        );
        if expanded
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.kind.stops_all_execution())
        {
            return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
        }
        let failed_ordinals = expanded
            .diagnostics
            .iter()
            .filter_map(|diagnostic| diagnostic.invocation_ordinal)
            .collect::<BTreeSet<_>>();
        if !failed_ordinals.is_empty() {
            for (projected_index, instruction) in projected_ast.instructions.iter().enumerate() {
                let SemanticHead::MacroInvocation(head) = &instruction.entity.head else {
                    continue;
                };
                if failed_ordinals.contains(&head.provenance.ordinal) {
                    let source_index = source_instruction_indices[projected_index];
                    diagnostics.push(CompilerExecutionDiagnostic {
                        issue_kind: CompilerExecutionIssueKind::Hole,
                        issue_id: format!("macro-expansion:{}", head.provenance.ordinal),
                        reason: "local_macro_expansion_failure".to_owned(),
                        span: Some(head.provenance.source.span),
                        disposition: CompilerExecutionDisposition::Omitted {
                            unit: CompilerExecutionOmissionUnit::MacroInvocation {
                                source_instruction_index: source_index,
                                invocation_ordinal: head.provenance.ordinal,
                            },
                        },
                    });
                }
            }
            let mut second_keep = projected_ast
                .instructions
                .iter()
                .map(|instruction| match &instruction.entity.head {
                    SemanticHead::MacroInvocation(head) => {
                        !failed_ordinals.contains(&head.provenance.ordinal)
                    }
                    SemanticHead::Primitive(_) => true,
                })
                .collect::<Vec<_>>();
            omit_projected_dependencies(
                &projected_ast,
                &mut second_keep,
                &source_instruction_indices,
                &source_group_indices,
                &mut diagnostics,
            );
            let (filtered, retained_projected_indices, retained_projected_groups) =
                retain_ast(&projected_ast, &second_keep);
            source_instruction_indices = retained_projected_indices
                .iter()
                .map(|index| source_instruction_indices[*index])
                .collect();
            source_group_indices = retained_projected_groups
                .iter()
                .map(|index| source_group_indices[*index])
                .collect();
            projected_ast = filtered;
            projected_ast.complete = true;
            omitted_binding_indices = omitted_bindings(&projected_ast, &binding);
            owners = match semantic_macro_execution_owners_for_projection(
                &projected_ast,
                &binding,
                Some(&projection_ordinals),
                &omitted_binding_indices,
            ) {
                Ok(value) => value,
                Err(_) => {
                    return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
                }
            };
        }
        let retained = owners
            .owners()
            .iter()
            .map(|owner| owner.source_ordinal)
            .collect::<BTreeSet<_>>();
        let subset = match exact_successful_expansion_subset(&expanded, &retained) {
            Ok(value) => value,
            Err(_) => return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation)),
        };
        let selected = selected_seeds
            .into_iter()
            .filter(|seed| {
                owners
                    .owners()
                    .iter()
                    .any(|owner| owner.semantic_ordinal == seed.ordinal())
            })
            .collect::<Vec<_>>();
        let identities = selected.iter().map(compiler_seed_identity).collect();
        (subset, identities)
    };

    if validate_execution_projection_boundary(
        &compilation.document,
        &projected_ast,
        lock,
        &expansion.parameter_binding,
        &owners,
        definitions,
    )
    .is_err()
        || owners
            .validate_seed_identities(seed_bytes, &expansion, &seed_identities, composition_seed)
            .is_err()
    {
        return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation));
    }
    let expanded_bytes = match expanded_meaning_canonical_bytes_with_owners(&owners, &expansion) {
        Ok(value) => value,
        Err(_) => return ExecutionProjectionResult::Stopped(stopped_diagnostics(compilation)),
    };
    let projection_bytes = canonical_ast_bytes(&projected_ast);
    let projection = ExecutionProjection {
        semantic_document: projected_ast,
        expanded_invocations: std::mem::take(&mut expansion.expanded),
        pre_expansion_digest: sha256_hex(&projection_bytes),
        expanded_meaning_digest: sha256_hex(&expanded_bytes),
        composition_seed,
        geometry_policy_id: lock.geometry_policy_id,
        geometry_policy_digest: lock.geometry_policy_digest.clone(),
        execution_owners: owners,
        source_instruction_indices,
        source_group_indices,
    };
    ExecutionProjectionResult::Ready(ReadyExecutionProjection {
        projection,
        diagnostics,
    })
}

fn relation_omission_unit(
    semantic: &crate::SemanticDocumentResult,
    span: Option<crate::SourceSpan>,
) -> Option<CompilerExecutionOmissionUnit> {
    let span = span?;
    let issue = semantic
        .instruction_association
        .relation_issues
        .iter()
        .find(|issue| {
            issue
                .occurrences
                .iter()
                .any(|occurrence| occurrence.provenance.span == span)
        })?;
    let instruction_index = semantic.ast.instructions.iter().position(|instruction| {
        instruction.entity.head.source().region_index == issue.region_index
    })?;
    Some(CompilerExecutionOmissionUnit::RelationInstruction {
        instruction_index,
        dependency_instruction_indices: Vec::new(),
    })
}

fn omit_projected_dependencies(
    ast: &SemanticDocumentAst,
    keep: &mut [bool],
    source_instruction_indices: &[usize],
    source_group_indices: &[usize],
    diagnostics: &mut Vec<CompilerExecutionDiagnostic>,
) {
    loop {
        let before = keep.to_vec();
        for (group_index, group) in ast.coordinated_head_groups.iter().enumerate() {
            if group
                .member_instruction_indices
                .iter()
                .any(|index| !keep[*index])
            {
                for index in &group.member_instruction_indices {
                    keep[*index] = false;
                }
                let issue_id = format!("group-dependency:{}", source_group_indices[group_index]);
                if !diagnostics
                    .iter()
                    .any(|diagnostic| diagnostic.issue_id == issue_id)
                {
                    diagnostics.push(CompilerExecutionDiagnostic {
                        issue_kind: CompilerExecutionIssueKind::Dependency,
                        issue_id,
                        reason: "coordinated_group_dependency".to_owned(),
                        span: group.markers.first().map(|marker| marker.span),
                        disposition: CompilerExecutionDisposition::Omitted {
                            unit: CompilerExecutionOmissionUnit::CoordinatedGroup {
                                group_index: source_group_indices[group_index],
                                member_instruction_indices: group
                                    .member_instruction_indices
                                    .iter()
                                    .map(|index| source_instruction_indices[*index])
                                    .collect(),
                            },
                        },
                    });
                }
            }
        }
        for (index, instruction) in ast.instructions.iter().enumerate() {
            if !keep[index] {
                continue;
            }
            let Some(relation) = &instruction.relation else {
                continue;
            };
            let required = match relation.reference {
                SemanticPreviousReference::PreviousOne => 1,
                SemanticPreviousReference::PreviousTwo => 2,
            };
            let dependencies = (index.saturating_sub(required)..index).collect::<Vec<_>>();
            if index < required || dependencies.iter().any(|dependency| !keep[*dependency]) {
                keep[index] = false;
                diagnostics.push(CompilerExecutionDiagnostic {
                    issue_kind: CompilerExecutionIssueKind::Dependency,
                    issue_id: format!("relation-dependency:{}", source_instruction_indices[index]),
                    reason: "relation_dependency".to_owned(),
                    span: Some(relation.provenance.span),
                    disposition: CompilerExecutionDisposition::Omitted {
                        unit: CompilerExecutionOmissionUnit::RelationInstruction {
                            instruction_index: source_instruction_indices[index],
                            dependency_instruction_indices: dependencies
                                .iter()
                                .map(|dependency| source_instruction_indices[*dependency])
                                .collect(),
                        },
                    },
                });
            }
        }
        if before == keep {
            break;
        }
    }
}

fn derive_projection_seeds(
    canonical: &str,
    binding: &crate::MacroParameterBindingResult,
    owners: &SemanticMacroExecutionOwners,
    composition_seed: Option<u64>,
) -> Result<Vec<crate::MacroSeed>, ()> {
    owners
        .owners()
        .iter()
        .map(|owner| {
            let complete = binding.complete.get(owner.binding_index).ok_or(())?;
            let resolved = binding
                .macro_resolution
                .resolved
                .get(complete.invocation_index)
                .ok_or(())?;
            let invocation = MacroInvocation::new(
                resolved.invocation.namespace(),
                resolved.invocation.heading(),
                owner.semantic_ordinal,
            )
            .map_err(|_| ())?;
            Ok(derive_macro_seed(canonical, &invocation, composition_seed))
        })
        .collect()
}

fn compiler_issues(
    compilation: &TypedDdlCompilation,
) -> Vec<(
    CompilerExecutionIssueKind,
    String,
    String,
    Option<crate::SourceSpan>,
)> {
    compilation
        .holes
        .iter()
        .map(|issue| {
            (
                CompilerExecutionIssueKind::Hole,
                issue.id.clone(),
                issue.kind.clone(),
                Some(issue.span),
            )
        })
        .chain(compilation.conflicts.iter().map(|issue| {
            (
                CompilerExecutionIssueKind::Conflict,
                issue.id.clone(),
                issue.kind.clone(),
                issue.span,
            )
        }))
        .chain(compilation.blocking_diagnostics.iter().map(|issue| {
            (
                CompilerExecutionIssueKind::BlockingDiagnostic,
                issue.id.clone(),
                issue.kind.clone(),
                issue.span,
            )
        }))
        .collect()
}

pub(crate) fn stopped_diagnostics(
    compilation: &TypedDdlCompilation,
) -> Vec<CompilerExecutionDiagnostic> {
    let mut diagnostics = compiler_issues(compilation)
        .into_iter()
        .map(
            |(issue_kind, issue_id, reason, span)| CompilerExecutionDiagnostic {
                issue_kind,
                issue_id,
                reason,
                span,
                disposition: CompilerExecutionDisposition::Stopped,
            },
        )
        .collect::<Vec<_>>();
    if diagnostics.is_empty() {
        diagnostics.push(CompilerExecutionDiagnostic {
            issue_kind: CompilerExecutionIssueKind::BlockingDiagnostic,
            issue_id: "execution_projection_integrity".to_owned(),
            reason: "execution_projection_integrity".to_owned(),
            span: None,
            disposition: CompilerExecutionDisposition::Stopped,
        });
    }
    diagnostics
}

fn stops_all_execution(kind: &str, span: Option<crate::SourceSpan>) -> bool {
    span.is_none()
        || matches!(
            kind,
            "invalid_expansion_limits"
                | "clause_stream_integrity"
                | "missing_canonical_semantic_identity"
                | "coordination_marker_delivery_integrity"
                | "continuation_claim_owner_integrity"
                | "missing_continuation_original_instruction"
                | "expansion_invocation_budget"
                | "expansion_total_node_budget"
                | "missing_derived_seed"
                | "duplicate_derived_seed"
                | "mismatched_derived_seed"
                | "expansion_definition_ownership"
                | "expansion_binding_ownership"
                | "expansion_target_ownership"
                | "expansion_provenance_ownership"
        )
}

fn clauses_for_span(compilation: &TypedDdlCompilation, span: crate::SourceSpan) -> Vec<usize> {
    compilation
        .accepted_parameter_binding()
        .map(|binding| {
            binding
                .macro_resolution
                .relation_reference_evidence
                .attachment_evidence
                .noun_phrase
                .clause_stream
                .clauses
                .iter()
                .enumerate()
                .filter_map(|(index, clause)| {
                    clause
                        .atoms
                        .iter()
                        .any(|atom| spans_overlap(atom.span(), span))
                        .then_some(index)
                })
                .collect()
        })
        .unwrap_or_default()
}

fn spans_overlap(left: crate::SourceSpan, right: crate::SourceSpan) -> bool {
    left.start_byte < right.end_byte && right.start_byte < left.end_byte
}

fn macro_or_instruction_unit(
    ast: &SemanticDocumentAst,
    indices: &[usize],
) -> CompilerExecutionOmissionUnit {
    if indices.len() == 1
        && let SemanticHead::MacroInvocation(head) = &ast.instructions[indices[0]].entity.head
    {
        return CompilerExecutionOmissionUnit::MacroInvocation {
            source_instruction_index: indices[0],
            invocation_ordinal: head.provenance.ordinal,
        };
    }
    CompilerExecutionOmissionUnit::SourceInstructions {
        instruction_indices: indices.to_vec(),
    }
}

fn omit_typed_dependencies(
    semantic: &crate::SemanticDocumentResult,
    omitted_clauses: &BTreeSet<usize>,
    keep: &mut [bool],
    diagnostics: &mut Vec<CompilerExecutionDiagnostic>,
) {
    for issue in &semantic.instruction_association.coordination_issues {
        let member_spans = issue
            .member_instruction_indices
            .iter()
            .filter_map(|index| {
                semantic
                    .instruction_association
                    .ast
                    .instructions
                    .get(*index)
            })
            .map(|instruction| instruction.entity.head.source().span)
            .collect::<Vec<_>>();
        let members = semantic
            .ast
            .instructions
            .iter()
            .enumerate()
            .filter_map(|(index, instruction)| {
                member_spans
                    .contains(&instruction.entity.head.source().span)
                    .then_some(index)
            })
            .collect::<Vec<_>>();
        for index in &members {
            keep[*index] = false;
        }
        if !members.is_empty() {
            diagnostics.push(CompilerExecutionDiagnostic {
                issue_kind: CompilerExecutionIssueKind::Dependency,
                issue_id: format!("coordination:{}", issue.kind.as_str()),
                reason: issue.kind.as_str().to_owned(),
                span: issue.markers.first().map(|marker| marker.span),
                disposition: CompilerExecutionDisposition::Omitted {
                    unit: CompilerExecutionOmissionUnit::CoordinatedGroup {
                        group_index: issue
                            .member_instruction_indices
                            .first()
                            .copied()
                            .unwrap_or(0),
                        member_instruction_indices: members,
                    },
                },
            });
        }
    }
    for edge in &semantic.ast.continuations {
        if omitted_clauses.contains(&edge.reintroduced_head.source().clause_index)
            || omitted_clauses.contains(&edge.marker.clause_index)
            || omitted_clauses.iter().any(|clause| {
                edge.consumed_upstream_spans
                    .iter()
                    .any(|span| clauses_for_semantic(semantic, *span).contains(clause))
            })
        {
            keep[edge.target_instruction_index] = false;
            diagnostics.push(CompilerExecutionDiagnostic {
                issue_kind: CompilerExecutionIssueKind::Dependency,
                issue_id: format!("continuation-target:{}", edge.target_instruction_index),
                reason: "accepted_continuation_dependency".to_owned(),
                span: Some(edge.predicate_span),
                disposition: CompilerExecutionDisposition::Omitted {
                    unit: CompilerExecutionOmissionUnit::AcceptedContinuationTarget {
                        target_instruction_index: edge.target_instruction_index,
                    },
                },
            });
        }
    }
    loop {
        let before = keep.to_vec();
        for (group_index, group) in semantic.ast.coordinated_head_groups.iter().enumerate() {
            let target_missing = semantic.ast.group_predicates.iter().any(|edge| edge.group_index == group_index
                && matches!(&edge.fill_target, Some(crate::SemanticFillTarget::InlineShape {target_instruction_index, ..}) if !keep[*target_instruction_index]));
            if group
                .member_instruction_indices
                .iter()
                .any(|index| !keep[*index])
                || target_missing
            {
                for index in &group.member_instruction_indices {
                    keep[*index] = false;
                }
                if !diagnostics.iter().any(|diagnostic| {
                    matches!(
                        &diagnostic.disposition,
                        CompilerExecutionDisposition::Omitted {
                            unit: CompilerExecutionOmissionUnit::CoordinatedGroup {
                                group_index: existing,
                                ..
                            }
                        } if *existing == group_index
                    )
                }) {
                    diagnostics.push(CompilerExecutionDiagnostic {
                        issue_kind: CompilerExecutionIssueKind::Dependency,
                        issue_id: format!("group-dependency:{group_index}"),
                        reason: "coordinated_group_dependency".to_owned(),
                        span: group.markers.first().map(|marker| marker.span),
                        disposition: CompilerExecutionDisposition::Omitted {
                            unit: CompilerExecutionOmissionUnit::CoordinatedGroup {
                                group_index,
                                member_instruction_indices: group
                                    .member_instruction_indices
                                    .clone(),
                            },
                        },
                    });
                }
            }
        }
        for (index, instruction) in semantic.ast.instructions.iter().enumerate() {
            if !keep[index] {
                continue;
            }
            // Losing an inline operand cannot rebind a fill after compaction.
            if let Some(crate::SemanticFillTarget::InlineShape {
                target_instruction_index,
                ..
            }) = &instruction.fill_target
                && !keep[*target_instruction_index]
            {
                keep[index] = false;
                diagnostics.push(CompilerExecutionDiagnostic {
                    issue_kind: CompilerExecutionIssueKind::Dependency,
                    issue_id: format!("fill-target:{index}:{target_instruction_index}"),
                    reason: "fill_target_dependency".to_owned(),
                    span: Some(instruction.entity.head.source().span),
                    disposition: CompilerExecutionDisposition::Omitted {
                        unit: CompilerExecutionOmissionUnit::SourceInstructions {
                            instruction_indices: vec![index],
                        },
                    },
                });
                continue;
            }
            let Some(relation) = &instruction.relation else {
                continue;
            };
            let required = match relation.reference {
                SemanticPreviousReference::PreviousOne => 1,
                SemanticPreviousReference::PreviousTwo => 2,
            };
            let dependencies = (index.saturating_sub(required)..index).collect::<Vec<_>>();
            if index < required || dependencies.iter().any(|dependency| !keep[*dependency]) {
                keep[index] = false;
                diagnostics.push(CompilerExecutionDiagnostic {
                    issue_kind: CompilerExecutionIssueKind::Dependency,
                    issue_id: format!("relation-dependency:{index}"),
                    reason: "relation_dependency".to_owned(),
                    span: Some(relation.provenance.span),
                    disposition: CompilerExecutionDisposition::Omitted {
                        unit: CompilerExecutionOmissionUnit::RelationInstruction {
                            instruction_index: index,
                            dependency_instruction_indices: dependencies,
                        },
                    },
                });
            }
        }
        if before == keep {
            break;
        }
    }
}

fn clauses_for_semantic(
    semantic: &crate::SemanticDocumentResult,
    span: crate::SourceSpan,
) -> Vec<usize> {
    semantic
        .instruction_association
        .association
        .clause_stream
        .clauses
        .iter()
        .enumerate()
        .filter_map(|(index, clause)| {
            clause
                .atoms
                .iter()
                .any(|atom| spans_overlap(atom.span(), span))
                .then_some(index)
        })
        .collect()
}

fn retain_ast(
    ast: &SemanticDocumentAst,
    keep: &[bool],
) -> (SemanticDocumentAst, Vec<usize>, Vec<usize>) {
    let mut index_map = vec![None; ast.instructions.len()];
    let mut source_instruction_indices = Vec::new();
    let mut instructions = ast
        .instructions
        .iter()
        .enumerate()
        .filter_map(|(index, instruction)| {
            keep[index].then(|| {
                index_map[index] = Some(source_instruction_indices.len());
                source_instruction_indices.push(index);
                instruction.clone()
            })
        })
        .collect::<Vec<_>>();
    for instruction in &mut instructions {
        let Some(sequence) = &mut instruction.sequence else {
            continue;
        };
        if !matches!(sequence.kind, crate::SemanticSequenceKind::Units) {
            continue;
        }
        let remapped = sequence
            .units
            .iter()
            .map(|unit| {
                unit.member_entity_indices
                    .iter()
                    .map(|index| index_map[*index])
                    .collect::<Option<Vec<_>>>()
                    .map(|member_entity_indices| crate::SemanticSequenceUnit {
                        member_entity_indices,
                        source_span: unit.source_span,
                    })
            })
            .collect::<Option<Vec<_>>>();
        if let Some(units) = remapped {
            sequence.units = units;
        } else {
            instruction.sequence = None;
        }
    }
    crate::semantic_document::remap_fill_targets(&mut instructions, &index_map);
    let mut group_map = vec![None; ast.coordinated_head_groups.len()];
    let mut source_group_indices = Vec::new();
    let coordinated_head_groups = ast
        .coordinated_head_groups
        .iter()
        .enumerate()
        .filter_map(|(group_index, group)| {
            group
                .member_instruction_indices
                .iter()
                .map(|index| index_map[*index])
                .collect::<Option<Vec<_>>>()
                .map(|member_instruction_indices| {
                    group_map[group_index] = Some(source_group_indices.len());
                    source_group_indices.push(group_index);
                    crate::SemanticCoordinatedHeadGroup {
                        member_instruction_indices,
                        markers: group.markers.clone(),
                    }
                })
        })
        .collect();
    let group_predicates = ast
        .group_predicates
        .iter()
        .filter_map(|edge| {
            group_map[edge.group_index].map(|group_index| {
                let mut fill_target = edge.fill_target.clone();
                crate::semantic_document::remap_fill_target(&mut fill_target, &index_map);
                crate::SemanticGroupPredicateEdge {
                    group_index,
                    action: edge.action.clone(),
                    position: edge.position.clone(),
                    layout: edge.layout,
                    fill_target,
                }
            })
        })
        .collect();
    let continuations = ast
        .continuations
        .iter()
        .filter_map(|edge| {
            index_map[edge.target_instruction_index].map(|target_instruction_index| {
                let mut edge = edge.clone();
                edge.target_instruction_index = target_instruction_index;
                edge
            })
        })
        .collect();
    (
        SemanticDocumentAst {
            background: ast.background.clone(),
            ground: ast.ground.clone(),
            instructions,
            coordinated_head_groups,
            group_predicates,
            continuations,
            complete: true,
        },
        source_instruction_indices,
        source_group_indices,
    )
}

fn omitted_bindings(
    ast: &SemanticDocumentAst,
    binding: &crate::MacroParameterBindingResult,
) -> BTreeSet<usize> {
    let retained = ast
        .instructions
        .iter()
        .filter_map(|instruction| match &instruction.entity.head {
            SemanticHead::MacroInvocation(head) => Some(head.provenance.ordinal),
            SemanticHead::Primitive(_) => None,
        })
        .chain(
            ast.continuations
                .iter()
                .filter_map(|edge| match &edge.reintroduced_head {
                    SemanticHead::MacroInvocation(head) => Some(head.provenance.ordinal),
                    SemanticHead::Primitive(_) => None,
                }),
        )
        .collect::<BTreeSet<_>>();
    binding
        .complete
        .iter()
        .enumerate()
        .filter_map(|(index, complete)| {
            (!retained.contains(&complete.invocation_ordinal)).then_some(index)
        })
        .collect()
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
