use inku_ddl::{
    CompilerLockState, EXPANDED_MACRO_MEANING_SCHEMA_ID, ExpandedMacroNode, FocusRegion,
    GEOMETRY_RESOLUTION_POLICY_ID, MacroDefinition, MacroExpansionDiagnosticKind,
    MacroExpansionLimits, MacroInvocationProvenance, MacroLock, NormalizedDdlDocument,
    ResolvedInstructionLanguage, STAGE15_FOCUS_SELECTION_DOMAIN, STAGE15_TRANSFORMATION_SCHEMA_ID,
    SemanticContinuationTarget, SemanticHead, SemanticIdentity, Stage15TargetPath,
    Stage15TransformError, Stage15Variation, Stage15VariationAmplitude, compile_typed_ddl,
    compiler_lock_hash_input, expanded_generated_provenance_canonical_bytes,
    expanded_meaning_canonical_bytes, geometry_resolution_policy_digest,
    semantic_source_provenance_canonical_bytes, stage15_transformation_input, transform_stage15,
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
    geometry_policy_id: String,
    geometry_policy_digest: String,
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
        "inku.typed-stage15-transformation.v5"
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
    assert_eq!(fixture.geometry_policy_id, GEOMETRY_RESOLUTION_POLICY_ID);
    assert_eq!(
        fixture.geometry_policy_digest,
        geometry_resolution_policy_digest()
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
            assert_eq!(result.geometry_policy_id(), fixture.geometry_policy_id);
            assert_eq!(
                result.geometry_policy_digest(),
                fixture.geometry_policy_digest
            );
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
fn step9i_input_boundary_rejects_visible_source_replacement() {
    let mut red = compile(
        "a red circle",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    let blue = compile(
        "a blue square",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );

    let red_result = transform_stage15(stage15_transformation_input(&red).unwrap(), None).unwrap();
    let blue_result =
        transform_stage15(stage15_transformation_input(&blue).unwrap(), None).unwrap();
    assert_ne!(
        red_result.effective_canonical_bytes(),
        blue_result.effective_canonical_bytes()
    );

    red.document = blue.document.clone();
    assert_eq!(
        stage15_transformation_input(&red),
        Err(Stage15TransformError::CompilerLockDigestMismatch)
    );
}

#[test]
fn verified_stage15_input_rejects_a_self_consistent_foreign_geometry_policy() {
    let mut compilation = compile(
        "place one thin pencil line at the center",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    let lock = compilation.compiler_lock.as_mut().unwrap();
    lock.geometry_policy_digest = "foreign-policy-digest".to_owned();
    lock.full_digest = sha256(&compiler_lock_hash_input(lock));

    assert_eq!(
        stage15_transformation_input(&compilation),
        Err(Stage15TransformError::GeometryPolicyMismatch)
    );
}

#[test]
fn step9i_input_boundary_checks_language_evidence_but_allows_empty_source() {
    let source = "place one thin pencil line at the center";
    let mut language_mismatch = compile(
        source,
        ResolvedInstructionLanguage::En,
        &[],
        Some(0),
        LIMITS,
    );
    language_mismatch.document =
        NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::Ja, Vec::new()).unwrap();
    assert_eq!(
        stage15_transformation_input(&language_mismatch),
        Err(Stage15TransformError::SemanticSourceProvenanceDigestMismatch)
    );

    let empty = compile("", ResolvedInstructionLanguage::En, &[], Some(0), LIMITS);
    let input = stage15_transformation_input(&empty).unwrap();
    let result = transform_stage15(input, None).unwrap();
    assert!(result.targets().is_empty());
    assert_eq!(result.composition_seed(), Some(0));
}

#[test]
fn explicit_geometry_and_numeric_position_language_evidence_is_checked() {
    let source =
        "place one red pen solid empty circle with radius 0.25 at horizontal 0.5, vertical 0.5.";
    let control = compile(source, ResolvedInstructionLanguage::En, &[], None, LIMITS);
    assert!(stage15_transformation_input(&control).is_ok());

    let mut geometry_mismatch = control.clone();
    let geometry = geometry_mismatch
        .semantic_document
        .as_mut()
        .unwrap()
        .ast
        .instructions[0]
        .entity
        .explicit_geometry
        .as_mut()
        .unwrap();
    let inku_ddl::SemanticExplicitGeometry::Radius(value) = geometry else {
        panic!("control has radius geometry");
    };
    value.keyword_provenance.language = ResolvedInstructionLanguage::Ja;
    value.decimal.provenance.language = ResolvedInstructionLanguage::Ja;
    refresh_semantic_source_provenance_and_full_lock(&mut geometry_mismatch);
    assert_eq!(
        stage15_transformation_input(&geometry_mismatch),
        Err(Stage15TransformError::SemanticSourceProvenanceDigestMismatch)
    );

    let mut position_mismatch = control;
    let position = position_mismatch
        .semantic_document
        .as_mut()
        .unwrap()
        .ast
        .instructions[0]
        .entity
        .numeric_position
        .as_mut()
        .unwrap();
    position.x.keyword_provenance.language = ResolvedInstructionLanguage::Ja;
    position.x.decimal.provenance.language = ResolvedInstructionLanguage::Ja;
    position.y.keyword_provenance.language = ResolvedInstructionLanguage::Ja;
    position.y.decimal.provenance.language = ResolvedInstructionLanguage::Ja;
    refresh_semantic_source_provenance_and_full_lock(&mut position_mismatch);
    assert_eq!(
        stage15_transformation_input(&position_mismatch),
        Err(Stage15TransformError::SemanticSourceProvenanceDigestMismatch)
    );
}

#[test]
fn step9i_input_boundary_checks_all_sidecars_and_consumed_definition_identity() {
    let used = center_emit_definition();
    let unused = unused_sidecar_definition();
    let locks = vec![lock_for(&used), lock_for(&unused)];
    let control = compile_typed_ddl(
        NormalizedDdlDocument::new(
            "Focus.Center",
            ResolvedInstructionLanguage::En,
            locks.clone(),
        )
        .unwrap(),
        std::slice::from_ref(&used),
        Some(19),
        LIMITS,
    );
    let control_lock = control.compiler_lock.as_ref().unwrap();
    assert_eq!(control_lock.definition_identities.len(), 2);
    assert!(
        control_lock
            .definition_identities
            .iter()
            .find(|identity| identity.qualified_name == "Spare.Unused")
            .unwrap()
            .resolved_definition_digest
            .is_none()
    );
    assert!(stage15_transformation_input(&control).is_ok());

    let mut missing_projection = control.clone();
    missing_projection
        .compiler_lock
        .as_mut()
        .unwrap()
        .definition_identities
        .pop();
    refresh_full_lock(&mut missing_projection);
    assert_eq!(
        stage15_transformation_input(&missing_projection),
        Err(Stage15TransformError::CompilerLockDigestMismatch)
    );

    let mut extra_projection = control.clone();
    let extra = extra_sidecar_definition();
    let extra_identity = extra.identity().unwrap();
    extra_projection
        .compiler_lock
        .as_mut()
        .unwrap()
        .definition_identities
        .push(inku_ddl::CompilerDefinitionIdentity {
            qualified_name: extra_identity.qualified_name().to_owned(),
            version: extra_identity.version().to_owned(),
            sidecar_digest: format!("sha256:{}", extra_identity.full_digest_hex()),
            resolved_definition_digest: None,
        });
    refresh_full_lock(&mut extra_projection);
    assert_eq!(
        stage15_transformation_input(&extra_projection),
        Err(Stage15TransformError::CompilerLockDigestMismatch)
    );

    let mut changed_projection = control.clone();
    changed_projection
        .compiler_lock
        .as_mut()
        .unwrap()
        .definition_identities[0]
        .sidecar_digest =
        "sha256:0000000000000000000000000000000000000000000000000000000000000000".to_owned();
    refresh_full_lock(&mut changed_projection);
    assert_eq!(
        stage15_transformation_input(&changed_projection),
        Err(Stage15TransformError::CompilerLockDigestMismatch)
    );

    let replacement = replacement_center_definition();
    let replacement_lock = lock_for(&replacement);
    let replacement_identity = replacement.identity().unwrap();
    let mut stale_consumer = control;
    stale_consumer.document = NormalizedDdlDocument::new(
        "Focus.Center",
        ResolvedInstructionLanguage::En,
        vec![replacement_lock, lock_for(&unused)],
    )
    .unwrap();
    let projected = stale_consumer
        .compiler_lock
        .as_mut()
        .unwrap()
        .definition_identities
        .iter_mut()
        .find(|identity| identity.qualified_name == "Focus.Center")
        .unwrap();
    projected.version = replacement_identity.version().to_owned();
    projected.sidecar_digest = format!("sha256:{}", replacement_identity.full_digest_hex());
    projected.resolved_definition_digest = Some(replacement_identity.full_digest_hex().to_owned());
    refresh_full_lock(&mut stale_consumer);
    assert_eq!(
        stage15_transformation_input(&stale_consumer),
        Err(Stage15TransformError::ExpansionDiagnostic)
    );
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
fn noun_introduction_reaches_stage15_with_distinct_entity_and_macro_provenance() {
    let source = "circle. place a red circle.";
    let compilation = compile(
        source,
        ResolvedInstructionLanguage::En,
        &[],
        Some(0),
        LIMITS,
    );
    assert_eq!(
        compilation.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady
    );
    let semantic = compilation.semantic_document.as_ref().unwrap();
    assert_eq!(semantic.ast.instructions.len(), 2);
    assert!(semantic.ast.instructions[0].entity.color.is_none());
    assert_eq!(
        semantic.ast.instructions[1]
            .entity
            .color
            .as_ref()
            .map(|term| term.identity.id.as_str()),
        Some("red")
    );
    assert_eq!(
        semantic.ast.instructions[1]
            .action
            .as_ref()
            .map(|term| term.identity.id.as_str()),
        Some("place")
    );
    for instruction in &semantic.ast.instructions {
        let occurrence = instruction.entity.head.source();
        assert_eq!(
            &source[occurrence.span.start_byte..occurrence.span.end_byte],
            occurrence.surface
        );
    }
    let transformed =
        transform_stage15(stage15_transformation_input(&compilation).unwrap(), None).unwrap();
    assert_eq!(transformed.original_semantic_document(), &semantic.ast);

    let definition = center_emit_definition();
    let macro_source = "a Focus.Center";
    let macro_compilation = compile_locked(
        macro_source,
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
        Some(17),
        LIMITS,
    );
    assert_eq!(
        macro_compilation.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady
    );
    let macro_semantic = macro_compilation.semantic_document.as_ref().unwrap();
    assert_eq!(macro_semantic.ast.instructions.len(), 1);
    let SemanticHead::MacroInvocation(head) = &macro_semantic.ast.instructions[0].entity.head
    else {
        panic!("locked synthetic macro remains a semantic noun introduction");
    };
    assert_eq!(head.qualified_name, "Focus.Center");
    assert_eq!(head.provenance.source.surface, "Focus.Center");
    assert_eq!(
        &macro_source[head.provenance.source.span.start_byte..head.provenance.source.span.end_byte],
        "Focus.Center"
    );
    let macro_transformed = transform_stage15(
        stage15_transformation_input(&macro_compilation).unwrap(),
        None,
    )
    .unwrap();
    assert_eq!(
        macro_transformed.original_semantic_document(),
        &macro_semantic.ast
    );
    assert_eq!(
        macro_transformed.original_expanded_invocations(),
        macro_compilation
            .macro_expansion
            .as_ref()
            .unwrap()
            .expanded
            .as_slice()
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
fn primitive_inline_and_continuation_share_baseline_and_complete_variation_identity() {
    let compilations = ["赤い円を中心に置く。", "円を中心に置く。円は赤い。"].map(|source| {
        compile(
            source,
            ResolvedInstructionLanguage::Ja,
            &[],
            Some(41),
            LIMITS,
        )
    });
    assert_eq!(
        compilations[0].pre_expansion_canonical_bytes(),
        compilations[1].pre_expansion_canonical_bytes()
    );
    let baseline = compilations.each_ref().map(|compilation| {
        transform_stage15(stage15_transformation_input(compilation).unwrap(), None).unwrap()
    });
    assert_eq!(baseline[0].baseline_focus(), baseline[1].baseline_focus());
    assert_eq!(
        baseline[0].effective_canonical_bytes(),
        baseline[1].effective_canonical_bytes()
    );

    for amplitude in Stage15VariationAmplitude::ALL {
        let varied = compilations.each_ref().map(|compilation| {
            transform_stage15(
                stage15_transformation_input(compilation).unwrap(),
                Some(Stage15Variation {
                    amplitude,
                    seed: 13,
                }),
            )
            .unwrap()
        });
        assert_eq!(varied[0].resolved_focus(), varied[1].resolved_focus());
        assert_eq!(
            varied[0].effective_canonical_bytes(),
            varied[1].effective_canonical_bytes()
        );
    }
}

#[test]
fn macro_source_gap_keeps_source_paths_and_projects_effective_paths_to_semantic_ordinals() {
    let definition = center_emit_definition();
    let compilations = [
        "a red Focus.Center; a blue Focus.Center",
        "a Focus.Center; the red Focus.Center; a blue Focus.Center",
    ]
    .map(|source| {
        compile_locked(
            source,
            ResolvedInstructionLanguage::En,
            std::slice::from_ref(&definition),
            Some(19),
            LIMITS,
        )
    });
    let transformed = compilations.each_ref().map(|compilation| {
        transform_stage15(
            stage15_transformation_input(compilation).unwrap(),
            Some(Stage15Variation {
                amplitude: Stage15VariationAmplitude::Large,
                seed: 7,
            }),
        )
        .unwrap()
    });
    let source_ordinals = transformed.each_ref().map(|result| {
        result
            .targets()
            .iter()
            .filter_map(|target| match &target.path {
                Stage15TargetPath::MacroEmit {
                    invocation_ordinal, ..
                } => Some(*invocation_ordinal),
                _ => None,
            })
            .collect::<Vec<_>>()
    });
    assert_eq!(source_ordinals[0], [0, 0, 1, 1]);
    assert_eq!(source_ordinals[1], [0, 0, 2, 2]);
    assert_eq!(
        transformed[0].effective_canonical_bytes(),
        transformed[1].effective_canonical_bytes()
    );
    let canonical: serde_json::Value =
        serde_json::from_slice(transformed[1].effective_canonical_bytes()).unwrap();
    let semantic_ordinals = canonical["targets"]
        .as_array()
        .unwrap()
        .iter()
        .map(|target| target["path"]["invocation_ordinal"].as_u64().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(semantic_ordinals, [0, 0, 1, 1]);
}

#[test]
fn continuation_target_and_execution_mapping_tampering_fail_closed_before_transform() {
    let mut target_tamper = compile(
        "円を中心に置く。円は赤い。",
        ResolvedInstructionLanguage::Ja,
        &[],
        Some(41),
        LIMITS,
    );
    let semantic = target_tamper.semantic_document.as_mut().unwrap();
    assert!(
        !std::str::from_utf8(semantic.canonical_bytes.as_ref().unwrap())
            .unwrap()
            .contains("continuations")
    );
    semantic.ast.continuations[0].target =
        SemanticContinuationTarget::Primitive(SemanticIdentity {
            category: "shape".to_owned(),
            id: "line".to_owned(),
        });
    assert_eq!(
        stage15_transformation_input(&target_tamper),
        Err(Stage15TransformError::SemanticSourceProvenanceDigestMismatch)
    );

    let definition = center_emit_definition();
    let compilation = compile_locked(
        "a Focus.Center; the red Focus.Center; a blue Focus.Center",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
        Some(19),
        LIMITS,
    );
    let mut missing = compilation.clone();
    missing.macro_expansion.as_mut().unwrap().expanded.pop();
    assert_eq!(
        stage15_transformation_input(&missing),
        Err(Stage15TransformError::ExpansionDiagnostic)
    );

    let mut duplicate = compilation.clone();
    let first = duplicate.macro_expansion.as_ref().unwrap().expanded[0].clone();
    duplicate.macro_expansion.as_mut().unwrap().expanded[1] = first;
    assert_eq!(
        stage15_transformation_input(&duplicate),
        Err(Stage15TransformError::ExpansionDiagnostic)
    );

    let mut reordered = compilation.clone();
    reordered
        .macro_expansion
        .as_mut()
        .unwrap()
        .expanded
        .swap(0, 1);
    assert_eq!(
        stage15_transformation_input(&reordered),
        Err(Stage15TransformError::ExpansionDiagnostic)
    );

    let mut seed_mismatch = compilation.clone();
    let lock = seed_mismatch.compiler_lock.as_mut().unwrap();
    lock.macro_seeds[1].ordinal = 2;
    lock.full_digest = sha256(&compiler_lock_hash_input(lock));
    assert_eq!(
        stage15_transformation_input(&seed_mismatch),
        Err(Stage15TransformError::ExpansionDiagnostic)
    );

    let named = named_target_definition();
    let mut unmapped = compile_locked(
        "a Focus.Named; the red Focus.Named; a blue Focus.Named",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&named),
        Some(19),
        LIMITS,
    );
    let inku_ddl::ExpandedMacroNode::Emit {
        binding: Some(target),
        ..
    } = &mut unmapped.macro_expansion.as_mut().unwrap().expanded[1].nodes[1]
    else {
        panic!("named fixture retains the generated target owner");
    };
    target.invocation_ordinal += 99;
    assert_eq!(
        stage15_transformation_input(&unmapped),
        Err(Stage15TransformError::ExpansionDiagnostic)
    );
}

#[test]
fn step9h_nested_coupled_provenance_tamper_is_rejected() {
    let definition = MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Review","heading":"Nested","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"group","body":[{"op":"transform","transform":{"translate_x":{"expr":"number","value":0.25},"translate_y":null,"scale_x":null,"scale_y":null,"rotate_degrees":null},"body":[{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"center"}}}]}]}]}"#,
    )
    .unwrap();
    let mut coupled = compile_locked(
        "Review.Nested",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
        Some(19),
        LIMITS,
    );
    assert!(stage15_transformation_input(&coupled).is_ok());

    let ExpandedMacroNode::Group { body, .. } =
        &mut coupled.macro_expansion.as_mut().unwrap().expanded[0].nodes[0]
    else {
        panic!("nested fixture starts with a generated group");
    };
    let ExpandedMacroNode::Transform { body, .. } = &mut body[0] else {
        panic!("nested fixture group contains a generated transform");
    };
    let ExpandedMacroNode::Emit { provenance, .. } = &mut body[0] else {
        panic!("nested fixture transform contains a generated emit");
    };
    provenance.invocation.invocation_ordinal += 1;
    assert_eq!(
        expanded_meaning_canonical_bytes(
            &coupled.semantic_document.as_ref().unwrap().ast,
            coupled.macro_expansion.as_ref().unwrap(),
        ),
        Err(MacroExpansionDiagnosticKind::ProvenanceOwnershipMismatch)
    );

    let generated_provenance_digest = sha256(&expanded_generated_provenance_canonical_bytes(
        coupled.macro_expansion.as_ref().unwrap(),
    ));
    let lock = coupled.compiler_lock.as_mut().unwrap();
    lock.expanded_generated_provenance_digest = Some(generated_provenance_digest);
    lock.full_digest = sha256(&compiler_lock_hash_input(lock));

    assert_eq!(
        stage15_transformation_input(&coupled),
        Err(Stage15TransformError::ExpansionDiagnostic)
    );
}

#[test]
fn coupled_seed_and_generated_provenance_tamper_is_rejected() {
    let definition = center_emit_definition();
    let mut coupled = compile_locked(
        "Focus.Center",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
        Some(19),
        LIMITS,
    );
    let tampered_full_digest = "0000000000000000000000000000000000000000000000000000000000000001";
    let tampered_resolved_seed = coupled.compiler_lock.as_ref().unwrap().macro_seeds[0]
        .resolved_seed
        .wrapping_add(1);
    {
        let seed = &mut coupled.compiler_lock.as_mut().unwrap().macro_seeds[0];
        seed.full_digest = tampered_full_digest.to_owned();
        seed.resolved_seed = tampered_resolved_seed;
    }
    {
        let invocation = &mut coupled.macro_expansion.as_mut().unwrap().expanded[0];
        rewrite_seed_provenance(
            &mut invocation.provenance,
            tampered_full_digest,
            tampered_resolved_seed,
        );
        for node in &mut invocation.nodes {
            rewrite_node_seed_provenance(node, tampered_full_digest, tampered_resolved_seed);
        }
    }
    let generated_provenance_digest = sha256(&expanded_generated_provenance_canonical_bytes(
        coupled.macro_expansion.as_ref().unwrap(),
    ));
    let lock = coupled.compiler_lock.as_mut().unwrap();
    lock.expanded_generated_provenance_digest = Some(generated_provenance_digest);
    lock.full_digest = sha256(&compiler_lock_hash_input(lock));

    assert_eq!(
        stage15_transformation_input(&coupled),
        Err(Stage15TransformError::ExpansionDiagnostic)
    );
}

#[test]
fn definite_imperative_object_groups_do_not_reach_stage15() {
    for source in ["place the circle and a line.", "place the circle and line."] {
        let compilation = compile(
            source,
            ResolvedInstructionLanguage::En,
            &[],
            Some(0),
            LIMITS,
        );
        let state = compilation.compiler_lock.as_ref().unwrap().state;
        assert_ne!(state, CompilerLockState::CanonicalReady, "{source}");
        assert!(
            compilation
                .semantic_document
                .as_ref()
                .unwrap()
                .canonical_bytes
                .is_none(),
            "{source}"
        );
        assert_eq!(
            stage15_transformation_input(&compilation),
            Err(Stage15TransformError::CompilerState(state)),
            "{source}"
        );
    }

    let definition = center_emit_definition();
    let source = "place the Focus.Center and a line.";
    let compilation = compile_locked(
        source,
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
        Some(0),
        LIMITS,
    );
    let state = compilation.compiler_lock.as_ref().unwrap().state;
    assert_ne!(state, CompilerLockState::CanonicalReady);
    let semantic = compilation.semantic_document.as_ref().unwrap();
    assert_eq!(semantic.ast.instructions.len(), 2);
    assert!(matches!(
        semantic.ast.instructions[0].entity.head,
        SemanticHead::MacroInvocation(_)
    ));
    assert_eq!(
        semantic.ast.instructions[0].entity.head.source().surface,
        "Focus.Center"
    );
    assert!(semantic.canonical_bytes.is_none());
    assert_eq!(
        stage15_transformation_input(&compilation),
        Err(Stage15TransformError::CompilerState(state))
    );
}

#[test]
fn canonical_ready_gate_and_target_integrity_fail_closed() {
    for (source, expected_state) in [
        ("many", CompilerLockState::IncompleteKnownHole),
        (
            "line. place the line.",
            CompilerLockState::BlockedDiagnostic,
        ),
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
    let semantic_ast = duplicate.semantic_document.as_ref().unwrap().ast.clone();
    let expansion = duplicate.macro_expansion.as_mut().unwrap();
    let duplicated_node = expansion.expanded[0].nodes[0].clone();
    expansion.expanded[0].nodes.push(duplicated_node);
    let lock = duplicate.compiler_lock.as_mut().unwrap();
    lock.expanded_meaning_digest = Some(sha256(
        &expanded_meaning_canonical_bytes(&semantic_ast, expansion).unwrap(),
    ));
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

fn rewrite_seed_provenance(
    provenance: &mut MacroInvocationProvenance,
    full_digest: &str,
    resolved_seed: u64,
) {
    provenance.seed_full_digest = full_digest.to_owned();
    provenance.resolved_seed = resolved_seed;
}

fn rewrite_node_seed_provenance(
    node: &mut ExpandedMacroNode,
    full_digest: &str,
    resolved_seed: u64,
) {
    match node {
        ExpandedMacroNode::Emit { provenance, .. }
        | ExpandedMacroNode::Anchor { provenance, .. }
        | ExpandedMacroNode::Relation { provenance, .. } => {
            rewrite_seed_provenance(&mut provenance.invocation, full_digest, resolved_seed);
        }
        ExpandedMacroNode::Group {
            body, provenance, ..
        }
        | ExpandedMacroNode::Transform {
            body, provenance, ..
        } => {
            rewrite_seed_provenance(&mut provenance.invocation, full_digest, resolved_seed);
            for child in body {
                rewrite_node_seed_provenance(child, full_digest, resolved_seed);
            }
        }
    }
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

fn unused_sidecar_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Spare","heading":"Unused","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"left_edge"}}}]}"#,
    )
    .unwrap()
}

fn extra_sidecar_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Spare","heading":"Extra","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"center"}}}]}"#,
    )
    .unwrap()
}

fn replacement_center_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Focus","heading":"Center","version":"2.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"place":{"expr":"semantic_ref","category":"place","id":"left_edge"}}}]}"#,
    )
    .unwrap()
}

fn refresh_full_lock(compilation: &mut inku_ddl::TypedDdlCompilation) {
    let lock = compilation.compiler_lock.as_mut().unwrap();
    lock.full_digest = sha256(&compiler_lock_hash_input(lock));
}

fn refresh_semantic_source_provenance_and_full_lock(
    compilation: &mut inku_ddl::TypedDdlCompilation,
) {
    let semantic = compilation.semantic_document.as_ref().unwrap();
    let digest = sha256(&semantic_source_provenance_canonical_bytes(&semantic.ast));
    let lock = compilation.compiler_lock.as_mut().unwrap();
    lock.semantic_source_provenance_digest = Some(digest);
    lock.full_digest = sha256(&compiler_lock_hash_input(lock));
}

fn named_target_definition() -> MacroDefinition {
    MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Focus","heading":"Named","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"anchor","name":"origin"},{"op":"emit","binding":"center","fields":{"place":{"expr":"semantic_ref","category":"place","id":"center"}}},{"op":"relation","kind":"touching","from":"origin","to":"center"}]}"#,
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
