use std::collections::{BTreeSet, HashMap, HashSet};

use inku_ddl::{
    ExpandedMacroNode, ExpandedMacroValue, ExpansionPathSegment, GeneratedTargetId,
    MACRO_EXPANSION_SCHEMA_ID, MACRO_VARY_CHOICE_SCHEME_ID, MacroDefinition,
    MacroExpansionDiagnosticKind, MacroExpansionLimits, MacroInvocation, MacroLock, MacroSeed,
    NormalizedDdlDocument, ResolvedInstructionLanguage, bind_macro_parameters, derive_macro_seed,
    expand_macros, macro_vary_choice_hash_input,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

const FIXTURE: &str = include_str!("fixtures/macro-expansion-v1.json");
const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 16,
    max_depth: 16,
    max_evaluation_steps: 1_000,
    max_nodes_per_invocation: 100,
    max_total_nodes: 500,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Fixture {
    schema: String,
    version: u32,
    definitions: HashMap<String, Value>,
    valid_cases: Vec<ValidCase>,
    known_answers: KnownAnswers,
    diagnostic_case_ids: Vec<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ValidCase {
    id: String,
    definition: String,
    source: String,
    language: String,
    composition_seed: u64,
    expected_definition_digest: String,
    expected_seed_digests: Vec<String>,
    expected_node_kinds: Vec<String>,
    expected_node_count: usize,
    expected_nodes: Vec<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct KnownAnswers {
    all_seed_digest: String,
    repeat_zero_hash: String,
    repeat_zero_selected: u64,
    repeat_one_hash: String,
    repeat_one_selected: u64,
    different_domain_hash: String,
    different_composition_hash: String,
    typed_range_hash: String,
    typed_range_selected: u64,
}

#[test]
fn fixed_fixture_materializes_all_operators_as_closed_nodes_with_complete_provenance() {
    let fixture = load_fixture();
    for case in &fixture.valid_cases {
        let definition = definition(&fixture, &case.definition);
        let binding = binding(&definition, &case.source, &case.language);
        let accepted = binding.clone();
        let seeds = seeds(&binding, &case.source, case.composition_seed);
        let result = expand_macros(binding, &[definition.clone()], &seeds, LIMITS);

        assert_eq!(result.parameter_binding, accepted, "{}", case.id);
        assert!(
            result.diagnostics.is_empty(),
            "{}: {:?}",
            case.id,
            result.diagnostics
        );
        assert_eq!(
            result.expanded.len(),
            accepted.complete.len(),
            "{}",
            case.id
        );
        assert_eq!(
            result
                .expanded
                .iter()
                .map(|invocation| invocation.provenance.seed_full_digest.as_str())
                .collect::<Vec<_>>(),
            case.expected_seed_digests
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}",
            case.id
        );

        let flattened = result
            .expanded
            .iter()
            .flat_map(|invocation| flatten(&invocation.nodes))
            .collect::<Vec<_>>();
        assert_eq!(
            flattened.len(),
            case.expected_node_count * result.expanded.len(),
            "{}",
            case.id
        );
        if result.expanded.len() == 1 {
            assert_eq!(
                flattened
                    .iter()
                    .map(|node| node_kind(node))
                    .collect::<Vec<_>>(),
                case.expected_node_kinds
                    .iter()
                    .map(String::as_str)
                    .collect::<Vec<_>>(),
                "{}",
                case.id
            );
            assert_eq!(
                flattened
                    .iter()
                    .map(|node| node_snapshot(node))
                    .collect::<Vec<_>>(),
                case.expected_nodes,
                "{}",
                case.id
            );
        }

        for invocation in &result.expanded {
            assert_eq!(invocation.provenance.schema_id, MACRO_EXPANSION_SCHEMA_ID);
            assert_eq!(invocation.provenance.seed_scheme_id, "ddl-v1");
            assert_eq!(
                invocation.provenance.definition_full_digest, case.expected_definition_digest,
                "{}",
                case.id
            );
            assert_eq!(invocation.provenance.seed_full_digest.len(), 64);
            let nodes = flatten(&invocation.nodes);
            assert_eq!(
                nodes
                    .iter()
                    .map(|node| node.provenance().generated_ordinal)
                    .collect::<Vec<_>>(),
                (0..u64::try_from(nodes.len()).unwrap()).collect::<Vec<_>>()
            );
            for node in nodes {
                assert_eq!(node.provenance().invocation, invocation.provenance);
                assert!(!node.provenance().expansion_path.is_empty());
            }
        }

        if case.id.starts_with("all-operators") {
            assert_all_operator_targets_and_values(&result.expanded[0].nodes);
        }
        if case.id.starts_with("recursive-list") {
            let nodes = flatten(&result.expanded[0].nodes);
            match nodes[0] {
                ExpandedMacroNode::Transform { transform, .. } => {
                    assert_eq!(transform.translate_x, Some(1.0));
                }
                _ => panic!("typed fixture must start with transform"),
            }
            assert_eq!(
                selected_vary_index(nodes[1]),
                fixture.known_answers.typed_range_selected
            );
        }
        if case.id == "two-invocations-distinct-seeds" {
            assert_eq!(result.expanded.len(), 2);
            assert_ne!(
                result.expanded[0].provenance.seed_full_digest,
                result.expanded[1].provenance.seed_full_digest
            );
        }
    }
}

#[test]
fn crossed_seed_is_not_accounted_by_name_or_ordinal_alone() {
    let fixture = load_fixture();
    let empty = definition(&fixture, "empty");
    let mut other = empty.clone();
    other.heading = "Other".to_owned();
    let definitions = [empty, other];
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
        })
        .collect();
    let source = "Expand.Empty Expand.Other";
    let document =
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, locks).unwrap();
    let binding = bind_macro_parameters(&document, &definitions).unwrap();
    assert_eq!(binding.complete.len(), 2);
    let valid_seeds = seeds(&binding, source, 29);

    let normal = expand_macros(binding.clone(), &definitions, &valid_seeds, LIMITS);
    assert!(normal.diagnostics.is_empty());
    assert_eq!(normal.expanded.len(), 2);
    assert_eq!(
        normal
            .expanded
            .iter()
            .map(|expanded| expanded.provenance.definition_qualified_name.as_str())
            .collect::<Vec<_>>(),
        ["Expand.Empty", "Expand.Other"]
    );
    for (index, (expanded, seed)) in normal.expanded.iter().zip(&valid_seeds).enumerate() {
        assert_eq!(expanded.provenance.invocation_index, index);
        assert_eq!(expanded.provenance.invocation_ordinal, index as u64);
        assert_eq!(expanded.provenance.seed_full_digest, seed.full_digest_hex());
        assert_eq!(expanded.provenance.resolved_seed, seed.resolved_seed());
        assert_eq!(
            expanded.provenance.effective_composition_seed,
            seed.effective_composition_seed()
        );
    }

    let crossed = derive_macro_seed(
        source,
        &MacroInvocation::new("Expand", "Empty", 1).unwrap(),
        Some(29),
    );
    let mut seeds_with_crossed = valid_seeds;
    seeds_with_crossed.push(crossed);
    assert_global_failure(
        expand_macros(binding, &definitions, &seeds_with_crossed, LIMITS),
        MacroExpansionDiagnosticKind::MismatchedSeed,
    );
}

#[test]
fn vary_framing_paths_and_modulo_match_fixed_known_answers() {
    let fixture = load_fixture();
    assert_eq!(MACRO_VARY_CHOICE_SCHEME_ID, "inku.macro-vary-choice.v1");

    let all = fixture
        .valid_cases
        .iter()
        .find(|case| case.definition == "all")
        .unwrap();
    let all_definition = definition(&fixture, "all");
    let all_binding = binding(&all_definition, &all.source, &all.language);
    let seed = seeds(&all_binding, &all.source, all.composition_seed).remove(0);
    assert_eq!(
        seed.full_digest_hex(),
        fixture.known_answers.all_seed_digest
    );

    let path_zero = vec![
        ExpansionPathSegment::RootStatement { statement_index: 3 },
        ExpansionPathSegment::Repeat {
            statement_index: 0,
            iteration: 0,
        },
        ExpansionPathSegment::Transform { statement_index: 0 },
    ];
    let path_one = vec![
        ExpansionPathSegment::RootStatement { statement_index: 3 },
        ExpansionPathSegment::Repeat {
            statement_index: 0,
            iteration: 1,
        },
        ExpansionPathSegment::Transform { statement_index: 0 },
    ];
    assert_hash_answer(
        &seed,
        &path_zero,
        "tone_choice",
        &fixture.known_answers.repeat_zero_hash,
        2,
        fixture.known_answers.repeat_zero_selected,
    );
    assert_hash_answer(
        &seed,
        &path_one,
        "tone_choice",
        &fixture.known_answers.repeat_one_hash,
        2,
        fixture.known_answers.repeat_one_selected,
    );
    assert_hash_answer(
        &seed,
        &path_zero,
        "other_domain",
        &fixture.known_answers.different_domain_hash,
        2,
        hash_selected(&fixture.known_answers.different_domain_hash, 2),
    );

    let different_seed = derive_macro_seed(
        &all.source,
        &MacroInvocation::new("studio", "枝組.共通", 0).unwrap(),
        Some(all.composition_seed + 1),
    );
    assert_hash_answer(
        &different_seed,
        &path_zero,
        "tone_choice",
        &fixture.known_answers.different_composition_hash,
        2,
        hash_selected(&fixture.known_answers.different_composition_hash, 2),
    );
    assert_ne!(
        fixture.known_answers.repeat_zero_hash,
        fixture.known_answers.repeat_one_hash
    );
    assert_ne!(
        fixture.known_answers.repeat_zero_hash,
        fixture.known_answers.different_domain_hash
    );
    assert_ne!(
        fixture.known_answers.repeat_zero_hash,
        fixture.known_answers.different_composition_hash
    );

    let typed = fixture
        .valid_cases
        .iter()
        .find(|case| case.definition == "typed")
        .unwrap();
    let typed_definition = definition(&fixture, "typed");
    let typed_binding = binding(&typed_definition, &typed.source, &typed.language);
    let typed_seed = seeds(&typed_binding, &typed.source, typed.composition_seed).remove(0);
    let typed_path = vec![
        ExpansionPathSegment::RootStatement { statement_index: 0 },
        ExpansionPathSegment::ComponentUse {
            statement_index: 0,
            component_id: "typed".to_owned(),
        },
        ExpansionPathSegment::Transform { statement_index: 0 },
    ];
    assert_hash_answer(
        &typed_seed,
        &typed_path,
        "range_choice",
        &fixture.known_answers.typed_range_hash,
        3,
        fixture.known_answers.typed_range_selected,
    );

    let digest_before = seed.full_digest_hex().to_owned();
    let mut changed_definition = all_definition.clone();
    changed_definition.version = "1.2.4".to_owned();
    assert_ne!(
        all_definition.identity().unwrap(),
        changed_definition.identity().unwrap()
    );
    assert_eq!(seed.full_digest_hex(), digest_before);
}

#[test]
fn identity_expression_repeat_and_budget_failures_are_atomic_stable_diagnostics() {
    let fixture = load_fixture();
    let empty = definition(&fixture, "empty");
    let empty_binding = binding(&empty, "Expand.Empty", "en");
    let empty_seed = seeds(&empty_binding, "Expand.Empty", 0);

    assert_global_failure(
        expand_macros(
            empty_binding.clone(),
            &[empty.clone()],
            &empty_seed,
            MacroExpansionLimits {
                max_depth: 0,
                ..LIMITS
            },
        ),
        MacroExpansionDiagnosticKind::InvalidLimits,
    );

    let two_binding = binding(&empty, "Expand.Empty。Expand.Empty", "ja");
    let two_seeds = seeds(&two_binding, "Expand.Empty。Expand.Empty", 13);
    assert_global_failure(
        expand_macros(
            two_binding,
            &[empty.clone()],
            &two_seeds,
            MacroExpansionLimits {
                max_invocations: 1,
                ..LIMITS
            },
        ),
        MacroExpansionDiagnosticKind::InvocationBudget,
    );

    let all = definition(&fixture, "all");
    let all_binding = binding(&all, "studio.枝組.共通 2", "en");
    let all_seed = seeds(&all_binding, "studio.枝組.共通 2", 7);
    assert_global_failure(
        expand_macros(
            all_binding.clone(),
            &[all.clone()],
            &all_seed,
            MacroExpansionLimits {
                max_total_nodes: 11,
                ..LIMITS
            },
        ),
        MacroExpansionDiagnosticKind::TotalNodeBudget,
    );
    assert_invocation_failure(
        expand_macros(
            all_binding.clone(),
            &[all.clone()],
            &all_seed,
            MacroExpansionLimits {
                max_depth: 1,
                ..LIMITS
            },
        ),
        MacroExpansionDiagnosticKind::DepthBudget,
    );
    assert_invocation_failure(
        expand_macros(
            all_binding.clone(),
            &[all.clone()],
            &all_seed,
            MacroExpansionLimits {
                max_evaluation_steps: 2,
                ..LIMITS
            },
        ),
        MacroExpansionDiagnosticKind::EvaluationStepBudget,
    );
    assert_invocation_failure(
        expand_macros(
            all_binding.clone(),
            &[all.clone()],
            &all_seed,
            MacroExpansionLimits {
                max_nodes_per_invocation: 11,
                ..LIMITS
            },
        ),
        MacroExpansionDiagnosticKind::NodeBudget,
    );
    assert_invocation_failure(
        expand_macros(all_binding.clone(), &[all.clone()], &[], LIMITS),
        MacroExpansionDiagnosticKind::MissingSeed,
    );
    assert_invocation_failure(
        expand_macros(
            all_binding.clone(),
            &[all.clone()],
            &[all_seed[0].clone(), all_seed[0].clone()],
            LIMITS,
        ),
        MacroExpansionDiagnosticKind::DuplicateSeed,
    );
    let wrong_seed = derive_macro_seed(
        "studio.枝組.共通 2",
        &MacroInvocation::new("studio", "枝組.共通", 1).unwrap(),
        Some(7),
    );
    assert_invocation_failure(
        expand_macros(all_binding.clone(), &[all.clone()], &[wrong_seed], LIMITS),
        MacroExpansionDiagnosticKind::MismatchedSeed,
    );
    let ordinal_only_seed = derive_macro_seed(
        "studio.枝組.共通 2",
        &MacroInvocation::new("Other", "Seed", 0).unwrap(),
        Some(7),
    );
    assert_invocation_failure(
        expand_macros(
            all_binding.clone(),
            &[all.clone()],
            &[ordinal_only_seed],
            LIMITS,
        ),
        MacroExpansionDiagnosticKind::MismatchedSeed,
    );
    let both_mismatch_seed = derive_macro_seed(
        "studio.枝組.共通 2",
        &MacroInvocation::new("Other", "Seed", 9).unwrap(),
        Some(7),
    );
    let both_mismatch = expand_macros(
        all_binding.clone(),
        &[all.clone()],
        &[both_mismatch_seed],
        LIMITS,
    );
    assert!(both_mismatch.expanded.is_empty());
    assert!(both_mismatch.diagnostics.iter().any(|diagnostic| {
        diagnostic.kind == MacroExpansionDiagnosticKind::MissingSeed
            && diagnostic.invocation_index.is_some()
    }));
    assert!(both_mismatch.diagnostics.iter().any(|diagnostic| {
        diagnostic.kind == MacroExpansionDiagnosticKind::MismatchedSeed
            && diagnostic.invocation_index.is_none()
    }));
    assert_invocation_failure(
        expand_macros(all_binding.clone(), &[], &all_seed, LIMITS),
        MacroExpansionDiagnosticKind::DefinitionOwnershipMismatch,
    );

    let mut corrupt_binding = all_binding.clone();
    corrupt_binding.complete[0].atom_index += 1;
    assert_invocation_failure(
        expand_macros(corrupt_binding, &[all.clone()], &all_seed, LIMITS),
        MacroExpansionDiagnosticKind::BindingOwnershipMismatch,
    );

    let repeat_binding = binding(&all, "studio.枝組.共通 4", "en");
    let repeat_seed = seeds(&repeat_binding, "studio.枝組.共通 4", 7);
    assert_invocation_failure(
        expand_macros(repeat_binding, &[all.clone()], &repeat_seed, LIMITS),
        MacroExpansionDiagnosticKind::RepeatMaximumExceeded,
    );

    let mismatch = definition(&fixture, "component-mismatch");
    let mismatch_binding = binding(&mismatch, "Expand.Mismatch", "en");
    let mismatch_seed = seeds(&mismatch_binding, "Expand.Mismatch", 0);
    assert_invocation_failure(
        expand_macros(mismatch_binding, &[mismatch], &mismatch_seed, LIMITS),
        MacroExpansionDiagnosticKind::ExpressionMismatch,
    );

    let mut target_corruption = all.clone();
    if let inku_ddl::Statement::Group { body } = &mut target_corruption.body[2]
        && let inku_ddl::Statement::Relation { from, .. } = &mut body[2]
    {
        *from = "missing".to_owned();
    }
    assert_invocation_failure(
        expand_macros(all_binding, &[target_corruption], &all_seed, LIMITS),
        MacroExpansionDiagnosticKind::DefinitionOwnershipMismatch,
    );
}

#[test]
fn incomplete_i581_outcome_is_owned_unchanged_and_never_expanded() {
    let fixture = load_fixture();
    let all = definition(&fixture, "all");
    let binding = binding(&all, "studio.枝組.共通", "en");
    assert!(binding.complete.is_empty());
    assert_eq!(binding.diagnostics.len(), 1);
    let accepted = binding.clone();
    let result = expand_macros(binding, &[all], &[], LIMITS);
    assert_eq!(result.parameter_binding, accepted);
    assert!(result.expanded.is_empty());
    assert!(result.diagnostics.is_empty());
}

#[test]
fn definition_local_place_alias_materializes_only_the_canonical_value() {
    let definition = |id: &str| {
        MacroDefinition::from_json(
            &serde_json::json!({
                "schema": "inku.macro-definition.v1",
                "namespace": "Alias",
                "heading": "Place",
                "version": "1.0.0",
                "parameters": {},
                "components": {},
                "body": [{
                    "op": "emit",
                    "binding": null,
                    "fields": {
                        "place": {"expr": "semantic_ref", "category": "place", "id": id}
                    }
                }]
            })
            .to_string(),
        )
        .unwrap()
    };

    for id in ["center", "middle"] {
        let definition = definition(id);
        let binding = binding(&definition, "Alias.Place", "en");
        let seeds = seeds(&binding, "Alias.Place", 17);
        let result = expand_macros(binding, &[definition], &seeds, LIMITS);
        assert!(result.diagnostics.is_empty(), "{id}");
        let ExpandedMacroNode::Emit { fields, .. } = &result.expanded[0].nodes[0] else {
            panic!("{id}: expected emitted node");
        };
        assert_eq!(
            fields.get("place"),
            Some(&ExpandedMacroValue::SemanticRef {
                category: "place".to_owned(),
                id: "center".to_owned(),
            })
        );
    }
}

#[test]
fn fixture_schema_and_required_coverage_are_fixed() {
    let fixture = load_fixture();
    assert_eq!(fixture.schema, "inku.macro-expansion-v1-fixture.v1");
    assert_eq!(fixture.version, 1);
    assert_eq!(MACRO_EXPANSION_SCHEMA_ID, "inku.macro-expansion.v1");
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));
    let valid_ids = fixture
        .valid_cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    for required in [
        "empty-body",
        "all-operators-parameter-component-group-relation-repeat-transform-vary",
        "recursive-list-boolean-integer-to-number-and-range",
        "two-invocations-distinct-seeds",
    ] {
        assert!(
            valid_ids.contains(required),
            "missing valid case {required}"
        );
    }
    let diagnostic_ids = fixture
        .diagnostic_case_ids
        .iter()
        .map(String::as_str)
        .collect::<HashSet<_>>();
    assert_eq!(diagnostic_ids.len(), fixture.diagnostic_case_ids.len());
    for required in [
        "invalid-limits",
        "invocation-budget",
        "total-node-budget",
        "depth-budget",
        "step-budget",
        "per-invocation-node-budget",
        "missing-seed",
        "duplicate-seed",
        "mismatched-seed",
        "definition-mismatch",
        "binding-ownership",
        "repeat-maximum",
        "recursive-list-type-mismatch",
        "target-corruption-defensive-identity",
        "i581-diagnostic-unchanged",
    ] {
        assert!(
            diagnostic_ids.contains(required),
            "missing diagnostic case {required}"
        );
    }
    assert!(!FIXTURE.contains("raw_score"));
    assert!(!FIXTURE.contains("renderer"));
}

fn load_fixture() -> Fixture {
    serde_json::from_str(FIXTURE).expect("fixture must be valid JSON")
}

fn definition(fixture: &Fixture, id: &str) -> MacroDefinition {
    MacroDefinition::from_json(&serde_json::to_string(&fixture.definitions[id]).unwrap())
        .unwrap_or_else(|error| panic!("{id}: invalid definition: {error}"))
}

fn binding(
    definition: &MacroDefinition,
    source: &str,
    language: &str,
) -> inku_ddl::MacroParameterBindingResult {
    let identity = definition.identity().unwrap();
    let lock = MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap();
    let language = match language {
        "ja" => ResolvedInstructionLanguage::Ja,
        "en" => ResolvedInstructionLanguage::En,
        _ => panic!("invalid fixture language"),
    };
    let document = NormalizedDdlDocument::new(source, language, vec![lock]).unwrap();
    bind_macro_parameters(&document, std::slice::from_ref(definition)).unwrap()
}

fn seeds(
    binding: &inku_ddl::MacroParameterBindingResult,
    canonical_ddl: &str,
    composition_seed: u64,
) -> Vec<MacroSeed> {
    binding
        .complete
        .iter()
        .map(|complete| {
            let resolved = &binding.macro_resolution.resolved[complete.invocation_index];
            derive_macro_seed(canonical_ddl, &resolved.invocation, Some(composition_seed))
        })
        .collect()
}

fn flatten(nodes: &[ExpandedMacroNode]) -> Vec<&ExpandedMacroNode> {
    let mut output = Vec::new();
    for node in nodes {
        output.push(node);
        match node {
            ExpandedMacroNode::Group { body, .. } | ExpandedMacroNode::Transform { body, .. } => {
                output.extend(flatten(body))
            }
            ExpandedMacroNode::Emit { .. }
            | ExpandedMacroNode::Anchor { .. }
            | ExpandedMacroNode::Relation { .. } => {}
        }
    }
    output
}

fn node_kind(node: &ExpandedMacroNode) -> &'static str {
    match node {
        ExpandedMacroNode::Emit { .. } => "emit",
        ExpandedMacroNode::Group { .. } => "group",
        ExpandedMacroNode::Anchor { .. } => "anchor",
        ExpandedMacroNode::Relation { .. } => "relation",
        ExpandedMacroNode::Transform { .. } => "transform",
    }
}

fn node_snapshot(node: &ExpandedMacroNode) -> String {
    let provenance = node.provenance();
    let detail = match node {
        ExpandedMacroNode::Emit {
            binding, fields, ..
        } => format!(
            "binding={};fields={};children=0",
            binding
                .as_ref()
                .map(target_snapshot)
                .unwrap_or_else(|| "-".to_owned()),
            fields
                .iter()
                .map(|(name, value)| format!("{name}={}", value_snapshot(value)))
                .collect::<Vec<_>>()
                .join(",")
        ),
        ExpandedMacroNode::Group { body, .. } => format!("children={}", body.len()),
        ExpandedMacroNode::Anchor { target, .. } => {
            format!("target={};children=0", target_snapshot(target))
        }
        ExpandedMacroNode::Relation { kind, from, to, .. } => format!(
            "kind={kind};from={};to={};children=0",
            target_snapshot(from),
            target_snapshot(to)
        ),
        ExpandedMacroNode::Transform {
            transform, body, ..
        } => format!(
            "tx={};ty={};sx={};sy={};rotate={};children={}",
            number_option(transform.translate_x),
            number_option(transform.translate_y),
            number_option(transform.scale_x),
            number_option(transform.scale_y),
            number_option(transform.rotate_degrees),
            body.len()
        ),
    };
    format!(
        "{}|{}|{}|{}",
        provenance.generated_ordinal,
        node_kind(node),
        path_snapshot(&provenance.expansion_path),
        detail
    )
}

fn target_snapshot(target: &GeneratedTargetId) -> String {
    format!(
        "{}:{}:{}",
        target.invocation_ordinal,
        path_snapshot(&target.expansion_path),
        target.local_name
    )
}

fn path_snapshot(path: &[ExpansionPathSegment]) -> String {
    path.iter()
        .map(|segment| match segment {
            ExpansionPathSegment::RootStatement { statement_index } => {
                format!("R{statement_index}")
            }
            ExpansionPathSegment::ComponentUse {
                statement_index,
                component_id,
            } => format!("C{statement_index}:{component_id}"),
            ExpansionPathSegment::Group { statement_index } => {
                format!("G{statement_index}")
            }
            ExpansionPathSegment::Repeat {
                statement_index,
                iteration,
            } => format!("P{statement_index}:{iteration}"),
            ExpansionPathSegment::Transform { statement_index } => {
                format!("T{statement_index}")
            }
            ExpansionPathSegment::Vary {
                statement_index,
                selected_index,
            } => format!("V{statement_index}:{selected_index}"),
        })
        .collect::<Vec<_>>()
        .join("/")
}

fn value_snapshot(value: &ExpandedMacroValue) -> String {
    match value {
        ExpandedMacroValue::Number(value) => value.to_string(),
        ExpandedMacroValue::Integer(value) => value.to_string(),
        ExpandedMacroValue::Boolean(value) => value.to_string(),
        ExpandedMacroValue::List(values) => format!(
            "[{}]",
            values
                .iter()
                .map(value_snapshot)
                .collect::<Vec<_>>()
                .join(",")
        ),
        ExpandedMacroValue::SemanticRef { category, id } => {
            format!("ref({category},{id})")
        }
    }
}

fn number_option(value: Option<f64>) -> String {
    value
        .map(|value| value.to_string())
        .unwrap_or_else(|| "-".to_owned())
}

fn assert_all_operator_targets_and_values(nodes: &[ExpandedMacroNode]) {
    let flattened = flatten(nodes);
    let mut declared = BTreeSet::new();
    let mut referenced = Vec::new();
    let mut translate_x = Vec::new();
    let mut colors = Vec::new();
    for node in flattened {
        match node {
            ExpandedMacroNode::Emit {
                binding, fields, ..
            } => {
                if let Some(binding) = binding {
                    assert!(declared.insert(binding.clone()));
                }
                if let Some(ExpandedMacroValue::SemanticRef { category, id }) = fields.get("color")
                {
                    assert_eq!(category, "color");
                    colors.push(id.as_str());
                }
            }
            ExpandedMacroNode::Anchor { target, .. } => {
                assert!(declared.insert(target.clone()));
            }
            ExpandedMacroNode::Relation { from, to, .. } => {
                referenced.push(from);
                referenced.push(to);
            }
            ExpandedMacroNode::Transform { transform, .. } => {
                translate_x.push(transform.translate_x)
            }
            ExpandedMacroNode::Group { .. } => {}
        }
    }
    assert_eq!(declared.len(), 6);
    assert!(
        referenced
            .into_iter()
            .all(|target| declared.contains(target))
    );
    assert_eq!(translate_x, vec![Some(0.0), Some(1.0)]);
    assert_eq!(colors.len(), 2);
}

fn selected_vary_index(node: &ExpandedMacroNode) -> u64 {
    node.provenance()
        .expansion_path
        .iter()
        .find_map(|segment| match segment {
            ExpansionPathSegment::Vary { selected_index, .. } => Some(*selected_index),
            _ => None,
        })
        .expect("node must be nested under vary")
}

fn assert_hash_answer(
    seed: &MacroSeed,
    path: &[ExpansionPathSegment],
    domain: &str,
    expected: &str,
    candidate_count: u64,
    expected_selected: u64,
) {
    let digest = hex_digest(&macro_vary_choice_hash_input(seed, path, domain));
    assert_eq!(digest, expected);
    assert_eq!(hash_selected(&digest, candidate_count), expected_selected);
}

fn hash_selected(digest: &str, candidate_count: u64) -> u64 {
    u64::from_str_radix(&digest[..16], 16).unwrap() % candidate_count
}

fn hex_digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn assert_global_failure(
    result: inku_ddl::MacroExpansionResult,
    kind: MacroExpansionDiagnosticKind,
) {
    assert!(result.expanded.is_empty());
    assert!(
        result
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.kind == kind && diagnostic.invocation_index.is_none()),
        "{:?}",
        result.diagnostics
    );
}

fn assert_invocation_failure(
    result: inku_ddl::MacroExpansionResult,
    kind: MacroExpansionDiagnosticKind,
) {
    assert!(result.expanded.is_empty());
    assert!(
        result
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.kind == kind && diagnostic.invocation_index.is_some()),
        "{:?}",
        result.diagnostics
    );
}
