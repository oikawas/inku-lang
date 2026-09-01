use std::collections::{HashMap, HashSet};

use inku_ddl::{
    CanonicalPreviousReference, CanonicalRelationForm, ClauseAtom, ClauseSeparatorKind,
    ClauseStream, CoreRoleKind, MacroDefinition, MacroLock, NormalizedDdlDocument,
    OwnedSemanticOccurrence, RemainingRoleKind, ResolvedInstructionLanguage,
    SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID, SemanticAssociationResult, SemanticHead,
    SemanticMacroInvocationHead, SemanticMacroParameterValue, SourceOccurrence,
    associate_semantic_entities, associate_semantic_entities_with_macro_binding,
    bind_macro_parameters, project_macro_semantic_ref, saijiki_asset,
};
use serde::Deserialize;

const FIXTURE: &str = include_str!("fixtures/semantic-association-v10.json");

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Fixture {
    schema: String,
    version: u32,
    cases: Vec<Case>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    id: String,
    language: String,
    source: String,
    entity_count: usize,
    issue_kinds: Vec<String>,
    canonical: Option<String>,
    owned_occurrence_count: usize,
    #[serde(default)]
    explicit_touches: Vec<String>,
    #[serde(default)]
    explicit_thinnesses: Vec<String>,
    #[serde(default)]
    explicit_continuities: Vec<String>,
    #[serde(default)]
    explicit_angles: Vec<String>,
    #[serde(default)]
    surface_qualities: Vec<String>,
    #[serde(default)]
    surface_intensities: Vec<String>,
    #[serde(default)]
    fluctuation_amplitudes: Vec<String>,
    #[serde(default)]
    fluctuation_frequencies: Vec<String>,
    #[serde(default)]
    fluctuation_qualities: Vec<String>,
    #[serde(default)]
    proportion_aspects: Vec<String>,
    #[serde(default)]
    proportion_width_extents: Vec<String>,
    #[serde(default)]
    proportion_arc_forms: Vec<String>,
}

#[test]
fn fixture_associates_single_head_entities_without_surface_order_rules() {
    let fixture = load_fixture();
    let mut canonical_by_case = HashMap::new();

    for case in &fixture.cases {
        let document = NormalizedDdlDocument::new(
            case.source.clone(),
            parse_language(&case.language, &case.id),
            Vec::new(),
        )
        .unwrap_or_else(|error| panic!("{}: unexpected document diagnostic: {error}", case.id));
        let result = associate_semantic_entities(&document)
            .unwrap_or_else(|error| panic!("{}: unexpected clause-stream error: {error}", case.id));

        assert_eq!(
            result.schema_id, SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
            "{}",
            case.id
        );
        assert_eq!(result.ast.entities.len(), case.entity_count, "{}", case.id);
        assert_eq!(
            result
                .issues
                .iter()
                .map(|issue| issue.kind.as_str())
                .collect::<Vec<_>>(),
            case.issue_kinds
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}",
            case.id
        );
        assert_eq!(
            result.canonical_bytes.as_deref(),
            case.canonical.as_ref().map(String::as_bytes),
            "{}",
            case.id
        );
        assert_eq!(
            result.ast.complete,
            result.issues.is_empty(),
            "{}: only issue-free AST is complete",
            case.id
        );
        assert_eq!(
            result.owned_occurrence_count, case.owned_occurrence_count,
            "{}",
            case.id
        );
        assert_eq!(
            result.delivered_occurrence_count, result.owned_occurrence_count,
            "{}: every slice-owned occurrence must be delivered exactly once",
            case.id
        );
        assert!(
            result.explicit_previous_references.is_empty(),
            "{}: legacy fixture has no accepted full relation literal",
            case.id
        );
        assert_eq!(result.owned_compound_reference_count, 0, "{}", case.id);
        assert_eq!(result.delivered_compound_reference_count, 0, "{}", case.id);
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| entity.touch.as_ref().map(|term| term.identity.id.as_str()))
                .collect::<Vec<_>>(),
            case.explicit_touches
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Touch fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| {
                    entity
                        .thinness
                        .as_ref()
                        .map(|thinness| thinness.value.as_str())
                })
                .collect::<Vec<_>>(),
            case.explicit_thinnesses
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit core Thinness fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| {
                    entity
                        .fluctuation
                        .amplitude
                        .as_ref()
                        .map(|term| term.identity.id.as_str())
                })
                .collect::<Vec<_>>(),
            case.fluctuation_amplitudes
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Fluctuation amplitude fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| {
                    entity
                        .fluctuation
                        .frequency
                        .as_ref()
                        .map(|term| term.identity.id.as_str())
                })
                .collect::<Vec<_>>(),
            case.fluctuation_frequencies
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Fluctuation frequency fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| {
                    entity
                        .fluctuation
                        .quality
                        .as_ref()
                        .map(|term| term.identity.id.as_str())
                })
                .collect::<Vec<_>>(),
            case.fluctuation_qualities
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Fluctuation quality fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| {
                    entity
                        .proportion
                        .aspect
                        .as_ref()
                        .map(|term| term.identity.id.as_str())
                })
                .collect::<Vec<_>>(),
            case.proportion_aspects
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Proportion aspect fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| {
                    entity
                        .proportion
                        .width_extent
                        .as_ref()
                        .map(|term| term.identity.id.as_str())
                })
                .collect::<Vec<_>>(),
            case.proportion_width_extents
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Proportion width extent fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| {
                    entity
                        .proportion
                        .arc_form
                        .as_ref()
                        .map(|term| term.identity.id.as_str())
                })
                .collect::<Vec<_>>(),
            case.proportion_arc_forms
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Proportion arc form fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| {
                    entity
                        .surface
                        .quality
                        .as_ref()
                        .map(|term| term.identity.id.as_str())
                })
                .collect::<Vec<_>>(),
            case.surface_qualities
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Surface quality fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| {
                    entity
                        .surface
                        .intensity
                        .as_ref()
                        .map(|term| term.identity.id.as_str())
                })
                .collect::<Vec<_>>(),
            case.surface_intensities
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Surface intensity fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| entity
                    .continuity
                    .as_ref()
                    .map(|term| term.identity.id.as_str()))
                .collect::<Vec<_>>(),
            case.explicit_continuities
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Continuity fields",
            case.id
        );
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .filter_map(|entity| entity.angle.as_ref().map(|term| term.identity.id.as_str()))
                .collect::<Vec<_>>(),
            case.explicit_angles
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            "{}: explicit Angle fields",
            case.id
        );
        assert_source_provenance(case, &result);
        assert_owned_occurrence_join(case, &result);

        if let Some(canonical) = &case.canonical {
            canonical_by_case.insert(case.id.as_str(), canonical.as_str());
        }
    }

    let equivalent = [
        "ja-canonical-order-one",
        "ja-canonical-order-two",
        "en-canonical-order-one",
        "en-canonical-order-two",
        "en-case-comma-space-soft-line-break",
    ]
    .map(|id| canonical_by_case[id]);
    assert!(equivalent.windows(2).all(|pair| pair[0] == pair[1]));
    assert_ne!(
        canonical_by_case["ownership-a"],
        canonical_by_case["ownership-b"]
    );
    let styled_equivalent = [
        "ja-style-order-one",
        "ja-style-order-two",
        "en-style-order-one",
        "en-style-order-two",
        "style-soft-line-break",
    ]
    .map(|id| canonical_by_case[id]);
    assert!(styled_equivalent.windows(2).all(|pair| pair[0] == pair[1]));
    assert_ne!(
        canonical_by_case["en-style-order-one"],
        canonical_by_case["style-touch-contrast"]
    );
    assert_ne!(
        canonical_by_case["en-style-order-one"],
        canonical_by_case["style-continuity-contrast"]
    );
    assert_ne!(
        canonical_by_case["en-style-order-one"],
        canonical_by_case["style-angle-contrast"]
    );
    let surface_equivalent = [
        "ja-surface-order-one",
        "ja-surface-order-two",
        "en-surface-order-one",
        "en-surface-order-two",
        "surface-soft-line-break",
    ]
    .map(|id| canonical_by_case[id]);
    assert!(surface_equivalent.windows(2).all(|pair| pair[0] == pair[1]));
    assert_ne!(
        canonical_by_case["en-surface-order-one"],
        canonical_by_case["surface-quality-contrast"]
    );
    assert_ne!(
        canonical_by_case["en-surface-order-one"],
        canonical_by_case["surface-intensity-contrast"]
    );
    let fluctuation_equivalent = [
        "ja-fluctuation-order-one",
        "ja-fluctuation-order-two",
        "en-fluctuation-order-one",
        "en-fluctuation-order-two",
        "fluctuation-soft-line-break",
    ]
    .map(|id| canonical_by_case[id]);
    assert!(
        fluctuation_equivalent
            .windows(2)
            .all(|pair| pair[0] == pair[1])
    );
    assert_ne!(
        canonical_by_case["en-fluctuation-order-one"],
        canonical_by_case["fluctuation-amplitude-contrast"]
    );
    assert_ne!(
        canonical_by_case["en-fluctuation-order-one"],
        canonical_by_case["fluctuation-frequency-contrast"]
    );
    assert_ne!(
        canonical_by_case["en-fluctuation-order-one"],
        canonical_by_case["fluctuation-quality-contrast"]
    );
    let proportion_equivalent = [
        "ja-proportion-order-one",
        "ja-proportion-order-two",
        "en-proportion-order-one",
        "en-proportion-order-two",
    ]
    .map(|id| canonical_by_case[id]);
    assert!(
        proportion_equivalent
            .windows(2)
            .all(|pair| pair[0] == pair[1])
    );
    assert_ne!(
        canonical_by_case["en-proportion-order-one"],
        canonical_by_case["proportion-aspect-only"]
    );
    assert_ne!(
        canonical_by_case["en-proportion-order-one"],
        canonical_by_case["proportion-width-extent-only"]
    );
    assert_ne!(
        canonical_by_case["en-proportion-order-one"],
        canonical_by_case["proportion-arc-form-only"]
    );
}

#[test]
fn fixture_schema_and_required_semantic_boundaries_are_guarded() {
    let fixture = load_fixture();
    assert_eq!(
        SEMANTIC_ENTITY_ASSOCIATION_SCHEMA_ID,
        "inku.semantic-entity-association.v10"
    );
    assert_eq!(
        fixture.schema,
        "inku.semantic-entity-association-fixture.v10"
    );
    assert_eq!(fixture.version, 10);
    assert_eq!(FIXTURE.as_bytes().last(), Some(&b'\n'));

    let ids = fixture
        .cases
        .iter()
        .map(|case| case.id.as_str())
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), fixture.cases.len());
    for required in [
        "ja-canonical-order-one",
        "en-core-thinness",
        "ja-canonical-order-two",
        "en-canonical-order-one",
        "en-canonical-order-two",
        "en-case-comma-space-soft-line-break",
        "ownership-a",
        "ownership-b",
        "multi-head-ambiguity",
        "orphan-color",
        "orphan-quantity",
        "conflicting-colors",
        "conflicting-quantities",
        "upstream-hole-retained",
        "upstream-unknown-retained",
        "negative-quantity-remains-hole",
        "unobserved-order-and-vocabulary",
        "ja-style-order-one",
        "ja-style-order-two",
        "en-style-order-one",
        "en-style-order-two",
        "style-touch-only",
        "style-touch-contrast",
        "style-continuity-contrast",
        "style-angle-contrast",
        "conflicting-touches",
        "conflicting-continuities",
        "conflicting-angles",
        "orphan-style-terms",
        "multi-head-style-ambiguity",
        "regional-style-ownership",
        "style-soft-line-break",
        "style-upstream-issue-retained",
        "unobserved-primitive-style-combination",
        "ja-surface-order-one",
        "ja-surface-order-two",
        "en-surface-order-one",
        "en-surface-order-two",
        "surface-quality-only",
        "surface-intensity-only",
        "surface-quality-contrast",
        "surface-intensity-contrast",
        "conflicting-surface-qualities",
        "conflicting-surface-intensities",
        "orphan-surface-terms",
        "multi-head-surface-ambiguity",
        "regional-surface-ownership",
        "surface-soft-line-break",
        "surface-upstream-issue-retained",
        "unobserved-line-surface-combination",
        "unobserved-arc-surface-combination",
        "ja-fluctuation-order-one",
        "ja-fluctuation-order-two",
        "en-fluctuation-order-one",
        "en-fluctuation-order-two",
        "fluctuation-amplitude-only",
        "fluctuation-frequency-only",
        "fluctuation-quality-only",
        "fluctuation-amplitude-contrast",
        "fluctuation-frequency-contrast",
        "fluctuation-quality-contrast",
        "conflicting-fluctuation-amplitudes",
        "conflicting-fluctuation-frequencies",
        "conflicting-fluctuation-qualities",
        "orphan-fluctuation-terms",
        "multi-head-fluctuation-ambiguity",
        "regional-fluctuation-ownership",
        "fluctuation-soft-line-break",
        "fluctuation-upstream-issue-retained",
        "blurring-and-surface-bleed-coexist",
        "unobserved-primitive-fluctuation-combination",
        "ja-proportion-order-one",
        "ja-proportion-order-two",
        "en-proportion-order-one",
        "en-proportion-order-two",
        "proportion-aspect-only",
        "proportion-width-extent-only",
        "proportion-arc-form-only",
        "conflicting-proportion-aspects",
        "conflicting-proportion-width-extents",
        "conflicting-proportion-arc-forms",
        "orphan-proportion-terms",
        "multi-head-proportion-ambiguity",
    ] {
        assert!(
            ids.contains(required),
            "missing required fixture case: {required}"
        );
    }
}

#[test]
fn head_only_multi_head_regions_are_complete_source_ordered_entity_sequences() {
    let mut canonical = Vec::new();
    for (source, language, expected) in [
        (
            "circle line",
            ResolvedInstructionLanguage::En,
            ["circle", "line"],
        ),
        ("円 線", ResolvedInstructionLanguage::Ja, ["circle", "line"]),
        (
            "line circle",
            ResolvedInstructionLanguage::En,
            ["line", "circle"],
        ),
    ] {
        let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
        let result = associate_semantic_entities(&document).unwrap();
        assert!(result.issues.is_empty(), "{source}");
        assert!(result.ast.complete, "{source}");
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .map(|entity| match &entity.head {
                    SemanticHead::Primitive(term) => term.identity.id.as_str(),
                    SemanticHead::MacroInvocation(_) => "macro",
                })
                .collect::<Vec<_>>(),
            expected,
            "{source}"
        );
        assert!(result.ast.entities.iter().all(|entity| {
            entity.color.is_none()
                && entity.quantity.is_none()
                && entity.touch.is_none()
                && entity.continuity.is_none()
                && entity.angle.is_none()
                && entity.surface.quality.is_none()
                && entity.surface.intensity.is_none()
                && entity.fluctuation.amplitude.is_none()
                && entity.fluctuation.frequency.is_none()
                && entity.fluctuation.quality.is_none()
                && entity.proportion.aspect.is_none()
                && entity.proportion.width_extent.is_none()
                && entity.proportion.arc_form.is_none()
        }));
        canonical.push(result.canonical_bytes.unwrap());
    }
    assert_eq!(canonical[0], canonical[1], "JA/EN meaning parity");
    assert_ne!(canonical[0], canonical[2], "head order is semantic");
}

#[test]
fn pre_head_colors_are_owned_by_each_multi_head_in_source_order() {
    let mut canonical = Vec::new();
    for (source, expected_colors) in [
        ("red circle blue line", ["red", "blue"]),
        ("blue circle red line", ["blue", "red"]),
    ] {
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .unwrap();
        let result = associate_semantic_entities(&document).unwrap();

        assert!(result.issues.is_empty(), "{source}");
        assert!(result.ast.complete, "{source}");
        assert_eq!(result.ast.entities.len(), 2, "{source}");
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .map(|entity| {
                    entity
                        .color
                        .as_ref()
                        .map(|color| color.identity.id.as_str())
                })
                .collect::<Vec<_>>(),
            expected_colors.into_iter().map(Some).collect::<Vec<_>>(),
            "{source}"
        );
        assert_eq!(result.owned_occurrence_count, 4, "{source}");
        assert_eq!(result.delivered_occurrence_count, 4, "{source}");
        canonical.push(result.canonical_bytes.unwrap());
    }
    assert_ne!(canonical[0], canonical[1]);
}

#[test]
fn spec_core_thinness_has_language_independent_entity_meaning_and_source_provenance() {
    let mut canonical = Vec::new();
    for (source, language, expected_surface) in [
        (
            "中心に鉛筆の細い線をひとつ置く。",
            ResolvedInstructionLanguage::Ja,
            "細い",
        ),
        (
            "Place one thin pencil line at the center.",
            ResolvedInstructionLanguage::En,
            "thin",
        ),
    ] {
        let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
        let result = associate_semantic_entities(&document).unwrap();

        assert!(result.issues.is_empty(), "{source}: {:?}", result.issues);
        assert!(result.ast.complete, "{source}");
        assert_eq!(result.ast.entities.len(), 1, "{source}");
        let entity = &result.ast.entities[0];
        assert_eq!(
            entity.head.source().surface,
            if language == ResolvedInstructionLanguage::Ja {
                "線"
            } else {
                "line"
            }
        );
        assert_eq!(entity.touch.as_ref().unwrap().identity.id, "pencil");
        assert_eq!(entity.quantity.as_ref().unwrap().value, 1);
        let thinness = entity.thinness.as_ref().expect("explicit core thinness");
        assert_eq!(thinness.value.as_str(), "fine");
        assert_eq!(thinness.provenance.surface, expected_surface);
        assert_eq!(
            &document.source()
                [thinness.provenance.span.start_byte..thinness.provenance.span.end_byte],
            expected_surface
        );
        assert_eq!(result.owned_occurrence_count, 4, "{source}");
        assert_eq!(result.delivered_occurrence_count, 4, "{source}");
        canonical.push(result.canonical_bytes.unwrap());
    }

    assert_eq!(canonical[0], canonical[1]);
}

#[test]
fn core_thinness_uses_pre_head_ownership_without_default_or_nearest_fallback() {
    let multi = NormalizedDdlDocument::new(
        "thin line circle",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let multi = associate_semantic_entities(&multi).unwrap();
    assert!(multi.issues.is_empty());
    assert_eq!(multi.ast.entities.len(), 2);
    assert_eq!(
        multi.ast.entities[0]
            .thinness
            .as_ref()
            .unwrap()
            .value
            .as_str(),
        "fine"
    );
    assert!(multi.ast.entities[1].thinness.is_none());

    let post_head =
        NormalizedDdlDocument::new("line thin", ResolvedInstructionLanguage::En, Vec::new())
            .unwrap();
    let post_head = associate_semantic_entities(&post_head).unwrap();
    assert!(post_head.ast.entities[0].thinness.is_none());
    assert_eq!(
        association_issue_kinds(&post_head),
        ["ambiguous_entity_ownership"]
    );
    assert!(matches!(
        post_head.issues[0].occurrences.as_slice(),
        [OwnedSemanticOccurrence::Thinness(_)]
    ));

    let conflict = NormalizedDdlDocument::new(
        "thin THIN line",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let conflict = associate_semantic_entities(&conflict).unwrap();
    assert!(conflict.ast.entities[0].thinness.is_none());
    assert_eq!(association_issue_kinds(&conflict), ["conflicting_thinness"]);
    assert_eq!(conflict.issues[0].occurrences.len(), 2);
    assert_eq!(
        conflict.owned_occurrence_count,
        conflict.delivered_occurrence_count
    );
}

#[test]
fn conflicting_modifiers_inside_one_pre_head_phrase_use_existing_typed_conflict() {
    let document = NormalizedDdlDocument::new(
        "red blue circle green line",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = associate_semantic_entities(&document).unwrap();

    assert!(!result.ast.complete);
    assert_eq!(result.ast.entities.len(), 2);
    assert!(result.ast.entities[0].color.is_none());
    assert_eq!(
        result.ast.entities[1].color.as_ref().unwrap().identity.id,
        "green"
    );
    assert_eq!(association_issue_kinds(&result), ["conflicting_colors"]);
    assert_eq!(
        result.issues[0]
            .occurrences
            .iter()
            .map(|occurrence| occurrence.source().surface.as_str())
            .collect::<Vec<_>>(),
        ["red", "blue"]
    );
    assert_eq!(result.owned_occurrence_count, 5);
    assert_eq!(result.delivered_occurrence_count, 5);
}

#[test]
fn pre_head_phrases_deliver_every_closed_modifier_dimension() {
    let document = NormalizedDdlDocument::new(
        "red two pen dashed horizontal hatch dense fine slowly swaying tall full-width semicircle circle blue three pencil dotted vertical grain faint large quickly trembling wide half-width crescent line",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = associate_semantic_entities(&document).unwrap();

    assert!(result.issues.is_empty(), "{:?}", result.issues);
    assert!(result.ast.complete);
    assert_eq!(result.ast.entities.len(), 2);
    let first = &result.ast.entities[0];
    let second = &result.ast.entities[1];
    assert_eq!(first.color.as_ref().unwrap().identity.id, "red");
    assert_eq!(first.quantity.as_ref().unwrap().value, 2);
    assert_eq!(first.touch.as_ref().unwrap().identity.id, "pen");
    assert_eq!(first.continuity.as_ref().unwrap().identity.id, "dashed");
    assert_eq!(first.angle.as_ref().unwrap().identity.id, "horizontal");
    assert_eq!(first.surface.quality.as_ref().unwrap().identity.id, "hatch");
    assert_eq!(
        first.surface.intensity.as_ref().unwrap().identity.id,
        "dense"
    );
    assert_eq!(
        first.fluctuation.amplitude.as_ref().unwrap().identity.id,
        "fine"
    );
    assert_eq!(
        first.fluctuation.frequency.as_ref().unwrap().identity.id,
        "slowly"
    );
    assert_eq!(
        first.fluctuation.quality.as_ref().unwrap().identity.id,
        "swaying"
    );
    assert_eq!(
        first.proportion.aspect.as_ref().unwrap().identity.id,
        "tall"
    );
    assert_eq!(
        first.proportion.width_extent.as_ref().unwrap().identity.id,
        "full_width"
    );
    assert_eq!(
        first.proportion.arc_form.as_ref().unwrap().identity.id,
        "semicircle"
    );

    assert_eq!(second.color.as_ref().unwrap().identity.id, "blue");
    assert_eq!(second.quantity.as_ref().unwrap().value, 3);
    assert_eq!(second.touch.as_ref().unwrap().identity.id, "pencil");
    assert_eq!(second.continuity.as_ref().unwrap().identity.id, "dotted");
    assert_eq!(second.angle.as_ref().unwrap().identity.id, "vertical");
    assert_eq!(
        second.surface.quality.as_ref().unwrap().identity.id,
        "grain"
    );
    assert_eq!(
        second.surface.intensity.as_ref().unwrap().identity.id,
        "faint"
    );
    assert_eq!(
        second.fluctuation.amplitude.as_ref().unwrap().identity.id,
        "large"
    );
    assert_eq!(
        second.fluctuation.frequency.as_ref().unwrap().identity.id,
        "quickly"
    );
    assert_eq!(
        second.fluctuation.quality.as_ref().unwrap().identity.id,
        "trembling"
    );
    assert_eq!(
        second.proportion.aspect.as_ref().unwrap().identity.id,
        "wide"
    );
    assert_eq!(
        second.proportion.width_extent.as_ref().unwrap().identity.id,
        "half_width"
    );
    assert_eq!(
        second.proportion.arc_form.as_ref().unwrap().identity.id,
        "crescent"
    );
    assert_eq!(result.owned_occurrence_count, 28);
    assert_eq!(result.delivered_occurrence_count, 28);
}

#[test]
fn typed_determiner_and_genitive_connectors_stay_inside_pre_head_phrases() {
    for (source, language) in [
        (
            "the red circle the blue line",
            ResolvedInstructionLanguage::En,
        ),
        (
            "red of circle blue of line",
            ResolvedInstructionLanguage::En,
        ),
        ("赤の円 青の線", ResolvedInstructionLanguage::Ja),
    ] {
        let document = NormalizedDdlDocument::new(source, language, Vec::new()).unwrap();
        let result = associate_semantic_entities(&document).unwrap();
        assert!(result.issues.is_empty(), "{source}");
        assert!(result.ast.complete, "{source}");
        assert_eq!(result.ast.entities.len(), 2, "{source}");
        assert_eq!(
            result
                .ast
                .entities
                .iter()
                .map(|entity| entity.color.as_ref().unwrap().identity.id.as_str())
                .collect::<Vec<_>>(),
            ["red", "blue"],
            "{source}"
        );
    }
}

#[test]
fn pre_head_ownership_stops_at_typed_boundaries_and_keeps_remaining_issues() {
    for source in [
        "red circle blue with line",
        "red circle blue mystery line",
        "red\ncircle blue line",
        "red circle blue line eight",
    ] {
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .unwrap();
        let result = associate_semantic_entities(&document).unwrap();
        assert_eq!(result.ast.entities.len(), 2, "{source}");
        assert_eq!(
            result.ast.entities[0]
                .color
                .as_ref()
                .map(|color| color.identity.id.as_str()),
            (source != "red\ncircle blue line").then_some("red"),
            "{source}"
        );
        assert_eq!(
            result.ast.entities[1]
                .color
                .as_ref()
                .map(|color| color.identity.id.as_str()),
            (!source.contains("with") && !source.contains("mystery")).then_some("blue"),
            "{source}"
        );
        let ambiguous = result
            .issues
            .iter()
            .find(|issue| issue.kind.as_str() == "ambiguous_entity_ownership")
            .expect("one typed ownership issue");
        assert_eq!(
            ambiguous
                .occurrences
                .iter()
                .map(|occurrence| occurrence.source().surface.as_str())
                .collect::<Vec<_>>(),
            if source.ends_with("eight") {
                vec!["eight"]
            } else {
                vec![if source.starts_with("red\n") {
                    "red"
                } else {
                    "blue"
                }]
            },
            "{source}"
        );
        assert_eq!(
            result.owned_occurrence_count,
            result.delivered_occurrence_count
        );
    }
}

#[test]
fn multi_head_remaining_modifiers_are_issues_without_redelivering_heads() {
    let document = NormalizedDdlDocument::new(
        "red circle blue line eight pen dashed horizontal solid dense fine slowly swaying tall full-width semicircle",
        ResolvedInstructionLanguage::En,
        Vec::new(),
    )
    .unwrap();
    let result = associate_semantic_entities(&document).unwrap();

    assert_eq!(result.ast.entities.len(), 2);
    assert_eq!(
        result
            .ast
            .entities
            .iter()
            .map(|entity| entity.color.as_ref().unwrap().identity.id.as_str())
            .collect::<Vec<_>>(),
        ["red", "blue"]
    );
    assert!(result.ast.entities.iter().all(|entity| {
        entity.quantity.is_none()
            && entity.touch.is_none()
            && entity.continuity.is_none()
            && entity.angle.is_none()
            && entity.surface.quality.is_none()
            && entity.surface.intensity.is_none()
            && entity.fluctuation.amplitude.is_none()
            && entity.fluctuation.frequency.is_none()
            && entity.fluctuation.quality.is_none()
            && entity.proportion.aspect.is_none()
            && entity.proportion.width_extent.is_none()
            && entity.proportion.arc_form.is_none()
    }));
    assert_eq!(
        association_issue_kinds(&result),
        ["ambiguous_entity_ownership"]
    );
    assert_eq!(result.issues[0].occurrences.len(), 12);
    assert!(
        result.issues[0]
            .occurrences
            .iter()
            .all(|occurrence| !matches!(occurrence, OwnedSemanticOccurrence::Head(_)))
    );
    assert!(
        result.issues[0]
            .occurrences
            .windows(2)
            .all(|pair| pair[0].source().span.start_byte < pair[1].source().span.start_byte)
    );
    assert_eq!(result.owned_occurrence_count, 16);
    assert_eq!(result.delivered_occurrence_count, 16);
}

#[test]
fn every_accepted_surface_row_belongs_to_exactly_one_closed_dimension() {
    let category = saijiki_asset()
        .categories
        .iter()
        .find(|category| category.key == "omote")
        .expect("accepted asset has the Surface category");
    assert_eq!(category.words.len(), 11);

    let mut quality_ids = HashSet::new();
    let mut intensity_ids = HashSet::new();
    for word in &category.words {
        let projection = project_macro_semantic_ref(&category.key, &word.surface_ja)
            .expect("accepted Surface row has canonical identity");
        let source = format!(
            "circle {}.",
            word.surface_en
                .as_deref()
                .expect("accepted Surface row has English source surface")
        );
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .expect("accepted Surface row forms a normalized document");
        let result = associate_semantic_entities(&document)
            .expect("accepted Surface row forms a clause stream");
        assert!(result.issues.is_empty(), "{}", projection.canonical_id);
        let entity = result.ast.entities.first().expect("one entity");
        match (&entity.surface.quality, &entity.surface.intensity) {
            (Some(term), None) => {
                assert_eq!(term.identity.category, "surface");
                assert_eq!(term.identity.id, projection.canonical_id);
                assert!(quality_ids.insert(term.identity.id.clone()));
            }
            (None, Some(term)) => {
                assert_eq!(term.identity.category, "surface");
                assert_eq!(term.identity.id, projection.canonical_id);
                assert!(intensity_ids.insert(term.identity.id.clone()));
            }
            _ => panic!(
                "{} must belong to exactly one Surface dimension",
                projection.canonical_id
            ),
        }
    }

    assert_eq!(
        quality_ids,
        [
            "none",
            "solid",
            "wash",
            "grain",
            "stipple",
            "hatch",
            "crosshatch",
            "bleed",
            "aquatint",
        ]
        .map(str::to_owned)
        .into_iter()
        .collect()
    );
    assert_eq!(
        intensity_ids,
        ["dense", "faint"].map(str::to_owned).into_iter().collect()
    );
}

#[test]
fn every_accepted_fluctuation_row_belongs_to_exactly_one_closed_dimension() {
    let category = saijiki_asset()
        .categories
        .iter()
        .find(|category| category.key == "yuragi")
        .expect("accepted asset has the Fluctuation category");
    assert_eq!(category.words.len(), 8);

    let mut amplitude_ids = HashSet::new();
    let mut frequency_ids = HashSet::new();
    let mut quality_ids = HashSet::new();
    for word in &category.words {
        let projection = project_macro_semantic_ref(&category.key, &word.surface_ja)
            .expect("accepted Fluctuation row has canonical identity");
        let source = format!(
            "circle {}.",
            word.surface_en
                .as_deref()
                .expect("accepted Fluctuation row has English source surface")
        );
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .expect("accepted Fluctuation row forms a normalized document");
        let result = associate_semantic_entities(&document)
            .expect("accepted Fluctuation row forms a clause stream");
        assert!(result.issues.is_empty(), "{}", projection.canonical_id);
        let entity = result.ast.entities.first().expect("one entity");
        match (
            &entity.fluctuation.amplitude,
            &entity.fluctuation.frequency,
            &entity.fluctuation.quality,
        ) {
            (Some(term), None, None) => {
                assert_eq!(term.identity.category, "variation");
                assert_eq!(term.identity.id, projection.canonical_id);
                assert!(amplitude_ids.insert(term.identity.id.clone()));
            }
            (None, Some(term), None) => {
                assert_eq!(term.identity.category, "variation");
                assert_eq!(term.identity.id, projection.canonical_id);
                assert!(frequency_ids.insert(term.identity.id.clone()));
            }
            (None, None, Some(term)) => {
                assert_eq!(term.identity.category, "variation");
                assert_eq!(term.identity.id, projection.canonical_id);
                assert!(quality_ids.insert(term.identity.id.clone()));
            }
            _ => panic!(
                "{} must belong to exactly one Fluctuation dimension",
                projection.canonical_id
            ),
        }
    }

    assert_eq!(
        amplitude_ids,
        ["fine", "large"].map(str::to_owned).into_iter().collect()
    );
    assert_eq!(
        frequency_ids,
        ["quickly", "slowly"]
            .map(str::to_owned)
            .into_iter()
            .collect()
    );
    assert_eq!(
        quality_ids,
        ["swaying", "undulating", "trembling", "blurring"]
            .map(str::to_owned)
            .into_iter()
            .collect()
    );
}

#[test]
fn every_accepted_proportion_row_belongs_to_exactly_one_closed_dimension() {
    let category = saijiki_asset()
        .categories
        .iter()
        .find(|category| category.key == "wariai")
        .expect("accepted asset has the Proportion category");
    assert_eq!(category.words.len(), 8);

    let mut aspect_ids = HashSet::new();
    let mut width_extent_ids = HashSet::new();
    let mut arc_form_ids = HashSet::new();
    for word in &category.words {
        let projection = project_macro_semantic_ref(&category.key, &word.surface_ja)
            .expect("accepted Proportion row has canonical identity");
        let source = format!(
            "circle {}.",
            word.surface_en
                .as_deref()
                .expect("accepted Proportion row has English source surface")
        );
        let document =
            NormalizedDdlDocument::new(source, ResolvedInstructionLanguage::En, Vec::new())
                .expect("accepted Proportion row forms a normalized document");
        let result = associate_semantic_entities(&document)
            .expect("accepted Proportion row forms a clause stream");
        assert!(result.issues.is_empty(), "{}", projection.canonical_id);
        let entity = result.ast.entities.first().expect("one entity");
        match (
            &entity.proportion.aspect,
            &entity.proportion.width_extent,
            &entity.proportion.arc_form,
        ) {
            (Some(term), None, None) => {
                assert_eq!(term.identity.category, "ratio");
                assert_eq!(term.identity.id, projection.canonical_id);
                assert!(aspect_ids.insert(term.identity.id.clone()));
            }
            (None, Some(term), None) => {
                assert_eq!(term.identity.category, "ratio");
                assert_eq!(term.identity.id, projection.canonical_id);
                assert!(width_extent_ids.insert(term.identity.id.clone()));
            }
            (None, None, Some(term)) => {
                assert_eq!(term.identity.category, "ratio");
                assert_eq!(term.identity.id, projection.canonical_id);
                assert!(arc_form_ids.insert(term.identity.id.clone()));
            }
            _ => panic!(
                "{} must belong to exactly one Proportion dimension",
                projection.canonical_id
            ),
        }
    }

    assert_eq!(
        aspect_ids,
        ["tall", "wide"].map(str::to_owned).into_iter().collect()
    );
    assert_eq!(
        width_extent_ids,
        ["full_width", "half_width"]
            .map(str::to_owned)
            .into_iter()
            .collect()
    );
    assert_eq!(
        arc_form_ids,
        ["semicircle", "waxing", "waning", "crescent"]
            .map(str::to_owned)
            .into_iter()
            .collect()
    );
}

#[test]
fn accepted_full_relation_atoms_are_compound_owned_without_false_entity_delivery() {
    let asset = saijiki_asset();
    let shapes = asset
        .categories
        .iter()
        .find(|category| category.key == "katachi")
        .expect("accepted asset has Primitive rows");
    let line = shapes
        .words
        .iter()
        .find(|word| word.surface_en.as_deref() == Some("line"))
        .expect("accepted asset has line");
    let circle = shapes
        .words
        .iter()
        .find(|word| word.surface_en.as_deref() == Some("circle"))
        .expect("accepted asset has circle");

    for relation in &asset.relations {
        let mut meaning_bytes = None;
        for (language, literals, previous_surface, current_surface, ending) in [
            (
                ResolvedInstructionLanguage::Ja,
                &relation.literals_ja,
                line.surface_ja.as_str(),
                circle.surface_ja.as_str(),
                "。",
            ),
            (
                ResolvedInstructionLanguage::En,
                &relation.literals_en,
                line.surface_en.as_deref().expect("line has EN surface"),
                circle.surface_en.as_deref().expect("circle has EN surface"),
                ".",
            ),
        ] {
            for literal in literals {
                let source =
                    format!("{previous_surface}{ending} {current_surface} {literal}{ending}");
                let document = NormalizedDdlDocument::new(source.clone(), language, Vec::new())
                    .expect("accepted full relation source forms a document");
                let result = associate_semantic_entities(&document)
                    .expect("accepted full relation source forms an association");
                assert!(
                    result.issues.is_empty(),
                    "{literal}: {:?}",
                    result
                        .issues
                        .iter()
                        .map(|issue| (
                            issue.kind.as_str(),
                            issue
                                .upstream_diagnostic
                                .as_ref()
                                .map(|diagnostic| diagnostic.surface.as_str()),
                        ))
                        .collect::<Vec<_>>()
                );
                assert_eq!(
                    result.ast.entities.len(),
                    2,
                    "{literal}: no false target head"
                );
                assert_eq!(result.owned_occurrence_count, 2, "{literal}");
                assert_eq!(result.explicit_previous_references.len(), 1, "{literal}");
                assert_eq!(result.owned_compound_reference_count, 1, "{literal}");
                assert_eq!(result.delivered_compound_reference_count, 1, "{literal}");
                let canonical_bytes = result
                    .canonical_bytes
                    .as_ref()
                    .expect("accepted relation association remains complete");
                if let Some(expected) = &meaning_bytes {
                    assert_eq!(canonical_bytes, expected, "{literal}: JA/EN meaning parity");
                } else {
                    meaning_bytes = Some(canonical_bytes.clone());
                }
                let occurrence = &result.explicit_previous_references[0];
                assert_eq!(
                    occurrence.kind.as_str(),
                    relation.relation_type,
                    "{literal}"
                );
                assert_eq!(occurrence.provenance.surface, *literal, "{literal}");
                assert_eq!(
                    source[occurrence.provenance.span.start_byte
                        ..occurrence.provenance.span.end_byte],
                    *literal,
                    "{literal}"
                );
                let Some(ClauseAtom::SaijikiRelation {
                    span,
                    canonical_identity,
                    ..
                }) = result
                    .clause_stream
                    .clauses
                    .get(occurrence.provenance.clause_index)
                    .and_then(|clause| clause.atoms.get(occurrence.provenance.atom_index))
                else {
                    panic!("{literal}: compound occurrence must retain its relation atom");
                };
                assert_eq!(*span, occurrence.provenance.span, "{literal}");
                assert_eq!(canonical_identity.form, CanonicalRelationForm::FullLiteral);
                assert_eq!(canonical_identity.kind.as_str(), occurrence.kind.as_str());
                assert_eq!(
                    canonical_identity.previous_reference,
                    Some(match occurrence.reference {
                        inku_ddl::SemanticPreviousReference::PreviousOne => {
                            CanonicalPreviousReference::PreviousOne
                        }
                        inku_ddl::SemanticPreviousReference::PreviousTwo => {
                            CanonicalPreviousReference::PreviousTwo
                        }
                    }),
                    "{literal}"
                );
            }
        }
    }

    for relation in &asset.relations {
        for (language, short_surface, previous_surface, current_surface, ending) in [
            (
                ResolvedInstructionLanguage::Ja,
                relation.surface_ja.as_str(),
                line.surface_ja.as_str(),
                circle.surface_ja.as_str(),
                "。",
            ),
            (
                ResolvedInstructionLanguage::En,
                relation.surface_en.as_str(),
                line.surface_en.as_deref().expect("line has EN surface"),
                circle.surface_en.as_deref().expect("circle has EN surface"),
                ".",
            ),
        ] {
            let source =
                format!("{previous_surface}{ending} {current_surface} {short_surface}{ending}");
            let document = NormalizedDdlDocument::new(source, language, Vec::new())
                .expect("short relation surface forms a document");
            let result = associate_semantic_entities(&document)
                .expect("short relation surface forms an association");
            assert!(
                result.explicit_previous_references.is_empty(),
                "{short_surface}"
            );
            assert_eq!(result.ast.entities.len(), 2, "{short_surface}");
        }
    }
}

fn load_fixture() -> Fixture {
    serde_json::from_str(FIXTURE).expect("fixture must be valid JSON")
}

fn parse_language(value: &str, case_id: &str) -> ResolvedInstructionLanguage {
    match value {
        "ja" => ResolvedInstructionLanguage::Ja,
        "en" => ResolvedInstructionLanguage::En,
        _ => panic!("{case_id}: invalid fixture language"),
    }
}

fn assert_source_provenance(case: &Case, result: &SemanticAssociationResult) {
    for entity in &result.ast.entities {
        assert_source_occurrence(case, entity.head.source(), &result.clause_stream);
        if let Some(color) = &entity.color {
            assert_source_occurrence(case, &color.provenance.source, &result.clause_stream);
        }
        if let Some(quantity) = &entity.quantity {
            assert_source_occurrence(case, &quantity.provenance, &result.clause_stream);
        }
        for term in [&entity.touch, &entity.continuity, &entity.angle]
            .into_iter()
            .flatten()
        {
            assert_source_occurrence(case, &term.provenance.source, &result.clause_stream);
            assert_eq!(
                entity.head.source().region_index,
                term.provenance.source.region_index,
                "{}: entity attribute must remain in its sentence region",
                case.id
            );
        }
        for term in [&entity.surface.quality, &entity.surface.intensity]
            .into_iter()
            .flatten()
        {
            assert_source_occurrence(case, &term.provenance.source, &result.clause_stream);
            assert_eq!(
                entity.head.source().region_index,
                term.provenance.source.region_index,
                "{}: Surface dimension must remain in its sentence region",
                case.id
            );
        }
        if let Some(thinness) = &entity.thinness {
            assert_source_occurrence(case, &thinness.provenance, &result.clause_stream);
            assert_eq!(
                entity.head.source().region_index,
                thinness.provenance.region_index,
                "{}: core thinness must remain in its sentence region",
                case.id
            );
        }
        for term in [
            &entity.fluctuation.amplitude,
            &entity.fluctuation.frequency,
            &entity.fluctuation.quality,
        ]
        .into_iter()
        .flatten()
        {
            assert_source_occurrence(case, &term.provenance.source, &result.clause_stream);
            assert_eq!(
                entity.head.source().region_index,
                term.provenance.source.region_index,
                "{}: Fluctuation dimension must remain in its sentence region",
                case.id
            );
        }
        for term in [
            &entity.proportion.aspect,
            &entity.proportion.width_extent,
            &entity.proportion.arc_form,
        ]
        .into_iter()
        .flatten()
        {
            assert_source_occurrence(case, &term.provenance.source, &result.clause_stream);
            assert_eq!(
                entity.head.source().region_index,
                term.provenance.source.region_index,
                "{}: Proportion dimension must remain in its sentence region",
                case.id
            );
        }
    }
    for issue in &result.issues {
        for occurrence in &issue.occurrences {
            assert_eq!(
                occurrence.source().region_index,
                issue.region_index,
                "{}",
                case.id
            );
            assert_source_occurrence(case, occurrence.source(), &result.clause_stream);
        }
        if let Some(diagnostic) = &issue.upstream_diagnostic {
            assert_eq!(
                diagnostic.surface,
                case.source[diagnostic.span.start_byte..diagnostic.span.end_byte],
                "{}: upstream diagnostic source slice",
                case.id
            );
            assert_eq!(
                issue.region_index,
                expected_region_index(&result.clause_stream, diagnostic.span),
                "{}: upstream diagnostic region provenance",
                case.id
            );
        }
    }
}

fn assert_source_occurrence(case: &Case, occurrence: &SourceOccurrence, stream: &ClauseStream) {
    let span = occurrence.span;
    assert!(
        span.start_byte < span.end_byte,
        "{}: empty occurrence",
        case.id
    );
    assert!(
        span.end_byte <= case.source.len(),
        "{}: span outside source",
        case.id
    );
    assert!(
        case.source.is_char_boundary(span.start_byte)
            && case.source.is_char_boundary(span.end_byte),
        "{}: non-UTF-8-boundary span",
        case.id
    );
    assert_eq!(
        occurrence.surface,
        case.source[span.start_byte..span.end_byte],
        "{}: source slice mismatch",
        case.id
    );
    assert_eq!(
        occurrence.language,
        parse_language(&case.language, &case.id),
        "{}: language provenance",
        case.id
    );
    let atom = stream
        .clauses
        .get(occurrence.clause_index)
        .and_then(|clause| clause.atoms.get(occurrence.atom_index))
        .unwrap_or_else(|| panic!("{}: invalid clause / atom provenance", case.id));
    assert_eq!(atom.span(), occurrence.span, "{}: atom provenance", case.id);
    assert_eq!(
        occurrence.region_index,
        expected_region_index(stream, occurrence.span),
        "{}: region provenance",
        case.id
    );
}

fn expected_region_index(stream: &ClauseStream, span: inku_ddl::SourceSpan) -> usize {
    stream
        .separators
        .iter()
        .filter(|separator| {
            separator.kind == ClauseSeparatorKind::SentenceEnd
                && separator.span.end_byte <= span.start_byte
        })
        .count()
}

fn assert_owned_occurrence_join(case: &Case, result: &inku_ddl::SemanticAssociationResult) {
    let input_spans = result
        .clause_stream
        .clauses
        .iter()
        .flat_map(|clause| &clause.atoms)
        .filter_map(|atom| match atom {
            ClauseAtom::CoreRole(term)
                if matches!(
                    term.role,
                    CoreRoleKind::Primitive
                        | CoreRoleKind::Color
                        | CoreRoleKind::Touch
                        | CoreRoleKind::Surface
                ) =>
            {
                Some(term.span)
            }
            ClauseAtom::RemainingRole(term)
                if matches!(
                    term.role,
                    RemainingRoleKind::Continuity
                        | RemainingRoleKind::Angle
                        | RemainingRoleKind::Fluctuation
                        | RemainingRoleKind::Proportion
                ) =>
            {
                Some(term.span)
            }
            ClauseAtom::UnattachedExactNumber(number) => Some(number.span),
            ClauseAtom::CoreModifier(modifier) => Some(modifier.span),
            _ => None,
        })
        .collect::<Vec<_>>();

    let mut output_spans = Vec::new();
    for entity in &result.ast.entities {
        output_spans.push(entity.head.source().span);
        if let Some(color) = &entity.color {
            output_spans.push(color.provenance.source.span);
        }
        if let Some(quantity) = &entity.quantity {
            output_spans.push(quantity.provenance.span);
        }
        if let Some(thinness) = &entity.thinness {
            output_spans.push(thinness.provenance.span);
        }
        for term in [&entity.touch, &entity.continuity, &entity.angle]
            .into_iter()
            .flatten()
        {
            output_spans.push(term.provenance.source.span);
        }
        for term in [&entity.surface.quality, &entity.surface.intensity]
            .into_iter()
            .flatten()
        {
            output_spans.push(term.provenance.source.span);
        }
        for term in [
            &entity.fluctuation.amplitude,
            &entity.fluctuation.frequency,
            &entity.fluctuation.quality,
        ]
        .into_iter()
        .flatten()
        {
            output_spans.push(term.provenance.source.span);
        }
        for term in [
            &entity.proportion.aspect,
            &entity.proportion.width_extent,
            &entity.proportion.arc_form,
        ]
        .into_iter()
        .flatten()
        {
            output_spans.push(term.provenance.source.span);
        }
    }
    for occurrence in result.issues.iter().flat_map(|issue| &issue.occurrences) {
        output_spans.push(match occurrence {
            OwnedSemanticOccurrence::Head(head) => head.source().span,
            OwnedSemanticOccurrence::MacroDiagnostic(provenance) => provenance.source.span,
            OwnedSemanticOccurrence::Color(term) => term.provenance.source.span,
            OwnedSemanticOccurrence::Quantity(quantity) => quantity.provenance.span,
            OwnedSemanticOccurrence::Thinness(thinness) => thinness.provenance.span,
            OwnedSemanticOccurrence::Touch(term)
            | OwnedSemanticOccurrence::Continuity(term)
            | OwnedSemanticOccurrence::Angle(term)
            | OwnedSemanticOccurrence::Surface(term)
            | OwnedSemanticOccurrence::Fluctuation(term)
            | OwnedSemanticOccurrence::Proportion(term) => term.provenance.source.span,
        });
    }

    assert_eq!(output_spans.len(), input_spans.len(), "{}", case.id);
    for span in input_spans {
        assert_eq!(
            output_spans
                .iter()
                .filter(|candidate| **candidate == span)
                .count(),
            1,
            "{}: owned span {span:?} must join exactly once",
            case.id
        );
    }
}

#[test]
fn resolved_complete_macro_invocation_becomes_a_semantic_head_without_reexecution() {
    let definition = MacroDefinition::from_json(
        r#"{"schema":"inku.macro-definition.v1","namespace":"Nature","heading":"Leaf","version":"1.0.0","parameters":{},"components":{},"body":[]}"#,
    )
    .expect("fixture definition parses");
    let identity = definition.identity().expect("fixture definition is valid");
    let document = NormalizedDdlDocument::new(
        "Nature.Leaf",
        ResolvedInstructionLanguage::En,
        vec![
            MacroLock::new(
                identity.qualified_name(),
                identity.version(),
                format!("sha256:{}", identity.full_digest_hex()),
            )
            .expect("fixture lock is valid"),
        ],
    )
    .expect("fixture document is valid");
    let binding = bind_macro_parameters(&document, std::slice::from_ref(&definition))
        .expect("fixture binding is accepted");

    let result = associate_semantic_entities_with_macro_binding(&document, binding);
    assert!(result.issues.is_empty());
    assert_eq!(result.ast.entities.len(), 1);
    let SemanticHead::MacroInvocation(head) = &result.ast.entities[0].head else {
        panic!("resolved invocation must not fall back to Primitive");
    };
    assert_eq!(head.qualified_name, "Nature.Leaf");
    assert!(head.parameters.is_empty());
    let accepted = result
        .macro_parameter_binding
        .as_ref()
        .expect("macro-aware result owns accepted I-581 result");
    assert_eq!(
        result.clause_stream,
        accepted
            .macro_resolution
            .relation_reference_evidence
            .attachment_evidence
            .noun_phrase
            .clause_stream
    );
}

#[test]
fn complete_macro_parameters_are_owned_once_and_excluded_from_outer_fields() {
    let definition = semantic_macro_definition(
        "Nature",
        "Leaf",
        "1.0.0",
        serde_json::json!({
            "count": {"type": "integer"},
            "shape": {"type": "semantic_ref", "category": "shape"},
            "tint": {"type": "semantic_ref", "category": "color"},
            "touch": {"type": "semantic_ref", "category": "touch"}
        }),
        serde_json::json!([]),
    );
    let document = locked_macro_document(
        "Nature.Leaf circle 8 blue silverpoint",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let binding = bind_macro_parameters(&document, std::slice::from_ref(&definition)).unwrap();
    let accepted = binding.clone();
    let result = associate_semantic_entities_with_macro_binding(&document, binding);

    assert!(result.issues.is_empty());
    assert_eq!(result.macro_parameter_binding.as_ref(), Some(&accepted));
    assert_eq!(result.ast.entities.len(), 1);
    let entity = &result.ast.entities[0];
    let head = macro_head(entity);
    let identity = definition
        .identity()
        .expect("synthetic definition identity");
    assert_eq!(head.definition_version, identity.version());
    assert_eq!(head.definition_digest, identity.full_digest_hex());
    assert_eq!(head.lock.qualified_name, head.qualified_name);
    assert_eq!(head.lock.version, head.definition_version);
    assert_eq!(
        head.lock.digest,
        format!("sha256:{}", head.definition_digest)
    );
    assert_eq!(head.parameters.len(), 4);
    assert!(
        entity.color.is_none(),
        "bound Color must not become outer Color"
    );
    assert!(
        entity.quantity.is_none(),
        "bound number must not become outer quantity"
    );
    assert!(
        entity.touch.is_none(),
        "bound Touch must not become outer Touch"
    );
    assert_eq!(result.owned_occurrence_count, 5);
    assert_eq!(result.delivered_occurrence_count, 5);
    assert_eq!(
        head.parameters
            .iter()
            .map(|parameter| parameter.name.as_str())
            .collect::<Vec<_>>(),
        ["count", "shape", "tint", "touch"]
    );
    assert!(matches!(
        head.parameters[0].value,
        SemanticMacroParameterValue::Integer(8)
    ));
    assert!(matches!(
        &head.parameters[1].value,
        SemanticMacroParameterValue::SemanticRef(identity)
            if identity.category == "shape" && identity.id == "circle"
    ));
    let mut owned_spans = head
        .parameters
        .iter()
        .map(|parameter| parameter.provenance.span)
        .collect::<Vec<_>>();
    owned_spans.push(head.provenance.source.span);
    owned_spans.sort_by_key(|span| span.start_byte);
    owned_spans.dedup();
    assert_eq!(
        owned_spans.len(),
        5,
        "macro head and parameters own distinct spans"
    );

    let canonical: serde_json::Value = serde_json::from_slice(
        result
            .canonical_bytes
            .as_deref()
            .expect("complete canonical"),
    )
    .unwrap();
    let canonical_head = &canonical["entities"][0]["head"];
    assert_eq!(canonical_head["kind"], "macro_invocation");
    assert_eq!(canonical_head["qualified_name"], "Nature.Leaf");
    assert_eq!(
        canonical_head["parameters"].as_array().map(Vec::len),
        Some(4)
    );
    assert!(canonical_head.get("source").is_none());
    assert!(canonical_head.get("span").is_none());
    assert!(canonical_head.get("ordinal").is_none());
    assert!(canonical_head.get("lock").is_none());

    let outer_definition = semantic_macro_definition(
        "Nature",
        "Outer",
        "1.0.0",
        serde_json::json!({}),
        serde_json::json!([]),
    );
    let outer_document = locked_macro_document(
        "Nature.Outer blue",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&outer_definition),
    );
    let outer_binding =
        bind_macro_parameters(&outer_document, std::slice::from_ref(&outer_definition)).unwrap();
    let outer = associate_semantic_entities_with_macro_binding(&outer_document, outer_binding);
    assert_eq!(
        outer.ast.entities[0]
            .color
            .as_ref()
            .map(|term| term.identity.id.as_str()),
        Some("blue"),
        "unbound Color remains an outer modifier"
    );

    let number_definition = semantic_macro_definition(
        "Nature",
        "Measure",
        "1.0.0",
        serde_json::json!({"measure": {"type": "number"}}),
        serde_json::json!([]),
    );
    let number = macro_association(
        "Nature.Measure 5",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&number_definition),
    );
    assert!(matches!(
        macro_head(&number.ast.entities[0]).parameters[0].value,
        SemanticMacroParameterValue::Number(value) if value == 5.0
    ));
    assert!(number.ast.entities[0].quantity.is_none());
}

#[test]
fn macro_place_parameter_keeps_lexical_provenance_with_one_typed_identity() {
    let definition = semantic_macro_definition(
        "Bind",
        "Place",
        "1.0.0",
        serde_json::json!({"where": {"type": "semantic_ref", "category": "place"}}),
        serde_json::json!([]),
    );

    for source_surface in ["center", "middle"] {
        let source = format!("Bind.Place {source_surface}");
        let result = macro_association(
            &source,
            ResolvedInstructionLanguage::En,
            std::slice::from_ref(&definition),
        );
        assert!(result.issues.is_empty(), "{source_surface}");
        let parameter = &macro_head(&result.ast.entities[0]).parameters[0];
        assert!(matches!(
            &parameter.value,
            SemanticMacroParameterValue::SemanticRef(identity)
                if identity.category == "place" && identity.id == "center"
        ));
        assert_eq!(parameter.provenance.surface, source_surface);
        assert_eq!(
            &source[parameter.provenance.span.start_byte..parameter.provenance.span.end_byte],
            source_surface
        );
    }
}

#[test]
fn macro_head_canonical_depends_only_on_definition_and_parameter_meaning() {
    let definition = semantic_macro_definition(
        "Nature",
        "Leaf",
        "1.0.0",
        serde_json::json!({"shape": {"type": "semantic_ref", "category": "shape"}}),
        serde_json::json!([]),
    );
    let en = macro_association(
        "Nature.Leaf circle",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let ja = macro_association(
        "紙 Nature.Leaf 円",
        ResolvedInstructionLanguage::Ja,
        std::slice::from_ref(&definition),
    );
    assert_eq!(canonical_head(&en, 0), canonical_head(&ja, 0));

    let prefix = semantic_macro_definition(
        "Nature",
        "Other",
        "1.0.0",
        serde_json::json!({}),
        serde_json::json!([]),
    );
    let ordinal_shifted = macro_association(
        "Nature.Other! Nature.Leaf circle",
        ResolvedInstructionLanguage::En,
        &[prefix, definition.clone()],
    );
    assert_eq!(canonical_head(&en, 0), canonical_head(&ordinal_shifted, 1));
    assert_ne!(
        macro_head(&en.ast.entities[0]).provenance.ordinal,
        macro_head(&ordinal_shifted.ast.entities[1])
            .provenance
            .ordinal
    );

    let version = semantic_macro_definition(
        "Nature",
        "Leaf",
        "2.0.0",
        serde_json::json!({"shape": {"type": "semantic_ref", "category": "shape"}}),
        serde_json::json!([]),
    );
    let digest = semantic_macro_definition(
        "Nature",
        "Leaf",
        "1.0.0",
        serde_json::json!({"shape": {"type": "semantic_ref", "category": "shape"}}),
        serde_json::json!([{"op": "anchor", "name": "root"}]),
    );
    let qualified = semantic_macro_definition(
        "Nature",
        "Bud",
        "1.0.0",
        serde_json::json!({"shape": {"type": "semantic_ref", "category": "shape"}}),
        serde_json::json!([]),
    );
    let changed_version = macro_association(
        "Nature.Leaf circle",
        ResolvedInstructionLanguage::En,
        &[version],
    );
    let changed_digest = macro_association(
        "Nature.Leaf circle",
        ResolvedInstructionLanguage::En,
        &[digest],
    );
    let changed_name = macro_association(
        "Nature.Bud circle",
        ResolvedInstructionLanguage::En,
        &[qualified],
    );
    let changed_value = macro_association(
        "Nature.Leaf square",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&definition),
    );
    let base = canonical_head(&en, 0);
    assert_ne!(base, canonical_head(&changed_version, 0));
    assert_ne!(base, canonical_head(&changed_digest, 0));
    assert_ne!(base, canonical_head(&changed_name, 0));
    assert_ne!(base, canonical_head(&changed_value, 0));
}

#[test]
fn macro_diagnostics_and_ambiguous_heads_never_fall_back_or_guess() {
    let zero = semantic_macro_definition(
        "Nature",
        "Leaf",
        "1.0.0",
        serde_json::json!({}),
        serde_json::json!([]),
    );
    let unlocked_document =
        NormalizedDdlDocument::new("Nature.Leaf", ResolvedInstructionLanguage::En, Vec::new())
            .unwrap();
    let unlocked_binding =
        bind_macro_parameters(&unlocked_document, std::slice::from_ref(&zero)).unwrap();
    let unlocked =
        associate_semantic_entities_with_macro_binding(&unlocked_document, unlocked_binding);
    assert_eq!(
        association_issue_kinds(&unlocked),
        ["macro_resolution_missing_lock"]
    );
    assert!(unlocked.ast.entities.is_empty());
    let [OwnedSemanticOccurrence::MacroDiagnostic(provenance)] =
        unlocked.issues[0].occurrences.as_slice()
    else {
        panic!("typed macro issue must own exactly one invocation occurrence");
    };
    assert_eq!(provenance.source.surface, "Nature.Leaf");
    assert_eq!(provenance.qualified_name.as_deref(), Some("Nature.Leaf"));
    assert_eq!(provenance.ordinal, 0);

    let missing_document = locked_macro_document(
        "Nature.Leaf",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&zero),
    );
    let missing_binding = bind_macro_parameters(&missing_document, &[]).unwrap();
    let missing =
        associate_semantic_entities_with_macro_binding(&missing_document, missing_binding);
    assert_eq!(
        association_issue_kinds(&missing),
        ["macro_resolution_missing_definition"]
    );

    let leaf = semantic_macro_definition(
        "Nature",
        "若葉",
        "1.0.0",
        serde_json::json!({}),
        serde_json::json!([]),
    );
    let morning = semantic_macro_definition(
        "Nature",
        "若葉.朝",
        "1.0.0",
        serde_json::json!({}),
        serde_json::json!([]),
    );
    let ambiguous_lock_document = locked_macro_document(
        "Nature.若葉.朝",
        ResolvedInstructionLanguage::Ja,
        &[leaf.clone(), morning.clone()],
    );
    let ambiguous_lock_binding =
        bind_macro_parameters(&ambiguous_lock_document, &[leaf, morning]).unwrap();
    let ambiguous_lock = associate_semantic_entities_with_macro_binding(
        &ambiguous_lock_document,
        ambiguous_lock_binding,
    );
    assert_eq!(
        association_issue_kinds(&ambiguous_lock),
        ["macro_resolution_ambiguous_lock_prefix"]
    );

    let integer = semantic_macro_definition(
        "Bind",
        "Integer",
        "1.0.0",
        serde_json::json!({"count": {"type": "integer"}}),
        serde_json::json!([]),
    );
    let incomplete = macro_association(
        "Bind.Integer blue",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&integer),
    );
    assert!(
        association_issue_kinds(&incomplete).contains(&"macro_binding_missing_compatible_fact")
    );
    assert!(incomplete.ast.entities.is_empty());

    let color = semantic_macro_definition(
        "Bind",
        "Color",
        "1.0.0",
        serde_json::json!({"tint": {"type": "semantic_ref", "category": "color"}}),
        serde_json::json!([]),
    );
    let ambiguous_binding = macro_association(
        "Bind.Color blue red",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&color),
    );
    assert!(
        association_issue_kinds(&ambiguous_binding)
            .contains(&"macro_binding_ambiguous_complete_assignment")
    );
    assert!(ambiguous_binding.ast.entities.is_empty());

    let primitive_and_macro = macro_association(
        "Nature.Leaf circle",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&zero),
    );
    assert!(primitive_and_macro.issues.is_empty());
    assert!(primitive_and_macro.ast.complete);
    assert_eq!(primitive_and_macro.ast.entities.len(), 2);
    assert!(matches!(
        primitive_and_macro.ast.entities[0].head,
        SemanticHead::MacroInvocation(_)
    ));
    assert!(matches!(
        primitive_and_macro.ast.entities[1].head,
        SemanticHead::Primitive(_)
    ));

    let primitive_then_macro = macro_association(
        "circle Nature.Leaf",
        ResolvedInstructionLanguage::En,
        std::slice::from_ref(&zero),
    );
    assert!(primitive_then_macro.issues.is_empty());
    assert!(primitive_then_macro.ast.complete);
    assert!(matches!(
        primitive_then_macro.ast.entities[0].head,
        SemanticHead::Primitive(_)
    ));
    assert!(matches!(
        primitive_then_macro.ast.entities[1].head,
        SemanticHead::MacroInvocation(_)
    ));

    let other = semantic_macro_definition(
        "Nature",
        "Other",
        "1.0.0",
        serde_json::json!({}),
        serde_json::json!([]),
    );
    let multiple_macro = macro_association(
        "Nature.Leaf Nature.Other",
        ResolvedInstructionLanguage::En,
        &[zero, other],
    );
    assert!(multiple_macro.issues.is_empty());
    assert!(multiple_macro.ast.complete);
    assert_eq!(multiple_macro.ast.entities.len(), 2);
    assert!(
        multiple_macro
            .ast
            .entities
            .iter()
            .all(|entity| matches!(entity.head, SemanticHead::MacroInvocation(_)))
    );
}

fn semantic_macro_definition(
    namespace: &str,
    heading: &str,
    version: &str,
    parameters: serde_json::Value,
    body: serde_json::Value,
) -> MacroDefinition {
    MacroDefinition::from_json(
        &serde_json::json!({
            "schema": "inku.macro-definition.v1",
            "namespace": namespace,
            "heading": heading,
            "version": version,
            "parameters": parameters,
            "components": {},
            "body": body
        })
        .to_string(),
    )
    .expect("synthetic semantic macro definition parses")
}

fn locked_macro_document(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> NormalizedDdlDocument {
    let locks = definitions
        .iter()
        .map(|definition| {
            let identity = definition
                .identity()
                .expect("synthetic definition is valid");
            MacroLock::new(
                identity.qualified_name(),
                identity.version(),
                format!("sha256:{}", identity.full_digest_hex()),
            )
            .expect("synthetic lock is valid")
        })
        .collect();
    NormalizedDdlDocument::new(source, language, locks).expect("synthetic macro document is valid")
}

fn macro_association(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
) -> SemanticAssociationResult {
    let document = locked_macro_document(source, language, definitions);
    let binding = bind_macro_parameters(&document, definitions).expect("accepted I-581 result");
    associate_semantic_entities_with_macro_binding(&document, binding)
}

fn macro_head(entity: &inku_ddl::SemanticEntity) -> &SemanticMacroInvocationHead {
    let SemanticHead::MacroInvocation(head) = &entity.head else {
        panic!("expected MacroInvocation head");
    };
    head
}

fn canonical_head(result: &SemanticAssociationResult, index: usize) -> serde_json::Value {
    serde_json::from_slice::<serde_json::Value>(
        result
            .canonical_bytes
            .as_deref()
            .expect("complete canonical"),
    )
    .expect("canonical JSON")["entities"][index]["head"]
        .clone()
}

fn association_issue_kinds(result: &SemanticAssociationResult) -> Vec<&str> {
    result
        .issues
        .iter()
        .map(|issue| issue.kind.as_str())
        .collect()
}
