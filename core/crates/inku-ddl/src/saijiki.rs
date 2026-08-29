//! Immutable, versioned Saijiki and relation source asset.

use std::sync::OnceLock;

use serde::Deserialize;
use sha2::{Digest, Sha256};

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
