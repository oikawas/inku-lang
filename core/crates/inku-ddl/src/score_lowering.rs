//! Score candidates and eligible explicit lowering from verified Stage 1.5.

use crate::composition_plan::{
    CompositionPlanOutcome, CompositionPlanResult, FillCountResolution, FillGroupPlan,
    FillPlanOwner, FillRegionGeometry, FillRegionOwner, MirrorBodyPlanRef, MirrorRelationPlan,
    ObjectAnchor, ObjectPlacementPlan, PlacementAction, PlacementGroupPlan, PlacementMemberKind,
    PlacementMemberPlan, PlacementRecipe, PlanRelation, ResolvedFillRegion,
    ResolvedObjectAppearance, TransformGroupPlan,
};
use std::collections::{BTreeMap, BTreeSet};

use serde::Serialize;

use inku_score::{
    AnchorPoint, AtRegion, Canvas, CanvasFormat, CanvasGroundSpec, CanvasSpec, Color,
    ConnectedPositionAuthority, GroundMaterial, Instruction, InstructionMode, LineStyle, Point,
    Primitive, Relation, RelationGap, RelationType, ResolvedPaletteContext, Score,
    SurfaceIntensity, SurfaceSpec, SurfaceTexture, Thinness, TouchingConstraints, TransformGroup,
    Weight, lookup_canvas_format,
};

use crate::geometry::{
    NORMAL_ELLIPTICAL_ASPECT_RATIO, NORMAL_SHORT_EDGE_RATIO, named_region_bounds,
    relative_scale_factor,
};
use crate::score_angle::{ScoreAngleContext, ScoreAngleOccurrence, resolve_score_angle};
use crate::{
    CoreModifierValue, ExactDecimal, ExactDecimalError, ExpandedMacroInvocation, ExpandedMacroNode,
    ExpandedMacroValue, FocusRegion, GEOMETRY_RESOLUTION_POLICY_ID, GeneratedNodeProvenance,
    GeneratedTargetId, ScoreAppearanceField, ScoreAppearanceResolution, ScoreDiagnosticDisposition,
    ScoreDiagnosticOwner, ScoreErrorPolicy, ScoreFieldGap, ScoreInstructionField,
    ScoreLoweringDiagnostic, ScoreLoweringOutcome, ScoreMacroCallerField, ScoreOmissionUnit,
    SemanticExplicitGeometry, SemanticHead, SemanticIdentity, SemanticInstruction,
    SemanticMacroInvocationHead, SemanticNumericPosition, SemanticPreviousReference,
    SemanticRelation, SemanticRelationKind, SourceSpan, Stage15TargetPath, Stage15TargetProvenance,
    VerifiedStage15EffectiveView, geometry_resolution_policy_digest,
};

/// Stable identity for the non-serializable Score-field candidate boundary.
pub const SCORE_FIELD_CANDIDATE_SCHEMA_ID: &str = "inku.score-field-candidate.v2";
pub const EXPLICIT_SCORE_LOWERING_SCHEMA_ID: &str = "inku.explicit-score-lowering.v7";

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

/// Map only the closed canonical nine-shape identity into the shared Score type.
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
        ("shape", "point") => Primitive::Point,
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
        .chain(
            resolved_palette
                .observations()
                .into_iter()
                .flatten()
                .map(|color| color.oklch_lightness()),
        )
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
    view: VerifiedStage15EffectiveView<'a>,
    instruction_index: usize,
    instruction: &'a SemanticInstruction,
    effective_focus: Option<FocusRegion>,
) -> Option<ScoreLoweringInput<'a>> {
    let SemanticHead::Primitive(term) = &instruction.entity.head else {
        return None;
    };
    Some(ScoreLoweringInput {
        fill_target: project_fill_target(view, instruction.fill_target.as_ref()),
        group_region: None,
        proportion_width_extent: instruction
            .entity
            .proportion
            .width_extent
            .as_ref()
            .map(|term| (&term.identity).into()),
        proportion_arc_form: instruction
            .entity
            .proportion
            .arc_form
            .as_ref()
            .map(|term| (&term.identity).into()),
        additional_relative_scales: &instruction.entity.additional_relative_scales,
        additional_explicit_geometries: &instruction.entity.additional_explicit_geometries,
        additional_width_extents: &instruction.entity.additional_width_extents,
        shape_constraint: instruction
            .entity
            .shape_constraint
            .as_ref()
            .map(|value| value.value),
        proportion_aspect: instruction
            .entity
            .proportion
            .aspect
            .as_ref()
            .map(|term| (&term.identity).into()),
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
        color_cycle: instruction
            .sequence
            .as_ref()
            .filter(|sequence| matches!(sequence.kind, crate::SemanticSequenceKind::Color))
            .map_or(&[], |sequence| sequence.items.as_slice()),
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
        surface_intensity: instruction
            .entity
            .surface
            .intensity
            .as_ref()
            .map(|term| (&term.identity).into()),
        thinness: instruction
            .entity
            .thinness
            .as_ref()
            .map(|thinness| thinness.value),
        action: instruction
            .action
            .as_ref()
            .map(|term| (&term.identity).into()),
        numeric_position: instruction.entity.numeric_position.as_ref(),
        generated_position: None,
        generated_geometries: [None; 6],
        has_named_position: instruction.position.is_some(),
        named_position: instruction
            .position
            .as_ref()
            .map(|term| (&term.identity).into()),
        effective_focus,
        explicit_geometry: instruction.entity.explicit_geometry.as_ref(),
        relative_scale: instruction
            .entity
            .relative_scale
            .as_ref()
            .map(|scale| scale.value),
        angle: instruction
            .entity
            .angle
            .as_ref()
            .map(|term| (&term.identity).into()),
        angle_context: Some(ScoreAngleContext {
            composition_seed: view.composition_seed(),
            original_pre_expansion_digest: view.original_pre_expansion_digest(),
            original_expanded_meaning_digest: view.original_expanded_meaning_digest(),
            occurrence: ScoreAngleOccurrence::Direct {
                logical_ordinal: instruction_index as u64,
            },
        }),
        layout_direction: instruction
            .layout_direction
            .as_ref()
            .map(|term| (&term.identity).into()),
        ink_spread: instruction
            .entity
            .fluctuation
            .spread
            .as_ref()
            .map(|term| (&term.identity).into()),
        fluctuation: [
            instruction
                .entity
                .fluctuation
                .amplitude
                .as_ref()
                .map(|term| (&term.identity).into()),
            instruction
                .entity
                .fluctuation
                .frequency
                .as_ref()
                .map(|term| (&term.identity).into()),
            instruction
                .entity
                .fluctuation
                .quality
                .as_ref()
                .map(|term| (&term.identity).into()),
        ],
        has_unsupported_meaning: false,
    })
}

#[derive(Clone, Copy)]
struct MacroTransformScope<'a> {
    transform: &'a crate::ExpandedTransform,
    provenance: &'a GeneratedNodeProvenance,
}

#[derive(Clone)]
struct MacroDeliveryNode<'a> {
    node: &'a ExpandedMacroNode,
    transform_stack: Vec<MacroTransformScope<'a>>,
}

/// Visit pure containers while retaining every containing Transform in lexical order.
fn collect_macro_delivery_nodes<'a>(
    nodes: &'a [ExpandedMacroNode],
    transform_stack: &mut Vec<MacroTransformScope<'a>>,
    output: &mut Vec<MacroDeliveryNode<'a>>,
    transforms: &mut Vec<MacroTransformScope<'a>>,
) {
    for node in nodes {
        match node {
            ExpandedMacroNode::Group { body, .. } => {
                collect_macro_delivery_nodes(body, transform_stack, output, transforms)
            }
            ExpandedMacroNode::Transform {
                transform,
                body,
                provenance,
            } => {
                let scope = MacroTransformScope {
                    transform,
                    provenance,
                };
                transforms.push(scope);
                transform_stack.push(scope);
                collect_macro_delivery_nodes(body, transform_stack, output, transforms);
                transform_stack.pop();
            }
            _ => output.push(MacroDeliveryNode {
                node,
                transform_stack: transform_stack.clone(),
            }),
        }
    }
}

#[derive(Clone, Copy)]
struct MacroTransformValues {
    rotation_degrees: f64,
    scale_x: f64,
    scale_y: f64,
    translate_x: f64,
    translate_y: f64,
}

fn macro_transform_values(scope: MacroTransformScope<'_>) -> Option<MacroTransformValues> {
    let transform = scope.transform;
    let values = MacroTransformValues {
        rotation_degrees: transform.rotate_degrees.unwrap_or(0.0),
        scale_x: transform.scale_x.unwrap_or(1.0),
        scale_y: transform.scale_y.unwrap_or(1.0),
        translate_x: transform.translate_x.unwrap_or(0.0),
        translate_y: transform.translate_y.unwrap_or(0.0),
    };
    (values.rotation_degrees.is_finite()
        && values.scale_x.is_finite()
        && values.scale_y.is_finite()
        && values.translate_x.is_finite()
        && values.translate_y.is_finite())
    .then_some(values)
}

fn scope_contains(scope: MacroTransformScope<'_>, child: MacroTransformScope<'_>) -> bool {
    scope.provenance.expansion_path.len() < child.provenance.expansion_path.len()
        && child
            .provenance
            .expansion_path
            .starts_with(&scope.provenance.expansion_path)
}

fn is_in_invalid_transform(
    delivery: &MacroDeliveryNode<'_>,
    invalid_transforms: &[MacroTransformScope<'_>],
) -> bool {
    delivery.transform_stack.iter().any(|scope| {
        invalid_transforms.iter().any(|invalid| {
            invalid.provenance.generated_ordinal == scope.provenance.generated_ordinal
        })
    })
}

#[derive(Clone)]
struct MacroTransformRange {
    scope: GeneratedNodeProvenance,
    rotation_degrees: f64,
    scale_x: f64,
    scale_y: f64,
    translate_x: f64,
    translate_y: f64,
    start: usize,
    end: usize,
    fixed_position_indices: Vec<usize>,
    anchor_indices: Vec<usize>,
}

impl MacroTransformRange {
    fn record_cursor(&mut self, cursor: usize) {
        self.start = self.start.min(cursor);
        self.end = self.end.max(cursor);
    }

    fn record(&mut self, index: usize, numeric_anchor: bool) {
        self.start = self.start.min(index);
        self.end = self.end.max(index + 1);
        if numeric_anchor && !self.fixed_position_indices.contains(&index) {
            self.fixed_position_indices.push(index);
        }
    }

    fn record_anchor(&mut self, index: usize) {
        if !self.anchor_indices.contains(&index) {
            self.anchor_indices.push(index);
        }
    }
}

fn record_macro_transform_anchors(
    ranges: &mut BTreeMap<u64, MacroTransformRange>,
    transform_stack: &[MacroTransformScope<'_>],
    index: usize,
) {
    for scope in transform_stack {
        if let Some(range) = ranges.get_mut(&scope.provenance.generated_ordinal) {
            range.record_anchor(index);
        }
    }
}

fn record_macro_transform_ranges(
    ranges: &mut BTreeMap<u64, MacroTransformRange>,
    transform_stack: &[MacroTransformScope<'_>],
    index: usize,
    numeric_anchor: bool,
) {
    for scope in transform_stack {
        if let Some(range) = ranges.get_mut(&scope.provenance.generated_ordinal) {
            range.record(index, numeric_anchor);
        }
    }
}

fn checked_object_relation(
    kind: RelationType,
    input: ScoreLoweringInput<'_>,
    target_instruction_index: usize,
    prior: Option<(Primitive, Option<inku_score::ArcForm>)>,
) -> Option<Relation> {
    let touching = kind == RelationType::Touching;
    let bounds_relation = matches!(kind, RelationType::NotTouching | RelationType::Between);
    if !bounds_relation {
        let line_relation = matches!(kind, RelationType::Along | RelationType::Cutting);
        let supported = |primitive, arc_form: Option<inku_score::ArcForm>| {
            if line_relation {
                primitive == Primitive::Line
            } else {
                (matches!(primitive, Primitive::Line | Primitive::Arc) && arc_form.is_none())
                    || (!touching && primitive == Primitive::Point)
            }
        };
        let primitive = score_primitive_from_identity(input.primitive).ok()?;
        let arc_form = input
            .proportion_arc_form
            .filter(|form| form.id == "crescent")
            .map(|_| inku_score::ArcForm::Crescent);
        if !supported(primitive, arc_form)
            || !prior.is_some_and(|(primitive, arc_form)| supported(primitive, arc_form))
        {
            return None;
        }
    }
    // Geometry resolution validates the position. Every admitted named region
    // remains movable; an explicit numeric anchor is never changed by a relation.
    Some(Relation {
        kind,
        gap: RelationGap::Medium,
        target_instruction_index: Some(target_instruction_index),
        target_anchor_index: None,
        target_path_position: None,
        target_endpoint: None,
        position_authority: Some(input.position_authority()),
        touching_constraints: touching.then_some(TouchingConstraints {
            dimensions_fixed: input.exact_geometry().is_some()
                || input.relative_scale.is_some()
                || input.proportion_width_extent.is_some(),
            direction_fixed: input.angle.is_some() || input.proportion_arc_form.is_some(),
        }),
    })
}

fn checked_macro_relation(
    kind: &str,
    input: ScoreLoweringInput<'_>,
    target_instruction_index: Option<usize>,
    prior: Option<(Primitive, Option<inku_score::ArcForm>)>,
    target_path_position: Option<inku_score::TargetPathPosition>,
    target_endpoint: Option<inku_score::Endpoint>,
) -> Result<Relation, ScoreFieldGap> {
    let target =
        target_instruction_index.ok_or(ScoreFieldGap::UnavailableMacroRelationReference)?;
    let kind = match kind {
        "along" => RelationType::Along,
        "cutting" => RelationType::Cutting,
        "touching" => RelationType::Touching,
        "connected" => RelationType::Connected,
        "not_touching" => RelationType::NotTouching,
        "between" => RelationType::Between,
        _ => return Err(ScoreFieldGap::UnsupportedMacroRelation),
    };
    if target_endpoint.is_some()
        && (kind != RelationType::Connected
            || target_path_position.is_some()
            || !prior.is_some_and(|(primitive, _)| {
                matches!(primitive, Primitive::Line | Primitive::Arc)
            }))
    {
        return Err(ScoreFieldGap::UnsupportedMacroRelation);
    }
    if let Some(position) = &target_path_position {
        let valid_target = match position {
            inku_score::TargetPathPosition::Exact(position) => {
                position.is_finite()
                    && (0.0..=1.0).contains(position)
                    && prior.is_some_and(|(primitive, _)| primitive == Primitive::Line)
            }
            inku_score::TargetPathPosition::Selection(
                inku_score::TargetPathSelection::Interior,
            ) => prior.is_some_and(|(primitive, _)| {
                matches!(primitive, Primitive::Line | Primitive::Arc)
            }),
        };
        if kind != RelationType::Connected || !valid_target {
            return Err(ScoreFieldGap::UnsupportedMacroRelation);
        }
    }
    let mut relation = checked_object_relation(kind, input, target, prior)
        .ok_or(ScoreFieldGap::UnsupportedMacroRelation)?;
    relation.target_path_position = target_path_position;
    relation.target_endpoint = target_endpoint;
    Ok(relation)
}

fn checked_macro_anchor_relation(
    kind: &str,
    input: ScoreLoweringInput<'_>,
    target_anchor_index: usize,
    current_primitive: Primitive,
    current_arc_form: Option<inku_score::ArcForm>,
) -> Result<Relation, ScoreFieldGap> {
    let current_supported = (matches!(current_primitive, Primitive::Line | Primitive::Arc)
        && current_arc_form.is_none())
        || current_primitive == Primitive::Point;
    if kind != "connected" || !current_supported {
        return Err(ScoreFieldGap::UnsupportedMacroRelation);
    }
    Ok(Relation {
        kind: RelationType::Connected,
        gap: RelationGap::Medium,
        target_instruction_index: None,
        target_anchor_index: Some(target_anchor_index),
        target_path_position: None,
        target_endpoint: None,
        position_authority: Some(input.position_authority()),
        touching_constraints: None,
    })
}

fn plan_relation(relation: Relation) -> PlanRelation {
    PlanRelation {
        kind: relation.kind,
        gap: relation.gap,
        target_object_index: relation.target_instruction_index,
        target_anchor_index: relation.target_anchor_index,
        target_path_position: relation.target_path_position,
        target_endpoint: relation.target_endpoint,
        position_authority: relation.position_authority,
        touching_constraints: relation.touching_constraints,
    }
}

#[allow(clippy::too_many_arguments)]
fn lower_macro_instruction(
    view: VerifiedStage15EffectiveView<'_>,
    source_instruction_index: usize,
    instruction: &SemanticInstruction,
    head: &SemanticMacroInvocationHead,
    group_count: Option<u64>,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
    instructions: &mut Vec<Instruction>,
    anchors: &mut Vec<AnchorPoint>,
    anchor_origins: &mut Vec<ScoreAnchorOrigin>,
    instruction_origins: &mut Vec<ScoreInstructionOrigin>,
    diagnostics: &mut Vec<ScoreLoweringDiagnostic>,
    mut objects: Option<&mut Vec<ObjectPlacementPlan>>,
    mut transform_groups: Option<&mut Vec<TransformGroupPlan>>,
    score_transform_groups: &mut Vec<TransformGroup>,
) {
    let caller_invalid = append_macro_caller_diagnostics(
        source_instruction_index,
        instruction,
        head,
        group_count,
        objects.is_some(),
        error_policy,
        diagnostics,
    );
    if caller_invalid {
        return;
    }
    let expansion = match exact_macro_expansion(view, head) {
        Ok(expansion) => expansion,
        Err(reason) => {
            diagnostics.push(ScoreLoweringDiagnostic {
                owner: macro_invocation_owner(source_instruction_index, head, None),
                disposition: diagnostic_disposition(
                    error_policy,
                    &reason,
                    macro_invocation_unit(source_instruction_index, head),
                    None,
                ),
                reason,
            });
            return;
        }
    };

    let mut delivery_nodes = Vec::new();
    let mut transform_stack = Vec::new();
    let mut transforms = Vec::new();
    collect_macro_delivery_nodes(
        &expansion.nodes,
        &mut transform_stack,
        &mut delivery_nodes,
        &mut transforms,
    );
    let invalid_transforms = transforms
        .iter()
        .copied()
        .filter(|scope| macro_transform_values(*scope).is_none())
        .collect::<Vec<_>>();
    for scope in invalid_transforms.iter().copied().filter(|scope| {
        !invalid_transforms
            .iter()
            .copied()
            .any(|ancestor| scope_contains(ancestor, *scope))
    }) {
        let reason = ScoreFieldGap::UnsupportedMacroStructure;
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: generated_owner(source_instruction_index, scope.provenance, None),
            disposition: diagnostic_disposition(
                error_policy,
                &reason,
                ScoreOmissionUnit::MacroStructuralSubtree {
                    source_instruction_index,
                    invocation_ordinal: scope.provenance.invocation.invocation_ordinal,
                    expansion_path: scope.provenance.expansion_path.clone(),
                    generated_ordinal: scope.provenance.generated_ordinal,
                },
                None,
            ),
            reason,
        });
    }
    let mut transform_ranges = transforms
        .iter()
        .copied()
        .filter_map(|scope| {
            macro_transform_values(scope).and_then(|transform| {
                (!invalid_transforms
                    .iter()
                    .copied()
                    .any(|ancestor| scope_contains(ancestor, scope)))
                .then_some((
                    scope.provenance.generated_ordinal,
                    MacroTransformRange {
                        scope: scope.provenance.clone(),
                        rotation_degrees: transform.rotation_degrees,
                        scale_x: transform.scale_x,
                        scale_y: transform.scale_y,
                        translate_x: transform.translate_x,
                        translate_y: transform.translate_y,
                        start: usize::MAX,
                        end: 0,
                        fixed_position_indices: Vec::new(),
                        anchor_indices: Vec::new(),
                    },
                ))
            })
        })
        .collect::<BTreeMap<_, _>>();
    let emit_nodes = delivery_nodes
        .iter()
        .enumerate()
        .filter_map(|(index, delivery)| match delivery.node {
            ExpandedMacroNode::Emit {
                binding,
                provenance,
                ..
            } => Some((binding.as_ref(), provenance, index)),
            _ => None,
        })
        .collect::<Vec<_>>();
    let mut successful_anchors: BTreeMap<GeneratedTargetId, usize> = BTreeMap::new();
    let mut unavailable_anchor_targets = BTreeSet::new();
    for delivery in &delivery_nodes {
        if is_in_invalid_transform(delivery, &invalid_transforms) {
            continue;
        }
        let ExpandedMacroNode::Anchor {
            target,
            fields,
            provenance,
        } = delivery.node
        else {
            continue;
        };
        let angle_context = ScoreAngleContext {
            composition_seed: view.composition_seed(),
            original_pre_expansion_digest: view.original_pre_expansion_digest(),
            original_expanded_meaning_digest: view.original_expanded_meaning_digest(),
            occurrence: ScoreAngleOccurrence::MacroEmit {
                macro_semantic_ordinal: view
                    .macro_semantic_ordinal(provenance.invocation.invocation_ordinal)
                    .expect("verified Stage 1.5 view preserves every Macro semantic ordinal"),
                expansion_path: &provenance.expansion_path,
                generated_ordinal: provenance.generated_ordinal,
            },
        };
        match project_macro_anchor(fields, angle_context) {
            Ok(anchor) => {
                let anchor_index = anchors.len();
                anchors.push(anchor);
                anchor_origins.push(ScoreAnchorOrigin::MacroAnchor {
                    source_instruction_index,
                    target: target.clone(),
                    provenance: provenance.clone(),
                });
                record_macro_transform_anchors(
                    &mut transform_ranges,
                    &delivery.transform_stack,
                    anchor_index,
                );
                successful_anchors.insert(target.clone(), anchor_index);
            }
            Err(gaps) => {
                unavailable_anchor_targets.insert(target.clone());
                for reason in gaps {
                    diagnostics.push(ScoreLoweringDiagnostic {
                        owner: generated_owner(source_instruction_index, provenance, None),
                        disposition: diagnostic_disposition(
                            error_policy,
                            &reason,
                            ScoreOmissionUnit::MacroStructuralSubtree {
                                source_instruction_index,
                                invocation_ordinal: provenance.invocation.invocation_ordinal,
                                expansion_path: provenance.expansion_path.clone(),
                                generated_ordinal: provenance.generated_ordinal,
                            },
                            None,
                        ),
                        reason,
                    });
                }
            }
        }
    }
    let mut relation_by_to = BTreeMap::new();
    let mut anchor_relation_by_to = BTreeMap::new();
    for delivery in &delivery_nodes {
        if is_in_invalid_transform(delivery, &invalid_transforms) {
            continue;
        }
        let node = delivery.node;
        let ExpandedMacroNode::Relation {
            kind,
            from,
            to,
            target_path_position,
            target_endpoint,
            provenance,
        } = node
        else {
            continue;
        };
        if !matches!(
            kind.as_str(),
            "along" | "cutting" | "connected" | "touching" | "not_touching" | "between"
        ) {
            continue;
        }
        if let Some(anchor_index) = successful_anchors.get(from) {
            let to_position = emit_nodes
                .iter()
                .position(|(binding, _, _)| binding.is_some_and(|binding| binding == to));
            if to_position.is_some()
                && kind == "connected"
                && target_path_position.is_none()
                && target_endpoint.is_none()
                && anchor_relation_by_to
                    .insert(to.clone(), (*anchor_index, kind.as_str()))
                    .is_none()
            {
                continue;
            }
        }
        let from_position = emit_nodes
            .iter()
            .position(|(binding, _, _)| binding.is_some_and(|binding| binding == from));
        let to_position = emit_nodes
            .iter()
            .position(|(binding, _, _)| binding.is_some_and(|binding| binding == to));
        let secondary = (kind == "between")
            .then(|| {
                from_position
                    .and_then(|from| from.checked_sub(1))
                    .map(|position| emit_nodes[position].1.generated_ordinal)
            })
            .flatten();
        let path_connected = kind == "connected" && target_path_position.is_some();
        if from_position.zip(to_position).is_some_and(|(from, to)| {
            from < to
                && (path_connected
                    || (to == from + 1
                        && (kind != "between" || secondary.is_some())
                        && delivery_nodes[emit_nodes[if kind == "between" {
                            from.saturating_sub(1)
                        } else {
                            from
                        }]
                        .2 + 1..emit_nodes[to].2]
                            .iter()
                            .all(|node| !matches!(node.node, ExpandedMacroNode::Anchor { .. }))))
        }) && relation_by_to
            .insert(
                to.clone(),
                (
                    from.clone(),
                    kind.as_str(),
                    secondary,
                    target_path_position.clone(),
                    *target_endpoint,
                ),
            )
            .is_none()
        {
            continue;
        }
        let reason = ScoreFieldGap::UnsupportedMacroRelation;
        let target_provenance = to_position.map(|position| emit_nodes[position].1);
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: generated_owner(
                source_instruction_index,
                target_provenance.unwrap_or(provenance),
                None,
            ),
            disposition: relation_diagnostic_disposition(),
            reason,
        });
    }
    let mut successful_bindings: BTreeMap<GeneratedTargetId, usize> = BTreeMap::new();
    let mut successful_emits = BTreeMap::new();

    for delivery in &delivery_nodes {
        let node = delivery.node;
        if is_in_invalid_transform(delivery, &invalid_transforms) {
            continue;
        }
        let ExpandedMacroNode::Emit {
            binding,
            fields,
            provenance,
        } = node
        else {
            if let ExpandedMacroNode::Anchor { target, .. } = node
                && successful_anchors.contains_key(target)
            {
                // Anchors were resolved before Emits for reference lookup, but
                // their empty drawable range belongs at this source-body cursor.
                let cursor = objects
                    .as_ref()
                    .map_or(instructions.len(), |objects| objects.len());
                for scope in &delivery.transform_stack {
                    if let Some(range) =
                        transform_ranges.get_mut(&scope.provenance.generated_ordinal)
                    {
                        range.record_cursor(cursor);
                    }
                }
            }
            if matches!(node, ExpandedMacroNode::Anchor { .. })
                || matches!(node, ExpandedMacroNode::Relation { kind, .. } if matches!(kind.as_str(), "along" | "cutting" | "connected" | "touching" | "not_touching" | "between"))
            {
                continue;
            }
            let provenance = node.provenance();
            let reason = ScoreFieldGap::UnsupportedMacroStructure;
            diagnostics.push(ScoreLoweringDiagnostic {
                owner: generated_owner(source_instruction_index, provenance, None),
                disposition: diagnostic_disposition(
                    error_policy,
                    &reason,
                    ScoreOmissionUnit::MacroStructuralSubtree {
                        source_instruction_index,
                        invocation_ordinal: provenance.invocation.invocation_ordinal,
                        expansion_path: provenance.expansion_path.clone(),
                        generated_ordinal: provenance.generated_ordinal,
                    },
                    None,
                ),
                reason,
            });
            continue;
        };
        let mut relation_dependency = binding
            .as_ref()
            .and_then(|binding| relation_by_to.get(binding));
        let anchor_relation_dependency = binding
            .as_ref()
            .and_then(|binding| anchor_relation_by_to.get(binding));
        if let Some((dependency, _, secondary, _, _)) = relation_dependency
            && (!successful_bindings.contains_key(dependency)
                || secondary.is_some_and(|ordinal| !successful_emits.contains_key(&ordinal)))
        {
            let reason = ScoreFieldGap::UnavailableMacroRelationReference;
            diagnostics.push(ScoreLoweringDiagnostic {
                owner: generated_owner(source_instruction_index, provenance, None),
                disposition: relation_diagnostic_disposition(),
                reason,
            });
            relation_dependency = None;
        }
        let mut input = match project_macro_emit(fields, &[], objects.is_some()) {
            Ok(input) => input,
            Err(emit_gaps) => {
                let recoverable = emit_gaps
                    .iter()
                    .filter_map(|gap| {
                        appearance_field_for_macro_projection_gap(gap)
                            .map(|field| (gap.clone(), field))
                    })
                    .collect::<Vec<_>>();
                let remaining = emit_gaps
                    .iter()
                    .filter(|gap| appearance_field_for_macro_projection_gap(gap).is_none())
                    .cloned()
                    .collect::<Vec<_>>();
                for (reason, field) in &recoverable {
                    diagnostics.push(ScoreLoweringDiagnostic {
                        owner: generated_owner(
                            source_instruction_index,
                            provenance,
                            macro_key_for_appearance(*field).map(str::to_owned),
                        ),
                        disposition: diagnostic_disposition(
                            error_policy,
                            reason,
                            ScoreOmissionUnit::AppearanceField { field: *field },
                            Some(default_resolution(*field, false)),
                        ),
                        reason: reason.clone(),
                    });
                }
                for reason in &remaining {
                    diagnostics.push(ScoreLoweringDiagnostic {
                        owner: generated_owner(
                            source_instruction_index,
                            provenance,
                            macro_key_for_gap(reason),
                        ),
                        disposition: diagnostic_disposition(
                            error_policy,
                            reason,
                            macro_emit_unit(source_instruction_index, provenance),
                            None,
                        ),
                        reason: reason.clone(),
                    });
                }
                if !remaining.is_empty() {
                    continue;
                }
                let omitted = recoverable
                    .iter()
                    .map(|(_, field)| *field)
                    .collect::<Vec<_>>();
                match project_macro_emit(fields, &omitted, objects.is_some()) {
                    Ok(input) => input,
                    Err(_) => unreachable!("removing only optional appearance fields is complete"),
                }
            }
        };
        input.effective_focus = if input
            .named_position
            .is_some_and(|place| place.id == "center")
        {
            match exact_macro_emit_focus(view, provenance) {
                Ok(focus) => Some(focus),
                Err(reason) => {
                    diagnostics.push(ScoreLoweringDiagnostic {
                        owner: generated_owner(
                            source_instruction_index,
                            provenance,
                            Some("place".to_owned()),
                        ),
                        disposition: diagnostic_disposition(
                            error_policy,
                            &reason,
                            macro_emit_unit(source_instruction_index, provenance),
                            None,
                        ),
                        reason,
                    });
                    continue;
                }
            }
        } else {
            None
        };
        input.angle_context = Some(ScoreAngleContext {
            composition_seed: view.composition_seed(),
            original_pre_expansion_digest: view.original_pre_expansion_digest(),
            original_expanded_meaning_digest: view.original_expanded_meaning_digest(),
            occurrence: ScoreAngleOccurrence::MacroEmit {
                macro_semantic_ordinal: view
                    .macro_semantic_ordinal(provenance.invocation.invocation_ordinal)
                    .expect("verified Stage 1.5 view preserves every Macro semantic ordinal"),
                expansion_path: &provenance.expansion_path,
                generated_ordinal: provenance.generated_ordinal,
            },
        });
        if let Some(objects) = objects.as_deref_mut() {
            let origin = ScoreInstructionOrigin::MacroEmit {
                source_instruction_index,
                binding: binding.clone(),
                provenance: provenance.clone(),
            };
            let attempt =
                resolve_projected_instruction(input, context, error_policy, |input, context| {
                    resolve_object_plan(input, context, origin.clone())
                });
            let object_index = append_plan_attempt(
                attempt,
                |reason| {
                    generated_owner(
                        source_instruction_index,
                        provenance,
                        macro_key_for_gap(reason),
                    )
                },
                macro_emit_unit(source_instruction_index, provenance),
                error_policy,
                objects,
                diagnostics,
            );
            let Some(object_index) = object_index else {
                continue;
            };
            if let Some((dependency, kind, _, target_path_position, target_endpoint)) =
                relation_dependency
            {
                let target_object_index = successful_bindings[dependency];
                let prior = &objects[target_object_index];
                let relation = checked_macro_relation(
                    kind,
                    input,
                    Some(target_object_index),
                    Some((prior.primitive(), prior.arc_form())),
                    target_path_position.clone(),
                    *target_endpoint,
                );
                match relation {
                    Ok(relation) => objects[object_index].relation = Some(plan_relation(relation)),
                    Err(reason) => {
                        diagnostics.push(ScoreLoweringDiagnostic {
                            owner: generated_owner(source_instruction_index, provenance, None),
                            disposition: relation_diagnostic_disposition(),
                            reason,
                        });
                    }
                }
            } else if let Some((target_anchor_index, kind)) = anchor_relation_dependency {
                let current = &objects[object_index];
                match checked_macro_anchor_relation(
                    kind,
                    input,
                    *target_anchor_index,
                    current.primitive(),
                    current.arc_form(),
                ) {
                    Ok(relation) => objects[object_index].relation = Some(plan_relation(relation)),
                    Err(reason) => {
                        diagnostics.push(ScoreLoweringDiagnostic {
                            owner: generated_owner(source_instruction_index, provenance, None),
                            disposition: relation_diagnostic_disposition(),
                            reason,
                        });
                    }
                }
            }
            record_macro_transform_ranges(
                &mut transform_ranges,
                &delivery.transform_stack,
                object_index,
                input.exact_position().is_some(),
            );
            successful_emits.insert(provenance.generated_ordinal, object_index);
            if let Some(binding) = binding {
                successful_bindings.insert(binding.clone(), object_index);
            }
            continue;
        }
        let attempt = lower_projected_instruction(input, context, error_policy);
        for omission in attempt.appearance_omissions {
            diagnostics.push(ScoreLoweringDiagnostic {
                owner: generated_owner(
                    source_instruction_index,
                    provenance,
                    macro_key_for_appearance(omission.field).map(str::to_owned),
                ),
                disposition: diagnostic_disposition(
                    error_policy,
                    &omission.reason,
                    ScoreOmissionUnit::AppearanceField {
                        field: omission.field,
                    },
                    Some(omission.resolution),
                ),
                reason: omission.reason,
            });
        }
        for omission in attempt.instruction_field_omissions {
            diagnostics.push(ScoreLoweringDiagnostic {
                owner: generated_owner(
                    source_instruction_index,
                    provenance,
                    macro_key_for_gap(&omission.reason),
                ),
                disposition: diagnostic_disposition(
                    error_policy,
                    &omission.reason,
                    ScoreOmissionUnit::InstructionField {
                        field: omission.field,
                    },
                    None,
                ),
                reason: omission.reason,
            });
        }
        for reason in attempt.remaining_gaps {
            diagnostics.push(ScoreLoweringDiagnostic {
                owner: generated_owner(
                    source_instruction_index,
                    provenance,
                    macro_key_for_gap(&reason),
                ),
                disposition: diagnostic_disposition(
                    error_policy,
                    &reason,
                    macro_emit_unit(source_instruction_index, provenance),
                    None,
                ),
                reason,
            });
        }
        if let Some(mut score_instruction) = attempt.instruction {
            if let Some((dependency, kind, _, target_path_position, target_endpoint)) =
                relation_dependency
            {
                let target_instruction_index = successful_bindings.get(dependency).copied();
                let prior = target_instruction_index.and_then(|index| instructions.get(index));
                match checked_macro_relation(
                    kind,
                    input,
                    target_instruction_index,
                    prior.map(|instruction| (instruction.primitive, instruction.arc_form)),
                    target_path_position.clone(),
                    *target_endpoint,
                ) {
                    Ok(relation) => score_instruction.relation = Some(relation),
                    Err(reason) => {
                        diagnostics.push(ScoreLoweringDiagnostic {
                            owner: generated_owner(source_instruction_index, provenance, None),
                            disposition: relation_diagnostic_disposition(),
                            reason,
                        });
                    }
                }
            } else if let Some((target_anchor_index, kind)) = anchor_relation_dependency {
                match checked_macro_anchor_relation(
                    kind,
                    input,
                    *target_anchor_index,
                    score_instruction.primitive,
                    score_instruction.arc_form,
                ) {
                    Ok(relation) => score_instruction.relation = Some(relation),
                    Err(reason) => {
                        diagnostics.push(ScoreLoweringDiagnostic {
                            owner: generated_owner(source_instruction_index, provenance, None),
                            disposition: relation_diagnostic_disposition(),
                            reason,
                        });
                    }
                }
            }
            let score_index = instructions.len();
            instructions.push(score_instruction);
            record_macro_transform_ranges(
                &mut transform_ranges,
                &delivery.transform_stack,
                score_index,
                input.exact_position().is_some(),
            );
            successful_emits.insert(provenance.generated_ordinal, score_index);
            if let Some(binding) = binding {
                successful_bindings.insert(binding.clone(), score_index);
            }
            instruction_origins.push(ScoreInstructionOrigin::MacroEmit {
                source_instruction_index,
                binding: binding.clone(),
                provenance: provenance.clone(),
            });
        }
    }
    let mut completed_ranges = transform_ranges
        .into_values()
        .filter(|range| range.end > range.start || !range.anchor_indices.is_empty())
        .collect::<Vec<_>>();
    completed_ranges.sort_by(|left, right| {
        let left_path = &left.scope.expansion_path;
        let right_path = &right.scope.expansion_path;
        if left_path.len() < right_path.len() && right_path.starts_with(left_path) {
            std::cmp::Ordering::Greater
        } else if right_path.len() < left_path.len() && left_path.starts_with(right_path) {
            std::cmp::Ordering::Less
        } else {
            left_path.cmp(right_path)
        }
    });
    if let Some(groups) = transform_groups.as_deref_mut() {
        groups.extend(
            completed_ranges
                .into_iter()
                .map(|range| TransformGroupPlan {
                    start: range.start,
                    end: range.end,
                    rotation_degrees: range.rotation_degrees,
                    scale_x: range.scale_x,
                    scale_y: range.scale_y,
                    translate_x: range.translate_x,
                    translate_y: range.translate_y,
                    fixed_position_indices: range.fixed_position_indices,
                    anchor_indices: range.anchor_indices,
                    provenance: range.scope,
                }),
        );
    } else {
        score_transform_groups.extend(completed_ranges.into_iter().map(|range| TransformGroup {
            start: range.start,
            end: range.end,
            rotation_degrees: range.rotation_degrees,
            scale_x: range.scale_x,
            scale_y: range.scale_y,
            translate_x: range.translate_x,
            translate_y: range.translate_y,
            fixed_position_indices: range.fixed_position_indices,
            anchor_indices: range.anchor_indices,
        }));
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

fn append_macro_caller_diagnostics(
    source_instruction_index: usize,
    instruction: &SemanticInstruction,
    head: &SemanticMacroInvocationHead,
    group_count: Option<u64>,
    planning: bool,
    error_policy: ScoreErrorPolicy,
    diagnostics: &mut Vec<ScoreLoweringDiagnostic>,
) -> bool {
    let mut invalid = false;
    match group_count.or_else(|| {
        instruction
            .entity
            .quantity
            .as_ref()
            .map(|value| value.value)
    }) {
        None | Some(1) => {}
        Some(value) if planning && (1..=u64::from(u32::MAX)).contains(&value) => {}
        Some(0) => {
            invalid = true;
            append_macro_invocation_diagnostic(
                source_instruction_index,
                head,
                ScoreFieldGap::ExactCountZero { value: 0 },
                error_policy,
                diagnostics,
            );
        }
        Some(value) if value <= u64::from(u32::MAX) => {
            invalid = true;
            append_macro_invocation_diagnostic(
                source_instruction_index,
                head,
                ScoreFieldGap::RepeatedCountUnsupported {
                    value: value as u32,
                },
                error_policy,
                diagnostics,
            );
        }
        Some(value) => {
            invalid = true;
            append_macro_invocation_diagnostic(
                source_instruction_index,
                head,
                ScoreFieldGap::ExactCountExceedsScoreRange { value },
                error_policy,
                diagnostics,
            );
        }
    }
    for (field, present) in [
        (
            ScoreAppearanceField::Color,
            instruction.entity.color.is_some(),
        ),
        (
            ScoreAppearanceField::Touch,
            instruction.entity.touch.is_some(),
        ),
        (
            ScoreAppearanceField::Continuity,
            instruction.entity.continuity.is_some(),
        ),
        (
            ScoreAppearanceField::SurfaceQuality,
            instruction.entity.surface.quality.is_some(),
        ),
        (
            ScoreAppearanceField::SurfaceIntensity,
            instruction.entity.surface.intensity.is_some(),
        ),
    ] {
        if !present {
            continue;
        }
        let reason = ScoreFieldGap::UnboundMacroCallerMeaning;
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: macro_caller_owner(source_instruction_index, instruction, head, field),
            disposition: diagnostic_disposition(
                error_policy,
                &reason,
                ScoreOmissionUnit::AppearanceField { field },
                Some(ScoreAppearanceResolution::PreserveGeneratedValue),
            ),
            reason,
        });
    }
    if instruction.action.is_some() {
        let reason = ScoreFieldGap::UnboundMacroCallerMeaning;
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: macro_caller_field_owner(
                source_instruction_index,
                instruction,
                head,
                ScoreMacroCallerField::Action,
            ),
            disposition: diagnostic_disposition(
                error_policy,
                &reason,
                macro_caller_field_unit(
                    source_instruction_index,
                    head,
                    ScoreMacroCallerField::Action,
                ),
                None,
            ),
            reason,
        });
    }
    if instruction.entity.thinness.is_some()
        || instruction.entity.relative_scale.is_some()
        || instruction.entity.explicit_geometry.is_some()
        || instruction.entity.numeric_position.is_some()
        || instruction.entity.angle.is_some()
        || instruction.entity.fluctuation.amplitude.is_some()
        || instruction.entity.fluctuation.frequency.is_some()
        || instruction.entity.fluctuation.quality.is_some()
        || instruction.entity.fluctuation.spread.is_some()
        || instruction.entity.shape_constraint.is_some()
        || instruction.entity.proportion.aspect.is_some()
        || instruction.entity.proportion.width_extent.is_some()
        || instruction.entity.proportion.arc_form.is_some()
        || instruction.layout_direction.is_some()
        || instruction.position.is_some()
    {
        invalid = true;
        append_macro_invocation_diagnostic(
            source_instruction_index,
            head,
            ScoreFieldGap::UnboundMacroCallerMeaning,
            error_policy,
            diagnostics,
        );
    }
    invalid
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

const MACRO_SCORE_FIELD_KEYS: [&str; 32] = [
    "radius",
    "diameter",
    "length",
    "side",
    "width",
    "height",
    "chord",
    "sagitta",
    "position_x",
    "position_y",
    "proportion_width_extent",
    "proportion_arc_form",
    "proportion_aspect",
    "shape_form",
    "sides",
    "layout_direction",
    "shape",
    "movement",
    "place",
    "color",
    "touch",
    "continuity",
    "surface",
    "surface_intensity",
    "count",
    "angle",
    "thinness",
    "relative_scale",
    "fluctuation_amplitude",
    "fluctuation_frequency",
    "fluctuation_quality",
    "ink_spread",
];

fn project_macro_emit<'a>(
    fields: &'a BTreeMap<String, ExpandedMacroValue>,
    omitted_appearance: &[ScoreAppearanceField],
    planning: bool,
) -> Result<ScoreLoweringInput<'a>, Vec<ScoreFieldGap>> {
    let mut gaps = fields
        .keys()
        .filter(|key| !MACRO_SCORE_FIELD_KEYS.contains(&key.as_str()))
        .map(|key| ScoreFieldGap::UnknownMacroEmitField { key: key.clone() })
        .collect::<Vec<_>>();
    let primitive = macro_semantic_field(fields, "shape", "shape", true, &mut gaps);
    let proportion_aspect =
        macro_semantic_field(fields, "proportion_aspect", "ratio", false, &mut gaps);
    let proportion_width_extent =
        macro_semantic_field(fields, "proportion_width_extent", "ratio", false, &mut gaps);
    let proportion_arc_form =
        macro_semantic_field(fields, "proportion_arc_form", "ratio", false, &mut gaps);
    let form = macro_semantic_field(fields, "shape_form", "shape_form", false, &mut gaps);
    if let Some(form) = form
        && form.id != "regular"
    {
        gaps.push(ScoreFieldGap::UnsupportedMacroEmitIdentity {
            key: "shape_form".to_owned(),
            category: form.category.to_owned(),
            id: form.id.to_owned(),
        });
    }
    let sides = match fields.get("sides") {
        None => None,
        Some(ExpandedMacroValue::Integer(value)) if (5..=8).contains(value) => Some(*value as u64),
        Some(ExpandedMacroValue::Integer(value)) => {
            gaps.push(ScoreFieldGap::MacroEmitIntegerOutOfRange {
                key: "sides".to_owned(),
                value: *value,
            });
            None
        }
        Some(_) => {
            gaps.push(ScoreFieldGap::MacroEmitFieldTypeMismatch {
                key: "sides".to_owned(),
            });
            None
        }
    };
    let shape_constraint = (form.is_some() || sides.is_some()).then_some(crate::ShapeConstraint {
        regular: form.is_some() || sides.is_some(),
        sides,
    });
    let action = macro_semantic_field(fields, "movement", "movement", true, &mut gaps);
    let place = macro_semantic_field(fields, "place", "place", false, &mut gaps);
    use crate::geometry::{ExactGeometry as G, ExactPosition};
    let radius = macro_exact_field(fields, "radius", &mut gaps);
    let diameter = macro_exact_field(fields, "diameter", &mut gaps);
    let length = macro_exact_field(fields, "length", &mut gaps);
    let side = macro_exact_field(fields, "side", &mut gaps);
    let size = macro_exact_pair(fields, "width", "height", &mut gaps);
    let arc = macro_exact_pair(fields, "chord", "sagitta", &mut gaps);
    let generated_position = macro_exact_pair(fields, "position_x", "position_y", &mut gaps)
        .map(|(x, y)| ExactPosition { x, y });
    let generated_geometries = [
        radius.map(G::Radius),
        diameter.map(G::Diameter),
        length.map(G::Length),
        side.map(G::Side),
        size.map(|(width, height)| G::WidthHeight { width, height }),
        arc.map(|(chord, sagitta)| G::ChordSagitta { chord, sagitta }),
    ];
    let color = (!omitted_appearance.contains(&ScoreAppearanceField::Color))
        .then(|| macro_semantic_field(fields, "color", "color", false, &mut gaps))
        .flatten();
    let touch = (!omitted_appearance.contains(&ScoreAppearanceField::Touch))
        .then(|| macro_semantic_field(fields, "touch", "touch", false, &mut gaps))
        .flatten();
    let continuity = (!omitted_appearance.contains(&ScoreAppearanceField::Continuity))
        .then(|| macro_semantic_field(fields, "continuity", "continuity", false, &mut gaps))
        .flatten();
    let surface = (!omitted_appearance.contains(&ScoreAppearanceField::SurfaceQuality))
        .then(|| macro_semantic_field(fields, "surface", "surface", false, &mut gaps))
        .flatten();
    let surface_intensity = (!omitted_appearance.contains(&ScoreAppearanceField::SurfaceIntensity))
        .then(|| macro_semantic_field(fields, "surface_intensity", "surface", false, &mut gaps))
        .flatten();
    let angle = macro_semantic_field(fields, "angle", "angle", false, &mut gaps);
    let layout_direction =
        macro_semantic_field(fields, "layout_direction", "angle", false, &mut gaps);
    let ink_spread = macro_semantic_field(fields, "ink_spread", "variation", false, &mut gaps);
    let fluctuation = [
        "fluctuation_amplitude",
        "fluctuation_frequency",
        "fluctuation_quality",
    ]
    .map(|key| {
        let value = macro_semantic_field(fields, key, "variation", false, &mut gaps);
        if let Some(identity) = value
            && !crate::fluctuation::matches_dimension(
                identity.category,
                identity.id,
                crate::fluctuation::FluctuationDimension::from_field(key),
            )
        {
            gaps.push(ScoreFieldGap::UnsupportedMacroEmitIdentity {
                key: key.to_owned(),
                category: identity.category.to_owned(),
                id: identity.id.to_owned(),
            });
        }
        value
    });
    let thinness = macro_semantic_field(fields, "thinness", "thinness", false, &mut gaps);
    let relative_scale =
        macro_semantic_field(fields, "relative_scale", "relative_scale", false, &mut gaps);
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
        && !matches!(
            identity.id,
            "line"
                | "circle"
                | "ellipse"
                | "cloudform"
                | "square"
                | "triangle"
                | "polygon"
                | "arc"
                | "point"
        )
    {
        gaps.push(ScoreFieldGap::UnsupportedMacroEmitIdentity {
            key: "shape".to_owned(),
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        });
    }
    if let Some(identity) = action
        && identity.id != "place"
        && identity.id != "draw"
        && identity.id != "fill"
        && !(planning && matches!(identity.id, "line_up" | "scatter" | "tile" | "fill"))
    {
        gaps.push(ScoreFieldGap::UnsupportedMacroEmitIdentity {
            key: "movement".to_owned(),
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        });
    }
    if let Some(identity) = place
        && !crate::geometry::supports_named_position(identity.id)
    {
        gaps.push(ScoreFieldGap::UnsupportedMacroEmitIdentity {
            key: "place".to_owned(),
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        });
    }
    if let Some(identity) = thinness
        && !matches!(identity.id, "fine" | "extra_fine")
    {
        gaps.push(ScoreFieldGap::UnsupportedMacroEmitIdentity {
            key: "thinness".to_owned(),
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        });
    }
    if let Some(identity) = relative_scale
        && CoreModifierValue::from_semantic_ref(identity.category, identity.id).is_none()
    {
        gaps.push(ScoreFieldGap::UnsupportedMacroEmitIdentity {
            key: "relative_scale".to_owned(),
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        });
    }
    if !gaps.is_empty() {
        return Err(gaps);
    }

    Ok(ScoreLoweringInput {
        fill_target: None,
        group_region: None,
        generated_position,
        generated_geometries,
        proportion_width_extent,
        proportion_arc_form,
        additional_relative_scales: &[],
        additional_explicit_geometries: &[],
        additional_width_extents: &[],
        shape_constraint,
        proportion_aspect,
        primitive: primitive.expect("required macro shape field checked"),
        count,
        color,
        color_cycle: &[],
        touch,
        continuity,
        surface,
        surface_intensity,
        thinness: thinness.map(|identity| match identity.id {
            "fine" => CoreModifierValue::Fine,
            "extra_fine" => CoreModifierValue::ExtraFine,
            _ => unreachable!("unsupported thinness identity checked"),
        }),
        action,
        numeric_position: None,
        has_named_position: place.is_some(),
        named_position: place,
        effective_focus: None,
        explicit_geometry: None,
        relative_scale: relative_scale.and_then(|identity| {
            CoreModifierValue::from_semantic_ref(identity.category, identity.id)
        }),
        angle,
        angle_context: None,
        layout_direction,
        fluctuation,
        ink_spread,
        has_unsupported_meaning: false,
    })
}

fn project_macro_anchor(
    fields: &BTreeMap<String, ExpandedMacroValue>,
    context: ScoreAngleContext<'_>,
) -> Result<AnchorPoint, Vec<ScoreFieldGap>> {
    if fields.is_empty() {
        return Err(vec![ScoreFieldGap::UnsupportedMacroStructure]);
    }
    let mut gaps = fields
        .keys()
        .filter(|key| !matches!(key.as_str(), "place" | "position_x" | "position_y"))
        .map(|key| ScoreFieldGap::UnknownMacroEmitField { key: key.clone() })
        .collect::<Vec<_>>();
    let place = macro_semantic_field(fields, "place", "place", false, &mut gaps);
    let numeric = macro_exact_pair(fields, "position_x", "position_y", &mut gaps);
    if place.is_some() == numeric.is_some() {
        gaps.push(ScoreFieldGap::NamedAndNumericPositionConflict);
    }
    if !gaps.is_empty() {
        return Err(gaps);
    }
    if let Some((x, y)) = numeric {
        let x = Rational::from_decimal(x).map_err(|gap| vec![gap])?;
        let y = Rational::from_decimal(y).map_err(|gap| vec![gap])?;
        if !x.in_unit_interval() || !y.in_unit_interval() {
            return Err(vec![ScoreFieldGap::PositionOutOfRange]);
        }
        return Ok(AnchorPoint {
            position: Some(Point::new(
                x.to_f64().map_err(|gap| vec![gap])?,
                y.to_f64().map_err(|gap| vec![gap])?,
            )),
            at: None,
        });
    }
    let place = place.expect("one explicit Anchor position was checked");
    let region = if place.id == "center" {
        [0.5, 0.5, 0.5, 0.5]
    } else {
        named_region_bounds(place.id, None, context)
            .ok_or_else(|| vec![ScoreFieldGap::UnsupportedNamedPosition])?
    };
    Ok(AnchorPoint {
        position: None,
        at: Some(AtRegion { region }),
    })
}

fn macro_exact_field(
    fields: &BTreeMap<String, ExpandedMacroValue>,
    key: &str,
    gaps: &mut Vec<ScoreFieldGap>,
) -> Option<ExactDecimal> {
    match fields.get(key) {
        None => None,
        Some(ExpandedMacroValue::ExactDecimal(value)) => Some(*value),
        Some(_) => {
            gaps.push(ScoreFieldGap::MacroEmitFieldTypeMismatch {
                key: key.to_owned(),
            });
            None
        }
    }
}

fn macro_exact_pair(
    fields: &BTreeMap<String, ExpandedMacroValue>,
    first: &str,
    second: &str,
    gaps: &mut Vec<ScoreFieldGap>,
) -> Option<(ExactDecimal, ExactDecimal)> {
    let a = macro_exact_field(fields, first, gaps);
    let b = macro_exact_field(fields, second, gaps);
    if fields.contains_key(first) != fields.contains_key(second) {
        gaps.push(ScoreFieldGap::MissingMacroEmitField {
            key: if fields.contains_key(first) {
                second
            } else {
                first
            }
            .to_owned(),
        });
    }
    a.zip(b)
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

/// Candidate evidence plus the selected policy, diagnostics, and actual Score outcome.
#[derive(Clone, Debug)]
pub struct ExplicitScoreLoweringResult<'a> {
    candidate: ScoreLoweringCandidate<'a>,
    context: ScoreLoweringContext,
    policy_digest: String,
    resolved_ground: Option<CanvasGroundSpec>,
    error_policy: ScoreErrorPolicy,
    outcome: ScoreLoweringOutcome,
    score: Option<Score>,
    anchors: Vec<AnchorPoint>,
    anchor_origins: Vec<ScoreAnchorOrigin>,
    instruction_origins: Vec<ScoreInstructionOrigin>,
    gaps: Vec<ScoreFieldGap>,
    diagnostics: Vec<ScoreLoweringDiagnostic>,
    placement_groups: Vec<PlacementGroupPlan>,
    fill_groups: Vec<FillGroupPlan>,
    standalone_macro_repetitions: Vec<PlacementMemberPlan>,
    mirror_relations: Vec<MirrorRelationPlan>,
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

    pub const fn error_policy(&self) -> ScoreErrorPolicy {
        self.error_policy
    }

    pub const fn outcome(&self) -> ScoreLoweringOutcome {
        self.outcome
    }

    pub const fn score(&self) -> Option<&Score> {
        self.score.as_ref()
    }

    pub fn instruction_origins(&self) -> &[ScoreInstructionOrigin] {
        &self.instruction_origins
    }

    pub fn anchors(&self) -> &[AnchorPoint] {
        &self.anchors
    }

    pub fn anchor_origins(&self) -> &[ScoreAnchorOrigin] {
        &self.anchor_origins
    }

    pub fn gaps(&self) -> &[ScoreFieldGap] {
        &self.gaps
    }

    pub fn diagnostics(&self) -> &[ScoreLoweringDiagnostic] {
        &self.diagnostics
    }
}

/// Exact source or generated owner for one instruction in a successful Score.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
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

/// Exact generated owner for one non-drawing Anchor in a successful Score.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ScoreAnchorOrigin {
    MacroAnchor {
        source_instruction_index: usize,
        target: GeneratedTargetId,
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
        .map(|(projected_index, instruction)| {
            let instruction_index = view
                .source_instruction_index(projected_index)
                .expect("verified Stage 1.5 view maps every projected instruction");
            lower_source_instruction(instruction_index, instruction)
        })
        .collect();
    ScoreLoweringCandidate {
        verified_effective_view: view,
        instructions,
    }
}

/// Lower with the default recoverable-error policy.
pub fn lower_verified_stage15_score<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
) -> ExplicitScoreLoweringResult<'a> {
    lower_verified_stage15_score_with_policy(view, context, ScoreErrorPolicy::default())
}

/// Lower with an explicit shared policy for ordinary instructions and macro expansions.
///
/// The legacy `Stop` value remains accepted, but recoverable failures retain
/// every independently drawable unit.
pub fn lower_verified_stage15_score_with_policy<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
) -> ExplicitScoreLoweringResult<'a> {
    lower_verified_stage15_shared(view, context, error_policy, None, None)
}

pub(crate) fn resolve_composition_plan<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
) -> CompositionPlanResult<'a> {
    let mut objects = Vec::new();
    let mut transform_groups = Vec::new();
    let result = lower_verified_stage15_shared(
        view,
        context,
        error_policy,
        Some(&mut objects),
        Some(&mut transform_groups),
    );
    let outcome = match result.outcome {
        ScoreLoweringOutcome::Stopped => CompositionPlanOutcome::Stopped,
        _ if !has_resolved_drawable_content(
            objects.len() + result.anchors.len(),
            result.resolved_ground.as_ref(),
            view.original_semantic_document().background.is_some(),
        ) =>
        {
            CompositionPlanOutcome::Stopped
        }
        ScoreLoweringOutcome::Complete => CompositionPlanOutcome::Ready,
        ScoreLoweringOutcome::CompleteWithOmissions => CompositionPlanOutcome::ReadyWithOmissions,
    };
    if outcome == CompositionPlanOutcome::Stopped {
        objects.clear();
        transform_groups.clear();
    }
    CompositionPlanResult {
        view,
        context: result.context,
        error_policy,
        policy_digest: result.policy_digest,
        outcome,
        objects,
        anchors: result.anchors,
        anchor_origins: result.anchor_origins,
        transform_groups,
        placement_groups: result.placement_groups,
        fill_groups: result.fill_groups,
        standalone_macro_repetitions: result.standalone_macro_repetitions,
        mirror_relations: result.mirror_relations,
        ground: result.resolved_ground,
        diagnostics: result.diagnostics,
    }
}

fn has_resolved_drawable_content(
    drawable_count: usize,
    resolved_ground: Option<&CanvasGroundSpec>,
    has_background: bool,
) -> bool {
    drawable_count != 0 || resolved_ground.is_some() || has_background
}

fn lower_verified_stage15_shared<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
    mut objects: Option<&mut Vec<ObjectPlacementPlan>>,
    mut transform_groups: Option<&mut Vec<TransformGroupPlan>>,
) -> ExplicitScoreLoweringResult<'a> {
    let candidate = lower_verified_stage15_view(view);
    let document = candidate
        .verified_effective_view()
        .original_semantic_document();
    let context = if let Some(background) = &document.background {
        let color: Color = serde_json::from_value(serde_json::Value::String(
            background.color.identity.id.clone(),
        ))
        .expect("typed background contains an accepted abstract color");
        ScoreLoweringContext {
            background: color,
            resolved_palette: context
                .resolved_palette
                .and_then(|palette| palette.select_background(color)),
            ..context
        }
    } else {
        context
    };
    let mut diagnostics = Vec::new();
    let mut score_transform_groups = Vec::new();
    let mut omitted_group_members = BTreeSet::new();
    let mut group_members = BTreeMap::new();
    let mut supported_groups = Vec::new();
    let mut supported_fill_groups = Vec::new();
    let mut standalone_fill_members = BTreeSet::new();
    let mut fill_groups = Vec::new();
    let mut fill_checkpoints = BTreeMap::new();
    let mut lowered_members = BTreeMap::new();
    let mut field_cycle_members = BTreeMap::new();
    let mut standalone_macro_repetitions = Vec::new();
    let mut supported_member_cycles = Vec::new();
    let mut mirror_relations = Vec::new();

    let ground =
        document.ground.as_ref().and_then(|ground| {
            match canvas_ground_spec_from_identity(&ground.identity) {
                Ok(spec) => Some(spec),
                Err(reason) => {
                    diagnostics.push(ScoreLoweringDiagnostic {
                        owner: ScoreDiagnosticOwner::Ground {
                            spans: vec![ground.provenance.source.span],
                        },
                        disposition: diagnostic_disposition(
                            error_policy,
                            &reason,
                            ScoreOmissionUnit::Ground,
                            None,
                        ),
                        reason,
                    });
                    None
                }
            }
        });
    for (projected_group_index, group) in document.coordinated_head_groups.iter().enumerate() {
        let group_index = candidate
            .verified_effective_view()
            .source_group_index(projected_group_index)
            .expect("verified Stage 1.5 view maps every projected group");
        let source_member_instruction_indices = group
            .member_instruction_indices
            .iter()
            .map(|index| {
                candidate
                    .verified_effective_view()
                    .source_instruction_index(*index)
                    .expect("verified Stage 1.5 view maps every group member")
            })
            .collect::<Vec<_>>();
        let mut spans = group
            .member_instruction_indices
            .iter()
            .filter_map(|index| document.instructions.get(*index))
            .map(|instruction| instruction.entity.head.source().span)
            .collect::<Vec<_>>();
        spans.extend(group.markers.iter().map(|marker| marker.span));
        if let Some(predicate) = document
            .group_predicates
            .iter()
            .find(|predicate| predicate.group_index == projected_group_index)
        {
            let focus = view
                .pending_focus_targets()
                .iter()
                .find_map(|target| match target.path {
                    Stage15TargetPath::GroupPredicate {
                        group_index: target_group,
                        ..
                    } if target_group == group_index => Some(target.effective_focus),
                    _ => None,
                });
            let action = predicate
                .action
                .as_ref()
                .map(|action| action.identity.id.as_str());
            if action == Some("fill") {
                let allocation = resolve_fill_group(view, group, predicate, focus, context);
                let reason = match allocation {
                    Ok(allocation) if objects.is_some() => {
                        for (&member, &count) in group
                            .member_instruction_indices
                            .iter()
                            .zip(&allocation.counts)
                        {
                            group_members.insert(member, ([0.5; 4], u64::from(count)));
                        }
                        supported_fill_groups.push((
                            FillPlanOwner::CoordinatedGroup { group_index },
                            source_member_instruction_indices,
                            allocation,
                        ));
                        continue;
                    }
                    Ok(_) => ScoreFieldGap::FillRequiresRegionMaterialization,
                    Err(reason) => reason,
                };
                omitted_group_members.extend(group.member_instruction_indices.iter().copied());
                diagnostics.push(ScoreLoweringDiagnostic {
                    owner: ScoreDiagnosticOwner::CoordinatedGroup {
                        group_index,
                        member_instruction_indices: source_member_instruction_indices.clone(),
                        spans,
                    },
                    disposition: diagnostic_disposition(
                        error_policy,
                        &reason,
                        ScoreOmissionUnit::CoordinatedGroup {
                            group_index,
                            member_instruction_indices: source_member_instruction_indices,
                        },
                        None,
                    ),
                    reason,
                });
                continue;
            }
            let counts = action.and_then(|action| {
                crate::group_quantity::coordinated_counts(
                    action,
                    &group
                        .member_instruction_indices
                        .iter()
                        .map(|&member| {
                            document.instructions[member]
                                .entity
                                .quantity
                                .as_ref()
                                .map(|quantity| quantity.value)
                        })
                        .collect::<Vec<_>>(),
                )
            });
            let bounds = crate::geometry::resolved_position_rational_bounds(
                predicate
                    .position
                    .as_ref()
                    .map(|position| position.identity.id.as_str()),
                focus,
                ScoreAngleContext {
                    composition_seed: view.composition_seed(),
                    original_pre_expansion_digest: view.original_pre_expansion_digest(),
                    original_expanded_meaning_digest: view.original_expanded_meaning_digest(),
                    occurrence: ScoreAngleOccurrence::Direct {
                        logical_ordinal: source_member_instruction_indices[0] as u64,
                    },
                },
            );
            if let (Some(counts), Some(bounds)) = (counts, bounds) {
                let region = bounds.map(|(n, d)| n as f64 / d as f64);
                let layout = match action.expect("allocated known action") {
                    "line_up" => inku_score::GroupLayout::HorizontalSourceOrder,
                    "scatter" => inku_score::GroupLayout::Scatter,
                    "tile" => inku_score::GroupLayout::Tile,
                    _ => match predicate.layout {
                        crate::GroupLayout::Overlap => inku_score::GroupLayout::Overlap,
                        crate::GroupLayout::HorizontalSourceOrder => {
                            inku_score::GroupLayout::HorizontalSourceOrder
                        }
                    },
                };
                for (&member, count) in group.member_instruction_indices.iter().zip(counts) {
                    group_members.insert(member, (region, count));
                }
                supported_groups.push((
                    group_index,
                    source_member_instruction_indices,
                    layout,
                    region,
                    bounds,
                ));
                continue;
            }
            spans.extend(
                predicate
                    .action
                    .iter()
                    .chain(predicate.position.iter())
                    .map(|term| term.provenance.source.span),
            );
        }
        omitted_group_members.extend(group.member_instruction_indices.iter().copied());
        let reason = ScoreFieldGap::UnsupportedCoordinatedGroup;
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: ScoreDiagnosticOwner::CoordinatedGroup {
                group_index,
                member_instruction_indices: source_member_instruction_indices.clone(),
                spans,
            },
            disposition: diagnostic_disposition(
                error_policy,
                &reason,
                ScoreOmissionUnit::CoordinatedGroup {
                    group_index,
                    member_instruction_indices: source_member_instruction_indices,
                },
                None,
            ),
            reason,
        });
    }

    for (owner_projected_index, instruction) in document.instructions.iter().enumerate() {
        let Some(sequence) = instruction.sequence.as_ref() else {
            continue;
        };
        let (members, member_count) = match sequence.kind {
            crate::SemanticSequenceKind::Color => continue,
            crate::SemanticSequenceKind::Field(_) => (
                SupportedCycleMembers::Field {
                    owner_projected_index,
                },
                sequence.items.len(),
            ),
            crate::SemanticSequenceKind::Units => (
                SupportedCycleMembers::Units(
                    sequence
                        .units
                        .iter()
                        .map(|unit| unit.member_entity_indices.clone())
                        .collect(),
                ),
                sequence.units.len(),
            ),
        };
        let Some(action_term) = instruction.action.as_ref() else {
            continue;
        };
        let action = match action_term.identity.id.as_str() {
            "place" => PlacementAction::Place,
            "line_up" => PlacementAction::LineUp,
            "scatter" => PlacementAction::Scatter,
            "tile" => PlacementAction::Tile,
            "fill" => PlacementAction::Fill,
            _ => continue,
        };
        let first_projected_index = match &members {
            SupportedCycleMembers::Field { .. } => owner_projected_index,
            SupportedCycleMembers::Units(units) => units
                .first()
                .and_then(|unit| unit.first())
                .copied()
                .unwrap_or(owner_projected_index),
        };
        let Some(first_source_index) = view.source_instruction_index(first_projected_index) else {
            continue;
        };
        let focus = direct_instruction_focus(view, first_source_index);
        let fill_region = if action == PlacementAction::Fill {
            let input = ScoreLoweringInput {
                fill_target: project_fill_target(view, instruction.fill_target.as_ref()),
                has_named_position: instruction.position.is_some(),
                named_position: instruction
                    .position
                    .as_ref()
                    .map(|term| (&term.identity).into()),
                effective_focus: focus,
                angle_context: Some(ScoreAngleContext {
                    composition_seed: view.composition_seed(),
                    original_pre_expansion_digest: view.original_pre_expansion_digest(),
                    original_expanded_meaning_digest: view.original_expanded_meaning_digest(),
                    occurrence: ScoreAngleOccurrence::Direct {
                        logical_ordinal: first_source_index as u64,
                    },
                }),
                ..ScoreLoweringInput::default()
            };
            let Ok(region) = resolve_fill_region(input, context) else {
                continue;
            };
            Some(region)
        } else {
            None
        };
        let bounds = if action == PlacementAction::Fill {
            None
        } else {
            let Some(bounds) = crate::geometry::resolved_position_rational_bounds(
                instruction
                    .position
                    .as_ref()
                    .map(|position| position.identity.id.as_str()),
                focus,
                ScoreAngleContext {
                    composition_seed: view.composition_seed(),
                    original_pre_expansion_digest: view.original_pre_expansion_digest(),
                    original_expanded_meaning_digest: view.original_expanded_meaning_digest(),
                    occurrence: ScoreAngleOccurrence::Direct {
                        logical_ordinal: first_source_index as u64,
                    },
                },
            ) else {
                continue;
            };
            Some(bounds)
        };
        let count = sequence
            .quantity
            .as_ref()
            .map(|quantity| quantity.value)
            .or(match action {
                PlacementAction::Scatter | PlacementAction::Tile => Some(8),
                PlacementAction::Place | PlacementAction::LineUp => Some(member_count as u64),
                PlacementAction::Fill => None,
            });
        if count == Some(0) {
            continue;
        }
        let region = bounds.map_or([0.5; 4], |bounds| {
            bounds.map(|(numerator, denominator)| numerator as f64 / denominator as f64)
        });
        match &members {
            SupportedCycleMembers::Field {
                owner_projected_index,
                ..
            } => {
                group_members.insert(*owner_projected_index, ([0.5; 4], 1));
            }
            SupportedCycleMembers::Units(units) => {
                for projected_index in units.iter().flatten().copied() {
                    group_members.insert(projected_index, ([0.5; 4], 1));
                }
            }
        }
        let (width, height) = context.canvas_format.integer_ratio();
        let short = width.min(height);
        let domain = [
            Rational::from_ratio(width.into(), short.into()).expect("valid canvas ratio"),
            Rational::from_ratio(height.into(), short.into()).expect("valid canvas ratio"),
        ];
        supported_member_cycles.push(SupportedMemberCycle {
            owner_projected_index,
            members,
            count,
            action,
            layout: match action {
                PlacementAction::Place => inku_score::GroupLayout::Overlap,
                PlacementAction::LineUp => inku_score::GroupLayout::HorizontalSourceOrder,
                PlacementAction::Scatter => inku_score::GroupLayout::Scatter,
                PlacementAction::Tile => inku_score::GroupLayout::Tile,
                PlacementAction::Fill => inku_score::GroupLayout::Overlap,
            },
            region,
            domain,
            fill_region,
        });
    }

    // Consume the standalone Macro caller's placement once, outside its intact
    // body. The body keeps its own actions, quantities, anchors and transforms.
    for (projected_index, instruction) in document.instructions.iter().enumerate() {
        if !matches!(instruction.entity.head, SemanticHead::MacroInvocation(_))
            || instruction
                .action
                .as_ref()
                .map(|term| term.identity.id.as_str())
                != Some("fill")
            || group_members.contains_key(&projected_index)
            || omitted_group_members.contains(&projected_index)
        {
            continue;
        }
        let source_index = view
            .source_instruction_index(projected_index)
            .expect("verified source");
        let prepared = prepare_single_macro_fill(view, source_index, instruction, context);
        let reason = match prepared {
            Ok(prepared) if objects.is_some() => {
                group_members.insert(projected_index, ([0.5; 4], u64::from(prepared.counts[0])));
                standalone_fill_members.insert(projected_index);
                supported_fill_groups.push((
                    FillPlanOwner::Instruction {
                        source_instruction_index: source_index,
                    },
                    vec![source_index],
                    prepared,
                ));
                continue;
            }
            Ok(_) => ScoreFieldGap::FillRequiresRegionMaterialization,
            Err(reason) => reason,
        };
        omitted_group_members.insert(projected_index);
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: source_owner_for_gap(source_index, instruction, &reason),
            disposition: diagnostic_disposition(
                error_policy,
                &reason,
                ScoreOmissionUnit::SourceInstruction {
                    instruction_index: source_index,
                },
                None,
            ),
            reason,
        });
    }

    let mut instructions = Vec::new();
    let mut anchors = Vec::new();
    let mut anchor_origins = Vec::new();
    let mut instruction_origins = Vec::new();
    for (projected_index, instruction) in document.instructions.iter().enumerate() {
        // An inline region operand supplies geometry; it is not an extra drawing.
        if document.instructions.iter().any(|owner| {
            matches!(owner.fill_target,
            Some(crate::SemanticFillTarget::InlineShape { target_instruction_index, .. })
                if target_instruction_index == projected_index)
        }) || document.group_predicates.iter().any(|owner| {
            matches!(owner.fill_target,
            Some(crate::SemanticFillTarget::InlineShape { target_instruction_index, .. })
                if target_instruction_index == projected_index)
        }) {
            let source_index = view
                .source_instruction_index(projected_index)
                .expect("verified view maps each region operand");
            if let Some(target_input) = project_source_instruction(
                view,
                source_index,
                instruction,
                direct_instruction_focus(view, source_index),
            ) && let Some(reason) = size_recovery_diagnostic(target_input, context)
            {
                diagnostics.push(ScoreLoweringDiagnostic {
                    owner: source_owner_for_gap(source_index, instruction, &reason),
                    disposition: ScoreDiagnosticDisposition::Recovered,
                    reason,
                });
            }
            continue;
        }
        if omitted_group_members.contains(&projected_index) {
            continue;
        }
        let instruction_index = candidate
            .verified_effective_view()
            .source_instruction_index(projected_index)
            .expect("verified Stage 1.5 view maps every projected instruction");
        let body_start = objects
            .as_ref()
            .map_or(instructions.len(), |objects| objects.len());
        let anchor_start = anchors.len();
        let transform_start = transform_groups
            .as_ref()
            .map_or(score_transform_groups.len(), |groups| groups.len());
        if let Some((group_index, _, _)) = supported_fill_groups
            .iter()
            .find(|(_, sources, _)| sources.first() == Some(&instruction_index))
        {
            fill_checkpoints.insert(*group_index, (body_start, anchor_start, transform_start));
        }
        if let Some(sequence) = instruction.sequence.as_ref()
            && let crate::SemanticSequenceKind::Field(field) = sequence.kind
            && let Some((region, _)) = group_members.get(&projected_index)
        {
            let effective_focus =
                direct_instruction_focus(candidate.verified_effective_view(), instruction_index);
            let mut members = Vec::new();
            let plan_relation = if let Some(objects) = objects.as_deref() {
                instruction
                    .relation
                    .as_ref()
                    .filter(|relation| relation.kind != SemanticRelationKind::Mirrored)
                    .and_then(|relation| {
                        match direct_score_relation(
                            instruction_index,
                            project_source_instruction(
                                candidate.verified_effective_view(),
                                instruction_index,
                                instruction,
                                effective_focus,
                            )
                            .expect("field cycle has a primitive source"),
                            relation,
                            objects
                                .last()
                                .map(|object| (object.primitive(), object.arc_form())),
                            objects.iter().map(|object| &object.origin),
                            objects.len().checked_sub(1),
                        ) {
                            Ok(relation) => Some(plan_relation(relation)),
                            Err(reason) => {
                                diagnostics.push(ScoreLoweringDiagnostic {
                                    owner: source_owner_for_gap(
                                        instruction_index,
                                        instruction,
                                        &reason,
                                    ),
                                    disposition: relation_diagnostic_disposition(),
                                    reason,
                                });
                                None
                            }
                        }
                    })
            } else {
                None
            };
            let score_relation = if objects.is_none() {
                instruction
                    .relation
                    .as_ref()
                    .filter(|relation| relation.kind != SemanticRelationKind::Mirrored)
                    .and_then(|relation| {
                        match direct_score_relation(
                            instruction_index,
                            project_source_instruction(
                                candidate.verified_effective_view(),
                                instruction_index,
                                instruction,
                                effective_focus,
                            )
                            .expect("field cycle has a primitive source"),
                            relation,
                            instructions
                                .last()
                                .map(|prior: &Instruction| (prior.primitive, prior.arc_form)),
                            instruction_origins.iter(),
                            instructions.len().checked_sub(1),
                        ) {
                            Ok(relation) => Some(relation),
                            Err(reason) => {
                                diagnostics.push(ScoreLoweringDiagnostic {
                                    owner: source_owner_for_gap(
                                        instruction_index,
                                        instruction,
                                        &reason,
                                    ),
                                    disposition: relation_diagnostic_disposition(),
                                    reason,
                                });
                                None
                            }
                        }
                    })
            } else {
                None
            };
            let mut complete = true;
            for item in &sequence.items {
                let member_start = objects
                    .as_ref()
                    .map_or(instructions.len(), |objects| objects.len());
                let mut member_instruction = instruction.clone();
                member_instruction.sequence = None;
                apply_sequence_field(&mut member_instruction, field, item.clone());
                let mut input = project_source_instruction(
                    candidate.verified_effective_view(),
                    instruction_index,
                    &member_instruction,
                    effective_focus,
                )
                .expect("field cycle has a primitive source");
                input.action = Some(SemanticInputIdentity {
                    category: "movement",
                    id: "place",
                });
                input.count = Some(1);
                input.has_named_position = true;
                input.group_region = Some(*region);
                if let Some(objects) = objects.as_deref_mut() {
                    let attempt = resolve_projected_instruction(
                        input,
                        context,
                        error_policy,
                        |input, context| {
                            resolve_object_plan(
                                input,
                                context,
                                ScoreInstructionOrigin::SourceInstruction { instruction_index },
                            )
                        },
                    );
                    let object_index = append_plan_attempt(
                        attempt,
                        |reason| {
                            source_owner_for_gap(instruction_index, &member_instruction, reason)
                        },
                        ScoreOmissionUnit::SourceInstruction { instruction_index },
                        error_policy,
                        objects,
                        &mut diagnostics,
                    );
                    let Some(index) = object_index else {
                        complete = false;
                        break;
                    };
                    objects[index].relation = plan_relation.clone();
                    objects[index].count_was_omitted = true;
                } else {
                    let before = instructions.len();
                    if let Some(relation) = score_relation.clone() {
                        lower_source_relation_instruction_with_policy(
                            instruction_index,
                            &member_instruction,
                            input,
                            relation,
                            context,
                            error_policy,
                            &mut instructions,
                            &mut instruction_origins,
                            &mut diagnostics,
                        );
                    } else {
                        lower_source_instruction_with_policy(
                            instruction_index,
                            &member_instruction,
                            input,
                            context,
                            error_policy,
                            &mut instructions,
                            &mut instruction_origins,
                            &mut diagnostics,
                        );
                    }
                    if instructions.len() == before {
                        complete = false;
                        break;
                    }
                }
                let member_end = objects
                    .as_ref()
                    .map_or(instructions.len(), |objects| objects.len());
                members.push(PlacementMemberPlan {
                    source_instruction_index: instruction_index,
                    source_instruction_indices: vec![instruction_index],
                    member: inku_score::PlacementMember {
                        start: member_start,
                        end: member_end,
                        anchor_indices: Vec::new(),
                        transform_group_indices: Vec::new(),
                        symbolic: None,
                    },
                    kind: PlacementMemberKind::Primitive,
                    source_count: 1,
                    count_was_omitted: true,
                });
            }
            if complete && members.len() == sequence.items.len() {
                field_cycle_members.insert(instruction_index, members);
            } else if let Some(objects) = objects.as_deref_mut() {
                objects.truncate(body_start);
            } else {
                instructions.truncate(body_start);
                instruction_origins.truncate(body_start);
            }
            continue;
        }
        match &instruction.entity.head {
            SemanticHead::Primitive(_) => {
                let effective_focus = direct_instruction_focus(
                    candidate.verified_effective_view(),
                    instruction_index,
                );
                let mut input = project_source_instruction(
                    candidate.verified_effective_view(),
                    instruction_index,
                    instruction,
                    effective_focus,
                )
                .expect("source projection is called only for primitive heads");
                if let Some((region, count)) = group_members.get(&projected_index) {
                    // The group alone owns action and target; members retain appearance
                    // and quantities while resolving geometry in a local Place recipe.
                    input.action = Some(SemanticInputIdentity {
                        category: "movement",
                        id: "place",
                    });
                    input.count = Some(*count);
                    input.has_named_position = true;
                    input.group_region = Some(*region);
                }
                if let Some(objects) = objects.as_deref_mut() {
                    let relation = instruction
                        .relation
                        .as_ref()
                        .filter(|relation| relation.kind != SemanticRelationKind::Mirrored)
                        .and_then(|relation| {
                            let resolved = direct_score_relation(
                                instruction_index,
                                input,
                                relation,
                                objects
                                    .last()
                                    .map(|object| (object.primitive(), object.arc_form())),
                                objects.iter().map(|object| &object.origin),
                                objects.len().checked_sub(1),
                            );
                            match resolved {
                                Ok(relation) => Some(plan_relation(relation)),
                                Err(reason) => {
                                    diagnostics.push(ScoreLoweringDiagnostic {
                                        owner: source_owner_for_gap(
                                            instruction_index,
                                            instruction,
                                            &reason,
                                        ),
                                        disposition: relation_diagnostic_disposition(),
                                        reason,
                                    });
                                    None
                                }
                            }
                        });
                    let attempt = resolve_projected_instruction(
                        input,
                        context,
                        error_policy,
                        |input, context| {
                            resolve_object_plan(
                                input,
                                context,
                                ScoreInstructionOrigin::SourceInstruction { instruction_index },
                            )
                        },
                    );
                    let object_index = append_plan_attempt(
                        attempt,
                        |reason| source_owner_for_gap(instruction_index, instruction, reason),
                        ScoreOmissionUnit::SourceInstruction { instruction_index },
                        error_policy,
                        objects,
                        &mut diagnostics,
                    );
                    if let Some(index) = object_index {
                        objects[index].relation = relation;
                        objects[index].count_was_omitted = instruction.entity.quantity.is_none();
                    }
                } else if let Some(relation) = instruction
                    .relation
                    .as_ref()
                    .filter(|relation| relation.kind != SemanticRelationKind::Mirrored)
                {
                    match direct_score_relation(
                        instruction_index,
                        input,
                        relation,
                        instructions
                            .last()
                            .map(|prior: &Instruction| (prior.primitive, prior.arc_form)),
                        instruction_origins.iter(),
                        instructions.len().checked_sub(1),
                    ) {
                        Ok(score_relation) => lower_source_relation_instruction_with_policy(
                            instruction_index,
                            instruction,
                            input,
                            score_relation,
                            context,
                            error_policy,
                            &mut instructions,
                            &mut instruction_origins,
                            &mut diagnostics,
                        ),
                        Err(reason) => {
                            diagnostics.push(ScoreLoweringDiagnostic {
                                owner: ScoreDiagnosticOwner::SourceInstruction {
                                    instruction_index,
                                    field: None,
                                    spans: vec![relation.provenance.span],
                                },
                                disposition: relation_diagnostic_disposition(),
                                reason,
                            });
                            lower_source_instruction_with_policy(
                                instruction_index,
                                instruction,
                                input,
                                context,
                                error_policy,
                                &mut instructions,
                                &mut instruction_origins,
                                &mut diagnostics,
                            );
                        }
                    }
                } else {
                    lower_source_instruction_with_policy(
                        instruction_index,
                        instruction,
                        input,
                        context,
                        error_policy,
                        &mut instructions,
                        &mut instruction_origins,
                        &mut diagnostics,
                    );
                }
            }
            SemanticHead::MacroInvocation(head) => {
                if let Some(relation) = instruction
                    .relation
                    .as_ref()
                    .filter(|relation| relation.kind != SemanticRelationKind::Mirrored)
                {
                    let reason = unsupported_relation_reason(instruction_index, relation);
                    diagnostics.push(ScoreLoweringDiagnostic {
                        owner: ScoreDiagnosticOwner::MacroInvocation {
                            source_instruction_index: instruction_index,
                            invocation_ordinal: head.provenance.ordinal,
                            field: None,
                            spans: vec![relation.provenance.span, head.provenance.source.span],
                        },
                        disposition: relation_diagnostic_disposition(),
                        reason,
                    });
                }
                let mut body_caller;
                let body_instruction = if standalone_fill_members.contains(&projected_index)
                    || group_members.contains_key(&projected_index)
                {
                    body_caller = instruction.clone();
                    body_caller.action = None;
                    body_caller.position = None;
                    body_caller.fill_target = None;
                    body_caller.sequence = None;
                    &body_caller
                } else {
                    instruction
                };
                lower_macro_instruction(
                    candidate.verified_effective_view(),
                    instruction_index,
                    body_instruction,
                    head,
                    group_members.get(&projected_index).map(|(_, count)| *count),
                    context,
                    error_policy,
                    &mut instructions,
                    &mut anchors,
                    &mut anchor_origins,
                    &mut instruction_origins,
                    &mut diagnostics,
                    objects.as_deref_mut(),
                    transform_groups.as_deref_mut(),
                    &mut score_transform_groups,
                );
            }
        }
        let body_end = objects
            .as_ref()
            .map_or(instructions.len(), |objects| objects.len());
        let transform_end = transform_groups
            .as_ref()
            .map_or(score_transform_groups.len(), |groups| groups.len());
        if let Some((_, count)) = group_members.get(&projected_index)
            && (body_start < body_end || anchor_start < anchors.len())
        {
            lowered_members.insert(
                instruction_index,
                PlacementMemberPlan {
                    source_instruction_index: instruction_index,
                    source_instruction_indices: vec![instruction_index],
                    member: inku_score::PlacementMember {
                        start: body_start,
                        end: body_end,
                        anchor_indices: (anchor_start..anchors.len()).collect(),
                        transform_group_indices: (transform_start..transform_end).collect(),
                        symbolic: None,
                    },
                    kind: match instruction.entity.head {
                        SemanticHead::Primitive(_) => PlacementMemberKind::Primitive,
                        SemanticHead::MacroInvocation(_) => PlacementMemberKind::Macro,
                    },
                    source_count: u32::try_from(*count)
                        .expect("successful source count was validated"),
                    count_was_omitted: instruction.entity.quantity.is_none(),
                },
            );
        } else if objects.is_some()
            && matches!(instruction.entity.head, SemanticHead::MacroInvocation(_))
            && (body_start < body_end || anchor_start < anchors.len())
        {
            // Count one still owns a complete body, including Anchor-only macros.
            // Preserve that envelope for saved-Score resource accounting and replay.
            let quantity = instruction.entity.quantity.as_ref();
            standalone_macro_repetitions.push(PlacementMemberPlan {
                source_instruction_index: instruction_index,
                source_instruction_indices: vec![instruction_index],
                member: inku_score::PlacementMember {
                    start: body_start,
                    end: body_end,
                    anchor_indices: (anchor_start..anchors.len()).collect(),
                    transform_group_indices: (transform_start..transform_end).collect(),
                    symbolic: None,
                },
                kind: PlacementMemberKind::Macro,
                source_count: u32::try_from(quantity.map_or(1, |value| value.value))
                    .expect("successful source count was validated"),
                count_was_omitted: quantity.is_none(),
            });
        }
        if let Some(group_slot) = supported_fill_groups
            .iter()
            .position(|(_, sources, _)| sources.last() == Some(&instruction_index))
        {
            let (group_index, sources, prepared) = supported_fill_groups.remove(group_slot);
            let checkpoint = fill_checkpoints
                .remove(&group_index)
                .expect("source-ordered fill group has a start checkpoint");
            let members = sources
                .iter()
                .filter_map(|source| lowered_members.remove(source))
                .collect();
            let planned = finalize_fill_group(
                group_index,
                prepared,
                members,
                objects.as_deref_mut().expect("fill groups are symbolic"),
                transform_groups
                    .as_ref()
                    .map_or(&[][..], |groups| groups.as_slice()),
                &anchors,
                context.canvas_format,
            );
            match planned {
                Ok(group) => fill_groups.push(group),
                Err(reason) => {
                    // This group is still the tail: recover before the next source
                    // instruction, so previous owners/indices never need rewriting.
                    objects.as_deref_mut().unwrap().truncate(checkpoint.0);
                    anchors.truncate(checkpoint.1);
                    anchor_origins.truncate(checkpoint.1);
                    if let Some(transforms) = transform_groups.as_deref_mut() {
                        transforms.truncate(checkpoint.2);
                    }
                    let spans = document
                        .instructions
                        .iter()
                        .enumerate()
                        .filter_map(|(index, instruction)| {
                            sources
                                .contains(&view.source_instruction_index(index)?)
                                .then_some(instruction.entity.head.source().span)
                        })
                        .collect();
                    let (owner, unit) = match group_index {
                        FillPlanOwner::CoordinatedGroup { group_index } => (
                            ScoreDiagnosticOwner::CoordinatedGroup {
                                group_index,
                                member_instruction_indices: sources.clone(),
                                spans,
                            },
                            ScoreOmissionUnit::CoordinatedGroup {
                                group_index,
                                member_instruction_indices: sources,
                            },
                        ),
                        FillPlanOwner::Instruction {
                            source_instruction_index,
                        } => (
                            ScoreDiagnosticOwner::SourceInstruction {
                                instruction_index: source_instruction_index,
                                field: None,
                                spans,
                            },
                            ScoreOmissionUnit::SourceInstruction {
                                instruction_index: source_instruction_index,
                            },
                        ),
                    };
                    diagnostics.push(ScoreLoweringDiagnostic {
                        owner,
                        disposition: diagnostic_disposition(error_policy, &reason, unit, None),
                        reason,
                    });
                }
            }
        }
    }

    let mut placement_groups = Vec::new();
    for cycle in supported_member_cycles {
        let mut members = Vec::new();
        let mut complete = true;
        let cycle_units = match cycle.members {
            SupportedCycleMembers::Units(units) => units,
            SupportedCycleMembers::Field {
                owner_projected_index,
                ..
            } => {
                let Some(source_index) = view.source_instruction_index(owner_projected_index)
                else {
                    continue;
                };
                let Some(field_members) = field_cycle_members.remove(&source_index) else {
                    continue;
                };
                members.extend(field_members);
                Vec::new()
            }
        };
        for unit in &cycle_units {
            let mut parts = Vec::new();
            for &projected_index in unit {
                let Some(source_index) = view.source_instruction_index(projected_index) else {
                    complete = false;
                    break;
                };
                let Some(member) = lowered_members.remove(&source_index) else {
                    complete = false;
                    break;
                };
                parts.push(member);
            }
            if !complete || parts.is_empty() {
                break;
            }
            for part in &parts {
                if part.kind == PlacementMemberKind::Primitive {
                    if let Some(objects) = objects.as_deref_mut() {
                        objects[part.member.start].anchor = ObjectAnchor::Named([0.5; 4]);
                    } else {
                        instructions[part.member.start].at = Some(AtRegion { region: [0.5; 4] });
                    }
                }
            }
            if parts.len() == 1 {
                members.push(parts.remove(0));
                continue;
            }
            let source_instruction_indices = parts
                .iter()
                .flat_map(|member| member.source_instruction_indices.iter().copied())
                .collect::<Vec<_>>();
            members.push(PlacementMemberPlan {
                source_instruction_index: source_instruction_indices[0],
                source_instruction_indices,
                member: inku_score::PlacementMember {
                    start: parts[0].member.start,
                    end: parts.last().expect("ordinary group has members").member.end,
                    anchor_indices: parts
                        .iter()
                        .flat_map(|member| member.member.anchor_indices.iter().copied())
                        .collect(),
                    transform_group_indices: parts
                        .iter()
                        .flat_map(|member| member.member.transform_group_indices.iter().copied())
                        .collect(),
                    symbolic: None,
                },
                kind: PlacementMemberKind::OrdinaryGroup,
                source_count: 1,
                count_was_omitted: true,
            });
        }
        if !complete || members.is_empty() {
            continue;
        }
        let start = members[0].member.start;
        let end = members.last().expect("member cycle is nonempty").member.end;
        let group_index = document.coordinated_head_groups.len() + cycle.owner_projected_index;
        if cycle.action == PlacementAction::Fill {
            let Some(region) = cycle.fill_region else {
                continue;
            };
            let (occurrence_count, count_resolution) = if let Some(count) = cycle.count {
                (count, FillCountResolution::Explicit)
            } else {
                let Some(plan_objects) = objects.as_deref() else {
                    continue;
                };
                let plan_transforms = transform_groups
                    .as_ref()
                    .map_or(&[][..], |groups| groups.as_slice());
                let extents = members
                    .iter()
                    .map(|member| match member.kind {
                        PlacementMemberKind::Primitive => {
                            reference_extent(plan_objects[member.member.start].dimensions)
                        }
                        PlacementMemberKind::Macro | PlacementMemberKind::OrdinaryGroup => {
                            crate::plan_reference_extent::reference_member_extent(
                                plan_objects,
                                plan_transforms,
                                &anchors,
                                member,
                                context.canvas_format,
                            )
                        }
                    })
                    .collect::<Result<Vec<_>, _>>();
                let Ok(extents) = extents else {
                    continue;
                };
                let explicit_counts = vec![None; members.len()];
                let Ok(counts) =
                    balanced_fill_counts(region.reference_area, &extents, &explicit_counts)
                else {
                    continue;
                };
                let occurrence_count = counts.iter().map(|count| u64::from(*count)).sum();
                (
                    occurrence_count,
                    FillCountResolution::BalancedGroup {
                        reference_extents: extents,
                        explicit_counts,
                    },
                )
            };
            fill_groups.push(FillGroupPlan {
                owner: FillPlanOwner::CoordinatedGroup { group_index },
                logical_count: occurrence_count,
                members,
                recipe: PlacementRecipe::FillUniformInRegionAndClip {
                    region: Box::new(region),
                    count_resolution,
                },
                cycle_occurrence_count: Some(occurrence_count),
            });
            continue;
        }
        let count = cycle.count.expect("non-fill cycles resolve an outer count");
        let recipe = placement_recipe(cycle.action, count, cycle.domain, None, false)
            .expect("bounded member cycle recipe");
        placement_groups.push(PlacementGroupPlan {
            group_index,
            placement: inku_score::PlacementGroup {
                start,
                end,
                layout: cycle.layout,
                at: AtRegion {
                    region: cycle.region,
                },
                members: members.iter().map(|member| member.member.clone()).collect(),
                resolved: None,
                cycle_members: None,
            },
            logical_count: count,
            domain: cycle.domain,
            recipe,
            members,
            cycle_occurrence_count: Some(count),
        });
    }
    for (group_index, members, layout, region, bounds) in supported_groups {
        let members = members
            .iter()
            .filter_map(|source| lowered_members.remove(source))
            .collect::<Vec<_>>();
        let (Some(first), Some(last)) = (members.first(), members.last()) else {
            continue;
        };
        let start = first.member.start;
        let end = last.member.end;
        let logical_count = members
            .iter()
            .map(|member| u64::from(member.logical_count()))
            .sum();
        let (width, height) = context.canvas_format.integer_ratio();
        let short = width.min(height);
        let mut domain = [
            Rational::from_ratio(width.into(), short.into()).expect("valid canvas ratio"),
            Rational::from_ratio(height.into(), short.into()).expect("valid canvas ratio"),
        ];
        if layout == inku_score::GroupLayout::Tile {
            for axis in 0..2 {
                let (end_n, end_d) = bounds[axis + 2];
                let (start_n, start_d) = bounds[axis];
                let extent = Rational::from_ratio(end_n.into(), end_d.into())
                    .unwrap()
                    .sub(Rational::from_ratio(start_n.into(), start_d.into()).unwrap())
                    .unwrap();
                domain[axis] = domain[axis].mul(extent).unwrap();
            }
        }
        let recipe = placement_recipe(
            match layout {
                inku_score::GroupLayout::Overlap => PlacementAction::Place,
                inku_score::GroupLayout::HorizontalSourceOrder => PlacementAction::LineUp,
                inku_score::GroupLayout::Scatter => PlacementAction::Scatter,
                inku_score::GroupLayout::Tile => PlacementAction::Tile,
            },
            logical_count,
            domain,
            None,
            false,
        )
        .expect("bounded validated group recipe");
        // These are local coordinates; only the group carries the semantic focus.
        for member in &members {
            if member.kind == PlacementMemberKind::Primitive {
                if let Some(objects) = objects.as_deref_mut() {
                    objects[member.member.start].anchor = ObjectAnchor::Named([0.5; 4]);
                } else {
                    instructions[member.member.start].at = Some(AtRegion { region: [0.5; 4] });
                }
            }
        }
        let score_members = if members
            .iter()
            .any(|member| member.kind == PlacementMemberKind::Macro)
        {
            members.iter().map(|member| member.member.clone()).collect()
        } else {
            Vec::new()
        };
        placement_groups.push(PlacementGroupPlan {
            group_index,
            logical_count,
            domain,
            recipe,
            members,
            cycle_occurrence_count: None,
            placement: inku_score::PlacementGroup {
                start,
                end,
                layout,
                at: AtRegion { region },
                members: score_members,
                cycle_members: None,
                resolved: None,
            },
        });
    }
    if let Some(plan_objects) = objects.as_deref() {
        mirror_relations = collect_mirror_relation_plans(
            view,
            document,
            plan_objects,
            &placement_groups,
            &standalone_macro_repetitions,
            &mut diagnostics,
        );
    } else {
        append_unmaterialized_mirror_diagnostics(view, document, &mut diagnostics);
    }
    let stopped = diagnostics
        .iter()
        .any(|diagnostic| matches!(diagnostic.disposition, ScoreDiagnosticDisposition::Stopped));
    let omitted = diagnostics.iter().any(|diagnostic| {
        matches!(
            diagnostic.disposition,
            ScoreDiagnosticDisposition::Omitted { .. }
                | ScoreDiagnosticDisposition::RelationOmitted
        )
    });
    let has_drawable_content = has_resolved_drawable_content(
        objects
            .as_ref()
            .map_or(instructions.len(), |objects| objects.len()),
        ground.as_ref(),
        document.background.is_some(),
    );
    let outcome = if stopped || (omitted && !has_drawable_content) {
        ScoreLoweringOutcome::Stopped
    } else if omitted {
        ScoreLoweringOutcome::CompleteWithOmissions
    } else {
        ScoreLoweringOutcome::Complete
    };
    let score = (objects.is_none() && outcome != ScoreLoweringOutcome::Stopped).then(|| Score {
        version: if instructions.iter().any(|instruction| {
            instruction.relation.as_ref().is_some_and(|relation| {
                matches!(
                    relation.target_path_position,
                    Some(inku_score::TargetPathPosition::Selection(
                        inku_score::TargetPathSelection::Interior
                    ))
                )
            })
        }) {
            "0.13.0".to_owned()
        } else if instructions.iter().any(|instruction| {
            instruction.ink_spread.is_some()
                || instruction
                    .relation
                    .as_ref()
                    .is_some_and(|relation| relation.target_endpoint.is_some())
        }) {
            "0.12.0".to_owned()
        } else if instructions.iter().any(|instruction| {
            instruction
                .relation
                .as_ref()
                .is_some_and(|relation| relation.target_path_position.is_some())
        }) {
            "0.11.0".to_owned()
        } else {
            score_wire_version()
        },
        canvas: ground.clone().map_or_else(
            || Canvas::Id(context.canvas_format.id.to_owned()),
            |ground| {
                Canvas::Spec(CanvasSpec {
                    aspect: context.canvas_format.id.to_owned(),
                    ground: Some(ground),
                })
            },
        ),
        background: context.background,
        presence: None,
        instructions,
        anchors: anchors.clone(),
        transform_groups: score_transform_groups,
        placement_groups: placement_groups
            .iter()
            .map(|group| group.placement.clone())
            .collect(),
        repetition_groups: Vec::new(),
        fill_groups: Vec::new(),
        mirror_relations: Vec::new(),
        resource_policy: None,
    });
    if score.is_none() {
        instruction_origins.clear();
    }
    let gaps = diagnostics
        .iter()
        .map(|diagnostic| diagnostic.reason.clone())
        .collect();
    ExplicitScoreLoweringResult {
        candidate,
        context,
        policy_digest: geometry_resolution_policy_digest(),
        resolved_ground: ground,
        error_policy,
        outcome,
        score,
        anchors,
        anchor_origins,
        instruction_origins,
        gaps,
        diagnostics,
        placement_groups,
        fill_groups,
        standalone_macro_repetitions,
        mirror_relations,
    }
}

#[derive(Clone)]
struct PlannedMirrorBody {
    source_instruction_indices: Vec<usize>,
    object_indices: Vec<usize>,
    reference: MirrorBodyPlanRef,
}

impl PlannedMirrorBody {
    fn first_source_index(&self) -> usize {
        self.source_instruction_indices[0]
    }
}

struct PendingMirrorRelation<'a> {
    follower_source_index: usize,
    expected_target_source_index: usize,
    follower_group_index: Option<usize>,
    relation: &'a SemanticRelation,
}

fn collect_mirror_relation_plans(
    view: VerifiedStage15EffectiveView<'_>,
    document: &crate::SemanticDocumentAst,
    objects: &[ObjectPlacementPlan],
    placement_groups: &[PlacementGroupPlan],
    standalone_macros: &[PlacementMemberPlan],
    diagnostics: &mut Vec<ScoreLoweringDiagnostic>,
) -> Vec<MirrorRelationPlan> {
    let bodies = planned_mirror_bodies(objects, placement_groups, standalone_macros);
    let mut pending = Vec::new();
    for (projected_index, instruction) in document.instructions.iter().enumerate() {
        let Some(relation) = instruction
            .relation
            .as_ref()
            .filter(|relation| relation.kind == SemanticRelationKind::Mirrored)
        else {
            continue;
        };
        let Some(target_projected_index) = projected_index.checked_sub(1) else {
            continue;
        };
        let Some(follower_source_index) = view.source_instruction_index(projected_index) else {
            continue;
        };
        let Some(expected_target_source_index) =
            view.source_instruction_index(target_projected_index)
        else {
            continue;
        };
        pending.push(PendingMirrorRelation {
            follower_source_index,
            expected_target_source_index,
            follower_group_index: None,
            relation,
        });
    }
    for predicate in &document.group_predicates {
        let Some(relation) = predicate
            .relation
            .as_ref()
            .filter(|relation| relation.kind == SemanticRelationKind::Mirrored)
        else {
            continue;
        };
        let group = &document.coordinated_head_groups[predicate.group_index];
        let Some(&first_projected_index) = group.member_instruction_indices.first() else {
            continue;
        };
        let Some(target_projected_index) = first_projected_index.checked_sub(1) else {
            continue;
        };
        let Some(follower_source_index) = group
            .member_instruction_indices
            .last()
            .and_then(|index| view.source_instruction_index(*index))
        else {
            continue;
        };
        let Some(expected_target_source_index) =
            view.source_instruction_index(target_projected_index)
        else {
            continue;
        };
        let Some(follower_group_index) = view.source_group_index(predicate.group_index) else {
            continue;
        };
        pending.push(PendingMirrorRelation {
            follower_source_index,
            expected_target_source_index,
            follower_group_index: Some(follower_group_index),
            relation,
        });
    }

    let mut plans = Vec::new();
    for pending in pending {
        let follower = if let Some(group_index) = pending.follower_group_index {
            bodies.iter().find(|body| {
                matches!(
                    body.reference,
                    MirrorBodyPlanRef::PlacementGroup { group_index: candidate }
                        if placement_groups[candidate].group_index() == group_index
                )
            })
        } else {
            bodies.iter().find(|body| {
                body.source_instruction_indices
                    .contains(&pending.follower_source_index)
            })
        };
        let target = bodies.iter().find(|body| {
            body.source_instruction_indices
                .contains(&pending.expected_target_source_index)
        });
        let (Some(target), Some(follower)) = (target, follower) else {
            diagnostics.push(mirror_relation_diagnostic(
                pending.follower_source_index,
                pending.expected_target_source_index,
                pending.relation,
            ));
            continue;
        };
        let target_primitives = target
            .object_indices
            .iter()
            .map(|&index| objects[index].primitive())
            .collect::<Vec<_>>();
        let follower_primitives = follower
            .object_indices
            .iter()
            .map(|&index| objects[index].primitive())
            .collect::<Vec<_>>();
        if target_primitives != follower_primitives || target_primitives.is_empty() {
            diagnostics.push(mirror_relation_diagnostic(
                pending.follower_source_index,
                pending.expected_target_source_index,
                pending.relation,
            ));
            continue;
        }
        let whole_body_fixed = !matches!(follower.reference, MirrorBodyPlanRef::Object { .. });
        let dimensions_fixed = follower
            .object_indices
            .iter()
            .any(|&index| mirror_dimensions_fixed(&objects[index], whole_body_fixed));
        let direction_degrees =
            if matches!(follower.reference, MirrorBodyPlanRef::PlacementGroup { .. }) {
                None
            } else {
                resolved_mirror_follower_direction(
                    view,
                    document,
                    pending.follower_source_index,
                    follower,
                    objects,
                )
            };
        plans.push(MirrorRelationPlan {
            owner: ScoreInstructionOrigin::SourceInstruction {
                instruction_index: pending.follower_source_index,
            },
            target: target.reference.clone(),
            follower: follower.reference.clone(),
            follower_facts: inku_score::MirrorFollowerFactsV1 {
                dimensions_fixed,
                direction_degrees,
            },
        });
    }
    plans
}

fn planned_mirror_bodies(
    objects: &[ObjectPlacementPlan],
    placement_groups: &[PlacementGroupPlan],
    standalone_macros: &[PlacementMemberPlan],
) -> Vec<PlannedMirrorBody> {
    let mut covered_objects = BTreeSet::new();
    let mut bodies = Vec::new();
    for (group_index, group) in placement_groups.iter().enumerate() {
        let mut sources = group
            .members()
            .iter()
            .flat_map(|member| member.source_instruction_indices().iter().copied())
            .collect::<Vec<_>>();
        sources.sort_unstable();
        sources.dedup();
        let object_indices = (group.placement().start..group.placement().end).collect::<Vec<_>>();
        covered_objects.extend(object_indices.iter().copied());
        if !sources.is_empty() && !object_indices.is_empty() {
            bodies.push(PlannedMirrorBody {
                source_instruction_indices: sources,
                object_indices,
                reference: MirrorBodyPlanRef::PlacementGroup { group_index },
            });
        }
    }
    for (member_index, member) in standalone_macros.iter().enumerate() {
        let object_indices = (member.member().start..member.member().end).collect::<Vec<_>>();
        covered_objects.extend(object_indices.iter().copied());
        if !object_indices.is_empty() {
            bodies.push(PlannedMirrorBody {
                source_instruction_indices: member.source_instruction_indices().to_vec(),
                object_indices,
                reference: MirrorBodyPlanRef::StandaloneMacro { member_index },
            });
        }
    }
    for (object_index, object) in objects.iter().enumerate() {
        if covered_objects.contains(&object_index) {
            continue;
        }
        let source_instruction_index = match object.origin() {
            ScoreInstructionOrigin::SourceInstruction { instruction_index } => *instruction_index,
            ScoreInstructionOrigin::MacroEmit {
                source_instruction_index,
                ..
            } => *source_instruction_index,
        };
        bodies.push(PlannedMirrorBody {
            source_instruction_indices: vec![source_instruction_index],
            object_indices: vec![object_index],
            reference: MirrorBodyPlanRef::Object { object_index },
        });
    }
    bodies.sort_by_key(PlannedMirrorBody::first_source_index);
    bodies
}

fn mirror_dimensions_fixed(object: &ObjectPlacementPlan, whole_body_fixed: bool) -> bool {
    whole_body_fixed
        || matches!(object.origin(), ScoreInstructionOrigin::MacroEmit { .. })
        || !object.generated_geometries().is_empty()
        || object.explicit_geometry().is_some()
        || object.relative_scale().is_some()
        || object.proportion_width_extent().is_some()
        || !object.additional_relative_scales().is_empty()
        || !object.additional_explicit_geometries().is_empty()
        || !object.additional_width_extents().is_empty()
        || object.shape_constraint().is_some()
        || object.proportion_aspect().is_some()
}

fn resolved_mirror_follower_direction(
    view: VerifiedStage15EffectiveView<'_>,
    document: &crate::SemanticDocumentAst,
    source_instruction_index: usize,
    follower: &PlannedMirrorBody,
    objects: &[ObjectPlacementPlan],
) -> Option<f64> {
    if let MirrorBodyPlanRef::Object { object_index } = follower.reference {
        return objects[object_index].angle();
    }
    let (_, instruction) =
        document
            .instructions
            .iter()
            .enumerate()
            .find(|(projected_index, _)| {
                view.source_instruction_index(*projected_index) == Some(source_instruction_index)
            })?;
    let angle = instruction.entity.angle.as_ref()?;
    resolve_score_angle(
        &angle.identity.id,
        ScoreAngleContext {
            composition_seed: view.composition_seed(),
            original_pre_expansion_digest: view.original_pre_expansion_digest(),
            original_expanded_meaning_digest: view.original_expanded_meaning_digest(),
            occurrence: ScoreAngleOccurrence::Direct {
                logical_ordinal: source_instruction_index as u64,
            },
        },
    )
    .filter(|value| value.is_finite())
}

fn mirror_relation_diagnostic(
    follower_source_index: usize,
    target_source_index: usize,
    relation: &SemanticRelation,
) -> ScoreLoweringDiagnostic {
    let reason = ScoreFieldGap::UnsupportedRelation {
        kind: relation.kind,
        reference: relation.reference,
        dependency_instruction_indices: vec![target_source_index],
    };
    ScoreLoweringDiagnostic {
        owner: ScoreDiagnosticOwner::SourceInstruction {
            instruction_index: follower_source_index,
            field: None,
            spans: vec![relation.provenance.span],
        },
        disposition: relation_diagnostic_disposition(),
        reason,
    }
}

fn append_unmaterialized_mirror_diagnostics(
    view: VerifiedStage15EffectiveView<'_>,
    document: &crate::SemanticDocumentAst,
    diagnostics: &mut Vec<ScoreLoweringDiagnostic>,
) {
    for (projected_index, instruction) in document.instructions.iter().enumerate() {
        let Some(relation) = instruction
            .relation
            .as_ref()
            .filter(|relation| relation.kind == SemanticRelationKind::Mirrored)
        else {
            continue;
        };
        let Some(follower) = view.source_instruction_index(projected_index) else {
            continue;
        };
        let target = projected_index
            .checked_sub(1)
            .and_then(|index| view.source_instruction_index(index))
            .unwrap_or(follower);
        diagnostics.push(mirror_relation_diagnostic(follower, target, relation));
    }
    // A coordinated group owns its mirror through a group predicate; it is
    // diagnosed with the same follower and target as the materialized path.
    for predicate in &document.group_predicates {
        let Some(relation) = predicate
            .relation
            .as_ref()
            .filter(|relation| relation.kind == SemanticRelationKind::Mirrored)
        else {
            continue;
        };
        let members =
            &document.coordinated_head_groups[predicate.group_index].member_instruction_indices;
        let Some(follower) = members
            .last()
            .and_then(|index| view.source_instruction_index(*index))
        else {
            continue;
        };
        let target = members
            .first()
            .and_then(|index| index.checked_sub(1))
            .and_then(|index| view.source_instruction_index(index))
            .unwrap_or(follower);
        diagnostics.push(mirror_relation_diagnostic(follower, target, relation));
    }
}

fn relation_dependency_instruction_indices(
    instruction_index: usize,
    reference: SemanticPreviousReference,
) -> Vec<usize> {
    let required = match reference {
        SemanticPreviousReference::PreviousOne => 1,
        SemanticPreviousReference::PreviousTwo => 2,
    };
    instruction_index
        .checked_sub(required)
        .map_or_else(Vec::new, |first| (first..instruction_index).collect())
}

fn unsupported_relation_reason(
    instruction_index: usize,
    relation: &SemanticRelation,
) -> ScoreFieldGap {
    ScoreFieldGap::UnsupportedRelation {
        kind: relation.kind,
        reference: relation.reference,
        dependency_instruction_indices: relation_dependency_instruction_indices(
            instruction_index,
            relation.reference,
        ),
    }
}

fn direct_score_relation<'a>(
    instruction_index: usize,
    input: ScoreLoweringInput<'_>,
    relation: &SemanticRelation,
    prior: Option<(Primitive, Option<inku_score::ArcForm>)>,
    instruction_origins: impl DoubleEndedIterator<Item = &'a ScoreInstructionOrigin>,
    target_instruction_index: Option<usize>,
) -> Result<Relation, ScoreFieldGap> {
    let expected_reference = if relation.kind == SemanticRelationKind::Between {
        SemanticPreviousReference::PreviousTwo
    } else {
        SemanticPreviousReference::PreviousOne
    };
    if relation.reference != expected_reference {
        return Err(unsupported_relation_reason(instruction_index, relation));
    }

    let required = match relation.reference {
        SemanticPreviousReference::PreviousOne => 1,
        SemanticPreviousReference::PreviousTwo => 2,
    };
    let dependency_instruction_indices =
        relation_dependency_instruction_indices(instruction_index, relation.reference);
    if dependency_instruction_indices.len() != required {
        return Err(ScoreFieldGap::UnavailableRelationReference {
            kind: relation.kind,
            reference: relation.reference,
            dependency_instruction_indices: Vec::new(),
        });
    }
    let prior_origins = instruction_origins.rev().take(required).collect::<Vec<_>>();
    let actual_dependencies_match = {
        let origins = &prior_origins;
        origins.len() == required
            && origins
                .iter()
                .rev()
                .zip(&dependency_instruction_indices)
                .all(|(origin, expected_index)| {
                    matches!(
                        origin,
                        ScoreInstructionOrigin::SourceInstruction { instruction_index }
                            if instruction_index == expected_index
                    )
                })
    };
    if !actual_dependencies_match {
        return Err(ScoreFieldGap::UnavailableRelationReference {
            kind: relation.kind,
            reference: relation.reference,
            dependency_instruction_indices,
        });
    }
    let kind = match relation.kind {
        SemanticRelationKind::NotTouching => RelationType::NotTouching,
        SemanticRelationKind::Between => RelationType::Between,
        SemanticRelationKind::Connected => RelationType::Connected,
        SemanticRelationKind::Touching => RelationType::Touching,
        SemanticRelationKind::Along => RelationType::Along,
        SemanticRelationKind::Cutting => RelationType::Cutting,
        SemanticRelationKind::Mirrored => {
            return Err(unsupported_relation_reason(instruction_index, relation));
        }
    };
    let mut checked = checked_object_relation(
        kind,
        input,
        target_instruction_index.expect("verified original dependency has a delivered target"),
        prior,
    )
    .ok_or_else(|| unsupported_relation_reason(instruction_index, relation))?;
    if (relation.target_endpoint.is_some() || relation.target_path_selection.is_some())
        && (relation.target_endpoint.is_some() && relation.target_path_selection.is_some()
            || kind != RelationType::Connected
            || !prior.is_some_and(|(primitive, _)| {
                matches!(primitive, Primitive::Line | Primitive::Arc)
            }))
    {
        return Err(unsupported_relation_reason(instruction_index, relation));
    }
    checked.target_endpoint = relation.target_endpoint;
    checked.target_path_position = relation
        .target_path_selection
        .map(|selection| inku_score::TargetPathPosition::Selection(selection));
    Ok(checked)
}

#[derive(Clone, Debug)]
struct AppearanceOmission {
    reason: ScoreFieldGap,
    field: ScoreAppearanceField,
    resolution: ScoreAppearanceResolution,
}

#[derive(Clone, Debug)]
struct InstructionFieldOmission {
    reason: ScoreFieldGap,
    field: ScoreInstructionField,
}

#[derive(Clone, Debug)]
struct InstructionLoweringAttempt<T = Instruction> {
    instruction: Option<T>,
    appearance_omissions: Vec<AppearanceOmission>,
    instruction_field_omissions: Vec<InstructionFieldOmission>,
    remaining_gaps: Vec<ScoreFieldGap>,
}

fn lower_projected_instruction(
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
    _error_policy: ScoreErrorPolicy,
) -> InstructionLoweringAttempt {
    resolve_projected_instruction(input, context, _error_policy, lower_complete_instruction)
}

fn resolve_projected_instruction<'a, T>(
    input: ScoreLoweringInput<'a>,
    context: ScoreLoweringContext,
    _error_policy: ScoreErrorPolicy,
    mut resolve: impl FnMut(
        ScoreLoweringInput<'a>,
        ScoreLoweringContext,
    ) -> Result<T, Vec<ScoreFieldGap>>,
) -> InstructionLoweringAttempt<T> {
    let first_gaps = match resolve(input, context) {
        Ok(instruction) => {
            return InstructionLoweringAttempt {
                instruction: Some(instruction),
                appearance_omissions: Vec::new(),
                instruction_field_omissions: Vec::new(),
                remaining_gaps: size_recovery_diagnostic(input, context)
                    .into_iter()
                    .collect(),
            };
        }
        Err(gaps) => gaps,
    };
    let appearance_fields = first_gaps
        .iter()
        .filter_map(appearance_field_for_gap)
        .collect::<Vec<_>>();
    let surface_quality_survives = input.surface.is_some()
        && !appearance_fields.contains(&ScoreAppearanceField::SurfaceQuality);
    let mut projected = input;
    let mut appearance_omissions = Vec::new();
    let mut instruction_field_omissions = Vec::new();
    let mut remaining_gaps = Vec::new();
    for reason in first_gaps {
        if let Some(field) = appearance_field_for_gap(&reason) {
            omit_appearance_field(&mut projected, field);
            appearance_omissions.push(AppearanceOmission {
                reason,
                field,
                resolution: default_resolution(field, surface_quality_survives),
            });
        } else if let Some(field) = instruction_field_for_gap(&reason) {
            omit_instruction_field(&mut projected, field);
            instruction_field_omissions.push(InstructionFieldOmission { reason, field });
        } else {
            remaining_gaps.push(reason);
        }
    }
    if !remaining_gaps.is_empty() {
        return InstructionLoweringAttempt {
            instruction: None,
            appearance_omissions,
            instruction_field_omissions,
            remaining_gaps,
        };
    }
    match resolve(projected, context) {
        Ok(instruction) => InstructionLoweringAttempt {
            instruction: Some(instruction),
            appearance_omissions,
            instruction_field_omissions,
            remaining_gaps: size_recovery_diagnostic(projected, context)
                .into_iter()
                .collect(),
        },
        Err(gaps) => InstructionLoweringAttempt {
            instruction: None,
            appearance_omissions,
            instruction_field_omissions,
            remaining_gaps: gaps,
        },
    }
}

#[allow(clippy::too_many_arguments)]
fn lower_source_instruction_with_policy(
    instruction_index: usize,
    instruction: &SemanticInstruction,
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
    instructions: &mut Vec<Instruction>,
    instruction_origins: &mut Vec<ScoreInstructionOrigin>,
    diagnostics: &mut Vec<ScoreLoweringDiagnostic>,
) {
    let attempt = lower_projected_instruction(input, context, error_policy);
    for omission in attempt.appearance_omissions {
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: source_owner_for_gap(instruction_index, instruction, &omission.reason),
            disposition: diagnostic_disposition(
                error_policy,
                &omission.reason,
                ScoreOmissionUnit::AppearanceField {
                    field: omission.field,
                },
                Some(omission.resolution),
            ),
            reason: omission.reason,
        });
    }
    for omission in attempt.instruction_field_omissions {
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: source_owner_for_gap(instruction_index, instruction, &omission.reason),
            disposition: diagnostic_disposition(
                error_policy,
                &omission.reason,
                ScoreOmissionUnit::InstructionField {
                    field: omission.field,
                },
                None,
            ),
            reason: omission.reason,
        });
    }
    for reason in attempt.remaining_gaps {
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: source_owner_for_gap(instruction_index, instruction, &reason),
            disposition: diagnostic_disposition(
                error_policy,
                &reason,
                ScoreOmissionUnit::SourceInstruction { instruction_index },
                None,
            ),
            reason,
        });
    }
    if let Some(score_instruction) = attempt.instruction {
        instructions.push(score_instruction);
        instruction_origins.push(ScoreInstructionOrigin::SourceInstruction { instruction_index });
    }
}

#[allow(clippy::too_many_arguments)]
fn lower_source_relation_instruction_with_policy(
    instruction_index: usize,
    instruction: &SemanticInstruction,
    input: ScoreLoweringInput<'_>,
    relation: Relation,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
    instructions: &mut Vec<Instruction>,
    instruction_origins: &mut Vec<ScoreInstructionOrigin>,
    diagnostics: &mut Vec<ScoreLoweringDiagnostic>,
) {
    let attempt = lower_projected_instruction(input, context, error_policy);
    for omission in attempt.appearance_omissions {
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: source_owner_for_gap(instruction_index, instruction, &omission.reason),
            disposition: diagnostic_disposition(
                error_policy,
                &omission.reason,
                ScoreOmissionUnit::AppearanceField {
                    field: omission.field,
                },
                Some(omission.resolution),
            ),
            reason: omission.reason,
        });
    }
    for omission in attempt.instruction_field_omissions {
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: source_owner_for_gap(instruction_index, instruction, &omission.reason),
            disposition: diagnostic_disposition(
                error_policy,
                &omission.reason,
                ScoreOmissionUnit::InstructionField {
                    field: omission.field,
                },
                None,
            ),
            reason: omission.reason,
        });
    }
    for reason in attempt.remaining_gaps {
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: source_owner_for_gap(instruction_index, instruction, &reason),
            disposition: diagnostic_disposition(
                error_policy,
                &reason,
                ScoreOmissionUnit::RelationInstruction { instruction_index },
                None,
            ),
            reason,
        });
    }
    if let Some(mut score_instruction) = attempt.instruction {
        score_instruction.relation = Some(relation);
        instructions.push(score_instruction);
        instruction_origins.push(ScoreInstructionOrigin::SourceInstruction { instruction_index });
    }
}

fn diagnostic_disposition(
    _error_policy: ScoreErrorPolicy,
    reason: &ScoreFieldGap,
    unit: ScoreOmissionUnit,
    appearance_resolution: Option<ScoreAppearanceResolution>,
) -> ScoreDiagnosticDisposition {
    if matches!(reason, ScoreFieldGap::ConflictingSizeSpecifications { .. }) {
        return ScoreDiagnosticDisposition::Recovered;
    }
    if !reason.is_integrity_failure() {
        ScoreDiagnosticDisposition::Omitted {
            unit,
            appearance_resolution,
        }
    } else {
        ScoreDiagnosticDisposition::Stopped
    }
}

const fn relation_diagnostic_disposition() -> ScoreDiagnosticDisposition {
    ScoreDiagnosticDisposition::RelationOmitted
}

fn appearance_field_for_gap(gap: &ScoreFieldGap) -> Option<ScoreAppearanceField> {
    match gap {
        ScoreFieldGap::UnsupportedColorIdentity { .. } => Some(ScoreAppearanceField::Color),
        ScoreFieldGap::UnsupportedTouchIdentity { .. } => Some(ScoreAppearanceField::Touch),
        ScoreFieldGap::UnsupportedContinuityIdentity { .. } => {
            Some(ScoreAppearanceField::Continuity)
        }
        ScoreFieldGap::UnsupportedSurfaceIdentity { .. } => {
            Some(ScoreAppearanceField::SurfaceQuality)
        }
        ScoreFieldGap::UnsupportedSurfaceIntensity { .. } => {
            Some(ScoreAppearanceField::SurfaceIntensity)
        }
        _ => None,
    }
}

fn instruction_field_for_gap(gap: &ScoreFieldGap) -> Option<ScoreInstructionField> {
    match gap {
        ScoreFieldGap::UnsupportedLayoutDirection { .. } => {
            Some(ScoreInstructionField::LayoutDirection)
        }
        _ => None,
    }
}

fn omit_appearance_field(input: &mut ScoreLoweringInput<'_>, field: ScoreAppearanceField) {
    match field {
        ScoreAppearanceField::Color => input.color = None,
        ScoreAppearanceField::Touch => input.touch = None,
        ScoreAppearanceField::Continuity => input.continuity = None,
        ScoreAppearanceField::SurfaceQuality => input.surface = None,
        ScoreAppearanceField::SurfaceIntensity => input.surface_intensity = None,
    }
}

fn omit_instruction_field(input: &mut ScoreLoweringInput<'_>, field: ScoreInstructionField) {
    match field {
        ScoreInstructionField::LayoutDirection => input.layout_direction = None,
    }
}

fn default_resolution(
    field: ScoreAppearanceField,
    surface_quality_survives: bool,
) -> ScoreAppearanceResolution {
    match field {
        ScoreAppearanceField::Color => ScoreAppearanceResolution::ContrastColor,
        ScoreAppearanceField::Touch => ScoreAppearanceResolution::Pen,
        ScoreAppearanceField::Continuity => ScoreAppearanceResolution::Solid,
        ScoreAppearanceField::SurfaceQuality => ScoreAppearanceResolution::Filled,
        ScoreAppearanceField::SurfaceIntensity if surface_quality_survives => {
            ScoreAppearanceResolution::PreserveExplicitSurfaceQuality
        }
        ScoreAppearanceField::SurfaceIntensity => ScoreAppearanceResolution::Filled,
    }
}

fn source_owner_for_gap(
    instruction_index: usize,
    instruction: &SemanticInstruction,
    gap: &ScoreFieldGap,
) -> ScoreDiagnosticOwner {
    let field = appearance_field_for_gap(gap);
    let spans = if matches!(gap, ScoreFieldGap::ConflictingSizeSpecifications { .. }) {
        let entity = &instruction.entity;
        let mut spans = entity
            .explicit_geometry
            .iter()
            .chain(&entity.additional_explicit_geometries)
            .map(|geometry| geometry.source().span)
            .chain(
                entity
                    .relative_scale
                    .iter()
                    .chain(&entity.additional_relative_scales)
                    .map(|scale| scale.provenance.span),
            )
            .chain(
                entity
                    .proportion
                    .width_extent
                    .iter()
                    .chain(&entity.additional_width_extents)
                    .map(|term| term.provenance.source.span),
            )
            .collect::<Vec<_>>();
        spans.sort_by_key(|span| (span.start_byte, span.end_byte));
        spans
    } else {
        vec![source_span_for_gap(instruction, gap, field)]
    };
    ScoreDiagnosticOwner::SourceInstruction {
        instruction_index,
        field,
        spans,
    }
}

fn source_span_for_gap(
    instruction: &SemanticInstruction,
    gap: &ScoreFieldGap,
    field: Option<ScoreAppearanceField>,
) -> SourceSpan {
    if let Some(field) = field {
        return source_span_for_appearance(instruction, field)
            .unwrap_or(instruction.entity.head.source().span);
    }
    match gap {
        ScoreFieldGap::ExactCountZero { .. }
        | ScoreFieldGap::ExactCountExceedsScoreRange { .. }
        | ScoreFieldGap::RepeatedCountUnsupported { .. } => instruction
            .entity
            .quantity
            .as_ref()
            .map(|quantity| quantity.provenance.span),
        ScoreFieldGap::UnsupportedActionIdentity { .. } | ScoreFieldGap::MissingPlaceAction => {
            instruction
                .action
                .as_ref()
                .map(|action| action.provenance.source.span)
        }
        ScoreFieldGap::NamedAndNumericPositionConflict
        | ScoreFieldGap::UnsupportedNamedPosition
        | ScoreFieldGap::MissingNumericPosition
        | ScoreFieldGap::PositionOutOfRange
        | ScoreFieldGap::GeometryExtentOutOfBounds => instruction
            .position
            .as_ref()
            .map(|position| position.provenance.source.span)
            .or_else(|| {
                instruction
                    .entity
                    .numeric_position
                    .as_ref()
                    .map(|position| position.source().span)
            }),
        ScoreFieldGap::NonPositiveDimension
        | ScoreFieldGap::GeometryRepresentationLimit
        | ScoreFieldGap::GeometryDimensionMismatch { .. }
        | ScoreFieldGap::ShapeConstraintMismatch { .. }
        | ScoreFieldGap::UnsupportedPrimitiveForExplicitGeometry { .. } => instruction
            .entity
            .explicit_geometry
            .as_ref()
            .map(|geometry| geometry.source().span),
        ScoreFieldGap::UnsupportedAngleIdentity { .. }
        | ScoreFieldGap::UnsupportedAngleForPrimitive { .. } => instruction
            .entity
            .angle
            .as_ref()
            .map(|angle| angle.provenance.source.span),
        ScoreFieldGap::UnsupportedLayoutDirection { .. } => instruction
            .layout_direction
            .as_ref()
            .map(|term| term.provenance.source.span),
        _ => None,
    }
    .unwrap_or(instruction.entity.head.source().span)
}

fn source_span_for_appearance(
    instruction: &SemanticInstruction,
    field: ScoreAppearanceField,
) -> Option<SourceSpan> {
    match field {
        ScoreAppearanceField::Color => instruction.entity.color.as_ref(),
        ScoreAppearanceField::Touch => instruction.entity.touch.as_ref(),
        ScoreAppearanceField::Continuity => instruction.entity.continuity.as_ref(),
        ScoreAppearanceField::SurfaceQuality => instruction.entity.surface.quality.as_ref(),
        ScoreAppearanceField::SurfaceIntensity => instruction.entity.surface.intensity.as_ref(),
    }
    .map(|term| term.provenance.source.span)
}

fn macro_invocation_owner(
    source_instruction_index: usize,
    head: &SemanticMacroInvocationHead,
    field: Option<ScoreAppearanceField>,
) -> ScoreDiagnosticOwner {
    ScoreDiagnosticOwner::MacroInvocation {
        source_instruction_index,
        invocation_ordinal: head.provenance.ordinal,
        field,
        spans: vec![head.provenance.source.span],
    }
}

fn macro_caller_owner(
    source_instruction_index: usize,
    instruction: &SemanticInstruction,
    head: &SemanticMacroInvocationHead,
    field: ScoreAppearanceField,
) -> ScoreDiagnosticOwner {
    ScoreDiagnosticOwner::MacroInvocation {
        source_instruction_index,
        invocation_ordinal: head.provenance.ordinal,
        field: Some(field),
        spans: vec![
            source_span_for_appearance(instruction, field).unwrap_or(head.provenance.source.span),
        ],
    }
}

fn macro_caller_field_owner(
    source_instruction_index: usize,
    instruction: &SemanticInstruction,
    head: &SemanticMacroInvocationHead,
    field: ScoreMacroCallerField,
) -> ScoreDiagnosticOwner {
    let span = match field {
        ScoreMacroCallerField::Action => instruction
            .action
            .as_ref()
            .map(|term| term.provenance.source.span),
    }
    .unwrap_or(head.provenance.source.span);
    ScoreDiagnosticOwner::MacroInvocation {
        source_instruction_index,
        invocation_ordinal: head.provenance.ordinal,
        field: None,
        spans: vec![span],
    }
}

fn macro_invocation_unit(
    source_instruction_index: usize,
    head: &SemanticMacroInvocationHead,
) -> ScoreOmissionUnit {
    ScoreOmissionUnit::MacroInvocation {
        source_instruction_index,
        invocation_ordinal: head.provenance.ordinal,
    }
}

fn macro_caller_field_unit(
    source_instruction_index: usize,
    head: &SemanticMacroInvocationHead,
    field: ScoreMacroCallerField,
) -> ScoreOmissionUnit {
    ScoreOmissionUnit::MacroCallerField {
        source_instruction_index,
        invocation_ordinal: head.provenance.ordinal,
        field,
    }
}

fn append_macro_invocation_diagnostic(
    source_instruction_index: usize,
    head: &SemanticMacroInvocationHead,
    reason: ScoreFieldGap,
    error_policy: ScoreErrorPolicy,
    diagnostics: &mut Vec<ScoreLoweringDiagnostic>,
) {
    diagnostics.push(ScoreLoweringDiagnostic {
        owner: macro_invocation_owner(source_instruction_index, head, None),
        disposition: diagnostic_disposition(
            error_policy,
            &reason,
            macro_invocation_unit(source_instruction_index, head),
            None,
        ),
        reason,
    });
}

fn generated_owner(
    source_instruction_index: usize,
    provenance: &GeneratedNodeProvenance,
    key: Option<String>,
) -> ScoreDiagnosticOwner {
    ScoreDiagnosticOwner::GeneratedNode {
        source_instruction_index,
        invocation_ordinal: provenance.invocation.invocation_ordinal,
        expansion_path: provenance.expansion_path.clone(),
        generated_ordinal: provenance.generated_ordinal,
        key,
        spans: vec![provenance.invocation.source_span],
    }
}

fn macro_emit_unit(
    source_instruction_index: usize,
    provenance: &GeneratedNodeProvenance,
) -> ScoreOmissionUnit {
    ScoreOmissionUnit::MacroEmit {
        source_instruction_index,
        invocation_ordinal: provenance.invocation.invocation_ordinal,
        expansion_path: provenance.expansion_path.clone(),
        generated_ordinal: provenance.generated_ordinal,
    }
}

fn macro_key_for_appearance(field: ScoreAppearanceField) -> Option<&'static str> {
    match field {
        ScoreAppearanceField::Color => Some("color"),
        ScoreAppearanceField::Touch => Some("touch"),
        ScoreAppearanceField::Continuity => Some("continuity"),
        ScoreAppearanceField::SurfaceQuality => Some("surface"),
        ScoreAppearanceField::SurfaceIntensity => Some("surface_intensity"),
    }
}

fn macro_key_for_gap(gap: &ScoreFieldGap) -> Option<String> {
    match gap {
        ScoreFieldGap::MissingMacroEmitField { key }
        | ScoreFieldGap::UnknownMacroEmitField { key }
        | ScoreFieldGap::MacroEmitFieldTypeMismatch { key }
        | ScoreFieldGap::MacroEmitIntegerOutOfRange { key, .. }
        | ScoreFieldGap::MacroEmitFieldCategoryMismatch { key, .. }
        | ScoreFieldGap::UnsupportedMacroEmitIdentity { key, .. } => Some(key.clone()),
        ScoreFieldGap::UnsupportedPrimitiveIdentity { .. }
        | ScoreFieldGap::UnsupportedPrimitiveForExplicitGeometry { .. } => Some("shape".to_owned()),
        ScoreFieldGap::UnsupportedColorIdentity { .. }
        | ScoreFieldGap::MissingColor
        | ScoreFieldGap::MissingResolvedPaletteContext => Some("color".to_owned()),
        ScoreFieldGap::UnsupportedTouchIdentity { .. } | ScoreFieldGap::MissingTouch => {
            Some("touch".to_owned())
        }
        ScoreFieldGap::UnsupportedContinuityIdentity { .. } | ScoreFieldGap::MissingContinuity => {
            Some("continuity".to_owned())
        }
        ScoreFieldGap::UnsupportedSurfaceIdentity { .. } | ScoreFieldGap::MissingEmptySurface => {
            Some("surface".to_owned())
        }
        ScoreFieldGap::UnsupportedSurfaceIntensity { .. } => Some("surface_intensity".to_owned()),
        ScoreFieldGap::UnsupportedActionIdentity { .. } | ScoreFieldGap::MissingPlaceAction => {
            Some("movement".to_owned())
        }
        ScoreFieldGap::UnsupportedAngleIdentity { .. }
        | ScoreFieldGap::UnsupportedAngleForPrimitive { .. } => Some("angle".to_owned()),
        ScoreFieldGap::UnsupportedLayoutDirection { .. } => Some("layout_direction".to_owned()),
        ScoreFieldGap::MissingMacroEmitFocusTarget { .. }
        | ScoreFieldGap::DuplicateMacroEmitFocusTarget { .. }
        | ScoreFieldGap::MissingNumericPosition
        | ScoreFieldGap::UnsupportedNamedPosition => Some("place".to_owned()),
        ScoreFieldGap::ExactCountZero { .. }
        | ScoreFieldGap::ExactCountExceedsScoreRange { .. }
        | ScoreFieldGap::RepeatedCountUnsupported { .. }
        | ScoreFieldGap::MissingExactCount => Some("count".to_owned()),
        _ => None,
    }
}

fn appearance_field_for_macro_projection_gap(gap: &ScoreFieldGap) -> Option<ScoreAppearanceField> {
    let key = match gap {
        ScoreFieldGap::MacroEmitFieldTypeMismatch { key }
        | ScoreFieldGap::MacroEmitFieldCategoryMismatch { key, .. }
        | ScoreFieldGap::UnsupportedMacroEmitIdentity { key, .. } => key.as_str(),
        _ => return None,
    };
    match key {
        "color" => Some(ScoreAppearanceField::Color),
        "touch" => Some(ScoreAppearanceField::Touch),
        "continuity" => Some(ScoreAppearanceField::Continuity),
        "surface" => Some(ScoreAppearanceField::SurfaceQuality),
        "surface_intensity" => Some(ScoreAppearanceField::SurfaceIntensity),
        _ => None,
    }
}

#[derive(Clone, Copy, Debug, Default)]
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
enum FillTargetInput<'a> {
    Canvas(&'a crate::SourceOccurrence),
    Shape {
        instruction: &'a SemanticInstruction,
        source_instruction_index: usize,
        effective_focus: Option<FocusRegion>,
    },
    Invalid,
}

#[derive(Clone, Copy, Debug, Default)]
struct ScoreLoweringInput<'a> {
    fill_target: Option<FillTargetInput<'a>>,
    group_region: Option<[f64; 4]>,
    generated_position: Option<crate::geometry::ExactPosition>,
    generated_geometries: [Option<crate::geometry::ExactGeometry>; 6],
    proportion_width_extent: Option<SemanticInputIdentity<'a>>,
    proportion_arc_form: Option<SemanticInputIdentity<'a>>,
    additional_relative_scales: &'a [crate::SemanticRelativeScale],
    additional_explicit_geometries: &'a [SemanticExplicitGeometry],
    additional_width_extents: &'a [crate::SemanticTerm],
    shape_constraint: Option<crate::ShapeConstraint>,
    proportion_aspect: Option<SemanticInputIdentity<'a>>,
    primitive: SemanticInputIdentity<'a>,
    count: Option<u64>,
    color: Option<SemanticInputIdentity<'a>>,
    color_cycle: &'a [crate::SemanticTerm],
    touch: Option<SemanticInputIdentity<'a>>,
    continuity: Option<SemanticInputIdentity<'a>>,
    surface: Option<SemanticInputIdentity<'a>>,
    surface_intensity: Option<SemanticInputIdentity<'a>>,
    thinness: Option<CoreModifierValue>,
    action: Option<SemanticInputIdentity<'a>>,
    numeric_position: Option<&'a SemanticNumericPosition>,
    has_named_position: bool,
    named_position: Option<SemanticInputIdentity<'a>>,
    effective_focus: Option<FocusRegion>,
    explicit_geometry: Option<&'a SemanticExplicitGeometry>,
    relative_scale: Option<CoreModifierValue>,
    angle: Option<SemanticInputIdentity<'a>>,
    angle_context: Option<ScoreAngleContext<'a>>,
    layout_direction: Option<SemanticInputIdentity<'a>>,
    fluctuation: [Option<SemanticInputIdentity<'a>>; 3],
    ink_spread: Option<SemanticInputIdentity<'a>>,
    has_unsupported_meaning: bool,
}

impl ScoreLoweringInput<'_> {
    fn position_authority(self) -> ConnectedPositionAuthority {
        if self.exact_position().is_some() {
            ConnectedPositionAuthority::NumericFixed
        } else {
            ConnectedPositionAuthority::NamedMovable
        }
    }

    fn exact_position(self) -> Option<crate::geometry::ExactPosition> {
        self.numeric_position
            .map(Into::into)
            .or(self.generated_position)
    }
    fn exact_geometry(self) -> Option<crate::geometry::ExactGeometry> {
        self.explicit_geometry
            .map(Into::into)
            .or_else(|| self.generated_geometries.into_iter().flatten().next())
    }
}

fn lower_complete_instruction(
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
) -> Result<Instruction, Vec<ScoreFieldGap>> {
    if input
        .action
        .is_some_and(|action| action.category == "movement" && action.id == "fill")
    {
        // Even count one needs the region clip contract. Validate the same plan
        // without pretending that the current un-clipped Score can carry it.
        resolve_fill_plan(input, context)?;
        return Err(vec![ScoreFieldGap::FillRequiresRegionMaterialization]);
    }
    let resolved = resolve_complete_object(input, context, false)?;
    let geometric = match resolved.placement {
        ScorePlacement::Numeric(position) => lower_numeric_geometry(
            resolved.primitive,
            resolved.dimensions,
            position,
            context.canvas_format,
            resolved.rotation,
        ),
        ScorePlacement::Named(focus) => {
            lower_named_geometry(resolved.dimensions, focus, context.canvas_format)
        }
    }
    .map_err(|gap| vec![gap])?;
    Ok(instruction_from_resolved_geometry(
        resolved.primitive,
        resolved.dimensions,
        resolved.arc_form,
        resolved.rotation,
        resolved.appearance,
        geometric,
    ))
}

/// Lower one already-resolved body template without reading or resolving source again.
/// A fill's region owns its placement; the neutral local anchor is translated by
/// the performer, and is never promoted to an explicit source position.
pub(crate) fn lower_resolved_object_template(
    object: &ObjectPlacementPlan,
    context: ScoreLoweringContext,
) -> Result<Instruction, ScoreFieldGap> {
    let geometric = if matches!(
        object.recipe,
        PlacementRecipe::FillUniformInRegionAndClip { .. }
    ) {
        lower_named_geometry(object.dimensions, [0.5; 4], context.canvas_format)?
    } else {
        match &object.anchor {
            ObjectAnchor::Numeric(position) => lower_numeric_geometry(
                object.primitive,
                object.dimensions,
                position.into(),
                context.canvas_format,
                object.angle,
            )?,
            ObjectAnchor::GeneratedNumeric(position) => lower_numeric_geometry(
                object.primitive,
                object.dimensions,
                *position,
                context.canvas_format,
                object.angle,
            )?,
            ObjectAnchor::Named(region) => {
                lower_named_geometry(object.dimensions, *region, context.canvas_format)?
            }
        }
    };
    Ok(instruction_from_resolved_geometry(
        object.primitive,
        object.dimensions,
        object.arc_form,
        object.angle,
        object.appearance.clone(),
        geometric,
    ))
}

fn instruction_from_resolved_geometry(
    primitive: Primitive,
    dimensions: ResolvedGeometryDimensions,
    arc_form: Option<inku_score::ArcForm>,
    rotation: Option<f64>,
    appearance: ResolvedObjectAppearance,
    geometric: LoweredGeometry,
) -> Instruction {
    Instruction {
        arc_form,
        primitive,
        note: None,
        from_: geometric.from,
        to: geometric.to,
        center: geometric.center,
        radius: geometric.radius,
        sides: match dimensions {
            ResolvedGeometryDimensions::Polygon { sides, .. } => Some(sides),
            _ => None,
        },
        position: geometric.position,
        size: geometric.size,
        angle_start: geometric.angle_start,
        angle_end: geometric.angle_end,
        rotation,
        filled: appearance.filled,
        style: appearance.continuity,
        weight: appearance.touch,
        mode_: InstructionMode::Additive,
        carve_depth: None,
        color: appearance.color,
        color_hint: None,
        variation: appearance.fluctuation,
        ink_spread: appearance.ink_spread,
        arrangement: None,
        at: geometric.at,
        relation: None,
        surface_intensity: appearance.surface_intensity,
        thinness: appearance.thinness,
        surface: appearance.surface,
    }
}

struct ResolvedObject {
    arc_form: Option<inku_score::ArcForm>,
    primitive: Primitive,
    count: u32,
    action: PlacementAction,
    dimensions: ResolvedGeometryDimensions,
    appearance: ResolvedObjectAppearance,
    color_cycle: Vec<Color>,
    rotation: Option<f64>,
    layout_direction: Option<crate::composition_plan::ResolvedLayoutDirection>,
    placement: ScorePlacement,
}

fn resolve_object_plan(
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
    origin: ScoreInstructionOrigin,
) -> Result<ObjectPlacementPlan, Vec<ScoreFieldGap>> {
    let resolved = resolve_complete_object(input, context, true)?;
    let build = || -> Result<ObjectPlacementPlan, ScoreFieldGap> {
        let (width, height) = context.canvas_format.integer_ratio();
        let short = width.min(height);
        let mut domain = [
            Rational::from_ratio(width.into(), short.into())?,
            Rational::from_ratio(height.into(), short.into())?,
        ];
        let anchor = match resolved.placement {
            ScorePlacement::Numeric(position) => input
                .numeric_position
                .map(|source| ObjectAnchor::Numeric(source.clone()))
                .unwrap_or(ObjectAnchor::GeneratedNumeric(position)),
            ScorePlacement::Named(region) => {
                if resolved.action == PlacementAction::Tile {
                    let bounds = crate::geometry::resolved_position_rational_bounds(
                        input.named_position.map(|position| position.id),
                        input.effective_focus,
                        input.angle_context.expect("verified occurrence"),
                    )
                    .expect("the shared named region was already resolved");
                    for axis in 0..2 {
                        let (end_n, end_d) = bounds[axis + 2];
                        let (start_n, start_d) = bounds[axis];
                        let extent = Rational::from_ratio(end_n.into(), end_d.into())?
                            .sub(Rational::from_ratio(start_n.into(), start_d.into())?)?;
                        domain[axis] = domain[axis].mul(extent)?;
                    }
                }
                ObjectAnchor::Named(region)
            }
        };
        let (n, fill_recipe) = if resolved.action == PlacementAction::Fill {
            let (count, recipe) = resolve_fill_plan_with_object(input, context, &resolved)?;
            (count, Some(recipe))
        } else {
            (resolved.count, None)
        };
        let layout_direction = resolved.layout_direction;
        let recipe = if let Some(recipe) = fill_recipe {
            recipe
        } else {
            placement_recipe(
                resolved.action,
                u64::from(n),
                domain,
                layout_direction.as_ref(),
                matches!(
                    anchor,
                    ObjectAnchor::Numeric(_) | ObjectAnchor::GeneratedNumeric(_)
                ),
            )?
        };
        Ok(ObjectPlacementPlan {
            arc_form: resolved.arc_form,
            proportion_width_extent: input.proportion_width_extent.map(|identity| {
                crate::SemanticIdentity {
                    category: identity.category.to_owned(),
                    id: identity.id.to_owned(),
                }
            }),
            additional_relative_scales: input.additional_relative_scales.to_vec(),
            additional_explicit_geometries: input.additional_explicit_geometries.to_vec(),
            additional_width_extents: input.additional_width_extents.to_vec(),
            shape_constraint: input.shape_constraint,
            proportion_aspect: input
                .proportion_aspect
                .map(|identity| crate::SemanticIdentity {
                    category: identity.category.to_owned(),
                    id: identity.id.to_owned(),
                }),
            origin,
            primitive: resolved.primitive,
            count: n,
            count_was_omitted: input.count.is_none(),
            dimensions: resolved.dimensions,
            explicit_geometry: input.explicit_geometry.cloned(),
            generated_geometries: input.generated_geometries.into_iter().flatten().collect(),
            relative_scale: input.relative_scale,
            appearance: resolved.appearance,
            color_cycle: resolved.color_cycle,
            angle: resolved.rotation,
            layout_direction,
            anchor,
            domain,
            recipe,
            relation: None,
        })
    };
    build().map_err(|gap| vec![gap])
}

struct PreparedFillGroup {
    region: ResolvedFillRegion,
    /// Provisional source-head counts; omitted counts are resolved after each
    /// member body has produced its symbolic geometry, without repeating it.
    counts: Vec<u32>,
}

struct SupportedMemberCycle {
    owner_projected_index: usize,
    members: SupportedCycleMembers,
    count: Option<u64>,
    action: PlacementAction,
    layout: inku_score::GroupLayout,
    region: [f64; 4],
    domain: [Rational; 2],
    fill_region: Option<ResolvedFillRegion>,
}

enum SupportedCycleMembers {
    Units(Vec<Vec<usize>>),
    Field { owner_projected_index: usize },
}

fn apply_sequence_field(
    instruction: &mut SemanticInstruction,
    field: crate::SemanticSequenceField,
    item: crate::SemanticTerm,
) {
    match field {
        crate::SemanticSequenceField::Touch => instruction.entity.touch = Some(item),
        crate::SemanticSequenceField::Continuity => instruction.entity.continuity = Some(item),
        crate::SemanticSequenceField::Angle => instruction.entity.angle = Some(item),
        crate::SemanticSequenceField::SurfaceQuality => {
            instruction.entity.surface.quality = Some(item)
        }
        crate::SemanticSequenceField::SurfaceIntensity => {
            instruction.entity.surface.intensity = Some(item)
        }
        crate::SemanticSequenceField::FluctuationAmplitude => {
            instruction.entity.fluctuation.amplitude = Some(item)
        }
        crate::SemanticSequenceField::FluctuationFrequency => {
            instruction.entity.fluctuation.frequency = Some(item)
        }
        crate::SemanticSequenceField::FluctuationQuality => {
            instruction.entity.fluctuation.quality = Some(item)
        }
        crate::SemanticSequenceField::FluctuationSpread => {
            instruction.entity.fluctuation.spread = Some(item)
        }
        crate::SemanticSequenceField::ProportionAspect => {
            instruction.entity.proportion.aspect = Some(item)
        }
        crate::SemanticSequenceField::ProportionWidthExtent => {
            instruction.entity.proportion.width_extent = Some(item)
        }
        crate::SemanticSequenceField::ProportionArcForm => {
            instruction.entity.proportion.arc_form = Some(item)
        }
    }
}

fn project_fill_target<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    target: Option<&'a crate::SemanticFillTarget>,
) -> Option<FillTargetInput<'a>> {
    match target {
        Some(crate::SemanticFillTarget::Canvas { source, .. }) => {
            Some(FillTargetInput::Canvas(source))
        }
        Some(crate::SemanticFillTarget::InlineShape {
            target_instruction_index,
            ..
        }) => Some(
            match view
                .original_semantic_document()
                .instructions
                .get(*target_instruction_index)
            {
                Some(instruction) => {
                    let source_instruction_index = view
                        .source_instruction_index(*target_instruction_index)
                        .expect("verified view maps every inline target");
                    FillTargetInput::Shape {
                        instruction,
                        source_instruction_index,
                        effective_focus: direct_instruction_focus(view, source_instruction_index),
                    }
                }
                None => FillTargetInput::Invalid,
            },
        ),
        None => None,
    }
}

fn resolve_fill_group(
    view: VerifiedStage15EffectiveView<'_>,
    group: &crate::SemanticCoordinatedHeadGroup,
    predicate: &crate::SemanticGroupPredicateEdge,
    focus: Option<FocusRegion>,
    context: ScoreLoweringContext,
) -> Result<PreparedFillGroup, ScoreFieldGap> {
    let mut counts = Vec::new();
    for &index in &group.member_instruction_indices {
        let instruction = &view.original_semantic_document().instructions[index];
        if instruction.entity.numeric_position.is_some() || instruction.position.is_some() {
            return Err(ScoreFieldGap::InvalidFillTarget);
        }
        let count = instruction
            .entity
            .quantity
            .as_ref()
            .map_or(1, |quantity| quantity.value);
        if count == 0 {
            return Err(ScoreFieldGap::ExactCountZero { value: count });
        }
        counts.push(
            u32::try_from(count)
                .map_err(|_| ScoreFieldGap::ExactCountExceedsScoreRange { value: count })?,
        );
    }
    let first = *group
        .member_instruction_indices
        .first()
        .ok_or(ScoreFieldGap::InvalidFillTarget)?;
    // This empty structural input supplies only region authority. It does not
    // insert drawing defaults or use any member's size/appearance as the target.
    let input = ScoreLoweringInput {
        fill_target: project_fill_target(view, predicate.fill_target.as_ref()),
        has_named_position: predicate.position.is_some(),
        named_position: predicate
            .position
            .as_ref()
            .map(|term| (&term.identity).into()),
        effective_focus: focus,
        angle_context: Some(ScoreAngleContext {
            composition_seed: view.composition_seed(),
            original_pre_expansion_digest: view.original_pre_expansion_digest(),
            original_expanded_meaning_digest: view.original_expanded_meaning_digest(),
            occurrence: ScoreAngleOccurrence::Direct {
                logical_ordinal: view
                    .source_instruction_index(first)
                    .expect("verified group source member") as u64,
            },
        }),
        ..ScoreLoweringInput::default()
    };
    Ok(PreparedFillGroup {
        region: resolve_fill_region(input, context)?,
        counts,
    })
}

fn prepare_single_macro_fill(
    view: VerifiedStage15EffectiveView<'_>,
    source_index: usize,
    instruction: &SemanticInstruction,
    context: ScoreLoweringContext,
) -> Result<PreparedFillGroup, ScoreFieldGap> {
    if instruction.entity.numeric_position.is_some() {
        return Err(ScoreFieldGap::InvalidFillTarget);
    }
    let count = instruction
        .entity
        .quantity
        .as_ref()
        .map_or(1, |quantity| quantity.value);
    if count == 0 {
        return Err(ScoreFieldGap::ExactCountZero { value: count });
    }
    let count = u32::try_from(count)
        .map_err(|_| ScoreFieldGap::ExactCountExceedsScoreRange { value: count })?;
    let input = ScoreLoweringInput {
        fill_target: project_fill_target(view, instruction.fill_target.as_ref()),
        has_named_position: instruction.position.is_some(),
        named_position: instruction
            .position
            .as_ref()
            .map(|term| (&term.identity).into()),
        effective_focus: direct_instruction_focus(view, source_index),
        angle_context: Some(ScoreAngleContext {
            composition_seed: view.composition_seed(),
            original_pre_expansion_digest: view.original_pre_expansion_digest(),
            original_expanded_meaning_digest: view.original_expanded_meaning_digest(),
            occurrence: ScoreAngleOccurrence::Direct {
                logical_ordinal: source_index as u64,
            },
        }),
        ..ScoreLoweringInput::default()
    };
    Ok(PreparedFillGroup {
        region: resolve_fill_region(input, context)?,
        counts: vec![count],
    })
}

fn balanced_fill_counts(
    area: Rational,
    extents: &[Rational],
    explicit_counts: &[Option<u32>],
) -> Result<Vec<u32>, ScoreFieldGap> {
    // Explicit quantities need no density arithmetic, even for large extents.
    if let Some(counts) = explicit_counts.iter().copied().collect::<Option<Vec<_>>>() {
        return Ok(counts);
    }
    let mut explicit_area = Rational::from_ratio(0, 1)?;
    let mut omitted_footprints = Rational::from_ratio(0, 1)?;
    let mut omitted = 0_i128;
    for (&extent, count) in extents.iter().zip(explicit_counts) {
        let footprint = fill_product(extent, extent)?;
        if footprint.numerator <= 0 {
            return Err(ScoreFieldGap::FillRegionHasNoArea);
        }
        if let Some(count) = count {
            explicit_area = fill_sum(
                explicit_area,
                fill_product(footprint, Rational::from_ratio((*count).into(), 1)?)?,
            )?;
        } else {
            omitted += 1;
            omitted_footprints = fill_sum(omitted_footprints, footprint)?;
        }
    }
    let difference = fill_sum(
        area,
        Rational::from_ratio(-explicit_area.numerator, explicit_area.denominator)?,
    )?;
    let remaining = if difference.numerator <= 0 {
        Rational::from_ratio(0, 1)?
    } else {
        difference
    };
    let budget = fill_quotient(
        fill_product(remaining, Rational::from_ratio(omitted, 1)?)?,
        omitted_footprints,
    )?;
    let total = (budget.numerator / budget.denominator
        + i128::from(budget.numerator % budget.denominator != 0))
    .max(omitted);
    let base = total / omitted;
    let remainder = total % omitted;
    let mut ordinal = 0;
    explicit_counts
        .iter()
        .map(|count| match count {
            Some(count) => Ok(*count),
            None => {
                let count = base + i128::from(ordinal < remainder);
                ordinal += 1;
                u32::try_from(count).map_err(|_| ScoreFieldGap::FillCountExceedsScoreRange)
            }
        })
        .collect()
}

fn finalize_fill_group(
    owner: FillPlanOwner,
    prepared: PreparedFillGroup,
    mut members: Vec<PlacementMemberPlan>,
    objects: &mut [ObjectPlacementPlan],
    transforms: &[TransformGroupPlan],
    anchors: &[AnchorPoint],
    canvas: CanvasFormat,
) -> Result<FillGroupPlan, ScoreFieldGap> {
    if members.is_empty() {
        return Err(ScoreFieldGap::InvalidFillTarget);
    }
    let extents = members
        .iter()
        .map(|member| match member.kind {
            PlacementMemberKind::Primitive => {
                reference_extent(objects[member.member.start].dimensions)
            }
            PlacementMemberKind::Macro => crate::plan_reference_extent::reference_member_extent(
                objects, transforms, anchors, member, canvas,
            ),
            PlacementMemberKind::OrdinaryGroup => {
                crate::plan_reference_extent::reference_member_extent(
                    objects, transforms, anchors, member, canvas,
                )
            }
        })
        .collect::<Result<Vec<_>, _>>()?;
    let explicit_counts = members
        .iter()
        .map(|member| (!member.count_was_omitted).then_some(member.source_count))
        .collect::<Vec<_>>();
    let counts = balanced_fill_counts(prepared.region.reference_area, &extents, &explicit_counts)?;
    let mut logical_count = 0_u64;
    for (member, count) in members.iter_mut().zip(counts) {
        logical_count = logical_count
            .checked_add(u64::from(count))
            .ok_or(ScoreFieldGap::FillCountExceedsScoreRange)?;
        member.source_count = count;
        if member.kind == PlacementMemberKind::Primitive {
            let object = &mut objects[member.member.start];
            object.count = count;
            object.anchor = ObjectAnchor::Named([0.5; 4]);
        }
    }
    Ok(FillGroupPlan {
        owner,
        logical_count,
        members,
        recipe: PlacementRecipe::FillUniformInRegionAndClip {
            region: Box::new(prepared.region),
            count_resolution: FillCountResolution::BalancedGroup {
                reference_extents: extents,
                explicit_counts,
            },
        },
        cycle_occurrence_count: None,
    })
}

// Cross-cancel before checked arithmetic. Geometry's finite decimal reference
// extents may have large denominators, even for ordinary mixed polygons.
fn fill_gcd(mut a: i128, mut b: i128) -> i128 {
    while b != 0 {
        let next = a % b;
        a = b;
        b = next;
    }
    a.max(1)
}

fn fill_product(a: Rational, b: Rational) -> Result<Rational, ScoreFieldGap> {
    let a = reduced_ratio(a);
    let b = reduced_ratio(b);
    let g1 = fill_gcd(a.numerator.abs(), b.denominator);
    let g2 = fill_gcd(b.numerator.abs(), a.denominator);
    Ok(reduced_ratio(Rational::from_ratio(
        (a.numerator / g1)
            .checked_mul(b.numerator / g2)
            .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
        (a.denominator / g2)
            .checked_mul(b.denominator / g1)
            .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
    )?))
}

fn fill_sum(a: Rational, b: Rational) -> Result<Rational, ScoreFieldGap> {
    let a = reduced_ratio(a);
    let b = reduced_ratio(b);
    let common = fill_gcd(a.denominator, b.denominator);
    let left = a
        .numerator
        .checked_mul(b.denominator / common)
        .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?;
    let right = b
        .numerator
        .checked_mul(a.denominator / common)
        .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?;
    Ok(reduced_ratio(Rational::from_ratio(
        left.checked_add(right)
            .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
        a.denominator
            .checked_mul(b.denominator / common)
            .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
    )?))
}

fn fill_quotient(a: Rational, b: Rational) -> Result<Rational, ScoreFieldGap> {
    if b.numerator <= 0 {
        return Err(ScoreFieldGap::GeometryRepresentationLimit);
    }
    fill_product(a, Rational::from_ratio(b.denominator, b.numerator)?)
}

fn resolve_fill_plan(
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
) -> Result<(u32, PlacementRecipe), Vec<ScoreFieldGap>> {
    let object = resolve_complete_object(input, context, true)?;
    resolve_fill_plan_with_object(input, context, &object).map_err(|gap| vec![gap])
}

fn resolve_fill_plan_with_object(
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
    object: &ResolvedObject,
) -> Result<(u32, PlacementRecipe), ScoreFieldGap> {
    // A fixed center is not an area. The position of an inline target is a
    // separate authority and is preserved below.
    if input.exact_position().is_some() {
        return Err(ScoreFieldGap::InvalidFillTarget);
    }
    let region = resolve_fill_region(input, context)?;
    let extent = reduced_ratio(reference_extent(object.dimensions)?);
    if extent.numerator <= 0 || region.reference_area.numerator <= 0 {
        return Err(ScoreFieldGap::FillRegionHasNoArea);
    }
    let (count, count_resolution) = if input.count.is_some() {
        (object.count, FillCountResolution::Explicit)
    } else {
        let footprint = fill_product(extent, extent)?;
        let ratio = fill_quotient(region.reference_area, footprint)?;
        let count = ratio.numerator / ratio.denominator
            + i128::from(ratio.numerator % ratio.denominator != 0);
        let count =
            u32::try_from(count.max(1)).map_err(|_| ScoreFieldGap::FillCountExceedsScoreRange)?;
        (
            count,
            FillCountResolution::FromRegionAndExtent {
                reference_extent: extent,
            },
        )
    };
    Ok((
        count,
        PlacementRecipe::FillUniformInRegionAndClip {
            region: Box::new(region),
            count_resolution,
        },
    ))
}

fn resolve_fill_region(
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
) -> Result<ResolvedFillRegion, ScoreFieldGap> {
    let (cw, ch) = context.canvas_format.integer_ratio();
    let short = cw.min(ch);
    let canvas_area =
        Rational::from_ratio(i128::from(cw) * i128::from(ch), i128::from(short).pow(2))?;
    match input.fill_target {
        Some(FillTargetInput::Invalid) => Err(ScoreFieldGap::InvalidFillTarget),
        Some(FillTargetInput::Shape {
            instruction,
            source_instruction_index,
            effective_focus,
        }) => {
            if input.has_named_position
                || instruction
                    .entity
                    .quantity
                    .as_ref()
                    .is_some_and(|q| q.value != 1)
            {
                return Err(ScoreFieldGap::InvalidFillTarget);
            }
            let entity = &instruction.entity;
            let SemanticHead::Primitive(term) = &entity.head else {
                return Err(ScoreFieldGap::InvalidFillTarget);
            };
            let primitive = score_primitive_from_semantic_identity(&term.identity)
                .map_err(|_| ScoreFieldGap::InvalidFillTarget)?;
            let arc_form = entity
                .proportion
                .arc_form
                .as_ref()
                .filter(|form| form.identity.id == "crescent")
                .map(|_| inku_score::ArcForm::Crescent);
            if primitive == Primitive::Line || (primitive == Primitive::Arc && arc_form.is_none()) {
                return Err(ScoreFieldGap::FillRegionHasNoArea);
            }
            let target_input = ScoreLoweringInput {
                fill_target: None,
                primitive: (&term.identity).into(),
                explicit_geometry: entity.explicit_geometry.as_ref(),
                generated_geometries: [None; 6],
                relative_scale: entity.relative_scale.as_ref().map(|scale| scale.value),
                additional_relative_scales: &entity.additional_relative_scales,
                additional_explicit_geometries: &entity.additional_explicit_geometries,
                additional_width_extents: &entity.additional_width_extents,
                shape_constraint: entity.shape_constraint.as_ref().map(|shape| shape.value),
                proportion_aspect: entity
                    .proportion
                    .aspect
                    .as_ref()
                    .map(|term| (&term.identity).into()),
                proportion_arc_form: entity
                    .proportion
                    .arc_form
                    .as_ref()
                    .map(|term| (&term.identity).into()),
                proportion_width_extent: entity
                    .proportion
                    .width_extent
                    .as_ref()
                    .map(|term| (&term.identity).into()),
                ..input
            };
            let (dimensions, _) = resolve_size_candidates(target_input, context, primitive)?;
            let mut angle_context = input
                .angle_context
                .ok_or(ScoreFieldGap::InvalidFillTarget)?;
            angle_context.occurrence = ScoreAngleOccurrence::Direct {
                logical_ordinal: source_instruction_index as u64,
            };
            let anchor = match (
                entity.numeric_position.as_ref(),
                instruction.position.as_ref(),
            ) {
                (Some(_), Some(_)) => return Err(ScoreFieldGap::NamedAndNumericPositionConflict),
                (Some(position), None) => {
                    let exact: crate::geometry::ExactPosition = position.into();
                    if !Rational::from_decimal(exact.x)?.in_unit_interval()
                        || !Rational::from_decimal(exact.y)?.in_unit_interval()
                    {
                        return Err(ScoreFieldGap::PositionOutOfRange);
                    }
                    ObjectAnchor::Numeric(position.clone())
                }
                (None, Some(position)) => ObjectAnchor::Named(
                    named_region_bounds(&position.identity.id, effective_focus, angle_context)
                        .ok_or(ScoreFieldGap::UnsupportedNamedPosition)?,
                ),
                (None, None) => ObjectAnchor::Named(crate::geometry::omitted_position_bounds()),
            };
            let rotation_degrees = instruction
                .entity
                .angle
                .as_ref()
                .map(|angle| {
                    if primitive == Primitive::Point {
                        return Err(ScoreFieldGap::UnsupportedAngleForPrimitive { primitive });
                    }
                    resolve_score_angle(&angle.identity.id, angle_context).ok_or(
                        ScoreFieldGap::UnsupportedAngleIdentity {
                            category: angle.identity.category.clone(),
                            id: angle.identity.id.clone(),
                        },
                    )
                })
                .transpose()?;
            let reference_area = fill_shape_reference_area(primitive, dimensions, arc_form)?;
            let contour_variation = crate::fluctuation::resolve_fluctuation(
                entity
                    .fluctuation
                    .amplitude
                    .as_ref()
                    .map(|term| term.identity.id.as_str()),
                entity
                    .fluctuation
                    .frequency
                    .as_ref()
                    .map(|term| term.identity.id.as_str()),
                entity
                    .fluctuation
                    .quality
                    .as_ref()
                    .map(|term| term.identity.id.as_str()),
            )
            .map_err(|_| ScoreFieldGap::UnsupportedInstructionMeaning)?;
            Ok(ResolvedFillRegion {
                owner: FillRegionOwner::InlineShape {
                    source_instruction_index,
                    source: entity.head.source().clone(),
                },
                geometry: FillRegionGeometry::Shape {
                    primitive,
                    dimensions,
                    arc_form,
                    anchor,
                    rotation_degrees,
                    contour_variation,
                },
                reference_area,
            })
        }
        canvas_target => {
            let (owner, bounds) = if let Some(position) = input.named_position {
                if canvas_target.is_some() {
                    return Err(ScoreFieldGap::InvalidFillTarget);
                }
                let rational = crate::geometry::named_region_rational_bounds(
                    position.id,
                    input.effective_focus,
                    input
                        .angle_context
                        .ok_or(ScoreFieldGap::InvalidFillTarget)?,
                )
                .ok_or(ScoreFieldGap::UnsupportedNamedPosition)?;
                let mut bounds = [Rational::from_ratio(0, 1)?; 4];
                for (output, (n, d)) in bounds.iter_mut().zip(rational) {
                    *output = Rational::from_ratio(n.into(), d.into())?;
                }
                (
                    FillRegionOwner::Named(SemanticIdentity {
                        category: position.category.to_owned(),
                        id: position.id.to_owned(),
                    }),
                    bounds,
                )
            } else {
                let owner = match canvas_target {
                    Some(FillTargetInput::Canvas(source)) => {
                        FillRegionOwner::ExplicitCanvas(source.clone())
                    }
                    None => FillRegionOwner::OmittedCanvas,
                    _ => unreachable!("shape and invalid handled above"),
                };
                (
                    owner,
                    [
                        Rational::from_ratio(0, 1)?,
                        Rational::from_ratio(0, 1)?,
                        Rational::from_ratio(1, 1)?,
                        Rational::from_ratio(1, 1)?,
                    ],
                )
            };
            let area = canvas_area
                .mul(reduced_ratio(bounds[2].sub(bounds[0])?))?
                .mul(reduced_ratio(bounds[3].sub(bounds[1])?))?;
            if area.numerator <= 0 {
                return Err(ScoreFieldGap::FillRegionHasNoArea);
            }
            Ok(ResolvedFillRegion {
                owner,
                geometry: FillRegionGeometry::Rectangle { bounds },
                reference_area: reduced_ratio(area),
            })
        }
    }
}

fn fill_shape_reference_area(
    primitive: Primitive,
    dimensions: ResolvedGeometryDimensions,
    arc_form: Option<inku_score::ArcForm>,
) -> Result<Rational, ScoreFieldGap> {
    let area = match dimensions {
        ResolvedGeometryDimensions::Circle { radius }
        | ResolvedGeometryDimensions::Point { radius } => radius
            .mul(radius)?
            .mul(finite_geometry_ratio(std::f64::consts::PI)?)?,
        ResolvedGeometryDimensions::Square { side } => side.mul(side)?,
        ResolvedGeometryDimensions::RegularTriangle { side } => side
            .mul(side)?
            .mul(finite_geometry_ratio(3.0_f64.sqrt() / 4.0)?)?,
        ResolvedGeometryDimensions::Polygon { radius, sides } => {
            radius.mul(radius)?.mul(finite_geometry_ratio(
                f64::from(sides) * (std::f64::consts::TAU / f64::from(sides)).sin() / 2.0,
            )?)?
        }
        ResolvedGeometryDimensions::Bbox { width, height }
        | ResolvedGeometryDimensions::CenteredSize { width, height } => {
            let fraction = match primitive {
                Primitive::Ellipse => std::f64::consts::PI / 4.0,
                Primitive::Triangle => 0.5,
                // Declared envelope area keeps count independent of performance contours.
                Primitive::Cloudform | Primitive::Square => 1.0,
                Primitive::Arc if arc_form == Some(inku_score::ArcForm::Crescent) => {
                    inku_score::crescent_reference_area_ratio()
                }
                _ => return Err(ScoreFieldGap::FillRegionHasNoArea),
            };
            width.mul(height)?.mul(finite_geometry_ratio(fraction)?)?
        }
        ResolvedGeometryDimensions::Line { .. } | ResolvedGeometryDimensions::Arc { .. } => {
            return Err(ScoreFieldGap::FillRegionHasNoArea);
        }
    };
    if area.numerator <= 0 {
        return Err(ScoreFieldGap::FillRegionHasNoArea);
    }
    Ok(reduced_ratio(area))
}

pub(crate) fn placement_recipe(
    action: PlacementAction,
    n: u64,
    domain: [Rational; 2],
    layout_direction: Option<&crate::composition_plan::ResolvedLayoutDirection>,
    translate_to_numeric_anchor: bool,
) -> Result<PlacementRecipe, ScoreFieldGap> {
    Ok(match action {
        PlacementAction::Place => PlacementRecipe::Place,
        PlacementAction::LineUp => match layout_direction
            .map(|direction| direction.axis)
            .unwrap_or([1, 0])
        {
            [1, 0] => PlacementRecipe::HorizontalLine {
                cell_width: domain[0].div_i128(n.into())?,
            },
            [0, 1] => PlacementRecipe::VerticalLine {
                cell_height: domain[1].div_i128(n.into())?,
            },
            [1, y] => {
                let short = if domain[0].le(domain[1])? {
                    domain[0]
                } else {
                    domain[1]
                };
                let step = short.div_i128(n.into())?;
                PlacementRecipe::DiagonalLine {
                    step: [step, step.mul_i128(y.into())?],
                }
            }
            _ => unreachable!("closed layout axes"),
        },
        PlacementAction::Scatter => PlacementRecipe::ScatterUniformWithCentroidTranslation,
        PlacementAction::Fill => return Err(ScoreFieldGap::InvalidFillTarget),
        PlacementAction::Tile => {
            let landscape = domain[1].le(domain[0])?;
            // Integer binary search of k² >= n * long/short. This is bounded
            // by 64 iterations and has no floating ceil boundary or count loop.
            // A flat domain is one row/column; a point domain collapses every cell.
            let degenerate = domain.iter().any(|axis| axis.numerator() == 0);
            let aspect = if degenerate {
                Rational::from_ratio(1, 1)?
            } else if landscape {
                domain[0].div(domain[1])?
            } else {
                domain[1].div(domain[0])?
            };
            let target = aspect.mul_i128(n.into())?;
            let mut low = if degenerate { n } else { 1_u64 };
            let mut high = n;
            while low < high {
                let middle = low + (high - low) / 2;
                if target.le(Rational::from_ratio(
                    i128::from(middle) * i128::from(middle),
                    1,
                )?)? {
                    high = middle;
                } else {
                    low = middle + 1;
                }
            }
            let long_count = low;
            let short_count = n.div_ceil(long_count);
            let (columns, rows) = if landscape {
                (long_count, short_count)
            } else {
                (short_count, long_count)
            };
            let cell_width = domain[0].div_i128(columns.into())?;
            let cell_height = domain[1].div_i128(rows.into())?;
            let c = i128::from(columns);
            let q = i128::from(n / columns);
            let remainder = i128::from(n % columns);
            let centroid = [
                cell_width.mul_ratio(q * c * c + remainder * remainder, 2 * i128::from(n))?,
                cell_height.mul_ratio(c * q * q + remainder * (2 * q + 1), 2 * i128::from(n))?,
            ];
            PlacementRecipe::Grid {
                columns,
                rows,
                filled_count: n,
                cell_width,
                cell_height,
                centroid,
                translate_to_numeric_anchor,
            }
        }
    })
}

fn append_plan_attempt(
    attempt: InstructionLoweringAttempt<ObjectPlacementPlan>,
    owner: impl Fn(&ScoreFieldGap) -> ScoreDiagnosticOwner,
    unit: ScoreOmissionUnit,
    error_policy: ScoreErrorPolicy,
    objects: &mut Vec<ObjectPlacementPlan>,
    diagnostics: &mut Vec<ScoreLoweringDiagnostic>,
) -> Option<usize> {
    for omission in attempt.appearance_omissions {
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: owner(&omission.reason),
            disposition: diagnostic_disposition(
                error_policy,
                &omission.reason,
                ScoreOmissionUnit::AppearanceField {
                    field: omission.field,
                },
                Some(omission.resolution),
            ),
            reason: omission.reason,
        });
    }
    for omission in attempt.instruction_field_omissions {
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: owner(&omission.reason),
            disposition: diagnostic_disposition(
                error_policy,
                &omission.reason,
                ScoreOmissionUnit::InstructionField {
                    field: omission.field,
                },
                None,
            ),
            reason: omission.reason,
        });
    }
    for reason in attempt.remaining_gaps {
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: owner(&reason),
            disposition: diagnostic_disposition(error_policy, &reason, unit.clone(), None),
            reason,
        });
    }
    if let Some(object) = attempt.instruction {
        let index = objects.len();
        objects.push(object);
        Some(index)
    } else {
        None
    }
}

fn resolve_complete_object<'a>(
    input: ScoreLoweringInput<'a>,
    context: ScoreLoweringContext,
    planning: bool,
) -> Result<ResolvedObject, Vec<ScoreFieldGap>> {
    let mut gaps = Vec::new();
    let layout_direction = input.layout_direction.and_then(|direction| {
        let axis = (planning
            && input
                .action
                .is_some_and(|action| action.category == "movement" && action.id == "line_up")
            && direction.category == "angle")
            .then(|| {
                input.angle_context.and_then(|context| {
                    crate::score_angle::resolve_layout_direction(direction.id, context)
                })
            })
            .flatten();
        if let Some(axis) = axis {
            Some(crate::composition_plan::ResolvedLayoutDirection {
                identity: crate::SemanticIdentity {
                    category: direction.category.to_owned(),
                    id: direction.id.to_owned(),
                },
                axis,
            })
        } else {
            gaps.push(ScoreFieldGap::UnsupportedLayoutDirection {
                category: direction.category.to_owned(),
                id: direction.id.to_owned(),
            });
            None
        }
    });
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
    let mut rotation = if primitive == Primitive::Point && input.angle.is_some() {
        gaps.push(ScoreFieldGap::UnsupportedAngleForPrimitive { primitive });
        None
    } else {
        match input.angle {
            None => None,
            Some(identity) if identity.category != "angle" => {
                gaps.push(ScoreFieldGap::UnsupportedAngleIdentity {
                    category: identity.category.to_owned(),
                    id: identity.id.to_owned(),
                });
                None
            }
            Some(identity) => match input
                .angle_context
                .and_then(|context| resolve_score_angle(identity.id, context))
            {
                Some(rotation) => Some(rotation),
                None => {
                    gaps.push(ScoreFieldGap::UnsupportedAngleIdentity {
                        category: identity.category.to_owned(),
                        id: identity.id.to_owned(),
                    });
                    None
                }
            },
        }
    };
    let count = match input.count {
        Some(0) => {
            gaps.push(ScoreFieldGap::ExactCountZero { value: 0 });
            0
        }
        Some(1) => 1,
        Some(value) if planning && value <= u64::from(u32::MAX) => value as u32,
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
        None if planning
            && input.action.is_some_and(|action| {
                action.category == "movement" && matches!(action.id, "line_up" | "scatter" | "tile")
            }) =>
        {
            8
        }
        None => 1,
    };
    debug_assert!(
        planning || count <= 1,
        "finite lowering never materializes repeated count"
    );

    let color_cycle = input
        .color_cycle
        .iter()
        .filter_map(|item| {
            map_score_enum::<Color>(Some((&item.identity).into()), "color", &mut gaps)
        })
        .collect::<Vec<_>>();
    let color = match input.color {
        Some(_) => map_score_enum::<Color>(input.color, "color", &mut gaps),
        None => color_cycle
            .first()
            .copied()
            .or_else(|| resolve_omitted_color(context, &mut gaps)),
    };
    let weight = match input.touch {
        Some(_) => map_score_enum::<Weight>(input.touch, "touch", &mut gaps),
        None => Some(Weight::Pen),
    };
    let style = match input.continuity {
        Some(_) => map_score_enum::<LineStyle>(input.continuity, "continuity", &mut gaps),
        None => Some(LineStyle::Solid),
    };
    let arc_form = match input.proportion_arc_form {
        Some(identity)
            if primitive != Primitive::Arc
                || identity.category != "ratio"
                || !matches!(identity.id, "semicircle" | "waxing" | "waning" | "crescent") =>
        {
            gaps.push(ScoreFieldGap::ShapeConstraintMismatch { primitive });
            None
        }
        Some(identity) if identity.id == "crescent" => Some(inku_score::ArcForm::Crescent),
        Some(identity) => {
            let offset = match identity.id {
                "waxing" => 90.0,
                "waning" => 270.0,
                _ => 0.0,
            };
            if offset != 0.0 {
                rotation = Some((rotation.unwrap_or(0.0) + offset).rem_euclid(360.0));
            }
            None
        }
        None => None,
    };
    let (filled, surface) = if primitive == Primitive::Point && input.surface.is_some() {
        let identity = input.surface.expect("checked present Point surface");
        gaps.push(ScoreFieldGap::UnsupportedSurfaceIdentity {
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        });
        (true, None)
    } else {
        let closes_area = arc_form.is_some()
            || matches!(
                primitive,
                Primitive::Circle
                    | Primitive::Ellipse
                    | Primitive::Square
                    | Primitive::Triangle
                    | Primitive::Polygon
                    | Primitive::Point
                    | Primitive::Cloudform
            );
        match input.surface {
            Some(identity)
                if arc_form.is_some()
                    && (identity.category != "surface" || identity.id != "solid") =>
            {
                gaps.push(ScoreFieldGap::UnsupportedSurfaceIdentity {
                    category: identity.category.to_owned(),
                    id: identity.id.to_owned(),
                });
                (true, None)
            }
            Some(identity) if identity.category == "surface" && identity.id == "none" => {
                (false, None)
            }
            Some(identity) if identity.category == "surface" && identity.id == "solid" => {
                // An explicit fill can belong to the closed contour formed by
                // two checked Touching arcs. Keep that intent for performance.
                (closes_area || primitive == Primitive::Arc, None)
            }
            // A named surface texture is itself the area's performance. A flat
            // base fill under it would hide the texture entirely.
            Some(identity) => match surface_spec_from_identity(identity) {
                Ok(spec) => (false, Some(spec)),
                Err(gap) => {
                    gaps.push(gap);
                    (false, None)
                }
            },
            None => (closes_area, None),
        }
    };
    let surface_intensity = match input.surface_intensity {
        None => SurfaceIntensity::Normal,
        Some(identity)
            if identity.category == "surface"
                && filled
                && surface.is_none()
                && primitive != Primitive::Point
                && matches!(identity.id, "dense" | "faint") =>
        {
            if identity.id == "dense" {
                SurfaceIntensity::Dense
            } else {
                SurfaceIntensity::Faint
            }
        }
        Some(identity) => {
            gaps.push(ScoreFieldGap::UnsupportedSurfaceIntensity {
                category: identity.category.to_owned(),
                id: identity.id.to_owned(),
            });
            SurfaceIntensity::Normal
        }
    };
    let thinness = match input.thinness {
        None => None,
        Some(CoreModifierValue::Fine) => Some(Thinness::Fine),
        Some(CoreModifierValue::ExtraFine) => Some(Thinness::ExtraFine),
        Some(_) => {
            gaps.push(ScoreFieldGap::UnsupportedInstructionMeaning);
            None
        }
    };
    let action = match input.action {
        Some(identity)
            if identity.category == "movement"
                && identity.id == "draw"
                && matches!(primitive, Primitive::Line | Primitive::Arc) =>
        {
            PlacementAction::Place
        }
        Some(identity) if identity.category == "movement" && identity.id == "place" => {
            PlacementAction::Place
        }
        Some(identity)
            if planning && identity.category == "movement" && identity.id == "line_up" =>
        {
            PlacementAction::LineUp
        }
        Some(identity) if planning && identity.category == "movement" && identity.id == "tile" => {
            PlacementAction::Tile
        }
        Some(identity)
            if planning && identity.category == "movement" && identity.id == "scatter" =>
        {
            PlacementAction::Scatter
        }
        Some(identity) if planning && identity.category == "movement" && identity.id == "fill" => {
            PlacementAction::Fill
        }
        Some(identity) => {
            gaps.push(ScoreFieldGap::UnsupportedActionIdentity {
                category: identity.category.to_owned(),
                id: identity.id.to_owned(),
            });
            PlacementAction::Place
        }
        None => {
            gaps.push(ScoreFieldGap::MissingPlaceAction);
            PlacementAction::Place
        }
    };
    if !color_cycle.is_empty()
        && !matches!(
            action,
            PlacementAction::LineUp
                | PlacementAction::Tile
                | PlacementAction::Scatter
                | PlacementAction::Fill
        )
    {
        gaps.push(ScoreFieldGap::UnsupportedInstructionMeaning);
    }
    let named_focus = if input.has_named_position && input.exact_position().is_some() {
        gaps.push(ScoreFieldGap::NamedAndNumericPositionConflict);
        None
    } else if let Some(region) = input.group_region {
        Some(region)
    } else if input.has_named_position {
        if let Some(region) = input
            .named_position
            .filter(|place| place.category == "place")
            .and_then(|place| {
                crate::geometry::resolved_position_bounds(
                    Some(place.id),
                    input.effective_focus,
                    input.angle_context.expect("verified occurrence"),
                )
            })
        {
            Some(region)
        } else {
            gaps.push(ScoreFieldGap::UnsupportedNamedPosition);
            None
        }
    } else if input.exact_position().is_none() && action == PlacementAction::Fill {
        Some([0.0, 0.0, 1.0, 1.0])
    } else if input.exact_position().is_none() {
        crate::geometry::resolved_position_bounds(
            None,
            input.effective_focus,
            input.angle_context.expect("verified occurrence"),
        )
    } else {
        None
    };
    if input.exact_geometry().is_none()
        && !matches!(
            primitive,
            Primitive::Line
                | Primitive::Circle
                | Primitive::Ellipse
                | Primitive::Cloudform
                | Primitive::Square
                | Primitive::Triangle
                | Primitive::Polygon
                | Primitive::Arc
                | Primitive::Point
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
    let ink_spread = match input.ink_spread {
        None => None,
        Some(identity) if identity.category == "variation" && identity.id == "bleeding" => {
            Some(inku_score::InkSpread::Bleed)
        }
        Some(_) => {
            gaps.push(ScoreFieldGap::UnsupportedInstructionMeaning);
            None
        }
    };
    let variation = if input
        .fluctuation
        .iter()
        .flatten()
        .any(|identity| identity.category != "variation")
    {
        gaps.push(ScoreFieldGap::UnsupportedInstructionMeaning);
        None
    } else {
        match crate::fluctuation::resolve_fluctuation(
            input.fluctuation[0].map(|identity| identity.id),
            input.fluctuation[1].map(|identity| identity.id),
            input.fluctuation[2].map(|identity| identity.id),
        ) {
            Ok(variation) => variation,
            Err(()) => {
                gaps.push(ScoreFieldGap::UnsupportedInstructionMeaning);
                None
            }
        }
    };
    if variation.is_some()
        && !matches!(
            primitive,
            Primitive::Line
                | Primitive::Arc
                | Primitive::Circle
                | Primitive::Ellipse
                | Primitive::Square
                | Primitive::Triangle
                | Primitive::Polygon
                | Primitive::Cloudform
        )
    {
        gaps.push(ScoreFieldGap::UnsupportedInstructionMeaning);
    }
    if !gaps.is_empty() {
        return Err(gaps);
    }

    let placement = match (input.exact_position(), named_focus) {
        (Some(position), None) => ScorePlacement::Numeric(position),
        (None, Some(focus)) => ScorePlacement::Named(focus),
        _ => unreachable!("checked position authority"),
    };
    let (dimensions, _) =
        resolve_size_candidates(input, context, primitive).map_err(|gap| vec![gap])?;
    if let ScorePlacement::Numeric(position) = placement {
        let x = Rational::from_decimal(position.x).map_err(|gap| vec![gap])?;
        let y = Rational::from_decimal(position.y).map_err(|gap| vec![gap])?;
        if !x.in_unit_interval() || !y.in_unit_interval() {
            return Err(vec![ScoreFieldGap::PositionOutOfRange]);
        }
    }
    Ok(ResolvedObject {
        arc_form,
        primitive,
        count,
        action,
        dimensions,
        placement,
        rotation,
        layout_direction,
        appearance: ResolvedObjectAppearance {
            filled,
            continuity: style.expect("checked continuity"),
            touch: weight.expect("checked touch"),
            color: color.expect("checked color"),
            fluctuation: variation,
            ink_spread,
            thinness,
            surface,
            surface_intensity,
        },
        color_cycle,
    })
}

fn surface_spec_from_identity(
    identity: SemanticInputIdentity<'_>,
) -> Result<SurfaceSpec, ScoreFieldGap> {
    let texture: SurfaceTexture = match (identity.category, identity.id) {
        (
            "surface",
            "wash" | "grain" | "stipple" | "hatch" | "crosshatch" | "bleed" | "aquatint",
        ) => serde_json::from_value(serde_json::Value::String(identity.id.to_owned())).map_err(
            |_| ScoreFieldGap::UnsupportedSurfaceIdentity {
                category: identity.category.to_owned(),
                id: identity.id.to_owned(),
            },
        )?,
        _ => {
            return Err(ScoreFieldGap::UnsupportedSurfaceIdentity {
                category: identity.category.to_owned(),
                id: identity.id.to_owned(),
            });
        }
    };
    Ok(
        serde_json::from_value(serde_json::json!({ "texture": texture }))
            .expect("shared SurfaceSpec defaults accept a supported texture"),
    )
}

fn canvas_ground_spec_from_identity(
    identity: &SemanticIdentity,
) -> Result<CanvasGroundSpec, ScoreFieldGap> {
    let material: GroundMaterial = match (identity.category.as_str(), identity.id.as_str()) {
        (
            "ground",
            "paper" | "washi" | "ink_wash" | "charcoal_ground" | "canvas" | "drawing_paper"
            | "mezzotint",
        ) => serde_json::from_value(serde_json::Value::String(identity.id.clone()))
            .map_err(|_| ScoreFieldGap::UnsupportedGround)?,
        _ => return Err(ScoreFieldGap::UnsupportedGround),
    };
    Ok(
        serde_json::from_value(serde_json::json!({ "material": material }))
            .expect("shared CanvasGroundSpec defaults accept a supported material"),
    )
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
    from: Option<Point>,
    to: Option<Point>,
    center: Option<Point>,
    radius: Option<f64>,
    position: Option<Point>,
    size: Option<Point>,
    angle_start: Option<f64>,
    angle_end: Option<f64>,
    at: Option<AtRegion>,
}

#[derive(Clone, Copy)]
enum ScorePlacement {
    Numeric(crate::geometry::ExactPosition),
    Named([f64; 4]),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ResolvedGeometryDimensions {
    Bbox { width: Rational, height: Rational },
    RegularTriangle { side: Rational },
    Polygon { radius: Rational, sides: u8 },
    Line { length: Rational },
    Circle { radius: Rational },
    Arc { chord: Rational, sagitta: Rational },
    Point { radius: Rational },
    CenteredSize { width: Rational, height: Rational },
    Square { side: Rational },
}

/// The reference extent is measured before any instruction rotation or ink variation.
pub(crate) fn reference_extent(
    dimensions: ResolvedGeometryDimensions,
) -> Result<Rational, ScoreFieldGap> {
    match dimensions {
        ResolvedGeometryDimensions::Bbox { width, .. }
        | ResolvedGeometryDimensions::CenteredSize { width, .. } => Ok(width),
        ResolvedGeometryDimensions::RegularTriangle { side }
        | ResolvedGeometryDimensions::Square { side } => Ok(side),
        ResolvedGeometryDimensions::Line { length } => Ok(length),
        ResolvedGeometryDimensions::Arc { chord, .. } => Ok(chord),
        ResolvedGeometryDimensions::Circle { radius }
        | ResolvedGeometryDimensions::Point { radius } => radius.mul_i128(2),
        ResolvedGeometryDimensions::Polygon { radius, sides } => {
            let mut minimum = f64::INFINITY;
            let mut maximum = f64::NEG_INFINITY;
            for vertex in 0..sides {
                let angle = -std::f64::consts::FRAC_PI_2
                    + std::f64::consts::TAU * f64::from(vertex) / f64::from(sides);
                minimum = minimum.min(angle.cos());
                maximum = maximum.max(angle.cos());
            }
            radius.mul(finite_geometry_ratio(maximum - minimum)?)
        }
    }
}

// Curved reference bounds and regular polygon trigonometry have one finite precision boundary.
fn finite_geometry_ratio(value: f64) -> Result<Rational, ScoreFieldGap> {
    if !value.is_finite() || value <= 0.0 || value > 1_000_000.0 {
        return Err(ScoreFieldGap::GeometryRepresentationLimit);
    }
    Rational::from_ratio(
        (value * 1_000_000_000_000.0).round() as i128,
        1_000_000_000_000,
    )
}

fn scale_dimensions(
    dimensions: ResolvedGeometryDimensions,
    factor: Rational,
) -> Result<ResolvedGeometryDimensions, ScoreFieldGap> {
    let factor = reduced_ratio(factor);
    Ok(match dimensions {
        ResolvedGeometryDimensions::Bbox { width, height } => ResolvedGeometryDimensions::Bbox {
            width: width.mul(factor)?,
            height: height.mul(factor)?,
        },
        ResolvedGeometryDimensions::CenteredSize { width, height } => {
            ResolvedGeometryDimensions::CenteredSize {
                width: width.mul(factor)?,
                height: height.mul(factor)?,
            }
        }
        ResolvedGeometryDimensions::RegularTriangle { side } => {
            ResolvedGeometryDimensions::RegularTriangle {
                side: side.mul(factor)?,
            }
        }
        ResolvedGeometryDimensions::Square { side } => ResolvedGeometryDimensions::Square {
            side: side.mul(factor)?,
        },
        ResolvedGeometryDimensions::Line { length } => ResolvedGeometryDimensions::Line {
            length: length.mul(factor)?,
        },
        ResolvedGeometryDimensions::Arc { chord, sagitta } => ResolvedGeometryDimensions::Arc {
            chord: chord.mul(factor)?,
            sagitta: sagitta.mul(factor)?,
        },
        ResolvedGeometryDimensions::Circle { radius } => ResolvedGeometryDimensions::Circle {
            radius: radius.mul(factor)?,
        },
        ResolvedGeometryDimensions::Point { radius } => ResolvedGeometryDimensions::Point {
            radius: radius.mul(factor)?,
        },
        ResolvedGeometryDimensions::Polygon { radius, sides } => {
            ResolvedGeometryDimensions::Polygon {
                radius: radius.mul(factor)?,
                sides,
            }
        }
    })
}

fn reduced_ratio(value: Rational) -> Rational {
    let mut a = value.numerator.unsigned_abs();
    let mut b = value.denominator as u128;
    while b != 0 {
        (a, b) = (b, a % b);
    }
    let divisor = a.max(1) as i128;
    Rational {
        numerator: value.numerator / divisor,
        denominator: value.denominator / divisor,
    }
}

fn resolve_size_candidates(
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
    primitive: Primitive,
) -> Result<(ResolvedGeometryDimensions, Vec<Rational>), ScoreFieldGap> {
    let resolve = |geometry: Option<crate::geometry::ExactGeometry>,
                   scale: Option<CoreModifierValue>|
     -> Result<ResolvedGeometryDimensions, ScoreFieldGap> {
        if let Some(form) = input.proportion_arc_form {
            if primitive != Primitive::Arc || form.category != "ratio" {
                return Err(ScoreFieldGap::ShapeConstraintMismatch { primitive });
            }
            if form.id == "crescent" {
                if input.proportion_aspect.is_some()
                    || input
                        .shape_constraint
                        .is_some_and(|constraint| constraint.regular || constraint.sides.is_some())
                {
                    return Err(ScoreFieldGap::ShapeConstraintMismatch { primitive });
                }
                let normal =
                    Rational::from_ratio(NORMAL_SHORT_EDGE_RATIO.0, NORMAL_SHORT_EDGE_RATIO.1)?;
                let width = match geometry {
                    None => {
                        let (n, d) =
                            relative_scale_factor(scale.unwrap_or(CoreModifierValue::Normal))
                                .ok_or(ScoreFieldGap::ShapeConstraintMismatch { primitive })?;
                        normal.mul_ratio(n, d)?
                    }
                    Some(crate::geometry::ExactGeometry::WidthHeight { width, height }) => {
                        let width = positive(width)?;
                        let height = positive(height)?;
                        if (width.div(height)?.to_f64()?
                            - inku_score::crescent_reference_aspect_ratio())
                        .abs()
                            > 1e-9
                        {
                            return Err(ScoreFieldGap::ShapeConstraintMismatch { primitive });
                        }
                        width
                    }
                    _ => return Err(ScoreFieldGap::GeometryDimensionMismatch { primitive }),
                };
                return Ok(ResolvedGeometryDimensions::CenteredSize {
                    width,
                    height: width.mul(finite_geometry_ratio(
                        1.0 / inku_score::crescent_reference_aspect_ratio(),
                    )?)?,
                });
            }
            if !matches!(form.id, "semicircle" | "waxing" | "waning") {
                return Err(ScoreFieldGap::ShapeConstraintMismatch { primitive });
            }
            let dimensions = resolve_shape_dimensions(
                primitive,
                geometry,
                scale,
                input.shape_constraint,
                input.proportion_aspect,
            )?;
            let ResolvedGeometryDimensions::Arc { chord, sagitta } = dimensions else {
                return Err(ScoreFieldGap::GeometryDimensionMismatch { primitive });
            };
            let half = chord.div_i128(2)?;
            if geometry.is_some() && !(sagitta.le(half)? && half.le(sagitta)?) {
                return Err(ScoreFieldGap::ShapeConstraintMismatch { primitive });
            }
            return Ok(ResolvedGeometryDimensions::Arc {
                chord,
                sagitta: chord.div_i128(2)?,
            });
        }
        resolve_shape_dimensions(
            primitive,
            geometry,
            scale,
            input.shape_constraint,
            input.proportion_aspect,
        )
    };
    // Every size is an independent proposal. Relative size is never applied to an explicit size.
    let base = resolve(input.exact_geometry(), None)?;
    let mut candidates = Vec::new();
    for geometry in input
        .explicit_geometry
        .into_iter()
        .chain(input.additional_explicit_geometries.iter())
        .map(crate::geometry::ExactGeometry::from)
        .chain(input.generated_geometries.into_iter().flatten())
    {
        candidates.push(reference_extent(resolve(Some(geometry), None)?)?);
    }
    for scale in input.relative_scale.into_iter().chain(
        input
            .additional_relative_scales
            .iter()
            .map(|value| value.value),
    ) {
        candidates.push(reference_extent(resolve(None, Some(scale))?)?);
    }
    let (width, height) = context.canvas_format.integer_ratio();
    let canvas_width = Rational::from_ratio(width.into(), width.min(height).into())?;
    for extent in input.proportion_width_extent.into_iter().chain(
        input
            .additional_width_extents
            .iter()
            .map(|term| (&term.identity).into()),
    ) {
        let factor = match (extent.category, extent.id) {
            ("ratio", "full_width") => 1,
            ("ratio", "half_width") => 2,
            _ => return Err(ScoreFieldGap::ShapeConstraintMismatch { primitive }),
        };
        candidates.push(canvas_width.div_i128(factor)?);
    }
    let Some(mut effective) = candidates.first().copied() else {
        return Ok((base, candidates));
    };
    for candidate in &candidates[1..] {
        if candidate.le(effective)? {
            effective = *candidate;
        }
    }
    let base_extent = reference_extent(base)?;
    if effective.le(base_extent)? && base_extent.le(effective)? {
        return Ok((base, candidates));
    }
    Ok((
        scale_dimensions(base, effective.div(base_extent)?)?,
        candidates,
    ))
}

fn size_recovery_diagnostic(
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
) -> Option<ScoreFieldGap> {
    let primitive = score_primitive_from_identity(input.primitive).ok()?;
    let (dimensions, candidate_extents) =
        resolve_size_candidates(input, context, primitive).ok()?;
    (candidate_extents.len() > 1).then(|| ScoreFieldGap::ConflictingSizeSpecifications {
        candidate_extents,
        effective_extent: reference_extent(dimensions).expect("validated effective extent"),
    })
}

fn resolve_shape_dimensions(
    primitive: Primitive,
    geometry: Option<crate::geometry::ExactGeometry>,
    scale: Option<CoreModifierValue>,
    constraint: Option<crate::ShapeConstraint>,
    aspect: Option<SemanticInputIdentity<'_>>,
) -> Result<ResolvedGeometryDimensions, ScoreFieldGap> {
    let constraint = constraint.unwrap_or_default();
    let invalid = || ScoreFieldGap::ShapeConstraintMismatch { primitive };
    if constraint.sides.is_some() && primitive != Primitive::Polygon
        || constraint.regular
            && !matches!(
                primitive,
                Primitive::Triangle | Primitive::Square | Primitive::Polygon
            )
    {
        return Err(invalid());
    }
    if let Some(aspect) = aspect {
        if aspect.category != "ratio"
            || !matches!(aspect.id, "tall" | "wide")
            || !matches!(
                primitive,
                Primitive::Triangle | Primitive::Square | Primitive::Ellipse | Primitive::Cloudform
            )
            || constraint.regular
        {
            return Err(invalid());
        }
    }
    let normal = || -> Result<Rational, ScoreFieldGap> {
        let (n, d) = relative_scale_factor(scale.unwrap_or(CoreModifierValue::Normal))
            .ok_or_else(invalid)?;
        Rational::from_ratio(NORMAL_SHORT_EDGE_RATIO.0, NORMAL_SHORT_EDGE_RATIO.1)?.mul_ratio(n, d)
    };
    if primitive == Primitive::Polygon {
        let sides = constraint.sides.unwrap_or(5);
        if !(5..=8).contains(&sides) {
            return Err(invalid());
        }
        let radius = match geometry {
            None => normal()?.div_i128(2)?,
            Some(crate::geometry::ExactGeometry::Radius(value)) => positive(value)?,
            Some(crate::geometry::ExactGeometry::Diameter(value)) => {
                positive(value)?.div_i128(2)?
            }
            _ => return Err(invalid()),
        };
        return Ok(ResolvedGeometryDimensions::Polygon {
            radius,
            sides: sides as u8,
        });
    }
    if primitive == Primitive::Triangle && constraint.regular {
        let side = match geometry {
            None => normal()?,
            Some(crate::geometry::ExactGeometry::Side(value)) => positive(value)?,
            _ => return Err(invalid()),
        };
        return Ok(ResolvedGeometryDimensions::RegularTriangle { side });
    }
    if matches!(primitive, Primitive::Triangle | Primitive::Square) || aspect.is_some() {
        let (width, height) = match geometry {
            Some(crate::geometry::ExactGeometry::WidthHeight { width, height }) => {
                (positive(width)?, positive(height)?)
            }
            Some(crate::geometry::ExactGeometry::Side(value)) if primitive == Primitive::Square => {
                let side = positive(value)?;
                (side, side)
            }
            None => {
                let long = normal()?;
                match aspect.map(|value| value.id) {
                    Some("tall") => (long.div_i128(2)?, long),
                    Some("wide") => (long, long.div_i128(2)?),
                    _ => (long, long),
                }
            }
            _ => return Err(invalid()),
        };
        if constraint.regular && width != height {
            return Err(invalid());
        }
        if let Some(aspect) = aspect {
            if aspect.id == "tall" && height.le(width)?
                || aspect.id == "wide" && width.le(height)?
            {
                return Err(invalid());
            }
        }
        return Ok(
            if matches!(primitive, Primitive::Triangle | Primitive::Square) {
                if primitive == Primitive::Square && width == height {
                    ResolvedGeometryDimensions::Square { side: width }
                } else {
                    ResolvedGeometryDimensions::Bbox { width, height }
                }
            } else {
                ResolvedGeometryDimensions::CenteredSize { width, height }
            },
        );
    }
    resolve_geometry_dimensions(primitive, geometry, scale)
}

fn resolve_geometry_dimensions(
    primitive: Primitive,
    geometry: Option<crate::geometry::ExactGeometry>,
    relative_scale: Option<CoreModifierValue>,
) -> Result<ResolvedGeometryDimensions, ScoreFieldGap> {
    let Some(geometry) = geometry else {
        return resolve_normal_dimensions(
            primitive,
            relative_scale.unwrap_or(CoreModifierValue::Normal),
        );
    };

    match (primitive, geometry) {
        (Primitive::Line, crate::geometry::ExactGeometry::Length(value)) => {
            Ok(ResolvedGeometryDimensions::Line {
                length: positive(value)?,
            })
        }
        (Primitive::Circle, crate::geometry::ExactGeometry::Radius(value))
        | (Primitive::Circle, crate::geometry::ExactGeometry::Diameter(value))
        | (Primitive::Point, crate::geometry::ExactGeometry::Radius(value))
        | (Primitive::Point, crate::geometry::ExactGeometry::Diameter(value)) => {
            let mut radius = positive(value)?;
            if matches!(geometry, crate::geometry::ExactGeometry::Diameter(_)) {
                radius = radius.div_i128(2)?;
            }
            Ok(if primitive == Primitive::Point {
                ResolvedGeometryDimensions::Point { radius }
            } else {
                ResolvedGeometryDimensions::Circle { radius }
            })
        }
        (Primitive::Arc, crate::geometry::ExactGeometry::ChordSagitta { chord, sagitta }) => {
            let chord = positive(chord)?;
            let sagitta = positive(sagitta)?;
            if !sagitta.le(chord.div_i128(2)?)? {
                return Err(ScoreFieldGap::GeometryDimensionMismatch { primitive });
            }
            Ok(ResolvedGeometryDimensions::Arc { chord, sagitta })
        }
        (
            Primitive::Ellipse | Primitive::Cloudform,
            crate::geometry::ExactGeometry::WidthHeight { width, height },
        ) => Ok(ResolvedGeometryDimensions::CenteredSize {
            width: positive(width)?,
            height: positive(height)?,
        }),
        (Primitive::Square, crate::geometry::ExactGeometry::Side(value)) => {
            Ok(ResolvedGeometryDimensions::Square {
                side: positive(value)?,
            })
        }
        (
            Primitive::Line
            | Primitive::Circle
            | Primitive::Ellipse
            | Primitive::Cloudform
            | Primitive::Square
            | Primitive::Arc
            | Primitive::Point,
            _,
        ) => Err(ScoreFieldGap::GeometryDimensionMismatch { primitive }),
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
        Primitive::Line => Ok(ResolvedGeometryDimensions::Line { length: width }),
        Primitive::Circle => Ok(ResolvedGeometryDimensions::Circle {
            radius: width.div_i128(2)?,
        }),
        Primitive::Arc => Ok(ResolvedGeometryDimensions::Arc {
            chord: width,
            sagitta: width.div_i128(4)?,
        }),
        Primitive::Point => Ok(ResolvedGeometryDimensions::Point {
            radius: Rational::from_ratio(3, 500)?
                .mul_ratio(factor_numerator, factor_denominator)?,
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
    primitive: Primitive,
    dimensions: ResolvedGeometryDimensions,
    position: crate::geometry::ExactPosition,
    canvas: CanvasFormat,
    rotation: Option<f64>,
) -> Result<LoweredGeometry, ScoreFieldGap> {
    let x = Rational::from_decimal(position.x)?;
    let y = Rational::from_decimal(position.y)?;
    if !x.in_unit_interval() || !y.in_unit_interval() {
        return Err(ScoreFieldGap::PositionOutOfRange);
    }
    let center = Point::new(x.to_f64()?, y.to_f64()?);
    let (width_units, height_units) = canvas.integer_ratio();
    let short_units = width_units.min(height_units);

    match dimensions {
        ResolvedGeometryDimensions::Bbox { width, height } => lower_vertex_geometry(
            primitive,
            x,
            y,
            width.to_f64()?,
            height.to_f64()?,
            None,
            canvas,
            rotation,
        ),
        ResolvedGeometryDimensions::RegularTriangle { side } => {
            let side = side.to_f64()?;
            lower_vertex_geometry(
                primitive,
                x,
                y,
                side,
                side * 3.0_f64.sqrt() / 2.0,
                None,
                canvas,
                rotation,
            )
        }
        ResolvedGeometryDimensions::Polygon { radius, sides } => lower_vertex_geometry(
            primitive,
            x,
            y,
            0.0,
            0.0,
            Some((radius.to_f64()?, sides)),
            canvas,
            rotation,
        ),
        ResolvedGeometryDimensions::Line { length } => {
            ensure_rotated_centered_extent(
                Primitive::Line,
                x,
                y,
                length,
                Rational::from_ratio(0, 1)?,
                width_units,
                height_units,
                short_units,
                rotation,
            )?;
            let half_x = length
                .div_i128(2)?
                .mul_ratio(i128::from(short_units), i128::from(width_units))?;
            Ok(LoweredGeometry {
                from: Some(Point::new(x.sub(half_x)?.to_f64()?, y.to_f64()?)),
                to: Some(Point::new(x.add(half_x)?.to_f64()?, y.to_f64()?)),
                center: None,
                radius: None,
                position: None,
                size: None,
                angle_start: None,
                angle_end: None,
                at: None,
            })
        }
        ResolvedGeometryDimensions::Circle { radius } => {
            ensure_centered_extent(x, y, radius, radius, width_units, height_units, short_units)?;
            Ok(LoweredGeometry {
                from: None,
                to: None,
                center: Some(center),
                radius: Some(radius.to_f64()?),
                position: None,
                size: None,
                angle_start: None,
                angle_end: None,
                at: None,
            })
        }
        ResolvedGeometryDimensions::Arc { chord, sagitta } => {
            let (radius, start, end) = arc_parameters(chord, sagitta)?;
            ensure_arc_extent(
                x,
                y,
                radius,
                start,
                end,
                rotation,
                width_units,
                height_units,
                short_units,
            )?;
            let offset_y = radius
                .sub(sagitta)?
                .mul_ratio(i128::from(short_units), i128::from(height_units))?;
            Ok(LoweredGeometry {
                from: None,
                to: None,
                center: Some(Point::new(x.to_f64()?, y.add(offset_y)?.to_f64()?)),
                radius: Some(radius.to_f64()?),
                position: Some(center),
                size: None,
                angle_start: Some(start),
                angle_end: Some(end),
                at: None,
            })
        }
        ResolvedGeometryDimensions::Point { radius } => {
            ensure_centered_extent(x, y, radius, radius, width_units, height_units, short_units)?;
            Ok(LoweredGeometry {
                from: None,
                to: None,
                center: Some(center),
                radius: Some(radius.to_f64()?),
                position: None,
                size: None,
                angle_start: None,
                angle_end: None,
                at: None,
            })
        }
        ResolvedGeometryDimensions::CenteredSize { width, height } => {
            if primitive == Primitive::Arc {
                let scale_x = f64::from(width_units) / f64::from(short_units);
                let scale_y = f64::from(height_units) / f64::from(short_units);
                let (minimum, maximum) = inku_score::crescent_contour_bounds(
                    Point::new(center.x * scale_x, center.y * scale_y),
                    Point::new(width.to_f64()?, height.to_f64()?),
                    rotation.unwrap_or(0.0),
                );
                let epsilon = 1e-12;
                if minimum.x < -epsilon
                    || minimum.y < -epsilon
                    || maximum.x > scale_x + epsilon
                    || maximum.y > scale_y + epsilon
                {
                    return Err(ScoreFieldGap::GeometryExtentOutOfBounds);
                }
            } else {
                ensure_rotated_centered_extent(
                    primitive,
                    x,
                    y,
                    width,
                    height,
                    width_units,
                    height_units,
                    short_units,
                    rotation,
                )?;
            }
            Ok(LoweredGeometry {
                from: None,
                to: None,
                center: Some(center),
                radius: None,
                position: None,
                size: Some(Point::new(width.to_f64()?, height.to_f64()?)),
                angle_start: None,
                angle_end: None,
                at: None,
            })
        }
        ResolvedGeometryDimensions::Square { side } => {
            ensure_rotated_centered_extent(
                Primitive::Square,
                x,
                y,
                side,
                side,
                width_units,
                height_units,
                short_units,
                rotation,
            )?;
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
                from: None,
                to: None,
                center: None,
                radius: None,
                position: Some(Point::new(top_left_x.to_f64()?, top_left_y.to_f64()?)),
                size: Some(Point::new(side.to_f64()?, side.to_f64()?)),
                angle_start: None,
                angle_end: None,
                at: None,
            })
        }
    }
}

fn ensure_rotated_centered_extent(
    primitive: Primitive,
    x: Rational,
    y: Rational,
    width: Rational,
    height: Rational,
    width_units: u32,
    height_units: u32,
    short_units: u32,
    rotation: Option<f64>,
) -> Result<(), ScoreFieldGap> {
    let normalized = rotation.unwrap_or(0.0).rem_euclid(360.0);
    if normalized == 0.0 || normalized == 180.0 {
        return ensure_centered_extent(
            x,
            y,
            width.div_i128(2)?,
            height.div_i128(2)?,
            width_units,
            height_units,
            short_units,
        );
    }
    if normalized == 90.0 || normalized == 270.0 {
        return ensure_centered_extent(
            x,
            y,
            height.div_i128(2)?,
            width.div_i128(2)?,
            width_units,
            height_units,
            short_units,
        );
    }

    let radians = normalized.to_radians();
    let cosine = radians.cos().abs();
    let sine = radians.sin().abs();
    let half_width = width.to_f64()? * f64::from(short_units) / 2.0;
    let half_height = height.to_f64()? * f64::from(short_units) / 2.0;
    let (physical_extent_x, physical_extent_y) = match primitive {
        Primitive::Ellipse => (
            (half_width * cosine).hypot(half_height * sine),
            (half_width * sine).hypot(half_height * cosine),
        ),
        Primitive::Line | Primitive::Cloudform | Primitive::Square | Primitive::Arc => (
            cosine * half_width + sine * half_height,
            sine * half_width + cosine * half_height,
        ),
        _ => {
            unreachable!("only line, ellipse, cloudform, and square dimensions use rotated extents")
        }
    };
    let extent_x = physical_extent_x / f64::from(width_units);
    let extent_y = physical_extent_y / f64::from(height_units);
    let center_x = x.to_f64()?;
    let center_y = y.to_f64()?;
    if !extent_x.is_finite()
        || !extent_y.is_finite()
        || !(0.0..=1.0).contains(&(center_x - extent_x))
        || !(0.0..=1.0).contains(&(center_x + extent_x))
        || !(0.0..=1.0).contains(&(center_y - extent_y))
        || !(0.0..=1.0).contains(&(center_y + extent_y))
    {
        return Err(ScoreFieldGap::GeometryExtentOutOfBounds);
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn lower_vertex_geometry(
    primitive: Primitive,
    x: Rational,
    y: Rational,
    width: f64,
    height: f64,
    polygon: Option<(f64, u8)>,
    canvas: CanvasFormat,
    rotation: Option<f64>,
) -> Result<LoweredGeometry, ScoreFieldGap> {
    let (cw, ch) = canvas.integer_ratio();
    let short = f64::from(cw.min(ch));
    let cx = x.to_f64()? * f64::from(cw) / short;
    let cy = y.to_f64()? * f64::from(ch) / short;
    let radians = rotation.unwrap_or(0.0).to_radians();
    let (sine, cosine) = radians.sin_cos();
    let check = |dx: f64, dy: f64| -> Result<(), ScoreFieldGap> {
        let px = (cx + dx * cosine - dy * sine) * short / f64::from(cw);
        let py = (cy + dx * sine + dy * cosine) * short / f64::from(ch);
        if !px.is_finite()
            || !py.is_finite()
            || !(0.0..=1.0).contains(&px)
            || !(0.0..=1.0).contains(&py)
        {
            return Err(ScoreFieldGap::GeometryExtentOutOfBounds);
        }
        Ok(())
    };
    if let Some((radius, sides)) = polygon {
        for vertex in 0..sides {
            let angle = -std::f64::consts::FRAC_PI_2
                + std::f64::consts::TAU * f64::from(vertex) / f64::from(sides);
            check(radius * angle.cos(), radius * angle.sin())?;
        }
    } else if primitive == Primitive::Triangle {
        for (dx, dy) in [
            (0.0, -height / 2.0),
            (-width / 2.0, height / 2.0),
            (width / 2.0, height / 2.0),
        ] {
            check(dx, dy)?;
        }
    } else {
        for (dx, dy) in [
            (-width / 2.0, -height / 2.0),
            (width / 2.0, -height / 2.0),
            (-width / 2.0, height / 2.0),
            (width / 2.0, height / 2.0),
        ] {
            check(dx, dy)?;
        }
    }
    Ok(LoweredGeometry {
        from: None,
        to: None,
        center: polygon.map(|_| {
            Point::new(
                x.to_f64().expect("checked x"),
                y.to_f64().expect("checked y"),
            )
        }),
        radius: polygon.map(|value| value.0),
        position: polygon.is_none().then_some(Point::new(
            (cx - width / 2.0) * short / f64::from(cw),
            (cy - height / 2.0) * short / f64::from(ch),
        )),
        size: polygon.is_none().then_some(Point::new(width, height)),
        angle_start: None,
        angle_end: None,
        at: None,
    })
}

fn lower_named_geometry(
    dimensions: ResolvedGeometryDimensions,
    region: [f64; 4],
    canvas: CanvasFormat,
) -> Result<LoweredGeometry, ScoreFieldGap> {
    let (width_units, height_units) = canvas.integer_ratio();
    let short_units = width_units.min(height_units);
    let mut lowered = LoweredGeometry {
        from: None,
        to: None,
        center: None,
        radius: None,
        position: None,
        size: None,
        angle_start: None,
        angle_end: None,
        at: Some(AtRegion { region }),
    };
    match dimensions {
        ResolvedGeometryDimensions::Bbox { width, height } => {
            lowered.size = Some(Point::new(width.to_f64()?, height.to_f64()?));
        }
        ResolvedGeometryDimensions::RegularTriangle { side } => {
            let side = side.to_f64()?;
            lowered.size = Some(Point::new(side, side * 3.0_f64.sqrt() / 2.0));
        }
        ResolvedGeometryDimensions::Polygon { radius, .. } => {
            lowered.radius = Some(radius.to_f64()?);
        }
        ResolvedGeometryDimensions::Line { length } => {
            let half_x = length.to_f64()? * f64::from(short_units) / (2.0 * f64::from(width_units));
            lowered.from = Some(Point::new(0.5 - half_x, 0.5));
            lowered.to = Some(Point::new(0.5 + half_x, 0.5));
        }
        ResolvedGeometryDimensions::Circle { radius }
        | ResolvedGeometryDimensions::Point { radius } => {
            lowered.radius = Some(radius.to_f64()?);
        }
        ResolvedGeometryDimensions::Arc { chord, sagitta } => {
            let (radius, start, end) = arc_parameters(chord, sagitta)?;
            let offset_y =
                radius.sub(sagitta)?.to_f64()? * f64::from(short_units) / f64::from(height_units);
            lowered.center = Some(Point::new(0.5, 0.5 + offset_y));
            lowered.position = Some(Point::new(0.5, 0.5));
            lowered.radius = Some(radius.to_f64()?);
            lowered.angle_start = Some(start);
            lowered.angle_end = Some(end);
        }
        ResolvedGeometryDimensions::CenteredSize { width, height } => {
            lowered.size = Some(Point::new(width.to_f64()?, height.to_f64()?));
        }
        ResolvedGeometryDimensions::Square { side } => {
            lowered.size = Some(Point::new(side.to_f64()?, side.to_f64()?));
        }
    }
    Ok(lowered)
}

fn arc_parameters(
    chord: Rational,
    sagitta: Rational,
) -> Result<(Rational, f64, f64), ScoreFieldGap> {
    let radius = chord
        .mul(chord)?
        .div(sagitta.mul_i128(8)?)?
        .add(sagitta.div_i128(2)?)?;
    let ratio = chord.div(radius.mul_i128(2)?)?.to_f64()?;
    if !ratio.is_finite() || !(0.0..=1.0).contains(&ratio) {
        return Err(ScoreFieldGap::GeometryRepresentationLimit);
    }
    let half_angle = ratio.asin().to_degrees();
    Ok((radius, 90.0 + half_angle, 90.0 - half_angle))
}

#[allow(clippy::too_many_arguments)]
fn ensure_arc_extent(
    x: Rational,
    y: Rational,
    radius: Rational,
    start: f64,
    end: f64,
    rotation: Option<f64>,
    width_units: u32,
    height_units: u32,
    short_units: u32,
) -> Result<(), ScoreFieldGap> {
    let anchor_x = x.to_f64()? * f64::from(width_units);
    let anchor_y = y.to_f64()? * f64::from(height_units);
    let radius = radius.to_f64()? * f64::from(short_units);
    let center_y = anchor_y + radius * start.to_radians().sin();
    let rotation = rotation.unwrap_or(0.0).to_radians();
    for step in 0..=64 {
        let t = f64::from(step) / 64.0;
        let angle = (start + (end - start) * t).to_radians();
        let point_x = anchor_x + radius * angle.cos();
        let point_y = center_y - radius * angle.sin();
        let delta_x = point_x - anchor_x;
        let delta_y = point_y - anchor_y;
        let rotated_x = anchor_x + delta_x * rotation.cos() - delta_y * rotation.sin();
        let rotated_y = anchor_y + delta_x * rotation.sin() + delta_y * rotation.cos();
        if !rotated_x.is_finite()
            || !rotated_y.is_finite()
            || !(0.0..=f64::from(width_units)).contains(&rotated_x)
            || !(0.0..=f64::from(height_units)).contains(&rotated_y)
        {
            return Err(ScoreFieldGap::GeometryExtentOutOfBounds);
        }
    }
    Ok(())
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

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub struct Rational {
    numerator: i128,
    denominator: i128,
}

impl Rational {
    pub const fn numerator(self) -> i128 {
        self.numerator
    }

    pub const fn denominator(self) -> i128 {
        self.denominator
    }

    pub(crate) fn from_ratio(numerator: i128, denominator: i128) -> Result<Self, ScoreFieldGap> {
        if denominator <= 0 {
            return Err(ScoreFieldGap::GeometryRepresentationLimit);
        }
        Ok(Self {
            numerator,
            denominator,
        })
    }

    pub(crate) fn from_decimal(value: ExactDecimal) -> Result<Self, ScoreFieldGap> {
        Ok(Self {
            numerator: value.coefficient(),
            denominator: value.denominator().map_err(map_decimal_error)?,
        })
    }

    const fn in_unit_interval(self) -> bool {
        0 <= self.numerator && self.numerator <= self.denominator
    }

    pub(crate) fn mul_ratio(
        self,
        numerator: i128,
        denominator: i128,
    ) -> Result<Self, ScoreFieldGap> {
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

    pub(crate) fn mul_i128(self, value: i128) -> Result<Self, ScoreFieldGap> {
        self.mul_ratio(value, 1)
    }

    pub(crate) fn mul(self, other: Self) -> Result<Self, ScoreFieldGap> {
        Ok(Self {
            numerator: self
                .numerator
                .checked_mul(other.numerator)
                .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
            denominator: self
                .denominator
                .checked_mul(other.denominator)
                .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
        })
    }

    pub(crate) fn div(self, other: Self) -> Result<Self, ScoreFieldGap> {
        if other.numerator <= 0 {
            return Err(ScoreFieldGap::GeometryRepresentationLimit);
        }
        self.mul_ratio(other.denominator, other.numerator)
    }

    pub(crate) fn le(self, other: Self) -> Result<bool, ScoreFieldGap> {
        let left = self
            .numerator
            .checked_mul(other.denominator)
            .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?;
        let right = other
            .numerator
            .checked_mul(self.denominator)
            .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?;
        Ok(left <= right)
    }

    pub(crate) fn div_i128(self, value: i128) -> Result<Self, ScoreFieldGap> {
        self.mul_ratio(1, value)
    }

    pub(crate) fn add(self, other: Self) -> Result<Self, ScoreFieldGap> {
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

    pub(crate) fn sub(self, other: Self) -> Result<Self, ScoreFieldGap> {
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

    pub(crate) fn to_f64(self) -> Result<f64, ScoreFieldGap> {
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
                    Primitive::Line
                    | Primitive::Circle
                    | Primitive::Ellipse
                    | Primitive::Cloudform
                    | Primitive::Square
                    | Primitive::Arc
                    | Primitive::Point,
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
    fn composition_plan_recovery_preserves_original_source_slot_and_integrity() {
        let limits = crate::MacroExpansionLimits {
            max_invocations: 16,
            max_depth: 16,
            max_evaluation_steps: 1000,
            max_nodes_per_invocation: 100,
            max_total_nodes: 500,
        };
        let mut compilation = crate::compile_typed_ddl(
            crate::NormalizedDdlDocument::new(
                "place many red circle at center. arrange eight red square vertically at left-edge.",
                crate::ResolvedInstructionLanguage::En,
                vec![],
            )
            .unwrap(),
            &[],
            None,
            limits,
        );
        assert!(crate::stage15_transformation_input(&compilation).is_err());
        let context = ScoreLoweringContext::resolve("square", Color::White).unwrap();
        let crate::execution_projection::ExecutionProjectionResult::Ready(ready) =
            crate::execution_projection::project_compilation_for_execution(
                &compilation,
                &[],
                None,
                limits,
                context,
                None,
            )
        else {
            panic!("expected typed independent survivor")
        };
        assert!(!ready.diagnostics.is_empty());
        let transformed = crate::transform_stage15(
            crate::stage15_transform::stage15_execution_projection_input(ready.projection),
            None,
        )
        .unwrap();
        let plan = resolve_composition_plan(
            transformed.verified_effective_view(),
            context,
            ScoreErrorPolicy::OmitAndContinue,
        );
        assert_eq!(plan.objects().unwrap().len(), 1);
        assert_eq!(
            plan.objects().unwrap()[0].origin(),
            &ScoreInstructionOrigin::SourceInstruction {
                instruction_index: 1
            }
        );
        assert_eq!(plan.objects().unwrap()[0].count(), 8);
        assert_eq!(
            plan.objects().unwrap()[0].layout_direction().unwrap().axis,
            [0, 1]
        );
        compilation.compiler_lock.as_mut().unwrap().full_digest = "tampered".to_owned();
        assert!(matches!(
            crate::execution_projection::project_compilation_for_execution(
                &compilation,
                &[],
                None,
                limits,
                context,
                None
            ),
            crate::execution_projection::ExecutionProjectionResult::Stopped(_)
        ));
    }

    #[test]
    fn composition_plan_physical_aspect_and_exact_ceil_boundaries() {
        for (width, height, expected, spacing) in
            [(1200, 800, (4, 2), 300), (800, 1200, (2, 4), 200)]
        {
            let context = ScoreLoweringContext {
                canvas_format: CanvasFormat {
                    id: "physical-test",
                    width_units: width,
                    height_units: height,
                },
                background: Color::White,
                resolved_palette: None,
            };
            for (action, count) in [("tile", 8), ("line_up", 4)] {
                let mut fields = complete_macro_fields();
                fields.insert(
                    "movement".to_owned(),
                    ExpandedMacroValue::SemanticRef {
                        category: "movement".to_owned(),
                        id: action.to_owned(),
                    },
                );
                fields.insert("count".to_owned(), ExpandedMacroValue::Integer(count));
                let mut input = project_macro_emit(&fields, &[], true).unwrap();
                input.color = Some(SemanticInputIdentity {
                    category: "color",
                    id: "red",
                });
                input.has_named_position = true;
                input.named_position = Some(SemanticInputIdentity {
                    category: "place",
                    id: "center",
                });
                input.effective_focus = Some(FocusRegion::UpperRight);
                input.angle_context = Some(ScoreAngleContext {
                    composition_seed: None,
                    original_pre_expansion_digest: "test",
                    original_expanded_meaning_digest: "test",
                    occurrence: ScoreAngleOccurrence::Direct { logical_ordinal: 0 },
                });
                // Numeric anchor allows the whole canvas domain and exact centroid.
                let source = "place one red circle at horizontal 0.5, vertical 0.5.";
                let compilation = crate::compile_typed_ddl(
                    crate::NormalizedDdlDocument::new(
                        source,
                        crate::ResolvedInstructionLanguage::En,
                        vec![],
                    )
                    .unwrap(),
                    &[],
                    None,
                    crate::MacroExpansionLimits {
                        max_invocations: 16,
                        max_depth: 16,
                        max_evaluation_steps: 1000,
                        max_nodes_per_invocation: 100,
                        max_total_nodes: 500,
                    },
                );
                input.numeric_position = compilation
                    .semantic_document
                    .as_ref()
                    .unwrap()
                    .ast
                    .instructions[0]
                    .entity
                    .numeric_position
                    .as_ref();
                input.has_named_position = false;
                input.named_position = None;
                let object = resolve_object_plan(
                    input,
                    context,
                    ScoreInstructionOrigin::SourceInstruction {
                        instruction_index: 0,
                    },
                )
                .unwrap();
                let ResolvedGeometryDimensions::Circle { radius } = object.dimensions else {
                    panic!()
                };
                assert_eq!(
                    radius.numerator * i128::from(width.min(height)) * 2,
                    192 * radius.denominator
                );
                match object.recipe {
                    PlacementRecipe::Grid { columns, rows, .. } => {
                        assert_eq!((columns, rows), expected)
                    }
                    PlacementRecipe::HorizontalLine { cell_width } => assert_eq!(
                        cell_width.numerator * i128::from(width.min(height)),
                        i128::from(spacing) * cell_width.denominator
                    ),
                    _ => panic!(),
                }
            }
        }
    }

    #[test]
    fn layout_direction_physical_rectangles_and_original_seed_identity() {
        let limits = crate::MacroExpansionLimits {
            max_invocations: 16,
            max_depth: 16,
            max_evaluation_steps: 1000,
            max_nodes_per_invocation: 100,
            max_total_nodes: 500,
        };
        for (width, height) in [(1200, 800), (800, 1200)] {
            let context = ScoreLoweringContext {
                canvas_format: CanvasFormat {
                    id: "physical-test",
                    width_units: width,
                    height_units: height,
                },
                background: Color::White,
                resolved_palette: None,
            };
            for (word, y) in [("縦", 0), ("右上がり", -1), ("右下がり", 1), ("斜め", 2)]
            {
                for seed in [None, Some(0), Some(19)] {
                    let compilation = crate::compile_typed_ddl(
                        crate::NormalizedDdlDocument::new(
                            format!("中央に、黒い横線を{word}に4294967295本並べる。"),
                            crate::ResolvedInstructionLanguage::Ja,
                            vec![],
                        )
                        .unwrap(),
                        &[],
                        seed,
                        limits,
                    );
                    let transformed = crate::transform_stage15(
                        crate::stage15_transformation_input(&compilation).unwrap(),
                        None,
                    )
                    .unwrap();
                    let view = transformed.verified_effective_view();
                    let result = resolve_composition_plan(view, context, ScoreErrorPolicy::Stop);
                    let objects = result
                        .objects()
                        .unwrap_or_else(|| panic!("{:?}", result.diagnostics()));
                    assert_eq!(objects.len(), 1);
                    let object = &objects[0];
                    assert_eq!(object.count(), u32::MAX);
                    assert_eq!(object.angle(), Some(0.0));
                    let ResolvedGeometryDimensions::Line { length } = object.dimensions() else {
                        panic!()
                    };
                    assert_eq!(length.numerator * 800 * 25, 4800 * length.denominator);
                    match object.recipe() {
                        PlacementRecipe::VerticalLine { cell_height } => assert_eq!(
                            cell_height.numerator * i128::from(u32::MAX) * 800,
                            i128::from(height) * cell_height.denominator
                        ),
                        PlacementRecipe::DiagonalLine { step } => {
                            assert_eq!(
                                step[0].numerator * i128::from(u32::MAX),
                                step[0].denominator
                            );
                            if y != 2 {
                                assert_eq!(
                                    step[1].numerator * i128::from(u32::MAX),
                                    i128::from(y) * step[1].denominator
                                );
                            }
                            assert_eq!(
                                step[1].numerator.abs() * step[0].denominator,
                                step[0].numerator * step[1].denominator
                            );
                        }
                        other => panic!("{other:?}"),
                    }
                    let variation = crate::transform_stage15(
                        crate::stage15_transformation_input(&compilation).unwrap(),
                        Some(crate::Stage15Variation {
                            amplitude: crate::Stage15VariationAmplitude::Large,
                            seed: 234,
                        }),
                    )
                    .unwrap();
                    let varied = resolve_composition_plan(
                        variation.verified_effective_view(),
                        context,
                        ScoreErrorPolicy::Stop,
                    );
                    assert_eq!(
                        object.layout_direction(),
                        varied.objects().unwrap()[0].layout_direction()
                    );
                }
            }
        }
    }

    #[test]
    fn macro_count_requires_an_integer_without_reinterpreting_number() {
        let mut fields = complete_macro_fields();
        fields.insert("count".to_owned(), ExpandedMacroValue::Integer(1));
        assert_eq!(
            project_macro_emit(&fields, &[], false).unwrap().count,
            Some(1)
        );

        fields.insert("count".to_owned(), ExpandedMacroValue::Number(1.0));
        assert_eq!(
            project_macro_emit(&fields, &[], false).unwrap_err(),
            [ScoreFieldGap::MacroEmitFieldTypeMismatch {
                key: "count".to_owned(),
            }]
        );
    }

    #[test]
    fn owner_and_focus_integrity_failures_stop_both_error_modes() {
        let failures = [
            ScoreFieldGap::MissingMacroExpansionOwner {
                invocation_ordinal: 3,
            },
            ScoreFieldGap::DuplicateMacroExpansionOwner {
                invocation_ordinal: 3,
            },
            ScoreFieldGap::MissingMacroEmitFocusTarget {
                invocation_ordinal: 3,
                expansion_path: Vec::new(),
                generated_ordinal: 5,
            },
            ScoreFieldGap::DuplicateMacroEmitFocusTarget {
                invocation_ordinal: 3,
                expansion_path: Vec::new(),
                generated_ordinal: 5,
            },
        ];
        for policy in [ScoreErrorPolicy::Stop, ScoreErrorPolicy::OmitAndContinue] {
            for reason in &failures {
                assert_eq!(
                    diagnostic_disposition(
                        policy,
                        reason,
                        ScoreOmissionUnit::MacroInvocation {
                            source_instruction_index: 0,
                            invocation_ordinal: 3,
                        },
                        None,
                    ),
                    ScoreDiagnosticDisposition::Stopped
                );
            }
        }
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
