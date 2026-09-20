//! Base-lock constrained visible-source patching and full candidate recompilation.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::{
    ClauseAtom, CompilerLockState, CoreRoleKind, MacroDefinition, MacroExpansionLimits,
    NormalizedDdlDocument, RemainingRoleKind, SemanticDeliveryIdentity, SemanticDeliveryKind,
    SemanticDeliveryOwner, SemanticFillTarget, SemanticInstruction, SemanticRelation, SourceSpan,
    TypedDdlCompilation, compile_typed_ddl,
    semantic_association::{
        semantic_entity_value, semantic_explicit_geometry_value, semantic_identity_value,
        semantic_numeric_position_value, semantic_sequence_value,
    },
};

/// Stable identity for constrained visible DDL patch requests.
pub const VISIBLE_DDL_PATCH_SCHEMA_ID: &str = "inku.visible-ddl-patch.v1";

/// One exact typed-hole edit. `String` makes replacement UTF-8 validity structural.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VisibleDdlPatchEdit {
    pub hole_id: String,
    pub allowed_span: SourceSpan,
    pub expected_range_digest: String,
    pub replacement: String,
}

/// A source-ordered patch locked to both source bytes and the full compiler lock.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VisibleDdlPatch {
    pub schema_id: &'static str,
    pub base_source_digest: String,
    pub base_compiler_lock_digest: String,
    pub edits: Vec<VisibleDdlPatchEdit>,
}

impl VisibleDdlPatch {
    pub fn new(
        base_source_digest: impl Into<String>,
        base_compiler_lock_digest: impl Into<String>,
        edits: Vec<VisibleDdlPatchEdit>,
    ) -> Self {
        Self {
            schema_id: VISIBLE_DDL_PATCH_SCHEMA_ID,
            base_source_digest: base_source_digest.into(),
            base_compiler_lock_digest: base_compiler_lock_digest.into(),
            edits,
        }
    }
}

/// Stable fail-closed patch outcomes. No variant carries a partially merged document.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum VisiblePatchDiagnostic {
    InvalidSchema,
    EmptyPatch,
    BaseIntegrityFailure,
    PatchTargetUnavailable,
    StaleSource,
    StaleCompilerLock,
    UnknownTarget,
    ExplicitTarget,
    ConflictTarget,
    BlockingDiagnosticTarget,
    DuplicateHole,
    UnorderedEdits,
    OverlappingEdits,
    InvalidRange,
    SpanMismatch,
    RangeDigestMismatch,
    EmptyReplacement,
    SidecarLockChanged,
    OutsideBytesChanged,
    OutsideExplicitChanged,
    EstablishedFactChanged,
    OwnerAssociationChanged,
    TargetUnresolved,
    NewDiagnostic,
    CandidateIntegrityFailure,
}

impl VisiblePatchDiagnostic {
    pub const fn kind(self) -> &'static str {
        match self {
            Self::InvalidSchema => "invalid_schema",
            Self::EmptyPatch => "empty_patch",
            Self::BaseIntegrityFailure => "base_integrity_failure",
            Self::PatchTargetUnavailable => "patch_target_unavailable",
            Self::StaleSource => "stale_source",
            Self::StaleCompilerLock => "stale_compiler_lock",
            Self::UnknownTarget => "unknown_target",
            Self::ExplicitTarget => "explicit_target",
            Self::ConflictTarget => "conflict_target",
            Self::BlockingDiagnosticTarget => "blocking_diagnostic_target",
            Self::DuplicateHole => "duplicate_hole",
            Self::UnorderedEdits => "unordered_edits",
            Self::OverlappingEdits => "overlapping_edits",
            Self::InvalidRange => "invalid_range",
            Self::SpanMismatch => "span_mismatch",
            Self::RangeDigestMismatch => "range_digest_mismatch",
            Self::EmptyReplacement => "empty_replacement",
            Self::SidecarLockChanged => "sidecar_lock_changed",
            Self::OutsideBytesChanged => "outside_bytes_changed",
            Self::OutsideExplicitChanged => "outside_explicit_changed",
            Self::EstablishedFactChanged => "established_fact_changed",
            Self::OwnerAssociationChanged => "owner_association_changed",
            Self::TargetUnresolved => "target_unresolved",
            Self::NewDiagnostic => "new_diagnostic",
            Self::CandidateIntegrityFailure => "candidate_integrity_failure",
        }
    }
}

/// In-memory author-review candidate. This type has no persistence or approval operation.
#[derive(Clone, Debug, PartialEq)]
pub struct ValidatedVisibleDdlCandidate {
    pub document: NormalizedDdlDocument,
    pub compilation: TypedDdlCompilation,
    pub resolved_hole_ids: Vec<String>,
}

/// One fail-closed patch outcome with the exact target hole when attribution is certain.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VisiblePatchFailure {
    pub diagnostic: VisiblePatchDiagnostic,
    pub hole_id: Option<String>,
}

impl VisiblePatchFailure {
    fn global(diagnostic: VisiblePatchDiagnostic) -> Self {
        Self {
            diagnostic,
            hole_id: None,
        }
    }

    fn for_hole(diagnostic: VisiblePatchDiagnostic, hole_id: &str) -> Self {
        Self {
            diagnostic,
            hole_id: Some(hole_id.to_owned()),
        }
    }
}

/// Whether the compilation has known holes and no global failure that forbids a bounded patch.
pub fn visible_ddl_patch_available(compilation: &TypedDdlCompilation) -> bool {
    let Some(lock) = compilation.compiler_lock.as_ref() else {
        return false;
    };
    !compilation.holes.is_empty()
        && matches!(
            lock.state,
            CompilerLockState::IncompleteKnownHole
                | CompilerLockState::BlockedConflict
                | CompilerLockState::BlockedDiagnostic
        )
        && compilation
            .conflicts
            .iter()
            .all(|conflict| conflict.span.is_some())
        && compilation
            .blocking_diagnostics
            .iter()
            .all(|diagnostic| !diagnostic.stops_all_execution())
}

/// Validate, merge, fully reparse, and fully recompile one constrained visible-source patch.
pub fn validate_visible_ddl_patch(
    base: &TypedDdlCompilation,
    patch: &VisibleDdlPatch,
    definitions: &[MacroDefinition],
    composition_seed: Option<u64>,
    limits: MacroExpansionLimits,
) -> Result<ValidatedVisibleDdlCandidate, VisiblePatchDiagnostic> {
    validate_visible_ddl_patch_detailed(base, patch, definitions, composition_seed, limits)
        .map_err(|failure| failure.diagnostic)
}

/// Validate one constrained patch and retain exact hole attribution for local failures.
pub fn validate_visible_ddl_patch_detailed(
    base: &TypedDdlCompilation,
    patch: &VisibleDdlPatch,
    definitions: &[MacroDefinition],
    composition_seed: Option<u64>,
    limits: MacroExpansionLimits,
) -> Result<ValidatedVisibleDdlCandidate, VisiblePatchFailure> {
    if patch.schema_id != VISIBLE_DDL_PATCH_SCHEMA_ID {
        return Err(VisiblePatchFailure::global(
            VisiblePatchDiagnostic::InvalidSchema,
        ));
    }
    if patch.edits.is_empty() {
        return Err(VisiblePatchFailure::global(
            VisiblePatchDiagnostic::EmptyPatch,
        ));
    }
    let Some(base_lock) = &base.compiler_lock else {
        return Err(VisiblePatchFailure::global(
            VisiblePatchDiagnostic::BaseIntegrityFailure,
        ));
    };
    let source = base.document.source();
    if patch.base_source_digest != sha256_hex(source.as_bytes()) {
        return Err(VisiblePatchFailure::global(
            VisiblePatchDiagnostic::StaleSource,
        ));
    }
    if patch.base_compiler_lock_digest != base_lock.full_digest {
        return Err(VisiblePatchFailure::global(
            VisiblePatchDiagnostic::StaleCompilerLock,
        ));
    }
    if !visible_ddl_patch_available(base) {
        if let Some(edit) = patch.edits.iter().find(|edit| {
            base.conflicts
                .iter()
                .any(|conflict| conflict.id == edit.hole_id)
        }) {
            return Err(VisiblePatchFailure::for_hole(
                VisiblePatchDiagnostic::ConflictTarget,
                &edit.hole_id,
            ));
        }
        if let Some(edit) = patch.edits.iter().find(|edit| {
            base.blocking_diagnostics
                .iter()
                .any(|diagnostic| diagnostic.id == edit.hole_id)
        }) {
            return Err(VisiblePatchFailure::for_hole(
                VisiblePatchDiagnostic::BlockingDiagnosticTarget,
                &edit.hole_id,
            ));
        }
        return Err(VisiblePatchFailure::global(
            VisiblePatchDiagnostic::PatchTargetUnavailable,
        ));
    }

    let mut previous: Option<&VisibleDdlPatchEdit> = None;
    let mut hole_ids = Vec::new();
    for edit in &patch.edits {
        if edit.replacement.is_empty() {
            return Err(VisiblePatchFailure::for_hole(
                VisiblePatchDiagnostic::EmptyReplacement,
                &edit.hole_id,
            ));
        }
        if !hole_ids.insert_sorted(edit.hole_id.clone()) {
            return Err(VisiblePatchFailure::for_hole(
                VisiblePatchDiagnostic::DuplicateHole,
                &edit.hole_id,
            ));
        }
        if let Some(previous) = previous {
            if edit.allowed_span.start_byte < previous.allowed_span.start_byte {
                return Err(VisiblePatchFailure::global(
                    VisiblePatchDiagnostic::UnorderedEdits,
                ));
            }
            if edit.allowed_span.start_byte < previous.allowed_span.end_byte {
                return Err(VisiblePatchFailure::global(
                    VisiblePatchDiagnostic::OverlappingEdits,
                ));
            }
        }
        previous = Some(edit);

        let span = edit.allowed_span;
        if span.start_byte >= span.end_byte
            || span.end_byte > source.len()
            || !source.is_char_boundary(span.start_byte)
            || !source.is_char_boundary(span.end_byte)
        {
            return Err(VisiblePatchFailure::for_hole(
                VisiblePatchDiagnostic::InvalidRange,
                &edit.hole_id,
            ));
        }

        let Some(hole) = base.holes.iter().find(|hole| hole.id == edit.hole_id) else {
            if base.conflicts.iter().any(|item| item.id == edit.hole_id) {
                return Err(VisiblePatchFailure::for_hole(
                    VisiblePatchDiagnostic::ConflictTarget,
                    &edit.hole_id,
                ));
            }
            if base
                .blocking_diagnostics
                .iter()
                .any(|item| item.id == edit.hole_id)
            {
                return Err(VisiblePatchFailure::for_hole(
                    VisiblePatchDiagnostic::BlockingDiagnosticTarget,
                    &edit.hole_id,
                ));
            }
            if base
                .deliveries
                .iter()
                .any(|item| item.id == edit.hole_id && item.kind == SemanticDeliveryKind::Explicit)
            {
                return Err(VisiblePatchFailure::for_hole(
                    VisiblePatchDiagnostic::ExplicitTarget,
                    &edit.hole_id,
                ));
            }
            return Err(VisiblePatchFailure::for_hole(
                VisiblePatchDiagnostic::UnknownTarget,
                &edit.hole_id,
            ));
        };
        if hole.allowed_span != edit.allowed_span {
            return Err(VisiblePatchFailure::for_hole(
                VisiblePatchDiagnostic::SpanMismatch,
                &edit.hole_id,
            ));
        }
        let actual_range_digest = sha256_hex(source[span.start_byte..span.end_byte].as_bytes());
        if edit.expected_range_digest != hole.expected_range_digest
            || edit.expected_range_digest != actual_range_digest
        {
            return Err(VisiblePatchFailure::for_hole(
                VisiblePatchDiagnostic::RangeDigestMismatch,
                &edit.hole_id,
            ));
        }
    }

    let (candidate_source, candidate_ranges) = merge(source, &patch.edits);
    if !outside_bytes_preserved(source, &candidate_source, &patch.edits, &candidate_ranges) {
        return Err(VisiblePatchFailure::global(
            VisiblePatchDiagnostic::OutsideBytesChanged,
        ));
    }
    let candidate_document = NormalizedDdlDocument::new(
        candidate_source,
        base.document.language(),
        base.document.macro_locks().to_vec(),
    )
    .map_err(|_| VisiblePatchFailure::global(VisiblePatchDiagnostic::SidecarLockChanged))?;
    if candidate_document.macro_locks() != base.document.macro_locks() {
        return Err(VisiblePatchFailure::global(
            VisiblePatchDiagnostic::SidecarLockChanged,
        ));
    }

    let candidate = compile_typed_ddl(
        candidate_document.clone(),
        definitions,
        composition_seed,
        limits,
    );
    if candidate.compiler_lock.is_none() {
        return Err(VisiblePatchFailure::global(
            VisiblePatchDiagnostic::CandidateIntegrityFailure,
        ));
    }

    for (edit, range) in patch.edits.iter().zip(&candidate_ranges) {
        if candidate
            .holes
            .iter()
            .any(|item| overlaps(item.span, *range))
            || candidate
                .conflicts
                .iter()
                .any(|item| item.span.is_some_and(|span| overlaps(span, *range)))
            || candidate
                .blocking_diagnostics
                .iter()
                .any(|item| item.span.is_some_and(|span| overlaps(span, *range)))
        {
            return Err(VisiblePatchFailure::for_hole(
                VisiblePatchDiagnostic::TargetUnresolved,
                &edit.hole_id,
            ));
        }
        let hole = base
            .holes
            .iter()
            .find(|hole| hole.id == edit.hole_id)
            .expect("validated edit retains its exact typed hole");
        if let Some(diagnostic) = target_resolution_failure(hole, base, &candidate, *range) {
            return Err(VisiblePatchFailure::for_hole(diagnostic, &edit.hole_id));
        }
    }

    let base_outside = outside_explicit(
        base,
        &patch
            .edits
            .iter()
            .map(|item| item.allowed_span)
            .collect::<Vec<_>>(),
    );
    let candidate_outside = outside_explicit(&candidate, &candidate_ranges);
    if base_outside != candidate_outside {
        return Err(VisiblePatchFailure::global(
            VisiblePatchDiagnostic::OutsideExplicitChanged,
        ));
    }
    let base_holes = outside_holes(
        base,
        &patch
            .edits
            .iter()
            .map(|item| item.allowed_span)
            .collect::<Vec<_>>(),
    );
    let candidate_holes = outside_holes(&candidate, &candidate_ranges);
    let base_conflicts = outside_conflicts(
        base,
        &patch
            .edits
            .iter()
            .map(|item| item.allowed_span)
            .collect::<Vec<_>>(),
    );
    let candidate_conflicts = outside_conflicts(&candidate, &candidate_ranges);
    let base_blocking = outside_blocking_diagnostics(
        base,
        &patch
            .edits
            .iter()
            .map(|item| item.allowed_span)
            .collect::<Vec<_>>(),
    );
    let candidate_blocking = outside_blocking_diagnostics(&candidate, &candidate_ranges);
    if base_holes != candidate_holes
        || base_conflicts != candidate_conflicts
        || base_blocking != candidate_blocking
    {
        return Err(VisiblePatchFailure::global(
            VisiblePatchDiagnostic::NewDiagnostic,
        ));
    }

    Ok(ValidatedVisibleDdlCandidate {
        document: candidate_document,
        compilation: candidate,
        resolved_hole_ids: patch
            .edits
            .iter()
            .map(|edit| edit.hole_id.clone())
            .collect(),
    })
}

fn target_resolution_failure(
    hole: &crate::TypedHole,
    base: &TypedDdlCompilation,
    candidate: &TypedDdlCompilation,
    range: SourceSpan,
) -> Option<VisiblePatchDiagnostic> {
    if hole.kind == "unresolved_clause" {
        // A support-only proposal cannot introduce drawable owners or alter the
        // source-ordered reference namespace. This also permits independent
        // support repair while an unrelated drawable clause remains unresolved.
        if let Some(owner) = base.semantic_document.as_ref().and_then(|semantic| {
            semantic
                .instruction_association
                .association
                .clause_stream
                .clauses
                .iter()
                .find(|clause| clause.span == hole.span)
                .and_then(crate::compiler_lock::isolated_support_clause_owner)
        }) {
            let explicit = candidate
                .deliveries
                .iter()
                .filter(|item| {
                    item.kind == SemanticDeliveryKind::Explicit
                        && item.span.is_some_and(|span| overlaps(span, range))
                })
                .collect::<Vec<_>>();
            if !explicit.iter().any(|item| item.identity.owner == owner)
                || explicit.iter().any(|item| item.identity.owner != owner)
                || candidate_has_drawable_instruction(candidate, range)
            {
                return Some(VisiblePatchDiagnostic::OwnerAssociationChanged);
            }
        }
        let required = typed_fact_counts(base, hole.span);
        let delivered = typed_fact_counts(candidate, range);
        let reference_facts = reclassified_reference_facts(base, hole.span, candidate, range);
        if required.iter().any(|(fact, count)| {
            delivered.get(fact).copied().unwrap_or_default()
                + reference_facts.get(fact).copied().unwrap_or_default()
                < *count
        }) {
            return Some(VisiblePatchDiagnostic::EstablishedFactChanged);
        }
        let required_associations = resolved_association_counts(base, hole.span);
        let delivered_associations = resolved_association_counts(candidate, range);
        if required_associations.iter().any(|(association, count)| {
            delivered_associations
                .get(association)
                .copied()
                .unwrap_or_default()
                < *count
        }) {
            return Some(VisiblePatchDiagnostic::OwnerAssociationChanged);
        }
        let owners = candidate
            .deliveries
            .iter()
            .filter(|item| item.kind == SemanticDeliveryKind::Explicit)
            .filter(|item| item.span.is_some_and(|span| overlaps(span, range)))
            .map(|item| item.identity.owner)
            .collect::<BTreeSet<_>>();
        if source_has_drawing_fact(base, hole.span) {
            return (!candidate_has_drawable_instruction(candidate, range))
                .then_some(VisiblePatchDiagnostic::TargetUnresolved);
        }
        return (!(owners.contains(&SemanticDeliveryOwner::Background)
            || owners.contains(&SemanticDeliveryOwner::Ground)
            || candidate_has_drawable_instruction(candidate, range)))
        .then_some(VisiblePatchDiagnostic::TargetUnresolved);
    }
    (!candidate.deliveries.iter().any(|item| {
        item.kind == SemanticDeliveryKind::Explicit
            && item.identity.owner == hole.expected_owner
            && item.span.is_some_and(|span| overlaps(span, range))
    }))
    .then_some(VisiblePatchDiagnostic::TargetUnresolved)
}

fn source_has_drawing_fact(compilation: &TypedDdlCompilation, range: SourceSpan) -> bool {
    compilation
        .semantic_document
        .as_ref()
        .is_some_and(|semantic| {
            semantic
                .instruction_association
                .association
                .clause_stream
                .clauses
                .iter()
                .flat_map(|clause| &clause.atoms)
                .any(|atom| {
                    let span = atom.span();
                    range.start_byte <= span.start_byte
                        && span.end_byte <= range.end_byte
                        && match atom {
                            ClauseAtom::CoreRole(term) => term.role == CoreRoleKind::Primitive,
                            ClauseAtom::RemainingRole(term) => {
                                term.role == RemainingRoleKind::Motion
                            }
                            _ => false,
                        }
                })
        })
}

/// A bare lexical head in an ambiguous clause may name a reference target,
/// rather than another drawable. Retain its primitive as a compiler-resolved
/// previous target, without relaxing any established owner association.
fn reclassified_reference_facts(
    base: &TypedDdlCompilation,
    base_range: SourceSpan,
    candidate: &TypedDdlCompilation,
    candidate_range: SourceSpan,
) -> BTreeMap<String, usize> {
    let mut facts = BTreeMap::new();
    let (Some(before), Some(after)) = (&base.semantic_document, &candidate.semantic_document)
    else {
        return facts;
    };
    if [before, after].iter().any(|semantic| {
        !semantic.ast.coordinated_head_groups.is_empty()
            || !semantic.ast.group_predicates.is_empty()
            || !semantic.ast.continuations.is_empty()
            || !semantic.continuation_issues.is_empty()
            || !semantic
                .instruction_association
                .coordination_issues
                .is_empty()
            || !semantic.instruction_association.relation_issues.is_empty()
            || !semantic
                .instruction_association
                .association
                .ast
                .sequences
                .is_empty()
    }) || before.ast.instructions.iter().any(|instruction| {
        instruction.relation.is_some()
            || instruction.fill_target.is_some()
            || instruction.sequence.is_some()
    }) || after.ast.instructions.iter().any(|instruction| {
        instruction.fill_target.is_some()
            || instruction.sequence.is_some()
            || instruction
                .relation
                .as_ref()
                .is_some_and(|relation| !span_within(relation.provenance.span, candidate_range))
    }) {
        return facts;
    }
    let mut reference_targets = after
        .ast
        .instructions
        .iter()
        .enumerate()
        .filter_map(|(index, instruction)| {
            let relation = instruction.relation.as_ref()?;
            if !span_within(relation.provenance.span, candidate_range)
                || relation.reference != crate::SemanticPreviousReference::PreviousOne
            {
                return None;
            }
            let target = after.ast.instructions.get(index.checked_sub(1)?)?;
            (target.entity.head.source().span.end_byte <= candidate_range.start_byte)
                .then(|| semantic_head_value(target))
        })
        .collect::<Vec<_>>();
    for instruction in &before.ast.instructions {
        let source = instruction.entity.head.source();
        if !span_within(source.span, base_range)
            || !matches!(instruction.entity.head, crate::SemanticHead::Primitive(_))
            || instruction.action.is_some()
            || instruction.position.is_some()
            || instruction.layout_direction.is_some()
            || instruction.relation.is_some()
            || instruction.fill_target.is_some()
            || instruction.sequence.is_some()
            || !before.instruction_association.issues.iter().any(|issue| {
                issue.region_index == source.region_index
                    && issue.kind == crate::SemanticInstructionIssueKind::AmbiguousActionOwnership
            })
        {
            continue;
        }
        let mut associations = BTreeMap::new();
        record_entity_associations(
            &mut associations,
            &Value::Null,
            instruction,
            SourceSpan {
                start_byte: 0,
                end_byte: base.document.source().len(),
            },
        );
        if !associations.is_empty() {
            continue;
        }
        let head = semantic_head_value(instruction);
        if let Some(index) = reference_targets.iter().position(|target| *target == head) {
            reference_targets.remove(index);
            for (fact, count) in typed_fact_counts(base, source.span) {
                *facts.entry(fact).or_default() += count;
            }
        }
    }
    facts
}

fn candidate_has_drawable_instruction(
    compilation: &TypedDdlCompilation,
    range: SourceSpan,
) -> bool {
    let Some(semantic) = &compilation.semantic_document else {
        return false;
    };
    semantic
        .ast
        .instructions
        .iter()
        .enumerate()
        .any(|(instruction_index, instruction)| {
            if !overlaps(instruction.entity.head.source().span, range) {
                return false;
            }
            if instruction
                .action
                .as_ref()
                .is_some_and(|action| overlaps(action.provenance.source.span, range))
            {
                return true;
            }
            semantic.ast.group_predicates.iter().any(|predicate| {
                predicate
                    .action
                    .as_ref()
                    .is_some_and(|action| overlaps(action.provenance.source.span, range))
                    && semantic
                        .ast
                        .coordinated_head_groups
                        .get(predicate.group_index)
                        .is_some_and(|group| {
                            group
                                .member_instruction_indices
                                .contains(&instruction_index)
                        })
            })
        })
}

fn resolved_association_counts(
    compilation: &TypedDdlCompilation,
    range: SourceSpan,
) -> BTreeMap<String, usize> {
    let mut associations = BTreeMap::new();
    let Some(semantic) = &compilation.semantic_document else {
        return associations;
    };
    let instructions = &semantic.ast.instructions;
    for (instruction_index, instruction) in instructions.iter().enumerate() {
        if !span_within(instruction.entity.head.source().span, range) {
            continue;
        }
        let target = semantic_target_value(instruction_index, instructions);
        record_entity_associations(&mut associations, &target, instruction, range);

        if let Some(sequence) = &instruction.sequence
            && span_within(sequence.operator.provenance.source.span, range)
        {
            record_association(
                &mut associations,
                &target,
                "sequence",
                semantic_sequence_value(0, sequence),
            );
        }
        if let Some(action) = &instruction.action
            && span_within(action.provenance.source.span, range)
        {
            record_association(
                &mut associations,
                &target,
                "action",
                semantic_identity_value(&action.identity),
            );
        }
        if let Some(position) = &instruction.position
            && span_within(position.provenance.source.span, range)
        {
            record_association(
                &mut associations,
                &target,
                "position",
                semantic_identity_value(&position.identity),
            );
        }
        if let Some(direction) = &instruction.layout_direction
            && span_within(direction.provenance.source.span, range)
        {
            record_association(
                &mut associations,
                &target,
                "layout_direction",
                semantic_identity_value(&direction.identity),
            );
        }
        if let Some(relation) = &instruction.relation
            && span_within(relation.provenance.span, range)
        {
            record_association(
                &mut associations,
                &target,
                "relation",
                relation_value(relation, instruction_index, instructions),
            );
        }
        if let Some(fill_target) = &instruction.fill_target
            && fill_target
                .sources()
                .iter()
                .any(|source| span_within(source.span, range))
        {
            record_association(
                &mut associations,
                &target,
                "fill_target",
                fill_target_value(fill_target, instructions),
            );
        }
    }

    for predicate in &semantic.ast.group_predicates {
        let Some(group) = semantic
            .ast
            .coordinated_head_groups
            .get(predicate.group_index)
        else {
            continue;
        };
        let member_targets = group
            .member_instruction_indices
            .iter()
            .filter(|index| {
                instructions.get(**index).is_some_and(|instruction| {
                    span_within(instruction.entity.head.source().span, range)
                })
            })
            .map(|index| semantic_target_value(*index, instructions))
            .collect::<Vec<_>>();
        if member_targets.len() != group.member_instruction_indices.len() {
            continue;
        }
        let target = Value::Array(member_targets);
        if let Some(action) = &predicate.action
            && span_within(action.provenance.source.span, range)
        {
            record_association(
                &mut associations,
                &target,
                "group_action",
                semantic_identity_value(&action.identity),
            );
        }
        if let Some(position) = &predicate.position
            && span_within(position.provenance.source.span, range)
        {
            record_association(
                &mut associations,
                &target,
                "group_position",
                semantic_identity_value(&position.identity),
            );
        }
        if let Some(relation) = &predicate.relation
            && span_within(relation.provenance.span, range)
        {
            let owner_index = group
                .member_instruction_indices
                .iter()
                .copied()
                .min()
                .unwrap_or_default();
            record_association(
                &mut associations,
                &target,
                "group_relation",
                relation_value(relation, owner_index, instructions),
            );
        }
        if let Some(fill_target) = &predicate.fill_target
            && fill_target
                .sources()
                .iter()
                .any(|source| span_within(source.span, range))
        {
            record_association(
                &mut associations,
                &target,
                "group_fill_target",
                fill_target_value(fill_target, instructions),
            );
        }
    }

    if let Some(background) = &semantic.ast.background {
        let target = Value::String("background".to_owned());
        if span_within(background.color.provenance.source.span, range) {
            record_association(
                &mut associations,
                &target,
                "color",
                semantic_identity_value(&background.color.identity),
            );
        }
        if span_within(background.action.provenance.source.span, range) {
            record_association(
                &mut associations,
                &target,
                "action",
                semantic_identity_value(&background.action.identity),
            );
        }
    }
    associations
}

fn record_entity_associations(
    associations: &mut BTreeMap<String, usize>,
    target: &Value,
    instruction: &SemanticInstruction,
    range: SourceSpan,
) {
    let entity = &instruction.entity;
    let canonical = semantic_entity_value(entity);
    let field = |name: &str| {
        canonical
            .get(name)
            .cloned()
            .expect("closed semantic entity value contains every requested field")
    };
    let nested_field = |owner: &str, name: &str| {
        canonical
            .get(owner)
            .and_then(|value| value.get(name))
            .cloned()
            .unwrap_or(Value::Null)
    };

    if let Some(constraint) = &entity.shape_constraint
        && std::iter::once(&constraint.provenance)
            .chain(&constraint.additional_provenance)
            .any(|source| span_within(source.span, range))
    {
        record_association(
            associations,
            target,
            "shape_constraint",
            field("shape_constraint"),
        );
    }
    if let Some(color) = &entity.color
        && span_within(color.provenance.source.span, range)
    {
        record_association(associations, target, "color", field("color"));
    }
    if let Some(quantity) = &entity.quantity
        && span_within(quantity.provenance.span, range)
    {
        record_association(associations, target, "quantity", field("quantity"));
    }
    if let Some(thinness) = &entity.thinness
        && span_within(thinness.provenance.span, range)
    {
        record_association(associations, target, "thinness", field("thinness"));
    }
    if let Some(scale) = &entity.relative_scale
        && span_within(scale.provenance.span, range)
    {
        record_association(
            associations,
            target,
            "relative_scale",
            field("relative_scale"),
        );
    }
    if let Some(geometry) = &entity.explicit_geometry
        && span_within(geometry.source().span, range)
    {
        record_association(
            associations,
            target,
            "explicit_geometry",
            semantic_explicit_geometry_value(geometry),
        );
    }
    for scale in &entity.additional_relative_scales {
        if span_within(scale.provenance.span, range) {
            record_association(
                associations,
                target,
                "additional_relative_scale",
                Value::String(scale.value.as_str().to_owned()),
            );
        }
    }
    for geometry in &entity.additional_explicit_geometries {
        if span_within(geometry.source().span, range) {
            record_association(
                associations,
                target,
                "additional_explicit_geometry",
                semantic_explicit_geometry_value(geometry),
            );
        }
    }
    for width_extent in &entity.additional_width_extents {
        if span_within(width_extent.provenance.source.span, range) {
            record_association(
                associations,
                target,
                "additional_width_extent",
                semantic_identity_value(&width_extent.identity),
            );
        }
    }
    if let Some(position) = &entity.numeric_position
        && span_within(position.source().span, range)
    {
        record_association(
            associations,
            target,
            "numeric_position",
            semantic_numeric_position_value(position),
        );
    }
    for (owner, term, value) in [
        ("touch", entity.touch.as_ref(), field("touch")),
        (
            "continuity",
            entity.continuity.as_ref(),
            field("continuity"),
        ),
        ("angle", entity.angle.as_ref(), field("angle")),
        (
            "surface_quality",
            entity.surface.quality.as_ref(),
            nested_field("surface", "quality"),
        ),
        (
            "surface_intensity",
            entity.surface.intensity.as_ref(),
            nested_field("surface", "intensity"),
        ),
        (
            "fluctuation_spread",
            entity.fluctuation.spread.as_ref(),
            nested_field("fluctuation", "spread"),
        ),
        (
            "fluctuation_amplitude",
            entity.fluctuation.amplitude.as_ref(),
            nested_field("fluctuation", "amplitude"),
        ),
        (
            "fluctuation_frequency",
            entity.fluctuation.frequency.as_ref(),
            nested_field("fluctuation", "frequency"),
        ),
        (
            "fluctuation_quality",
            entity.fluctuation.quality.as_ref(),
            nested_field("fluctuation", "quality"),
        ),
        (
            "proportion_aspect",
            entity.proportion.aspect.as_ref(),
            nested_field("proportion", "aspect"),
        ),
        (
            "proportion_width_extent",
            entity.proportion.width_extent.as_ref(),
            nested_field("proportion", "width_extent"),
        ),
        (
            "proportion_arc_form",
            entity.proportion.arc_form.as_ref(),
            nested_field("proportion", "arc_form"),
        ),
    ] {
        if term.is_some_and(|term| span_within(term.provenance.source.span, range)) {
            record_association(associations, target, owner, value);
        }
    }
}

fn semantic_head_value(instruction: &SemanticInstruction) -> Value {
    semantic_entity_value(&instruction.entity)
        .get("head")
        .cloned()
        .expect("closed semantic entity value contains its head")
}

fn semantic_target_value(instruction_index: usize, instructions: &[SemanticInstruction]) -> Value {
    let head = semantic_head_value(&instructions[instruction_index]);
    let occurrence = instructions[..instruction_index]
        .iter()
        .filter(|instruction| semantic_head_value(instruction) == head)
        .count();
    serde_json::json!({
        "head": head,
        "source_order_occurrence": occurrence,
    })
}

fn relation_value(
    relation: &SemanticRelation,
    owner_index: usize,
    instructions: &[SemanticInstruction],
) -> Value {
    let target_count = match relation.reference {
        crate::SemanticPreviousReference::PreviousOne => 1,
        crate::SemanticPreviousReference::PreviousTwo => 2,
    };
    let referenced_targets = instructions[..owner_index.min(instructions.len())]
        .iter()
        .enumerate()
        .rev()
        .take(target_count)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .map(|(index, _)| semantic_target_value(index, instructions))
        .collect::<Vec<_>>();
    serde_json::json!({
        "kind": relation.kind.as_str(),
        "reference": relation.reference.as_str(),
        "referenced_targets": referenced_targets,
        "target_endpoint": relation.target_endpoint,
        "target_path_selection": relation.target_path_selection,
    })
}

fn fill_target_value(
    fill_target: &SemanticFillTarget,
    instructions: &[SemanticInstruction],
) -> Value {
    match fill_target {
        SemanticFillTarget::Canvas { .. } => serde_json::json!({"kind": "canvas"}),
        SemanticFillTarget::InlineShape {
            target_instruction_index,
            ..
        } => serde_json::json!({
            "kind": "inline_shape",
            "target": instructions
                .get(*target_instruction_index)
                .map(|_| semantic_target_value(*target_instruction_index, instructions)),
        }),
    }
}

fn record_association(
    associations: &mut BTreeMap<String, usize>,
    target: &Value,
    owner: &str,
    value: Value,
) {
    let key = serde_json::to_string(&Value::Array(vec![
        target.clone(),
        Value::String(owner.to_owned()),
        value,
    ]))
    .expect("closed semantic association key serializes");
    *associations.entry(key).or_default() += 1;
}

const fn span_within(span: SourceSpan, range: SourceSpan) -> bool {
    range.start_byte <= span.start_byte && span.end_byte <= range.end_byte
}

fn typed_fact_counts(
    compilation: &TypedDdlCompilation,
    range: SourceSpan,
) -> BTreeMap<String, usize> {
    let mut facts = BTreeMap::new();
    let Some(semantic) = &compilation.semantic_document else {
        return facts;
    };
    for atom in semantic
        .instruction_association
        .association
        .clause_stream
        .clauses
        .iter()
        .flat_map(|clause| &clause.atoms)
    {
        let span = atom.span();
        if range.start_byte > span.start_byte || span.end_byte > range.end_byte {
            continue;
        }
        let fact = match atom {
            ClauseAtom::CoreRole(term) => Some(format!(
                "core:{:?}:{}:{}:{}",
                term.role, term.asset_id, term.category_key, term.canonical_surface_ja
            )),
            ClauseAtom::CoreModifier(term) => Some(format!(
                "modifier:{:?}:{:?}",
                term.identity.dimension, term.identity.value
            )),
            ClauseAtom::RemainingRole(term) => Some(format!(
                "remaining:{:?}:{}:{}:{}",
                term.role, term.asset_id, term.category_key, term.canonical_surface_ja
            )),
            ClauseAtom::UnattachedExactNumber(number) => Some(format!("number:{}", number.value)),
            ClauseAtom::SaijikiRelation {
                asset_id,
                relation_type,
                ..
            } => Some(format!("relation:{relation_type}:{asset_id}")),
            ClauseAtom::FunctionWord { .. } | ClauseAtom::UnresolvedDiagnostic(_) => None,
        };
        if let Some(fact) = fact {
            *facts.entry(fact).or_default() += 1;
        }
    }
    facts
}

trait SortedInsert {
    fn insert_sorted(&mut self, value: String) -> bool;
}

impl SortedInsert for Vec<String> {
    fn insert_sorted(&mut self, value: String) -> bool {
        match self.binary_search(&value) {
            Ok(_) => false,
            Err(index) => {
                self.insert(index, value);
                true
            }
        }
    }
}

fn merge(source: &str, edits: &[VisibleDdlPatchEdit]) -> (String, Vec<SourceSpan>) {
    let growth = edits
        .iter()
        .map(|edit| {
            edit.replacement
                .len()
                .saturating_sub(edit.allowed_span.end_byte - edit.allowed_span.start_byte)
        })
        .sum::<usize>();
    let mut output = String::with_capacity(source.len() + growth);
    let mut ranges = Vec::with_capacity(edits.len());
    let mut cursor = 0;
    for edit in edits {
        output.push_str(&source[cursor..edit.allowed_span.start_byte]);
        let start_byte = output.len();
        output.push_str(&edit.replacement);
        ranges.push(SourceSpan {
            start_byte,
            end_byte: output.len(),
        });
        cursor = edit.allowed_span.end_byte;
    }
    output.push_str(&source[cursor..]);
    (output, ranges)
}

fn outside_bytes_preserved(
    base: &str,
    candidate: &str,
    edits: &[VisibleDdlPatchEdit],
    candidate_ranges: &[SourceSpan],
) -> bool {
    let mut base_cursor = 0;
    let mut candidate_cursor = 0;
    for (edit, candidate_range) in edits.iter().zip(candidate_ranges) {
        if base[base_cursor..edit.allowed_span.start_byte]
            != candidate[candidate_cursor..candidate_range.start_byte]
        {
            return false;
        }
        base_cursor = edit.allowed_span.end_byte;
        candidate_cursor = candidate_range.end_byte;
    }
    base[base_cursor..] == candidate[candidate_cursor..]
}

fn outside_explicit(
    compilation: &TypedDdlCompilation,
    ranges: &[SourceSpan],
) -> Vec<SemanticDeliveryIdentity> {
    let mut values = compilation
        .deliveries
        .iter()
        .filter(|item| item.kind == SemanticDeliveryKind::Explicit)
        .filter(|item| {
            item.span
                .is_none_or(|span| !ranges.iter().any(|range| overlaps(span, *range)))
        })
        .map(|item| item.identity.clone())
        .collect::<Vec<_>>();
    values.sort();
    values
}

fn outside_holes(
    compilation: &TypedDdlCompilation,
    ranges: &[SourceSpan],
) -> Vec<(String, crate::SemanticDeliveryOwner)> {
    let mut values = compilation
        .holes
        .iter()
        .filter(|item| !ranges.iter().any(|range| overlaps(item.span, *range)))
        .map(|item| (item.kind.clone(), item.expected_owner))
        .collect::<Vec<_>>();
    values.sort();
    values
}

fn outside_conflicts(
    compilation: &TypedDdlCompilation,
    ranges: &[SourceSpan],
) -> Vec<(String, Vec<String>, Option<String>)> {
    let source = compilation.document.source();
    let mut values = compilation
        .conflicts
        .iter()
        .filter(|item| {
            item.span
                .is_none_or(|span| !ranges.iter().any(|range| overlaps(span, *range)))
        })
        .map(|item| {
            let mut candidates = item.candidate_identities.clone();
            candidates.sort();
            (
                item.kind.clone(),
                candidates,
                item.span
                    .map(|span| sha256_hex(source[span.start_byte..span.end_byte].as_bytes())),
            )
        })
        .collect::<Vec<_>>();
    values.sort();
    values
}

fn outside_blocking_diagnostics(
    compilation: &TypedDdlCompilation,
    ranges: &[SourceSpan],
) -> Vec<(String, Option<String>)> {
    let source = compilation.document.source();
    let mut values = compilation
        .blocking_diagnostics
        .iter()
        .filter(|item| {
            item.span
                .is_none_or(|span| !ranges.iter().any(|range| overlaps(span, *range)))
        })
        .map(|item| {
            (
                item.kind.clone(),
                item.span
                    .map(|span| sha256_hex(source[span.start_byte..span.end_byte].as_bytes())),
            )
        })
        .collect::<Vec<_>>();
    values.sort();
    values
}

const fn overlaps(left: SourceSpan, right: SourceSpan) -> bool {
    left.start_byte < right.end_byte && right.start_byte < left.end_byte
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ResolvedInstructionLanguage;

    const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
        max_invocations: 16,
        max_depth: 16,
        max_evaluation_steps: 1_000,
        max_nodes_per_invocation: 100,
        max_total_nodes: 500,
    };

    fn compile(source: &str) -> TypedDdlCompilation {
        compile_typed_ddl(
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new())
                .unwrap(),
            &[],
            None,
            LIMITS,
        )
    }

    #[test]
    fn unresolved_clause_with_drawing_facts_requires_an_associated_instruction() {
        let base = compile("出力: 黒い背景に、粗筆の黒い四角を中央に置く。面: 粗く塗りつぶす。");
        let hole = base.holes.first().expect("whole unresolved clause");
        assert_eq!(hole.allowed_span.start_byte, 0);
        assert_eq!(hole.allowed_span.end_byte, 65);

        let mut candidate =
            compile("背景を黒で埋める。太筆の黒い四角を中央に置く。面: 粗く塗りつぶす。");
        let range = SourceSpan {
            start_byte: 0,
            end_byte: "背景を黒で埋める。太筆の黒い四角を中央に置く。".len(),
        };
        assert_eq!(
            candidate.compiler_lock.as_ref().unwrap().state,
            CompilerLockState::BlockedDiagnostic
        );
        assert!(target_resolution_failure(hole, &base, &candidate, range).is_none());

        candidate
            .semantic_document
            .as_mut()
            .unwrap()
            .ast
            .instructions
            .clear();
        assert!(
            candidate
                .deliveries
                .iter()
                .any(|delivery| { delivery.identity.owner == SemanticDeliveryOwner::Background })
        );
        assert!(
            candidate
                .deliveries
                .iter()
                .any(|delivery| { delivery.identity.owner == SemanticDeliveryOwner::EntityHead })
        );
        assert_eq!(
            target_resolution_failure(hole, &base, &candidate, range),
            Some(VisiblePatchDiagnostic::TargetUnresolved)
        );
    }

    #[test]
    fn detailed_validation_attributes_owner_reassignment_to_the_exact_hole() {
        let base = compile("出力: 赤い円と青い円を中央に置く。面: 粗く塗りつぶす。");
        let hole = base.holes.first().expect("whole unresolved clause");
        assert_eq!(hole.kind, "unresolved_clause");
        let patch = VisibleDdlPatch::new(
            sha256_hex(base.document.source().as_bytes()),
            base.compiler_lock.as_ref().unwrap().full_digest.clone(),
            vec![VisibleDdlPatchEdit {
                hole_id: hole.id.clone(),
                allowed_span: hole.allowed_span,
                expected_range_digest: hole.expected_range_digest.clone(),
                replacement: "青い円と赤い円を中央に置く。".to_owned(),
            }],
        );

        let failure =
            validate_visible_ddl_patch_detailed(&base, &patch, &[], None, LIMITS).unwrap_err();
        assert_eq!(
            failure.diagnostic,
            VisiblePatchDiagnostic::OwnerAssociationChanged
        );
        assert_eq!(failure.diagnostic.kind(), "owner_association_changed");
        assert_eq!(failure.hole_id.as_deref(), Some(hole.id.as_str()));
    }
}
