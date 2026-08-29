//! Immutable, versioned Stage 1 and Stage 2 prompt body source asset.

use std::sync::OnceLock;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::ResolvedInstructionLanguage;

/// Stable identity for the prompt-body template asset semantics.
pub const PROMPT_BODY_TEMPLATE_ASSET_ID: &str = "inku.prompt-body-templates.v1";

/// The exact embedded UTF-8 source bytes for this asset edition.
pub const PROMPT_BODY_TEMPLATE_ASSET_BYTES: &[u8] =
    include_bytes!("../assets/prompt-body-templates-v1.json");

/// The supported prompt-body stages in canonical asset order.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PromptBodyTemplateStage {
    Stage1,
    Stage2,
}

/// A named placeholder that remains unresolved in a static prompt body.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum PromptBodyTemplateSlot {
    #[serde(rename = "TEXTURE_MATERIAL_ENUMERATION")]
    TextureMaterialEnumeration,
    #[serde(rename = "COUNT_CLAMP")]
    CountClamp,
    #[serde(rename = "COUNT_RANGE_HEADING")]
    CountRangeHeading,
    #[serde(rename = "COUNT_BANDS")]
    CountBands,
    #[serde(rename = "TILE_COUNT")]
    TileCount,
    #[serde(rename = "SAIJIKI_PROMPT_BLOCK")]
    SaijikiPromptBlock,
    #[serde(rename = "CANVAS")]
    Canvas,
    #[serde(rename = "COUNT_DENSITY")]
    CountDensity,
    #[serde(rename = "GRID_COUNT")]
    GridCount,
}

impl PromptBodyTemplateSlot {
    /// Return this slot's literal token in a static body.
    pub const fn token(self) -> &'static str {
        match self {
            Self::TextureMaterialEnumeration => "%%TEXTURE_MATERIAL_ENUMERATION%%",
            Self::CountClamp => "%%COUNT_CLAMP%%",
            Self::CountRangeHeading => "%%COUNT_RANGE_HEADING%%",
            Self::CountBands => "%%COUNT_BANDS%%",
            Self::TileCount => "%%TILE_COUNT%%",
            Self::SaijikiPromptBlock => "%%SAIJIKI_PROMPT_BLOCK%%",
            Self::Canvas => "%%CANVAS%%",
            Self::CountDensity => "%%COUNT_DENSITY%%",
            Self::GridCount => "%%GRID_COUNT%%",
        }
    }

    const fn name(self) -> &'static str {
        match self {
            Self::TextureMaterialEnumeration => "TEXTURE_MATERIAL_ENUMERATION",
            Self::CountClamp => "COUNT_CLAMP",
            Self::CountRangeHeading => "COUNT_RANGE_HEADING",
            Self::CountBands => "COUNT_BANDS",
            Self::TileCount => "TILE_COUNT",
            Self::SaijikiPromptBlock => "SAIJIKI_PROMPT_BLOCK",
            Self::Canvas => "CANVAS",
            Self::CountDensity => "COUNT_DENSITY",
            Self::GridCount => "GRID_COUNT",
        }
    }
}

/// Lossless representation of the complete versioned source asset.
#[derive(Debug, Deserialize, Eq, PartialEq)]
pub struct PromptBodyTemplateAsset {
    pub schema_version: u32,
    pub asset_id: String,
    pub languages: Vec<ResolvedInstructionLanguage>,
    pub stages: Vec<PromptBodyTemplateStageAsset>,
}

/// One stage in the canonical asset order.
#[derive(Debug, Deserialize, Eq, PartialEq)]
pub struct PromptBodyTemplateStageAsset {
    pub stage: PromptBodyTemplateStage,
    pub templates: Vec<PromptBodyTemplate>,
}

/// One static prompt body and its ordered unresolved slots.
#[derive(Debug, Deserialize, Eq, PartialEq)]
pub struct PromptBodyTemplate {
    pub language: ResolvedInstructionLanguage,
    pub body: String,
    pub required_slots: Vec<PromptBodyTemplateSlot>,
}

/// An immutable, typed view of one embedded static prompt body.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PromptBodyTemplateRef {
    pub stage: PromptBodyTemplateStage,
    pub language: ResolvedInstructionLanguage,
    pub body: &'static str,
    pub required_slots: &'static [PromptBodyTemplateSlot],
}

/// A stable validation failure for an invalid prompt-body source asset.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PromptBodyTemplateAssetError {
    InvalidJson,
    MissingTerminalLf,
    InvalidLineEndings,
    ByteOrderMark,
    InvalidSchemaVersion {
        actual: u32,
    },
    AssetIdMismatch {
        actual: String,
    },
    InvalidLanguages,
    InvalidStages,
    InvalidTemplateLanguages {
        stage: PromptBodyTemplateStage,
    },
    EmptyBody {
        stage: PromptBodyTemplateStage,
        language: ResolvedInstructionLanguage,
    },
    BodyByteOrderMark {
        stage: PromptBodyTemplateStage,
        language: ResolvedInstructionLanguage,
    },
    InvalidSlots {
        stage: PromptBodyTemplateStage,
        language: ResolvedInstructionLanguage,
    },
}

impl PromptBodyTemplateAssetError {
    /// Stable machine-readable failure classification.
    pub const fn kind(&self) -> &'static str {
        match self {
            Self::InvalidJson => "invalid_json",
            Self::MissingTerminalLf => "missing_terminal_lf",
            Self::InvalidLineEndings => "invalid_line_endings",
            Self::ByteOrderMark => "byte_order_mark",
            Self::InvalidSchemaVersion { .. } => "invalid_schema_version",
            Self::AssetIdMismatch { .. } => "asset_id_mismatch",
            Self::InvalidLanguages => "invalid_languages",
            Self::InvalidStages => "invalid_stages",
            Self::InvalidTemplateLanguages { .. } => "invalid_template_languages",
            Self::EmptyBody { .. } => "empty_body",
            Self::BodyByteOrderMark { .. } => "body_byte_order_mark",
            Self::InvalidSlots { .. } => "invalid_slots",
        }
    }
}

static PROMPT_BODY_TEMPLATE_ASSET: OnceLock<PromptBodyTemplateAsset> = OnceLock::new();
static PROMPT_BODY_TEMPLATE_ASSET_SHA256_HEX: OnceLock<String> = OnceLock::new();

/// Return the parsed embedded asset, parsing and validating it once per process.
///
/// An invalid embedded edition is a programmer error and deliberately never
/// falls back to a missing body or another language.
pub fn prompt_body_template_asset() -> &'static PromptBodyTemplateAsset {
    PROMPT_BODY_TEMPLATE_ASSET.get_or_init(|| {
        prompt_body_template_asset_from_bytes(PROMPT_BODY_TEMPLATE_ASSET_BYTES)
            .expect("embedded inku.prompt-body-templates.v1 asset must remain valid")
    })
}

/// Parse and validate a prompt-body asset without consulting host state.
pub fn prompt_body_template_asset_from_bytes(
    bytes: &[u8],
) -> Result<PromptBodyTemplateAsset, PromptBodyTemplateAssetError> {
    if bytes.starts_with(&[0xef, 0xbb, 0xbf]) {
        return Err(PromptBodyTemplateAssetError::ByteOrderMark);
    }
    if !bytes.ends_with(b"\n") || bytes.ends_with(b"\n\n") {
        return Err(PromptBodyTemplateAssetError::MissingTerminalLf);
    }
    if bytes.contains(&b'\r') {
        return Err(PromptBodyTemplateAssetError::InvalidLineEndings);
    }
    let asset =
        serde_json::from_slice(bytes).map_err(|_| PromptBodyTemplateAssetError::InvalidJson)?;
    validate_asset(&asset)?;
    Ok(asset)
}

/// Return the lowercase SHA-256 of the exact embedded asset bytes.
pub fn prompt_body_template_asset_sha256_hex() -> &'static str {
    PROMPT_BODY_TEMPLATE_ASSET_SHA256_HEX
        .get_or_init(|| {
            Sha256::digest(PROMPT_BODY_TEMPLATE_ASSET_BYTES)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect()
        })
        .as_str()
}

/// Return one static body by typed stage and resolved language.
pub fn prompt_body_template(
    stage: PromptBodyTemplateStage,
    language: ResolvedInstructionLanguage,
) -> PromptBodyTemplateRef {
    let asset = prompt_body_template_asset();
    let stage_asset = asset
        .stages
        .iter()
        .find(|candidate| candidate.stage == stage)
        .expect("validated prompt-body template stage must exist");
    let template = stage_asset
        .templates
        .iter()
        .find(|candidate| candidate.language == language)
        .expect("validated prompt-body template language must exist");
    PromptBodyTemplateRef {
        stage,
        language,
        body: &template.body,
        required_slots: &template.required_slots,
    }
}

fn validate_asset(asset: &PromptBodyTemplateAsset) -> Result<(), PromptBodyTemplateAssetError> {
    if asset.schema_version != 1 {
        return Err(PromptBodyTemplateAssetError::InvalidSchemaVersion {
            actual: asset.schema_version,
        });
    }
    if asset.asset_id != PROMPT_BODY_TEMPLATE_ASSET_ID {
        return Err(PromptBodyTemplateAssetError::AssetIdMismatch {
            actual: asset.asset_id.clone(),
        });
    }
    if asset.languages
        != [
            ResolvedInstructionLanguage::Ja,
            ResolvedInstructionLanguage::En,
        ]
    {
        return Err(PromptBodyTemplateAssetError::InvalidLanguages);
    }
    let expected_stages = [
        PromptBodyTemplateStage::Stage1,
        PromptBodyTemplateStage::Stage2,
    ];
    if asset
        .stages
        .iter()
        .map(|stage| stage.stage)
        .ne(expected_stages)
    {
        return Err(PromptBodyTemplateAssetError::InvalidStages);
    }
    for stage_asset in &asset.stages {
        if stage_asset
            .templates
            .iter()
            .map(|template| template.language)
            .ne([
                ResolvedInstructionLanguage::Ja,
                ResolvedInstructionLanguage::En,
            ])
        {
            return Err(PromptBodyTemplateAssetError::InvalidTemplateLanguages {
                stage: stage_asset.stage,
            });
        }
        for template in &stage_asset.templates {
            if template.body.is_empty() {
                return Err(PromptBodyTemplateAssetError::EmptyBody {
                    stage: stage_asset.stage,
                    language: template.language,
                });
            }
            if template.body.starts_with('\u{feff}') {
                return Err(PromptBodyTemplateAssetError::BodyByteOrderMark {
                    stage: stage_asset.stage,
                    language: template.language,
                });
            }
            let expected_slots = expected_slots(stage_asset.stage);
            if template.required_slots.as_slice() != expected_slots
                || body_slot_names(&template.body)?
                    != expected_slots
                        .iter()
                        .map(|slot| slot.name())
                        .collect::<Vec<_>>()
            {
                return Err(PromptBodyTemplateAssetError::InvalidSlots {
                    stage: stage_asset.stage,
                    language: template.language,
                });
            }
        }
    }
    Ok(())
}

fn expected_slots(stage: PromptBodyTemplateStage) -> &'static [PromptBodyTemplateSlot] {
    match stage {
        PromptBodyTemplateStage::Stage1 => &[
            PromptBodyTemplateSlot::TextureMaterialEnumeration,
            PromptBodyTemplateSlot::CountClamp,
            PromptBodyTemplateSlot::CountRangeHeading,
            PromptBodyTemplateSlot::CountBands,
            PromptBodyTemplateSlot::TileCount,
            PromptBodyTemplateSlot::SaijikiPromptBlock,
        ],
        PromptBodyTemplateStage::Stage2 => &[
            PromptBodyTemplateSlot::Canvas,
            PromptBodyTemplateSlot::CountDensity,
            PromptBodyTemplateSlot::GridCount,
        ],
    }
}

fn body_slot_names(body: &str) -> Result<Vec<&str>, PromptBodyTemplateAssetError> {
    let mut names = Vec::new();
    let mut remainder = body;
    while let Some(start) = remainder.find("%%") {
        remainder = &remainder[start + 2..];
        let Some(end) = remainder.find("%%") else {
            return Err(PromptBodyTemplateAssetError::InvalidSlots {
                stage: PromptBodyTemplateStage::Stage1,
                language: ResolvedInstructionLanguage::Ja,
            });
        };
        let name = &remainder[..end];
        if name.is_empty() {
            return Err(PromptBodyTemplateAssetError::InvalidSlots {
                stage: PromptBodyTemplateStage::Stage1,
                language: ResolvedInstructionLanguage::Ja,
            });
        }
        names.push(name);
        remainder = &remainder[end + 2..];
    }
    Ok(names)
}
