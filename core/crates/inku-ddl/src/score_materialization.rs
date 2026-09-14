//! Deliver admitted symbolic templates to a replayable Score, without sampling.

use std::collections::HashSet;

use serde::Serialize;

use inku_score::{
    Arrangement, ArrangementPath, Canvas, CanvasSpec, CountOrigin, Density, Fade, FillBoundary,
    FillGroup, FillGroupOwner, FillRecipe, FillTarget, FillTargetAnchor, FillTargetGeometry,
    FillTargetOwner, InstanceOrdinalScheme, Layout, PlacementGroupOwner, PlacementMember, Point,
    Relation, RepetitionGroup, ResolvedArrangement, ResolvedPlacementAnchor,
    ResolvedPlacementGroup, ResolvedPlacementRecipe, ResolvedShapeDimensions, RhythmSpacing, Score,
    ScoreResourcePolicy, ScoreSourceOwner, ScoreSourceSite, SymbolicMember, SymbolicMemberKind,
    TransformGroup,
};

use crate::{
    FillCountResolution, FillPlanOwner, FillRegionGeometry, FillRegionOwner, MirrorBodyPlanRef,
    ObjectAnchor, PlacementMemberKind, PlacementMemberPlan, PlacementRecipe, Rational,
    ResolvedFillRegion, ResolvedGeometryDimensions, ScoreAnchorOrigin, ScoreFieldGap,
    ScoreInstructionOrigin, ScoreLoweringDiagnostic, SelectedCompositionPlan,
    plan_resources::PlanResourceOmission, score_lowering::lower_resolved_object_template,
};

const ORDINAL_SCHEME: InstanceOrdinalScheme = InstanceOrdinalScheme::SourceMemberThenInstanceV1;

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct MaterializedRelationOmission {
    pub owner: ScoreInstructionOrigin,
    pub target_object_index: Option<usize>,
    pub target_anchor_index: Option<usize>,
}

#[derive(Clone, Debug)]
pub struct MaterializedComposition {
    pub score: Score,
    pub instruction_origins: Vec<ScoreInstructionOrigin>,
    pub anchor_origins: Vec<ScoreAnchorOrigin>,
    pub diagnostics: Vec<ScoreLoweringDiagnostic>,
    pub resource_omissions: Vec<PlanResourceOmission>,
    pub relation_omissions: Vec<MaterializedRelationOmission>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum ScoreMaterializationError {
    Geometry {
        owner: ScoreInstructionOrigin,
        reason: ScoreFieldGap,
    },
    InvalidContract(&'static str),
}

struct IndexMap {
    values: Vec<Option<usize>>,
    boundaries: Vec<usize>,
}

impl IndexMap {
    fn new(length: usize, retained: &[usize]) -> Self {
        let mut values = vec![None; length];
        for (new, &old) in retained.iter().enumerate() {
            values[old] = Some(new);
        }
        let mut boundaries = Vec::with_capacity(length + 1);
        boundaries.push(0);
        for value in &values {
            boundaries.push(boundaries.last().copied().unwrap() + usize::from(value.is_some()));
        }
        Self { values, boundaries }
    }

    fn get(&self, old: usize) -> Option<usize> {
        self.values.get(old).copied().flatten()
    }

    fn indices(&self, original: &[usize]) -> Vec<usize> {
        original
            .iter()
            .filter_map(|&index| self.get(index))
            .collect()
    }
}

/// A selection can contain no drawable instructions after recoverable omissions.
/// It still produces its canvas/background Score and diagnostics, not a global abort.
pub fn materialize_selected_composition(
    admitted: &SelectedCompositionPlan<'_, '_>,
) -> Result<MaterializedComposition, ScoreMaterializationError> {
    let plan = admitted.plan();
    let objects = plan
        .objects()
        .ok_or(ScoreMaterializationError::InvalidContract("stopped plan"))?;
    let object_map = IndexMap::new(objects.len(), admitted.object_indices());
    let anchor_map = IndexMap::new(plan.anchors().len(), admitted.anchor_indices());
    let transform_map = IndexMap::new(plan.transform_groups().len(), admitted.transform_indices());
    let placement_group_map = IndexMap::new(
        plan.placement_groups().len(),
        admitted.placement_group_indices(),
    );
    let repetition_group_map = IndexMap::new(
        plan.standalone_macro_repetitions().len(),
        admitted.standalone_macro_indices(),
    );
    let mut managed_primitives = HashSet::new();
    for members in admitted
        .placement_group_indices()
        .iter()
        .map(|&i| plan.placement_groups()[i].members())
        .chain(
            admitted
                .fill_group_indices()
                .iter()
                .map(|&i| plan.fill_groups()[i].members.as_slice()),
        )
    {
        for member in members {
            if member.kind() == PlacementMemberKind::Primitive {
                managed_primitives.insert(member.member().start);
            }
        }
    }
    let mut instructions = Vec::with_capacity(admitted.object_indices().len());
    let mut instruction_origins = Vec::with_capacity(instructions.capacity());
    let mut relation_omissions = Vec::new();
    for &old in admitted.object_indices() {
        let object = &objects[old];
        let mut instruction =
            lower_resolved_object_template(object, plan.context()).map_err(|reason| {
                ScoreMaterializationError::Geometry {
                    owner: object.origin().clone(),
                    reason,
                }
            })?;
        let owned_elsewhere = managed_primitives.contains(&old)
            || matches!(
                object.recipe(),
                PlacementRecipe::FillUniformInRegionAndClip { .. }
            );
        let count = if owned_elsewhere { 1 } else { object.count() };
        let recipe = if owned_elsewhere {
            ResolvedPlacementRecipe::Place
        } else {
            saved_recipe(object.recipe())?
        };
        instruction.arrangement = Some(arrangement(
            count,
            object.color_cycle(),
            ResolvedArrangement {
                owner: saved_owner(object.origin()),
                first_instance_ordinal: 0,
                count_origin: if owned_elsewhere {
                    CountOrigin::TemplateSingle
                } else {
                    ordinary_count_origin(object.count_was_omitted())
                },
                domain: saved_point(object.domain())?,
                anchor: if owned_elsewhere {
                    ResolvedPlacementAnchor::EnclosingGroup
                } else {
                    saved_placement_anchor(object.anchor())?
                },
                recipe,
                ordinal_scheme: ORDINAL_SCHEME,
            },
        ));
        if let Some(relation) = object.relation() {
            let object_target = relation
                .target_object_index()
                .and_then(|i| object_map.get(i));
            let anchor_target = relation
                .target_anchor_index()
                .and_then(|i| anchor_map.get(i));
            let lost = relation.target_object_index().is_some() && object_target.is_none()
                || relation.target_anchor_index().is_some() && anchor_target.is_none();
            if lost {
                relation_omissions.push(MaterializedRelationOmission {
                    owner: object.origin().clone(),
                    target_object_index: relation.target_object_index(),
                    target_anchor_index: relation.target_anchor_index(),
                });
            } else {
                instruction.relation = Some(Relation {
                    kind: relation.kind(),
                    gap: relation.gap(),
                    target_instruction_index: object_target,
                    target_anchor_index: anchor_target,
                    position_authority: relation.position_authority(),
                    touching_constraints: relation.touching_constraints(),
                    target_path_position: relation.target_path_position(),
                    target_endpoint: relation.target_endpoint(),
                });
            }
        }
        instructions.push(instruction);
        instruction_origins.push(object.origin().clone());
    }
    let anchors = admitted
        .anchor_indices()
        .iter()
        .map(|&i| plan.anchors()[i].clone())
        .collect();
    let anchor_origins = admitted
        .anchor_indices()
        .iter()
        .map(|&i| plan.anchor_origins()[i].clone())
        .collect();
    let transform_groups = admitted
        .transform_indices()
        .iter()
        .map(|&index| {
            let group = &plan.transform_groups()[index];
            TransformGroup {
                start: object_map.boundaries[group.start()],
                end: object_map.boundaries[group.end()],
                rotation_degrees: group.rotation_degrees(),
                scale_x: group.scale_x(),
                scale_y: group.scale_y(),
                translate_x: group.translate_x(),
                translate_y: group.translate_y(),
                fixed_position_indices: object_map.indices(group.fixed_position_indices()),
                anchor_indices: anchor_map.indices(group.anchor_indices()),
            }
        })
        .collect();
    let mut placement_groups = Vec::new();
    for &index in admitted.placement_group_indices() {
        let planned = &plan.placement_groups()[index];
        let mut group = planned.placement().clone();
        group.start = object_map.boundaries[group.start];
        group.end = object_map.boundaries[group.end];
        group.members = saved_members(
            planned.members(),
            &object_map,
            &anchor_map,
            &transform_map,
            None,
            planned.cycle_occurrence_count().is_some(),
        )?;
        group.cycle_members = planned
            .cycle_occurrence_count()
            .map(|occurrence_count| inku_score::CycleMembersV1 { occurrence_count });
        group.resolved = Some(ResolvedPlacementGroup {
            owner: PlacementGroupOwner::CoordinatedGroup {
                group_index: planned.group_index(),
            },
            logical_count: planned.logical_count(),
            domain: saved_point(planned.domain())?,
            anchor: ResolvedPlacementAnchor::Named {
                region: group.at.region,
            },
            recipe: saved_recipe(planned.recipe())?,
            ordinal_scheme: ORDINAL_SCHEME,
        });
        placement_groups.push(group);
    }
    let mut fill_groups = Vec::new();
    for &index in admitted.fill_group_indices() {
        let group = &plan.fill_groups()[index];
        let (region, origin) = fill_parts(&group.recipe)?;
        let members = saved_members(
            &group.members,
            &object_map,
            &anchor_map,
            &transform_map,
            Some(origin),
            group.cycle_occurrence_count.is_some(),
        )?;
        let first = members
            .first()
            .ok_or(ScoreMaterializationError::InvalidContract(
                "empty fill group",
            ))?;
        let last = members.last().unwrap();
        fill_groups.push(FillGroup {
            start: first.start,
            end: last.end,
            owner: saved_fill_owner(group.owner),
            logical_count: group.logical_count,
            recipe: FillRecipe::UniformInRegion,
            target: saved_target(region)?,
            boundary: FillBoundary::ClipToTarget,
            ordinal_scheme: ORDINAL_SCHEME,
            members,
            cycle_members: group
                .cycle_occurrence_count
                .map(|occurrence_count| inku_score::CycleMembersV1 { occurrence_count }),
        });
    }
    for &old in admitted.object_indices() {
        let object = &objects[old];
        if let PlacementRecipe::FillUniformInRegionAndClip {
            region,
            count_resolution,
        } = object.recipe()
        {
            let start = object_map.get(old).unwrap();
            fill_groups.push(FillGroup {
                start,
                end: start + 1,
                owner: FillGroupOwner::Instruction {
                    source_instruction_index: source_index(object.origin()),
                },
                logical_count: u64::from(object.count()),
                recipe: FillRecipe::UniformInRegion,
                target: saved_target(region)?,
                boundary: FillBoundary::ClipToTarget,
                ordinal_scheme: ORDINAL_SCHEME,
                cycle_members: None,
                members: vec![PlacementMember {
                    start,
                    end: start + 1,
                    anchor_indices: Vec::new(),
                    transform_group_indices: Vec::new(),
                    symbolic: Some(SymbolicMember {
                        owner: saved_owner(object.origin()),
                        kind: SymbolicMemberKind::Primitive,
                        member_ordinal: 0,
                        first_instance_ordinal: 0,
                        instance_count: u64::from(object.count()),
                        count_origin: saved_count_origin(count_resolution)?,
                    }),
                }],
            });
        }
    }
    fill_groups.sort_by_key(|group| group.start);
    let repetition_groups = admitted
        .standalone_macro_indices()
        .iter()
        .map(|&index| {
            let member = &plan.standalone_macro_repetitions()[index];
            let mut members = saved_members(
                std::slice::from_ref(member),
                &object_map,
                &anchor_map,
                &transform_map,
                None,
                false,
            )?;
            Ok(RepetitionGroup {
                member: members.remove(0),
                ordinal_scheme: ORDINAL_SCHEME,
            })
        })
        .collect::<Result<Vec<_>, ScoreMaterializationError>>()?;
    let mut mirror_relations = Vec::new();
    for planned in plan.mirror_relations() {
        let target = saved_mirror_body_ref(
            planned.target(),
            &object_map,
            &placement_group_map,
            &repetition_group_map,
        );
        let follower = saved_mirror_body_ref(
            planned.follower(),
            &object_map,
            &placement_group_map,
            &repetition_group_map,
        );
        if let (Some(target), Some(follower)) = (target, follower) {
            mirror_relations.push(inku_score::MirrorRelationV1 {
                target,
                follower,
                follower_facts: planned.follower_facts().clone(),
            });
        } else {
            relation_omissions.push(MaterializedRelationOmission {
                owner: planned.owner().clone(),
                target_object_index: match planned.target() {
                    MirrorBodyPlanRef::Object { object_index } => Some(*object_index),
                    _ => None,
                },
                target_anchor_index: None,
            });
        }
    }
    let score = Score {
        version: if !mirror_relations.is_empty() {
            "0.15.0"
        } else if placement_groups
            .iter()
            .any(|group| group.cycle_members.is_some())
            || fill_groups
                .iter()
                .any(|group| group.cycle_members.is_some())
        {
            "0.14.0"
        } else if instructions.iter().any(|instruction| {
            instruction.relation.as_ref().is_some_and(|relation| {
                matches!(
                    relation.target_path_position,
                    Some(inku_score::TargetPathPosition::Selection(
                        inku_score::TargetPathSelection::Interior
                    ))
                )
            })
        }) {
            "0.13.0"
        } else if instructions.iter().any(|instruction| {
            instruction.ink_spread.is_some()
                || instruction
                    .relation
                    .as_ref()
                    .is_some_and(|relation| relation.target_endpoint.is_some())
        }) {
            "0.12.0"
        } else if instructions.iter().any(|instruction| {
            instruction.relation.as_ref().is_some_and(|relation| {
                matches!(
                    relation.target_path_position,
                    Some(inku_score::TargetPathPosition::Exact(_))
                )
            })
        }) {
            "0.11.0"
        } else {
            "0.10.0"
        }
        .to_owned(),
        canvas: plan.ground().cloned().map_or_else(
            || Canvas::Id(plan.context().canvas_format().id.to_owned()),
            |ground| {
                Canvas::Spec(CanvasSpec {
                    aspect: plan.context().canvas_format().id.to_owned(),
                    ground: Some(ground),
                })
            },
        ),
        background: plan.context().background(),
        presence: None,
        instructions,
        anchors,
        transform_groups,
        placement_groups,
        fill_groups,
        repetition_groups,
        mirror_relations,
        resource_policy: Some(ScoreResourcePolicy {
            accounting_id: inku_score::RESOURCE_ACCOUNTING_ID.to_owned(),
            hard_policy: admitted.hard_policy().clone(),
            operational_budget: admitted.operational_budget(),
        }),
    };
    score
        .validate_schema_edition()
        .map_err(ScoreMaterializationError::InvalidContract)?;
    Ok(MaterializedComposition {
        score,
        instruction_origins,
        anchor_origins,
        diagnostics: plan.diagnostics().to_vec(),
        resource_omissions: admitted.omissions().to_vec(),
        relation_omissions,
    })
}

fn saved_mirror_body_ref(
    reference: &MirrorBodyPlanRef,
    objects: &IndexMap,
    placement_groups: &IndexMap,
    repetition_groups: &IndexMap,
) -> Option<inku_score::MirrorBodyRef> {
    match *reference {
        MirrorBodyPlanRef::Object { object_index } => objects
            .get(object_index)
            .map(|instruction_index| inku_score::MirrorBodyRef::Instruction { instruction_index }),
        MirrorBodyPlanRef::StandaloneMacro { member_index } => repetition_groups
            .get(member_index)
            .map(
                |repetition_group_index| inku_score::MirrorBodyRef::RepetitionGroup {
                    repetition_group_index,
                },
            ),
        MirrorBodyPlanRef::PlacementMember {
            group_index,
            member_index,
        } => placement_groups
            .get(group_index)
            .map(
                |placement_group_index| inku_score::MirrorBodyRef::PlacementMember {
                    placement_group_index,
                    member_index,
                },
            ),
        MirrorBodyPlanRef::PlacementGroup { group_index } => {
            placement_groups
                .get(group_index)
                .map(
                    |placement_group_index| inku_score::MirrorBodyRef::PlacementGroup {
                        placement_group_index,
                    },
                )
        }
    }
}

fn saved_members(
    members: &[PlacementMemberPlan],
    objects: &IndexMap,
    anchors: &IndexMap,
    transforms: &IndexMap,
    fill_origin: Option<&FillCountResolution>,
    cycle: bool,
) -> Result<Vec<PlacementMember>, ScoreMaterializationError> {
    let mut ordinal = 0_u64;
    members
        .iter()
        .enumerate()
        .map(|(member_ordinal, planned)| {
            let original = planned.member();
            let count = if cycle {
                1
            } else {
                u64::from(planned.logical_count())
            };
            let member = PlacementMember {
                start: objects.boundaries[original.start],
                end: objects.boundaries[original.end],
                anchor_indices: anchors.indices(&original.anchor_indices),
                transform_group_indices: transforms.indices(&original.transform_group_indices),
                symbolic: Some(SymbolicMember {
                    owner: if planned.kind() == PlacementMemberKind::OrdinaryGroup {
                        ScoreSourceOwner::OrdinaryGroup {
                            source_instruction_indices: planned
                                .source_instruction_indices()
                                .to_vec(),
                        }
                    } else {
                        ScoreSourceOwner::SourceInstruction {
                            instruction_index: planned.source_instruction_index(),
                        }
                    },
                    kind: match planned.kind() {
                        PlacementMemberKind::Primitive => SymbolicMemberKind::Primitive,
                        PlacementMemberKind::Macro => SymbolicMemberKind::Macro,
                        PlacementMemberKind::OrdinaryGroup => SymbolicMemberKind::OrdinaryGroup,
                    },
                    member_ordinal: member_ordinal as u64,
                    first_instance_ordinal: ordinal,
                    instance_count: count,
                    count_origin: if !planned.count_was_omitted() {
                        CountOrigin::Explicit
                    } else if cycle {
                        CountOrigin::OmittedDefault
                    } else if let Some(origin) = fill_origin {
                        saved_count_origin(origin)?
                    } else {
                        CountOrigin::OmittedDefault
                    },
                }),
            };
            ordinal =
                ordinal
                    .checked_add(count)
                    .ok_or(ScoreMaterializationError::InvalidContract(
                        "ordinal overflow",
                    ))?;
            Ok(member)
        })
        .collect()
}

fn source_index(owner: &ScoreInstructionOrigin) -> usize {
    match owner {
        ScoreInstructionOrigin::SourceInstruction { instruction_index } => *instruction_index,
        ScoreInstructionOrigin::MacroEmit {
            source_instruction_index,
            ..
        } => *source_instruction_index,
    }
}

fn saved_owner(owner: &ScoreInstructionOrigin) -> ScoreSourceOwner {
    match owner {
        ScoreInstructionOrigin::SourceInstruction { instruction_index } => {
            ScoreSourceOwner::SourceInstruction {
                instruction_index: *instruction_index,
            }
        }
        ScoreInstructionOrigin::MacroEmit {
            source_instruction_index,
            provenance,
            ..
        } => ScoreSourceOwner::MacroEmit {
            source_instruction_index: *source_instruction_index,
            invocation_ordinal: provenance.invocation.invocation_ordinal,
            generated_ordinal: provenance.generated_ordinal,
        },
    }
}

fn saved_placement_anchor(
    anchor: &ObjectAnchor,
) -> Result<ResolvedPlacementAnchor, ScoreMaterializationError> {
    Ok(match anchor {
        ObjectAnchor::Named(region) => ResolvedPlacementAnchor::Named { region: *region },
        ObjectAnchor::Numeric(position) => ResolvedPlacementAnchor::Numeric {
            point: exact_position(position.into())?,
        },
        ObjectAnchor::GeneratedNumeric(position) => ResolvedPlacementAnchor::GeneratedNumeric {
            point: exact_position(*position)?,
        },
    })
}

fn saved_fill_owner(owner: FillPlanOwner) -> FillGroupOwner {
    match owner {
        FillPlanOwner::CoordinatedGroup { group_index } => {
            FillGroupOwner::CoordinatedGroup { group_index }
        }
        FillPlanOwner::Instruction {
            source_instruction_index,
        } => FillGroupOwner::Instruction {
            source_instruction_index,
        },
    }
}

fn scalar(value: Rational) -> Result<f64, ScoreMaterializationError> {
    value.to_f64().map_err(|_| {
        ScoreMaterializationError::InvalidContract("resolved rational cannot enter Score")
    })
}

fn saved_point(value: [Rational; 2]) -> Result<Point, ScoreMaterializationError> {
    Ok(Point::new(scalar(value[0])?, scalar(value[1])?))
}

fn saved_recipe(
    recipe: &PlacementRecipe,
) -> Result<ResolvedPlacementRecipe, ScoreMaterializationError> {
    Ok(match recipe {
        PlacementRecipe::Place => ResolvedPlacementRecipe::Place,
        PlacementRecipe::HorizontalLine { cell_width } => ResolvedPlacementRecipe::HorizontalLine {
            cell_width: scalar(*cell_width)?,
        },
        PlacementRecipe::VerticalLine { cell_height } => ResolvedPlacementRecipe::VerticalLine {
            cell_height: scalar(*cell_height)?,
        },
        PlacementRecipe::DiagonalLine { step } => ResolvedPlacementRecipe::DiagonalLine {
            step: saved_point(*step)?,
        },
        PlacementRecipe::Grid {
            columns,
            rows,
            filled_count,
            cell_width,
            cell_height,
            centroid,
            translate_to_numeric_anchor,
        } => ResolvedPlacementRecipe::Grid {
            columns: *columns,
            rows: *rows,
            filled_count: *filled_count,
            cell_width: scalar(*cell_width)?,
            cell_height: scalar(*cell_height)?,
            centroid: saved_point(*centroid)?,
            translate_to_numeric_anchor: *translate_to_numeric_anchor,
        },
        PlacementRecipe::ScatterUniformWithCentroidTranslation => {
            ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation
        }
        PlacementRecipe::FillUniformInRegionAndClip { .. } => {
            return Err(ScoreMaterializationError::InvalidContract(
                "fill requires target group",
            ));
        }
    })
}

fn ordinary_count_origin(omitted: bool) -> CountOrigin {
    if omitted {
        CountOrigin::OmittedDefault
    } else {
        CountOrigin::Explicit
    }
}

fn saved_count_origin(
    origin: &FillCountResolution,
) -> Result<CountOrigin, ScoreMaterializationError> {
    Ok(match origin {
        FillCountResolution::Explicit => CountOrigin::Explicit,
        FillCountResolution::FromRegionAndExtent { reference_extent } => {
            CountOrigin::OmittedRegionExtent {
                reference_extent: scalar(*reference_extent)?,
            }
        }
        FillCountResolution::BalancedGroup {
            reference_extents,
            explicit_counts,
        } => CountOrigin::OmittedBalancedGroup {
            reference_extents: reference_extents
                .iter()
                .copied()
                .map(scalar)
                .collect::<Result<_, _>>()?,
            explicit_counts: explicit_counts.clone(),
        },
    })
}

fn fill_parts(
    recipe: &PlacementRecipe,
) -> Result<(&ResolvedFillRegion, &FillCountResolution), ScoreMaterializationError> {
    match recipe {
        PlacementRecipe::FillUniformInRegionAndClip {
            region,
            count_resolution,
        } => Ok((region, count_resolution)),
        _ => Err(ScoreMaterializationError::InvalidContract(
            "fill group has no fill recipe",
        )),
    }
}

fn saved_site(source: &crate::SourceOccurrence) -> ScoreSourceSite {
    ScoreSourceSite {
        region_index: source.region_index,
        clause_index: source.clause_index,
    }
}

fn saved_target(region: &ResolvedFillRegion) -> Result<FillTarget, ScoreMaterializationError> {
    let owner = match &region.owner {
        FillRegionOwner::OmittedCanvas => FillTargetOwner::OmittedCanvas,
        FillRegionOwner::ExplicitCanvas(source) => FillTargetOwner::ExplicitCanvas {
            source: saved_site(source),
        },
        FillRegionOwner::Named(identity) => FillTargetOwner::Named {
            category: identity.category.clone(),
            id: identity.id.clone(),
        },
        FillRegionOwner::InlineShape {
            source_instruction_index,
            source,
        } => FillTargetOwner::InlineShape {
            source_instruction_index: *source_instruction_index,
            source: saved_site(source),
        },
    };
    let geometry = match &region.geometry {
        FillRegionGeometry::Rectangle { bounds } => FillTargetGeometry::Rectangle {
            bounds: [
                scalar(bounds[0])?,
                scalar(bounds[1])?,
                scalar(bounds[2])?,
                scalar(bounds[3])?,
            ],
        },
        FillRegionGeometry::Shape {
            primitive,
            dimensions,
            arc_form,
            anchor,
            rotation_degrees,
            contour_variation,
        } => FillTargetGeometry::Shape {
            primitive: *primitive,
            dimensions: saved_dimensions(*dimensions)?,
            arc_form: *arc_form,
            anchor: match anchor {
                ObjectAnchor::Named(region) => FillTargetAnchor::Named { region: *region },
                ObjectAnchor::Numeric(position) => FillTargetAnchor::Numeric {
                    point: exact_position(position.into())?,
                },
                ObjectAnchor::GeneratedNumeric(position) => FillTargetAnchor::GeneratedNumeric {
                    point: exact_position(*position)?,
                },
            },
            rotation_degrees: *rotation_degrees,
            contour_variation: contour_variation.clone(),
        },
    };
    Ok(FillTarget {
        owner,
        geometry,
        reference_area: scalar(region.reference_area)?,
    })
}

fn exact_position(
    position: crate::geometry::ExactPosition,
) -> Result<Point, ScoreMaterializationError> {
    let convert = |value| {
        Rational::from_decimal(value)
            .map_err(|_| ScoreMaterializationError::InvalidContract("invalid resolved position"))
            .and_then(scalar)
    };
    Ok(Point::new(convert(position.x)?, convert(position.y)?))
}

fn saved_dimensions(
    dimensions: ResolvedGeometryDimensions,
) -> Result<ResolvedShapeDimensions, ScoreMaterializationError> {
    Ok(match dimensions {
        ResolvedGeometryDimensions::Bbox { width, height } => ResolvedShapeDimensions::Bbox {
            width: scalar(width)?,
            height: scalar(height)?,
        },
        ResolvedGeometryDimensions::RegularTriangle { side } => {
            ResolvedShapeDimensions::RegularTriangle {
                side: scalar(side)?,
            }
        }
        ResolvedGeometryDimensions::Polygon { radius, sides } => ResolvedShapeDimensions::Polygon {
            radius: scalar(radius)?,
            sides,
        },
        ResolvedGeometryDimensions::Line { length } => ResolvedShapeDimensions::Line {
            length: scalar(length)?,
        },
        ResolvedGeometryDimensions::Circle { radius } => ResolvedShapeDimensions::Circle {
            radius: scalar(radius)?,
        },
        ResolvedGeometryDimensions::Arc { chord, sagitta } => ResolvedShapeDimensions::Arc {
            chord: scalar(chord)?,
            sagitta: scalar(sagitta)?,
        },
        ResolvedGeometryDimensions::Point { radius } => ResolvedShapeDimensions::Point {
            radius: scalar(radius)?,
        },
        ResolvedGeometryDimensions::CenteredSize { width, height } => {
            ResolvedShapeDimensions::CenteredSize {
                width: scalar(width)?,
                height: scalar(height)?,
            }
        }
        ResolvedGeometryDimensions::Square { side } => ResolvedShapeDimensions::Square {
            side: scalar(side)?,
        },
    })
}

fn arrangement(
    count: u32,
    color_cycle: &[inku_score::Color],
    resolved: ResolvedArrangement,
) -> Arrangement {
    Arrangement {
        count,
        group_size: 1,
        layout: Layout::Horizontal,
        rows: None,
        cols: None,
        jitter: 0.0,
        path: ArrangementPath::None,
        color_cycle: color_cycle.to_vec(),
        margin: 0.0,
        center: None,
        radius: None,
        density: Density::None,
        cluster_count: None,
        fade: Fade::None,
        preserve_space: false,
        rhythm_spacing: RhythmSpacing::None,
        resolved: Some(resolved),
    }
}
