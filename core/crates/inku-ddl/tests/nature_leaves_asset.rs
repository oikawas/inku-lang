use std::collections::{BTreeMap, HashSet};

use inku_ddl::{
    MacroDefinition, MacroExpansionLimits, MacroLock, NormalizedDdlDocument,
    ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext, ScoreLoweringOutcome,
    compile_ddl_to_score,
};
use inku_score::{Color, Frequency, InkSpread, Primitive, Quality, RelationType};
use serde::Deserialize;
use serde_json::Value;

const ASSET: &str = include_str!("../assets/nature-leaves-v1.json");
/// The bundled package before draw-system04 (1.0.0 / 1.0.1 editions), which
/// saved works may still lock.
const PACKAGE_1_0: &str = include_str!("fixtures/nature-leaves-1.0-package.json");

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Package {
    schema: String,
    package_id: String,
    version: String,
    entries: Vec<Entry>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Entry {
    definition: Value,
    summaries: BTreeMap<String, String>,
}

fn canonical(alias: &str) -> &'static str {
    match alias {
        "Nature.若葉" => "Nature.YoungLeaves",
        "Nature.下草" => "Nature.Undergrowth",
        "Nature.青葉" => "Nature.SummerLeaves",
        "Nature.紅葉" => "Nature.AutumnLeaves",
        "Nature.落葉" => "Nature.FallenLeaves",
        "Nature.枯草" => "Nature.WitheredGrass",
        "Nature.枯葉" => "Nature.WitheredLeaves",
        other => panic!("no canonical name for {other}"),
    }
}

#[test]
fn bundled_nature_leaves_are_valid_bounded_definitions_that_reach_normal_score_lowering() {
    let package: Package = serde_json::from_str(ASSET).expect("Nature package must be JSON");
    assert_eq!(package.schema, "inku.bundled-macro-package.v1");
    assert_eq!(package.package_id, "Nature.leaves");
    assert_eq!(package.version, "2.0.0");
    assert_eq!(ASSET.as_bytes().last(), Some(&b'\n'));

    let expected = [
        ("Nature.若葉", "2.0.0", 12, 8..=12),
        ("Nature.下草", "2.0.0", 20, 6..=20),
        ("Nature.青葉", "2.0.0", 17, 13..=17),
        ("Nature.紅葉", "2.0.0", 15, 11..=15),
        ("Nature.落葉", "2.0.0", 24, 16..=24),
        ("Nature.枯草", "2.0.0", 20, 6..=20),
        ("Nature.枯葉", "2.0.0", 8, 4..=8),
    ];
    assert_eq!(package.entries.len(), expected.len());

    let mut definitions = Vec::new();
    let mut digests = HashSet::new();
    for (entry, (qualified_name, version, upper_bound, _)) in package.entries.iter().zip(&expected)
    {
        assert_eq!(
            entry
                .summaries
                .keys()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            ["en", "ja"]
        );
        assert!(entry.summaries.values().all(|summary| !summary.is_empty()));
        let definition = MacroDefinition::from_json(&entry.definition.to_string())
            .unwrap_or_else(|error| panic!("{qualified_name}: {error}"));
        let validation = definition.validate();
        assert!(
            validation.is_valid(),
            "{qualified_name}: {:?}",
            validation
                .diagnostics()
                .iter()
                .map(|diagnostic| (diagnostic.code(), diagnostic.path()))
                .collect::<Vec<_>>()
        );
        assert_eq!(validation.symbolic_upper_bound(), Some(*upper_bound));
        let identity = definition.identity().unwrap();
        // The English heading is canonical; the Japanese name is its alias.
        assert_eq!(identity.qualified_name(), canonical(qualified_name));
        assert_eq!(definition.alias_qualified_names(), [*qualified_name]);
        assert_eq!(identity.version(), *version);
        assert!(digests.insert(identity.full_digest_hex().to_owned()));
        definitions.push(definition);
    }

    let limits = MacroExpansionLimits {
        max_invocations: 64,
        max_depth: 16,
        max_evaluation_steps: 8_192,
        max_nodes_per_invocation: 128,
        max_total_nodes: 128,
    };
    for (definition, (qualified_name, _, _, instruction_range)) in definitions.iter().zip(&expected)
    {
        let identity = definition.identity().unwrap();
        let lock = MacroLock::new(
            identity.qualified_name(),
            identity.version(),
            format!("sha256:{}", identity.full_digest_hex()),
        )
        .unwrap()
        .with_aliases(definition.alias_qualified_names())
        .unwrap();
        let canonical_source = format!("{}.", identity.qualified_name());
        let (source, language) = if *qualified_name == "Nature.若葉" {
            (canonical_source.as_str(), ResolvedInstructionLanguage::En)
        } else {
            (*qualified_name, ResolvedInstructionLanguage::Ja)
        };
        let execution = compile_ddl_to_score(
            NormalizedDdlDocument::new(source, language, vec![lock]).unwrap(),
            &definitions,
            Some(37),
            limits,
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            None,
            ScoreErrorPolicy::Stop,
        );
        assert_eq!(
            execution.outcome(),
            ScoreLoweringOutcome::Complete,
            "{qualified_name}: upstream={:?}, downstream={:?}",
            execution.upstream_diagnostics(),
            execution.downstream_diagnostics()
        );
        assert!(
            execution.upstream_diagnostics().is_empty(),
            "{qualified_name}"
        );
        assert!(
            execution.downstream_diagnostics().is_empty(),
            "{qualified_name}"
        );
        let score = execution.score().unwrap();
        assert!(
            instruction_range.contains(&score.instructions.len()),
            "{qualified_name}: {} instructions",
            score.instructions.len()
        );

        let touching = score
            .instructions
            .iter()
            .filter(|instruction| {
                instruction.relation.as_ref().is_some_and(|relation| {
                    relation.kind == RelationType::Touching
                        && instruction.primitive == Primitive::Arc
                })
            })
            .count();
        assert!(
            touching > 0,
            "{qualified_name}: missing two-arc leaf relation"
        );
        if matches!(
            *qualified_name,
            "Nature.下草" | "Nature.紅葉" | "Nature.枯草"
        ) {
            assert!(!execution.anchor_origins().is_empty(), "{qualified_name}");
        }
        assert!(
            score
                .instructions
                .iter()
                .filter(|instruction| {
                    matches!(instruction.primitive, Primitive::Arc | Primitive::Cloudform)
                })
                .all(|instruction| instruction.filled),
            "{qualified_name}: every leaf requests its interior fill"
        );
        if *qualified_name == "Nature.青葉" {
            let branch = &score.instructions[0];
            assert_eq!(branch.primitive, Primitive::Line);
            assert_eq!(branch.color, Color::Gray);
            assert_eq!(branch.weight, inku_score::Weight::BrushThick);
            let variation = branch.variation.as_ref().expect("undulating branch");
            assert_eq!(variation.frequency, inku_score::Frequency::Slow);
            assert_eq!(variation.quality, inku_score::Quality::Wave);
            let path_connections = score
                .instructions
                .iter()
                .filter(|instruction| {
                    instruction.relation.as_ref().is_some_and(|relation| {
                        relation.kind == RelationType::Connected
                            && relation.target_instruction_index == Some(0)
                            && relation.target_path_position.is_some()
                    })
                })
                .count();
            assert!((6..=8).contains(&path_connections));
            assert!(score.instructions[1..].iter().all(|instruction| {
                instruction.color == Color::Green
                    && instruction.weight == inku_score::Weight::BrushThin
                    && instruction.filled
            }));
        }
        if *qualified_name == "Nature.枯葉" {
            // Curled withered leaves: a deep and a shallow chalk arc, gray and yellow in turn.
            for (leaf_index, pair) in score.instructions.chunks_exact(2).enumerate() {
                let expected_color = if leaf_index % 2 == 0 {
                    Color::Gray
                } else {
                    Color::Yellow
                };
                assert!(pair.iter().all(|instruction| {
                    instruction.primitive == Primitive::Arc
                        && instruction.color == expected_color
                        && instruction.weight == inku_score::Weight::Chalk
                }));
            }
        }
        if *qualified_name == "Nature.落葉" {
            for (leaf_index, pair) in score.instructions.chunks_exact(2).enumerate() {
                let expected_color = if leaf_index % 2 == 0 {
                    Color::Red
                } else {
                    Color::Gray
                };
                assert!(
                    pair.iter()
                        .all(|instruction| instruction.color == expected_color)
                );
                assert!(pair.iter().all(|instruction| {
                    instruction.variation.is_none()
                        && instruction.ink_spread == Some(InkSpread::Bleed)
                }));
            }
        }
        if matches!(*qualified_name, "Nature.若葉" | "Nature.枯葉") {
            assert!(score.instructions.iter().all(|instruction| {
                instruction
                    .variation
                    .as_ref()
                    .is_some_and(|variation| variation.quality == Quality::Perlin)
            }));
        }
        if *qualified_name == "Nature.枯草" {
            assert!(score.instructions.iter().all(|instruction| {
                instruction.ink_spread == Some(InkSpread::Bleed)
                    && instruction.variation.as_ref().is_some_and(|variation| {
                        variation.frequency == Frequency::High
                            && variation.quality == Quality::Perlin
                    })
            }));
        }
    }
}

#[test]
fn saved_retired_fluctuation_definitions_keep_their_v1_locks_and_meaning() {
    let package: Package = serde_json::from_str(PACKAGE_1_0).expect("1.0 package must be JSON");
    let mut wakaba = package.entries[0].definition.clone();
    wakaba["version"] = Value::String("1.0.0".to_owned());
    wakaba["components"]["leaf_form"]["body"][0]["fields"]["fluctuation_quality"]["id"] =
        Value::String("trembling".to_owned());
    wakaba["components"]["leaf_form"]["body"][1]["fields"]["fluctuation_quality"]["id"] =
        Value::String("trembling".to_owned());

    let mut kareha = package.entries[6].definition.clone();
    kareha["version"] = Value::String("1.0.0".to_owned());
    kareha["body"][0]["body"][0]["body"][0]["body"][0]["body"][0]["fields"]["fluctuation_quality"]
        ["id"] = Value::String("trembling".to_owned());

    let mut ochiba = package.entries[4].definition.clone();
    ochiba["version"] = Value::String("1.0.0".to_owned());
    for edge in 0..2 {
        let fields = ochiba["components"]["fallen_leaf"]["body"][edge]["fields"]
            .as_object_mut()
            .unwrap();
        fields.remove("ink_spread");
        fields.insert(
            "fluctuation_quality".to_owned(),
            serde_json::json!({
                "expr": "semantic_ref",
                "category": "variation",
                "id": "blurring"
            }),
        );
    }

    let mut karekusa = package.entries[5].definition.clone();
    karekusa["version"] = Value::String("1.0.0".to_owned());
    for edge in 0..2 {
        let fields = karekusa["components"]["rooted_blade"]["body"][1]["body"][edge]["fields"]
            .as_object_mut()
            .unwrap();
        fields.remove("ink_spread");
        fields.insert(
            "fluctuation_quality".to_owned(),
            serde_json::json!({
                "expr": "semantic_ref",
                "category": "variation",
                "id": "blurring"
            }),
        );
    }

    let cases = [
        (
            "Nature.若葉.",
            ResolvedInstructionLanguage::En,
            wakaba,
            "572f04f5b127e660a6d4876fa9eed344bd31e675b7d06da5c69d93a64c850e95",
            Quality::Perlin,
        ),
        (
            "Nature.落葉",
            ResolvedInstructionLanguage::Ja,
            ochiba,
            "81f36ea2703757cee78205b0bec2721e0a519fc0399000f2c41944583e608661",
            Quality::Pink,
        ),
        (
            "Nature.枯草",
            ResolvedInstructionLanguage::Ja,
            karekusa,
            "0d3a6f2316cec02e20322f9e9db43affb540a523e57c38ed1ae4729a47393b92",
            Quality::Pink,
        ),
        (
            "Nature.枯葉",
            ResolvedInstructionLanguage::Ja,
            kareha,
            "710c6ebb21cc6d1271dca9fa0922f2f8e9f377d70ff885adb033f69036bdf9b5",
            Quality::Perlin,
        ),
    ];
    let limits = MacroExpansionLimits {
        max_invocations: 64,
        max_depth: 16,
        max_evaluation_steps: 8_192,
        max_nodes_per_invocation: 128,
        max_total_nodes: 128,
    };

    for (source, language, value, expected_digest, expected_quality) in cases {
        let definition = MacroDefinition::from_json(&value.to_string()).unwrap();
        let identity = definition.identity().unwrap();
        assert_eq!(identity.version(), "1.0.0");
        assert_eq!(identity.full_digest_hex(), expected_digest);
        let lock = MacroLock::new(
            identity.qualified_name(),
            identity.version(),
            format!("sha256:{expected_digest}"),
        )
        .unwrap();
        let execution = compile_ddl_to_score(
            NormalizedDdlDocument::new(source, language, vec![lock]).unwrap(),
            std::slice::from_ref(&definition),
            Some(37),
            limits,
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            None,
            ScoreErrorPolicy::Stop,
        );
        assert_eq!(execution.outcome(), ScoreLoweringOutcome::Complete);
        assert!(execution.upstream_diagnostics().is_empty());
        assert!(execution.downstream_diagnostics().is_empty());
        assert!(
            execution
                .score()
                .unwrap()
                .instructions
                .iter()
                .all(|instruction| {
                    instruction.ink_spread.is_none()
                        && instruction
                            .variation
                            .as_ref()
                            .is_some_and(|variation| variation.quality == expected_quality)
                })
        );
    }
}

#[test]
fn a_saved_cloudform_kareha_keeps_its_lock_and_meaning() {
    let package: Package = serde_json::from_str(PACKAGE_1_0).expect("1.0 package must be JSON");
    let definition =
        MacroDefinition::from_json(&package.entries[6].definition.to_string()).unwrap();
    let identity = definition.identity().unwrap();
    assert_eq!(identity.version(), "1.0.1");
    assert_eq!(
        identity.full_digest_hex(),
        "1ceac898eb3b3f5478f8cf6cb8661eae7c4fc40a0a871e10cfeac64b02fafdf5"
    );
    let lock = MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap();
    let execution = compile_ddl_to_score(
        NormalizedDdlDocument::new("Nature.枯葉", ResolvedInstructionLanguage::Ja, vec![lock])
            .unwrap(),
        std::slice::from_ref(&definition),
        Some(37),
        MacroExpansionLimits {
            max_invocations: 64,
            max_depth: 16,
            max_evaluation_steps: 8_192,
            max_nodes_per_invocation: 128,
            max_total_nodes: 128,
        },
        ScoreLoweringContext::resolve("square", Color::White).unwrap(),
        None,
        ScoreErrorPolicy::Stop,
    );
    assert_eq!(execution.outcome(), ScoreLoweringOutcome::Complete);
    let instructions = &execution.score().unwrap().instructions;
    assert!((2..=4).contains(&instructions.len()));
    assert!(
        instructions
            .iter()
            .all(|instruction| instruction.primitive == Primitive::Cloudform)
    );
}

#[test]
fn every_saved_1_0_edition_keeps_its_lock_and_still_expands() {
    let package: Package = serde_json::from_str(PACKAGE_1_0).expect("1.0 package must be JSON");
    assert_eq!(package.version, "1.0.1");
    let current: Package = serde_json::from_str(ASSET).expect("Nature package must be JSON");
    for (old, new) in package.entries.iter().zip(&current.entries) {
        let definition = MacroDefinition::from_json(&old.definition.to_string()).unwrap();
        let identity = definition.identity().unwrap();
        let replacement = MacroDefinition::from_json(&new.definition.to_string()).unwrap();
        // Every word changed; a saved lock must never silently pick up the new edition.
        assert_ne!(
            identity.full_digest_hex(),
            replacement.identity().unwrap().full_digest_hex(),
            "{}",
            identity.qualified_name()
        );
        let lock = MacroLock::new(
            identity.qualified_name(),
            identity.version(),
            format!("sha256:{}", identity.full_digest_hex()),
        )
        .unwrap();
        let execution = compile_ddl_to_score(
            NormalizedDdlDocument::new(
                identity.qualified_name(),
                ResolvedInstructionLanguage::Ja,
                vec![lock],
            )
            .unwrap(),
            std::slice::from_ref(&definition),
            Some(37),
            MacroExpansionLimits {
                max_invocations: 64,
                max_depth: 16,
                max_evaluation_steps: 8_192,
                max_nodes_per_invocation: 128,
                max_total_nodes: 128,
            },
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            None,
            ScoreErrorPolicy::Stop,
        );
        assert_eq!(
            execution.outcome(),
            ScoreLoweringOutcome::Complete,
            "{}",
            identity.qualified_name()
        );
    }
}

#[test]
fn a_bundled_word_draws_the_same_score_by_its_canonical_name_or_its_alias() {
    let package: Package = serde_json::from_str(ASSET).expect("Nature package must be JSON");
    let definitions = package
        .entries
        .iter()
        .map(|entry| MacroDefinition::from_json(&entry.definition.to_string()).unwrap())
        .collect::<Vec<_>>();
    let locks = definitions
        .iter()
        .map(|definition| {
            let identity = definition.identity().unwrap();
            MacroLock::new(
                identity.qualified_name(),
                identity.version(),
                format!("sha256:{}", identity.full_digest_hex()),
            )
            .unwrap()
            .with_aliases(definition.alias_qualified_names())
            .unwrap()
        })
        .collect::<Vec<_>>();
    let limits = MacroExpansionLimits {
        max_invocations: 64,
        max_depth: 16,
        max_evaluation_steps: 8_192,
        max_nodes_per_invocation: 128,
        max_total_nodes: 128,
    };
    let score = |source: &str, language| {
        let execution = compile_ddl_to_score(
            NormalizedDdlDocument::new(source, language, locks.clone()).unwrap(),
            &definitions,
            Some(37),
            limits,
            ScoreLoweringContext::resolve("square", Color::White).unwrap(),
            None,
            ScoreErrorPolicy::Stop,
        );
        assert_eq!(
            execution.outcome(),
            ScoreLoweringOutcome::Complete,
            "{source}"
        );
        assert!(execution.upstream_diagnostics().is_empty(), "{source}");
        serde_json::to_value(execution.score().unwrap()).unwrap()
    };
    for definition in &definitions {
        let canonical = definition.qualified_name().unwrap();
        let alias = &definition.alias_qualified_names()[0];
        let by_alias = score(
            &format!("背景を白で埋める。\n{alias}。"),
            ResolvedInstructionLanguage::Ja,
        );
        assert_eq!(
            score(
                &format!("背景を白で埋める。\n{canonical}。"),
                ResolvedInstructionLanguage::Ja
            ),
            by_alias,
            "{canonical}"
        );
        assert_eq!(
            score(
                &format!("Fill the background with white.\n{canonical}."),
                ResolvedInstructionLanguage::En
            )["instructions"],
            by_alias["instructions"],
            "{canonical}"
        );
    }
    // An alias that repeats the heading or names another namespace's form is refused.
    let mut bad = package.entries[0].definition.clone();
    bad["aliases"] = serde_json::json!(["YoungLeaves"]);
    assert!(
        !MacroDefinition::from_json(&bad.to_string())
            .unwrap()
            .validate()
            .is_valid()
    );
    bad["aliases"] = serde_json::json!(["若 葉"]);
    assert!(
        !MacroDefinition::from_json(&bad.to_string())
            .unwrap()
            .validate()
            .is_valid()
    );
}

#[test]
fn every_bundled_word_expands_without_omission_at_many_placement_seeds() {
    let package: Package = serde_json::from_str(ASSET).expect("Nature package must be JSON");
    let definitions = package
        .entries
        .iter()
        .map(|entry| MacroDefinition::from_json(&entry.definition.to_string()).unwrap())
        .collect::<Vec<_>>();
    let limits = MacroExpansionLimits {
        max_invocations: 64,
        max_depth: 16,
        max_evaluation_steps: 8_192,
        max_nodes_per_invocation: 128,
        max_total_nodes: 128,
    };
    for definition in &definitions {
        let identity = definition.identity().unwrap();
        let lock = MacroLock::new(
            identity.qualified_name(),
            identity.version(),
            format!("sha256:{}", identity.full_digest_hex()),
        )
        .unwrap();
        // Every count and slot a vary can choose must stay inside the canvas.
        for seed in 0..32 {
            let execution = compile_ddl_to_score(
                NormalizedDdlDocument::new(
                    identity.qualified_name(),
                    ResolvedInstructionLanguage::Ja,
                    vec![lock.clone()],
                )
                .unwrap(),
                &definitions,
                Some(seed),
                limits,
                ScoreLoweringContext::resolve("square", Color::White).unwrap(),
                None,
                ScoreErrorPolicy::Stop,
            );
            assert_eq!(
                execution.outcome(),
                ScoreLoweringOutcome::Complete,
                "{} at seed {seed}: {:?}",
                identity.qualified_name(),
                execution.downstream_diagnostics()
            );
        }
    }
}
