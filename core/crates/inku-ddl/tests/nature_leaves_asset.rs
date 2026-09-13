use std::collections::{BTreeMap, HashSet};

use inku_ddl::{
    MacroDefinition, MacroExpansionLimits, MacroLock, NormalizedDdlDocument,
    ResolvedInstructionLanguage, ScoreErrorPolicy, ScoreLoweringContext, ScoreLoweringOutcome,
    compile_ddl_to_score,
};
use inku_score::{Color, Primitive, RelationType};
use serde::Deserialize;
use serde_json::Value;

const ASSET: &str = include_str!("../assets/nature-leaves-v1.json");

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

#[test]
fn bundled_nature_leaves_are_valid_bounded_definitions_that_reach_normal_score_lowering() {
    let package: Package = serde_json::from_str(ASSET).expect("Nature package must be JSON");
    assert_eq!(package.schema, "inku.bundled-macro-package.v1");
    assert_eq!(package.package_id, "Nature.leaves");
    assert_eq!(package.version, "1.0.0");
    assert_eq!(ASSET.as_bytes().last(), Some(&b'\n'));

    let expected = [
        ("Nature.若葉", 12, 8..=12),
        ("Nature.下草", 20, 6..=20),
        ("Nature.紅葉", 15, 11..=15),
        ("Nature.落葉", 20, 20..=20),
        ("Nature.枯草", 20, 6..=20),
        ("Nature.枯葉", 4, 2..=4),
    ];
    assert_eq!(package.entries.len(), expected.len());

    let mut definitions = Vec::new();
    let mut digests = HashSet::new();
    for (entry, (qualified_name, upper_bound, _)) in package.entries.iter().zip(&expected) {
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
        assert_eq!(identity.qualified_name(), *qualified_name);
        assert_eq!(identity.version(), "1.0.0");
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
    for (definition, (qualified_name, _, instruction_range)) in definitions.iter().zip(&expected) {
        let identity = definition.identity().unwrap();
        let lock = MacroLock::new(
            identity.qualified_name(),
            identity.version(),
            format!("sha256:{}", identity.full_digest_hex()),
        )
        .unwrap();
        let (source, language) = if *qualified_name == "Nature.若葉" {
            ("Nature.若葉.", ResolvedInstructionLanguage::En)
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
        if *qualified_name == "Nature.枯葉" {
            assert_eq!(touching, 0);
            assert!(
                score
                    .instructions
                    .iter()
                    .all(|instruction| instruction.primitive == Primitive::Cloudform)
            );
        } else {
            assert!(
                touching > 0,
                "{qualified_name}: missing two-arc leaf relation"
            );
        }
        if matches!(
            *qualified_name,
            "Nature.下草" | "Nature.紅葉" | "Nature.枯草"
        ) {
            assert!(!execution.anchor_origins().is_empty(), "{qualified_name}");
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
            }
        }
    }
}
