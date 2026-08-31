//! Base-lock constrained visible-source patching and full candidate recompilation.

use sha2::{Digest, Sha256};

use crate::{
    CompilerLockState, MacroDefinition, MacroExpansionLimits, NormalizedDdlDocument,
    SemanticDeliveryKind, SourceSpan, TypedDdlCompilation, compile_typed_ddl,
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
    if base_lock.state != CompilerLockState::IncompleteKnownHole {
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
        if !target_resolved(hole, &candidate, *range) {
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
    if base_holes != candidate_holes
        || candidate.conflicts.iter().any(|item| {
            item.span
                .is_none_or(|span| !candidate_ranges.iter().any(|range| overlaps(span, *range)))
        })
        || candidate.blocking_diagnostics.iter().any(|item| {
            item.span
                .is_none_or(|span| !candidate_ranges.iter().any(|range| overlaps(span, *range)))
        })
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
    candidate: &TypedDdlCompilation,
    range: SourceSpan,
) -> bool {
    candidate.deliveries.iter().any(|item| {
        if item.kind != SemanticDeliveryKind::Explicit
            || !item.span.is_some_and(|span| overlaps(span, range))
        {
            return false;
        }
        match hole.kind.as_str() {
            "unresolved_value" => item.descriptor.starts_with("number|"),
            "missing_relation_target" => hole
                .candidate_identity
                .strip_suffix(":missing-target")
                .is_some_and(|occurrence| {
                    item.descriptor
                        .contains(&format!("occurrence={occurrence}"))
                }),
            "missing_macro_lock"
            | "missing_macro_definition"
            | "invalid_macro_definition"
            | "missing_macro_parameter"
            | "unsupported_macro_parameter"
            | "macro_parameter_numeric_range"
            | "macro_parameter_numeric_precision" => {
                item.descriptor.contains(&hole.candidate_identity)
            }
            _ => false,
        }
    })
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

fn outside_explicit(compilation: &TypedDdlCompilation, ranges: &[SourceSpan]) -> Vec<String> {
    let mut values = compilation
        .deliveries
        .iter()
        .filter(|item| item.kind == SemanticDeliveryKind::Explicit)
        .filter(|item| {
            item.span
                .is_none_or(|span| !ranges.iter().any(|range| overlaps(span, *range)))
        })
        .map(|item| item.descriptor.clone())
        .collect::<Vec<_>>();
    values.sort();
    values
}

fn outside_holes(compilation: &TypedDdlCompilation, ranges: &[SourceSpan]) -> Vec<String> {
    let mut values = compilation
        .holes
        .iter()
        .filter(|item| !ranges.iter().any(|range| overlaps(item.span, *range)))
        .map(|item| format!("{}|{}", item.kind, item.candidate_identity))
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
