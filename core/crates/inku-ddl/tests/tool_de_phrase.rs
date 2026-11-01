use std::collections::BTreeMap;

use inku_ddl::{
    CompilerResourceExecutionResult, MacroExpansionLimits, NormalizedDdlDocument,
    ResolvedInstructionLanguage as Language, ScoreErrorPolicy, ScoreLoweringContext,
    ScoreLoweringOutcome, compile_ddl_to_score_with_resources,
};
use inku_score::{
    Color, HardResourcePolicy, OperationalResourceBudget, ResourceBudget, ResourceDemand,
};

fn compile(source: &str, language: Language) -> CompilerResourceExecutionResult {
    let budget = ResourceBudget {
        maximum: ResourceDemand {
            logical_objects: 4096,
            primitive_marks: 400,
            object_templates: 64,
            maximum_per_template_primitive_marks: 240,
            maximum_resolved_count: 2000,
            template_nodes: 128,
            anchor_instances: 4096,
            transform_instances: 4096,
            placement_instances: 64,
            fill_instances: 64,
        },
    };
    let colors: BTreeMap<String, String> = [
        ("white", "#ffffff"),
        ("black", "#111111"),
        ("gray", "#888888"),
        ("red", "#a2342a"),
        ("orange", "#b9671e"),
        ("yellow", "#b8901f"),
        ("green", "#2f6b3a"),
        ("blue", "#2c3e91"),
        ("purple", "#6a4d94"),
        ("palette:Black", "#111111"),
        ("palette:White", "#ffffff"),
        ("palette:Gray", "#888888"),
        ("palette:Red", "#a2342a"),
        ("palette:Green", "#2f6b3a"),
        ("palette:Blue", "#2c3e91"),
        ("palette:Yellow", "#b8901f"),
        ("palette:Orange", "#b9671e"),
        ("palette:Purple", "#6a4d94"),
        ("palette:Deep Red", "#7c2f26"),
    ]
    .into_iter()
    .map(|(k, v)| (k.into(), v.into()))
    .collect();
    let palette =
        inku_render::palette::work_palette_context(&colors, None, Some("default"), Color::White)
            .unwrap();
    compile_ddl_to_score_with_resources(
        NormalizedDdlDocument::new(source, language, vec![]).unwrap(),
        &[],
        Some(0),
        MacroExpansionLimits {
            max_invocations: 16,
            max_depth: 16,
            max_evaluation_steps: 1000,
            max_nodes_per_invocation: 100,
            max_total_nodes: 500,
        },
        ScoreLoweringContext::resolve_with_palette("square", Color::White, palette).unwrap(),
        ScoreErrorPolicy::OmitAndContinue,
        HardResourcePolicy {
            identity: "probe.v1".into(),
            budget,
        },
        OperationalResourceBudget(budget),
    )
}

#[test]
fn tool_and_color_phrases_match_noun_modifiers() {
    use Language::{En, Ja};
    let pairs = [
        (
            Ja,
            "チョークで緑の線を100本引く。",
            "チョークの緑の線を100本引く。",
        ),
        (
            Ja,
            "黒いペンで小さな四角を二百個散らす。",
            "黒いペンの小さな四角を二百個散らす。",
        ),
        (Ja, "中心に赤で円を置く。", "中心に赤い円を置く。"),
        (
            Ja,
            "灰色のガッシュで弧を五本並べる。",
            "灰色のガッシュの弧を五本並べる。",
        ),
        (
            Ja,
            "緑の線を100本チョークで引く。",
            "チョークの緑の線を100本引く。",
        ),
        (Ja, "円を赤で中心に置く。", "赤い円を中心に置く。"),
        (
            En,
            "draw 100 green lines with chalk.",
            "draw 100 green chalk lines.",
        ),
        (En, "draw a line in chalk.", "draw a chalk line."),
        (En, "draw a line in red.", "draw a red line."),
        (En, "draw a line in red chalk.", "draw a red chalk line."),
        (
            En,
            "place a circle in red at the center.",
            "place a red circle at the center.",
        ),
        (
            En,
            "With chalk, draw a green line.",
            "draw a green chalk line.",
        ),
        (En, "In red, draw a line.", "draw a red line."),
        (En, "draw a line with a chalk.", "draw a chalk line."),
        (
            En,
            "draw a line in the red chalk.",
            "draw a red chalk line.",
        ),
    ];
    let mut failures = Vec::new();
    for (language, source, reference) in pairs {
        let actual = compile(source, language);
        let expected = compile(reference, language);
        if actual.outcome() != ScoreLoweringOutcome::Complete
            || expected.outcome() != ScoreLoweringOutcome::Complete
            || actual.score() != expected.score()
        {
            failures.push(format!("{source}: actual={:?} upstream={:?} downstream={:?}; reference={:?}; score_equal={}", actual.outcome(), actual.upstream_diagnostics(), actual.downstream_diagnostics(), expected.outcome(), actual.score() == expected.score()));
        }
    }
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

#[test]
fn instrument_phrases_match_noun_modifiers_across_newline_clauses() {
    for (language, source, reference) in [
        (
            Language::Ja,
            "エッチングで雲形を散らす\nチョークで雲形を並べる",
            "エッチングの雲形を散らす\nチョークの雲形を並べる",
        ),
        (
            Language::En,
            "draw a line in red\nplace a circle with chalk at the center",
            "draw a red line\nplace a chalk circle at the center",
        ),
    ] {
        let actual = compile(source, language);
        let expected = compile(reference, language);
        assert_eq!(
            expected.outcome(),
            ScoreLoweringOutcome::Complete,
            "{reference}: {:?} {:?}",
            expected.upstream_diagnostics(),
            expected.downstream_diagnostics()
        );
        assert_eq!(
            actual.outcome(),
            ScoreLoweringOutcome::Complete,
            "{source}: {:?} {:?}",
            actual.upstream_diagnostics(),
            actual.downstream_diagnostics()
        );
        assert_eq!(actual.score(), expected.score(), "{source}");
    }
}

#[test]
fn multiple_heads_in_one_clause_still_exclude_instrument_phrase() {
    let result = compile("チョークで線と円を置く。", Language::Ja);
    assert_eq!(result.outcome(), ScoreLoweringOutcome::Stopped);
    for reason in ["ambiguous_action_ownership", "ambiguous_entity_ownership"] {
        assert!(
            result
                .upstream_diagnostics()
                .iter()
                .any(|diagnostic| diagnostic.reason == reason)
        );
    }
    assert!(
        result
            .downstream_diagnostics()
            .iter()
            .any(|diagnostic| format!("{:?}", diagnostic.reason) == "UnsupportedCoordinatedGroup")
    );
}

#[test]
fn existing_non_phrase_outcomes_are_preserved() {
    use Language::{En, Ja};
    use ScoreLoweringOutcome::{Complete, CompleteWithOmissions, Stopped};
    for (language, source, outcome) in [
        (Ja, "チョークで線と円を置く。", Stopped),
        (Ja, "チョークで。", Stopped),
        (Ja, "ペンで、赤で。", Stopped),
        (En, "In chalk, in gray.", Stopped),
        (Ja, "線を引く。チョークで。", CompleteWithOmissions),
        (Ja, "大きな四角を小さな円で埋める。", Complete),
        (Ja, "四角を円で埋める。", Complete),
        (Ja, "背景を青で埋める。", Complete),
        (En, "fill the background with blue.", Complete),
        (Ja, "赤と青で線を引く。", Stopped),
        (
            En,
            "Line up nine small squares in red, blue, green.",
            CompleteWithOmissions,
        ),
        (Ja, "中央で緑の線を引く。", CompleteWithOmissions),
        (
            Ja,
            "その点線の上に、ペンで書いた小さな四角を一つ置く。",
            CompleteWithOmissions,
        ),
    ] {
        let actual = compile(source, language);
        assert_eq!(
            actual.outcome(),
            outcome,
            "{source}: {:?} {:?}",
            actual.upstream_diagnostics(),
            actual.downstream_diagnostics()
        );
    }
}

#[test]
fn conflicts_and_coordinated_colors_keep_their_diagnostics() {
    for (source, reason, count) in [
        ("チョークでペンの線を引く。", "conflicting_touches", 1),
        ("赤で青い線を引く。", "conflicting_colors", 1),
        ("赤で赤い線を引く。", "conflicting_colors", 1),
        ("赤と青で線を引く。", "ambiguous_entity_ownership", 2),
    ] {
        let result = compile(source, Language::Ja);
        assert_eq!(
            result
                .upstream_diagnostics()
                .iter()
                .filter(|d| d.reason == reason)
                .count(),
            count,
            "{source}: {:?}",
            result.upstream_diagnostics()
        );
    }
}

#[test]
fn preserved_diagnostic_reasons_and_background() {
    for (language, source, reason, count) in [
        (
            Language::Ja,
            "チョークで線と円を置く。",
            "ambiguous_action_ownership",
            1,
        ),
        (
            Language::Ja,
            "チョークで線と円を置く。",
            "ambiguous_entity_ownership",
            1,
        ),
        (Language::Ja, "チョークで。", "missing_entity_head", 1),
        (Language::Ja, "ペンで、赤で。", "missing_entity_head", 1),
        (Language::En, "In chalk, in gray.", "missing_entity_head", 1),
        (
            Language::Ja,
            "線を引く。チョークで。",
            "missing_entity_head",
            1,
        ),
        (
            Language::Ja,
            "赤と青で線を引く。",
            "missing_left_coordination_head",
            2,
        ),
        (
            Language::En,
            "Line up nine small squares in red, blue, green.",
            "ambiguous_entity_ownership",
            3,
        ),
        (Language::Ja, "中央で緑の線を引く。", "unresolved_clause", 1),
        (
            Language::Ja,
            "その点線の上に、ペンで書いた小さな四角を一つ置く。",
            "unresolved_clause",
            1,
        ),
    ] {
        let result = compile(source, language);
        assert_eq!(
            result
                .upstream_diagnostics()
                .iter()
                .filter(|d| d.reason == reason)
                .count(),
            count,
            "{source}: {:?}",
            result.upstream_diagnostics()
        );
    }
    for (language, source) in [
        (Language::Ja, "背景を青で埋める。"),
        (Language::En, "fill the background with blue."),
    ] {
        let result = compile(source, language);
        assert_eq!(result.score().unwrap().background, Color::Blue, "{source}");
    }
}

#[test]
fn unsupported_phrase_shapes_remain_unowned() {
    for (language, source) in [
        (Language::Ja, "赤の青で線を引く。"),
        (Language::Ja, "ペンのチョークで線を引く。"),
        (Language::En, "draw a line with red."),
        (Language::En, "draw a line in red blue."),
    ] {
        let result = compile(source, language);
        assert!(
            result
                .upstream_diagnostics()
                .iter()
                .any(|d| d.reason == "ambiguous_entity_ownership"),
            "{source}: {:?}",
            result.upstream_diagnostics()
        );
    }
}

#[test]
fn accepted_phrase_has_canonical_compiler_lock() {
    let source = "チョークで緑の線を100本引く。";
    let result = inku_ddl::compile_typed_ddl(
        NormalizedDdlDocument::new(source, Language::Ja, vec![]).unwrap(),
        &[],
        Some(0),
        MacroExpansionLimits {
            max_invocations: 16,
            max_depth: 16,
            max_evaluation_steps: 1000,
            max_nodes_per_invocation: 100,
            max_total_nodes: 500,
        },
    );
    let lock = result.compiler_lock.unwrap();
    assert_eq!(lock.state, inku_ddl::CompilerLockState::CanonicalReady);
    assert!(lock.canonical_pre_expansion_digest.is_some());
    eprintln!("phrase full lock digest: {}", lock.full_digest);
}
