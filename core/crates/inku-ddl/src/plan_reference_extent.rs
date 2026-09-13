//! Seed-independent density footprint of one complete declared Macro body.
//!
//! This is not an ink bound. Each Emit keeps the common primitive reference
//! width, separately from its center envelope. Rotation moves internal centers
//! but never enlarges that width; scale uses its largest absolute axis. Thus a
//! single Emit and its Direct spelling have the same density, including a
//! rotation-only Transform. Repetition contributes its declared center domain,
//! without expanding instances or multiplying by the outer source count.

use std::collections::HashSet;

use inku_score::{AnchorPoint, CanvasFormat};

use crate::ScoreFieldGap;
use crate::composition_plan::{
    FillRegionGeometry, ObjectAnchor, ObjectPlacementPlan, PlacementMemberPlan, PlacementRecipe,
    TransformGroupPlan,
};
use crate::score_lowering::{Rational, reference_extent};

#[derive(Clone, Copy)]
struct Footprint {
    centers: [f64; 4],
    radius: f64,
    drawable: bool,
}

impl Footprint {
    fn point(center: [f64; 2], radius: f64, drawable: bool) -> Self {
        Self {
            centers: [center[0], center[1], center[0], center[1]],
            radius,
            drawable,
        }
    }

    fn union(self, other: Self) -> Self {
        Self {
            centers: [
                self.centers[0].min(other.centers[0]),
                self.centers[1].min(other.centers[1]),
                self.centers[2].max(other.centers[2]),
                self.centers[3].max(other.centers[3]),
            ],
            radius: self.radius.max(other.radius),
            drawable: self.drawable || other.drawable,
        }
    }

    fn transform(self, group: &TransformGroupPlan) -> Result<Self, ScoreFieldGap> {
        let pivot = [
            (self.centers[0] + self.centers[2]) / 2.0,
            (self.centers[1] + self.centers[3]) / 2.0,
        ];
        let (sin, cos) = group.rotation_degrees.to_radians().sin_cos();
        let mut result: Option<Self> = None;
        for x in [self.centers[0], self.centers[2]] {
            for y in [self.centers[1], self.centers[3]] {
                let dx = (x - pivot[0]) * group.scale_x;
                let dy = (y - pivot[1]) * group.scale_y;
                let point = Self::point(
                    [
                        pivot[0] + cos * dx - sin * dy + group.translate_x,
                        pivot[1] + sin * dx + cos * dy + group.translate_y,
                    ],
                    self.radius * group.scale_x.abs().max(group.scale_y.abs()),
                    self.drawable,
                );
                result = Some(result.map_or(point, |previous| previous.union(point)));
            }
        }
        let result = result.ok_or(ScoreFieldGap::GeometryRepresentationLimit)?;
        if result
            .centers
            .into_iter()
            .chain([result.radius])
            .all(f64::is_finite)
        {
            Ok(result)
        } else {
            Err(ScoreFieldGap::GeometryRepresentationLimit)
        }
    }
}

struct TransformNode<'a> {
    group: &'a TransformGroupPlan,
    children: Vec<usize>,
}

fn contains(
    outer: &TransformGroupPlan,
    outer_anchors: &HashSet<usize>,
    inner: &TransformGroupPlan,
) -> bool {
    (inner.start == inner.end || (outer.start <= inner.start && inner.end <= outer.end))
        && inner
            .anchor_indices
            .iter()
            .all(|index| outer_anchors.contains(index))
}

/// The transform list is already in lexical postorder. Each node is consumed
/// once by its parent, and each object once by its innermost range. Work depends
/// on source nodes and their explicit ownership lists, never logical counts.
pub(crate) fn reference_member_extent(
    objects: &[ObjectPlacementPlan],
    transforms: &[TransformGroupPlan],
    anchors: &[AnchorPoint],
    member: &PlacementMemberPlan,
    canvas: CanvasFormat,
) -> Result<Rational, ScoreFieldGap> {
    let member = member.member();
    if member.start > member.end || member.end > objects.len() {
        return Err(ScoreFieldGap::GeometryRepresentationLimit);
    }
    // Preserve the common exact rational for an untransformed singleton. This
    // avoids introducing a floating boundary solely through source packaging.
    if member.end == member.start + 1
        && member.anchor_indices.is_empty()
        && member.transform_group_indices.iter().all(|index| {
            transforms
                .get(*index)
                .is_some_and(|group| group.scale_x.abs() == 1.0 && group.scale_y.abs() == 1.0)
        })
        && matches!(objects[member.start].recipe, PlacementRecipe::Place)
    {
        return reference_extent(objects[member.start].dimensions);
    }
    let short = canvas.width_units.min(canvas.height_units);
    if short == 0 {
        return Err(ScoreFieldGap::GeometryRepresentationLimit);
    }
    let axes = [
        f64::from(canvas.width_units) / f64::from(short),
        f64::from(canvas.height_units) / f64::from(short),
    ];
    let mut nodes: Vec<TransformNode<'_>> = Vec::new();
    let mut roots: Vec<usize> = Vec::new();
    for &index in &member.transform_group_indices {
        let group = transforms
            .get(index)
            .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?;
        if group.start < member.start || group.end > member.end || group.start > group.end {
            return Err(ScoreFieldGap::GeometryRepresentationLimit);
        }
        let mut children = Vec::new();
        let outer_anchors = group.anchor_indices.iter().copied().collect();
        while roots
            .last()
            .is_some_and(|index| contains(group, &outer_anchors, nodes[*index].group))
        {
            children.push(
                roots
                    .pop()
                    .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?,
            );
        }
        children.reverse();
        roots.push(nodes.len());
        nodes.push(TransformNode { group, children });
    }
    let mut consumed_anchors = HashSet::new();
    let footprint = range_footprint(
        member.start,
        member.end,
        &member.anchor_indices,
        &roots,
        &nodes,
        objects,
        anchors,
        axes,
        &mut consumed_anchors,
    )?
    .ok_or(ScoreFieldGap::FillRegionHasNoArea)?;
    if !footprint.drawable {
        return Err(ScoreFieldGap::FillRegionHasNoArea);
    }
    let extent = (footprint.centers[2] - footprint.centers[0])
        .max(footprint.centers[3] - footprint.centers[1])
        + 2.0 * footprint.radius;
    finite_ratio(extent)
}

#[allow(clippy::too_many_arguments)]
fn range_footprint(
    start: usize,
    end: usize,
    anchor_indices: &[usize],
    children: &[usize],
    nodes: &[TransformNode<'_>],
    objects: &[ObjectPlacementPlan],
    anchors: &[AnchorPoint],
    axes: [f64; 2],
    consumed_anchors: &mut HashSet<usize>,
) -> Result<Option<Footprint>, ScoreFieldGap> {
    let mut result = None;
    let merge = |result: &mut Option<Footprint>, next: Footprint| {
        *result = Some(result.map_or(next, |previous| previous.union(next)));
    };
    let mut cursor = start;
    for &index in children {
        let node = &nodes[index];
        if node.group.start < cursor || node.group.end > end {
            return Err(ScoreFieldGap::GeometryRepresentationLimit);
        }
        for object in &objects[cursor..node.group.start] {
            merge(&mut result, object_footprint(object, axes)?);
        }
        if let Some(child) = range_footprint(
            node.group.start,
            node.group.end,
            &node.group.anchor_indices,
            &node.children,
            nodes,
            objects,
            anchors,
            axes,
            consumed_anchors,
        )? {
            merge(&mut result, child.transform(node.group)?);
        }
        cursor = node.group.end;
    }
    for object in &objects[cursor..end] {
        merge(&mut result, object_footprint(object, axes)?);
    }
    for &index in anchor_indices {
        if consumed_anchors.insert(index) {
            let anchor = anchors
                .get(index)
                .ok_or(ScoreFieldGap::GeometryRepresentationLimit)?;
            let position = match (&anchor.position, &anchor.at) {
                (Some(position), None) => [position.x, position.y],
                (None, Some(at)) => [
                    (at.region[0] + at.region[2]) / 2.0,
                    (at.region[1] + at.region[3]) / 2.0,
                ],
                _ => return Err(ScoreFieldGap::GeometryRepresentationLimit),
            };
            merge(
                &mut result,
                Footprint::point([position[0] * axes[0], position[1] * axes[1]], 0.0, false),
            );
        }
    }
    Ok(result)
}

fn anchor_position(anchor: &ObjectAnchor, axes: [f64; 2]) -> Result<[f64; 2], ScoreFieldGap> {
    let value = match anchor {
        ObjectAnchor::GeneratedNumeric(position) => [
            Rational::from_decimal(position.x)?.to_f64()?,
            Rational::from_decimal(position.y)?.to_f64()?,
        ],
        ObjectAnchor::Numeric(position) => [
            Rational::from_decimal(position.x.decimal.value)?.to_f64()?,
            Rational::from_decimal(position.y.decimal.value)?.to_f64()?,
        ],
        ObjectAnchor::Named(region) => {
            [(region[0] + region[2]) / 2.0, (region[1] + region[3]) / 2.0]
        }
    };
    Ok([value[0] * axes[0], value[1] * axes[1]])
}

fn object_footprint(
    object: &ObjectPlacementPlan,
    axes: [f64; 2],
) -> Result<Footprint, ScoreFieldGap> {
    let center = anchor_position(&object.anchor, axes)?;
    let radius = reference_extent(object.dimensions)?.to_f64()? / 2.0;
    let mut footprint = Footprint::point(center, radius, true);
    let symmetric = |dx: f64, dy: f64| {
        [
            center[0] - dx.abs() / 2.0,
            center[1] - dy.abs() / 2.0,
            center[0] + dx.abs() / 2.0,
            center[1] + dy.abs() / 2.0,
        ]
    };
    let intervals = f64::from(object.count.saturating_sub(1));
    footprint.centers = match &object.recipe {
        PlacementRecipe::Place => footprint.centers,
        PlacementRecipe::HorizontalLine { cell_width } => {
            symmetric(intervals * cell_width.to_f64()?, 0.0)
        }
        PlacementRecipe::VerticalLine { cell_height } => {
            symmetric(0.0, intervals * cell_height.to_f64()?)
        }
        PlacementRecipe::DiagonalLine { step } => {
            symmetric(intervals * step[0].to_f64()?, intervals * step[1].to_f64()?)
        }
        PlacementRecipe::ScatterUniformWithCentroidTranslation if object.count == 1 => {
            footprint.centers
        }
        PlacementRecipe::ScatterUniformWithCentroidTranslation => {
            symmetric(object.domain[0].to_f64()?, object.domain[1].to_f64()?)
        }
        PlacementRecipe::Grid {
            columns,
            filled_count,
            cell_width,
            cell_height,
            centroid,
            translate_to_numeric_anchor,
            ..
        } => {
            if *columns == 0 || *filled_count == 0 {
                return Err(ScoreFieldGap::GeometryRepresentationLimit);
            }
            let width = cell_width.to_f64()?;
            let height = cell_height.to_f64()?;
            let offset = if *translate_to_numeric_anchor {
                [
                    center[0] - centroid[0].to_f64()?,
                    center[1] - centroid[1].to_f64()?,
                ]
            } else {
                [0.0, 0.0]
            };
            [
                offset[0] + width / 2.0,
                offset[1] + height / 2.0,
                offset[0] + (columns.min(filled_count).saturating_sub(1) as f64 + 0.5) * width,
                offset[1] + ((filled_count - 1) / columns) as f64 * height + height / 2.0,
            ]
        }
        PlacementRecipe::FillUniformInRegionAndClip { region, .. } => {
            // The clip, not a separately translated motif radius, bounds this body.
            match &region.geometry {
                FillRegionGeometry::Rectangle { bounds } => {
                    footprint.radius = 0.0;
                    [
                        bounds[0].to_f64()? * axes[0],
                        bounds[1].to_f64()? * axes[1],
                        bounds[2].to_f64()? * axes[0],
                        bounds[3].to_f64()? * axes[1],
                    ]
                }
                FillRegionGeometry::Shape {
                    dimensions, anchor, ..
                } => {
                    footprint.radius = reference_extent(*dimensions)?.to_f64()? / 2.0;
                    let center = anchor_position(anchor, axes)?;
                    [center[0], center[1], center[0], center[1]]
                }
            }
        }
    };
    Ok(footprint)
}

fn finite_ratio(value: f64) -> Result<Rational, ScoreFieldGap> {
    if !value.is_finite() || value <= 0.0 || value > 1_000_000.0 {
        return Err(if value == 0.0 {
            ScoreFieldGap::FillRegionHasNoArea
        } else {
            ScoreFieldGap::GeometryRepresentationLimit
        });
    }
    let numerator = (value * 1_000_000_000_000.0).round() as i128;
    if numerator == 0 {
        return Err(ScoreFieldGap::GeometryRepresentationLimit);
    }
    let mut a = numerator;
    let mut b = 1_000_000_000_000_i128;
    while b != 0 {
        (a, b) = (b, a % b);
    }
    Rational::from_ratio(numerator / a, 1_000_000_000_000 / a)
}
