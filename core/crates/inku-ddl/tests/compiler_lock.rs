use std::collections::HashSet;

use inku_ddl::{
    CANONICAL_SEMANTIC_DDL_SCHEMA_ID, CompilerLockState, MacroDefinition, MacroExpansionLimits,
    MacroLock, NormalizedDdlDocument, RelationReferenceEvidenceAvailability,
    ResolvedInstructionLanguage, SEMANTIC_DOCUMENT_SCHEMA_ID, SemanticDeliveryOwner, SemanticHead,
    TYPED_DDL_COMPILATION_SCHEMA_ID, TYPED_DDL_COMPILER_LOCK_SCHEMA_ID, bind_macro_parameters,
    compile_typed_ddl, expanded_meaning_canonical_bytes, saijiki_asset,
};
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

const FIXTURE: &str = include_str!("fixtures/compiler-lock-visible-patch-v6.json");
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
    definition: Value,
    known_answers: KnownAnswers,
    delivery_case_ids: Vec<String>,
    patch_case_ids: Vec<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct KnownAnswers {
    canonical_bytes: String,
    canonical_sha256: String,
    seed_digest: String,
    expanded_meaning_sha256: String,
    full_lock_digest: String,
}

#[test]
fn structured_document_is_the_only_pre_expansion_meaning_authority() {
    let result = compile(
        "eight white circle",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    let semantic_document = result
        .semantic_document
        .as_ref()
        .expect("an integrity-valid compilation owns the I-595 result");

    assert_eq!(
        CANONICAL_SEMANTIC_DDL_SCHEMA_ID,
        SEMANTIC_DOCUMENT_SCHEMA_ID
    );
    assert_eq!(
        result.pre_expansion_canonical_bytes(),
        semantic_document.canonical_bytes.as_deref()
    );
    assert_eq!(
        result
            .compiler_lock
            .as_ref()
            .unwrap()
            .canonical_pre_expansion_digest,
        semantic_document.canonical_bytes.as_deref().map(sha256)
    );
}

#[test]
fn multi_head_sequence_reaches_lock_while_unresolved_fields_are_conflicts() {
    let forward = compile(
        "circle line",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    let reverse = compile(
        "line circle",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    for result in [&forward, &reverse] {
        assert_eq!(
            result.compiler_lock.as_ref().map(|lock| lock.state),
            Some(CompilerLockState::CanonicalReady)
        );
        assert_eq!(
            result
                .deliveries
                .iter()
                .filter(|delivery| delivery.identity.owner == SemanticDeliveryOwner::EntityHead)
                .count(),
            2
        );
    }
    assert_ne!(
        forward.pre_expansion_canonical_bytes(),
        reverse.pre_expansion_canonical_bytes()
    );
    assert_ne!(
        forward.compiler_lock.as_ref().unwrap().full_digest,
        reverse.compiler_lock.as_ref().unwrap().full_digest
    );

    let unresolved = compile(
        "circle line red eight",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    assert_eq!(
        unresolved.compiler_lock.as_ref().map(|lock| lock.state),
        Some(CompilerLockState::BlockedConflict)
    );
    assert_eq!(unresolved.conflicts.len(), 2);
    assert_eq!(
        unresolved
            .deliveries
            .iter()
            .filter(|delivery| delivery.identity.owner == SemanticDeliveryOwner::EntityHead)
            .count(),
        2
    );
    assert_eq!(
        unresolved
            .deliveries
            .iter()
            .filter(|delivery| delivery.kind == inku_ddl::SemanticDeliveryKind::Conflict)
            .count(),
        2
    );

    let instruction_ambiguity = compile(
        "place center circle line",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    assert_eq!(instruction_ambiguity.conflicts.len(), 2);
    assert_eq!(
        instruction_ambiguity
            .deliveries
            .iter()
            .filter(|delivery| delivery.identity.owner == SemanticDeliveryOwner::EntityHead)
            .count(),
        2
    );

    let relation = saijiki_asset()
        .relations
        .iter()
        .find(|relation| relation.relation_type == "touching")
        .and_then(|relation| relation.literals_en.first())
        .expect("accepted touching relation has one EN full literal");
    let relation_ambiguity = compile(
        &format!("circle line {relation}"),
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    assert_eq!(relation_ambiguity.conflicts.len(), 1);
    assert_eq!(
        relation_ambiguity.conflicts[0].kind,
        "ambiguous_current_relation_ownership"
    );

    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Empty","version":"1.0.0","parameters":{},"components":{},"body":[]}"#,
    );
    for (source, macro_index) in [("Canon.Empty circle", 0), ("circle Canon.Empty", 1)] {
        let result = compile_locked(
            source,
            ResolvedInstructionLanguage::En,
            std::slice::from_ref(&definition),
            None,
            LIMITS,
        );
        assert_eq!(
            result.compiler_lock.as_ref().map(|lock| lock.state),
            Some(CompilerLockState::CanonicalReady),
            "{source}"
        );
        let document = result.semantic_document.as_ref().unwrap();
        assert_eq!(document.ast.instructions.len(), 2, "{source}");
        assert!(matches!(
            document.ast.instructions[macro_index].entity.head,
            SemanticHead::MacroInvocation(_)
        ));
        assert_eq!(
            result
                .deliveries
                .iter()
                .filter(|delivery| delivery.identity.owner == SemanticDeliveryOwner::EntityHead)
                .count(),
            2,
            "{source}"
        );
    }
}

#[test]
fn pre_head_modifier_ownership_reaches_compiler_for_primitive_and_macro_heads() {
    let primitive = compile(
        "red circle blue line",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    assert_eq!(
        primitive.compiler_lock.as_ref().map(|lock| lock.state),
        Some(CompilerLockState::CanonicalReady)
    );
    assert_eq!(
        primitive
            .deliveries
            .iter()
            .filter(|delivery| delivery.identity.owner == SemanticDeliveryOwner::EntityHead)
            .count(),
        2
    );

    let thin_primitive = compile(
        "thin circle",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    assert_eq!(
        thin_primitive
            .deliveries
            .iter()
            .filter(|delivery| delivery.identity.owner == SemanticDeliveryOwner::Thinness)
            .count(),
        1
    );
    let thin_delivery = thin_primitive
        .deliveries
        .iter()
        .find(|delivery| delivery.identity.owner == SemanticDeliveryOwner::Thinness)
        .unwrap();
    assert_eq!(thin_delivery.identity.canonical_key, "fine");
    assert_eq!(
        thin_delivery
            .span
            .map(|span| &thin_primitive.document.source()[span.start_byte..span.end_byte]),
        Some("thin")
    );
    assert_eq!(
        primitive
            .deliveries
            .iter()
            .filter(|delivery| delivery.identity.owner == SemanticDeliveryOwner::Color)
            .count(),
        2
    );

    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Empty","version":"1.0.0","parameters":{},"components":{},"body":[]}"#,
    );
    for (source, macro_index) in [
        ("red Canon.Empty blue circle", 0),
        ("red circle blue Canon.Empty", 1),
    ] {
        let result = compile_locked(
            source,
            ResolvedInstructionLanguage::En,
            std::slice::from_ref(&definition),
            None,
            LIMITS,
        );
        assert_eq!(
            result.compiler_lock.as_ref().map(|lock| lock.state),
            Some(CompilerLockState::CanonicalReady),
            "{source}"
        );
        let document = result.semantic_document.as_ref().unwrap();
        assert_eq!(
            document
                .ast
                .instructions
                .iter()
                .map(|instruction| {
                    instruction
                        .entity
                        .color
                        .as_ref()
                        .unwrap()
                        .identity
                        .id
                        .as_str()
                })
                .collect::<Vec<_>>(),
            ["red", "blue"],
            "{source}"
        );
        assert!(matches!(
            document.ast.instructions[macro_index].entity.head,
            SemanticHead::MacroInvocation(_)
        ));
    }

    let thin_macro = compile_locked(
        "thin Canon.Empty blue circle",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
        None,
        LIMITS,
    );
    assert_eq!(
        thin_macro
            .deliveries
            .iter()
            .filter(|delivery| delivery.identity.owner == SemanticDeliveryOwner::Thinness)
            .count(),
        1
    );
    assert!(thin_macro.deliveries.iter().all(|delivery| {
        !(delivery.identity.owner == SemanticDeliveryOwner::MacroParameter
            && delivery
                .span
                .map(|span| &thin_macro.document.source()[span.start_byte..span.end_byte])
                == Some("thin"))
    }));
}

#[test]
fn complete_binding_and_unbound_outer_modifier_keep_distinct_typed_owners() {
    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Color","version":"1.0.0","parameters":{"value":{"type":"semantic_ref","category":"color"}},"components":{},"body":[]}"#,
    );
    let result = compile_locked(
        "eight Canon.Color white",
        ResolvedInstructionLanguage::En,
        &[definition],
        Some(11),
        LIMITS,
    );
    let semantic_document = result.semantic_document.as_ref().unwrap();
    let instruction = &semantic_document.ast.instructions[0];
    let SemanticHead::MacroInvocation(head) = &instruction.entity.head else {
        panic!("expected resolved MacroInvocation head");
    };

    assert_eq!(head.parameters.len(), 1);
    assert_eq!(head.parameters[0].name, "value");
    assert_eq!(
        instruction
            .entity
            .quantity
            .as_ref()
            .map(|value| value.value),
        Some(8)
    );
    assert!(result.deliveries.iter().any(|delivery| {
        delivery.identity.owner == SemanticDeliveryOwner::MacroParameter
            && delivery
                .identity
                .canonical_key
                .contains("semantic_ref:color:white")
    }));
    assert!(result.deliveries.iter().any(|delivery| {
        delivery.identity.owner == SemanticDeliveryOwner::Quantity
            && delivery.identity.canonical_key == "8"
    }));
    assert_eq!(
        result.pre_expansion_canonical_bytes(),
        semantic_document.canonical_bytes.as_deref()
    );
    assert_eq!(
        result.accepted_parameter_binding(),
        result
            .macro_expansion
            .as_ref()
            .map(|expansion| &expansion.parameter_binding)
    );
}

#[test]
fn same_macro_meaning_across_language_and_format_has_same_seed_not_source_digest() {
    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Empty","version":"1.0.0","parameters":{},"components":{},"body":[]}"#,
    );
    let en = compile_locked(
        "  Canon.Empty  ",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
        Some(23),
        LIMITS,
    );
    let ja = compile_locked(
        "Canon.Empty",
        ResolvedInstructionLanguage::Ja,
        &[definition],
        Some(23),
        LIMITS,
    );

    assert_eq!(
        en.pre_expansion_canonical_bytes(),
        ja.pre_expansion_canonical_bytes()
    );
    assert_eq!(
        en.derived_seeds[0].full_digest_hex(),
        ja.derived_seeds[0].full_digest_hex()
    );
    assert_ne!(
        en.compiler_lock.as_ref().unwrap().visible_source_digest,
        ja.compiler_lock.as_ref().unwrap().visible_source_digest
    );
}

#[test]
fn i579_exact_one_availability_is_not_promoted_to_typed_relation_meaning() {
    let result = compile(
        "eight along circle",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    let binding = result.accepted_parameter_binding().unwrap();
    assert_eq!(
        binding
            .macro_resolution
            .relation_reference_evidence
            .evidence[0]
            .availability,
        RelationReferenceEvidenceAvailability::ExactOne
    );
    assert!(
        result
            .semantic_document
            .as_ref()
            .unwrap()
            .ast
            .instructions
            .iter()
            .all(|instruction| instruction.relation.is_none())
    );
    assert!(
        result
            .deliveries
            .iter()
            .all(|delivery| { delivery.identity.owner != SemanticDeliveryOwner::Relation })
    );
}

#[test]
fn structured_ownership_action_position_ground_and_previous_relation_change_the_lock() {
    let plain = compile("circle", ResolvedInstructionLanguage::En, &[], None, LIMITS);
    let action_position = compile(
        "place circle at center",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    let grounded = compile(
        "paper. place circle at center",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    let left_owned = compile(
        "white circle. square.",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    let right_owned = compile(
        "circle. white square.",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );

    let relation_literal = saijiki_asset()
        .relations
        .iter()
        .find(|relation| relation.relation_type == "along")
        .and_then(|relation| relation.literals_en.first())
        .expect("accepted along relation has an English full literal");
    let relation = compile(
        &format!("line. circle {relation_literal}."),
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );

    for result in [
        &plain,
        &action_position,
        &grounded,
        &left_owned,
        &right_owned,
        &relation,
    ] {
        assert_eq!(
            result.compiler_lock.as_ref().unwrap().state,
            CompilerLockState::CanonicalReady
        );
    }
    assert_ne!(
        canonical_bytes_of(&plain),
        canonical_bytes_of(&action_position)
    );
    assert_ne!(
        canonical_bytes_of(&action_position),
        canonical_bytes_of(&grounded)
    );
    assert_ne!(
        canonical_bytes_of(&left_owned),
        canonical_bytes_of(&right_owned)
    );
    assert!(relation.deliveries.iter().any(|delivery| {
        delivery.identity.owner == SemanticDeliveryOwner::Relation
            && delivery.identity.canonical_key == "along:previous_one"
    }));
    assert_ne!(canonical_bytes_of(&plain), canonical_bytes_of(&relation));
    assert_ne!(
        plain.compiler_lock.as_ref().unwrap().full_digest,
        relation.compiler_lock.as_ref().unwrap().full_digest
    );
}

#[test]
fn lexical_place_aliases_share_compiler_meaning_and_keep_source_provenance() {
    let center = compile(
        "place circle at center",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    let middle = compile(
        "place circle at middle",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );

    assert_eq!(canonical_bytes_of(&center), canonical_bytes_of(&middle));
    assert_eq!(
        center
            .compiler_lock
            .as_ref()
            .unwrap()
            .expanded_meaning_digest,
        middle
            .compiler_lock
            .as_ref()
            .unwrap()
            .expanded_meaning_digest
    );
    for (result, source_surface) in [(&center, "center"), (&middle, "middle")] {
        let position = result.semantic_document.as_ref().unwrap().ast.instructions[0]
            .position
            .as_ref()
            .unwrap();
        assert_eq!(position.identity.category, "place");
        assert_eq!(position.identity.id, "center");
        assert_eq!(position.provenance.source.surface, source_surface);
    }
}

#[test]
fn spec_ja_and_en_clause_topology_reaches_one_compiler_meaning() {
    let ja = compile(
        "中心に、鉛筆の細い線をひとつ置く。",
        ResolvedInstructionLanguage::Ja,
        &[],
        None,
        LIMITS,
    );
    let en = compile(
        "place one thin pencil line at the center",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );

    for result in [&ja, &en] {
        assert_eq!(
            result.compiler_lock.as_ref().unwrap().state,
            CompilerLockState::CanonicalReady
        );
        assert_eq!(result.delivery_summary.recognized_but_ignored, 0);
        for owner in [
            SemanticDeliveryOwner::Quantity,
            SemanticDeliveryOwner::Thinness,
            SemanticDeliveryOwner::Touch,
            SemanticDeliveryOwner::Action,
            SemanticDeliveryOwner::Position,
        ] {
            assert_eq!(
                result
                    .deliveries
                    .iter()
                    .filter(|delivery| delivery.identity.owner == owner)
                    .count(),
                1,
                "{owner:?}"
            );
        }
    }
    assert_eq!(
        ja.pre_expansion_canonical_bytes(),
        en.pre_expansion_canonical_bytes()
    );
    assert_eq!(
        ja.compiler_lock
            .as_ref()
            .unwrap()
            .canonical_pre_expansion_digest,
        en.compiler_lock
            .as_ref()
            .unwrap()
            .canonical_pre_expansion_digest
    );
    assert_ne!(
        ja.compiler_lock.as_ref().unwrap().visible_source_digest,
        en.compiler_lock.as_ref().unwrap().visible_source_digest
    );
}

#[test]
fn canonical_known_answers_bind_seed_expand_and_lock_exactly() {
    let fixture = fixture();
    let definition = fixture_definition(&fixture);
    let document = locked_document("Canon.Empty", ResolvedInstructionLanguage::En, &definition);
    let accepted = bind_macro_parameters(&document, &[definition.clone()]).unwrap();
    let result = compile_typed_ddl(document, &[definition], Some(7), LIMITS);

    assert_eq!(result.schema_id, TYPED_DDL_COMPILATION_SCHEMA_ID);
    assert_eq!(result.accepted_parameter_binding(), Some(&accepted));
    assert!(
        result
            .semantic_document
            .as_ref()
            .unwrap()
            .instruction_association
            .association
            .macro_parameter_binding
            .is_none()
    );
    let expansion = result.macro_expansion.as_ref().unwrap();
    assert_eq!(&expansion.parameter_binding, &accepted);
    assert!(expansion.diagnostics.is_empty());
    assert_eq!(result.derived_seeds.len(), 1);

    let canonical = result.pre_expansion_canonical_bytes().unwrap();
    let lock = result.compiler_lock.as_ref().unwrap();
    assert_eq!(lock.schema_id, TYPED_DDL_COMPILER_LOCK_SCHEMA_ID);
    assert_eq!(lock.state, CompilerLockState::CanonicalReady);

    let actual = KnownAnswers {
        canonical_bytes: std::str::from_utf8(canonical).unwrap().to_owned(),
        canonical_sha256: sha256(canonical),
        seed_digest: result.derived_seeds[0].full_digest_hex().to_owned(),
        expanded_meaning_sha256: sha256(&expanded_meaning_canonical_bytes(expansion)),
        full_lock_digest: lock.full_digest.clone(),
    };
    if fixture.known_answers.canonical_bytes == "__UPDATE__" {
        panic!(
            "known answers: canonical_bytes={:?} canonical_sha256={} seed_digest={} expanded_meaning_sha256={} full_lock_digest={}",
            actual.canonical_bytes,
            actual.canonical_sha256,
            actual.seed_digest,
            actual.expanded_meaning_sha256,
            actual.full_lock_digest
        );
    }
    assert_eq!(
        actual.canonical_bytes,
        fixture.known_answers.canonical_bytes
    );
    assert_eq!(
        actual.canonical_sha256,
        fixture.known_answers.canonical_sha256
    );
    assert_eq!(actual.seed_digest, fixture.known_answers.seed_digest);
    assert_eq!(
        actual.expanded_meaning_sha256,
        fixture.known_answers.expanded_meaning_sha256
    );
    assert_eq!(
        actual.full_lock_digest,
        fixture.known_answers.full_lock_digest
    );
    assert_eq!(
        lock.canonical_pre_expansion_digest,
        Some(actual.canonical_sha256)
    );
    assert_eq!(
        lock.expanded_meaning_digest,
        Some(actual.expanded_meaning_sha256)
    );
    assert_eq!(lock.macro_seeds[0].full_digest, actual.seed_digest);
}

#[test]
fn language_format_and_approved_order_project_to_same_semantics_but_not_source_lock() {
    let ja = compile(
        "八つ  白 円",
        ResolvedInstructionLanguage::Ja,
        &[],
        None,
        LIMITS,
    );
    let en = compile(
        "eight white circle",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    let en_format = compile(
        "  eight   white circle.  ",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    for result in [&ja, &en, &en_format] {
        assert_eq!(
            result.compiler_lock.as_ref().unwrap().state,
            CompilerLockState::CanonicalReady
        );
        assert_eq!(
            result.compiler_lock.as_ref().unwrap().composition_seed,
            Some(0)
        );
        assert_eq!(result.delivery_summary.recognized_but_ignored, 0);
    }
    assert_eq!(
        ja.pre_expansion_canonical_bytes(),
        en.pre_expansion_canonical_bytes()
    );
    assert_eq!(
        en.pre_expansion_canonical_bytes(),
        en_format.pre_expansion_canonical_bytes()
    );
    assert_eq!(
        ja.compiler_lock
            .as_ref()
            .unwrap()
            .canonical_pre_expansion_digest,
        en.compiler_lock
            .as_ref()
            .unwrap()
            .canonical_pre_expansion_digest
    );
    assert_ne!(
        ja.compiler_lock.as_ref().unwrap().visible_source_digest,
        en.compiler_lock.as_ref().unwrap().visible_source_digest
    );
    assert_ne!(
        ja.compiler_lock.as_ref().unwrap().full_digest,
        en.compiler_lock.as_ref().unwrap().full_digest
    );

    let different_number = compile(
        "twelve white circle",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    assert_ne!(
        en.pre_expansion_canonical_bytes(),
        different_number.pre_expansion_canonical_bytes()
    );
    let different_multiplicity = compile(
        "circle eight white circle",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        LIMITS,
    );
    assert_ne!(
        en.pre_expansion_canonical_bytes(),
        different_multiplicity.pre_expansion_canonical_bytes()
    );
}

#[test]
fn definition_identity_changes_structured_meaning_seed_and_lock_but_not_expanded_nodes() {
    let plain = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Meaning","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"}}}]}"#,
    );
    let unused_component = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Meaning","version":"1.0.0","parameters":{},"components":{"unused":{"parameters":{},"body":[]}},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"}}}]}"#,
    );
    assert_ne!(
        plain.identity().unwrap().full_digest_hex(),
        unused_component.identity().unwrap().full_digest_hex()
    );

    let left = compile_locked(
        "Canon.Meaning",
        ResolvedInstructionLanguage::En,
        &[plain.clone()],
        Some(17),
        LIMITS,
    );
    let right = compile_locked(
        "Canon.Meaning",
        ResolvedInstructionLanguage::En,
        &[unused_component],
        Some(17),
        LIMITS,
    );
    assert_ne!(
        left.pre_expansion_canonical_bytes(),
        right.pre_expansion_canonical_bytes()
    );
    assert_ne!(
        left.derived_seeds[0].full_digest_hex(),
        right.derived_seeds[0].full_digest_hex()
    );
    assert_eq!(
        left.compiler_lock.as_ref().unwrap().expanded_meaning_digest,
        right
            .compiler_lock
            .as_ref()
            .unwrap()
            .expanded_meaning_digest
    );
    assert_ne!(
        left.compiler_lock.as_ref().unwrap().definition_identities,
        right.compiler_lock.as_ref().unwrap().definition_identities
    );
    assert_ne!(
        left.compiler_lock.as_ref().unwrap().full_digest,
        right.compiler_lock.as_ref().unwrap().full_digest
    );

    let different_composition_seed = compile_locked(
        "Canon.Meaning",
        ResolvedInstructionLanguage::En,
        &[plain],
        Some(18),
        LIMITS,
    );
    assert_eq!(
        left.pre_expansion_canonical_bytes(),
        different_composition_seed.pre_expansion_canonical_bytes()
    );
    assert_ne!(
        left.derived_seeds[0].full_digest_hex(),
        different_composition_seed.derived_seeds[0].full_digest_hex()
    );
    assert_eq!(
        left.compiler_lock.as_ref().unwrap().expanded_meaning_digest,
        different_composition_seed
            .compiler_lock
            .as_ref()
            .unwrap()
            .expanded_meaning_digest
    );
    assert_ne!(
        left.compiler_lock.as_ref().unwrap().full_digest,
        different_composition_seed
            .compiler_lock
            .as_ref()
            .unwrap()
            .full_digest
    );
}

#[test]
fn exhaustive_delivery_mapping_has_no_default_or_ignored_bucket() {
    let fixture = fixture();
    let definition = fixture_definition(&fixture);
    let color = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Color","version":"1.0.0","parameters":{"value":{"type":"semantic_ref","category":"color"}},"components":{},"body":[]}"#,
    );
    let emits_two = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"Two","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{}},{"op":"emit","binding":null,"fields":{}}]}"#,
    );

    let cases = [
        (
            "explicit-and-syntax",
            compile(
                "the circle",
                ResolvedInstructionLanguage::En,
                &[],
                None,
                LIMITS,
            ),
            CompilerLockState::CanonicalReady,
        ),
        (
            "core-thinness-explicit",
            compile(
                "thin circle",
                ResolvedInstructionLanguage::En,
                &[],
                None,
                LIMITS,
            ),
            CompilerLockState::CanonicalReady,
        ),
        (
            "relation-zero-hole",
            compile(
                "eight along twelve",
                ResolvedInstructionLanguage::En,
                &[],
                None,
                LIMITS,
            ),
            CompilerLockState::BlockedDiagnostic,
        ),
        (
            "relation-exact-one",
            compile(
                "eight along circle",
                ResolvedInstructionLanguage::En,
                &[],
                None,
                LIMITS,
            ),
            CompilerLockState::CanonicalReady,
        ),
        (
            "head-only-multiple-ready",
            compile(
                "circle with line of square",
                ResolvedInstructionLanguage::En,
                &[],
                None,
                LIMITS,
            ),
            CompilerLockState::CanonicalReady,
        ),
        (
            "parser-hole",
            compile("many", ResolvedInstructionLanguage::En, &[], None, LIMITS),
            CompilerLockState::IncompleteKnownHole,
        ),
        (
            "unknown-blocking",
            compile(
                "mystery",
                ResolvedInstructionLanguage::En,
                &[],
                None,
                LIMITS,
            ),
            CompilerLockState::BlockedDiagnostic,
        ),
        (
            "macro-missing-hole",
            compile(
                "Canon.Empty",
                ResolvedInstructionLanguage::En,
                &[definition.clone()],
                None,
                LIMITS,
            ),
            CompilerLockState::IncompleteKnownHole,
        ),
        (
            "macro-ambiguous-conflict",
            compile_locked(
                "Canon.Color white black",
                ResolvedInstructionLanguage::En,
                &[color.clone()],
                None,
                LIMITS,
            ),
            CompilerLockState::BlockedDiagnostic,
        ),
        (
            "expansion-diagnostic-hole",
            compile_locked(
                "Canon.Two",
                ResolvedInstructionLanguage::En,
                &[emits_two],
                None,
                MacroExpansionLimits {
                    max_nodes_per_invocation: 1,
                    ..LIMITS
                },
            ),
            CompilerLockState::IncompleteKnownHole,
        ),
    ];
    let actual_ids = cases.iter().map(|(id, _, _)| *id).collect::<HashSet<_>>();
    assert_eq!(
        actual_ids,
        fixture
            .delivery_case_ids
            .iter()
            .map(String::as_str)
            .collect()
    );
    for (id, result, expected_state) in cases {
        assert_eq!(
            result.compiler_lock.as_ref().unwrap().state,
            expected_state,
            "{id}"
        );
        assert_eq!(
            result.pre_expansion_canonical_bytes(),
            result
                .semantic_document
                .as_ref()
                .and_then(|document| document.canonical_bytes.as_deref()),
            "{id}: I-595 result is the sole canonical authority"
        );
        assert_eq!(result.delivery_summary.unspecified, 0, "{id}");
        assert_eq!(result.delivery_summary.defaulted, 0, "{id}");
        assert_eq!(result.delivery_summary.recognized_but_ignored, 0, "{id}");
        assert_eq!(
            result.deliveries.len(),
            result.delivery_summary.explicit
                + result.delivery_summary.holes
                + result.delivery_summary.conflicts
                + result.delivery_summary.blocking_diagnostics
                + result.delivery_summary.syntax_only,
            "{id}"
        );
    }

    let invalid = compile(
        "circle",
        ResolvedInstructionLanguage::En,
        &[],
        None,
        MacroExpansionLimits {
            max_invocations: 0,
            ..LIMITS
        },
    );
    assert!(invalid.compiler_lock.is_none());
    assert_eq!(invalid.delivery_summary.blocking_diagnostics, 1);
}

#[test]
fn successful_expanded_nodes_are_explicit_deliveries_without_entering_pre_expansion_bytes() {
    let definition = definition_from(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Canon","heading":"One","version":"1.0.0","parameters":{},"components":{},"body":[{"op":"emit","binding":null,"fields":{"shape":{"expr":"semantic_ref","category":"shape","id":"circle"}}}]}"#,
    );
    let result = compile_locked(
        "Canon.One",
        ResolvedInstructionLanguage::En,
        &[definition],
        Some(3),
        LIMITS,
    );
    assert_eq!(
        result.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::CanonicalReady
    );
    assert_eq!(result.macro_expansion.as_ref().unwrap().expanded.len(), 1);
    assert!(
        result.deliveries.iter().any(
            |item| item.id.starts_with("expanded:") && item.descriptor.contains("semantic_ref")
        )
    );
    assert!(
        !std::str::from_utf8(result.pre_expansion_canonical_bytes().unwrap())
            .unwrap()
            .contains("semantic_ref")
    );
}

#[test]
fn incomplete_structured_document_retains_binding_and_does_not_seed_or_expand() {
    let fixture = fixture();
    let definition = fixture_definition(&fixture);
    let result = compile_locked(
        "Canon.Empty many",
        ResolvedInstructionLanguage::En,
        &[definition],
        Some(5),
        LIMITS,
    );
    assert_eq!(
        result.compiler_lock.as_ref().unwrap().state,
        CompilerLockState::IncompleteKnownHole
    );
    assert!(result.pre_expansion_canonical_bytes().is_none());
    assert_eq!(result.holes.len(), 1);
    assert!(result.derived_seeds.is_empty());
    assert!(
        result
            .semantic_document
            .as_ref()
            .unwrap()
            .instruction_association
            .association
            .macro_parameter_binding
            .is_some()
    );
    assert!(result.macro_expansion.is_none());
    let lock = result.compiler_lock.as_ref().unwrap();
    assert!(lock.canonical_pre_expansion_digest.is_none());
    assert!(lock.macro_seeds.is_empty());
    assert!(lock.expanded_meaning_digest.is_none());
}

#[test]
fn disabled_saijiki_row_uses_source_preserving_unknown_blocking_path() {
    let disabled = saijiki_asset()
        .categories
        .iter()
        .flat_map(|category| &category.words)
        .find(|word| !word.prompt && !word.display && word.marker != Some(true))
        .expect("accepted asset has one disabled tombstone");
    let source = disabled.surface_ja.clone();
    let source_digest = sha256(source.as_bytes());

    let result = compile(&source, ResolvedInstructionLanguage::Ja, &[], None, LIMITS);

    assert_eq!(result.document.source(), source);
    assert_eq!(result.document.source().len(), source.len());
    assert_eq!(sha256(result.document.source().as_bytes()), source_digest);
    assert_eq!(result.delivery_summary.blocking_diagnostics, 1);
    assert_eq!(
        result.compiler_lock.as_ref().map(|lock| lock.state),
        Some(CompilerLockState::BlockedDiagnostic)
    );
    assert!(result.derived_seeds.is_empty());
    assert!(result.macro_expansion.is_none());
    assert!(
        result
            .deliveries
            .iter()
            .any(|delivery| delivery.identity.owner == SemanticDeliveryOwner::TypedIssue)
    );
}

#[test]
fn fixture_schema_and_closed_ids_are_stable() {
    let fixture = fixture();
    assert_eq!(
        fixture.schema,
        "inku.compiler-lock-visible-patch-fixture.v6"
    );
    assert_eq!(fixture.version, 6);
    assert_eq!(
        CANONICAL_SEMANTIC_DDL_SCHEMA_ID,
        "inku.semantic-document.v8"
    );
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));
    assert_eq!(
        fixture
            .delivery_case_ids
            .iter()
            .collect::<HashSet<_>>()
            .len(),
        10
    );
    assert_eq!(
        fixture.patch_case_ids.iter().collect::<HashSet<_>>().len(),
        19
    );
}

fn fixture() -> Fixture {
    serde_json::from_str(FIXTURE).unwrap()
}

fn fixture_definition(fixture: &Fixture) -> MacroDefinition {
    definition_from(&serde_json::to_string(&fixture.definition).unwrap())
}

fn definition_from(value: &str) -> MacroDefinition {
    MacroDefinition::from_json(value).unwrap()
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

fn locked_document(
    source: &str,
    language: ResolvedInstructionLanguage,
    definition: &MacroDefinition,
) -> NormalizedDdlDocument {
    NormalizedDdlDocument::new(source, language, vec![lock_for(definition)]).unwrap()
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

fn sha256(value: &[u8]) -> String {
    Sha256::digest(value)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn canonical_bytes_of(result: &inku_ddl::TypedDdlCompilation) -> &[u8] {
    result
        .pre_expansion_canonical_bytes()
        .expect("focused input has complete I-595 canonical bytes")
}
