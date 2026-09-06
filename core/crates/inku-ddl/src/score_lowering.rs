//! Runtime-disconnected Score candidates and eligible explicit lowering from verified Stage 1.5.

use std::collections::BTreeMap;

use inku_score::{
    AtRegion, Canvas, CanvasFormat, Color, Instruction, InstructionMode, LineStyle, Point,
    Primitive, ResolvedPaletteContext, Score, Weight, lookup_canvas_format,
};

use crate::geometry::{
    NORMAL_ELLIPTICAL_ASPECT_RATIO, NORMAL_SHORT_EDGE_RATIO, focus_region_bounds,
    relative_scale_factor,
};
use crate::{
    CoreModifierValue, ExactDecimal, ExactDecimalError, ExpandedMacroInvocation, ExpandedMacroNode,
    ExpandedMacroValue, ExpansionPathSegment, FocusRegion, GEOMETRY_RESOLUTION_POLICY_ID,
    GeneratedNodeProvenance, GeneratedTargetId, SemanticExplicitGeometry, SemanticHead,
    SemanticIdentity, SemanticInstruction, SemanticMacroInvocationHead, SemanticNumericPosition,
    Stage15TargetPath, Stage15TargetProvenance, VerifiedStage15EffectiveView,
    geometry_resolution_policy_digest,
};

/// Stable identity for the non-serializable Score-field candidate boundary.
pub const SCORE_FIELD_CANDIDATE_SCHEMA_ID: &str = "inku.score-field-candidate.v2";
pub const EXPLICIT_SCORE_LOWERING_SCHEMA_ID: &str = "inku.explicit-score-lowering.v3";

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
    score_primitive_from_identity(identity.into())
}

fn score_primitive_from_identity(
    identity: SemanticInputIdentity<'_>,
) -> Result<Primitive, ScorePrimitiveMappingError> {
    let primitive = match (identity.category, identity.id) {
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
                category: identity.category.to_owned(),
                id: identity.id.to_owned(),
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
    UnsupportedPrimitiveIdentity {
        category: String,
        id: String,
    },
    MacroInvocationHead,
    ExactCountZero {
        value: u64,
    },
    ExactCountExceedsScoreRange {
        value: u64,
    },
    UnsupportedRelativeScalePrimitive {
        primitive: Primitive,
    },
    UnsupportedRelativeScaleValue {
        value: CoreModifierValue,
    },
    MissingExactCount,
    RepeatedCountUnsupported {
        value: u32,
    },
    MissingExplicitGeometry,
    MissingNumericPosition,
    MissingColor,
    MissingResolvedPaletteContext,
    MissingTouch,
    MissingContinuity,
    MissingEmptySurface,
    MissingPlaceAction,
    UnsupportedPrimitiveForExplicitGeometry {
        primitive: Primitive,
    },
    GeometryDimensionMismatch {
        primitive: Primitive,
    },
    UnsupportedColorIdentity {
        category: String,
        id: String,
    },
    UnsupportedTouchIdentity {
        category: String,
        id: String,
    },
    UnsupportedContinuityIdentity {
        category: String,
        id: String,
    },
    UnsupportedSurfaceIdentity {
        category: String,
        id: String,
    },
    UnsupportedActionIdentity {
        category: String,
        id: String,
    },
    NamedAndNumericPositionConflict,
    UnsupportedNamedPosition,
    UnsupportedInstructionMeaning,
    UnsupportedDocumentMeaning,
    UnboundMacroCallerMeaning,
    MissingMacroExpansionOwner {
        invocation_ordinal: u64,
    },
    DuplicateMacroExpansionOwner {
        invocation_ordinal: u64,
    },
    UnsupportedMacroStructure,
    MissingMacroEmitField {
        key: String,
    },
    UnknownMacroEmitField {
        key: String,
    },
    MacroEmitFieldTypeMismatch {
        key: String,
    },
    MacroEmitIntegerOutOfRange {
        key: String,
        value: i64,
    },
    MacroEmitFieldCategoryMismatch {
        key: String,
        expected: String,
        actual: String,
    },
    UnsupportedMacroEmitIdentity {
        key: String,
        category: String,
        id: String,
    },
    MissingMacroEmitFocusTarget {
        invocation_ordinal: u64,
        expansion_path: Vec<ExpansionPathSegment>,
        generated_ordinal: u64,
    },
    DuplicateMacroEmitFocusTarget {
        invocation_ordinal: u64,
        expansion_path: Vec<ExpansionPathSegment>,
        generated_ordinal: u64,
    },
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

fn direct_instruction_focus(
    view: VerifiedStage15EffectiveView<'_>,
    instruction_index: usize,
) -> Option<FocusRegion> {
    view.pending_focus_targets()
        .iter()
        .find_map(|target| match &target.path {
            Stage15TargetPath::Instruction {
                instruction_index: target_index,
            } if *target_index == instruction_index => Some(target.effective_focus),
            Stage15TargetPath::Instruction { .. }
            | Stage15TargetPath::GroupPredicate { .. }
            | Stage15TargetPath::MacroEmit { .. } => None,
        })
}

fn project_source_instruction<'a>(
    instruction: &'a SemanticInstruction,
    effective_focus: Option<FocusRegion>,
) -> Option<ScoreLoweringInput<'a>> {
    let SemanticHead::Primitive(term) = &instruction.entity.head else {
        return None;
    };
    Some(ScoreLoweringInput {
        primitive: (&term.identity).into(),
        count: instruction
            .entity
            .quantity
            .as_ref()
            .map(|value| value.value),
        color: instruction
            .entity
            .color
            .as_ref()
            .map(|term| (&term.identity).into()),
        touch: instruction
            .entity
            .touch
            .as_ref()
            .map(|term| (&term.identity).into()),
        continuity: instruction
            .entity
            .continuity
            .as_ref()
            .map(|term| (&term.identity).into()),
        surface: instruction
            .entity
            .surface
            .quality
            .as_ref()
            .map(|term| (&term.identity).into()),
        action: instruction
            .action
            .as_ref()
            .map(|term| (&term.identity).into()),
        numeric_position: instruction.entity.numeric_position.as_ref(),
        has_named_position: instruction.position.is_some(),
        effective_focus,
        explicit_geometry: instruction.entity.explicit_geometry.as_ref(),
        relative_scale: instruction
            .entity
            .relative_scale
            .as_ref()
            .map(|scale| scale.value),
        has_unsupported_meaning: instruction.entity.thinness.is_some()
            || instruction.entity.angle.is_some()
            || instruction.entity.surface.intensity.is_some()
            || instruction.entity.fluctuation.amplitude.is_some()
            || instruction.entity.fluctuation.frequency.is_some()
            || instruction.entity.fluctuation.quality.is_some()
            || instruction.entity.proportion.aspect.is_some()
            || instruction.entity.proportion.width_extent.is_some()
            || instruction.entity.proportion.arc_form.is_some()
            || instruction.relation.is_some(),
    })
}

#[allow(clippy::too_many_arguments)]
fn lower_macro_instruction(
    view: VerifiedStage15EffectiveView<'_>,
    source_instruction_index: usize,
    instruction: &SemanticInstruction,
    head: &SemanticMacroInvocationHead,
    context: ScoreLoweringContext,
    instructions: &mut Vec<Instruction>,
    instruction_origins: &mut Vec<ScoreInstructionOrigin>,
    gaps: &mut Vec<ScoreFieldGap>,
) {
    append_macro_caller_gaps(instruction, gaps);
    let expansion = match exact_macro_expansion(view, head) {
        Ok(expansion) => expansion,
        Err(gap) => {
            gaps.push(gap);
            return;
        }
    };

    for node in &expansion.nodes {
        let ExpandedMacroNode::Emit {
            binding,
            fields,
            provenance,
        } = node
        else {
            gaps.push(ScoreFieldGap::UnsupportedMacroStructure);
            continue;
        };
        let mut input = match project_macro_emit(fields) {
            Ok(input) => input,
            Err(mut emit_gaps) => {
                gaps.append(&mut emit_gaps);
                continue;
            }
        };
        input.effective_focus = match exact_macro_emit_focus(view, provenance) {
            Ok(focus) => Some(focus),
            Err(gap) => {
                gaps.push(gap);
                continue;
            }
        };
        match lower_complete_instruction(input, context) {
            Ok(score_instruction) => {
                instructions.push(score_instruction);
                instruction_origins.push(ScoreInstructionOrigin::MacroEmit {
                    source_instruction_index,
                    binding: binding.clone(),
                    provenance: provenance.clone(),
                });
            }
            Err(mut emit_gaps) => gaps.append(&mut emit_gaps),
        }
    }
}

fn exact_macro_expansion<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    head: &SemanticMacroInvocationHead,
) -> Result<&'a ExpandedMacroInvocation, ScoreFieldGap> {
    let mut matches = view
        .original_expanded_invocations()
        .iter()
        .filter(|invocation| {
            invocation.provenance.invocation_ordinal == head.provenance.ordinal
                && invocation.provenance.source_span == head.provenance.source.span
                && invocation.provenance.definition_qualified_name == head.qualified_name
                && invocation.provenance.definition_version == head.definition_version
                && invocation.provenance.definition_full_digest == head.definition_digest
        });
    let Some(expansion) = matches.next() else {
        return Err(ScoreFieldGap::MissingMacroExpansionOwner {
            invocation_ordinal: head.provenance.ordinal,
        });
    };
    if matches.next().is_some() {
        return Err(ScoreFieldGap::DuplicateMacroExpansionOwner {
            invocation_ordinal: head.provenance.ordinal,
        });
    }
    Ok(expansion)
}

fn append_macro_caller_gaps(instruction: &SemanticInstruction, gaps: &mut Vec<ScoreFieldGap>) {
    match instruction
        .entity
        .quantity
        .as_ref()
        .map(|value| value.value)
    {
        None | Some(1) => {}
        Some(0) => gaps.push(ScoreFieldGap::ExactCountZero { value: 0 }),
        Some(value) if value <= u64::from(u32::MAX) => {
            gaps.push(ScoreFieldGap::RepeatedCountUnsupported {
                value: value as u32,
            });
        }
        Some(value) => gaps.push(ScoreFieldGap::ExactCountExceedsScoreRange { value }),
    }
    if instruction.entity.color.is_some()
        || instruction.entity.thinness.is_some()
        || instruction.entity.relative_scale.is_some()
        || instruction.entity.explicit_geometry.is_some()
        || instruction.entity.numeric_position.is_some()
        || instruction.entity.touch.is_some()
        || instruction.entity.continuity.is_some()
        || instruction.entity.angle.is_some()
        || instruction.entity.surface.quality.is_some()
        || instruction.entity.surface.intensity.is_some()
        || instruction.entity.fluctuation.amplitude.is_some()
        || instruction.entity.fluctuation.frequency.is_some()
        || instruction.entity.fluctuation.quality.is_some()
        || instruction.entity.proportion.aspect.is_some()
        || instruction.entity.proportion.width_extent.is_some()
        || instruction.entity.proportion.arc_form.is_some()
        || instruction.action.is_some()
        || instruction.position.is_some()
        || instruction.relation.is_some()
    {
        gaps.push(ScoreFieldGap::UnboundMacroCallerMeaning);
    }
}

fn exact_macro_emit_focus(
    view: VerifiedStage15EffectiveView<'_>,
    provenance: &GeneratedNodeProvenance,
) -> Result<FocusRegion, ScoreFieldGap> {
    let mut matches = view.pending_focus_targets().iter().filter(|target| {
        matches!(
            &target.path,
            Stage15TargetPath::MacroEmit {
                invocation_ordinal,
                expansion_path,
                generated_ordinal,
                field,
            } if *invocation_ordinal == provenance.invocation.invocation_ordinal
                && expansion_path == &provenance.expansion_path
                && *generated_ordinal == provenance.generated_ordinal
                && field == "place"
                && matches!(
                    &target.provenance,
                    Stage15TargetProvenance::Generated(target_provenance)
                        if target_provenance == provenance
                )
        )
    });
    let Some(target) = matches.next() else {
        return Err(ScoreFieldGap::MissingMacroEmitFocusTarget {
            invocation_ordinal: provenance.invocation.invocation_ordinal,
            expansion_path: provenance.expansion_path.clone(),
            generated_ordinal: provenance.generated_ordinal,
        });
    };
    if matches.next().is_some() {
        return Err(ScoreFieldGap::DuplicateMacroEmitFocusTarget {
            invocation_ordinal: provenance.invocation.invocation_ordinal,
            expansion_path: provenance.expansion_path.clone(),
            generated_ordinal: provenance.generated_ordinal,
        });
    }
    Ok(target.effective_focus)
}

const MACRO_SCORE_FIELD_KEYS: [&str; 8] = [
    "shape",
    "movement",
    "place",
    "color",
    "touch",
    "continuity",
    "surface",
    "count",
];

fn project_macro_emit<'a>(
    fields: &'a BTreeMap<String, ExpandedMacroValue>,
) -> Result<ScoreLoweringInput<'a>, Vec<ScoreFieldGap>> {
    let mut gaps = fields
        .keys()
        .filter(|key| !MACRO_SCORE_FIELD_KEYS.contains(&key.as_str()))
        .map(|key| ScoreFieldGap::UnknownMacroEmitField { key: key.clone() })
        .collect::<Vec<_>>();
    let primitive = macro_semantic_field(fields, "shape", "shape", true, &mut gaps);
    let action = macro_semantic_field(fields, "movement", "movement", true, &mut gaps);
    let place = macro_semantic_field(fields, "place", "place", true, &mut gaps);
    let color = macro_semantic_field(fields, "color", "color", false, &mut gaps);
    let touch = macro_semantic_field(fields, "touch", "touch", false, &mut gaps);
    let continuity = macro_semantic_field(fields, "continuity", "continuity", false, &mut gaps);
    let surface = macro_semantic_field(fields, "surface", "surface", false, &mut gaps);
    let count = match fields.get("count") {
        None => None,
        Some(ExpandedMacroValue::Integer(value)) if *value >= 0 => Some(*value as u64),
        Some(ExpandedMacroValue::Integer(value)) => {
            gaps.push(ScoreFieldGap::MacroEmitIntegerOutOfRange {
                key: "count".to_owned(),
                value: *value,
            });
            None
        }
        Some(_) => {
            gaps.push(ScoreFieldGap::MacroEmitFieldTypeMismatch {
                key: "count".to_owned(),
            });
            None
        }
    };

    if let Some(identity) = primitive
        && !matches!(identity.id, "circle" | "ellipse" | "cloudform" | "square")
    {
        gaps.push(ScoreFieldGap::UnsupportedMacroEmitIdentity {
            key: "shape".to_owned(),
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        });
    }
    if let Some(identity) = action
        && identity.id != "place"
    {
        gaps.push(ScoreFieldGap::UnsupportedMacroEmitIdentity {
            key: "movement".to_owned(),
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        });
    }
    if let Some(identity) = place
        && identity.id != "center"
    {
        gaps.push(ScoreFieldGap::UnsupportedMacroEmitIdentity {
            key: "place".to_owned(),
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        });
    }
    if !gaps.is_empty() {
        return Err(gaps);
    }

    Ok(ScoreLoweringInput {
        primitive: primitive.expect("required macro shape field checked"),
        count,
        color,
        touch,
        continuity,
        surface,
        action,
        numeric_position: None,
        has_named_position: place.is_some(),
        effective_focus: None,
        explicit_geometry: None,
        relative_scale: None,
        has_unsupported_meaning: false,
    })
}

fn macro_semantic_field<'a>(
    fields: &'a BTreeMap<String, ExpandedMacroValue>,
    key: &str,
    expected_category: &str,
    required: bool,
    gaps: &mut Vec<ScoreFieldGap>,
) -> Option<SemanticInputIdentity<'a>> {
    let Some(value) = fields.get(key) else {
        if required {
            gaps.push(ScoreFieldGap::MissingMacroEmitField {
                key: key.to_owned(),
            });
        }
        return None;
    };
    let ExpandedMacroValue::SemanticRef { category, id } = value else {
        gaps.push(ScoreFieldGap::MacroEmitFieldTypeMismatch {
            key: key.to_owned(),
        });
        return None;
    };
    if category != expected_category {
        gaps.push(ScoreFieldGap::MacroEmitFieldCategoryMismatch {
            key: key.to_owned(),
            expected: expected_category.to_owned(),
            actual: category.clone(),
        });
        return None;
    }
    Some(SemanticInputIdentity { category, id })
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
    instruction_origins: Vec<ScoreInstructionOrigin>,
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

    pub fn instruction_origins(&self) -> &[ScoreInstructionOrigin] {
        &self.instruction_origins
    }

    pub fn gaps(&self) -> &[ScoreFieldGap] {
        &self.gaps
    }
}

/// Exact source or generated owner for one instruction in a successful Score.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ScoreInstructionOrigin {
    SourceInstruction {
        instruction_index: usize,
    },
    MacroEmit {
        source_instruction_index: usize,
        binding: Option<GeneratedTargetId>,
        provenance: GeneratedNodeProvenance,
    },
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

/// Lower only a document whose every instruction has a complete supported finite input.
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
        .flat_map(|instruction| instruction.gaps().iter())
        .filter(|gap| !matches!(gap, ScoreFieldGap::MacroInvocationHead))
        .cloned()
        .collect::<Vec<_>>();

    if document.ground.is_some()
        || !document.coordinated_head_groups.is_empty()
        || !document.group_predicates.is_empty()
    {
        gaps.push(ScoreFieldGap::UnsupportedDocumentMeaning);
    }

    let mut instructions = Vec::new();
    let mut instruction_origins = Vec::new();
    for (instruction_index, instruction) in document.instructions.iter().enumerate() {
        match &instruction.entity.head {
            SemanticHead::Primitive(_) => {
                let effective_focus = direct_instruction_focus(
                    candidate.verified_effective_view(),
                    instruction_index,
                );
                let input = project_source_instruction(instruction, effective_focus)
                    .expect("source projection is called only for primitive heads");
                match lower_complete_instruction(input, context) {
                    Ok(score_instruction) => {
                        instructions.push(score_instruction);
                        instruction_origins
                            .push(ScoreInstructionOrigin::SourceInstruction { instruction_index });
                    }
                    Err(mut instruction_gaps) => gaps.append(&mut instruction_gaps),
                }
            }
            SemanticHead::MacroInvocation(head) => {
                lower_macro_instruction(
                    candidate.verified_effective_view(),
                    instruction_index,
                    instruction,
                    head,
                    context,
                    &mut instructions,
                    &mut instruction_origins,
                    &mut gaps,
                );
            }
        }
    }

    let score = gaps.is_empty().then(|| Score {
        version: score_wire_version(),
        canvas: Canvas::Id(context.canvas_format.id.to_owned()),
        background: context.background,
        presence: None,
        instructions,
    });
    if score.is_none() {
        instruction_origins.clear();
    }
    ExplicitScoreLoweringResult {
        candidate,
        context,
        policy_digest: geometry_resolution_policy_digest(),
        score,
        instruction_origins,
        gaps,
    }
}

#[derive(Clone, Copy, Debug)]
struct SemanticInputIdentity<'a> {
    category: &'a str,
    id: &'a str,
}

impl<'a> From<&'a SemanticIdentity> for SemanticInputIdentity<'a> {
    fn from(identity: &'a SemanticIdentity) -> Self {
        Self {
            category: &identity.category,
            id: &identity.id,
        }
    }
}

#[derive(Clone, Copy, Debug)]
struct ScoreLoweringInput<'a> {
    primitive: SemanticInputIdentity<'a>,
    count: Option<u64>,
    color: Option<SemanticInputIdentity<'a>>,
    touch: Option<SemanticInputIdentity<'a>>,
    continuity: Option<SemanticInputIdentity<'a>>,
    surface: Option<SemanticInputIdentity<'a>>,
    action: Option<SemanticInputIdentity<'a>>,
    numeric_position: Option<&'a SemanticNumericPosition>,
    has_named_position: bool,
    effective_focus: Option<FocusRegion>,
    explicit_geometry: Option<&'a SemanticExplicitGeometry>,
    relative_scale: Option<CoreModifierValue>,
    has_unsupported_meaning: bool,
}

fn lower_complete_instruction(
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
) -> Result<Instruction, Vec<ScoreFieldGap>> {
    let mut gaps = Vec::new();
    let primitive = match score_primitive_from_identity(input.primitive) {
        Ok(primitive) => primitive,
        Err(error) => {
            gaps.push(ScoreFieldGap::UnsupportedPrimitiveIdentity {
                category: error.category,
                id: error.id,
            });
            return Err(gaps);
        }
    };
    let count = match input.count {
        Some(0) => {
            gaps.push(ScoreFieldGap::ExactCountZero { value: 0 });
            0
        }
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
    debug_assert!(
        count <= 1,
        "finite lowering never materializes repeated count"
    );

    let color = match input.color {
        Some(_) => map_score_enum::<Color>(input.color, "color", &mut gaps),
        None => resolve_omitted_color(context, &mut gaps),
    };
    let weight = match input.touch {
        Some(_) => map_score_enum::<Weight>(input.touch, "touch", &mut gaps),
        None => Some(Weight::Pen),
    };
    let style = match input.continuity {
        Some(_) => map_score_enum::<LineStyle>(input.continuity, "continuity", &mut gaps),
        None => Some(LineStyle::Solid),
    };
    let filled = match input.surface {
        Some(identity) if identity.category == "surface" && identity.id == "none" => false,
        Some(identity) if identity.category == "surface" && identity.id == "solid" => true,
        Some(identity) => {
            gaps.push(ScoreFieldGap::UnsupportedSurfaceIdentity {
                category: identity.category.to_owned(),
                id: identity.id.to_owned(),
            });
            false
        }
        None => true,
    };
    match input.action {
        Some(identity) if identity.category == "movement" && identity.id == "place" => {}
        Some(identity) => gaps.push(ScoreFieldGap::UnsupportedActionIdentity {
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        }),
        None => gaps.push(ScoreFieldGap::MissingPlaceAction),
    }
    let named_focus = if input.has_named_position && input.numeric_position.is_some() {
        gaps.push(ScoreFieldGap::NamedAndNumericPositionConflict);
        None
    } else if input.has_named_position {
        if let Some(focus) = input.effective_focus {
            Some(focus)
        } else {
            gaps.push(ScoreFieldGap::UnsupportedNamedPosition);
            None
        }
    } else if input.numeric_position.is_none() {
        gaps.push(ScoreFieldGap::MissingNumericPosition);
        None
    } else {
        None
    };
    if input.explicit_geometry.is_some() && input.relative_scale.is_some() {
        gaps.push(ScoreFieldGap::UnsupportedInstructionMeaning);
    } else if input.explicit_geometry.is_none()
        && !matches!(
            primitive,
            Primitive::Circle | Primitive::Ellipse | Primitive::Cloudform | Primitive::Square
        )
    {
        if input.relative_scale.is_some() {
            gaps.push(ScoreFieldGap::UnsupportedRelativeScalePrimitive { primitive });
        } else {
            gaps.push(ScoreFieldGap::MissingExplicitGeometry);
        }
    }
    if input.has_unsupported_meaning {
        gaps.push(ScoreFieldGap::UnsupportedInstructionMeaning);
    }
    if !gaps.is_empty() {
        return Err(gaps);
    }

    let placement = match (input.numeric_position, named_focus) {
        (Some(position), None) => ScorePlacement::Numeric(position),
        (None, Some(focus)) => ScorePlacement::Named(focus),
        _ => unreachable!("checked position authority"),
    };
    let geometric = lower_geometry(
        primitive,
        input.explicit_geometry,
        input.relative_scale,
        placement,
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
        at: geometric.at,
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
    identity: Option<SemanticInputIdentity<'_>>,
    owner: &str,
    gaps: &mut Vec<ScoreFieldGap>,
) -> Option<T> {
    let Some(identity) = identity else {
        gaps.push(match owner {
            "color" => ScoreFieldGap::MissingColor,
            "touch" => ScoreFieldGap::MissingTouch,
            "continuity" => ScoreFieldGap::MissingContinuity,
            _ => unreachable!(),
        });
        return None;
    };
    match serde_json::from_value(serde_json::Value::String(identity.id.to_owned())) {
        Ok(value) => Some(value),
        Err(_) => {
            gaps.push(match owner {
                "color" => ScoreFieldGap::UnsupportedColorIdentity {
                    category: identity.category.to_owned(),
                    id: identity.id.to_owned(),
                },
                "touch" => ScoreFieldGap::UnsupportedTouchIdentity {
                    category: identity.category.to_owned(),
                    id: identity.id.to_owned(),
                },
                "continuity" => ScoreFieldGap::UnsupportedContinuityIdentity {
                    category: identity.category.to_owned(),
                    id: identity.id.to_owned(),
                },
                _ => unreachable!(),
            });
            None
        }
    }
}

#[derive(Clone)]
struct LoweredGeometry {
    center: Option<Point>,
    radius: Option<f64>,
    position: Option<Point>,
    size: Option<Point>,
    at: Option<AtRegion>,
}

#[derive(Clone, Copy)]
enum ScorePlacement<'a> {
    Numeric(&'a crate::SemanticNumericPosition),
    Named(FocusRegion),
}

#[derive(Clone, Copy)]
enum ResolvedGeometryDimensions {
    Circle { radius: Rational },
    CenteredSize { width: Rational, height: Rational },
    Square { side: Rational },
}

fn lower_geometry(
    primitive: Primitive,
    geometry: Option<&SemanticExplicitGeometry>,
    relative_scale: Option<CoreModifierValue>,
    placement: ScorePlacement<'_>,
    canvas: CanvasFormat,
) -> Result<LoweredGeometry, ScoreFieldGap> {
    let dimensions = resolve_geometry_dimensions(primitive, geometry, relative_scale)?;
    match placement {
        ScorePlacement::Numeric(position) => lower_numeric_geometry(dimensions, position, canvas),
        ScorePlacement::Named(focus) => lower_named_geometry(dimensions, focus),
    }
}

fn resolve_geometry_dimensions(
    primitive: Primitive,
    geometry: Option<&SemanticExplicitGeometry>,
    relative_scale: Option<CoreModifierValue>,
) -> Result<ResolvedGeometryDimensions, ScoreFieldGap> {
    let Some(geometry) = geometry else {
        return resolve_normal_dimensions(
            primitive,
            relative_scale.unwrap_or(CoreModifierValue::Normal),
        );
    };

    match (primitive, geometry) {
        (Primitive::Circle, SemanticExplicitGeometry::Radius(value))
        | (Primitive::Circle, SemanticExplicitGeometry::Diameter(value)) => {
            let mut radius = positive(value.decimal.value)?;
            if matches!(geometry, SemanticExplicitGeometry::Diameter(_)) {
                radius = radius.div_i128(2)?;
            }
            Ok(ResolvedGeometryDimensions::Circle { radius })
        }
        (
            Primitive::Ellipse | Primitive::Cloudform,
            SemanticExplicitGeometry::WidthHeight { width, height },
        ) => Ok(ResolvedGeometryDimensions::CenteredSize {
            width: positive(width.decimal.value)?,
            height: positive(height.decimal.value)?,
        }),
        (Primitive::Square, SemanticExplicitGeometry::Side(value)) => {
            Ok(ResolvedGeometryDimensions::Square {
                side: positive(value.decimal.value)?,
            })
        }
        (Primitive::Circle | Primitive::Ellipse | Primitive::Cloudform | Primitive::Square, _) => {
            Err(ScoreFieldGap::GeometryDimensionMismatch { primitive })
        }
        _ => Err(ScoreFieldGap::UnsupportedPrimitiveForExplicitGeometry { primitive }),
    }
}

fn resolve_normal_dimensions(
    primitive: Primitive,
    relative_scale: CoreModifierValue,
) -> Result<ResolvedGeometryDimensions, ScoreFieldGap> {
    let (factor_numerator, factor_denominator) = relative_scale_factor(relative_scale).ok_or(
        ScoreFieldGap::UnsupportedRelativeScaleValue {
            value: relative_scale,
        },
    )?;
    let normal = Rational::from_ratio(NORMAL_SHORT_EDGE_RATIO.0, NORMAL_SHORT_EDGE_RATIO.1)?;
    let width = normal.mul_ratio(factor_numerator, factor_denominator)?;
    match primitive {
        Primitive::Circle => Ok(ResolvedGeometryDimensions::Circle {
            radius: width.div_i128(2)?,
        }),
        Primitive::Ellipse | Primitive::Cloudform => Ok(ResolvedGeometryDimensions::CenteredSize {
            width,
            height: width.mul_ratio(
                NORMAL_ELLIPTICAL_ASPECT_RATIO.0,
                NORMAL_ELLIPTICAL_ASPECT_RATIO.1,
            )?,
        }),
        Primitive::Square => Ok(ResolvedGeometryDimensions::Square { side: width }),
        _ => Err(ScoreFieldGap::UnsupportedRelativeScalePrimitive { primitive }),
    }
}

fn lower_numeric_geometry(
    dimensions: ResolvedGeometryDimensions,
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

    match dimensions {
        ResolvedGeometryDimensions::Circle { radius } => {
            ensure_centered_extent(x, y, radius, radius, width_units, height_units, short_units)?;
            Ok(LoweredGeometry {
                center: Some(center),
                radius: Some(radius.to_f64()?),
                position: None,
                size: None,
                at: None,
            })
        }
        ResolvedGeometryDimensions::CenteredSize { width, height } => {
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
                at: None,
            })
        }
        ResolvedGeometryDimensions::Square { side } => {
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
                at: None,
            })
        }
    }
}

fn lower_named_geometry(
    dimensions: ResolvedGeometryDimensions,
    focus: FocusRegion,
) -> Result<LoweredGeometry, ScoreFieldGap> {
    let (radius, size) = match dimensions {
        ResolvedGeometryDimensions::Circle { radius } => (Some(radius.to_f64()?), None),
        ResolvedGeometryDimensions::CenteredSize { width, height } => {
            (None, Some(Point::new(width.to_f64()?, height.to_f64()?)))
        }
        ResolvedGeometryDimensions::Square { side } => {
            (None, Some(Point::new(side.to_f64()?, side.to_f64()?)))
        }
    };
    Ok(LoweredGeometry {
        center: None,
        radius,
        position: None,
        size,
        at: Some(AtRegion {
            region: focus_region_bounds(focus),
        }),
    })
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn macro_count_requires_an_integer_without_reinterpreting_number() {
        let mut fields = complete_macro_fields();
        fields.insert("count".to_owned(), ExpandedMacroValue::Integer(1));
        assert_eq!(project_macro_emit(&fields).unwrap().count, Some(1));

        fields.insert("count".to_owned(), ExpandedMacroValue::Number(1.0));
        assert_eq!(
            project_macro_emit(&fields).unwrap_err(),
            [ScoreFieldGap::MacroEmitFieldTypeMismatch {
                key: "count".to_owned(),
            }]
        );
    }

    fn complete_macro_fields() -> BTreeMap<String, ExpandedMacroValue> {
        [
            ("shape", "shape", "circle"),
            ("movement", "movement", "place"),
            ("place", "place", "center"),
        ]
        .into_iter()
        .map(|(key, category, id)| {
            (
                key.to_owned(),
                ExpandedMacroValue::SemanticRef {
                    category: category.to_owned(),
                    id: id.to_owned(),
                },
            )
        })
        .collect()
    }
}
