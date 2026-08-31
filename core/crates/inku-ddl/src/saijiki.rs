//! Immutable, versioned Saijiki and relation source asset.

use std::{
    collections::{BTreeSet, HashMap},
    fmt,
    sync::OnceLock,
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::ResolvedInstructionLanguage;

/// Stable identity for the Saijiki asset semantics.
pub const SAIJIKI_ASSET_ID: &str = "inku.saijiki.v1";

/// The exact embedded UTF-8 source bytes for this asset edition.
pub const SAIJIKI_ASSET_BYTES: &[u8] = include_bytes!("../assets/saijiki-v1.json");

/// Lossless bilingual representation of the versioned Saijiki source asset.
#[derive(Debug, Deserialize, Eq, PartialEq)]
pub struct SaijikiAsset {
    pub schema_version: u32,
    pub asset_id: String,
    pub languages: Vec<String>,
    pub categories: Vec<SaijikiCategoryAsset>,
    pub relations: Vec<RelationAsset>,
    pub relation_marker_order: MarkerOrder,
    pub relation_display_order: Vec<String>,
    pub marker_class_order: Vec<String>,
}

/// A named Saijiki category and its canonical word order.
#[derive(Debug, Deserialize, Eq, PartialEq)]
pub struct SaijikiCategoryAsset {
    pub key: String,
    pub name_ja: String,
    pub name_en: String,
    pub marker_class: Option<String>,
    pub words: Vec<SaijikiWordAsset>,
    pub marker_order_ja: Option<Vec<String>>,
    pub marker_order_en: Option<Vec<String>>,
}

/// One bilingual Saijiki word, including all source flags and marker overrides.
#[derive(Debug, Deserialize, Eq, PartialEq)]
pub struct SaijikiWordAsset {
    pub surface_ja: String,
    pub surface_en: Option<String>,
    pub default: bool,
    pub prompt: bool,
    pub display: bool,
    pub marker: Option<bool>,
    pub score_value: Option<String>,
    pub marker_surfaces_ja: Option<Vec<String>>,
    pub marker_surfaces_en: Option<Vec<String>>,
}

/// The language-specific order used by a relation marker table.
#[derive(Debug, Deserialize, Eq, PartialEq)]
pub struct MarkerOrder {
    pub ja: Vec<String>,
    pub en: Vec<String>,
}

/// One relation type and its fixed bilingual previous-object literals.
#[derive(Debug, Deserialize, Eq, PartialEq)]
pub struct RelationAsset {
    pub relation_type: String,
    pub surface_ja: String,
    pub surface_en: String,
    pub literals_ja: Vec<String>,
    pub literals_en: Vec<String>,
}

/// Closed, language-independent identity of an accepted Saijiki relation row.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CanonicalRelationKind {
    Along,
    NotTouching,
    Touching,
    Cutting,
    Between,
}

impl CanonicalRelationKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Along => "along",
            Self::NotTouching => "not_touching",
            Self::Touching => "touching",
            Self::Cutting => "cutting",
            Self::Between => "between",
        }
    }
}

/// Candidate-time distinction between a short relation and a compound full literal.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CanonicalRelationForm {
    Short,
    FullLiteral,
}

impl CanonicalRelationForm {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Short => "short",
            Self::FullLiteral => "full_literal",
        }
    }
}

/// Closed source-order reference depth carried only by accepted full literals.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CanonicalPreviousReference {
    PreviousOne,
    PreviousTwo,
}

impl CanonicalPreviousReference {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::PreviousOne => "previous_one",
            Self::PreviousTwo => "previous_two",
        }
    }
}

/// One closed relation identity transported unchanged with the source occurrence.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct CanonicalRelationIdentity {
    pub kind: CanonicalRelationKind,
    pub form: CanonicalRelationForm,
    pub previous_reference: Option<CanonicalPreviousReference>,
}

pub(crate) fn canonical_relation_identity(
    relation_type: &str,
    form: CanonicalRelationForm,
) -> Option<CanonicalRelationIdentity> {
    let kind = match relation_type {
        "along" => CanonicalRelationKind::Along,
        "not_touching" => CanonicalRelationKind::NotTouching,
        "touching" => CanonicalRelationKind::Touching,
        "cutting" => CanonicalRelationKind::Cutting,
        "between" => CanonicalRelationKind::Between,
        _ => return None,
    };
    let previous_reference = match form {
        CanonicalRelationForm::Short => None,
        CanonicalRelationForm::FullLiteral => Some(match kind {
            CanonicalRelationKind::Between => CanonicalPreviousReference::PreviousTwo,
            CanonicalRelationKind::Along
            | CanonicalRelationKind::NotTouching
            | CanonicalRelationKind::Touching
            | CanonicalRelationKind::Cutting => CanonicalPreviousReference::PreviousOne,
        }),
    };
    Some(CanonicalRelationIdentity {
        kind,
        form,
        previous_reference,
    })
}

pub(crate) fn canonical_relation_identity_is_valid(
    relation_type: &str,
    identity: CanonicalRelationIdentity,
) -> bool {
    canonical_relation_identity(relation_type, identity.form) == Some(identity)
}

static SAIJIKI_ASSET: OnceLock<SaijikiAsset> = OnceLock::new();
static SAIJIKI_ASSET_SHA256_HEX: OnceLock<String> = OnceLock::new();

/// Return the parsed embedded asset, parsing it exactly once per process.
///
/// The embedded source is a build-time invariant. An invalid edition is a programmer
/// error and deliberately never falls back to an empty registry.
pub fn saijiki_asset() -> &'static SaijikiAsset {
    SAIJIKI_ASSET.get_or_init(|| {
        serde_json::from_slice(SAIJIKI_ASSET_BYTES)
            .expect("embedded inku.saijiki.v1 asset must remain valid JSON")
    })
}

/// Return the lowercase SHA-256 of the exact embedded asset bytes.
pub fn saijiki_asset_sha256_hex() -> &'static str {
    SAIJIKI_ASSET_SHA256_HEX
        .get_or_init(|| {
            Sha256::digest(SAIJIKI_ASSET_BYTES)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect()
        })
        .as_str()
}

/// Return the requested-language parser surface only when this asset row is eligible.
///
/// Candidate membership follows the accepted asset flags. A disabled tombstone remains in the
/// immutable asset but is never promoted into a recognized typed delivery.
pub(crate) fn parser_candidate_surface(
    word: &SaijikiWordAsset,
    language: ResolvedInstructionLanguage,
) -> Option<&str> {
    if !word.prompt && !word.display && word.marker != Some(true) {
        return None;
    }
    match language {
        ResolvedInstructionLanguage::Ja => Some(word.surface_ja.as_str()),
        ResolvedInstructionLanguage::En => word.surface_en.as_deref(),
    }
}

/// A stable failure while deriving a typed Saijiki projection from its asset.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SaijikiProjectionError {
    MissingCategory {
        key: String,
    },
    MissingRelation {
        relation_type: String,
    },
    MissingLanguageSurface {
        category_key: String,
        surface_ja: String,
        language: ResolvedInstructionLanguage,
    },
    MarkerOrderMismatch {
        scope: String,
        language: ResolvedInstructionLanguage,
        missing: Vec<String>,
        unexpected: Vec<String>,
    },
    InvalidMarkerOrderEntry {
        scope: String,
        language: ResolvedInstructionLanguage,
        entry: String,
        matches: usize,
    },
    DuplicateMarkerMember {
        scope: String,
        language: ResolvedInstructionLanguage,
        marker: String,
    },
    MarkerClassOrderMismatch {
        missing: Vec<String>,
        unexpected: Vec<String>,
    },
    MissingScoreValue {
        category_key: String,
        surface_ja: String,
    },
    DuplicateScoreSurface {
        surface: String,
        first_value: String,
        second_value: String,
    },
}

impl SaijikiProjectionError {
    /// Stable machine-readable failure classification.
    pub const fn kind(&self) -> &'static str {
        match self {
            Self::MissingCategory { .. } => "missing_category",
            Self::MissingRelation { .. } => "missing_relation",
            Self::MissingLanguageSurface { .. } => "missing_language_surface",
            Self::MarkerOrderMismatch { .. } => "marker_order_mismatch",
            Self::InvalidMarkerOrderEntry { .. } => "invalid_marker_order_entry",
            Self::DuplicateMarkerMember { .. } => "duplicate_marker_member",
            Self::MarkerClassOrderMismatch { .. } => "marker_class_order_mismatch",
            Self::MissingScoreValue { .. } => "missing_score_value",
            Self::DuplicateScoreSurface { .. } => "duplicate_score_surface",
        }
    }
}

impl fmt::Display for SaijikiProjectionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MissingCategory { key } => {
                write!(formatter, "Saijiki category is missing: {key}")
            }
            Self::MissingRelation { relation_type } => {
                write!(formatter, "Saijiki relation is missing: {relation_type}")
            }
            Self::MissingLanguageSurface {
                category_key,
                surface_ja,
                language,
            } => write!(
                formatter,
                "Saijiki word has no {} surface: {category_key}/{surface_ja}",
                language.as_str()
            ),
            Self::MarkerOrderMismatch {
                scope,
                language,
                missing,
                unexpected,
            } => write!(
                formatter,
                "Saijiki marker order mismatch for {scope}/{}: missing={missing:?}, unexpected={unexpected:?}",
                language.as_str()
            ),
            Self::InvalidMarkerOrderEntry {
                scope,
                language,
                entry,
                matches,
            } => write!(
                formatter,
                "Saijiki marker order entry is not uniquely mapped for {scope}/{}: {entry} ({matches} matches)",
                language.as_str()
            ),
            Self::DuplicateMarkerMember {
                scope,
                language,
                marker,
            } => write!(
                formatter,
                "Saijiki enabled marker is duplicated for {scope}/{}: {marker}",
                language.as_str()
            ),
            Self::MarkerClassOrderMismatch {
                missing,
                unexpected,
            } => write!(
                formatter,
                "Saijiki marker class order mismatch: missing={missing:?}, unexpected={unexpected:?}"
            ),
            Self::MissingScoreValue {
                category_key,
                surface_ja,
            } => write!(
                formatter,
                "Saijiki score value is missing: {category_key}/{surface_ja}"
            ),
            Self::DuplicateScoreSurface {
                surface,
                first_value,
                second_value,
            } => write!(
                formatter,
                "Saijiki score surface maps to conflicting values: {surface} ({first_value}, {second_value})"
            ),
        }
    }
}

impl std::error::Error for SaijikiProjectionError {}

/// One ordered category row for the reference projection.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ReferenceCategoryProjection {
    pub name: String,
    pub words: Vec<String>,
}

/// One ordered category row for the Saijiki display projection.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct DisplayCategoryProjection {
    pub key: String,
    pub name_ja: String,
    pub name_en: String,
    pub words: Vec<String>,
}

/// One ordered marker row for a marker class in one resolved language.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct MarkerClassProjection {
    pub marker_class: String,
    pub markers: Vec<String>,
}

/// One relation's fixed literals, with Japanese literals before English literals.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct RelationLiteralProjection {
    pub relation_type: String,
    pub literals: Vec<String>,
}

/// One ordered bilingual surface-to-Score-wire pair.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct SaijikiSurfaceScoreProjection {
    pub surface: String,
    pub score_value: String,
}

/// Ordered Score wire maps derived from the embedded Saijiki asset.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct SaijikiScoreWireMaps {
    pub weight: Vec<SaijikiSurfaceScoreProjection>,
    pub color: Vec<SaijikiSurfaceScoreProjection>,
    pub surface_texture: Vec<SaijikiSurfaceScoreProjection>,
}

/// All language-specific, ordered Saijiki projections consumed by a host.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct SaijikiDerivedProjection {
    pub prompt_block: String,
    pub texture_material_enumeration: String,
    pub shape_markers: Vec<String>,
    pub core_grammar_markers: Vec<String>,
    pub reference_categories: Vec<ReferenceCategoryProjection>,
    pub display_categories: Vec<DisplayCategoryProjection>,
}

/// Derive every language-specific projection from the embedded typed asset.
pub fn saijiki_derived_projection(
    language: ResolvedInstructionLanguage,
) -> Result<SaijikiDerivedProjection, SaijikiProjectionError> {
    saijiki_derived_projection_from_asset(saijiki_asset(), language)
}

/// Derive every language-specific projection from a typed Saijiki asset.
///
/// This is public so callers that validate a separately supplied typed asset can receive the
/// same stable errors as the embedded-asset path. It never performs I/O or language resolution.
pub fn saijiki_derived_projection_from_asset(
    asset: &SaijikiAsset,
    language: ResolvedInstructionLanguage,
) -> Result<SaijikiDerivedProjection, SaijikiProjectionError> {
    let prompt_rows = prompt_rows(asset, language)?;
    let prompt_block = prompt_rows
        .iter()
        .map(|row| format!("{}: {}", row.name, row.words.join(word_joiner(language))))
        .collect::<Vec<_>>()
        .join("\n");

    let texture_words = prompt_surfaces(required_category(asset, "tezawari")?, language)?;
    let texture_material_enumeration = match language {
        ResolvedInstructionLanguage::Ja => texture_words.join("・"),
        ResolvedInstructionLanguage::En => match texture_words.as_slice() {
            [] => String::new(),
            [word] => word.clone(),
            words => format!(
                "{}, or {}",
                words[..words.len() - 1].join(", "),
                words.last().unwrap()
            ),
        },
    };

    let shape_markers = category_markers(required_category(asset, "katachi")?, language)?;
    let operation_markers = category_markers(required_category(asset, "ugoki")?, language)?;
    let relation_markers = relation_markers(asset, language)?;
    let mut core_grammar_markers = shape_markers.clone();
    core_grammar_markers.extend(operation_markers);
    core_grammar_markers.extend(relation_markers);

    let mut display_categories = Vec::with_capacity(asset.categories.len() + 1);
    for category in &asset.categories {
        let words = category
            .words
            .iter()
            .filter(|word| word.display)
            .filter_map(|word| language_surface(word, language).map(str::to_owned))
            .collect();
        display_categories.push(DisplayCategoryProjection {
            key: category.key.clone(),
            name_ja: category.name_ja.clone(),
            name_en: category.name_en.clone(),
            words,
        });
    }
    let relations_by_type: HashMap<&str, &RelationAsset> = asset
        .relations
        .iter()
        .map(|relation| (relation.relation_type.as_str(), relation))
        .collect();
    let relation_words = asset
        .relation_display_order
        .iter()
        .map(|relation_type| {
            relations_by_type
                .get(relation_type.as_str())
                .ok_or_else(|| SaijikiProjectionError::MissingRelation {
                    relation_type: relation_type.clone(),
                })
                .map(|relation| relation_surface(relation, language).to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    display_categories.push(DisplayCategoryProjection {
        key: "aida".to_owned(),
        name_ja: "あいだ".to_owned(),
        name_en: "relations".to_owned(),
        words: relation_words,
    });

    Ok(SaijikiDerivedProjection {
        prompt_block,
        texture_material_enumeration,
        shape_markers,
        core_grammar_markers,
        reference_categories: prompt_rows,
        display_categories,
    })
}

/// Return the ordered marker-class table for one resolved language.
pub fn saijiki_marker_class_table(
    language: ResolvedInstructionLanguage,
) -> Result<Vec<MarkerClassProjection>, SaijikiProjectionError> {
    let asset = saijiki_asset();
    let by_class: HashMap<&str, &SaijikiCategoryAsset> = asset
        .categories
        .iter()
        .filter_map(|category| match category.marker_class.as_deref() {
            Some("shape" | "operation") | None => None,
            Some(marker_class) => Some((marker_class, category)),
        })
        .collect();
    let expected: BTreeSet<&str> = asset
        .marker_class_order
        .iter()
        .map(String::as_str)
        .collect();
    let actual: BTreeSet<&str> = by_class.keys().copied().collect();
    if expected != actual {
        return Err(SaijikiProjectionError::MarkerClassOrderMismatch {
            missing: expected
                .difference(&actual)
                .map(|value| (*value).to_owned())
                .collect(),
            unexpected: actual
                .difference(&expected)
                .map(|value| (*value).to_owned())
                .collect(),
        });
    }
    asset
        .marker_class_order
        .iter()
        .map(|marker_class| {
            let category = by_class[marker_class.as_str()];
            Ok(MarkerClassProjection {
                marker_class: marker_class.clone(),
                markers: category_markers(category, language)?,
            })
        })
        .collect()
}

/// Return relation literals in their asset storage order.
pub fn saijiki_relation_literal_table() -> Vec<RelationLiteralProjection> {
    saijiki_asset()
        .relations
        .iter()
        .map(|relation| RelationLiteralProjection {
            relation_type: relation.relation_type.clone(),
            literals: relation
                .literals_ja
                .iter()
                .chain(&relation.literals_en)
                .cloned()
                .collect(),
        })
        .collect()
}

/// Return ordered Score wire maps, preserving category and Japanese-then-English surface order.
pub fn saijiki_score_wire_maps() -> Result<SaijikiScoreWireMaps, SaijikiProjectionError> {
    let asset = saijiki_asset();
    Ok(SaijikiScoreWireMaps {
        weight: surface_score_pairs(required_category(asset, "tezawari")?, &[])?,
        color: surface_score_pairs(required_category(asset, "iro")?, &[])?,
        surface_texture: surface_score_pairs(
            required_category(asset, "omote")?,
            &["濃い", "薄い"],
        )?,
    })
}

fn required_category<'a>(
    asset: &'a SaijikiAsset,
    key: &str,
) -> Result<&'a SaijikiCategoryAsset, SaijikiProjectionError> {
    asset
        .categories
        .iter()
        .find(|category| category.key == key)
        .ok_or_else(|| SaijikiProjectionError::MissingCategory {
            key: key.to_owned(),
        })
}

fn word_joiner(language: ResolvedInstructionLanguage) -> &'static str {
    match language {
        ResolvedInstructionLanguage::Ja => "、",
        ResolvedInstructionLanguage::En => ", ",
    }
}

fn language_surface(
    word: &SaijikiWordAsset,
    language: ResolvedInstructionLanguage,
) -> Option<&str> {
    match language {
        ResolvedInstructionLanguage::Ja => Some(word.surface_ja.as_str()),
        ResolvedInstructionLanguage::En => word.surface_en.as_deref(),
    }
}

fn required_language_surface<'a>(
    category: &SaijikiCategoryAsset,
    word: &'a SaijikiWordAsset,
    language: ResolvedInstructionLanguage,
) -> Result<&'a str, SaijikiProjectionError> {
    language_surface(word, language).ok_or_else(|| SaijikiProjectionError::MissingLanguageSurface {
        category_key: category.key.clone(),
        surface_ja: word.surface_ja.clone(),
        language,
    })
}

fn annotated_word(
    category: &SaijikiCategoryAsset,
    word: &SaijikiWordAsset,
    language: ResolvedInstructionLanguage,
) -> Result<String, SaijikiProjectionError> {
    let surface = required_language_surface(category, word, language)?;
    if word.default {
        Ok(match language {
            ResolvedInstructionLanguage::Ja => format!("{surface}(既定)"),
            ResolvedInstructionLanguage::En => format!("{surface} (default)"),
        })
    } else {
        Ok(surface.to_owned())
    }
}

fn prompt_words(
    category: &SaijikiCategoryAsset,
    language: ResolvedInstructionLanguage,
) -> Result<Vec<String>, SaijikiProjectionError> {
    category
        .words
        .iter()
        .filter(|word| word.prompt && language_surface(word, language).is_some())
        .map(|word| annotated_word(category, word, language))
        .collect()
}

fn prompt_surfaces(
    category: &SaijikiCategoryAsset,
    language: ResolvedInstructionLanguage,
) -> Result<Vec<String>, SaijikiProjectionError> {
    category
        .words
        .iter()
        .filter(|word| word.prompt && language_surface(word, language).is_some())
        .map(|word| required_language_surface(category, word, language).map(str::to_owned))
        .collect()
}

fn prompt_rows(
    asset: &SaijikiAsset,
    language: ResolvedInstructionLanguage,
) -> Result<Vec<ReferenceCategoryProjection>, SaijikiProjectionError> {
    asset
        .categories
        .iter()
        .map(|category| {
            Ok(ReferenceCategoryProjection {
                name: match language {
                    ResolvedInstructionLanguage::Ja => category.name_ja.clone(),
                    ResolvedInstructionLanguage::En => category.name_en.clone(),
                },
                words: prompt_words(category, language)?,
            })
        })
        .collect()
}

fn marker_names(word: &SaijikiWordAsset, language: ResolvedInstructionLanguage) -> Vec<String> {
    let override_names = match language {
        ResolvedInstructionLanguage::Ja => &word.marker_surfaces_ja,
        ResolvedInstructionLanguage::En => &word.marker_surfaces_en,
    };
    override_names.clone().unwrap_or_else(|| {
        language_surface(word, language)
            .map(|surface| vec![surface.to_owned()])
            .unwrap_or_default()
    })
}

fn category_markers(
    category: &SaijikiCategoryAsset,
    language: ResolvedInstructionLanguage,
) -> Result<Vec<String>, SaijikiProjectionError> {
    let enabled = category
        .words
        .iter()
        .filter(|word| word.marker.unwrap_or(word.prompt))
        .filter(|word| language_surface(word, language).is_some())
        .flat_map(|word| marker_names(word, language))
        .collect::<Vec<_>>();
    let enabled_set = unique_marker_members(category, language, &enabled)?;
    let order = match language {
        ResolvedInstructionLanguage::Ja => category.marker_order_ja.as_ref(),
        ResolvedInstructionLanguage::En => category.marker_order_en.as_ref(),
    };
    let Some(order) = order else {
        return Ok(enabled);
    };
    let mut selected = Vec::with_capacity(order.len());
    for entry in order {
        let matches = category
            .words
            .iter()
            .filter(|word| {
                marker_names(word, language)
                    .iter()
                    .any(|name| name == entry)
            })
            .collect::<Vec<_>>();
        let [word] = matches.as_slice() else {
            return Err(SaijikiProjectionError::InvalidMarkerOrderEntry {
                scope: category.key.clone(),
                language,
                entry: entry.clone(),
                matches: matches.len(),
            });
        };
        if word.marker.unwrap_or(word.prompt) && language_surface(word, language).is_some() {
            selected.push(entry.clone());
        }
    }
    let selected_set = unique_marker_members(category, language, &selected)?;
    if enabled_set != selected_set {
        return Err(SaijikiProjectionError::MarkerOrderMismatch {
            scope: category.key.clone(),
            language,
            missing: enabled_set
                .difference(&selected_set)
                .map(|value| (*value).to_owned())
                .collect(),
            unexpected: selected_set
                .difference(&enabled_set)
                .map(|value| (*value).to_owned())
                .collect(),
        });
    }
    Ok(selected)
}

fn unique_marker_members<'a>(
    category: &SaijikiCategoryAsset,
    language: ResolvedInstructionLanguage,
    markers: &'a [String],
) -> Result<BTreeSet<&'a str>, SaijikiProjectionError> {
    let mut unique = BTreeSet::new();
    for marker in markers {
        if !unique.insert(marker.as_str()) {
            return Err(SaijikiProjectionError::DuplicateMarkerMember {
                scope: category.key.clone(),
                language,
                marker: marker.clone(),
            });
        }
    }
    Ok(unique)
}

fn relation_surface(relation: &RelationAsset, language: ResolvedInstructionLanguage) -> &str {
    match language {
        ResolvedInstructionLanguage::Ja => &relation.surface_ja,
        ResolvedInstructionLanguage::En => &relation.surface_en,
    }
}

fn relation_markers(
    asset: &SaijikiAsset,
    language: ResolvedInstructionLanguage,
) -> Result<Vec<String>, SaijikiProjectionError> {
    let enabled = asset
        .relations
        .iter()
        .map(|relation| relation_surface(relation, language))
        .collect::<BTreeSet<_>>();
    let order = match language {
        ResolvedInstructionLanguage::Ja => &asset.relation_marker_order.ja,
        ResolvedInstructionLanguage::En => &asset.relation_marker_order.en,
    };
    let ordered: BTreeSet<&str> = order.iter().map(String::as_str).collect();
    if enabled != ordered {
        return Err(SaijikiProjectionError::MarkerOrderMismatch {
            scope: "relations".to_owned(),
            language,
            missing: enabled
                .difference(&ordered)
                .map(|value| (*value).to_owned())
                .collect(),
            unexpected: ordered
                .difference(&enabled)
                .map(|value| (*value).to_owned())
                .collect(),
        });
    }
    Ok(order.clone())
}

fn surface_score_pairs(
    category: &SaijikiCategoryAsset,
    explicit_exclusions: &[&str],
) -> Result<Vec<SaijikiSurfaceScoreProjection>, SaijikiProjectionError> {
    let mut pairs = Vec::new();
    let mut values_by_surface = HashMap::<&str, &str>::new();
    for word in &category.words {
        if explicit_exclusions.contains(&word.surface_ja.as_str()) {
            continue;
        }
        let value = word.score_value.as_deref().ok_or_else(|| {
            SaijikiProjectionError::MissingScoreValue {
                category_key: category.key.clone(),
                surface_ja: word.surface_ja.clone(),
            }
        })?;
        for surface in std::iter::once(word.surface_ja.as_str()).chain(word.surface_en.as_deref()) {
            if let Some(first_value) = values_by_surface.insert(surface, value)
                && first_value != value
            {
                return Err(SaijikiProjectionError::DuplicateScoreSurface {
                    surface: surface.to_owned(),
                    first_value: first_value.to_owned(),
                    second_value: value.to_owned(),
                });
            }
            pairs.push(SaijikiSurfaceScoreProjection {
                surface: surface.to_owned(),
                score_value: value.to_owned(),
            });
        }
    }
    Ok(pairs)
}
