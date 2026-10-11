use std::collections::HashSet;

use inku_ddl::{
    CompilerLockState, CompletionRangeRecord, MacroDefinition, MacroExpansionLimits,
    NormalizedDdlDocument, RANGE_WORDS_CHANGED_HOLE_KIND, RecordedRange,
    ResolvedInstructionLanguage, SemanticDeliveryOwner, SemanticIssueCausalProvenance,
    SemanticUpstreamCausalRelation, SourceSpan, VISIBLE_DDL_PATCH_SCHEMA_ID, VisibleDdlPatch,
    VisibleDdlPatchEdit, VisiblePatchDiagnostic, compile_typed_ddl, validate_visible_ddl_patch,
    with_completion_record, written_ranges,
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
fn unresolved_clause_patch_keeps_typed_facts_and_resolves_the_clause() {
    let source = "青で背景を塗りつぶす\n様々な色の四角30個をクレヨンとコンピュータで塗りつぶす。";
    let base = compile_typed_ddl(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new()).unwrap(),
        &[],
        Some(23),
        LIMITS,
    );
    let holes = source_ordered_holes(&base);
    assert_eq!(holes.len(), 2, "{:?}", base.holes);
    let candidate = compile_typed_ddl(
        NormalizedDdlDocument::new(
            "背景を青で埋める\n様々な色の四角30個をクレヨンとコンピュータで塗りつぶす。",
            ResolvedInstructionLanguage::Ja,
            Vec::new(),
        )
        .unwrap(),
        &[],
        Some(23),
        LIMITS,
    );
    assert!(candidate.conflicts.is_empty(), "{:?}", candidate.conflicts);
    assert!(
        candidate.blocking_diagnostics.is_empty(),
        "{:?}",
        candidate.blocking_diagnostics
    );
    assert_eq!(candidate.holes.len(), 1, "{:?}", candidate.holes);

    let accepted = validate_visible_ddl_patch(
        &base,
        &patch(&base, vec![edit(holes[0], "背景を青で埋める")]),
        &[],
        Some(23),
        LIMITS,
    )
    .unwrap();
    assert_eq!(
        accepted.document.source(),
        "背景を青で埋める\n様々な色の四角30個をクレヨンとコンピュータで塗りつぶす。"
    );
    assert_eq!(accepted.compilation.holes.len(), 1);

    let complete_source = "背景を青で埋める。\n青いクレヨンの塗りの四角と赤いコンピュータの塗りの四角を交互に30個並べる。";
    let complete_compilation = compile_typed_ddl(
        NormalizedDdlDocument::new(complete_source, ResolvedInstructionLanguage::Ja, Vec::new())
            .unwrap(),
        &[],
        Some(23),
        LIMITS,
    );
    assert_eq!(
        complete_compilation.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady,
        "holes={:?}; conflicts={:?}; blocking={:?}",
        complete_compilation.holes,
        complete_compilation.conflicts,
        complete_compilation.blocking_diagnostics
    );
    let completed = validate_visible_ddl_patch(
        &base,
        &patch(
            &base,
            vec![
                edit(holes[0], "背景を青で埋める。"),
                edit(
                    holes[1],
                    "青いクレヨンの塗りの四角と赤いコンピュータの塗りの四角を交互に30個並べる",
                ),
            ],
        ),
        &[],
        Some(23),
        LIMITS,
    )
    .unwrap();
    assert_eq!(
        completed.compilation.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady,
        "holes={:?}; conflicts={:?}; blocking={:?}",
        completed.compilation.holes,
        completed.compilation.conflicts,
        completed.compilation.blocking_diagnostics
    );

    assert_error_with_seed(
        &base,
        patch(&base, vec![edit(holes[0], "背景を黒で埋める")]),
        VisiblePatchDiagnostic::EstablishedFactChanged,
        Some(23),
    );
}

#[test]
fn patch_preserves_unchanged_local_diagnostics_outside_the_hole() {
    let source = "出力: 黒い背景に、粗筆の黒い四角を中心に置く。面: 粗く塗りつぶす。";
    let base = compile_typed_ddl(
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new()).unwrap(),
        &[],
        Some(23),
        LIMITS,
    );
    assert_eq!(
        base.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::BlockedDiagnostic
    );
    assert_eq!(base.holes.len(), 1, "{:?}", base.holes);
    assert_eq!(
        base.blocking_diagnostics
            .iter()
            .map(|diagnostic| diagnostic.kind.as_str())
            .collect::<Vec<_>>(),
        vec!["upstream_unknown", "upstream_unknown"]
    );

    let accepted = validate_visible_ddl_patch(
        &base,
        &patch(
            &base,
            vec![edit(
                &base.holes[0],
                "背景を黒で埋める。太筆の黒い四角を中心に置く。",
            )],
        ),
        &[],
        Some(23),
        LIMITS,
    )
    .unwrap();

    assert!(accepted.compilation.holes.is_empty());
    assert_eq!(
        accepted.compilation.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::BlockedDiagnostic
    );
    assert_eq!(
        accepted
            .compilation
            .blocking_diagnostics
            .iter()
            .map(|diagnostic| diagnostic.kind.as_str())
            .collect::<Vec<_>>(),
        vec!["upstream_unknown", "upstream_unknown"]
    );
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
        std::slice::from_ref(&definition),
        None,
        LIMITS,
    );
    // A Macro invoked without its lock is an integrity failure: it blocks
    // and offers no hole to patch.
    assert!(missing_lock.holes.is_empty());
    assert_eq!(
        missing_lock.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::BlockedDiagnostic
    );
}

#[test]
fn visible_patch_preserves_continuation_identity_and_rejects_unresolved_reference_bases() {
    let continuation_base = base("line. the line swaying narrowly. many circle");
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

    let unresolved = base("circle. the line swaying narrowly.");
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
        VisiblePatchDiagnostic::NumericRangeOutsideWords,
        VisiblePatchDiagnostic::RangeWordsNotKept,
    ];
    assert_eq!(
        all.iter()
            .map(|value| value.kind())
            .collect::<HashSet<_>>()
            .len(),
        all.len()
    );
}

/// A1 (2026-10-06): a completion may keep the author's words and write the
/// place in numbers after them. A position word read in those words keeps the
/// established fact only when the numbers lie inside its range.
#[test]
fn completion_range_keeps_the_words_it_matches() {
    let mut mismatches = Vec::new();
    for (language, source, from, to, outside) in [
        (
            ResolvedInstructionLanguage::Ja,
            "右下に橙色の小さな円を十個ランダムに散らす。",
            "右下に",
            "右下（横2/3〜1、縦2/3〜1）に",
            "右下（横2/3〜1、縦0〜1/3）に",
        ),
        (
            ResolvedInstructionLanguage::En,
            "scatter ten small orange circles randomly at the bottom right.",
            "at the bottom right",
            "at the bottom right (horizontal 2/3 to 1, vertical 2/3 to 1)",
            "at the bottom right (horizontal 2/3 to 1, vertical 0 to 1/3)",
        ),
        (
            ResolvedInstructionLanguage::Ja,
            "右の隅に橙色の小さな円を十個ランダムに散らす。",
            "右の隅に",
            "右の隅（横4/5〜1、縦4/5〜1）に",
            "右の隅（横2/3〜1、縦2/3〜1）に",
        ),
    ] {
        let base = compiled(source, language);
        let holes = source_ordered_holes(&base);
        assert_eq!(holes.len(), 1, "{source}: {:?}", base.holes);
        let replaced = |range: &str| {
            let text = &source[holes[0].allowed_span.start_byte..holes[0].allowed_span.end_byte];
            text.replace(from, range)
                .replace("ランダムに", "")
                .replace(" randomly", "")
        };
        let accepted = validate_visible_ddl_patch(
            &base,
            &patch(&base, vec![edit(holes[0], &replaced(to))]),
            &[],
            None,
            LIMITS,
        );
        if let Err(reason) = &accepted {
            mismatches.push(format!("{source} -> {}: {reason:?}", replaced(to)));
        }
        let rejected = validate_visible_ddl_patch(
            &base,
            &patch(&base, vec![edit(holes[0], &replaced(outside))]),
            &[],
            None,
            LIMITS,
        );
        if rejected.as_ref().err() != Some(&VisiblePatchDiagnostic::NumericRangeOutsideWords) {
            mismatches.push(format!(
                "{source} -> {}: {:?}",
                replaced(outside),
                rejected.err()
            ));
        }
    }
    assert!(mismatches.is_empty(), "{mismatches:#?}");
}

/// Words without a position word are not matched: the numbers stand.
#[test]
fn completion_range_without_a_position_word_is_not_matched() {
    let source = "右寄りに橙色の小さな円を十個ランダムに散らす。";
    let base = compiled(source, ResolvedInstructionLanguage::Ja);
    let holes = source_ordered_holes(&base);
    assert_eq!(holes.len(), 1, "{:?}", base.holes);
    let accepted = validate_visible_ddl_patch(
        &base,
        &patch(
            &base,
            vec![edit(
                holes[0],
                &source[holes[0].allowed_span.start_byte..holes[0].allowed_span.end_byte]
                    .replace("右寄りに", "右寄り（横2/3〜1、縦0〜1）に")
                    .replace("ランダムに", ""),
            )],
        ),
        &[],
        None,
        LIMITS,
    );
    assert!(accepted.is_ok(), "{accepted:?}");
}

/// A numeric range already in the hole's clause is kept: a completion may not
/// move its bounds.
#[test]
fn completion_keeps_a_numeric_range_in_the_hole_clause() {
    let source = "右下（横2/3〜1、縦2/3〜1）に橙色の小さな円を十個ランダムに散らす。";
    let base = compiled(source, ResolvedInstructionLanguage::Ja);
    let holes = source_ordered_holes(&base);
    assert_eq!(holes.len(), 1, "{:?}", base.holes);
    let text = &source[holes[0].allowed_span.start_byte..holes[0].allowed_span.end_byte];
    let kept = validate_visible_ddl_patch(
        &base,
        &patch(&base, vec![edit(holes[0], &text.replace("ランダムに", ""))]),
        &[],
        None,
        LIMITS,
    );
    assert!(kept.is_ok(), "{kept:?}");
    let moved = validate_visible_ddl_patch(
        &base,
        &patch(
            &base,
            vec![edit(
                holes[0],
                &text
                    .replace("縦2/3〜1", "縦0〜1/3")
                    .replace("ランダムに", ""),
            )],
        ),
        &[],
        None,
        LIMITS,
    );
    assert_eq!(
        moved.err(),
        Some(VisiblePatchDiagnostic::OwnerAssociationChanged)
    );
}

/// A3 (2026-10-11): a range whose words the author changed takes new numbers
/// only. Its words stay to the letter, and a position word they hold must
/// contain the numbers, even the old ones; the same numbers pass for words that
/// mean the same place (T3).
#[test]
fn a_range_whose_words_changed_takes_new_numbers_only() {
    use VisiblePatchDiagnostic::{NumericRangeOutsideWords, RangeWordsNotKept};
    let ja = ResolvedInstructionLanguage::Ja;
    let completed =
        "白い四角を中心に置く。右下（横2/3〜1、縦2/3〜1）に橙色の小さな円を十個散らす。";
    let record = record_of(completed, ja);
    let mut mismatches = Vec::new();
    for (words, replacement, expected) in [
        ("左上", "左上（横0〜1/3、縦0〜1/3）", None),
        (
            "左上",
            "左の上（横0〜1/3、縦0〜1/3）",
            Some(RangeWordsNotKept),
        ),
        (
            "上",
            "上（横2/3〜1、縦2/3〜1）",
            Some(NumericRangeOutsideWords),
        ),
        ("上", "上（横0〜1、縦0〜1/3）", None),
        ("右下のあたり", "右下のあたり（横2/3〜1、縦2/3〜1）", None),
    ] {
        let edited = completed.replace("右下", words);
        let base = with_completion_record(compiled(&edited, ja), &record, &[]);
        let holes = words_changed_holes(&base);
        assert_eq!(holes.len(), 1, "{edited}: {:?}", base.holes);
        let result = validate_visible_ddl_patch(
            &base,
            &patch(&base, vec![edit(holes[0], replacement)]),
            &[],
            None,
            LIMITS,
        );
        match (&result, expected) {
            (Ok(candidate), None) => {
                // The range the patch wrote is the answer, not a hole again.
                assert!(words_changed_holes(&candidate.compilation).is_empty());
                let range = candidate.resolved_ranges[0];
                assert_eq!(
                    &candidate.document.source()[range.start_byte..range.end_byte],
                    replacement
                );
            }
            (Err(reason), Some(expected)) if *reason == expected => {}
            _ => mismatches.push(format!("{edited} -> {replacement}: {result:?}")),
        }
    }
    assert!(mismatches.is_empty(), "{mismatches:#?}");
}

/// T3: of two ranges whose words changed, one may take its numbers alone; the
/// other stays a hole on both sides, so no new diagnostic is reported.
#[test]
fn one_of_two_ranges_whose_words_changed_can_take_its_numbers_alone() {
    let ja = ResolvedInstructionLanguage::Ja;
    let completed = "右寄り（横2/3〜1、縦0〜1）に赤い円を置く。右下（横2/3〜1、縦2/3〜1）に橙色の小さな円を十個散らす。";
    let record = record_of(completed, ja);
    let edited = completed
        .replace("右寄り", "左寄り")
        .replace("右下", "左上");
    let base = with_completion_record(compiled(&edited, ja), &record, &[]);
    let holes = words_changed_holes(&base);
    assert_eq!(holes.len(), 2, "{:?}", base.holes);
    let candidate = validate_visible_ddl_patch(
        &base,
        &patch(&base, vec![edit(holes[1], "左上（横0〜1/3、縦0〜1/3）")]),
        &[],
        None,
        LIMITS,
    )
    .expect("one range alone");
    let left = words_changed_holes(&candidate.compilation);
    assert_eq!(left.len(), 1);
    assert!(
        candidate.document.source()[left[0].span.start_byte..left[0].span.end_byte]
            .starts_with("左寄り")
    );
}

fn record_of(source: &str, language: ResolvedInstructionLanguage) -> CompletionRangeRecord {
    CompletionRangeRecord {
        ranges: written_ranges(&compiled(source, language))
            .iter()
            .map(RecordedRange::from)
            .collect(),
    }
}

fn words_changed_holes(compilation: &inku_ddl::TypedDdlCompilation) -> Vec<&inku_ddl::TypedHole> {
    let mut holes = compilation
        .holes
        .iter()
        .filter(|hole| hole.kind == RANGE_WORDS_CHANGED_HOLE_KIND)
        .collect::<Vec<_>>();
    holes.sort_by_key(|hole| hole.span.start_byte);
    holes
}

fn compiled(source: &str, language: ResolvedInstructionLanguage) -> inku_ddl::TypedDdlCompilation {
    compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        None,
        LIMITS,
    )
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

fn assert_error_with_seed(
    base: &inku_ddl::TypedDdlCompilation,
    patch: VisibleDdlPatch,
    expected: VisiblePatchDiagnostic,
    seed: Option<u64>,
) {
    let result = validate_visible_ddl_patch(base, &patch, &[] as &[MacroDefinition], seed, LIMITS);
    assert_eq!(result.unwrap_err(), expected);
}
