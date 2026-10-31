//! Saijiki v3 migration and compiler contracts, independent of rendering style.
use inku_ddl::{
    MacroDefinition, MacroExpansionLimits, NormalizedDdlDocument,
    ResolvedInstructionLanguage as Lang, SAIJIKI_ASSET_ID, SAIJIKI_V1_ASSET_ID,
    SAIJIKI_V2_ASSET_ID, ScoreErrorPolicy, ScoreLoweringContext, ScoreLoweringOutcome,
    compile_ddl_to_score, migrate_document_from_saijiki_v1, migrate_document_from_saijiki_v2,
    migrate_macro_definition_from_saijiki_v2,
};
use inku_score::{Color, Weight};
use serde_json::{Value, json};

fn doc(source: &str, language: Lang) -> NormalizedDdlDocument {
    NormalizedDdlDocument::new(source, language, vec![]).unwrap()
}

#[test]
fn v2_document_migrates_all_six_tools_and_width_steps_in_both_languages() {
    // Each row is [extra-fine, fine, unspecified, thick, extra-thick].
    let tools = [
        ("細筆", "fine-brush", "ガッシュ", "gouache", [0, 1, 2, 3, 4]),
        (
            "太筆",
            "thick-brush",
            "ガッシュ",
            "gouache",
            [2, 2, 3, 4, 4],
        ),
        ("ロットリング", "rotring", "ペン", "pen", [0, 0, 1, 2, 4]),
        ("クレヨン", "crayon", "チョーク", "chalk", [1, 2, 2, 3, 4]),
        (
            "ビュラン",
            "burin",
            "エッチング",
            "etching",
            [0, 1, 3, 3, 4],
        ),
        (
            "ドライポイント",
            "drypoint",
            "エッチング",
            "etching",
            [0, 1, 2, 3, 4],
        ),
    ];
    let ja = ["ごく細い", "細い", "", "太い", "ごく太い"];
    let en = ["extra-fine ", "thin ", "", "thick ", "extra-thick "];
    for (old_ja, old_en, new_ja, new_en, map) in tools {
        for i in 0..5 {
            let before = format!("黒い{}{old_ja}の線を引く。", ja[i]);
            let after = format!("黒い{}{new_ja}の線を引く。", ja[map[i]]);
            let actual = migrate_document_from_saijiki_v2(&doc(&before, Lang::Ja)).unwrap();
            assert_eq!(actual.source, after, "{before}");
            assert!(actual.unassociated_tools.is_empty(), "{before}");
            let before = format!("Draw a {}{old_en} line.", en[i]);
            let after = format!("Draw a {}{new_en} line.", en[map[i]]);
            let actual = migrate_document_from_saijiki_v2(&doc(&before, Lang::En)).unwrap();
            assert_eq!(actual.source, after, "{before}");
            assert!(actual.unassociated_tools.is_empty(), "{before}");
        }
    }
}

#[test]
fn sequence_reports_unassociated_tool_and_v1_also_reaches_v3() {
    let source = "鉛筆と太筆を交互にして、線を五本並べる。";
    let result = migrate_document_from_saijiki_v2(&doc(source, Lang::Ja)).unwrap();
    assert_eq!(
        result.source,
        "鉛筆とガッシュを交互にして、線を五本並べる。"
    );
    assert_eq!(result.unassociated_tools.len(), 1);
    let span = result.unassociated_tools[0];
    assert_eq!(&result.source[span.start_byte..span.end_byte], "ガッシュ");
    let result =
        migrate_document_from_saijiki_v1(&doc("太筆の薄墨の線を引く。", Lang::Ja)).unwrap();
    assert_eq!(result.source, "太いガッシュの薄い刷きの線を引く。");
}

fn definition(touch: Value) -> Value {
    json!({"schema":"inku.macro-definition.v1","namespace":"Saved","heading":"Mark","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"line"},"movement":{"expr":"semantic_ref","category":"movement","id":"place"},"touch":touch}}]})
}
fn tool(id: &str) -> Value {
    json!({"expr":"semantic_ref","category":"touch","id":id})
}

#[test]
fn v2_definition_migrates_direct_tools_and_is_idempotent() {
    for (old, new, thin) in [
        ("brush_thick", "gouache", Some("thick")),
        ("rotring", "pen", Some("fine")),
        ("crayon", "chalk", None),
    ] {
        let m = migrate_macro_definition_from_saijiki_v2(&definition(tool(old))).unwrap();
        assert!(m.changed, "{old}");
        assert_eq!(m.definition["body"][0]["fields"]["touch"]["id"], new);
        assert_eq!(
            m.definition["body"][0]["fields"]
                .get("thinness")
                .and_then(|v| v["id"].as_str()),
            thin
        );
        assert!(m.unadjusted_thinness.is_empty());
        let again = migrate_macro_definition_from_saijiki_v2(&m.definition).unwrap();
        assert!(!again.changed);
        assert_eq!(again.definition, m.definition);
    }
    let current = migrate_macro_definition_from_saijiki_v2(&definition(tool("gouache"))).unwrap();
    assert!(!current.changed);
}

#[test]
fn a_saved_definition_is_identified_as_its_retired_edition_locked_it() {
    // The bundled 1.0 leaves, with the digests the cores of each edition computed for them:
    // 下草 by the v2 core (main 783fd7a81, render engine 94), 若葉 by the v1 core (7ba01022).
    let package: Value =
        serde_json::from_str(include_str!("fixtures/nature-leaves-1.0-package.json")).unwrap();
    let saved = |heading: &str| {
        let entry = package["entries"]
            .as_array()
            .unwrap()
            .iter()
            .find(|entry| entry["definition"]["heading"] == heading)
            .unwrap();
        MacroDefinition::from_json(&entry["definition"].to_string()).unwrap()
    };
    let digest = |definition: &MacroDefinition, edition: &str| {
        definition
            .identity_in_retired_saijiki(edition)
            .map(|identity| identity.full_digest_hex().to_owned())
    };
    let undergrowth = saved("下草");
    // Its retired tools are not current words, so it has no current identity.
    assert!(undergrowth.identity().is_err());
    assert_eq!(
        digest(&undergrowth, SAIJIKI_V2_ASSET_ID).as_deref(),
        Some("88046b24987a2600eeb8b985f36bc15222202a5758a0f4a7638e514dd6af2aea")
    );
    let young_leaves = saved("若葉");
    assert_eq!(
        digest(&young_leaves, SAIJIKI_V1_ASSET_ID).as_deref(),
        Some("82ffc5c348a82ba927b315acaaa5ce4bc4c3998e2497deecd91535fb3005c8f4")
    );
    // A v1 word the v2 edition no longer read leaves no v2 identity, and only a retired
    // edition is read this way.
    assert_eq!(digest(&young_leaves, SAIJIKI_V2_ASSET_ID), None);
    assert_eq!(digest(&undergrowth, SAIJIKI_ASSET_ID), None);
}

#[test]
fn a_definition_tool_sequence_keeps_width_unspecified_and_reports_the_emit() {
    let sequence = json!({"expr":"cycle","index":{"expr":"integer","value":0},"items":[tool("pencil"),tool("brush_thick")]});
    let migrated = migrate_macro_definition_from_saijiki_v2(&definition(sequence)).unwrap();
    assert!(migrated.changed);
    let fields = &migrated.definition["body"][0]["fields"];
    assert_eq!(fields["touch"]["items"][1]["id"], "gouache");
    assert!(fields.get("thinness").is_none());
    assert_eq!(migrated.unadjusted_thinness, ["$.body[0].fields"]);
}

fn compile(source: &str) -> inku_ddl::CompilerExecutionResult {
    compile_ddl_to_score(
        doc(source, Lang::En),
        &[],
        Some(37),
        MacroExpansionLimits {
            max_invocations: 8,
            max_depth: 8,
            max_evaluation_steps: 512,
            max_nodes_per_invocation: 64,
            max_total_nodes: 128,
        },
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        ScoreErrorPolicy::Stop,
    )
}

#[test]
fn new_tools_and_english_aliases_compile_to_v024_while_older_tools_keep_their_edition() {
    for (word, weight) in [
        ("gouache", Weight::Gouache),
        ("watercolor", Weight::Watercolor),
        ("watercolour", Weight::Watercolor),
        ("oil pastel", Weight::OilPastel),
        ("oil-pastel", Weight::OilPastel),
        ("painting knife", Weight::PaintingKnife),
        ("painting-knife", Weight::PaintingKnife),
        ("etching", Weight::Etching),
    ] {
        let source = format!("Draw one black {word} line at center.");
        let result = compile(&source);
        assert_eq!(
            result.outcome(),
            ScoreLoweringOutcome::Complete,
            "{source}: {:?}",
            result.upstream_diagnostics()
        );
        let score = result.score().unwrap();
        assert_eq!(score.version, "0.24.0", "{source}");
        assert_eq!(score.instructions[0].weight, weight, "{source}");
    }
    let result = compile("Draw one black pencil line at center.");
    assert_eq!(result.outcome(), ScoreLoweringOutcome::Complete);
    assert_ne!(result.score().unwrap().version, "0.24.0");
}
