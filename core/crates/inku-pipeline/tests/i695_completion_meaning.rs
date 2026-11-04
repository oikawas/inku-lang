//! I-695: freeze current outcomes, including false acceptance. No provider is called.
#![allow(dead_code)]
// Include the unchanged module so this integration test can exercise its
// crate-private single-unit guard without exporting or changing product code.
#[path = "../src/hole_completion.rs"]
mod hole_completion;

use inku_ddl::{
    MacroExpansionLimits, NormalizedDdlDocument, ResolvedInstructionLanguage as Lang,
    SemanticDeliveryKind, TypedDdlCompilation, VisibleDdlPatch, VisibleDdlPatchEdit,
    VisiblePatchDiagnostic, collect_attachment_evidence, compile_typed_ddl,
    validate_visible_ddl_patch_detailed,
};

const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 16,
    max_depth: 16,
    max_evaluation_steps: 1000,
    max_nodes_per_invocation: 100,
    max_total_nodes: 500,
};

fn compile(source: &str, lang: Lang) -> TypedDdlCompilation {
    compile_typed_ddl(
        NormalizedDdlDocument::new(source, lang, Vec::new()).unwrap(),
        &[],
        None,
        LIMITS,
    )
}

fn check(
    id: &str,
    lang: Lang,
    source: &str,
    replacement: &str,
    unread: &str,
    expected: Result<(), VisiblePatchDiagnostic>,
) {
    let base = compile(source, lang);
    let holes: Vec<_> = base
        .holes
        .iter()
        .filter(|h| h.kind == "unresolved_clause")
        .collect();
    assert_eq!(holes.len(), 1, "{id}: {:?}", base.holes);
    let hole = holes[0];
    let unknown = hole_completion::unread_words(&base, hole.allowed_span);
    assert!(
        unknown.iter().any(|s| s.contains(unread)),
        "{id}: {unknown:?}"
    );
    let lock = base.compiler_lock.as_ref().unwrap();
    let patch = VisibleDdlPatch::new(
        lock.visible_source_digest.clone(),
        lock.full_digest.clone(),
        vec![VisibleDdlPatchEdit {
            hole_id: hole.id.clone(),
            allowed_span: hole.allowed_span,
            expected_range_digest: hole.expected_range_digest.clone(),
            replacement: replacement.into(),
        }],
    );
    let merged = format!(
        "{}{}{}",
        &source[..hole.allowed_span.start_byte],
        replacement,
        &source[hole.allowed_span.end_byte..]
    );
    let candidate = compile(&merged, lang);
    let guard = hole_completion::standalone_repair_preserves_namespace(&base, &candidate, hole);
    let result = validate_visible_ddl_patch_detailed(&base, &patch, &[], None, LIMITS);
    let observed = result.as_ref().map(|_| ()).map_err(|e| e.diagnostic);
    assert_eq!(observed, expected, "{id}");
    assert!(guard, "{id}: standalone namespace guard rejected");
    let semantic = base.semantic_document.as_ref().unwrap();
    let atoms = &semantic
        .instruction_association
        .association
        .clause_stream
        .clauses;
    let attachment = collect_attachment_evidence(&base.document).unwrap();
    let deliveries: Vec<_> = candidate
        .deliveries
        .iter()
        .filter(|d| d.kind == SemanticDeliveryKind::Explicit)
        .collect();
    println!(
        "CASE {id}\nSOURCE {source}\nPROPOSAL {merged}\nHOLE {hole:?}\nUNREAD {unknown:?}\nATOMS {atoms:?}\nATTACHMENT {:?}\nCANDIDATE_EXPLICIT {deliveries:?}\nRESULT {observed:?}; standalone={guard}",
        attachment.evidence
    );
}

#[test]
fn i695_current_deletion_ja_en() {
    check(
        "ja-delete",
        Lang::Ja,
        "謎めいた青い線を中心に置く。",
        "青い線を中心に置く",
        "謎めいた",
        Ok(()),
    );
    check(
        "en-delete",
        Lang::En,
        "place one enigmatic blue line at center.",
        "place one blue line at center",
        "enigmatic",
        Ok(()),
    );
}

#[test]
fn i695_current_distribution_to_position_ja_en() {
    check(
        "ja-move",
        Lang::Ja,
        "青い線を上から下へ散らす。",
        "青い線を下に散らす",
        "上から",
        Ok(()),
    );
    check(
        "en-move",
        Lang::En,
        "scatter blue lines from top to bottom.",
        "scatter blue lines at bottom",
        "from",
        Err(VisiblePatchDiagnostic::EstablishedFactChanged),
    );
}

#[test]
fn i695_current_distribution_to_continuity_ja_en() {
    check(
        "ja-attr",
        Lang::Ja,
        "点状に青い線を中心に置く。",
        "点線の青い線を中心に置く",
        "点状に",
        Ok(()),
    );
    check(
        "en-attr",
        Lang::En,
        "scatter blue lines in dots at center.",
        "scatter dotted blue lines at center",
        "dots",
        Ok(()),
    );
}

#[test]
fn i695_current_legitimate_paraphrase_ja_en() {
    check(
        "ja-paraphrase",
        Lang::Ja,
        "ちっちゃい青い円を中心に置く。",
        "小さい青い円を中心に置く",
        "ちっちゃい",
        Ok(()),
    );
    check(
        "en-paraphrase",
        Lang::En,
        "place one tiny blue circle at center.",
        "place one small blue circle at center",
        "tiny",
        Ok(()),
    );
}

#[test]
fn i695_current_legitimate_word_order_ja_en() {
    check(
        "ja-order",
        Lang::Ja,
        "円 青い 小さい を中心に置く。",
        "小さい青い円を中心に置く",
        "小さい",
        Ok(()),
    );
    check(
        "en-order",
        Lang::En,
        "place one circle blue small at center.",
        "place one small blue circle at center",
        "small",
        Ok(()),
    );
}
