//! Runtime-disconnected Score candidates and eligible explicit lowering from verified Stage 1.5.

use inku_score::{
    Canvas, CanvasFormat, Color, Instruction, InstructionMode, LineStyle, Point, Primitive,
    ResolvedPaletteContext, Score, Weight, lookup_canvas_format,
};

use crate::geometry::{
    NORMAL_ELLIPTICAL_ASPECT_RATIO, NORMAL_SHORT_EDGE_RATIO, relative_scale_factor,
};
use crate::{
    CoreModifierValue, ExactDecimal, ExactDecimalError, GEOMETRY_RESOLUTION_POLICY_ID,
    SemanticExplicitGeometry, SemanticHead, SemanticIdentity, SemanticInstruction,
    VerifiedStage15EffectiveView, geometry_resolution_policy_digest,
};

/// Stable identity for the non-serializable Score-field candidate boundary.
pub const SCORE_FIELD_CANDIDATE_SCHEMA_ID: &str = "inku.score-field-candidate.v2";
pub const EXPLICIT_SCORE_LOWERING_SCHEMA_ID: &str = "inku.explicit-score-lowering.v2";

/// A canonical semantic primitive identity that cannot be represented by Score.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ScorePrimitiveMappingError {
    category: String,
    id: String,
}

impl ScorePrimitiveMappingError {
    pub fn category(&self) -> &str {
        &self.category
    }

    pub fn id(&self) -> &str {
        &self.id
    }
}

/// Map only the closed canonical eight-shape identity into the shared Score type.
pub fn score_primitive_from_semantic_identity(
    identity: &SemanticIdentity,
) -> Result<Primitive, ScorePrimitiveMappingError> {
    let primitive = match (identity.category.as_str(), identity.id.as_str()) {
        ("shape", "line") => Primitive::Line,
        ("shape", "circle") => Primitive::Circle,
        ("shape", "ellipse") => Primitive::Ellipse,
        ("shape", "triangle") => Primitive::Triangle,
        ("shape", "square") => Primitive::Square,
        ("shape", "polygon") => Primitive::Polygon,
        ("shape", "arc") => Primitive::Arc,
        ("shape", "cloudform") => Primitive::Cloudform,
        _ => {
            return Err(ScorePrimitiveMappingError {
                category: identity.category.clone(),
                id: identity.id.clone(),
            });
        }
    };
    Ok(primitive)
}

/// Lossless exact-count intent before layout and final limits are selected.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExactCountFieldCandidate {
    Single,
    Repeated(u32),
}

impl ExactCountFieldCandidate {
    pub const fn value(self) -> u32 {
        match self {
            Self::Single => 1,
            Self::Repeated(value) => value,
        }
    }
}

/// Closed gaps that preserve unsupported source meaning without a fallback or clamp.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ScoreFieldGap {
    UnsupportedPrimitiveIdentity { category: String, id: String },
    MacroInvocationHead,
    ExactCountZero { value: u64 },
    ExactCountExceedsScoreRange { value: u64 },
    UnsupportedRelativeScalePrimitive { primitive: Primitive },
    UnsupportedRelativeScaleValue { value: CoreModifierValue },
    MissingExactCount,
    RepeatedCountUnsupported { value: u32 },
    MissingExplicitGeometry,
    MissingNumericPosition,
    MissingColor,
    MissingResolvedPaletteContext,
    MissingTouch,
    MissingContinuity,
    MissingEmptySurface,
    MissingPlaceAction,
    UnsupportedPrimitiveForExplicitGeometry { primitive: Primitive },
    GeometryDimensionMismatch { primitive: Primitive },
    UnsupportedColorIdentity { category: String, id: String },
    UnsupportedTouchIdentity { category: String, id: String },
    UnsupportedContinuityIdentity { category: String, id: String },
    UnsupportedSurfaceIdentity { category: String, id: String },
    UnsupportedActionIdentity { category: String, id: String },
    NamedAndNumericPositionConflict,
    UnsupportedNamedPosition,
    UnsupportedInstructionMeaning,
    UnsupportedDocumentMeaning,
    NonPositiveDimension,
    PositionOutOfRange,
    GeometryExtentOutOfBounds,
    GeometryRepresentationLimit,
}

/// Explicit host-owned context. Canvas identity is resolved through the shared registry.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ScoreLoweringContext {
    canvas_format: CanvasFormat,
    background: Color,
    resolved_palette: Option<ResolvedPaletteContext>,
}

impl ScoreLoweringContext {
    pub fn resolve(
        canvas_format_id: &str,
        background: Color,
    ) -> Result<Self, ScoreLoweringContextError> {
        let canvas_format = lookup_canvas_format(canvas_format_id)
            .map_err(|_| ScoreLoweringContextError::UnknownCanvasFormat)?;
        Ok(Self {
            canvas_format: *canvas_format,
            background,
            resolved_palette: None,
        })
    }

    pub fn resolve_with_palette(
        canvas_format_id: &str,
        background: Color,
        resolved_palette: ResolvedPaletteContext,
    ) -> Result<Self, ScoreLoweringContextError> {
        let mut context = Self::resolve(canvas_format_id, background)?;
        if resolved_palette.background().abstract_color() != background
            || resolved_palette.black().abstract_color() != Color::Black
            || resolved_palette.white().abstract_color() != Color::White
        {
            return Err(ScoreLoweringContextError::ResolvedPaletteRoleMismatch);
        }
        if [
            resolved_palette.background().oklch_lightness(),
            resolved_palette.black().oklch_lightness(),
            resolved_palette.white().oklch_lightness(),
        ]
        .into_iter()
        .any(|lightness| !lightness.is_finite() || !(0.0..=1.0).contains(&lightness))
        {
            return Err(ScoreLoweringContextError::InvalidResolvedPaletteLightness);
        }
        context.resolved_palette = Some(resolved_palette);
        Ok(context)
    }

    pub const fn canvas_format(self) -> CanvasFormat {
        self.canvas_format
    }

    pub const fn background(self) -> Color {
        self.background
    }

    pub const fn resolved_palette(self) -> Option<ResolvedPaletteContext> {
        self.resolved_palette
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ScoreLoweringContextError {
    UnknownCanvasFormat,
    ResolvedPaletteRoleMismatch,
    InvalidResolvedPaletteLightness,
}

/// Candidate evidence plus an all-or-nothing actual Score outcome.
#[derive(Clone, Debug)]
pub struct ExplicitScoreLoweringResult<'a> {
    candidate: ScoreLoweringCandidate<'a>,
    context: ScoreLoweringContext,
    policy_digest: String,
    score: Option<Score>,
    gaps: Vec<ScoreFieldGap>,
}

impl<'a> ExplicitScoreLoweringResult<'a> {
    pub const fn schema_id(&self) -> &'static str {
        EXPLICIT_SCORE_LOWERING_SCHEMA_ID
    }

    pub const fn candidate(&self) -> &ScoreLoweringCandidate<'a> {
        &self.candidate
    }

    pub const fn context(&self) -> ScoreLoweringContext {
        self.context
    }

    pub const fn policy_id(&self) -> &'static str {
        GEOMETRY_RESOLUTION_POLICY_ID
    }

    pub fn policy_digest(&self) -> &str {
        &self.policy_digest
    }

    pub const fn score(&self) -> Option<&Score> {
        self.score.as_ref()
    }

    pub fn gaps(&self) -> &[ScoreFieldGap] {
        &self.gaps
    }
}

/// Score fields owned by one source instruction; all other Score fields remain absent.
#[derive(Clone, Debug, PartialEq)]
pub struct ScoreInstructionFieldCandidate {
    source_instruction_index: usize,
    primitive: Option<Primitive>,
    exact_count: Option<ExactCountFieldCandidate>,
    relative_scale: Option<CoreModifierValue>,
    gaps: Vec<ScoreFieldGap>,
}

impl ScoreInstructionFieldCandidate {
    pub const fn source_instruction_index(&self) -> usize {
        self.source_instruction_index
    }

    pub const fn primitive(&self) -> Option<Primitive> {
        self.primitive
    }

    pub const fn exact_count(&self) -> Option<ExactCountFieldCandidate> {
        self.exact_count
    }

    pub const fn relative_scale(&self) -> Option<CoreModifierValue> {
        self.relative_scale
    }

    pub fn gaps(&self) -> &[ScoreFieldGap] {
        &self.gaps
    }
}

/// Non-serializable candidate that keeps the verified view and pending focus overlay intact.
#[derive(Clone, Debug)]
pub struct ScoreLoweringCandidate<'a> {
    verified_effective_view: VerifiedStage15EffectiveView<'a>,
    instructions: Vec<ScoreInstructionFieldCandidate>,
}

impl<'a> ScoreLoweringCandidate<'a> {
    pub const fn schema_id(&self) -> &'static str {
        SCORE_FIELD_CANDIDATE_SCHEMA_ID
    }

    pub const fn verified_effective_view(&self) -> VerifiedStage15EffectiveView<'a> {
        self.verified_effective_view
    }

    pub fn instructions(&self) -> &[ScoreInstructionFieldCandidate] {
        &self.instructions
    }
}

/// Lower only primitive, exact count, and authoritatively explicit-small fields.
pub fn lower_verified_stage15_view<'a>(
    view: VerifiedStage15EffectiveView<'a>,
) -> ScoreLoweringCandidate<'a> {
    let instructions = view
        .original_semantic_document()
        .instructions
        .iter()
        .enumerate()
        .map(|(instruction_index, instruction)| {
            lower_source_instruction(instruction_index, instruction)
        })
        .collect();
    ScoreLoweringCandidate {
        verified_effective_view: view,
        instructions,
    }
}

/// Lower only a document whose every instruction has the complete explicit Step 10C subset.
pub fn lower_verified_stage15_score<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
) -> ExplicitScoreLoweringResult<'a> {
    let candidate = lower_verified_stage15_view(view);
    let document = candidate
        .verified_effective_view()
        .original_semantic_document();
    let mut gaps = candidate
        .instructions()
        .iter()
        .flat_map(|instruction| instruction.gaps().iter().cloned())
        .collect::<Vec<_>>();

    if document.ground.is_some()
        || !document.coordinated_head_groups.is_empty()
        || !document.group_predicates.is_empty()
    {
        gaps.push(ScoreFieldGap::UnsupportedDocumentMeaning);
    }

    let mut instructions = Vec::with_capacity(document.instructions.len());
    for instruction in &document.instructions {
        match lower_complete_instruction(instruction, context) {
            Ok(score_instruction) => instructions.push(score_instruction),
            Err(mut instruction_gaps) => gaps.append(&mut instruction_gaps),
        }
    }

    let score = gaps.is_empty().then(|| Score {
        version: score_wire_version(),
        canvas: Canvas::Id(context.canvas_format.id.to_owned()),
        background: context.background,
        presence: None,
        instructions,
    });
    ExplicitScoreLoweringResult {
        candidate,
        context,
        policy_digest: geometry_resolution_policy_digest(),
        score,
        gaps,
    }
}

fn lower_complete_instruction(
    instruction: &SemanticInstruction,
    context: ScoreLoweringContext,
) -> Result<Instruction, Vec<ScoreFieldGap>> {
    let mut gaps = Vec::new();
    let primitive = match &instruction.entity.head {
        SemanticHead::Primitive(term) => {
            match score_primitive_from_semantic_identity(&term.identity) {
                Ok(primitive) => primitive,
                Err(error) => {
                    gaps.push(ScoreFieldGap::UnsupportedPrimitiveIdentity {
                        category: error.category,
                        id: error.id,
                    });
                    return Err(gaps);
                }
            }
        }
        SemanticHead::MacroInvocation(_) => return Err(vec![ScoreFieldGap::MacroInvocationHead]),
    };
    let count = match instruction
        .entity
        .quantity
        .as_ref()
        .map(|quantity| quantity.value)
    {
        Some(1) => 1,
        Some(value) if value <= u64::from(u32::MAX) => {
            gaps.push(ScoreFieldGap::RepeatedCountUnsupported {
                value: value as u32,
            });
            0
        }
        Some(value) => {
            gaps.push(ScoreFieldGap::ExactCountExceedsScoreRange { value });
            0
        }
        None => 1,
    };
    debug_assert!(count <= 1, "Step 10E never materializes repeated count");

    let color = match instruction.entity.color.as_ref() {
        Some(_) => map_score_enum::<Color>(instruction.entity.color.as_ref(), "color", &mut gaps),
        None => resolve_omitted_color(context, &mut gaps),
    };
    let weight = match instruction.entity.touch.as_ref() {
        Some(_) => map_score_enum::<Weight>(instruction.entity.touch.as_ref(), "touch", &mut gaps),
        None => Some(Weight::Pen),
    };
    let style = match instruction.entity.continuity.as_ref() {
        Some(_) => map_score_enum::<LineStyle>(
            instruction.entity.continuity.as_ref(),
            "continuity",
            &mut gaps,
        ),
        None => Some(LineStyle::Solid),
    };
    let filled = match instruction.entity.surface.quality.as_ref() {
        Some(term) if term.identity.category == "surface" && term.identity.id == "none" => false,
        Some(term) if term.identity.category == "surface" && term.identity.id == "solid" => true,
        Some(term) => {
            gaps.push(ScoreFieldGap::UnsupportedSurfaceIdentity {
                category: term.identity.category.clone(),
                id: term.identity.id.clone(),
            });
            false
        }
        None => true,
    };
    match instruction.action.as_ref() {
        Some(term) if term.identity.category == "movement" && term.identity.id == "place" => {}
        Some(term) => gaps.push(ScoreFieldGap::UnsupportedActionIdentity {
            category: term.identity.category.clone(),
            id: term.identity.id.clone(),
        }),
        None => gaps.push(ScoreFieldGap::MissingPlaceAction),
    }
    if instruction.position.is_some() && instruction.entity.numeric_position.is_some() {
        gaps.push(ScoreFieldGap::NamedAndNumericPositionConflict);
    } else if instruction.position.is_some() {
        gaps.push(ScoreFieldGap::UnsupportedNamedPosition);
    } else if instruction.entity.numeric_position.is_none() {
        gaps.push(ScoreFieldGap::MissingNumericPosition);
    }
    if instruction.entity.explicit_geometry.is_some() && instruction.entity.relative_scale.is_some()
    {
        gaps.push(ScoreFieldGap::UnsupportedInstructionMeaning);
    } else if instruction.entity.explicit_geometry.is_none()
        && !matches!(
            primitive,
            Primitive::Circle | Primitive::Ellipse | Primitive::Cloudform | Primitive::Square
        )
    {
        if instruction.entity.relative_scale.is_some() {
            gaps.push(ScoreFieldGap::UnsupportedRelativeScalePrimitive { primitive });
        } else {
            gaps.push(ScoreFieldGap::MissingExplicitGeometry);
        }
    }
    if instruction.entity.thinness.is_some()
        || instruction.entity.angle.is_some()
        || instruction.entity.surface.intensity.is_some()
        || instruction.entity.fluctuation.amplitude.is_some()
        || instruction.entity.fluctuation.frequency.is_some()
        || instruction.entity.fluctuation.quality.is_some()
        || instruction.entity.proportion.aspect.is_some()
        || instruction.entity.proportion.width_extent.is_some()
        || instruction.entity.proportion.arc_form.is_some()
        || instruction.relation.is_some()
    {
        gaps.push(ScoreFieldGap::UnsupportedInstructionMeaning);
    }
    if !gaps.is_empty() {
        return Err(gaps);
    }

    let position = instruction
        .entity
        .numeric_position
        .as_ref()
        .expect("checked position");
    let relative_scale = instruction
        .entity
        .relative_scale
        .as_ref()
        .map(|relative_scale| relative_scale.value);
    let geometric = lower_geometry(
        primitive,
        instruction.entity.explicit_geometry.as_ref(),
        relative_scale,
        position,
        context.canvas_format,
    )
    .map_err(|gap| vec![gap])?;

    Ok(Instruction {
        primitive,
        note: None,
        from_: None,
        to: None,
        center: geometric.center,
        radius: geometric.radius,
        sides: None,
        position: geometric.position,
        size: geometric.size,
        angle_start: None,
        angle_end: None,
        rotation: None,
        filled,
        style: style.expect("checked continuity"),
        weight: weight.expect("checked touch"),
        mode_: InstructionMode::Additive,
        carve_depth: None,
        color: color.expect("checked color"),
        color_hint: None,
        variation: None,
        arrangement: None,
        at: None,
        relation: None,
        thinness: None,
        surface: None,
    })
}

fn resolve_omitted_color(
    context: ScoreLoweringContext,
    gaps: &mut Vec<ScoreFieldGap>,
) -> Option<Color> {
    let Some(resolved_palette) = context.resolved_palette else {
        gaps.push(ScoreFieldGap::MissingResolvedPaletteContext);
        return None;
    };
    let background = resolved_palette.background().oklch_lightness();
    let black_distance = (background - resolved_palette.black().oklch_lightness()).abs();
    let white_distance = (background - resolved_palette.white().oklch_lightness()).abs();
    Some(if black_distance >= white_distance {
        Color::Black
    } else {
        Color::White
    })
}

fn map_score_enum<T: serde::de::DeserializeOwned>(
    term: Option<&crate::SemanticTerm>,
    owner: &str,
    gaps: &mut Vec<ScoreFieldGap>,
) -> Option<T> {
    let Some(term) = term else {
        gaps.push(match owner {
            "color" => ScoreFieldGap::MissingColor,
            "touch" => ScoreFieldGap::MissingTouch,
            "continuity" => ScoreFieldGap::MissingContinuity,
            _ => unreachable!(),
        });
        return None;
    };
    match serde_json::from_value(serde_json::Value::String(term.identity.id.clone())) {
        Ok(value) => Some(value),
        Err(_) => {
            gaps.push(match owner {
                "color" => ScoreFieldGap::UnsupportedColorIdentity {
                    category: term.identity.category.clone(),
                    id: term.identity.id.clone(),
                },
                "touch" => ScoreFieldGap::UnsupportedTouchIdentity {
                    category: term.identity.category.clone(),
                    id: term.identity.id.clone(),
                },
                "continuity" => ScoreFieldGap::UnsupportedContinuityIdentity {
                    category: term.identity.category.clone(),
                    id: term.identity.id.clone(),
                },
                _ => unreachable!(),
            });
            None
        }
    }
}

#[derive(Clone, Copy)]
struct LoweredGeometry {
    center: Option<Point>,
    radius: Option<f64>,
    position: Option<Point>,
    size: Option<Point>,
}

fn lower_geometry(
    primitive: Primitive,
    geometry: Option<&SemanticExplicitGeometry>,
    relative_scale: Option<CoreModifierValue>,
    position: &crate::SemanticNumericPosition,
    canvas: CanvasFormat,
) -> Result<LoweredGeometry, ScoreFieldGap> {
    let x = Rational::from_decimal(position.x.decimal.value)?;
    let y = Rational::from_decimal(position.y.decimal.value)?;
    if !x.in_unit_interval() || !y.in_unit_interval() {
        return Err(ScoreFieldGap::PositionOutOfRange);
    }
    let center = Point::new(x.to_f64()?, y.to_f64()?);
    let (width_units, height_units) = canvas.integer_ratio();
    let short_units = width_units.min(height_units);

    let Some(geometry) = geometry else {
        return lower_normal_geometry(
            primitive,
            relative_scale.unwrap_or(CoreModifierValue::Normal),
            x,
            y,
            center,
            width_units,
            height_units,
            short_units,
        );
    };

    match (primitive, geometry) {
        (Primitive::Circle, SemanticExplicitGeometry::Radius(value))
        | (Primitive::Circle, SemanticExplicitGeometry::Diameter(value)) => {
            let mut radius = positive(value.decimal.value)?;
            if matches!(geometry, SemanticExplicitGeometry::Diameter(_)) {
                radius = radius.div_i128(2)?;
            }
            ensure_centered_extent(x, y, radius, radius, width_units, height_units, short_units)?;
            Ok(LoweredGeometry {
                center: Some(center),
                radius: Some(radius.to_f64()?),
                position: None,
                size: None,
            })
        }
        (
            Primitive::Ellipse | Primitive::Cloudform,
            SemanticExplicitGeometry::WidthHeight { width, height },
        ) => {
            let width = positive(width.decimal.value)?;
            let height = positive(height.decimal.value)?;
            ensure_centered_extent(
                x,
                y,
                width.div_i128(2)?,
                height.div_i128(2)?,
                width_units,
                height_units,
                short_units,
            )?;
            Ok(LoweredGeometry {
                center: Some(center),
                radius: None,
                position: None,
                size: Some(Point::new(width.to_f64()?, height.to_f64()?)),
            })
        }
        (Primitive::Square, SemanticExplicitGeometry::Side(value)) => {
            let side = positive(value.decimal.value)?;
            let half = side.div_i128(2)?;
            let extent_x = half.mul_ratio(i128::from(short_units), i128::from(width_units))?;
            let extent_y = half.mul_ratio(i128::from(short_units), i128::from(height_units))?;
            let top_left_x = x.sub(extent_x)?;
            let top_left_y = y.sub(extent_y)?;
            let full_x = extent_x.mul_i128(2)?;
            let full_y = extent_y.mul_i128(2)?;
            if !top_left_x.in_unit_interval()
                || !top_left_y.in_unit_interval()
                || !top_left_x.add(full_x)?.in_unit_interval()
                || !top_left_y.add(full_y)?.in_unit_interval()
            {
                return Err(ScoreFieldGap::GeometryExtentOutOfBounds);
            }
            Ok(LoweredGeometry {
                center: None,
                radius: None,
                position: Some(Point::new(top_left_x.to_f64()?, top_left_y.to_f64()?)),
                size: Some(Point::new(side.to_f64()?, side.to_f64()?)),
            })
        }
        (Primitive::Circle | Primitive::Ellipse | Primitive::Cloudform | Primitive::Square, _) => {
            Err(ScoreFieldGap::GeometryDimensionMismatch { primitive })
        }
        _ => Err(ScoreFieldGap::UnsupportedPrimitiveForExplicitGeometry { primitive }),
    }
}

#[allow(clippy::too_many_arguments)]
fn lower_normal_geometry(
    primitive: Primitive,
    relative_scale: CoreModifierValue,
    x: Rational,
    y: Rational,
    center: Point,
    width_units: u32,
    height_units: u32,
    short_units: u32,
) -> Result<LoweredGeometry, ScoreFieldGap> {
    let (factor_numerator, factor_denominator) = relative_scale_factor(relative_scale).ok_or(
        ScoreFieldGap::UnsupportedRelativeScaleValue {
            value: relative_scale,
        },
    )?;
    let normal = Rational::from_ratio(NORMAL_SHORT_EDGE_RATIO.0, NORMAL_SHORT_EDGE_RATIO.1)?;
    let width = normal.mul_ratio(factor_numerator, factor_denominator)?;
    match primitive {
        Primitive::Circle => {
            let radius = width.div_i128(2)?;
            ensure_centered_extent(x, y, radius, radius, width_units, height_units, short_units)?;
            Ok(LoweredGeometry {
                center: Some(center),
                radius: Some(radius.to_f64()?),
                position: None,
                size: None,
            })
        }
        Primitive::Ellipse | Primitive::Cloudform => {
            let height = width.mul_ratio(
                NORMAL_ELLIPTICAL_ASPECT_RATIO.0,
                NORMAL_ELLIPTICAL_ASPECT_RATIO.1,
            )?;
            ensure_centered_extent(
                x,
                y,
                width.div_i128(2)?,
                height.div_i128(2)?,
                width_units,
                height_units,
                short_units,
            )?;
            Ok(LoweredGeometry {
                center: Some(center),
                radius: None,
                position: None,
                size: Some(Point::new(width.to_f64()?, height.to_f64()?)),
            })
        }
        Primitive::Square => {
            let half = width.div_i128(2)?;
            let extent_x = half.mul_ratio(i128::from(short_units), i128::from(width_units))?;
            let extent_y = half.mul_ratio(i128::from(short_units), i128::from(height_units))?;
            let top_left_x = x.sub(extent_x)?;
            let top_left_y = y.sub(extent_y)?;
            if !top_left_x.in_unit_interval()
                || !top_left_y.in_unit_interval()
                || !top_left_x.add(extent_x.mul_i128(2)?)?.in_unit_interval()
                || !top_left_y.add(extent_y.mul_i128(2)?)?.in_unit_interval()
            {
                return Err(ScoreFieldGap::GeometryExtentOutOfBounds);
            }
            Ok(LoweredGeometry {
                center: None,
                radius: None,
                position: Some(Point::new(top_left_x.to_f64()?, top_left_y.to_f64()?)),
                size: Some(Point::new(width.to_f64()?, width.to_f64()?)),
            })
        }
        _ => Err(ScoreFieldGap::UnsupportedRelativeScalePrimitive { primitive }),
    }
}

fn positive(value: ExactDecimal) -> Result<Rational, ScoreFieldGap> {
    if !value.is_positive() {
        return Err(ScoreFieldGap::NonPositiveDimension);
    }
    Rational::from_decimal(value)
}

fn ensure_centered_extent(
    x: Rational,
    y: Rational,
    half_width: Rational,
    half_height: Rational,
    width_units: u32,
    height_units: u32,
    short_units: u32,
) -> Result<(), ScoreFieldGap> {
    let x_extent = half_width.mul_ratio(i128::from(short_units), i128::from(width_units))?;
    let y_extent = half_height.mul_ratio(i128::from(short_units), i128::from(height_units))?;
    if !x.sub(x_extent)?.in_unit_interval()
        || !x.add(x_extent)?.in_unit_interval()
        || !y.sub(y_extent)?.in_unit_interval()
        || !y.add(y_extent)?.in_unit_interval()
    {
        return Err(ScoreFieldGap::GeometryExtentOutOfBounds);
    }
    Ok(())
}

#[derive(Clone, Copy)]
struct Rational {
    numerator: i128,
    denominator: i128,
}

impl Rational {
    fn from_ratio(numerator: i128, denominator: i128) -> Result<Self, ScoreFieldGap> {
        if denominator <= 0 {
            return Err(ScoreFieldGap::GeometryRepresentationLimit);
        }
        Ok(Self {
            numerator,
            denominator,
        })
    }

    fn from_decimal(value: ExactDecimal) -> Result<Self, ScoreFieldGap> {
        Ok(Self {
            numerator: value.coefficient(),
            denominator: value.denominator().map_err(map_decimal_error)?,
        })
    }

    const fn in_unit_interval(self) -> bool {
        0 <= self.numerator && self.numerator <= self.denominator
    }

    fn mul_ratio(self, numerator: i128, denominator: i128) -> Result<Self, ScoreFieldGap> {
        Ok(Self {
            numerator: self
                .numerator
                .checked_mul(numerator)
                .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
            denominator: self
                .denominator
                .checked_mul(denominator)
                .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
        })
    }

    fn mul_i128(self, value: i128) -> Result<Self, ScoreFieldGap> {
        self.mul_ratio(value, 1)
    }

    fn div_i128(self, value: i128) -> Result<Self, ScoreFieldGap> {
        self.mul_ratio(1, value)
    }

    fn add(self, other: Self) -> Result<Self, ScoreFieldGap> {
        Ok(Self {
            numerator: self
                .numerator
                .checked_mul(other.denominator)
                .and_then(|left| {
                    other
                        .numerator
                        .checked_mul(self.denominator)
                        .and_then(|right| left.checked_add(right))
                })
                .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
            denominator: self
                .denominator
                .checked_mul(other.denominator)
                .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
        })
    }

    fn sub(self, other: Self) -> Result<Self, ScoreFieldGap> {
        Ok(Self {
            numerator: self
                .numerator
                .checked_mul(other.denominator)
                .and_then(|left| {
                    other
                        .numerator
                        .checked_mul(self.denominator)
                        .and_then(|right| left.checked_sub(right))
                })
                .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
            denominator: self
                .denominator
                .checked_mul(other.denominator)
                .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
        })
    }

    fn to_f64(self) -> Result<f64, ScoreFieldGap> {
        let value = self.numerator as f64 / self.denominator as f64;
        value
            .is_finite()
            .then_some(value)
            .ok_or(ScoreFieldGap::GeometryRepresentationLimit)
    }
}

fn map_decimal_error(_: ExactDecimalError) -> ScoreFieldGap {
    ScoreFieldGap::GeometryRepresentationLimit
}

fn score_wire_version() -> String {
    serde_json::from_value::<Score>(serde_json::json!({
        "canvas": "square",
        "background": "white",
        "instructions": []
    }))
    .expect("shared Score defaults supply only technical wire metadata")
    .version
}

fn lower_source_instruction(
    source_instruction_index: usize,
    instruction: &SemanticInstruction,
) -> ScoreInstructionFieldCandidate {
    let mut gaps = Vec::new();
    let primitive = match &instruction.entity.head {
        SemanticHead::Primitive(term) => {
            match score_primitive_from_semantic_identity(&term.identity) {
                Ok(primitive) => Some(primitive),
                Err(error) => {
                    gaps.push(ScoreFieldGap::UnsupportedPrimitiveIdentity {
                        category: error.category,
                        id: error.id,
                    });
                    None
                }
            }
        }
        SemanticHead::MacroInvocation(_) => {
            gaps.push(ScoreFieldGap::MacroInvocationHead);
            return ScoreInstructionFieldCandidate {
                source_instruction_index,
                primitive: None,
                exact_count: None,
                relative_scale: None,
                gaps,
            };
        }
    };

    let exact_count =
        instruction
            .entity
            .quantity
            .as_ref()
            .and_then(|quantity| match quantity.value {
                0 => {
                    gaps.push(ScoreFieldGap::ExactCountZero { value: 0 });
                    None
                }
                1 => Some(ExactCountFieldCandidate::Single),
                value if value <= u64::from(u32::MAX) => {
                    Some(ExactCountFieldCandidate::Repeated(value as u32))
                }
                value => {
                    gaps.push(ScoreFieldGap::ExactCountExceedsScoreRange { value });
                    None
                }
            });

    let relative_scale = instruction
        .entity
        .relative_scale
        .as_ref()
        .and_then(|scale| {
            if relative_scale_factor(scale.value).is_none() {
                gaps.push(ScoreFieldGap::UnsupportedRelativeScaleValue { value: scale.value });
                return None;
            }
            match primitive {
                Some(
                    Primitive::Circle
                    | Primitive::Ellipse
                    | Primitive::Cloudform
                    | Primitive::Square,
                ) => Some(scale.value),
                Some(primitive) => {
                    gaps.push(ScoreFieldGap::UnsupportedRelativeScalePrimitive { primitive });
                    None
                }
                None => None,
            }
        });

    ScoreInstructionFieldCandidate {
        source_instruction_index,
        primitive,
        exact_count,
        relative_scale,
        gaps,
    }
}
