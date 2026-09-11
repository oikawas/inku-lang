//! Physical geometry used by group pivots, endpoint relations and final bounds.

use crate::affine::AffineTransform;
use crate::cloudform::{CloudformRequest, generate_cloudform_contour};
use crate::geometry::{point_to_short_side_units, polygon_points};
use crate::planning::{
    Bounds, endpoint_geometry, group_instruction_bounds_on_canvas, instruction_anchor_on_canvas,
};
use crate::types::{
    ArcForm, CRESCENT_REFERENCE_CUBICS, CanvasSize, Instruction, Point, Primitive, Seed,
    crescent_transform_point,
};

pub(crate) fn endpoints(
    instruction: &Instruction,
    canvas: Option<CanvasSize>,
    transform: AffineTransform,
) -> Option<(Point, Point, Point, Point)> {
    endpoint_geometry(instruction, canvas).map(|(start, end, first, last)| {
        (
            transform.apply(start),
            transform.apply(end),
            transform.vector(first),
            transform.vector(last),
        )
    })
}

fn point_bounds(points: impl IntoIterator<Item = Point>) -> Option<Bounds> {
    let mut points = points.into_iter();
    let first = points.next()?;
    if !first.x.is_finite() || !first.y.is_finite() {
        return None;
    }
    let bounds = points.try_fold(
        Bounds {
            min: first,
            max: first,
        },
        |mut bounds, point| {
            if !point.x.is_finite() || !point.y.is_finite() {
                return None;
            }
            bounds.min.x = bounds.min.x.min(point.x);
            bounds.min.y = bounds.min.y.min(point.y);
            bounds.max.x = bounds.max.x.max(point.x);
            bounds.max.y = bounds.max.y.max(point.y);
            Some(bounds)
        },
    )?;
    [bounds.min.x, bounds.min.y, bounds.max.x, bounds.max.y]
        .into_iter()
        .all(f64::is_finite)
        .then_some(bounds)
}

fn cubic_value(points: [Point; 4], t: f64) -> Point {
    let s = 1.0 - t;
    let weights = [s * s * s, 3.0 * s * s * t, 3.0 * s * t * t, t * t * t];
    points
        .into_iter()
        .zip(weights)
        .fold(Point::new(0.0, 0.0), |sum, (point, weight)| {
            Point::new(sum.x + point.x * weight, sum.y + point.y * weight)
        })
}

fn cubic_extrema(points: [Point; 4]) -> Vec<Point> {
    let mut result = vec![points[0], points[3]];
    for values in [points.map(|point| point.x), points.map(|point| point.y)] {
        let [p0, p1, p2, p3] = values;
        let a = -p0 + 3.0 * p1 - 3.0 * p2 + p3;
        let b = 2.0 * (p0 - 2.0 * p1 + p2);
        let c = p1 - p0;
        let mut roots = Vec::new();
        if a.abs() < 1.0e-14 {
            if b.abs() >= 1.0e-14 {
                roots.push(-c / b);
            }
        } else {
            let discriminant = b * b - 4.0 * a * c;
            if discriminant >= 0.0 {
                let root = discriminant.sqrt();
                roots.extend([(-b + root) / (2.0 * a), (-b - root) / (2.0 * a)]);
            }
        }
        result.extend(
            roots
                .into_iter()
                .filter(|t| *t > 0.0 && *t < 1.0)
                .map(|t| cubic_value(points, t)),
        );
    }
    result
}

pub(crate) fn bounds(
    instruction: &Instruction,
    seed: Option<Seed>,
    index: usize,
    canvas: Option<CanvasSize>,
    seed_override: Option<Seed>,
    transform: AffineTransform,
) -> Option<Bounds> {
    if transform.is_identity() {
        return group_instruction_bounds_on_canvas(instruction, seed, index, canvas, seed_override);
    }
    let anchor =
        point_to_short_side_units(instruction_anchor_on_canvas(instruction, canvas), canvas);
    let transform = transform.compose(AffineTransform::around(
        anchor,
        1.0,
        1.0,
        instruction.rotation.unwrap_or(0.0),
        Point::new(0.0, 0.0),
    ));
    let center = || {
        instruction
            .center
            .map(|p| point_to_short_side_units(p, canvas))
    };
    let ellipse_bounds = |center: Point, rx: f64, ry: f64| {
        let center = transform.apply(center);
        let dx = (transform.a * rx).hypot(transform.c * ry);
        let dy = (transform.b * rx).hypot(transform.d * ry);
        point_bounds([
            Point::new(center.x - dx, center.y - dy),
            Point::new(center.x + dx, center.y + dy),
        ])
    };
    match instruction.primitive {
        Primitive::Line => point_bounds(
            [instruction.from_?, instruction.to?]
                .map(|p| transform.apply(point_to_short_side_units(p, canvas))),
        ),
        Primitive::Circle | Primitive::Point => {
            ellipse_bounds(center()?, instruction.radius?, instruction.radius?)
        }
        Primitive::Ellipse => {
            let size = instruction.size?;
            ellipse_bounds(center()?, size.x / 2.0, size.y / 2.0)
        }
        Primitive::Polygon => point_bounds(
            polygon_points(
                center()?,
                instruction.radius?,
                usize::from(instruction.sides.unwrap_or(5)),
                0.0,
            )
            .into_iter()
            .map(|p| transform.apply(p)),
        ),
        Primitive::Square | Primitive::Triangle => {
            let position = point_to_short_side_units(instruction.position?, canvas);
            let size = instruction.size?;
            let mut points = vec![
                Point::new(position.x, position.y + size.y),
                Point::new(position.x + size.x, position.y + size.y),
            ];
            if instruction.primitive == Primitive::Triangle {
                points.push(Point::new(position.x + size.x / 2.0, position.y));
            } else {
                points.extend([position, Point::new(position.x + size.x, position.y)]);
            }
            point_bounds(points.into_iter().map(|p| transform.apply(p)))
        }
        Primitive::Arc if instruction.arc_form == Some(ArcForm::Crescent) => {
            let center = center()?;
            let size = instruction.size?;
            point_bounds(CRESCENT_REFERENCE_CUBICS.into_iter().flat_map(|cubic| {
                cubic_extrema(
                    cubic.map(|p| transform.apply(crescent_transform_point(p, center, size, 0.0))),
                )
            }))
        }
        Primitive::Arc => {
            let center = center()?;
            let radius = instruction.radius?;
            let start = instruction.angle_start?;
            let end = instruction.angle_end?;
            let mut angles = vec![start, end];
            // For x=A*cos(t)-C*sin(t), extrema occur at atan2(-C,A) modulo pi.
            for angle in [
                (-transform.c).atan2(transform.a).to_degrees(),
                (-transform.d).atan2(transform.b).to_degrees(),
            ] {
                let lower = start.min(end);
                let upper = start.max(end);
                // At most two distinct extrema per axis, even for multiple turns.
                for candidate in [angle, angle + 180.0] {
                    let turn = ((lower - candidate) / 360.0).ceil();
                    let value = candidate + 360.0 * turn;
                    if value <= upper {
                        angles.push(value);
                    }
                }
            }
            point_bounds(
                angles
                    .into_iter()
                    .map(|angle| transform.apply(crate::arc::arc_point(center, radius, angle))),
            )
        }
        Primitive::Cloudform => {
            let contour = generate_cloudform_contour(CloudformRequest {
                center: center()?,
                size: instruction.size?,
                performance_seed: Some(
                    seed_override
                        .unwrap_or_else(|| crate::determinism::instruction_seed(instruction, seed)),
                ),
                instruction_index: index,
                mark_index: 0,
                variation: instruction.variation.as_ref(),
                weight: instruction.weight,
                point_count: 49,
            });
            point_bounds(contour.into_iter().map(|p| transform.apply(p)))
        }
    }
}
