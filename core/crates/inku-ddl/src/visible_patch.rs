//! Base-lock constrained visible-source patching and full candidate recompilation.

use std::collections::{BTreeMap, BTreeSet};

use sha2::{Digest, Sha256};

use crate::{
    ClauseAtom, CompilerLockState, CoreRoleKind, MacroDefinition, MacroExpansionLimits,
    NormalizedDdlDocument, RemainingRoleKind, SemanticDeliveryIdentity, SemanticDeliveryKind,
    SemanticDeliveryOwner, SourceSpan, TypedDdlCompilation, compile_typed_ddl,
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
    if patch.schema_id != VISIBLE_DDL_PATCH_SCHEMA_ID {
        return Err(VisiblePatchDiagnostic::InvalidSchema);
    }
    if patch.edits.is_empty() {
        return Err(VisiblePatchDiagnostic::EmptyPatch);
    }
    let Some(base_lock) = &base.compiler_lock else {
        return Err(VisiblePatchDiagnostic::BaseIntegrityFailure);
    };
    let source = base.document.source();
    if patch.base_source_digest != sha256_hex(source.as_bytes()) {
        return Err(VisiblePatchDiagnostic::StaleSource);
    }
    if patch.base_compiler_lock_digest != base_lock.full_digest {
        return Err(VisiblePatchDiagnostic::StaleCompilerLock);
    }
    if !visible_ddl_patch_available(base) {
        if patch.edits.iter().any(|edit| {
            base.conflicts
                .iter()
                .any(|conflict| conflict.id == edit.hole_id)
        }) {
            return Err(VisiblePatchDiagnostic::ConflictTarget);
        }
        if patch.edits.iter().any(|edit| {
            base.blocking_diagnostics
                .iter()
                .any(|diagnostic| diagnostic.id == edit.hole_id)
        }) {
            return Err(VisiblePatchDiagnostic::BlockingDiagnosticTarget);
        }
        return Err(VisiblePatchDiagnostic::PatchTargetUnavailable);
    }

    let mut previous: Option<&VisibleDdlPatchEdit> = None;
    let mut hole_ids = Vec::new();
    for edit in &patch.edits {
        if edit.replacement.is_empty() {
            return Err(VisiblePatchDiagnostic::EmptyReplacement);
        }
        if !hole_ids.insert_sorted(edit.hole_id.clone()) {
            return Err(VisiblePatchDiagnostic::DuplicateHole);
        }
        if let Some(previous) = previous {
            if edit.allowed_span.start_byte < previous.allowed_span.start_byte {
                return Err(VisiblePatchDiagnostic::UnorderedEdits);
            }
            if edit.allowed_span.start_byte < previous.allowed_span.end_byte {
                return Err(VisiblePatchDiagnostic::OverlappingEdits);
            }
        }
        previous = Some(edit);

        let span = edit.allowed_span;
        if span.start_byte >= span.end_byte
            || span.end_byte > source.len()
            || !source.is_char_boundary(span.start_byte)
            || !source.is_char_boundary(span.end_byte)
        {
            return Err(VisiblePatchDiagnostic::InvalidRange);
        }

        let Some(hole) = base.holes.iter().find(|hole| hole.id == edit.hole_id) else {
            if base.conflicts.iter().any(|item| item.id == edit.hole_id) {
                return Err(VisiblePatchDiagnostic::ConflictTarget);
            }
            if base
                .blocking_diagnostics
                .iter()
                .any(|item| item.id == edit.hole_id)
            {
                return Err(VisiblePatchDiagnostic::BlockingDiagnosticTarget);
            }
            if base
                .deliveries
                .iter()
                .any(|item| item.id == edit.hole_id && item.kind == SemanticDeliveryKind::Explicit)
            {
                return Err(VisiblePatchDiagnostic::ExplicitTarget);
            }
            return Err(VisiblePatchDiagnostic::UnknownTarget);
        };
        if hole.allowed_span != edit.allowed_span {
            return Err(VisiblePatchDiagnostic::SpanMismatch);
        }
        let actual_range_digest = sha256_hex(source[span.start_byte..span.end_byte].as_bytes());
        if edit.expected_range_digest != hole.expected_range_digest
            || edit.expected_range_digest != actual_range_digest
        {
            return Err(VisiblePatchDiagnostic::RangeDigestMismatch);
        }
    }

    let (candidate_source, candidate_ranges) = merge(source, &patch.edits);
    if !outside_bytes_preserved(source, &candidate_source, &patch.edits, &candidate_ranges) {
        return Err(VisiblePatchDiagnostic::OutsideBytesChanged);
    }
    let candidate_document = NormalizedDdlDocument::new(
        candidate_source,
        base.document.language(),
        base.document.macro_locks().to_vec(),
    )
    .map_err(|_| VisiblePatchDiagnostic::SidecarLockChanged)?;
    if candidate_document.macro_locks() != base.document.macro_locks() {
        return Err(VisiblePatchDiagnostic::SidecarLockChanged);
    }

    let candidate = compile_typed_ddl(
        candidate_document.clone(),
        definitions,
        composition_seed,
        limits,
    );
    if candidate.compiler_lock.is_none() {
        return Err(VisiblePatchDiagnostic::CandidateIntegrityFailure);
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
            return Err(VisiblePatchDiagnostic::TargetUnresolved);
        }
        let hole = base
            .holes
            .iter()
            .find(|hole| hole.id == edit.hole_id)
            .expect("validated edit retains its exact typed hole");
        if !target_resolved(hole, base, &candidate, *range) {
            return Err(VisiblePatchDiagnostic::TargetUnresolved);
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
        return Err(VisiblePatchDiagnostic::OutsideExplicitChanged);
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
        return Err(VisiblePatchDiagnostic::NewDiagnostic);
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

fn target_resolved(
    hole: &crate::TypedHole,
    base: &TypedDdlCompilation,
    candidate: &TypedDdlCompilation,
    range: SourceSpan,
) -> bool {
    if hole.kind == "unresolved_clause" {
        let required = typed_fact_counts(base, hole.span);
        let delivered = typed_fact_counts(candidate, range);
        if required
            .iter()
            .any(|(fact, count)| delivered.get(fact).copied().unwrap_or_default() < *count)
        {
            return false;
        }
        let owners = candidate
            .deliveries
            .iter()
            .filter(|item| item.kind == SemanticDeliveryKind::Explicit)
            .filter(|item| item.span.is_some_and(|span| overlaps(span, range)))
            .map(|item| item.identity.owner)
            .collect::<BTreeSet<_>>();
        if source_has_drawing_fact(base, hole.span) {
            return candidate_has_drawable_instruction(candidate, range);
        }
        return owners.contains(&SemanticDeliveryOwner::Background)
            || owners.contains(&SemanticDeliveryOwner::Ground)
            || candidate_has_drawable_instruction(candidate, range);
    }
    candidate.deliveries.iter().any(|item| {
        item.kind == SemanticDeliveryKind::Explicit
            && item.identity.owner == hole.expected_owner
            && item.span.is_some_and(|span| overlaps(span, range))
    })
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
        assert!(target_resolved(hole, &base, &candidate, range));

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
        assert!(!target_resolved(hole, &base, &candidate, range));
    }
}
