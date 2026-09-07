//! Runtime-disconnected Score candidates and eligible explicit lowering from verified Stage 1.5.

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
        has_unsupported_meaning: instruction.entity.fluctuation.amplitude.is_some()
            || instruction.entity.fluctuation.frequency.is_some()
            || instruction.entity.fluctuation.quality.is_some()
            || instruction.entity.proportion.aspect.is_some()
            || instruction.entity.proportion.width_extent.is_some()
            || instruction.entity.proportion.arc_form.is_some(),
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
                binding: Some(binding),
                provenance,
                ..
            } => Some((binding, provenance)),
            _ => None,
        })
        .collect::<Vec<_>>();
    let mut connected_by_to = BTreeMap::new();
    let mut invalid_connected_targets = BTreeSet::new();
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
        if kind != "connected" && kind != "touching" {
            continue;
        }
        let from_position = emit_nodes.iter().position(|(binding, _)| *binding == from);
        let to_position = emit_nodes.iter().position(|(binding, _)| *binding == to);
        if from_position
            .zip(to_position)
            .is_some_and(|(from, to)| to == from + 1)
            && connected_by_to
                .insert(to.clone(), (from.clone(), kind.as_str()))
                .is_none()
        {
            continue;
        }
        invalid_connected_targets.insert(to.clone());
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
            if matches!(node, ExpandedMacroNode::Relation { kind, .. } if kind == "connected" || kind == "touching")
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
            .is_some_and(|binding| invalid_connected_targets.contains(binding))
        {
            continue;
        }
        let connected_dependency = binding
            .as_ref()
            .and_then(|binding| connected_by_to.get(binding));
        if let Some((dependency, _)) = connected_dependency
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
        let mut input = match project_macro_emit(fields, &[]) {
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
                match project_macro_emit(fields, &omitted) {
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
            if let Some((dependency, kind)) = connected_dependency {
                let touching = *kind == "touching";
                let target_instruction_index = successful_bindings[dependency];
                let prior_supported =
                    instructions
                        .get(target_instruction_index)
                        .is_some_and(|prior| {
                            matches!(prior.primitive, Primitive::Line | Primitive::Arc)
                                || (!touching && prior.primitive == Primitive::Point)
                        });
                let current_supported = matches!(
                    score_instruction.primitive,
                    Primitive::Line | Primitive::Arc
                ) || (!touching
                    && score_instruction.primitive == Primitive::Point);
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
                        dimensions_fixed: input.explicit_geometry.is_some()
                            || input.relative_scale.is_some(),
                        direction_fixed: input.angle.is_some(),
                    }),
                });
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
        || instruction.entity.proportion.aspect.is_some()
        || instruction.entity.proportion.width_extent.is_some()
        || instruction.entity.proportion.arc_form.is_some()
        || instruction.action.is_some()
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

const MACRO_SCORE_FIELD_KEYS: [&str; 11] = [
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
];

fn project_macro_emit<'a>(
    fields: &'a BTreeMap<String, ExpandedMacroValue>,
    omitted_appearance: &[ScoreAppearanceField],
) -> Result<ScoreLoweringInput<'a>, Vec<ScoreFieldGap>> {
    let mut gaps = fields
        .keys()
        .filter(|key| !MACRO_SCORE_FIELD_KEYS.contains(&key.as_str()))
        .map(|key| ScoreFieldGap::UnknownMacroEmitField { key: key.clone() })
        .collect::<Vec<_>>();
    let primitive = macro_semantic_field(fields, "shape", "shape", true, &mut gaps);
    let action = macro_semantic_field(fields, "movement", "movement", true, &mut gaps);
    let place = macro_semantic_field(fields, "place", "place", true, &mut gaps);
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
            "line" | "circle" | "ellipse" | "cloudform" | "square" | "arc" | "point"
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

/// Candidate evidence plus the selected policy, diagnostics, and actual Score outcome.
#[derive(Clone, Debug)]
pub struct ExplicitScoreLoweringResult<'a> {
    candidate: ScoreLoweringCandidate<'a>,
    context: ScoreLoweringContext,
    policy_digest: String,
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
    let has_drawable_content = !instructions.is_empty() || ground.is_some();
    let outcome = if stopped || (omitted && !has_drawable_content) {
        ScoreLoweringOutcome::Stopped
    } else if omitted {
        ScoreLoweringOutcome::CompleteWithOmissions
    } else {
        ScoreLoweringOutcome::Complete
    };
    let score = (outcome != ScoreLoweringOutcome::Stopped).then(|| Score {
        version: score_wire_version(),
        canvas: ground.map_or_else(
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
            matches!(prior.primitive, Primitive::Line | Primitive::Arc)
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
                || instruction.entity.relative_scale.is_some(),
            direction_fixed: instruction.entity.angle.is_some(),
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
struct InstructionLoweringAttempt {
    instruction: Option<Instruction>,
    appearance_omissions: Vec<AppearanceOmission>,
    remaining_gaps: Vec<ScoreFieldGap>,
}

fn lower_projected_instruction(
    input: ScoreLoweringInput<'_>,
    context: ScoreLoweringContext,
    error_policy: ScoreErrorPolicy,
) -> InstructionLoweringAttempt {
    let first_gaps = match lower_complete_instruction(input, context) {
        Ok(instruction) => {
            return InstructionLoweringAttempt {
                instruction: Some(instruction),
                appearance_omissions: Vec::new(),
                remaining_gaps: Vec::new(),
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
    match lower_complete_instruction(projected, context) {
        Ok(instruction) => InstructionLoweringAttempt {
            instruction: Some(instruction),
            appearance_omissions,
            remaining_gaps,
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
    ScoreDiagnosticOwner::SourceInstruction {
        instruction_index,
        field,
        spans: vec![source_span_for_gap(instruction, gap, field)],
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
    let rotation = if primitive == Primitive::Point && input.angle.is_some() {
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
    let (filled, surface) = if primitive == Primitive::Point && input.surface.is_some() {
        let identity = input.surface.expect("checked present Point surface");
        gaps.push(ScoreFieldGap::UnsupportedSurfaceIdentity {
            category: identity.category.to_owned(),
            id: identity.id.to_owned(),
        });
        (true, None)
    } else {
        let closes_area = matches!(
            primitive,
            Primitive::Circle
                | Primitive::Ellipse
                | Primitive::Square
                | Primitive::Point
                | Primitive::Cloudform
        );
        match input.surface {
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
            Primitive::Line
                | Primitive::Circle
                | Primitive::Ellipse
                | Primitive::Cloudform
                | Primitive::Square
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
        rotation,
    )
    .map_err(|gap| vec![gap])?;

    Ok(Instruction {
        primitive,
        note: None,
        from_: geometric.from,
        to: geometric.to,
        center: geometric.center,
        radius: geometric.radius,
        sides: None,
        position: geometric.position,
        size: geometric.size,
        angle_start: geometric.angle_start,
        angle_end: geometric.angle_end,
        rotation,
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
        thinness,
        surface,
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
enum ScorePlacement<'a> {
    Numeric(&'a crate::SemanticNumericPosition),
    Named([f64; 4]),
}

#[derive(Clone, Copy)]
enum ResolvedGeometryDimensions {
    Line { length: Rational },
    Circle { radius: Rational },
    Arc { chord: Rational, sagitta: Rational },
    Point { radius: Rational },
    CenteredSize { width: Rational, height: Rational },
    Square { side: Rational },
}

fn lower_geometry(
    primitive: Primitive,
    geometry: Option<&SemanticExplicitGeometry>,
    relative_scale: Option<CoreModifierValue>,
    placement: ScorePlacement<'_>,
    canvas: CanvasFormat,
    rotation: Option<f64>,
) -> Result<LoweredGeometry, ScoreFieldGap> {
    let dimensions = resolve_geometry_dimensions(primitive, geometry, relative_scale)?;
    match placement {
        ScorePlacement::Numeric(position) => {
            lower_numeric_geometry(primitive, dimensions, position, canvas, rotation)
        }
        ScorePlacement::Named(focus) => lower_named_geometry(dimensions, focus, canvas),
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
        (Primitive::Line, SemanticExplicitGeometry::Length(value)) => {
            Ok(ResolvedGeometryDimensions::Line {
                length: positive(value.decimal.value)?,
            })
        }
        (Primitive::Circle, SemanticExplicitGeometry::Radius(value))
        | (Primitive::Circle, SemanticExplicitGeometry::Diameter(value))
        | (Primitive::Point, SemanticExplicitGeometry::Radius(value))
        | (Primitive::Point, SemanticExplicitGeometry::Diameter(value)) => {
            let mut radius = positive(value.decimal.value)?;
            if matches!(geometry, SemanticExplicitGeometry::Diameter(_)) {
                radius = radius.div_i128(2)?;
            }
            Ok(if primitive == Primitive::Point {
                ResolvedGeometryDimensions::Point { radius }
            } else {
                ResolvedGeometryDimensions::Circle { radius }
            })
        }
        (Primitive::Arc, SemanticExplicitGeometry::ChordSagitta { chord, sagitta }) => {
            let chord = positive(chord.decimal.value)?;
            let sagitta = positive(sagitta.decimal.value)?;
            if !sagitta.le(chord.div_i128(2)?)? {
                return Err(ScoreFieldGap::GeometryDimensionMismatch { primitive });
            }
            Ok(ResolvedGeometryDimensions::Arc { chord, sagitta })
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
    position: &crate::SemanticNumericPosition,
    canvas: CanvasFormat,
    rotation: Option<f64>,
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
        Primitive::Line | Primitive::Cloudform | Primitive::Square => (
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
    fn macro_count_requires_an_integer_without_reinterpreting_number() {
        let mut fields = complete_macro_fields();
        fields.insert("count".to_owned(), ExpandedMacroValue::Integer(1));
        assert_eq!(project_macro_emit(&fields, &[]).unwrap().count, Some(1));

        fields.insert("count".to_owned(), ExpandedMacroValue::Number(1.0));
        assert_eq!(
            project_macro_emit(&fields, &[]).unwrap_err(),
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
