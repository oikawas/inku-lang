//! Score-level performance planning and composite-group expansion.

use crate::arrangement::{ArrangementRequest, expand_arrangement};
use crate::planning::{
    PlanningWarning, ensure_line_coordinates, instruction_anchor, move_anchor_to,
    resolve_at_region, resolve_relation, scale_instruction,
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
pub struct PerformancePlan {
    pub score: Score,
    pub warnings: Vec<PlanningWarning>,
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
) -> Instruction {
    let scaled = scale_instruction(member, scale);
    let member_anchor = instruction_anchor(&scaled);
    let delta = Point::new(
        member_anchor.x - source_anchor.x,
        member_anchor.y - source_anchor.y,
    );
    let radians = rotation_delta.to_radians();
    let rotated = Point::new(
        delta.x * radians.cos() - delta.y * radians.sin(),
        delta.x * radians.sin() + delta.y * radians.cos(),
    );
    let target_anchor = instruction_anchor(target_head);
    let mut moved = move_anchor_to(
        &scaled,
        Point::new(target_anchor.x + rotated.x, target_anchor.y + rotated.y),
        true,
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

fn expand_composite_groups(
    score: &Score,
    placement_seed: Option<Seed>,
    performance_seed: Option<Seed>,
    canvas: Option<CanvasSize>,
) -> Score {
    let mut expanded = Vec::new();
    let mut index = 0;
    while index < score.instructions.len() {
        let head = &score.instructions[index];
        let Some(arrangement) = head.arrangement.as_ref() else {
            expanded.push(head.clone());
            index += 1;
            continue;
        };
        let group_size = arrangement.group_size as usize;
        if group_size == 1 {
            expanded.push(head.clone());
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
        let source_anchor = instruction_anchor(&prepared_head);
        let source_rotation = prepared_head.rotation.unwrap_or(0.0);
        let source_extent = instruction_extent(&prepared_head);
        let cycles_color = !arrangement.color_cycle.is_empty();
        for copy_head in copies {
            let rotation_delta = copy_head.rotation.unwrap_or(0.0) - source_rotation;
            let scale = instruction_extent(&copy_head) / source_extent;
            let color = cycles_color.then_some(copy_head.color);
            expanded.push(copy_head.clone());
            for member in &members[1..] {
                expanded.push(composite_member_copy(
                    member,
                    source_anchor,
                    &copy_head,
                    rotation_delta,
                    scale,
                    color,
                ));
            }
        }
        index += group_size;
    }
    let mut result = score.clone();
    result.instructions = expanded;
    result
}

/// Resolve the complete deterministic pre-draw instruction sequence.
#[must_use]
pub fn resolve_performance(request: PerformanceRequest<'_>) -> PerformancePlan {
    let placement_seed = request.composition_seed.or(request.performance_seed);
    let expanded = expand_composite_groups(
        request.score,
        placement_seed,
        request.performance_seed,
        request.canvas,
    );
    let Some(seed) = request.performance_seed else {
        return PerformancePlan {
            score: expanded,
            warnings: Vec::new(),
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
            let relation = resolve_relation(&instruction, &resolved, seed, index);
            instruction = relation.instruction;
            if let Some(warning) = relation.warning {
                warnings.push(warning);
            }
        }
        resolved.push(instruction);
    }
    let mut score = expanded;
    score.instructions = resolved;
    PerformancePlan { score, warnings }
}
