//! Serializable compile-once delivery and checked pure-core rendering boundary.

use std::fmt;

use inku_ddl::{
    MacroDefinition, MacroExpansionLimits, NormalizedDdlDocument,
    RESOURCE_COMPILER_EXECUTION_SCHEMA_ID, ScoreLoweringContext, ScoreLoweringOutcome,
    Stage15Variation, Stage15VariationAmplitude, TYPED_DDL_COMPILATION_SCHEMA_ID,
    compile_ddl_to_score_with_resources,
};
use inku_render::{
    compat_clip::ClipLimits,
    palette::work_palette_context,
    render::{CompatFillClipPolicy, RenderError, render_with_resources},
    types::{RenderOptions, RenderOutput, RenderRequest},
};
use inku_score::{
    CANVAS_FORMAT_REGISTRY_ID, Color, HardResourcePolicy, OperationalResourceBudget,
    ResolvedPaletteColor, ResolvedPaletteContext, ResourceDemand, Score, ScoreErrorPolicy,
    canonical_score_digest, canvas_format_registry_digest, lookup_canvas_format,
    validate_canvas_format_id,
};
use serde::{Deserialize, Deserializer, Serialize, de};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::protocol::DecimalU64;

pub const COMPILED_DELIVERY_SCHEMA_ID: &str = "inku.pipeline-compiled-delivery.v1";

/// How the concrete catalog snapshot was selected before compilation.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CatalogMode {
    Explicit,
    Default,
    AutoSelected,
    AutoFallbackDefault,
    Saved,
}

/// One exact concrete observation from the catalog selected by the host.
#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResolvedPaletteColorDto {
    pub abstract_color: Color,
    pub concrete_rgb: [u8; 3],
    pub oklch_lightness: f64,
}

impl ResolvedPaletteColorDto {
    const fn resolved(self) -> ResolvedPaletteColor {
        ResolvedPaletteColor::new(self.abstract_color, self.concrete_rgb, self.oklch_lightness)
    }
}

/// Complete role observations used by Score lowering; this contains no catalog lookup.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ResolvedPaletteDto {
    pub background: ResolvedPaletteColorDto,
    pub black: ResolvedPaletteColorDto,
    pub white: ResolvedPaletteColorDto,
    pub observations: Option<[ResolvedPaletteColorDto; 9]>,
}

impl ResolvedPaletteDto {
    fn resolved(&self) -> ResolvedPaletteContext {
        let context = ResolvedPaletteContext::new(
            self.background.resolved(),
            self.black.resolved(),
            self.white.resolved(),
        );
        match self.observations {
            Some(observations) => {
                context.with_observations(observations.map(|item| item.resolved()))
            }
            None => context,
        }
    }
}

/// Validated host selections carried beside, and excluded from, visible DDL.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ResolvedHostOptions {
    canvas_format_id: String,
    canvas_format_registry_id: String,
    canvas_format_registry_digest: String,
    resolved_catalog_id: String,
    catalog_mode: CatalogMode,
    background: Color,
    palette: ResolvedPaletteDto,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct UnvalidatedResolvedHostOptions {
    canvas_format_id: String,
    canvas_format_registry_id: String,
    canvas_format_registry_digest: String,
    resolved_catalog_id: String,
    catalog_mode: CatalogMode,
    background: Color,
    palette: ResolvedPaletteDto,
}

impl ResolvedHostOptions {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        canvas_format_id: impl Into<String>,
        canvas_format_registry_id: impl Into<String>,
        canvas_format_registry_digest: impl Into<String>,
        resolved_catalog_id: impl Into<String>,
        catalog_mode: CatalogMode,
        background: Color,
        palette: ResolvedPaletteDto,
    ) -> Result<Self, BoundaryError> {
        let result = Self {
            canvas_format_id: canvas_format_id.into(),
            canvas_format_registry_id: canvas_format_registry_id.into(),
            canvas_format_registry_digest: canvas_format_registry_digest.into(),
            resolved_catalog_id: resolved_catalog_id.into(),
            catalog_mode,
            background,
            palette,
        };
        result.validate()?;
        Ok(result)
    }

    pub fn validate(&self) -> Result<(), BoundaryError> {
        if self.canvas_format_registry_id != CANVAS_FORMAT_REGISTRY_ID {
            return Err(BoundaryError::HostOptions(
                HostOptionsError::CanvasRegistryIdMismatch,
            ));
        }
        let current_digest = canvas_format_registry_digest()
            .map_err(|_| BoundaryError::HostOptions(HostOptionsError::CanvasRegistryUnavailable))?;
        if self.canvas_format_registry_digest != current_digest {
            return Err(BoundaryError::HostOptions(
                HostOptionsError::CanvasRegistryDigestMismatch,
            ));
        }
        validate_canvas_format_id(&self.canvas_format_id)
            .map_err(|_| BoundaryError::HostOptions(HostOptionsError::UnknownCanvasFormat))?;
        if self.resolved_catalog_id.trim().is_empty() {
            return Err(BoundaryError::HostOptions(
                HostOptionsError::EmptyResolvedCatalogId,
            ));
        }
        if matches!(
            self.catalog_mode,
            CatalogMode::Default | CatalogMode::AutoFallbackDefault
        ) && self.resolved_catalog_id != "default"
        {
            return Err(BoundaryError::HostOptions(
                HostOptionsError::CatalogModeMismatch,
            ));
        }
        self.lowering_context()?;
        Ok(())
    }

    pub fn lowering_context(&self) -> Result<ScoreLoweringContext, BoundaryError> {
        ScoreLoweringContext::resolve_with_palette(
            &self.canvas_format_id,
            self.background,
            self.palette.resolved(),
        )
        .map_err(|_| BoundaryError::HostOptions(HostOptionsError::InvalidResolvedPalette))
    }

    pub fn with_catalog_mode(mut self, catalog_mode: CatalogMode) -> Result<Self, BoundaryError> {
        self.catalog_mode = catalog_mode;
        self.validate()?;
        Ok(self)
    }

    pub fn canvas_format_id(&self) -> &str {
        &self.canvas_format_id
    }

    pub fn canvas_format_registry_id(&self) -> &str {
        &self.canvas_format_registry_id
    }

    pub fn canvas_format_registry_digest(&self) -> &str {
        &self.canvas_format_registry_digest
    }

    pub fn resolved_catalog_id(&self) -> &str {
        &self.resolved_catalog_id
    }

    pub const fn catalog_mode(&self) -> CatalogMode {
        self.catalog_mode
    }

    pub const fn background(&self) -> Color {
        self.background
    }

    pub const fn palette(&self) -> &ResolvedPaletteDto {
        &self.palette
    }
}

impl<'de> Deserialize<'de> for ResolvedHostOptions {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let options = UnvalidatedResolvedHostOptions::deserialize(deserializer)?;
        Self::new(
            options.canvas_format_id,
            options.canvas_format_registry_id,
            options.canvas_format_registry_digest,
            options.resolved_catalog_id,
            options.catalog_mode,
            options.background,
            options.palette,
        )
        .map_err(de::Error::custom)
    }
}

/// Explicit bounded macro expansion values, encoded safely across JS hosts.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MacroExpansionLimitsDto {
    pub max_invocations: DecimalU64,
    pub max_depth: DecimalU64,
    pub max_evaluation_steps: DecimalU64,
    pub max_nodes_per_invocation: DecimalU64,
    pub max_total_nodes: DecimalU64,
}

impl MacroExpansionLimitsDto {
    fn checked(self) -> Result<MacroExpansionLimits, BoundaryError> {
        let result = MacroExpansionLimits {
            max_invocations: self.max_invocations.get(),
            max_depth: self.max_depth.get(),
            max_evaluation_steps: self.max_evaluation_steps.get(),
            max_nodes_per_invocation: self.max_nodes_per_invocation.get(),
            max_total_nodes: self.max_total_nodes.get(),
        };
        if result.max_invocations == 0
            || result.max_depth == 0
            || result.max_evaluation_steps == 0
            || result.max_nodes_per_invocation == 0
            || result.max_total_nodes == 0
        {
            return Err(BoundaryError::InvalidMacroExpansionLimits);
        }
        Ok(result)
    }
}

/// One explicit Stage 1.5 request; absence and seed zero remain distinct.
#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Stage15VariationDto {
    pub amplitude: Stage15VariationAmplitude,
    pub seed: DecimalU64,
}

impl Stage15VariationDto {
    const fn resolved(self) -> Stage15Variation {
        Stage15Variation {
            amplitude: self.amplitude,
            seed: self.seed.get(),
        }
    }
}

/// Every compile authority is supplied by the caller. This type defines no defaults.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct CompilerOptions {
    pub host: ResolvedHostOptions,
    pub composition_seed: Option<DecimalU64>,
    pub macro_expansion_limits: MacroExpansionLimitsDto,
    pub stage15_variation: Option<Stage15VariationDto>,
    pub error_policy: ScoreErrorPolicy,
    pub hard_resource_policy: HardResourcePolicy,
    pub operational_resource_budget: OperationalResourceBudget,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct UnvalidatedCompilerOptions {
    host: ResolvedHostOptions,
    composition_seed: Option<DecimalU64>,
    macro_expansion_limits: MacroExpansionLimitsDto,
    stage15_variation: Option<Stage15VariationDto>,
    error_policy: ScoreErrorPolicy,
    hard_resource_policy: HardResourcePolicy,
    operational_resource_budget: OperationalResourceBudget,
}

impl CompilerOptions {
    pub fn validate(&self) -> Result<(), BoundaryError> {
        self.host.validate()?;
        self.macro_expansion_limits.checked()?;
        Ok(())
    }

    pub fn macro_limits(&self) -> Result<MacroExpansionLimits, BoundaryError> {
        self.validate()?;
        self.macro_expansion_limits.checked()
    }

    pub fn composition_seed(&self) -> Result<Option<u64>, BoundaryError> {
        self.validate()?;
        Ok(self.composition_seed.map(DecimalU64::get))
    }

    pub fn stage15_variation(&self) -> Result<Option<Stage15Variation>, BoundaryError> {
        self.validate()?;
        Ok(self.stage15_variation.map(Stage15VariationDto::resolved))
    }
}

impl<'de> Deserialize<'de> for CompilerOptions {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let wire = UnvalidatedCompilerOptions::deserialize(deserializer)?;
        let options = Self {
            host: wire.host,
            composition_seed: wire.composition_seed,
            macro_expansion_limits: wire.macro_expansion_limits,
            stage15_variation: wire.stage15_variation,
            error_policy: wire.error_policy,
            hard_resource_policy: wire.hard_resource_policy,
            operational_resource_budget: wire.operational_resource_budget,
        };
        options.validate().map_err(de::Error::custom)?;
        Ok(options)
    }
}

/// Restorable compiler result; diagnostic payloads retain their full typed structure.
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CompiledDelivery {
    pub schema_id: String,
    pub compiler_execution_schema_id: String,
    pub compiler_options: CompilerOptions,
    pub compilation_schema_id: String,
    pub source_digest: String,
    pub semantic_digest: Option<String>,
    pub compiler_lock_digest: Option<String>,
    pub compiler_lock: Option<Value>,
    pub execution_pre_expansion_digest: Option<String>,
    pub effective_stage15_digest: Option<String>,
    pub score_digest: Option<String>,
    pub demand: Option<ResourceDemand>,
    pub outcome: ScoreLoweringOutcome,
    pub score: Option<Score>,
    pub upstream_diagnostics: Vec<Value>,
    pub downstream_diagnostics: Vec<Value>,
    pub resource_omissions: Vec<Value>,
    pub relation_omissions: Vec<Value>,
    pub resource_failure: Option<Value>,
    pub instruction_origins: Vec<Value>,
    pub anchor_origins: Vec<Value>,
}

impl CompiledDelivery {
    pub fn validate(&self) -> Result<(), BoundaryError> {
        if self.schema_id != COMPILED_DELIVERY_SCHEMA_ID
            || self.compiler_execution_schema_id != RESOURCE_COMPILER_EXECUTION_SCHEMA_ID
            || self.compilation_schema_id != TYPED_DDL_COMPILATION_SCHEMA_ID
        {
            return Err(BoundaryError::InvalidCompiledDelivery);
        }
        self.compiler_options.validate()?;

        match &self.compiler_lock {
            Some(Value::Object(lock)) => {
                if lock.get("visible_source_digest").and_then(Value::as_str)
                    != Some(self.source_digest.as_str())
                    || lock.get("full_digest").and_then(Value::as_str)
                        != self.compiler_lock_digest.as_deref()
                    || lock
                        .get("canonical_pre_expansion_digest")
                        .and_then(Value::as_str)
                        != self.semantic_digest.as_deref()
                {
                    return Err(BoundaryError::InvalidCompiledDelivery);
                }
            }
            None if self.compiler_lock_digest.is_none() && self.semantic_digest.is_none() => {}
            Some(_) | None => return Err(BoundaryError::InvalidCompiledDelivery),
        }

        match (&self.score, self.score_digest.as_deref(), self.outcome) {
            (Some(score), Some(expected), outcome) if outcome != ScoreLoweringOutcome::Stopped => {
                let actual =
                    canonical_score_digest(score).map_err(|_| BoundaryError::ScoreSerialization)?;
                if actual != expected {
                    return Err(BoundaryError::ScoreIdentityMismatch);
                }
            }
            (None, None, ScoreLoweringOutcome::Stopped) => {}
            _ => return Err(BoundaryError::InvalidCompiledDelivery),
        }
        Ok(())
    }
}

/// Compile the exact committed document once and retain all observable evidence.
pub fn compile_committed(
    document: NormalizedDdlDocument,
    definitions: &[MacroDefinition],
    options: &CompilerOptions,
) -> Result<CompiledDelivery, BoundaryError> {
    options.validate()?;
    let source_digest = sha256_hex(document.source().as_bytes());
    let result = compile_ddl_to_score_with_resources(
        document,
        definitions,
        options.composition_seed()?,
        options.macro_limits()?,
        options.host.lowering_context()?,
        options.stage15_variation()?,
        options.error_policy,
        options.hard_resource_policy.clone(),
        options.operational_resource_budget,
    );
    let compilation = result.compilation();
    let semantic_digest = compilation
        .compiler_lock
        .as_ref()
        .and_then(|lock| lock.canonical_pre_expansion_digest.clone());
    let compiler_lock_digest = compilation
        .compiler_lock
        .as_ref()
        .map(|lock| lock.full_digest.clone());
    let compiler_lock = compilation
        .compiler_lock
        .as_ref()
        .map(serialize_exact_value)
        .transpose()?;
    let score = result.score().cloned();
    let score_digest = score
        .as_ref()
        .map(canonical_score_digest)
        .transpose()
        .map_err(|_| BoundaryError::ScoreSerialization)?;

    let delivery = CompiledDelivery {
        schema_id: COMPILED_DELIVERY_SCHEMA_ID.to_owned(),
        compiler_execution_schema_id: result.schema_id().to_owned(),
        compiler_options: options.clone(),
        compilation_schema_id: compilation.schema_id.to_owned(),
        source_digest,
        semantic_digest,
        compiler_lock_digest,
        compiler_lock,
        execution_pre_expansion_digest: result.execution_pre_expansion_digest().map(str::to_owned),
        effective_stage15_digest: result.effective_stage15_digest().map(str::to_owned),
        score_digest,
        demand: result.demand(),
        outcome: result.outcome(),
        score,
        upstream_diagnostics: serialize_exact_values(result.upstream_diagnostics())?,
        downstream_diagnostics: serialize_exact_values(result.downstream_diagnostics())?,
        resource_omissions: serialize_exact_values(result.resource_omissions())?,
        relation_omissions: serialize_exact_values(result.relation_omissions())?,
        resource_failure: result.failure().map(serialize_exact_value).transpose()?,
        instruction_origins: serialize_exact_values(result.instruction_origins())?,
        anchor_origins: serialize_exact_values(result.anchor_origins())?,
    };
    delivery.validate()?;
    Ok(delivery)
}

/// Serializable caller-owned Compat clipping policy with no implicit limits.
#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClipPolicy {
    pub tolerance_pixels: f64,
    pub max_nodes: DecimalU64,
    pub max_path_elements: DecimalU64,
    pub max_flattened_points: DecimalU64,
    pub max_work: DecimalU64,
    pub max_output_vertices: DecimalU64,
}

/// Descriptive public name used by the orchestration snapshot.
pub type SerializableClipPolicy = ClipPolicy;

impl ClipPolicy {
    fn resolved(self) -> Result<CompatFillClipPolicy, BoundaryError> {
        if !self.tolerance_pixels.is_finite() || self.tolerance_pixels <= 0.0 {
            return Err(BoundaryError::InvalidClipTolerance);
        }
        let limit = |value: DecimalU64| {
            usize::try_from(value.get()).map_err(|_| BoundaryError::InvalidClipLimit)
        };
        Ok(CompatFillClipPolicy {
            tolerance_pixels: self.tolerance_pixels,
            limits: ClipLimits {
                max_nodes: limit(self.max_nodes)?,
                max_path_elements: limit(self.max_path_elements)?,
                max_flattened_points: limit(self.max_flattened_points)?,
                max_work: limit(self.max_work)?,
                max_output_vertices: limit(self.max_output_vertices)?,
            },
        })
    }
}

/// Replay without changing the saved Score, under independent host policies.
pub fn render_saved_score(
    request: RenderRequest,
    hard_policy: &HardResourcePolicy,
    operational_budget: OperationalResourceBudget,
    clip: ClipPolicy,
) -> Result<RenderOutput, BoundaryError> {
    render_with_resources(request, hard_policy, operational_budget, clip.resolved()?)
        .map_err(BoundaryError::Render)
}

/// Render only the Score and identities produced by the matching compiler options.
pub fn render_delivery(
    delivery: &CompiledDelivery,
    options: RenderOptions,
    compiler: &CompilerOptions,
    clip: ClipPolicy,
) -> Result<RenderOutput, BoundaryError> {
    compiler.validate()?;
    delivery.validate()?;
    if &delivery.compiler_options != compiler {
        return Err(BoundaryError::CompilerOptionsMismatch);
    }
    if options.canvas_aspect_id != compiler.host.canvas_format_id() {
        return Err(BoundaryError::RenderIdentityMismatch(
            RenderIdentityField::CanvasFormat,
        ));
    }
    if !render_canvas_matches_registry(&options, compiler.host.canvas_format_id()) {
        return Err(BoundaryError::RenderIdentityMismatch(
            RenderIdentityField::CanvasGeometry,
        ));
    }
    if options.catalog_id.as_deref() != Some(compiler.host.resolved_catalog_id()) {
        return Err(BoundaryError::RenderIdentityMismatch(
            RenderIdentityField::ResolvedCatalog,
        ));
    }
    let expected_composition_seed = compiler.composition_seed()?.map(i128::from);
    if options.composition_seed != expected_composition_seed {
        return Err(BoundaryError::RenderIdentityMismatch(
            RenderIdentityField::CompositionSeed,
        ));
    }
    if options.error_policy != compiler.error_policy {
        return Err(BoundaryError::RenderIdentityMismatch(
            RenderIdentityField::ErrorPolicy,
        ));
    }
    let rendered_palette = work_palette_context(
        &options.resolved_color_map,
        options.render_seed,
        options.catalog_id.as_deref(),
        compiler.host.background(),
    )
    .map_err(|_| BoundaryError::RenderIdentityMismatch(RenderIdentityField::ResolvedPalette))?;
    if !palette_rgb_matches(compiler.host.palette(), &rendered_palette) {
        return Err(BoundaryError::RenderIdentityMismatch(
            RenderIdentityField::ResolvedPalette,
        ));
    }
    let score = delivery
        .score
        .clone()
        .ok_or(BoundaryError::CompilationHasNoScore)?;
    let actual_score_digest =
        canonical_score_digest(&score).map_err(|_| BoundaryError::ScoreSerialization)?;
    if delivery.score_digest.as_deref() != Some(actual_score_digest.as_str()) {
        return Err(BoundaryError::ScoreIdentityMismatch);
    }

    render_with_resources(
        RenderRequest { score, options },
        &compiler.hard_resource_policy,
        compiler.operational_resource_budget,
        clip.resolved()?,
    )
    .map_err(BoundaryError::Render)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HostOptionsError {
    CanvasRegistryIdMismatch,
    CanvasRegistryDigestMismatch,
    CanvasRegistryUnavailable,
    UnknownCanvasFormat,
    EmptyResolvedCatalogId,
    CatalogModeMismatch,
    InvalidResolvedPalette,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RenderIdentityField {
    CanvasFormat,
    CanvasGeometry,
    ResolvedCatalog,
    ResolvedPalette,
    CompositionSeed,
    ErrorPolicy,
}

#[derive(Debug)]
pub enum BoundaryError {
    HostOptions(HostOptionsError),
    InvalidMacroExpansionLimits,
    MetadataSerialization,
    ScoreSerialization,
    InvalidClipTolerance,
    InvalidClipLimit,
    InvalidCompiledDelivery,
    CompilerOptionsMismatch,
    RenderIdentityMismatch(RenderIdentityField),
    CompilationHasNoScore,
    ScoreIdentityMismatch,
    Render(RenderError),
}

impl fmt::Display for BoundaryError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::HostOptions(error) => write!(formatter, "invalid host options: {error:?}"),
            Self::InvalidMacroExpansionLimits => {
                formatter.write_str("invalid macro expansion limits")
            }
            Self::MetadataSerialization => {
                formatter.write_str("compiler metadata serialization failed")
            }
            Self::ScoreSerialization => formatter.write_str("Score serialization failed"),
            Self::InvalidClipTolerance => formatter.write_str("invalid clip tolerance"),
            Self::InvalidClipLimit => formatter.write_str("clip limit cannot fit this core target"),
            Self::InvalidCompiledDelivery => formatter.write_str("invalid compiled delivery"),
            Self::CompilerOptionsMismatch => formatter.write_str("compiler options mismatch"),
            Self::RenderIdentityMismatch(field) => {
                write!(formatter, "render identity mismatch: {field:?}")
            }
            Self::CompilationHasNoScore => formatter.write_str("compilation has no Score"),
            Self::ScoreIdentityMismatch => formatter.write_str("Score identity mismatch"),
            Self::Render(error) => error.fmt(formatter),
        }
    }
}

impl std::error::Error for BoundaryError {}

fn serialize_exact_values<T: Serialize>(values: &[T]) -> Result<Vec<Value>, BoundaryError> {
    values.iter().map(serialize_exact_value).collect()
}

fn serialize_exact_value<T: Serialize>(value: &T) -> Result<Value, BoundaryError> {
    let mut value =
        serde_json::to_value(value).map_err(|_| BoundaryError::MetadataSerialization)?;
    stringify_exact_integer_fields(&mut value, None);
    Ok(value)
}

fn stringify_exact_integer_fields(value: &mut Value, field: Option<&str>) {
    match value {
        Value::Number(number) if field.is_some_and(is_exact_decimal_field) => {
            if let Some(exact) = number.as_u64() {
                *value = exact.to_string().into();
            }
        }
        Value::Array(values) => {
            for value in values {
                stringify_exact_integer_fields(value, field);
            }
        }
        Value::Object(fields) => {
            for (name, value) in fields {
                stringify_exact_integer_fields(value, Some(name));
            }
        }
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {}
    }
}

fn is_exact_decimal_field(field: &str) -> bool {
    field == "ordinal" || field.ends_with("_ordinal") || field == "seed" || field.ends_with("_seed")
}

fn render_canvas_matches_registry(options: &RenderOptions, canvas_format_id: &str) -> bool {
    let width = options.canvas.width;
    let height = options.canvas.height;
    if !width.is_finite() || !height.is_finite() || width <= 0.0 || height <= 0.0 {
        return false;
    }
    let Ok(format) = lookup_canvas_format(canvas_format_id) else {
        return false;
    };
    let width_units = f64::from(format.width_units);
    let height_units = f64::from(format.height_units);
    let cross_axis_error = (width * height_units - height * width_units).abs();
    cross_axis_error <= 0.5 * (width_units + height_units)
}

fn palette_rgb_matches(expected: &ResolvedPaletteDto, actual: &ResolvedPaletteContext) -> bool {
    let color_matches = |expected: ResolvedPaletteColorDto, actual: ResolvedPaletteColor| {
        expected.abstract_color == actual.abstract_color()
            && expected.concrete_rgb == actual.concrete_rgb()
    };
    if !color_matches(expected.background, actual.background())
        || !color_matches(expected.black, actual.black())
        || !color_matches(expected.white, actual.white())
    {
        return false;
    }
    match (&expected.observations, actual.observations()) {
        (Some(expected), Some(actual)) => expected
            .iter()
            .copied()
            .zip(actual.iter().copied())
            .all(|(expected, actual)| color_matches(expected, actual)),
        (None, _) => true,
        (Some(_), None) => false,
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
