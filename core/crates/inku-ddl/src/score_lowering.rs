//! Runtime-disconnected Score candidates and eligible explicit lowering from verified Stage 1.5.

use crate::composition_plan::{
    CompositionPlanOutcome, CompositionPlanResult, ObjectAnchor, ObjectPlacementPlan,
    PlacementAction, PlacementRecipe, ResolvedObjectAppearance,
};
use std::collections::{BTreeMap, BTreeSet};

use inku_score::{
    AtRegion, Canvas, CanvasFormat, CanvasGroundSpec, CanvasSpec, Color,
    ConnectedPositionAuthority, GroundMaterial, Instruction, InstructionMode, LineStyle, Point,
    Primitive, Relation, RelationGap, RelationType, ResolvedPaletteContext, Score, SurfaceSpec,
    SurfaceTexture, Thinness, TouchingConstraints, Weight, lookup_canvas_format,
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
    ScoreDiagnosticOwner, ScoreErrorPolicy, ScoreFieldGap, ScoreLoweringDiagnostic,
    ScoreLoweringOutcome, ScoreOmissionUnit, SemanticExplicitGeometry, SemanticHead,
    SemanticIdentity, SemanticInstruction, SemanticMacroInvocationHead, SemanticNumericPosition,
    SemanticPreviousReference, SemanticRelation, SemanticRelationKind, SourceSpan,
    Stage15TargetPath, Stage15TargetProvenance, VerifiedStage15EffectiveView,
    geometry_resolution_policy_digest,
};

/// Stable identity for the non-serializable Score-field candidate boundary.
pub const SCORE_FIELD_CANDIDATE_SCHEMA_ID: &str = "inku.score-field-candidate.v2";
pub const EXPLICIT_SCORE_LOWERING_SCHEMA_ID: &str = "inku.explicit-score-lowering.v4";

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

#[allow(clippy::too_many_arguments)]
fn lower_macro_instruction(
    view: VerifiedStage15EffectiveView<'_>,
    source_instruction_index: usize,
    instruction: &SemanticInstruction,
    head: &SemanticMacroInvocationHead,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
    instructions: &mut Vec<Instruction>,
    instruction_origins: &mut Vec<ScoreInstructionOrigin>,
    diagnostics: &mut Vec<ScoreLoweringDiagnostic>,
    mut objects: Option<&mut Vec<ObjectPlacementPlan>>,
) {
    let caller_invalid = append_macro_caller_diagnostics(
        source_instruction_index,
        instruction,
        head,
        error_policy,
        diagnostics,
    );
    if caller_invalid && error_policy == ScoreErrorPolicy::OmitAndContinue {
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

    let emit_nodes = expansion
        .nodes
        .iter()
        .filter_map(|node| match node {
            ExpandedMacroNode::Emit {
                binding,
                provenance,
                ..
            } => Some((binding.as_ref(), provenance)),
            _ => None,
        })
        .collect::<Vec<_>>();
    let mut relation_by_to = BTreeMap::new();
    let mut invalid_relation_targets = BTreeSet::new();
    for node in &expansion.nodes {
        let ExpandedMacroNode::Relation {
            kind,
            from,
            to,
            provenance,
        } = node
        else {
            continue;
        };
        if kind != "connected" && kind != "touching" && kind != "not_touching" {
            continue;
        }
        let from_position = emit_nodes
            .iter()
            .position(|(binding, _)| binding.is_some_and(|binding| binding == from));
        let to_position = emit_nodes
            .iter()
            .position(|(binding, _)| binding.is_some_and(|binding| binding == to));
        if from_position
            .zip(to_position)
            .is_some_and(|(from, to)| to == from + 1)
            && relation_by_to
                .insert(to.clone(), (from.clone(), kind.as_str()))
                .is_none()
        {
            continue;
        }
        invalid_relation_targets.insert(to.clone());
        let reason = ScoreFieldGap::UnsupportedMacroRelation;
        let target_provenance = to_position.map(|position| emit_nodes[position].1);
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: generated_owner(
                source_instruction_index,
                target_provenance.unwrap_or(provenance),
                None,
            ),
            disposition: diagnostic_disposition(
                error_policy,
                &reason,
                target_provenance.map_or_else(
                    || ScoreOmissionUnit::MacroStructuralSubtree {
                        source_instruction_index,
                        invocation_ordinal: provenance.invocation.invocation_ordinal,
                        expansion_path: provenance.expansion_path.clone(),
                        generated_ordinal: provenance.generated_ordinal,
                    },
                    |provenance| macro_emit_unit(source_instruction_index, provenance),
                ),
                None,
            ),
            reason,
        });
    }
    let mut successful_bindings: BTreeMap<GeneratedTargetId, usize> = BTreeMap::new();
    let mut center_bindings = BTreeSet::new();

    for node in &expansion.nodes {
        let ExpandedMacroNode::Emit {
            binding,
            fields,
            provenance,
        } = node
        else {
            if matches!(node, ExpandedMacroNode::Relation { kind, .. } if kind == "connected" || kind == "touching" || kind == "not_touching")
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
        if binding
            .as_ref()
            .is_some_and(|binding| invalid_relation_targets.contains(binding))
        {
            continue;
        }
        let relation_dependency = binding
            .as_ref()
            .and_then(|binding| relation_by_to.get(binding));
        if objects.is_some() && relation_dependency.is_some() {
            let reason = ScoreFieldGap::UnsupportedMacroRelation;
            diagnostics.push(ScoreLoweringDiagnostic {
                owner: generated_owner(source_instruction_index, provenance, None),
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
        if let Some((dependency, _)) = relation_dependency
            && !successful_bindings.contains_key(dependency)
        {
            let reason = ScoreFieldGap::UnavailableMacroRelationReference;
            diagnostics.push(ScoreLoweringDiagnostic {
                owner: generated_owner(source_instruction_index, provenance, None),
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
                if error_policy != ScoreErrorPolicy::OmitAndContinue || !remaining.is_empty() {
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
            append_plan_attempt(
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
            if let Some((dependency, kind)) = relation_dependency {
                if *kind == "not_touching" {
                    if input.effective_focus.is_none() {
                        let reason = ScoreFieldGap::UnsupportedMacroRelation;
                        diagnostics.push(ScoreLoweringDiagnostic {
                            owner: generated_owner(source_instruction_index, provenance, None),
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
                    score_instruction.relation = Some(Relation {
                        kind: RelationType::NotTouching,
                        gap: RelationGap::Medium,
                        target_instruction_index: None,
                        position_authority: None,
                        touching_constraints: None,
                    });
                } else {
                    let touching = *kind == "touching";
                    let target_instruction_index = successful_bindings[dependency];
                    let prior_supported =
                        instructions
                            .get(target_instruction_index)
                            .is_some_and(|prior| {
                                (matches!(prior.primitive, Primitive::Line | Primitive::Arc)
                                    && prior.arc_form.is_none())
                                    || (!touching && prior.primitive == Primitive::Point)
                            });
                    let current_supported = matches!(
                        score_instruction.primitive,
                        Primitive::Line | Primitive::Arc
                    ) && score_instruction.arc_form.is_none()
                        || (!touching && score_instruction.primitive == Primitive::Point);
                    if !prior_supported
                        || !current_supported
                        || input.effective_focus.is_none()
                        || !center_bindings.contains(dependency)
                    {
                        let reason = ScoreFieldGap::UnsupportedMacroRelation;
                        diagnostics.push(ScoreLoweringDiagnostic {
                            owner: generated_owner(source_instruction_index, provenance, None),
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
                    score_instruction.relation = Some(Relation {
                        kind: if touching {
                            RelationType::Touching
                        } else {
                            RelationType::Connected
                        },
                        gap: RelationGap::Medium,
                        target_instruction_index: Some(target_instruction_index),
                        position_authority: Some(ConnectedPositionAuthority::NamedMovable),
                        touching_constraints: touching.then_some(TouchingConstraints {
                            dimensions_fixed: input.exact_geometry().is_some()
                                || input.relative_scale.is_some()
                                || input.proportion_width_extent.is_some(),
                            direction_fixed: input.angle.is_some()
                                || input.proportion_arc_form.is_some(),
                        }),
                    });
                }
            }
            let score_index = instructions.len();
            instructions.push(score_instruction);
            if let Some(binding) = binding {
                successful_bindings.insert(binding.clone(), score_index);
                if input.effective_focus.is_some() {
                    center_bindings.insert(binding.clone());
                }
            }
            instruction_origins.push(ScoreInstructionOrigin::MacroEmit {
                source_instruction_index,
                binding: binding.clone(),
                provenance: provenance.clone(),
            });
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

fn append_macro_caller_diagnostics(
    source_instruction_index: usize,
    instruction: &SemanticInstruction,
    head: &SemanticMacroInvocationHead,
    error_policy: ScoreErrorPolicy,
    diagnostics: &mut Vec<ScoreLoweringDiagnostic>,
) -> bool {
    let mut invalid = false;
    match instruction
        .entity
        .quantity
        .as_ref()
        .map(|value| value.value)
    {
        None | Some(1) => {}
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
    if instruction.entity.thinness.is_some()
        || instruction.entity.relative_scale.is_some()
        || instruction.entity.explicit_geometry.is_some()
        || instruction.entity.numeric_position.is_some()
        || instruction.entity.angle.is_some()
        || instruction.entity.fluctuation.amplitude.is_some()
        || instruction.entity.fluctuation.frequency.is_some()
        || instruction.entity.fluctuation.quality.is_some()
        || instruction.entity.shape_constraint.is_some()
        || instruction.entity.proportion.aspect.is_some()
        || instruction.entity.proportion.width_extent.is_some()
        || instruction.entity.proportion.arc_form.is_some()
        || instruction.action.is_some()
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

const MACRO_SCORE_FIELD_KEYS: [&str; 30] = [
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
    "count",
    "angle",
    "thinness",
    "relative_scale",
    "fluctuation_amplitude",
    "fluctuation_frequency",
    "fluctuation_quality",
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
    let place = macro_semantic_field(
        fields,
        "place",
        "place",
        !fields.contains_key("position_x") && !fields.contains_key("position_y"),
        &mut gaps,
    );
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
    let angle = macro_semantic_field(fields, "angle", "angle", false, &mut gaps);
    let layout_direction =
        macro_semantic_field(fields, "layout_direction", "angle", false, &mut gaps);
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
        && !(planning && matches!(identity.id, "line_up" | "scatter" | "tile"))
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
        touch,
        continuity,
        surface,
        surface_intensity: None,
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
        has_unsupported_meaning: false,
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
    instruction_origins: Vec<ScoreInstructionOrigin>,
    gaps: Vec<ScoreFieldGap>,
    diagnostics: Vec<ScoreLoweringDiagnostic>,
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

    pub fn gaps(&self) -> &[ScoreFieldGap] {
        &self.gaps
    }

    pub fn diagnostics(&self) -> &[ScoreLoweringDiagnostic] {
        &self.diagnostics
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

/// Lower with the historical all-or-nothing behavior.
pub fn lower_verified_stage15_score<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
) -> ExplicitScoreLoweringResult<'a> {
    lower_verified_stage15_score_with_policy(view, context, ScoreErrorPolicy::Stop)
}

/// Lower with an explicit shared policy for ordinary instructions and macro expansions.
pub fn lower_verified_stage15_score_with_policy<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
) -> ExplicitScoreLoweringResult<'a> {
    lower_verified_stage15_shared(view, context, error_policy, None)
}

pub(crate) fn resolve_composition_plan<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
) -> CompositionPlanResult<'a> {
    let mut objects = Vec::new();
    let result = lower_verified_stage15_shared(view, context, error_policy, Some(&mut objects));
    let outcome = match result.outcome {
        ScoreLoweringOutcome::Stopped => CompositionPlanOutcome::Stopped,
        _ if objects.is_empty() => CompositionPlanOutcome::Stopped,
        ScoreLoweringOutcome::Complete => CompositionPlanOutcome::Ready,
        ScoreLoweringOutcome::CompleteWithOmissions => CompositionPlanOutcome::ReadyWithOmissions,
    };
    if outcome == CompositionPlanOutcome::Stopped {
        objects.clear();
    }
    CompositionPlanResult {
        view,
        context,
        error_policy,
        policy_digest: result.policy_digest,
        outcome,
        objects,
        ground: result.resolved_ground,
        diagnostics: result.diagnostics,
    }
}

fn lower_verified_stage15_shared<'a>(
    view: VerifiedStage15EffectiveView<'a>,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
    mut objects: Option<&mut Vec<ObjectPlacementPlan>>,
) -> ExplicitScoreLoweringResult<'a> {
    let candidate = lower_verified_stage15_view(view);
    let document = candidate
        .verified_effective_view()
        .original_semantic_document();
    let mut diagnostics = Vec::new();
    let mut omitted_group_members = BTreeSet::new();

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
        omitted_group_members.extend(group.member_instruction_indices.iter().copied());
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
            spans.extend(
                predicate
                    .action
                    .iter()
                    .chain(predicate.position.iter())
                    .map(|term| term.provenance.source.span),
            );
        }
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

    let mut instructions = Vec::new();
    let mut instruction_origins = Vec::new();
    for (projected_index, instruction) in document.instructions.iter().enumerate() {
        if omitted_group_members.contains(&projected_index) {
            continue;
        }
        let instruction_index = candidate
            .verified_effective_view()
            .source_instruction_index(projected_index)
            .expect("verified Stage 1.5 view maps every projected instruction");
        match &instruction.entity.head {
            SemanticHead::Primitive(_) => {
                let effective_focus = direct_instruction_focus(
                    candidate.verified_effective_view(),
                    instruction_index,
                );
                let input = project_source_instruction(
                    candidate.verified_effective_view(),
                    instruction_index,
                    instruction,
                    effective_focus,
                )
                .expect("source projection is called only for primitive heads");
                if let Some(objects) = objects.as_deref_mut() {
                    if let Some(relation) = &instruction.relation {
                        let reason = unsupported_relation_reason(instruction_index, relation);
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
                    } else {
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
                        append_plan_attempt(
                            attempt,
                            |reason| source_owner_for_gap(instruction_index, instruction, reason),
                            ScoreOmissionUnit::SourceInstruction { instruction_index },
                            error_policy,
                            objects,
                            &mut diagnostics,
                        );
                    }
                    continue;
                }
                if let Some(relation) = &instruction.relation {
                    let score_relation = direct_score_relation(
                        instruction_index,
                        instruction,
                        relation,
                        effective_focus,
                        &instructions,
                        &instruction_origins,
                    );
                    match score_relation {
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
                        Err(reason) => diagnostics.push(ScoreLoweringDiagnostic {
                            owner: ScoreDiagnosticOwner::SourceInstruction {
                                instruction_index,
                                field: None,
                                spans: vec![relation.provenance.span],
                            },
                            disposition: diagnostic_disposition(
                                error_policy,
                                &reason,
                                ScoreOmissionUnit::RelationInstruction { instruction_index },
                                None,
                            ),
                            reason,
                        }),
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
                if let Some(relation) = &instruction.relation {
                    let reason = unsupported_relation_reason(instruction_index, relation);
                    diagnostics.push(ScoreLoweringDiagnostic {
                        owner: ScoreDiagnosticOwner::MacroInvocation {
                            source_instruction_index: instruction_index,
                            invocation_ordinal: head.provenance.ordinal,
                            field: None,
                            spans: vec![relation.provenance.span, head.provenance.source.span],
                        },
                        disposition: diagnostic_disposition(
                            error_policy,
                            &reason,
                            macro_invocation_unit(instruction_index, head),
                            None,
                        ),
                        reason,
                    });
                    continue;
                }
                lower_macro_instruction(
                    candidate.verified_effective_view(),
                    instruction_index,
                    instruction,
                    head,
                    context,
                    error_policy,
                    &mut instructions,
                    &mut instruction_origins,
                    &mut diagnostics,
                    objects.as_deref_mut(),
                );
            }
        }
    }

    let stopped = diagnostics
        .iter()
        .any(|diagnostic| matches!(diagnostic.disposition, ScoreDiagnosticDisposition::Stopped));
    let omitted = diagnostics.iter().any(|diagnostic| {
        matches!(
            diagnostic.disposition,
            ScoreDiagnosticDisposition::Omitted { .. }
        )
    });
    let has_drawable_content = objects.as_ref().map_or_else(
        || !instructions.is_empty() || ground.is_some(),
        |objects| !objects.is_empty(),
    );
    let outcome = if stopped || (omitted && !has_drawable_content) {
        ScoreLoweringOutcome::Stopped
    } else if omitted {
        ScoreLoweringOutcome::CompleteWithOmissions
    } else {
        ScoreLoweringOutcome::Complete
    };
    let score = (objects.is_none() && outcome != ScoreLoweringOutcome::Stopped).then(|| Score {
        version: score_wire_version(),
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
        instruction_origins,
        gaps,
        diagnostics,
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

fn direct_score_relation(
    instruction_index: usize,
    instruction: &SemanticInstruction,
    relation: &SemanticRelation,
    effective_focus: Option<FocusRegion>,
    score_instructions: &[Instruction],
    instruction_origins: &[ScoreInstructionOrigin],
) -> Result<Relation, ScoreFieldGap> {
    let legacy_supported = matches!(
        (relation.kind, relation.reference),
        (
            SemanticRelationKind::NotTouching,
            SemanticPreviousReference::PreviousOne
        ) | (
            SemanticRelationKind::Between,
            SemanticPreviousReference::PreviousTwo
        )
    );
    let connected = matches!(
        (relation.kind, relation.reference),
        (
            SemanticRelationKind::Connected,
            SemanticPreviousReference::PreviousOne
        )
    );
    let touching = relation.kind == SemanticRelationKind::Touching
        && relation.reference == SemanticPreviousReference::PreviousOne;
    let checked = connected || touching;
    let has_exact_center = instruction.position.as_ref().is_some_and(|position| {
        position.identity.category == "place" && position.identity.id == "center"
    });
    let connected_position_supported = instruction.entity.numeric_position.is_some()
        || (instruction.position.is_some() && effective_focus.is_some());
    let connected_primitive_supported = matches!(
        &instruction.entity.head,
        SemanticHead::Primitive(term)
            if term.identity.category == "shape"
                && (matches!(term.identity.id.as_str(), "line" | "arc") || (!touching && term.identity.id == "point"))
                && instruction.entity.proportion.arc_form.as_ref().is_none_or(|form| form.identity.id != "crescent")
    );
    if (!legacy_supported && !checked)
        || (legacy_supported
            && (instruction.entity.numeric_position.is_some()
                || !has_exact_center
                || effective_focus.is_none()))
        || (checked && (!connected_position_supported || !connected_primitive_supported))
    {
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
    let actual_dependencies_match = instruction_origins
        .get(instruction_origins.len().saturating_sub(required)..)
        .is_some_and(|origins| {
            origins.len() == required
                && origins.iter().zip(&dependency_instruction_indices).all(
                    |(origin, expected_index)| {
                        matches!(
                            origin,
                            ScoreInstructionOrigin::SourceInstruction { instruction_index }
                                if instruction_index == expected_index
                        )
                    },
                )
        });
    if !actual_dependencies_match {
        return Err(ScoreFieldGap::UnavailableRelationReference {
            kind: relation.kind,
            reference: relation.reference,
            dependency_instruction_indices,
        });
    }
    if checked
        && !score_instructions.last().is_some_and(|prior| {
            (matches!(prior.primitive, Primitive::Line | Primitive::Arc)
                && prior.arc_form.is_none())
                || (!touching && prior.primitive == Primitive::Point)
        })
    {
        return Err(unsupported_relation_reason(instruction_index, relation));
    }

    Ok(Relation {
        kind: match relation.kind {
            SemanticRelationKind::NotTouching => RelationType::NotTouching,
            SemanticRelationKind::Between => RelationType::Between,
            SemanticRelationKind::Connected => RelationType::Connected,
            SemanticRelationKind::Touching => RelationType::Touching,
            SemanticRelationKind::Along | SemanticRelationKind::Cutting => {
                unreachable!("supported relation checked")
            }
        },
        gap: RelationGap::Medium,
        target_instruction_index: checked.then(|| score_instructions.len() - 1),
        position_authority: checked.then_some(if instruction.entity.numeric_position.is_some() {
            ConnectedPositionAuthority::NumericFixed
        } else {
            ConnectedPositionAuthority::NamedMovable
        }),
        touching_constraints: touching.then_some(TouchingConstraints {
            dimensions_fixed: instruction.entity.explicit_geometry.is_some()
                || instruction.entity.relative_scale.is_some()
                || instruction.entity.proportion.width_extent.is_some(),
            direction_fixed: instruction.entity.angle.is_some()
                || instruction.entity.proportion.arc_form.is_some(),
        }),
    })
}

#[derive(Clone, Debug)]
struct AppearanceOmission {
    reason: ScoreFieldGap,
    field: ScoreAppearanceField,
    resolution: ScoreAppearanceResolution,
}

#[derive(Clone, Debug)]
struct InstructionLoweringAttempt<T = Instruction> {
    instruction: Option<T>,
    appearance_omissions: Vec<AppearanceOmission>,
    remaining_gaps: Vec<ScoreFieldGap>,
}

fn lower_projected_instruction(
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
) -> InstructionLoweringAttempt {
    resolve_projected_instruction(input, context, error_policy, lower_complete_instruction)
}

fn resolve_projected_instruction<'a, T>(
    input: ScoreLoweringInput<'a>,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
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
                remaining_gaps: size_recovery_diagnostic(input, context)
                    .into_iter()
                    .collect(),
            };
        }
        Err(gaps) => gaps,
    };
    if error_policy == ScoreErrorPolicy::Stop {
        return InstructionLoweringAttempt {
            instruction: None,
            appearance_omissions: Vec::new(),
            remaining_gaps: first_gaps,
        };
    }

    let appearance_fields = first_gaps
        .iter()
        .filter_map(appearance_field_for_gap)
        .collect::<Vec<_>>();
    let surface_quality_survives = input.surface.is_some()
        && !appearance_fields.contains(&ScoreAppearanceField::SurfaceQuality);
    let mut projected = input;
    let mut appearance_omissions = Vec::new();
    let mut remaining_gaps = Vec::new();
    for reason in first_gaps {
        if let Some(field) = appearance_field_for_gap(&reason) {
            omit_appearance_field(&mut projected, field);
            appearance_omissions.push(AppearanceOmission {
                reason,
                field,
                resolution: default_resolution(field, surface_quality_survives),
            });
        } else {
            remaining_gaps.push(reason);
        }
    }
    if !remaining_gaps.is_empty() {
        return InstructionLoweringAttempt {
            instruction: None,
            appearance_omissions,
            remaining_gaps,
        };
    }
    match resolve(projected, context) {
        Ok(instruction) => InstructionLoweringAttempt {
            instruction: Some(instruction),
            appearance_omissions,
            remaining_gaps: size_recovery_diagnostic(projected, context)
                .into_iter()
                .collect(),
        },
        Err(gaps) => InstructionLoweringAttempt {
            instruction: None,
            appearance_omissions,
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
    error_policy: ScoreErrorPolicy,
    reason: &ScoreFieldGap,
    unit: ScoreOmissionUnit,
    appearance_resolution: Option<ScoreAppearanceResolution>,
) -> ScoreDiagnosticDisposition {
    if matches!(reason, ScoreFieldGap::ConflictingSizeSpecifications { .. }) {
        return ScoreDiagnosticDisposition::Recovered;
    }
    if error_policy == ScoreErrorPolicy::OmitAndContinue && !reason.is_integrity_failure() {
        ScoreDiagnosticDisposition::Omitted {
            unit,
            appearance_resolution,
        }
    } else {
        ScoreDiagnosticDisposition::Stopped
    }
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

fn omit_appearance_field(input: &mut ScoreLoweringInput<'_>, field: ScoreAppearanceField) {
    match field {
        ScoreAppearanceField::Color => input.color = None,
        ScoreAppearanceField::Touch => input.touch = None,
        ScoreAppearanceField::Continuity => input.continuity = None,
        ScoreAppearanceField::SurfaceQuality => input.surface = None,
        ScoreAppearanceField::SurfaceIntensity => input.surface_intensity = None,
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

fn macro_invocation_unit(
    source_instruction_index: usize,
    head: &SemanticMacroInvocationHead,
) -> ScoreOmissionUnit {
    ScoreOmissionUnit::MacroInvocation {
        source_instruction_index,
        invocation_ordinal: head.provenance.ordinal,
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
        ScoreAppearanceField::SurfaceIntensity => None,
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
        _ => None,
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
    has_unsupported_meaning: bool,
}

impl ScoreLoweringInput<'_> {
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
    let appearance = resolved.appearance;
    Ok(Instruction {
        arc_form: resolved.arc_form,
        primitive: resolved.primitive,
        note: None,
        from_: geometric.from,
        to: geometric.to,
        center: geometric.center,
        radius: geometric.radius,
        sides: match resolved.dimensions {
            ResolvedGeometryDimensions::Polygon { sides, .. } => Some(sides),
            _ => None,
        },
        position: geometric.position,
        size: geometric.size,
        angle_start: geometric.angle_start,
        angle_end: geometric.angle_end,
        rotation: resolved.rotation,
        filled: appearance.filled,
        style: appearance.continuity,
        weight: appearance.touch,
        mode_: InstructionMode::Additive,
        carve_depth: None,
        color: appearance.color,
        color_hint: None,
        variation: appearance.fluctuation,
        arrangement: None,
        at: geometric.at,
        relation: None,
        thinness: appearance.thinness,
        surface: appearance.surface,
    })
}

struct ResolvedObject {
    arc_form: Option<inku_score::ArcForm>,
    primitive: Primitive,
    count: u32,
    action: PlacementAction,
    dimensions: ResolvedGeometryDimensions,
    appearance: ResolvedObjectAppearance,
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
                    let bounds = crate::geometry::named_region_rational_bounds(
                        input.named_position.expect("resolved named position").id,
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
        let n = resolved.count;
        let layout_direction = resolved.layout_direction;
        let recipe = match resolved.action {
            PlacementAction::Place => PlacementRecipe::Place,
            PlacementAction::LineUp => match layout_direction
                .as_ref()
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
            PlacementAction::Tile => {
                let landscape = domain[1].le(domain[0])?;
                let aspect = if landscape {
                    domain[0].div(domain[1])?
                } else {
                    domain[1].div(domain[0])?
                };
                // Integer binary search of k² >= n * long/short. This is bounded
                // by 32 iterations and has no floating ceil boundary or count loop.
                let target = aspect.mul_i128(n.into())?;
                let mut low = 1_u32;
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
                    cell_height
                        .mul_ratio(c * q * q + remainder * (2 * q + 1), 2 * i128::from(n))?,
                ];
                PlacementRecipe::Grid {
                    columns,
                    rows,
                    filled_count: n,
                    cell_width,
                    cell_height,
                    centroid,
                    translate_to_numeric_anchor: matches!(
                        anchor,
                        ObjectAnchor::Numeric(_) | ObjectAnchor::GeneratedNumeric(_)
                    ),
                }
            }
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
            angle: resolved.rotation,
            layout_direction,
            anchor,
            domain,
            recipe,
        })
    };
    build().map_err(|gap| vec![gap])
}

fn append_plan_attempt(
    attempt: InstructionLoweringAttempt<ObjectPlacementPlan>,
    owner: impl Fn(&ScoreFieldGap) -> ScoreDiagnosticOwner,
    unit: ScoreOmissionUnit,
    error_policy: ScoreErrorPolicy,
    objects: &mut Vec<ObjectPlacementPlan>,
    diagnostics: &mut Vec<ScoreLoweringDiagnostic>,
) {
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
    for reason in attempt.remaining_gaps {
        diagnostics.push(ScoreLoweringDiagnostic {
            owner: owner(&reason),
            disposition: diagnostic_disposition(error_policy, &reason, unit.clone(), None),
            reason,
        });
    }
    if let Some(object) = attempt.instruction {
        objects.push(object);
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
                (closes_area, None)
            }
            Some(identity) => match surface_spec_from_identity(identity) {
                Ok(spec) => (closes_area, Some(spec)),
                Err(gap) => {
                    gaps.push(gap);
                    (false, None)
                }
            },
            None => (closes_area, None),
        }
    };
    if let Some(identity) = input.surface_intensity {
        gaps.push(ScoreFieldGap::UnsupportedSurfaceIntensity {
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        });
    }
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
    let named_focus = if input.has_named_position && input.exact_position().is_some() {
        gaps.push(ScoreFieldGap::NamedAndNumericPositionConflict);
        None
    } else if input.has_named_position {
        if let Some(region) = input
            .named_position
            .filter(|place| place.category == "place")
            .and_then(|place| {
                named_region_bounds(
                    place.id,
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
    } else if input.exact_position().is_none() {
        gaps.push(ScoreFieldGap::MissingNumericPosition);
        None
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
            thinness,
            surface,
        },
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
fn reference_extent(dimensions: ResolvedGeometryDimensions) -> Result<Rational, ScoreFieldGap> {
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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
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

    fn mul(self, other: Self) -> Result<Self, ScoreFieldGap> {
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

    fn div(self, other: Self) -> Result<Self, ScoreFieldGap> {
        if other.numerator <= 0 {
            return Err(ScoreFieldGap::GeometryRepresentationLimit);
        }
        self.mul_ratio(other.denominator, other.numerator)
    }

    fn le(self, other: Self) -> Result<bool, ScoreFieldGap> {
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
