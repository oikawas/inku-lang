//! Document-global semantic ownership over the accepted instruction association.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;

use crate::{
    AttachmentMarkerKind, ClauseAtom, ClauseStreamError, CoreRoleKind,
    JapaneseAttachmentMarkerKind, MacroParameterBindingResult, NormalizedDdlDocument,
    OwnedSemanticOccurrence, ResolvedInstructionLanguage, SemanticAssociationIssueKind,
    SemanticHead, SemanticIdentity, SemanticInstruction, SemanticInstructionAssociationResult,
    SemanticInstructionIssueKind, SemanticIssueCausalProvenance, SemanticTerm,
    SemanticUpstreamCausalRelation, SourceOccurrence, SourceSpan, associate_semantic_instructions,
    associate_semantic_instructions_with_macro_binding,
    semantic_association::{
        causal_provenance, diagnostic_causes_in_source_range, project_semantic_term,
        semantic_identity_value, sentence_region_index,
    },
    semantic_instruction::{
        semantic_coordinated_head_group_value, semantic_group_predicate_value,
        semantic_instruction_value,
    },
};

/// Stable identity for the runtime-disconnected semantic document root.
pub const SEMANTIC_DOCUMENT_SCHEMA_ID: &str = "inku.semantic-document.v12";

/// Source-independent identity of one continuation target.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SemanticContinuationTarget {
    Primitive(SemanticIdentity),
    MacroInvocation {
        qualified_name: String,
        definition_version: String,
        definition_digest: String,
    },
}

/// One source-owned marked-subject continuation into a unique prior instruction.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticContinuationEdge {
    pub target: SemanticContinuationTarget,
    pub target_instruction_index: usize,
    pub reintroduced_head: SemanticHead,
    pub marker: SourceOccurrence,
    pub predicate_span: SourceSpan,
    pub consumed_upstream_spans: Vec<SourceSpan>,
}

/// Document-global semantic AST with accepted drawable instructions and optional support material.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticDocumentAst {
    pub ground: Option<SemanticTerm>,
    pub instructions: Vec<SemanticInstruction>,
    pub coordinated_head_groups: Vec<crate::SemanticCoordinatedHeadGroup>,
    pub group_predicates: Vec<crate::SemanticGroupPredicateEdge>,
    pub continuations: Vec<SemanticContinuationEdge>,
    pub complete: bool,
}

/// Stable document-root issue classes.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticDocumentIssueKind {
    ConflictingGrounds,
}

impl SemanticDocumentIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ConflictingGrounds => "conflicting_grounds",
        }
    }
}

/// One document-root issue owning every conflicting Ground occurrence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticDocumentIssue {
    pub kind: SemanticDocumentIssueKind,
    pub occurrences: Vec<SemanticTerm>,
}

/// Stable fail-closed continuation issue classes.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SemanticContinuationIssueKind {
    MissingTarget,
    AmbiguousTarget,
    ConflictingPredicate,
    UnsupportedPredicate,
    BlockedBoundary,
}

impl SemanticContinuationIssueKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::MissingTarget => "missing_continuation_target",
            Self::AmbiguousTarget => "ambiguous_continuation_target",
            Self::ConflictingPredicate => "conflicting_continuation_predicate",
            Self::UnsupportedPredicate => "unsupported_continuation_predicate",
            Self::BlockedBoundary => "blocked_continuation_boundary",
        }
    }
}

/// One unresolved marked-subject continuation with all source-owned evidence retained.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticContinuationIssue {
    pub kind: SemanticContinuationIssueKind,
    pub instruction: SemanticInstruction,
    pub marker: SourceOccurrence,
    pub predicate_span: SourceSpan,
    pub candidate_targets: Vec<SemanticContinuationTarget>,
    pub consumed_upstream_spans: Vec<SourceSpan>,
    pub causal_provenance: SemanticIssueCausalProvenance,
}

/// Source-preserving document semantic result over the accepted instruction chain.
#[derive(Clone, Debug, PartialEq)]
pub struct SemanticDocumentResult {
    pub schema_id: &'static str,
    pub instruction_association: SemanticInstructionAssociationResult,
    pub ast: SemanticDocumentAst,
    pub issues: Vec<SemanticDocumentIssue>,
    pub continuation_issues: Vec<SemanticContinuationIssue>,
    pub canonical_bytes: Option<Vec<u8>>,
    pub owned_ground_occurrence_count: usize,
    pub delivered_ground_occurrence_count: usize,
    pub owned_continuation_occurrence_count: usize,
    pub delivered_continuation_occurrence_count: usize,
}

/// Associate document-global Ground and typed marked-subject continuation without reparsing.
pub fn associate_semantic_document(
    document: &NormalizedDdlDocument,
) -> Result<SemanticDocumentResult, ClauseStreamError> {
    let instruction_association = associate_semantic_instructions(document)?;
    Ok(build_semantic_document(document, instruction_association))
}

/// Associate a document from one caller-owned accepted I-581 result without rerunning it.
pub fn associate_semantic_document_with_macro_binding(
    document: &NormalizedDdlDocument,
    macro_parameter_binding: MacroParameterBindingResult,
) -> SemanticDocumentResult {
    let instruction_association =
        associate_semantic_instructions_with_macro_binding(document, macro_parameter_binding);
    build_semantic_document(document, instruction_association)
}

fn build_semantic_document(
    document: &NormalizedDdlDocument,
    instruction_association: SemanticInstructionAssociationResult,
) -> SemanticDocumentResult {
    let mut grounds = Vec::new();

    for (clause_index, clause) in instruction_association
        .association
        .clause_stream
        .clauses
        .iter()
        .enumerate()
    {
        for (atom_index, atom) in clause.atoms.iter().enumerate() {
            let ClauseAtom::CoreRole(term) = atom else {
                continue;
            };
            if term.role != CoreRoleKind::Ground {
                continue;
            }
            if instruction_association
                .association
                .macro_parameter_owns_span(term.span)
            {
                continue;
            }
            let region_index = sentence_region_index(
                &instruction_association.association.clause_stream,
                term.span,
            );
            grounds.push(project_semantic_term(
                document,
                &term.asset_id,
                &term.category_key,
                &term.canonical_surface_ja,
                term.span,
                region_index,
                clause_index,
                atom_index,
            ));
        }
    }

    let owned_ground_occurrence_count = grounds.len();
    let (ground, issues) = match grounds.len() {
        0 => (None, Vec::new()),
        1 => (grounds.pop(), Vec::new()),
        _ => (
            None,
            vec![SemanticDocumentIssue {
                kind: SemanticDocumentIssueKind::ConflictingGrounds,
                occurrences: grounds,
            }],
        ),
    };
    let delivered_ground_occurrence_count = usize::from(ground.is_some())
        + issues
            .iter()
            .map(|issue| issue.occurrences.len())
            .sum::<usize>();
    assert_eq!(
        delivered_ground_occurrence_count, owned_ground_occurrence_count,
        "semantic document must deliver every Ground occurrence exactly once"
    );

    let (
        instructions,
        continuations,
        continuation_issues,
        owned_continuation_occurrence_count,
        instruction_index_map,
    ) = associate_continuations(document, &instruction_association);
    let coordinated_head_groups = instruction_association
        .ast
        .coordinated_head_groups
        .iter()
        .map(|group| crate::SemanticCoordinatedHeadGroup {
            member_instruction_indices: group
                .member_instruction_indices
                .iter()
                .map(|index| {
                    instruction_index_map[*index]
                        .expect("coordinated member is retained by document ownership")
                })
                .collect(),
            markers: group.markers.clone(),
        })
        .collect();
    let mut delivered_continuation_owners = continuations
        .iter()
        .map(|edge| {
            (
                edge.reintroduced_head.source().span.start_byte,
                edge.reintroduced_head.source().span.end_byte,
                edge.marker.span.start_byte,
                edge.marker.span.end_byte,
            )
        })
        .chain(continuation_issues.iter().map(|issue| {
            (
                issue.instruction.entity.head.source().span.start_byte,
                issue.instruction.entity.head.source().span.end_byte,
                issue.marker.span.start_byte,
                issue.marker.span.end_byte,
            )
        }))
        .collect::<Vec<_>>();
    delivered_continuation_owners.sort_unstable();
    delivered_continuation_owners.dedup();
    let delivered_continuation_occurrence_count = 2 * delivered_continuation_owners.len();
    assert_eq!(
        delivered_continuation_occurrence_count, owned_continuation_occurrence_count,
        "semantic document must deliver every continuation head and marker exactly once"
    );

    let consumed_upstream_spans = continuations
        .iter()
        .flat_map(|edge| &edge.consumed_upstream_spans)
        .chain(
            continuation_issues
                .iter()
                .flat_map(|issue| &issue.consumed_upstream_spans),
        )
        .copied()
        .collect::<Vec<_>>();
    let upstream_complete = instruction_association
        .association
        .issues
        .iter()
        .all(|issue| {
            issue.kind == SemanticAssociationIssueKind::AmbiguousEntityOwnership
                && issue.upstream_diagnostic.is_none()
                && !issue.occurrences.is_empty()
                && issue
                    .occurrences
                    .iter()
                    .all(|occurrence| consumed_upstream_spans.contains(&occurrence.source().span))
        })
        && instruction_association.issues.iter().all(|issue| {
            issue.kind == SemanticInstructionIssueKind::AmbiguousActionOwnership
                && !issue.occurrences.is_empty()
                && issue.occurrences.iter().all(|occurrence| {
                    consumed_upstream_spans.contains(&occurrence.term.provenance.source.span)
                })
        })
        && instruction_association.relation_issues.is_empty();
    let ast = SemanticDocumentAst {
        ground,
        instructions,
        coordinated_head_groups,
        group_predicates: instruction_association.ast.group_predicates.clone(),
        continuations,
        complete: (instruction_association.ast.complete || upstream_complete)
            && issues.is_empty()
            && continuation_issues.is_empty(),
    };
    let canonical_bytes = ast.complete.then(|| canonical_ast_bytes(&ast));

    SemanticDocumentResult {
        schema_id: SEMANTIC_DOCUMENT_SCHEMA_ID,
        instruction_association,
        ast,
        issues,
        continuation_issues,
        canonical_bytes,
        owned_ground_occurrence_count,
        delivered_ground_occurrence_count,
        owned_continuation_occurrence_count,
        delivered_continuation_occurrence_count,
    }
}

struct PendingContinuation {
    instruction: SemanticInstruction,
    marker: SourceOccurrence,
    predicate_span: SourceSpan,
    target_instruction_index: usize,
    target: SemanticContinuationTarget,
    consumed_upstream_spans: Vec<SourceSpan>,
    claims: Vec<SourceSpan>,
}

fn associate_continuations(
    document: &NormalizedDdlDocument,
    association: &SemanticInstructionAssociationResult,
) -> (
    Vec<SemanticInstruction>,
    Vec<SemanticContinuationEdge>,
    Vec<SemanticContinuationIssue>,
    usize,
    Vec<Option<usize>>,
) {
    let mut instructions = Vec::new();
    let mut continuations = Vec::new();
    let mut issues = Vec::new();
    let mut pending = Vec::new();
    let mut owned = 0;
    let mut instruction_index_map = vec![None; association.ast.instructions.len()];
    let coordinated_members = association
        .ast
        .coordinated_head_groups
        .iter()
        .flat_map(|group| group.member_instruction_indices.iter().copied())
        .collect::<BTreeSet<_>>();

    for (original_index, original_instruction) in association.ast.instructions.iter().enumerate() {
        if coordinated_members.contains(&original_index) {
            instruction_index_map[original_index] = Some(instructions.len());
            instructions.push(original_instruction.clone());
            continue;
        }
        let (instruction, consumed_upstream_spans) =
            continuation_predicate(association, original_instruction);
        let Some(marker) = continuation_marker(document, association, &instruction) else {
            instruction_index_map[original_index] = Some(instructions.len());
            instructions.push(original_instruction.clone());
            continue;
        };
        if !has_continuation_predicate(&instruction) {
            instruction_index_map[original_index] = Some(instructions.len());
            instructions.push(original_instruction.clone());
            continue;
        }

        owned += 2;
        let clause = &association.association.clause_stream.clauses[marker.clause_index];
        let predicate_span = SourceSpan {
            start_byte: marker.span.end_byte,
            end_byte: clause.span.end_byte,
        };
        let targets = instructions
            .iter()
            .enumerate()
            .filter(|(_, candidate)| {
                same_head_identity(&candidate.entity.head, &instruction.entity.head)
            })
            .map(|(index, candidate)| (index, continuation_target(&candidate.entity.head)))
            .collect::<Vec<_>>();

        let issue_kind = if instruction.entity.quantity.is_some()
            || instruction.position.is_some()
            || instruction.relation.is_some()
        {
            Some(SemanticContinuationIssueKind::UnsupportedPredicate)
        } else if targets.is_empty() {
            Some(SemanticContinuationIssueKind::MissingTarget)
        } else if targets.len() != 1 {
            Some(SemanticContinuationIssueKind::AmbiguousTarget)
        } else if continuation_boundary_is_blocked(
            association,
            instructions[targets[0].0]
                .entity
                .head
                .source()
                .span
                .end_byte,
            marker.span.start_byte,
            &consumed_upstream_spans,
        ) {
            Some(SemanticContinuationIssueKind::BlockedBoundary)
        } else {
            None
        };

        if let Some(kind) = issue_kind {
            let causal_provenance = if kind == SemanticContinuationIssueKind::BlockedBoundary {
                let target_index = targets[0].0;
                causal_provenance(diagnostic_causes_in_source_range(
                    &association.association.clause_stream,
                    instructions[target_index]
                        .entity
                        .head
                        .source()
                        .span
                        .end_byte,
                    marker.span.start_byte,
                    &consumed_upstream_spans,
                    SemanticUpstreamCausalRelation::ContinuationBoundary,
                ))
            } else {
                SemanticIssueCausalProvenance::Unattributed
            };
            issues.push(SemanticContinuationIssue {
                kind,
                instruction,
                marker,
                predicate_span,
                candidate_targets: targets.into_iter().map(|(_, target)| target).collect(),
                consumed_upstream_spans,
                causal_provenance,
            });
            continue;
        }

        let (target_index, target) = targets.into_iter().next().expect("exact one target");
        let claims = consumed_upstream_spans.clone();
        pending.push(PendingContinuation {
            instruction,
            marker,
            predicate_span,
            target_instruction_index: target_index,
            target,
            consumed_upstream_spans,
            claims,
        });
    }

    let mut claimants = BTreeMap::<(usize, usize), Vec<usize>>::new();
    for (pending_index, candidate) in pending.iter().enumerate() {
        for claim in &candidate.claims {
            let claimants = claimants
                .entry((claim.start_byte, claim.end_byte))
                .or_default();
            if !claimants.contains(&pending_index) {
                claimants.push(pending_index);
            }
        }
    }
    let pending_targets = pending
        .iter()
        .map(|candidate| candidate.target.clone())
        .collect::<Vec<_>>();

    for candidate in pending {
        let duplicate_claims = candidate
            .claims
            .iter()
            .filter(|claim| claimants[&(claim.start_byte, claim.end_byte)].len() > 1)
            .copied()
            .collect::<Vec<_>>();
        if !duplicate_claims.is_empty() {
            let mut candidate_targets = Vec::new();
            for claim in &duplicate_claims {
                for pending_index in &claimants[&(claim.start_byte, claim.end_byte)] {
                    let target = pending_targets[*pending_index].clone();
                    if !candidate_targets.contains(&target) {
                        candidate_targets.push(target);
                    }
                }
            }
            issues.push(SemanticContinuationIssue {
                kind: SemanticContinuationIssueKind::AmbiguousTarget,
                instruction: candidate.instruction,
                marker: candidate.marker,
                predicate_span: duplicate_claims[0],
                candidate_targets,
                consumed_upstream_spans: duplicate_claims,
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
            });
            continue;
        }

        if !predicate_is_compatible(
            &instructions[candidate.target_instruction_index],
            &candidate.instruction,
        ) {
            issues.push(SemanticContinuationIssue {
                kind: SemanticContinuationIssueKind::ConflictingPredicate,
                instruction: candidate.instruction,
                marker: candidate.marker,
                predicate_span: candidate.predicate_span,
                candidate_targets: vec![candidate.target],
                consumed_upstream_spans: candidate.consumed_upstream_spans,
                causal_provenance: SemanticIssueCausalProvenance::Unattributed,
            });
            continue;
        }

        merge_predicate(
            &mut instructions[candidate.target_instruction_index],
            &candidate.instruction,
        );
        continuations.push(SemanticContinuationEdge {
            target: candidate.target,
            target_instruction_index: candidate.target_instruction_index,
            reintroduced_head: candidate.instruction.entity.head,
            marker: candidate.marker,
            predicate_span: candidate.predicate_span,
            consumed_upstream_spans: candidate.consumed_upstream_spans,
        });
    }

    (
        instructions,
        continuations,
        issues,
        owned,
        instruction_index_map,
    )
}

fn continuation_boundary_is_blocked(
    result: &SemanticInstructionAssociationResult,
    start_byte: usize,
    end_byte: usize,
    consumed: &[SourceSpan],
) -> bool {
    let in_path = |span: SourceSpan| {
        start_byte <= span.start_byte && span.end_byte <= end_byte && !consumed.contains(&span)
    };
    result
        .association
        .clause_stream
        .clauses
        .iter()
        .flat_map(|clause| &clause.atoms)
        .any(|atom| matches!(atom, ClauseAtom::UnresolvedDiagnostic(_)) && in_path(atom.span()))
        || result.association.issues.iter().any(|issue| {
            issue
                .upstream_diagnostic
                .as_ref()
                .is_some_and(|diagnostic| in_path(diagnostic.span))
                || issue
                    .occurrences
                    .iter()
                    .any(|occurrence| in_path(occurrence.source().span))
        })
        || result.issues.iter().any(|issue| {
            issue
                .occurrences
                .iter()
                .any(|occurrence| in_path(occurrence.term.provenance.source.span))
        })
        || result.relation_issues.iter().any(|issue| {
            issue
                .occurrences
                .iter()
                .any(|occurrence| in_path(occurrence.provenance.span))
        })
}

fn continuation_predicate(
    result: &SemanticInstructionAssociationResult,
    instruction: &SemanticInstruction,
) -> (SemanticInstruction, Vec<SourceSpan>) {
    let mut enriched = instruction.clone();
    let region_index = instruction.entity.head.source().region_index;
    let mut consumed = Vec::new();
    for issue in result.association.issues.iter().filter(|issue| {
        issue.kind == SemanticAssociationIssueKind::AmbiguousEntityOwnership
            && issue.region_index == region_index
            && issue.upstream_diagnostic.is_none()
    }) {
        for occurrence in &issue.occurrences {
            if apply_continuation_occurrence(&mut enriched, occurrence) {
                consumed.push(occurrence.source().span);
            }
        }
    }
    for issue in result.issues.iter().filter(|issue| {
        issue.kind == SemanticInstructionIssueKind::AmbiguousActionOwnership
            && issue.region_index == region_index
            && issue.occurrences.len() == 1
    }) {
        let action = &issue.occurrences[0].term;
        if set_if_empty(&mut enriched.action, action) {
            consumed.push(action.provenance.source.span);
        }
    }
    consumed.sort_by_key(|span| (span.start_byte, span.end_byte));
    consumed.dedup();
    (enriched, consumed)
}

fn apply_continuation_occurrence(
    instruction: &mut SemanticInstruction,
    occurrence: &OwnedSemanticOccurrence,
) -> bool {
    match occurrence {
        OwnedSemanticOccurrence::Color(term) => set_if_empty(&mut instruction.entity.color, term),
        OwnedSemanticOccurrence::Thinness(value) => {
            set_if_empty(&mut instruction.entity.thinness, value)
        }
        OwnedSemanticOccurrence::RelativeScale(value) => {
            set_if_empty(&mut instruction.entity.relative_scale, value)
        }
        OwnedSemanticOccurrence::Touch(term) => set_if_empty(&mut instruction.entity.touch, term),
        OwnedSemanticOccurrence::Continuity(term) => {
            set_if_empty(&mut instruction.entity.continuity, term)
        }
        OwnedSemanticOccurrence::Angle(term) => set_if_empty(&mut instruction.entity.angle, term),
        OwnedSemanticOccurrence::Surface(term) => match term.identity.id.as_str() {
            "none" | "solid" | "wash" | "grain" | "stipple" | "hatch" | "crosshatch" | "bleed"
            | "aquatint" => set_if_empty(&mut instruction.entity.surface.quality, term),
            "dense" | "faint" => set_if_empty(&mut instruction.entity.surface.intensity, term),
            _ => false,
        },
        OwnedSemanticOccurrence::Fluctuation(term) => match term.identity.id.as_str() {
            "fine" | "large" => set_if_empty(&mut instruction.entity.fluctuation.amplitude, term),
            "quickly" | "slowly" => {
                set_if_empty(&mut instruction.entity.fluctuation.frequency, term)
            }
            "swaying" | "undulating" | "trembling" | "blurring" => {
                set_if_empty(&mut instruction.entity.fluctuation.quality, term)
            }
            _ => false,
        },
        OwnedSemanticOccurrence::Proportion(term) => match term.identity.id.as_str() {
            "tall" | "wide" => set_if_empty(&mut instruction.entity.proportion.aspect, term),
            "full_width" | "half_width" => {
                set_if_empty(&mut instruction.entity.proportion.width_extent, term)
            }
            "semicircle" | "waxing" | "waning" | "crescent" => {
                set_if_empty(&mut instruction.entity.proportion.arc_form, term)
            }
            _ => false,
        },
        OwnedSemanticOccurrence::Head(_)
        | OwnedSemanticOccurrence::MacroDiagnostic(_)
        | OwnedSemanticOccurrence::Quantity(_) => false,
    }
}

fn set_if_empty<T: Clone>(target: &mut Option<T>, value: &T) -> bool {
    if target.is_some() {
        return false;
    }
    *target = Some(value.clone());
    true
}

pub(crate) fn exclusive_continuation_issue_claim_spans(
    issue: &SemanticContinuationIssue,
) -> Option<&[SourceSpan]> {
    if issue.kind != SemanticContinuationIssueKind::AmbiguousTarget
        || issue.consumed_upstream_spans.first() != Some(&issue.predicate_span)
    {
        return None;
    }
    Some(&issue.consumed_upstream_spans)
}

fn continuation_marker(
    document: &NormalizedDdlDocument,
    result: &SemanticInstructionAssociationResult,
    instruction: &SemanticInstruction,
) -> Option<SourceOccurrence> {
    let head = instruction.entity.head.source();
    let clause = result
        .association
        .clause_stream
        .clauses
        .get(head.clause_index)?;
    let marker_span = match document.language() {
        ResolvedInstructionLanguage::Ja => result
            .association
            .clause_topology
            .attachment_markers
            .iter()
            .filter(|marker| {
                marker.clause_index == head.clause_index
                    && matches!(
                        marker.marker,
                        AttachmentMarkerKind::Japanese(
                            JapaneseAttachmentMarkerKind::Wa | JapaneseAttachmentMarkerKind::Ga
                        )
                    )
                    && marker.left_atom_spans.last() == Some(&head.span)
            })
            .map(|marker| marker.span)
            .next(),
        ResolvedInstructionLanguage::En => result
            .association
            .clause_topology
            .determiner_starts
            .iter()
            .copied()
            .filter(|start| {
                clause.span.start_byte <= *start
                    && *start < head.span.start_byte
                    && !clause.atoms.iter().any(|atom| {
                        matches!(atom, ClauseAtom::CoreRole(term) if term.role == CoreRoleKind::Primitive)
                            && *start < atom.span().start_byte
                            && atom.span().end_byte <= head.span.start_byte
                            && atom.span() != head.span
                    })
            })
            .max()
            .and_then(|start| clause.atoms.iter().find(|atom| atom.span().start_byte == start))
            .map(ClauseAtom::span),
    }?;
    let atom_index = clause
        .atoms
        .iter()
        .position(|atom| atom.span() == marker_span)?;
    Some(SourceOccurrence {
        span: marker_span,
        surface: document.source()[marker_span.start_byte..marker_span.end_byte].to_owned(),
        language: document.language(),
        region_index: sentence_region_index(&result.association.clause_stream, marker_span),
        clause_index: head.clause_index,
        atom_index,
    })
}

fn has_continuation_predicate(instruction: &SemanticInstruction) -> bool {
    let entity = &instruction.entity;
    entity.color.is_some()
        || entity.thinness.is_some()
        || entity.relative_scale.is_some()
        || entity.touch.is_some()
        || entity.continuity.is_some()
        || entity.angle.is_some()
        || entity.surface.quality.is_some()
        || entity.surface.intensity.is_some()
        || entity.fluctuation.amplitude.is_some()
        || entity.fluctuation.frequency.is_some()
        || entity.fluctuation.quality.is_some()
        || entity.proportion.aspect.is_some()
        || entity.proportion.width_extent.is_some()
        || entity.proportion.arc_form.is_some()
        || instruction.action.is_some()
        || instruction.position.is_some()
        || instruction.relation.is_some()
}

fn same_head_identity(left: &SemanticHead, right: &SemanticHead) -> bool {
    continuation_target(left) == continuation_target(right)
}

fn continuation_target(head: &SemanticHead) -> SemanticContinuationTarget {
    match head {
        SemanticHead::Primitive(term) => {
            SemanticContinuationTarget::Primitive(term.identity.clone())
        }
        SemanticHead::MacroInvocation(head) => SemanticContinuationTarget::MacroInvocation {
            qualified_name: head.qualified_name.clone(),
            definition_version: head.definition_version.clone(),
            definition_digest: head.definition_digest.clone(),
        },
    }
}

fn predicate_is_compatible(
    target: &SemanticInstruction,
    continuation: &SemanticInstruction,
) -> bool {
    let left = &target.entity;
    let right = &continuation.entity;
    option_is_mergeable(&left.color, &right.color)
        && option_is_mergeable(&left.thinness, &right.thinness)
        && option_is_mergeable(&left.relative_scale, &right.relative_scale)
        && option_is_mergeable(&left.touch, &right.touch)
        && option_is_mergeable(&left.continuity, &right.continuity)
        && option_is_mergeable(&left.angle, &right.angle)
        && option_is_mergeable(&left.surface.quality, &right.surface.quality)
        && option_is_mergeable(&left.surface.intensity, &right.surface.intensity)
        && option_is_mergeable(&left.fluctuation.amplitude, &right.fluctuation.amplitude)
        && option_is_mergeable(&left.fluctuation.frequency, &right.fluctuation.frequency)
        && option_is_mergeable(&left.fluctuation.quality, &right.fluctuation.quality)
        && option_is_mergeable(&left.proportion.aspect, &right.proportion.aspect)
        && option_is_mergeable(
            &left.proportion.width_extent,
            &right.proportion.width_extent,
        )
        && option_is_mergeable(&left.proportion.arc_form, &right.proportion.arc_form)
        && option_is_mergeable(&target.action, &continuation.action)
}

fn option_is_mergeable<T>(left: &Option<T>, right: &Option<T>) -> bool {
    left.is_none() || right.is_none()
}

fn merge_predicate(target: &mut SemanticInstruction, continuation: &SemanticInstruction) {
    merge_option(&mut target.entity.color, &continuation.entity.color);
    merge_option(&mut target.entity.thinness, &continuation.entity.thinness);
    merge_option(
        &mut target.entity.relative_scale,
        &continuation.entity.relative_scale,
    );
    merge_option(&mut target.entity.touch, &continuation.entity.touch);
    merge_option(
        &mut target.entity.continuity,
        &continuation.entity.continuity,
    );
    merge_option(&mut target.entity.angle, &continuation.entity.angle);
    merge_option(
        &mut target.entity.surface.quality,
        &continuation.entity.surface.quality,
    );
    merge_option(
        &mut target.entity.surface.intensity,
        &continuation.entity.surface.intensity,
    );
    merge_option(
        &mut target.entity.fluctuation.amplitude,
        &continuation.entity.fluctuation.amplitude,
    );
    merge_option(
        &mut target.entity.fluctuation.frequency,
        &continuation.entity.fluctuation.frequency,
    );
    merge_option(
        &mut target.entity.fluctuation.quality,
        &continuation.entity.fluctuation.quality,
    );
    merge_option(
        &mut target.entity.proportion.aspect,
        &continuation.entity.proportion.aspect,
    );
    merge_option(
        &mut target.entity.proportion.width_extent,
        &continuation.entity.proportion.width_extent,
    );
    merge_option(
        &mut target.entity.proportion.arc_form,
        &continuation.entity.proportion.arc_form,
    );
    merge_option(&mut target.action, &continuation.action);
}

fn merge_option<T: Clone>(target: &mut Option<T>, continuation: &Option<T>) {
    if target.is_none() {
        *target = continuation.clone();
    }
}

fn canonical_ast_bytes(ast: &SemanticDocumentAst) -> Vec<u8> {
    let mut root = BTreeMap::new();
    root.insert(
        "coordinated_head_groups".to_owned(),
        Value::Array(
            ast.coordinated_head_groups
                .iter()
                .map(semantic_coordinated_head_group_value)
                .collect(),
        ),
    );
    root.insert(
        "continuations".to_owned(),
        Value::Array(
            ast.continuations
                .iter()
                .map(|edge| {
                    let mut value = BTreeMap::new();
                    value.insert(
                        "kind".to_owned(),
                        Value::String("subject_predicate".to_owned()),
                    );
                    value.insert("target".to_owned(), continuation_target_value(&edge.target));
                    Value::Object(value.into_iter().collect())
                })
                .collect(),
        ),
    );
    root.insert(
        "ground".to_owned(),
        ast.ground
            .as_ref()
            .map(|ground| semantic_identity_value(&ground.identity))
            .unwrap_or(Value::Null),
    );
    root.insert(
        "group_predicates".to_owned(),
        Value::Array(
            ast.group_predicates
                .iter()
                .map(semantic_group_predicate_value)
                .collect(),
        ),
    );
    root.insert(
        "instructions".to_owned(),
        Value::Array(
            ast.instructions
                .iter()
                .map(semantic_instruction_value)
                .collect(),
        ),
    );
    root.insert(
        "schema".to_owned(),
        Value::String(SEMANTIC_DOCUMENT_SCHEMA_ID.to_owned()),
    );
    serde_json::to_vec(&root).expect("closed semantic document AST serializes")
}

fn continuation_target_value(target: &SemanticContinuationTarget) -> Value {
    match target {
        SemanticContinuationTarget::Primitive(identity) => semantic_identity_value(identity),
        SemanticContinuationTarget::MacroInvocation {
            qualified_name,
            definition_version,
            definition_digest,
        } => {
            let mut value = BTreeMap::new();
            value.insert(
                "definition_digest".to_owned(),
                Value::String(definition_digest.clone()),
            );
            value.insert(
                "definition_version".to_owned(),
                Value::String(definition_version.clone()),
            );
            value.insert(
                "kind".to_owned(),
                Value::String("macro_invocation".to_owned()),
            );
            value.insert(
                "qualified_name".to_owned(),
                Value::String(qualified_name.clone()),
            );
            Value::Object(value.into_iter().collect())
        }
    }
}
