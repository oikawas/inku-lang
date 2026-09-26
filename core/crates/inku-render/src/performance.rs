//! Score-level performance planning and composite-group expansion.

use crate::arrangement::{ArrangementRequest, expand_arrangement};
use crate::effects::MarkEffects;
use crate::geometry::{point_from_short_side_units, point_to_short_side_units};
use crate::planning::{
    PlanningWarning, ensure_line_coordinates, instruction_anchor_on_canvas,
    move_anchor_to_on_canvas, resolve_at_region, resolve_relation_on_canvas,
    scale_instruction_on_canvas,
};
use crate::types::{CanvasSize, Color, Instruction, Layout, Point, Score, Seed};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PerformanceRequest<'a> {
    pub score: &'a Score,
    pub performance_seed: Option<Seed>,
    pub composition_seed: Option<Seed>,
    pub canvas: Option<CanvasSize>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct PerformedFillScope {
    /// Stable saved-Score owner of the target and all performed contents.
    pub owner: inku_score::FillGroupOwner,
    /// Final target contour in SVG pixel coordinates (`unit == 1` without a canvas).
    pub prepared_region: crate::fill_geometry::PreparedRegion,
    /// Enclosing fill scope, when a filled Macro contains another fill.
    pub parent_scope_index: Option<usize>,
    /// Final performed instruction indices belonging to this target.
    pub instruction_indices: Vec<usize>,
    /// Complete performed units from the nearest owner through the outer source unit.
    /// The last entry preserves the accepted exact count if any member cannot clip.
    pub atomic_instruction_groups: Vec<Vec<usize>>,
}

/// What the renderer reads about one performed instruction besides the
/// instruction itself. The instruction stays at the same index of the plan's
/// `score.instructions`, because the presence layer, the material filters and
/// the oil fill limit read the performed Score as a whole.
#[derive(Clone, Debug, PartialEq)]
pub struct PerformedInstruction {
    /// Pre-omission expanded ordinal used by drawing IDs and seed material.
    pub instruction_index: usize,
    /// Original Score owner of this performed instruction.
    pub original_instruction_index: usize,
    /// Stable seed material for rigid group transforms. `None` retains the
    /// normal seed derived from the performed instruction.
    pub seed_override: Option<Seed>,
    /// Geometry-only transform in physical short-side units.
    pub transform: crate::affine::AffineTransform,
    /// Performed centerline of a Line targeted by an explicit path connection.
    /// Points are in physical short-side units and already include every transform.
    pub line_centerline: Option<Vec<Point>>,
    /// Performed index of the follower Arc of a successful checked-Touching
    /// closed pair. The earlier Arc holds it so that the pair's fill can paint
    /// below both outlines.
    pub closed_arc_pair_follower: Option<usize>,
    /// Innermost enclosing entry of the plan's `fill_scopes`.
    pub fill_scope_index: Option<usize>,
    /// What the instruction inherits from the arrangement that copied it.
    pub effects: MarkEffects,
}

impl PerformedInstruction {
    /// An instruction performed as written: its own seed, no transform, and no
    /// centerline, closed pair, fill scope or arrangement effect.
    pub(crate) fn plain(instruction_index: usize, original_instruction_index: usize) -> Self {
        Self {
            instruction_index,
            original_instruction_index,
            seed_override: None,
            transform: crate::affine::AffineTransform::identity(),
            line_centerline: None,
            closed_arc_pair_follower: None,
            fill_scope_index: None,
            effects: MarkEffects::default(),
        }
    }
}

/// Where one instruction of an expanded Score came from.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct ExpandedOrigin {
    /// Original Score owner.
    pub original_instruction_index: usize,
    /// What a composite group's head copy inherits from the arrangement.
    pub effects: MarkEffects,
}

impl ExpandedOrigin {
    fn plain(original_instruction_index: usize) -> Self {
        Self {
            original_instruction_index,
            effects: MarkEffects::default(),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct PerformancePlan {
    pub score: Score,
    pub warnings: Vec<PlanningWarning>,
    /// One entry for each of `score.instructions`, in the same order.
    pub performed: Vec<PerformedInstruction>,
    /// Prepared fill targets after their enclosing placement/relation/affine transforms.
    pub fill_scopes: Vec<PerformedFillScope>,
    /// Recomputed admitted saved-Score demand when explicit authority was supplied.
    pub resource_demand: Option<inku_score::ResourceDemand>,
    pub resource_diagnostics: Vec<inku_score::SavedScoreResourceDiagnostic>,
    pub relation_diagnostics: Vec<inku_score::SavedScoreRelationDiagnostic>,
    pub execution: Option<inku_score::ScoreExecutionSummary>,
}

impl PerformancePlan {
    /// Each performed instruction with what the renderer reads about it.
    ///
    /// # Panics
    ///
    /// When a builder left `score.instructions` and `performed` at different
    /// lengths; reading them apart would drop instructions without a trace.
    pub fn performed_instructions(
        &self,
    ) -> impl Iterator<Item = (&Instruction, &PerformedInstruction)> {
        assert_eq!(
            self.score.instructions.len(),
            self.performed.len(),
            "one performed entry per instruction"
        );
        self.score.instructions.iter().zip(&self.performed)
    }

    /// The drawing ordinal of each performed instruction.
    #[must_use]
    pub fn instruction_indices(&self) -> Vec<usize> {
        self.performed
            .iter()
            .map(|entry| entry.instruction_index)
            .collect()
    }

    /// The original Score owner of each performed instruction.
    #[must_use]
    pub fn original_instruction_indices(&self) -> Vec<usize> {
        self.performed
            .iter()
            .map(|entry| entry.original_instruction_index)
            .collect()
    }

    /// The geometry-only transform of each performed instruction.
    #[must_use]
    pub fn instruction_transforms(&self) -> Vec<crate::affine::AffineTransform> {
        self.performed.iter().map(|entry| entry.transform).collect()
    }

    /// The seed override of each performed instruction.
    #[must_use]
    pub fn instruction_seed_overrides(&self) -> Vec<Option<Seed>> {
        self.performed
            .iter()
            .map(|entry| entry.seed_override)
            .collect()
    }
}

fn instruction_extent(instruction: &Instruction) -> f64 {
    if let Some(radius) = instruction.radius {
        return radius.abs().max(1.0e-9);
    }
    if let Some(size) = instruction.size {
        return size.x.hypot(size.y).max(1.0e-9);
    }
    if let (Some(start), Some(end)) = (instruction.from_, instruction.to) {
        return (end.x - start.x).hypot(end.y - start.y).max(1.0e-9);
    }
    1.0
}

fn composite_member_copy(
    member: &Instruction,
    source_anchor: Point,
    target_head: &Instruction,
    rotation_delta: f64,
    scale: f64,
    color: Option<Color>,
    canvas: Option<CanvasSize>,
) -> Instruction {
    let scaled = scale_instruction_on_canvas(member, scale, canvas);
    let member_anchor =
        point_to_short_side_units(instruction_anchor_on_canvas(&scaled, canvas), canvas);
    let source_anchor = point_to_short_side_units(source_anchor, canvas);
    let delta = Point::new(
        member_anchor.x - source_anchor.x,
        member_anchor.y - source_anchor.y,
    );
    let radians = rotation_delta.to_radians();
    let rotated = Point::new(
        delta.x * radians.cos() - delta.y * radians.sin(),
        delta.x * radians.sin() + delta.y * radians.cos(),
    );
    let target_anchor =
        point_to_short_side_units(instruction_anchor_on_canvas(target_head, canvas), canvas);
    let mut moved = move_anchor_to_on_canvas(
        &scaled,
        point_from_short_side_units(
            Point::new(target_anchor.x + rotated.x, target_anchor.y + rotated.y),
            canvas,
        ),
        true,
        canvas,
    );
    moved.arrangement = None;
    if rotation_delta != 0.0 {
        moved.rotation = Some(member.rotation.unwrap_or(0.0) + rotation_delta);
    }
    if let Some(color) = color {
        moved.color = color;
    }
    moved
}

pub(crate) fn expand_composite_groups_with_origins(
    score: &Score,
    placement_seed: Option<Seed>,
    performance_seed: Option<Seed>,
    canvas: Option<CanvasSize>,
) -> (Score, Vec<ExpandedOrigin>) {
    let mut expanded = Vec::new();
    let mut origins = Vec::new();
    let mut index = 0;
    while index < score.instructions.len() {
        let head = &score.instructions[index];
        let Some(arrangement) = head.arrangement.as_ref() else {
            expanded.push(head.clone());
            origins.push(ExpandedOrigin::plain(index));
            index += 1;
            continue;
        };
        let group_size = arrangement.group_size as usize;
        if group_size == 1 {
            expanded.push(head.clone());
            origins.push(ExpandedOrigin::plain(index));
            index += 1;
            continue;
        }
        let end = (index + group_size).min(score.instructions.len());
        let members = &score.instructions[index..end];
        let mut prepared_head = ensure_line_coordinates(head);
        if let Some(seed) = performance_seed {
            prepared_head = resolve_at_region(&prepared_head, seed, index, canvas);
        }
        let copies = expand_arrangement(ArrangementRequest {
            instruction: &prepared_head,
            placement_seed,
            performance_seed,
            canvas,
        });
        let source_anchor = instruction_anchor_on_canvas(&prepared_head, canvas);
        let source_rotation = prepared_head.rotation.unwrap_or(0.0);
        let source_extent = instruction_extent(&prepared_head);
        let cycles_color = !arrangement.color_cycle.is_empty();
        for copy in copies {
            let copy_head = copy.instruction;
            let rotation_delta = copy_head.rotation.unwrap_or(0.0) - source_rotation;
            let scale = instruction_extent(&copy_head) / source_extent;
            let color = cycles_color.then_some(copy_head.color);
            expanded.push(copy_head.clone());
            origins.push(ExpandedOrigin {
                original_instruction_index: index,
                effects: copy.effects,
            });
            // Members follow the head's place, size and cycled color, not
            // its fade.
            for (member_offset, member) in members[1..].iter().enumerate() {
                expanded.push(composite_member_copy(
                    member,
                    source_anchor,
                    &copy_head,
                    rotation_delta,
                    scale,
                    color,
                    canvas,
                ));
                origins.push(ExpandedOrigin::plain(index + member_offset + 1));
            }
        }
        index += group_size;
    }
    let mut result = score.clone();
    result.instructions = expanded;
    (result, origins)
}

/// Resolve the complete deterministic pre-draw instruction sequence.
#[must_use]
pub fn resolve_performance(request: PerformanceRequest<'_>) -> PerformancePlan {
    let placement_seed = request.composition_seed.or(request.performance_seed);
    let (expanded, origins) = expand_composite_groups_with_origins(
        request.score,
        placement_seed,
        request.performance_seed,
        request.canvas,
    );
    // Each expanded instruction is performed once, in order.
    let performed = origins
        .into_iter()
        .enumerate()
        .map(|(index, origin)| PerformedInstruction {
            effects: origin.effects,
            ..PerformedInstruction::plain(index, origin.original_instruction_index)
        })
        .collect();
    let Some(seed) = request.performance_seed else {
        return PerformancePlan {
            score: expanded,
            warnings: Vec::new(),
            performed,
            fill_scopes: Vec::new(),
            resource_demand: None,
            resource_diagnostics: Vec::new(),
            relation_diagnostics: Vec::new(),
            execution: None,
        };
    };
    let mut resolved = Vec::with_capacity(expanded.instructions.len());
    let mut warnings = Vec::new();
    for (index, original) in expanded.instructions.iter().enumerate() {
        let mut instruction = ensure_line_coordinates(original);
        let grid = instruction
            .arrangement
            .as_ref()
            .is_some_and(|arrangement| arrangement.layout == Layout::Grid);
        if grid {
            if let Some(relation) = instruction.relation.take() {
                warnings.push(PlanningWarning {
                    instruction_index: index,
                    relation: relation.kind,
                    reason: "grid layout consumes relation",
                });
            }
        } else {
            instruction = resolve_at_region(&instruction, seed, index, request.canvas);
            let relation =
                resolve_relation_on_canvas(&instruction, &resolved, seed, index, request.canvas);
            instruction = relation.instruction;
            if let Some(warning) = relation.warning {
                warnings.push(warning);
            }
        }
        resolved.push(instruction);
    }
    let mut score = expanded;
    score.instructions = resolved;
    PerformancePlan {
        score,
        warnings,
        performed,
        fill_scopes: Vec::new(),
        resource_demand: None,
        resource_diagnostics: Vec::new(),
        relation_diagnostics: Vec::new(),
        execution: None,
    }
}
