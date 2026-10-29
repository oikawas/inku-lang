use inku_ddl::{
    MacroDefinition, MacroExpansionLimits, MacroInvocationResolutionDiagnosticKind, MacroLock,
    NormalizedDdlDocument, ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext,
    compile_ddl_to_score, resolve_macro_invocations,
};
use inku_score::Color;
use serde_json::Value;

#[test]
fn old_notation_is_omitted_and_the_braced_v1_word_still_draws() {
    let package: Value =
        serde_json::from_str(include_str!("fixtures/nature-leaves-2.1-v1.json")).unwrap();
    let definition =
        MacroDefinition::from_json(&package["entries"][0]["definition"].to_string()).unwrap();
    let identity = definition.identity().unwrap();
    let lock = MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap()
    .with_aliases(definition.alias_qualified_names())
    .unwrap();
    let limits = MacroExpansionLimits {
        max_invocations: 64,
        max_depth: 16,
        max_evaluation_steps: 8192,
        max_nodes_per_invocation: 128,
        max_total_nodes: 128,
    };
    for (source, language, braced) in [
        (
            "Nature.若葉。\n｛若葉｝。",
            ResolvedInstructionLanguage::Ja,
            "｛若葉｝。",
        ),
        (
            "Nature.YoungLeaves.\n{young leaves}.",
            ResolvedInstructionLanguage::En,
            "{young leaves}.",
        ),
    ] {
        let document = NormalizedDdlDocument::new(source, language, vec![lock.clone()])
            .unwrap()
            .with_definition_names(std::slice::from_ref(&definition));
        let resolved =
            resolve_macro_invocations(&document, std::slice::from_ref(&definition)).unwrap();
        assert_eq!(
            resolved.diagnostics.len(),
            1,
            "{source}: {:?}",
            resolved.diagnostics
        );
        assert_eq!(
            resolved.diagnostics[0].kind,
            MacroInvocationResolutionDiagnosticKind::OldNotation
        );
        assert_eq!(
            &source[resolved.diagnostics[0].span.start_byte..resolved.diagnostics[0].span.end_byte],
            source.lines().next().unwrap().trim_end_matches(['。', '.'])
        );
        assert_eq!(resolved.resolved.len(), 1);
        let compile = |doc| {
            compile_ddl_to_score(
                doc,
                std::slice::from_ref(&definition),
                Some(37),
                limits,
                ScoreLoweringContext::resolve("square", Color::White).unwrap(),
                ScoreErrorPolicy::OmitAndContinue,
            )
        };
        let with_old = compile(document);
        let matching = with_old
            .upstream_diagnostics()
            .iter()
            .filter(|diagnostic| diagnostic.reason == "plugin_old_notation")
            .count();
        assert_eq!(
            matching,
            1,
            "{source}: {:?}",
            with_old.upstream_diagnostics()
        );
        let only_new =
            compile(NormalizedDdlDocument::new(braced, language, vec![lock.clone()]).unwrap());
        assert_eq!(with_old.score(), only_new.score(), "{source}");
    }
}

#[test]
fn unknown_longer_identifier_does_not_stop_at_a_locked_prefix() {
    let lock =
        MacroLock::new("Nature.Leaf", "1.0.0", format!("sha256:{}", "a".repeat(64))).unwrap();
    let text = "Nature.LeafOther.";
    let doc =
        NormalizedDdlDocument::new(text, ResolvedInstructionLanguage::En, vec![lock]).unwrap();
    let result = resolve_macro_invocations(&doc, &[]).unwrap();
    assert_eq!(result.diagnostics.len(), 1);
    assert_eq!(result.diagnostics[0].surface, "Nature.LeafOther");
    assert_eq!(
        result.diagnostics[0].kind,
        MacroInvocationResolutionDiagnosticKind::OldNotation
    );
}
