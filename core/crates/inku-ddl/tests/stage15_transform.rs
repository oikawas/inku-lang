use inku_ddl::{
    CompilerLockState, EXPANDED_MACRO_MEANING_SCHEMA_ID, FocusRegion, MacroDefinition,
    MacroExpansionLimits, MacroLock, NormalizedDdlDocument, ResolvedInstructionLanguage,
    STAGE15_FOCUS_SELECTION_DOMAIN, STAGE15_TRANSFORMATION_SCHEMA_ID, Stage15TargetPath,
    Stage15TransformError, Stage15Variation, Stage15VariationAmplitude, compile_typed_ddl,
    compiler_lock_hash_input, expanded_generated_provenance_canonical_bytes,
    expanded_meaning_canonical_bytes, stage15_transformation_input, transform_stage15,
};
use serde::Deserialize;
use sha2::{Digest, Sha256};

const FIXTURE: &str = include_str!("fixtures/stage15-transform-v1.json");
const LIMITS: MacroExpansionLimits = MacroExpansionLimits {
    max_invocations: 16,
    max_depth: 16,
    max_evaluation_steps: 1_000,
    max_nodes_per_invocation: 100,
    max_total_nodes: 500,
};

#[derive(Debug, Deserialize)]
struct Fixture {
    schema: String,
    version: u64,
    transformation_schema: String,
    focus_order: Vec<String>,
    cases: Vec<FixtureCase>,
}

#[derive(Debug, Deserialize)]
struct FixtureCase {
    id: String,
    source: String,
    language: String,
    composition_seed: Option<u64>,
    variation: Option<FixtureVariation>,
    expected_baseline_focus: String,
    expected_effective_focus: String,
    expected_effective_sha256: String,
}

#[derive(Clone, Copy, Debug, Deserialize)]
struct FixtureVariation {
    amplitude: FixtureAmplitude,
    seed: u64,
}

#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(rename_all = "snake_case")]
enum FixtureAmplitude {
    Small,
    Medium,
    Large,
}

#[derive(Debug, Eq, PartialEq)]
struct Snapshot {
    id: String,
    baseline_focus: String,
    effective_focus: String,
    effective_sha256: String,
}

#[test]
fn cross_platform_fixture_fixes_closed_focus_order_and_known_answers() {
    let fixture = fixture();
    assert_eq!(
        STAGE15_TRANSFORMATION_SCHEMA_ID,
        "inku.typed-stage15-transformation.v3"
    );
    assert_eq!(
        STAGE15_FOCUS_SELECTION_DOMAIN,
        b"inku.typed-stage15-focus-selection.v1"
    );
    assert_eq!(
        fixture.schema,
        "inku.stage15-transform-cross-platform-fixture.v1"
    );
    assert_eq!(fixture.version, 1);
    assert_eq!(
        fixture.transformation_schema,
        STAGE15_TRANSFORMATION_SCHEMA_ID
    );
    assert_eq!(
        fixture.focus_order,
        FocusRegion::ALL
            .iter()
            .map(|focus| focus.as_str().to_owned())
            .collect::<Vec<_>>()
    );
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let actual = fixture
        .cases
        .iter()
        .map(|case| {
            let compilation = compile(
                &case.source,
                language(&case.language),
                &[],
                case.composition_seed,
                LIMITS,
            );
            let original_semantic = compilation.semantic_document.as_ref().unwrap().ast.clone();
            let original_expansion = compilation
                .macro_expansion
                .as_ref()
                .unwrap()
                .expanded
                .clone();
            let result = transform_stage15(
                stage15_transformation_input(&compilation).unwrap(),
                case.variation.map(variation),
            )
            .unwrap();
            assert_eq!(result.schema_id(), STAGE15_TRANSFORMATION_SCHEMA_ID);
            let canonical: serde_json::Value =
                serde_json::from_slice(result.effective_canonical_bytes()).unwrap();
            assert_eq!(canonical["schema"], STAGE15_TRANSFORMATION_SCHEMA_ID);
            assert_eq!(result.composition_seed(), case.composition_seed);
            assert_eq!(
                result.verified_effective_view().composition_seed(),
                case.composition_seed
            );
            assert_eq!(
                canonical["composition_seed"],
                serde_json::json!(case.composition_seed)
            );
            assert_eq!(count_json_key(&canonical, "composition_seed"), 1);
            assert_eq!(
                result.original_semantic_document(),
                &original_semantic,
                "{}",
                case.id
            );
            assert_eq!(
                result.original_expanded_invocations(),
                original_expansion.as_slice(),
                "{}",
                case.id
            );
            assert_eq!(result.targets().len(), 1, "{}", case.id);
            Snapshot {
                id: case.id.clone(),
                baseline_focus: result.baseline_focus().unwrap().as_str().to_owned(),
                effective_focus: result.resolved_focus().unwrap().as_str().to_owned(),
                effective_sha256: result.effective_canonical_digest().to_owned(),
            }
        })
        .collect::<Vec<_>>();
    let expected = fixture
        .cases
        .iter()
        .map(|case| Snapshot {
            id: case.id.clone(),
            baseline_focus: case.expected_baseline_focus.clone(),
            effective_focus: case.expected_effective_focus.clone(),
            effective_sha256: case.expected_effective_sha256.clone(),
        })
        .collect::<Vec<_>>();
    assert_eq!(actual, expected);

    assert_eq!(actual[0].effective_sha256, actual[1].effective_sha256);
    for varied in &actual[2..] {
        assert_eq!(varied.baseline_focus, actual[1].baseline_focus);
        assert_ne!(varied.effective_focus, varied.baseline_focus);
    }
}

#[test]
fn no_target_and_non_center_meaning_remain_effective_no_ops() {
    for source in ["thin circle", "place eight circle at left-edge."] {
        let compilation = compile(
            source,
            ResolvedInstructionLanguage::En,
            &[],
            Some(42),
            LIMITS,
        );
        let original_semantic = compilation.semantic_document.as_ref().unwrap().ast.clone();
        let without_variation =
            transform_stage15(stage15_transformation_input(&compilation).unwrap(), None).unwrap();
        let with_variation = transform_stage15(
            stage15_transformation_input(&compilation).unwrap(),
            Some(Stage15Variation {
                amplitude: Stage15VariationAmplitude::Large,
                seed: 9,
            }),
        )
        .unwrap();

        assert!(without_variation.targets().is_empty(), "{source}");
        assert_eq!(without_variation.baseline_focus(), None, "{source}");
        assert_eq!(without_variation.resolved_focus(), None, "{source}");
        assert!(without_variation.moved_axes().is_empty(), "{source}");
        assert_eq!(
            without_variation.original_semantic_document(),
            &original_semantic
        );
        assert_eq!(
            with_variation.effective_canonical_bytes(),
            without_variation.effective_canonical_bytes(),
            "requested no-op option entered effective meaning for {source}"
        );
        assert!(with_variation.moved_axes().is_empty(), "{source}");
        assert_eq!(with_variation.effective_variation(), None, "{source}");
    }
}

#[test]
fn no_focus_attested_seed_passthrough_is_lossless_and_identity_bound() {
    let results = [None, Some(0), Some(42)].map(|composition_seed| {
        let compilation = compile(
            "thin circle",
            ResolvedInstructionLanguage::En,
            &[],
            composition_seed,
            LIMITS,
        );
        let without_variation =
            transform_stage15(stage15_transformation_input(&compilation).unwrap(), None).unwrap();
        let with_variation = transform_stage15(
            stage15_transformation_input(&compilation).unwrap(),
            Some(Stage15Variation {
                amplitude: Stage15VariationAmplitude::Large,
                seed: 9,
            }),
        )
        .unwrap();

        assert_eq!(without_variation.composition_seed(), composition_seed);
        assert_eq!(
            without_variation
                .verified_effective_view()
                .composition_seed(),
            composition_seed
        );
        let candidate =
            inku_ddl::lower_verified_stage15_view(without_variation.verified_effective_view());
        assert_eq!(
            candidate.verified_effective_view().composition_seed(),
            composition_seed
        );
        assert_eq!(
            without_variation.effective_canonical_bytes(),
            with_variation.effective_canonical_bytes(),
            "a no-op variation changed effective identity for {composition_seed:?}"
        );
        let canonical: serde_json::Value =
            serde_json::from_slice(without_variation.effective_canonical_bytes()).unwrap();
        assert_eq!(
            canonical["composition_seed"],
            serde_json::json!(composition_seed)
        );
        assert_eq!(count_json_key(&canonical, "composition_seed"), 1);
        assert!(canonical["focus_selection"].is_null());

        without_variation
    });

    assert_ne!(
        results[0].effective_canonical_digest(),
        results[1].effective_canonical_digest()
    );
    assert_ne!(
        results[0].effective_canonical_digest(),
        results[2].effective_canonical_digest()
    );
    assert_ne!(
        results[1].effective_canonical_digest(),
        results[2].effective_canonical_digest()
    );
}

#[test]
fn omitted_and_explicit_zero_composition_seeds_keep_distinct_focus_provenance() {
    let source = "place one thin pencil line at the center";
    let omitted = compile(source, ResolvedInstructionLanguage::En, &[], None, LIMITS);
    let explicit_zero = compile(
        source,
        ResolvedInstructionLanguage::En,
        &[],
        Some(0),
        LIMITS,
    );
    assert_eq!(
        omitted
            .compiler_lock
            .as_ref()
            .unwrap()
            .canonical_pre_expansion_digest,
        explicit_zero
            .compiler_lock
            .as_ref()
            .unwrap()
            .canonical_pre_expansion_digest
    );
    assert_eq!(
        omitted
            .compiler_lock
            .as_ref()
            .unwrap()
            .expanded_meaning_digest,
        explicit_zero
            .compiler_lock
            .as_ref()
            .unwrap()
            .expanded_meaning_digest
    );
    assert_eq!(
        omitted.compiler_lock.as_ref().unwrap().composition_seed,
        None
    );
    assert_eq!(
        explicit_zero
            .compiler_lock
            .as_ref()
            .unwrap()
            .composition_seed,
        Some(0)
    );
    assert_ne!(
        omitted.compiler_lock.as_ref().unwrap().full_digest,
        explicit_zero.compiler_lock.as_ref().unwrap().full_digest
    );
    let omitted_result =
        transform_stage15(stage15_transformation_input(&omitted).unwrap(), None).unwrap();
    let explicit_result =
        transform_stage15(stage15_transformation_input(&explicit_zero).unwrap(), None).unwrap();
    assert_eq!(omitted_result.composition_seed(), None);
    assert_eq!(explicit_result.composition_seed(), Some(0));
    assert_eq!(
        omitted_result.verified_effective_view().composition_seed(),
        None
    );
    assert_eq!(
        explicit_result.verified_effective_view().composition_seed(),
        Some(0)
    );
    for (result, expected) in [(&omitted_result, None), (&explicit_result, Some(0))] {
        let canonical: serde_json::Value =
            serde_json::from_slice(result.effective_canonical_bytes()).unwrap();
        assert_eq!(canonical["composition_seed"], serde_json::json!(expected));
        assert_eq!(count_json_key(&canonical, "composition_seed"), 1);
    }
    assert_ne!(
        omitted_result.effective_canonical_bytes(),
        explicit_result.effective_canonical_bytes()
    );
}

#[test]
fn ja_and_en_variation_keep_the_same_effective_identity_and_expanded_schema_owner() {
    let variation = Some(Stage15Variation {
        amplitude: Stage15VariationAmplitude::Medium,
        seed: 0,
    });
    let results = [
        (
            "中心に、鉛筆の細い線をひとつ置く。",
            ResolvedInstructionLanguage::Ja,
        ),
        (
            "place one thin pencil line at the center",
            ResolvedInstructionLanguage::En,
        ),
    ]
    .map(|(source, language)| {
        let compilation = compile(source, language, &[], None, LIMITS);
        transform_stage15(
            stage15_transformation_input(&compilation).unwrap(),
            variation,
        )
        .unwrap()
    });

    assert_eq!(
        results[0].effective_canonical_digest(),
        results[1].effective_canonical_digest()
    );
    let canonical: serde_json::Value =
        serde_json::from_slice(results[0].effective_canonical_bytes()).unwrap();
    assert_eq!(
        canonical["original_expanded"]["schema"],
        EXPANDED_MACRO_MEANING_SCHEMA_ID
    );
}

#[test]
fn seed_zero_variation_amplitudes_resolve_to_three_distinct_non_baseline_focuses() {
    let compilation = compile(
        "place one thin pencil line at the center",
        ResolvedInstructionLanguage::En,
        &[],
        Some(0),
        LIMITS,
    );
    let baseline = transform_stage15(stage15_transformation_input(&compilation).unwrap(), None)
        .unwrap()
        .baseline_focus()
        .unwrap();
    let results = [
        Stage15VariationAmplitude::Small,
        Stage15VariationAmplitude::Medium,
        Stage15VariationAmplitude::Large,
    ]
    .map(|amplitude| {
        transform_stage15(
            stage15_transformation_input(&compilation).unwrap(),
            Some(Stage15Variation { amplitude, seed: 0 }),
        )
        .unwrap()
    });
    let resolved = results.each_ref().map(|result| {
        assert_eq!(result.composition_seed(), Some(0));
        result.resolved_focus().unwrap()
    });
    let digests = results
        .each_ref()
        .map(|result| result.effective_canonical_digest().to_owned());

    assert!(resolved.iter().all(|focus| *focus != baseline));
    assert_ne!(resolved[0], resolved[1]);
    assert_ne!(resolved[0], resolved[2]);
    assert_ne!(resolved[1], resolved[2]);
    assert_ne!(digests[0], digests[1]);
    assert_ne!(digests[0], digests[2]);
    assert_ne!(digests[1], digests[2]);
}

#[test]
fn composition_seed_surface_is_read_only() {
    let source = include_str!("../src/stage15_transform.rs");
    let public_seed_surface = source
        .lines()
        .map(str::trim)
        .filter(|line| line.starts_with("pub ") && line.contains("composition_seed"))
        .collect::<Vec<_>>();
    assert_eq!(public_seed_surface.len(), 3);
    assert!(
        public_seed_surface
            .iter()
            .all(|line| line.starts_with("pub const fn composition_seed(")),
        "unexpected public seed surface: {public_seed_surface:?}"
    );
}

#[test]
fn source_group_and_macro_targets_are_ordered_once_with_lossless_provenance() {
    let source = compile(
        "place one thin pencil line at the center",
        ResolvedInstructionLanguage::En,
        &[],
        Some(11),
        LIMITS,
    );
    let source_result =
        transform_stage15(stage15_transformation_input(&source).unwrap(), None).unwrap();
    assert_eq!(source_result.targets().len(), 1);
    assert!(matches!(
        source_result.targets()[0].path,
        Stage15TargetPath::Instruction {
            instruction_index: 0
        }
    ));
    assert_eq!(
        source_result.original_semantic_document(),
        &source.semantic_document.as_ref().unwrap().ast
    );

    let group = compile(
        "place a circle and a line at the center.",
        ResolvedInstructionLanguage::En,
        &[],
        Some(11),
        LIMITS,
    );
    let group_result =
        transform_stage15(stage15_transformation_input(&group).unwrap(), None).unwrap();
    assert_eq!(group_result.targets().len(), 1);
    assert!(matches!(
        group_result.targets()[0].path,
        Stage15TargetPath::GroupPredicate {
            edge_index: 0,
            group_index: 0
        }
    ));
    assert_eq!(
        group_result.original_semantic_document(),
        &group.semantic_document.as_ref().unwrap().ast
    );

    let definition = center_emit_definition();
    let generated = compile_locked(
        "Focus.Center",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
        Some(17),
        LIMITS,
    );
    let original_expansion = generated.macro_expansion.as_ref().unwrap().expanded.clone();
    let generated_result = transform_stage15(
        stage15_transformation_input(&generated).unwrap(),
        Some(Stage15Variation {
            amplitude: Stage15VariationAmplitude::Small,
            seed: 3,
        }),
    )
    .unwrap();
    assert_eq!(generated_result.targets().len(), 2);
    let generated_ordinals = generated_result
        .targets()
        .iter()
        .map(|target| match &target.path {
            Stage15TargetPath::MacroEmit {
                generated_ordinal,
                field,
                ..
            } if field == "place" => *generated_ordinal,
            other => panic!("unexpected generated target {other:?}"),
        })
        .collect::<Vec<_>>();
    assert_eq!(generated_ordinals, [0, 1]);
    assert_eq!(
        generated_result.original_expanded_invocations(),
        original_expansion.as_slice()
    );
    assert_eq!(generated_result.moved_axes().len(), 1);
    assert_eq!(generated_result.moved_axes()[0].axis, "focus");
    assert_eq!(
        generated_result.effective_variation(),
        Some(Stage15Variation {
            amplitude: Stage15VariationAmplitude::Small,
            seed: 3,
        })
    );
}

#[test]
fn source_instruction_group_and_macro_targets_share_one_ordered_overlay() {
    let definition = center_emit_definition();
    let compilation = compile_locked(
        "place one thin pencil line at the center. place circle and Focus.Center at center.",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
        Some(19),
        LIMITS,
    );
    let result = transform_stage15(
        stage15_transformation_input(&compilation).unwrap(),
        Some(Stage15Variation {
            amplitude: Stage15VariationAmplitude::Large,
            seed: 0,
        }),
    )
    .unwrap();

    assert_eq!(result.targets().len(), 4);
    assert!(matches!(
        result.targets()[0].path,
        Stage15TargetPath::Instruction {
            instruction_index: 0
        }
    ));
    assert!(matches!(
        result.targets()[1].path,
        Stage15TargetPath::GroupPredicate {
            edge_index: 0,
            group_index: 0
        }
    ));
    assert!(
        result.targets()[2..]
            .iter()
            .all(|target| matches!(target.path, Stage15TargetPath::MacroEmit { .. }))
    );
    assert!(
        result
            .targets()
            .iter()
            .all(|target| target.effective_focus == result.resolved_focus().unwrap())
    );
}

#[test]
fn canonical_ready_gate_and_target_integrity_fail_closed() {
    for (source, expected_state) in [
        ("many", CompilerLockState::IncompleteKnownHole),
        (
            "line. place the line and a circle.",
            CompilerLockState::BlockedConflict,
        ),
        ("mystery", CompilerLockState::BlockedDiagnostic),
    ] {
        let compilation = compile(source, ResolvedInstructionLanguage::En, &[], None, LIMITS);
        assert_eq!(
            stage15_transformation_input(&compilation),
            Err(Stage15TransformError::CompilerState(expected_state)),
            "{source}"
        );
    }

    let mut semantic_corruption = compile(
        "place one thin pencil line at the center",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    semantic_corruption
        .semantic_document
        .as_mut()
        .unwrap()
        .canonical_bytes
        .as_mut()
        .unwrap()
        .push(b' ');
    assert_eq!(
        stage15_transformation_input(&semantic_corruption),
        Err(Stage15TransformError::SemanticAstCanonicalMismatch)
    );

    let mut ast_corruption = compile(
        "place one thin pencil line at the center",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    ast_corruption
        .semantic_document
        .as_mut()
        .unwrap()
        .ast
        .instructions[0]
        .position
        .as_mut()
        .unwrap()
        .identity
        .id = "left_edge".to_owned();
    assert_eq!(
        stage15_transformation_input(&ast_corruption),
        Err(Stage15TransformError::SemanticAstCanonicalMismatch)
    );

    let mut source_provenance_corruption = compile(
        "place one thin pencil line at the center",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    source_provenance_corruption
        .semantic_document
        .as_mut()
        .unwrap()
        .ast
        .instructions[0]
        .position
        .as_mut()
        .unwrap()
        .provenance
        .source
        .surface
        .push('!');
    assert_eq!(
        stage15_transformation_input(&source_provenance_corruption),
        Err(Stage15TransformError::SemanticSourceProvenanceDigestMismatch)
    );

    let definition = center_emit_definition();
    let mut generated_provenance_corruption = compile_locked(
        "Focus.Center",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
        Some(5),
        LIMITS,
    );
    let inku_ddl::ExpandedMacroNode::Emit { provenance, .. } = &mut generated_provenance_corruption
        .macro_expansion
        .as_mut()
        .unwrap()
        .expanded[0]
        .nodes[0]
    else {
        panic!("center fixture starts with one generated emit");
    };
    provenance.generated_ordinal += 1;
    assert_eq!(
        stage15_transformation_input(&generated_provenance_corruption),
        Err(Stage15TransformError::ExpandedGeneratedProvenanceDigestMismatch)
    );

    let mut duplicate = compile_locked(
        "Focus.Center",
        ResolvedInstructionLanguage::En,
        &[definition],
        Some(5),
        LIMITS,
    );
    let expansion = duplicate.macro_expansion.as_mut().unwrap();
    let duplicated_node = expansion.expanded[0].nodes[0].clone();
    expansion.expanded[0].nodes.push(duplicated_node);
    let lock = duplicate.compiler_lock.as_mut().unwrap();
    lock.expanded_meaning_digest = Some(sha256(&expanded_meaning_canonical_bytes(expansion)));
    lock.expanded_generated_provenance_digest = Some(sha256(
        &expanded_generated_provenance_canonical_bytes(expansion),
    ));
    lock.full_digest = sha256(&compiler_lock_hash_input(lock));
    let input = stage15_transformation_input(&duplicate).unwrap();
    assert!(matches!(
        transform_stage15(input, None),
        Err(Stage15TransformError::DuplicateTarget(
            Stage15TargetPath::MacroEmit { .. }
        ))
    ));
}

fn fixture() -> Fixture {
    serde_json::from_str(FIXTURE).unwrap()
}

fn language(value: &str) -> ResolvedInstructionLanguage {
    match value {
        "ja" => ResolvedInstructionLanguage::Ja,
        "en" => ResolvedInstructionLanguage::En,
        other => panic!("unexpected fixture language {other}"),
    }
}

fn variation(value: FixtureVariation) -> Stage15Variation {
    Stage15Variation {
        amplitude: match value.amplitude {
            FixtureAmplitude::Small => Stage15VariationAmplitude::Small,
            FixtureAmplitude::Medium => Stage15VariationAmplitude::Medium,
            FixtureAmplitude::Large => Stage15VariationAmplitude::Large,
        },
        seed: value.seed,
    }
}

fn compile(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    seed: Option<u64>,
    limits: MacroExpansionLimits,
) -> inku_ddl::TypedDdlCompilation {
    compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        definitions,
        seed,
        limits,
    )
}

fn compile_locked(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    seed: Option<u64>,
    limits: MacroExpansionLimits,
) -> inku_ddl::TypedDdlCompilation {
    let locks = definitions.iter().map(lock_for).collect::<Vec<_>>();
    compile_typed_ddl(
        NormalizedDdlDocument::new(source, language, locks).unwrap(),
        definitions,
        seed,
        limits,
    )
}

fn lock_for(definition: &MacroDefinition) -> MacroLock {
    let identity = definition.identity().unwrap();
    MacroLock::new(
        identity.qualified_name(),
        identity.version(),
        format!("sha256:{}", identity.full_digest_hex()),
    )
    .unwrap()
}

fn center_emit_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Focus","heading":"Center","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"left_edge"}}}]}"#,
    )
    .unwrap()
}

fn sha256(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn count_json_key(value: &serde_json::Value, key: &str) -> usize {
    match value {
        serde_json::Value::Array(values) => {
            values.iter().map(|value| count_json_key(value, key)).sum()
        }
        serde_json::Value::Object(values) => {
            usize::from(values.contains_key(key))
                + values
                    .values()
                    .map(|value| count_json_key(value, key))
                    .sum::<usize>()
        }
        _ => 0,
    }
}
