use std::collections::HashSet;

use inku_ddl::{
    CompilerLockState, MacroDefinition, MacroExpansionLimits, NormalizedDdlDocument,
    ResolvedInstructionLanguage, SemanticDeliveryOwner, SemanticIssueCausalProvenance,
    SemanticUpstreamCausalRelation, SourceSpan, VISIBLE_DDL_PATCH_SCHEMA_ID, VisibleDdlPatch,
    VisibleDdlPatchEdit, VisiblePatchDiagnostic, compile_typed_ddl, validate_visible_ddl_patch,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/compiler-lock-visible-patch-v12.json");
const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 16,
    max_depth: 16,
    max_evaluation_steps: 1_000,
    max_nodes_per_invocation: 100,
    max_total_nodes: 500,
};

#[derive(Deserialize)]
struct FixtureIds {
    schema: String,
    version: u32,
    patch_case_ids: Vec<String>,
}

#[test]
fn valid_single_multiple_and_subset_patches_preserve_base_and_return_only_candidates() {
    let base = base("white triangle. many circle. many square");
    let base_snapshot = base.clone();
    let holes = source_ordered_holes(&base);
    assert_eq!(holes.len(), 2);

    let single_patch = patch(&base, vec![edit(holes[0], "8")]);
    let single = validate_visible_ddl_patch(&base, &single_patch, &[], None, LIMITS).unwrap();
    assert_eq!(
        single.document.source(),
        "white triangle. 8 circle. many square"
    );
    assert_eq!(
        single.compilation.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::IncompleteKnownHole
    );
    assert_eq!(single.compilation.holes.len(), 1);
    assert_eq!(single.resolved_hole_ids, vec![holes[0].id.clone()]);
    assert_eq!(base, base_snapshot);

    let multiple_patch = patch(&base, vec![edit(holes[0], "8"), edit(holes[1], "12")]);
    let multiple = validate_visible_ddl_patch(&base, &multiple_patch, &[], None, LIMITS).unwrap();
    assert_eq!(
        multiple.document.source(),
        "white triangle. 8 circle. 12 square"
    );
    assert_eq!(
        multiple.compilation.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady
    );
    assert!(multiple.compilation.holes.is_empty());
    assert_eq!(multiple.document.macro_locks(), base.document.macro_locks());
    assert_eq!(base, base_snapshot);

    let explicit_outside = base
        .deliveries
        .iter()
        .find(|item| item.identity.owner == SemanticDeliveryOwner::Color)
        .unwrap();
    assert!(
        multiple
            .compilation
            .deliveries
            .iter()
            .any(|item| item.descriptor == explicit_outside.descriptor)
    );
}

#[test]
fn stale_order_range_overlap_and_target_boundaries_fail_closed() {
    let base = base("white triangle. many circle. many square");
    let holes = source_ordered_holes(&base);
    let valid_first = edit(holes[0], "8");
    let valid_second = edit(holes[1], "12");

    let mut invalid_schema = patch(&base, vec![valid_first.clone()]);
    invalid_schema.schema_id = "inku.visible-ddl-patch.invalid";
    assert_error(&base, invalid_schema, VisiblePatchDiagnostic::InvalidSchema);
    assert_error(
        &base,
        patch(&base, Vec::new()),
        VisiblePatchDiagnostic::EmptyPatch,
    );

    assert_error(
        &base,
        VisibleDdlPatch::new("0".repeat(64), lock(&base), vec![valid_first.clone()]),
        VisiblePatchDiagnostic::StaleSource,
    );
    assert_error(
        &base,
        VisibleDdlPatch::new(source(&base), "0".repeat(64), vec![valid_first.clone()]),
        VisiblePatchDiagnostic::StaleCompilerLock,
    );
    let mut span_mismatch = valid_first.clone();
    span_mismatch.allowed_span.end_byte -= 1;
    assert_error(
        &base,
        patch(&base, vec![span_mismatch]),
        VisiblePatchDiagnostic::SpanMismatch,
    );
    let mut range_mismatch = valid_first.clone();
    range_mismatch.expected_range_digest = "0".repeat(64);
    assert_error(
        &base,
        patch(&base, vec![range_mismatch]),
        VisiblePatchDiagnostic::RangeDigestMismatch,
    );
    let mut out_of_bound = valid_first.clone();
    out_of_bound.allowed_span.end_byte = base.document.source().len() + 1;
    assert_error(
        &base,
        patch(&base, vec![out_of_bound]),
        VisiblePatchDiagnostic::InvalidRange,
    );
    let ja_base = compile_typed_ddl(
        NormalizedDdlDocument::new("たくさん 円", ResolvedInstructionLanguage::Ja, Vec::new())
            .unwrap(),
        &[],
        None,
        LIMITS,
    );
    let mut non_char = edit(&ja_base.holes[0], "8");
    non_char.allowed_span.start_byte += 1;
    assert_error(
        &ja_base,
        patch(&ja_base, vec![non_char]),
        VisiblePatchDiagnostic::InvalidRange,
    );
    assert_error(
        &base,
        patch(&base, vec![valid_second.clone(), valid_first.clone()]),
        VisiblePatchDiagnostic::UnorderedEdits,
    );
    let mut overlapping_second = valid_second.clone();
    overlapping_second.allowed_span.start_byte = valid_first.allowed_span.end_byte - 1;
    assert_error(
        &base,
        patch(&base, vec![valid_first.clone(), overlapping_second]),
        VisiblePatchDiagnostic::OverlappingEdits,
    );
    assert_error(
        &base,
        patch(&base, vec![valid_first.clone(), valid_first.clone()]),
        VisiblePatchDiagnostic::DuplicateHole,
    );
    let mut empty = valid_first.clone();
    empty.replacement.clear();
    assert_error(
        &base,
        patch(&base, vec![empty]),
        VisiblePatchDiagnostic::EmptyReplacement,
    );

    let explicit = base
        .deliveries
        .iter()
        .find(|item| item.identity.owner == SemanticDeliveryOwner::Color)
        .unwrap();
    assert_error(
        &base,
        patch(
            &base,
            vec![VisibleDdlPatchEdit {
                hole_id: explicit.id.clone(),
                allowed_span: explicit.span.unwrap(),
                expected_range_digest: String::new(),
                replacement: "black".to_owned(),
            }],
        ),
        VisiblePatchDiagnostic::ExplicitTarget,
    );
    let explicit_scale_base = compile_typed_ddl(
        NormalizedDdlDocument::new(
            "small circle. many square",
            ResolvedInstructionLanguage::En,
            Vec::new(),
        )
        .unwrap(),
        &[],
        None,
        LIMITS,
    );
    let explicit_scale = explicit_scale_base
        .deliveries
        .iter()
        .find(|item| item.identity.owner == SemanticDeliveryOwner::RelativeScale)
        .unwrap();
    assert_error(
        &explicit_scale_base,
        patch(
            &explicit_scale_base,
            vec![VisibleDdlPatchEdit {
                hole_id: explicit_scale.id.clone(),
                allowed_span: explicit_scale.span.unwrap(),
                expected_range_digest: String::new(),
                replacement: "small".to_owned(),
            }],
        ),
        VisiblePatchDiagnostic::ExplicitTarget,
    );
    let mut unknown = valid_first.clone();
    unknown.hole_id = "hole:unknown".to_owned();
    assert_error(
        &base,
        patch(&base, vec![unknown]),
        VisiblePatchDiagnostic::UnknownTarget,
    );
}

#[test]
fn conflict_unknown_and_unresolved_replacements_never_return_a_candidate() {
    let conflict = base("red blue circle");
    assert_eq!(
        conflict.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::BlockedConflict
    );
    assert_error(
        &conflict,
        VisibleDdlPatch::new(source(&conflict), lock(&conflict), vec![fabricated_edit()]),
        VisiblePatchDiagnostic::PatchTargetUnavailable,
    );
    let conflict_item = &conflict.conflicts[0];
    assert_error(
        &conflict,
        VisibleDdlPatch::new(
            source(&conflict),
            lock(&conflict),
            vec![VisibleDdlPatchEdit {
                hole_id: conflict_item.id.clone(),
                allowed_span: conflict_item.span.unwrap(),
                expected_range_digest: String::new(),
                replacement: "circle".to_owned(),
            }],
        ),
        VisiblePatchDiagnostic::ConflictTarget,
    );

    let unknown = base("mystery");
    assert_eq!(
        unknown.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::BlockedDiagnostic
    );
    assert_error(
        &unknown,
        VisibleDdlPatch::new(source(&unknown), lock(&unknown), vec![fabricated_edit()]),
        VisiblePatchDiagnostic::PatchTargetUnavailable,
    );
    let blocking = &unknown.blocking_diagnostics[0];
    assert_error(
        &unknown,
        VisibleDdlPatch::new(
            source(&unknown),
            lock(&unknown),
            vec![VisibleDdlPatchEdit {
                hole_id: blocking.id.clone(),
                allowed_span: blocking.span.unwrap(),
                expected_range_digest: String::new(),
                replacement: "circle".to_owned(),
            }],
        ),
        VisiblePatchDiagnostic::BlockingDiagnosticTarget,
    );

    let ready = base("circle");
    assert_error(
        &ready,
        VisibleDdlPatch::new(source(&ready), lock(&ready), vec![fabricated_edit()]),
        VisiblePatchDiagnostic::PatchTargetUnavailable,
    );

    let integrity = compile_typed_ddl(
        NormalizedDdlDocument::new("circle", ResolvedInstructionLanguage::En, Vec::new()).unwrap(),
        &[],
        None,
        MacroExpansionLimits {
            max_invocations: 0,
            ..LIMITS
        },
    );
    assert_eq!(
        validate_visible_ddl_patch(
            &integrity,
            &VisibleDdlPatch::new(String::new(), String::new(), vec![fabricated_edit()]),
            &[],
            None,
            LIMITS,
        )
        .unwrap_err(),
        VisiblePatchDiagnostic::BaseIntegrityFailure
    );

    let patch_base = base("many circle");
    let hole = &patch_base.holes[0];
    assert_error(
        &patch_base,
        patch(&patch_base, vec![edit(hole, "mystery")]),
        VisiblePatchDiagnostic::TargetUnresolved,
    );
    assert_error(
        &patch_base,
        patch(&patch_base, vec![edit(hole, "Canon.Empty")]),
        VisiblePatchDiagnostic::TargetUnresolved,
    );

    let relation = base("eight along twelve");
    assert!(relation.holes.is_empty());
    assert_error(
        &relation,
        VisibleDdlPatch::new(source(&relation), lock(&relation), vec![fabricated_edit()]),
        VisiblePatchDiagnostic::PatchTargetUnavailable,
    );

    let definition = MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Empty","version":"1.0.0","parameters":{},"components":{},"body":[]}"#,
    )
    .unwrap();
    let missing_lock = compile_typed_ddl(
        NormalizedDdlDocument::new("Canon.Empty", ResolvedInstructionLanguage::En, Vec::new())
            .unwrap(),
        &[definition.clone()],
        None,
        LIMITS,
    );
    let missing_lock_hole = &missing_lock.holes[0];
    let result = validate_visible_ddl_patch(
        &missing_lock,
        &patch(&missing_lock, vec![edit(missing_lock_hole, "circle")]),
        &[definition],
        None,
        LIMITS,
    );
    let candidate = result.expect("typed macro-head hole accepts a Primitive head replacement");
    assert_eq!(candidate.document.source(), "circle");
    assert_eq!(
        candidate.compilation.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady
    );
}

#[test]
fn visible_patch_preserves_continuation_identity_and_rejects_unresolved_reference_bases() {
    let continuation_base = base("line. the line swaying fine. many circle");
    assert_eq!(continuation_base.holes.len(), 1);
    let continuation = &continuation_base
        .semantic_document
        .as_ref()
        .unwrap()
        .ast
        .continuations[0];
    let target = continuation.target.clone();
    let hole = &continuation_base.holes[0];
    let candidate = validate_visible_ddl_patch(
        &continuation_base,
        &patch(&continuation_base, vec![edit(hole, "eight")]),
        &[],
        None,
        LIMITS,
    )
    .expect("a disjoint quantity hole preserves the accepted continuation");
    assert_eq!(
        candidate.compilation.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady
    );
    assert_eq!(
        candidate
            .compilation
            .semantic_document
            .as_ref()
            .unwrap()
            .ast
            .continuations[0]
            .target,
        target
    );

    let unresolved = base("circle. the line swaying fine.");
    assert_eq!(
        unresolved.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::BlockedDiagnostic
    );
    assert_error(
        &unresolved,
        VisibleDdlPatch::new(
            source(&unresolved),
            lock(&unresolved),
            vec![fabricated_edit()],
        ),
        VisiblePatchDiagnostic::PatchTargetUnavailable,
    );

    let causal = base("blue orchard.");
    let issue = causal
        .semantic_document
        .as_ref()
        .unwrap()
        .instruction_association
        .association
        .issues
        .iter()
        .find(|issue| issue.kind.as_str() == "missing_entity_head")
        .unwrap();
    let SemanticIssueCausalProvenance::UpstreamDiagnostics(causes) = &issue.causal_provenance
    else {
        panic!("visible-patch base retains compiler-owned causal provenance");
    };
    assert_eq!(causes.len(), 1);
    assert_eq!(
        causes[0].relation,
        SemanticUpstreamCausalRelation::MissingEntityHeadGap
    );
    assert_eq!(
        causal
            .deliveries
            .iter()
            .filter(|delivery| delivery.span == Some(causes[0].span))
            .count(),
        1
    );
    assert_error(
        &causal,
        VisibleDdlPatch::new(source(&causal), lock(&causal), vec![fabricated_edit()]),
        VisiblePatchDiagnostic::PatchTargetUnavailable,
    );
}

#[test]
fn schema_fixture_and_patch_diagnostic_matrix_are_closed() {
    let fixture: FixtureIds = serde_json::from_str(FIXTURE).unwrap();
    assert_eq!(VISIBLE_DDL_PATCH_SCHEMA_ID, "inku.visible-ddl-patch.v1");
    assert_eq!(
        fixture.schema,
        "inku.compiler-lock-visible-patch-fixture.v12"
    );
    assert_eq!(fixture.version, 12);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));
    let ids = fixture
        .patch_case_ids
        .iter()
        .map(String::as_str)
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), 19);
    for required in [
        "valid-single",
        "valid-multiple",
        "valid-subset",
        "stale-source",
        "stale-lock",
        "span-mismatch",
        "range-mismatch",
        "out-of-bound",
        "non-char-boundary",
        "unordered",
        "overlap",
        "duplicate-hole",
        "empty-replacement",
        "explicit-target",
        "unknown-target",
        "conflict-base",
        "unknown-base",
        "unresolved-replacement",
        "new-macro-without-lock",
    ] {
        assert!(
            ids.contains(required),
            "missing patch fixture case {required}"
        );
    }
    let all = [
        VisiblePatchDiagnostic::InvalidSchema,
        VisiblePatchDiagnostic::EmptyPatch,
        VisiblePatchDiagnostic::BaseIntegrityFailure,
        VisiblePatchDiagnostic::PatchTargetUnavailable,
        VisiblePatchDiagnostic::StaleSource,
        VisiblePatchDiagnostic::StaleCompilerLock,
        VisiblePatchDiagnostic::UnknownTarget,
        VisiblePatchDiagnostic::ExplicitTarget,
        VisiblePatchDiagnostic::ConflictTarget,
        VisiblePatchDiagnostic::BlockingDiagnosticTarget,
        VisiblePatchDiagnostic::DuplicateHole,
        VisiblePatchDiagnostic::UnorderedEdits,
        VisiblePatchDiagnostic::OverlappingEdits,
        VisiblePatchDiagnostic::InvalidRange,
        VisiblePatchDiagnostic::SpanMismatch,
        VisiblePatchDiagnostic::RangeDigestMismatch,
        VisiblePatchDiagnostic::EmptyReplacement,
        VisiblePatchDiagnostic::SidecarLockChanged,
        VisiblePatchDiagnostic::OutsideBytesChanged,
        VisiblePatchDiagnostic::OutsideExplicitChanged,
        VisiblePatchDiagnostic::TargetUnresolved,
        VisiblePatchDiagnostic::NewDiagnostic,
        VisiblePatchDiagnostic::CandidateIntegrityFailure,
    ];
    assert_eq!(
        all.iter()
            .map(|value| value.kind())
            .collect::<HashSet<_>>()
            .len(),
        all.len()
    );
}

fn base(source: &str) -> inku_ddl::TypedDdlCompilation {
    compile_typed_ddl(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new()).unwrap(),
        &[],
        None,
        LIMITS,
    )
}

fn source_ordered_holes(base: &inku_ddl::TypedDdlCompilation) -> Vec<&inku_ddl::TypedHole> {
    let mut holes = base.holes.iter().collect::<Vec<_>>();
    holes.sort_by_key(|hole| hole.span.start_byte);
    holes
}

fn edit(hole: &inku_ddl::TypedHole, replacement: &str) -> VisibleDdlPatchEdit {
    VisibleDdlPatchEdit {
        hole_id: hole.id.clone(),
        allowed_span: hole.allowed_span,
        expected_range_digest: hole.expected_range_digest.clone(),
        replacement: replacement.to_owned(),
    }
}

fn patch(base: &inku_ddl::TypedDdlCompilation, edits: Vec<VisibleDdlPatchEdit>) -> VisibleDdlPatch {
    VisibleDdlPatch::new(source(base), lock(base), edits)
}

fn source(base: &inku_ddl::TypedDdlCompilation) -> String {
    base.compiler_lock
        .as_ref()
        .unwrap()
        .visible_source_digest
        .clone()
}

fn lock(base: &inku_ddl::TypedDdlCompilation) -> String {
    base.compiler_lock.as_ref().unwrap().full_digest.clone()
}

fn fabricated_edit() -> VisibleDdlPatchEdit {
    VisibleDdlPatchEdit {
        hole_id: "hole:fabricated".to_owned(),
        allowed_span: SourceSpan {
            start_byte: 0,
            end_byte: 1,
        },
        expected_range_digest: String::new(),
        replacement: "8".to_owned(),
    }
}

fn assert_error(
    base: &inku_ddl::TypedDdlCompilation,
    patch: VisibleDdlPatch,
    expected: VisiblePatchDiagnostic,
) {
    let result = validate_visible_ddl_patch(base, &patch, &[] as &[MacroDefinition], None, LIMITS);
    assert_eq!(result.unwrap_err(), expected);
}
