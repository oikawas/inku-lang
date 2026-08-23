//! Pure contour and scan geometry used by surface painting.

use crate::cloudform::{CloudformRequest, generate_cloudform_contour, sample_closed_catmull_rom};
use crate::determinism::{hash01, instruction_seed};
use crate::geometry::{
    circle_points, ellipse_perimeter, point_to_pixels, polygon_points, size_to_pixels,
    stroke_sample_count,
};
use crate::marks::MarkContext;
use crate::types::{Instruction, Point, Primitive, Seed};

pub(crate) fn shape_bbox(
    instruction: &Instruction,
    context: MarkContext<'_>,
) -> Option<(f64, f64, f64, f64)> {
    let canvas = context.canvas;
    match instruction.primitive {
        Primitive::Circle => {
            let center = point_to_pixels(instruction.center?, canvas);
            let radius = instruction.radius? * canvas.unit();
            Some((
                center.x - radius,
                center.y - radius,
                radius * 2.0,
                radius * 2.0,
            ))
        }
        Primitive::Ellipse => {
            let center = point_to_pixels(instruction.center?, canvas);
            let size = size_to_pixels(instruction.size?, canvas);
            Some((
                center.x - size.x / 2.0,
                center.y - size.y / 2.0,
                size.x,
                size.y,
            ))
        }
        Primitive::Cloudform => {
            let center = point_to_pixels(instruction.center?, canvas);
            let size = size_to_pixels(instruction.size?, canvas);
            Some((
                center.x - size.x * 0.56,
                center.y - size.y * 0.56,
                size.x * 1.12,
                size.y * 1.12,
            ))
        }
        Primitive::Square | Primitive::Triangle => {
            let position = point_to_pixels(instruction.position?, canvas);
            let size = size_to_pixels(instruction.size?, canvas);
            Some((position.x, position.y, size.x, size.y))
        }
        Primitive::Polygon => {
            let center = point_to_pixels(instruction.center?, canvas);
            let radius = instruction.radius? * canvas.unit();
            Some((
                center.x - radius,
                center.y - radius,
                radius * 2.0,
                radius * 2.0,
            ))
        }
        Primitive::Line | Primitive::Arc => None,
    }
}

pub(crate) fn surface_contour(
    instruction: &Instruction,
    context: MarkContext<'_>,
) -> Option<Vec<Point>> {
    let canvas = context.canvas;
    match instruction.primitive {
        Primitive::Circle => {
            let center = point_to_pixels(instruction.center?, canvas);
            let radius = instruction.radius? * canvas.unit();
            Some(circle_points(
                center,
                radius,
                radius,
                stroke_sample_count(std::f64::consts::TAU * radius, canvas),
            ))
        }
        Primitive::Ellipse => {
            let center = point_to_pixels(instruction.center?, canvas);
            let size = size_to_pixels(instruction.size?, canvas);
            let rx = size.x / 2.0;
            let ry = size.y / 2.0;
            Some(circle_points(
                center,
                rx,
                ry,
                stroke_sample_count(ellipse_perimeter(rx, ry), canvas),
            ))
        }
        Primitive::Square | Primitive::Triangle => {
            let position = point_to_pixels(instruction.position?, canvas);
            let size = size_to_pixels(instruction.size?, canvas);
            if instruction.primitive == Primitive::Square {
                Some(vec![
                    position,
                    Point::new(position.x + size.x, position.y),
                    Point::new(position.x + size.x, position.y + size.y),
                    Point::new(position.x, position.y + size.y),
                ])
            } else {
                Some(vec![
                    Point::new(position.x + size.x / 2.0, position.y),
                    Point::new(position.x + size.x, position.y + size.y),
                    Point::new(position.x, position.y + size.y),
                ])
            }
        }
        Primitive::Polygon => {
            let center = point_to_pixels(instruction.center?, canvas);
            Some(polygon_points(
                center,
                instruction.radius? * canvas.unit(),
                usize::from(instruction.sides.unwrap_or(5)),
                0.0,
            ))
        }
        Primitive::Cloudform => {
            let controls = generate_cloudform_contour(CloudformRequest {
                center: point_to_pixels(instruction.center?, canvas),
                size: size_to_pixels(instruction.size?, canvas),
                performance_seed: Some(instruction_seed(instruction, context.render_seed)),
                instruction_index: context.instruction_index,
                mark_index: context.mark_index,
                variation: instruction.variation.as_ref(),
                weight: instruction.weight,
                point_count: 49,
            });
            Some(sample_closed_catmull_rom(&controls, 5))
        }
        Primitive::Line | Primitive::Arc => None,
    }
}

pub(crate) fn point_in_polygon(point: Point, contour: &[Point]) -> bool {
    let mut inside = false;
    for index in 0..contour.len() {
        let a = contour[index];
        let b = contour[(index + 1) % contour.len()];
        if (a.y > point.y) != (b.y > point.y) {
            let t = (point.y - a.y) / (b.y - a.y);
            if point.x < a.x + (b.x - a.x) * t {
                inside = !inside;
            }
        }
    }
    inside
}

pub(crate) fn scanline_segments(
    contour: &[Point],
    angle: f64,
    spacing: f64,
    seed: Seed,
) -> Vec<(usize, Point, Point)> {
    let direction = Point::new(angle.cos(), angle.sin());
    let normal = Point::new(-direction.y, direction.x);
    let projections = contour
        .iter()
        .map(|point| point.x * normal.x + point.y * normal.y)
        .collect::<Vec<_>>();
    let low = projections.iter().copied().fold(f64::INFINITY, f64::min);
    let high = projections
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);
    let mut offset = low + spacing * 0.5;
    let mut index = 0_usize;
    let mut result = Vec::new();
    while offset < high && index < 4096 {
        let mut hits = Vec::new();
        for edge in 0..contour.len() {
            let a = contour[edge];
            let b = contour[(edge + 1) % contour.len()];
            let da = a.x * normal.x + a.y * normal.y - offset;
            let db = b.x * normal.x + b.y * normal.y - offset;
            if (da <= 0.0 && db > 0.0) || (db <= 0.0 && da > 0.0) {
                let t = da / (da - db);
                let point = Point::new(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t);
                hits.push(point.x * direction.x + point.y * direction.y);
            }
        }
        hits.sort_by(f64::total_cmp);
        for pair in (0..hits.len().saturating_sub(1)).step_by(2) {
            let start = Point::new(
                normal.x * offset + direction.x * hits[pair],
                normal.y * offset + direction.y * hits[pair],
            );
            let end = Point::new(
                normal.x * offset + direction.x * hits[pair + 1],
                normal.y * offset + direction.y * hits[pair + 1],
            );
            result.push((index, start, end));
        }
        let step = 1.0 + (hash01(index as i64, seed, "fill-spacing") - 0.5) * 0.24;
        offset += spacing * step;
        index += 1;
    }
    result
}

pub(crate) fn line_spans(contour: &[Point], point: Point, direction: Point) -> Vec<(f64, f64)> {
    let mut hits = Vec::new();
    for edge in 0..contour.len() {
        let a = contour[edge];
        let b = contour[(edge + 1) % contour.len()];
        let edge_vector = Point::new(b.x - a.x, b.y - a.y);
        let denominator = direction.x * edge_vector.y - direction.y * edge_vector.x;
        if denominator.abs() < 1.0e-12 {
            continue;
        }
        let delta = Point::new(a.x - point.x, a.y - point.y);
        let edge_t = (delta.x * direction.y - delta.y * direction.x) / denominator;
        if !(0.0..1.0).contains(&edge_t) {
            continue;
        }
        hits.push(
            (delta.x + edge_vector.x * edge_t) * direction.x
                + (delta.y + edge_vector.y * edge_t) * direction.y,
        );
    }
    hits.sort_by(f64::total_cmp);
    (0..hits.len().saturating_sub(1))
        .step_by(2)
        .map(|index| (hits[index], hits[index + 1]))
        .collect()
}

pub(crate) fn scatter(contour: &[Point], count: usize, seed: Seed) -> Vec<Point> {
    if count == 0 || contour.len() < 3 {
        return Vec::new();
    }
    let angle = hash01(0, seed, "fill-angle") * std::f64::consts::PI;
    let min_x = contour
        .iter()
        .map(|point| point.x)
        .fold(f64::INFINITY, f64::min);
    let max_x = contour
        .iter()
        .map(|point| point.x)
        .fold(f64::NEG_INFINITY, f64::max);
    let min_y = contour
        .iter()
        .map(|point| point.y)
        .fold(f64::INFINITY, f64::min);
    let max_y = contour
        .iter()
        .map(|point| point.y)
        .fold(f64::NEG_INFINITY, f64::max);
    let diagonal = (max_x - min_x).hypot(max_y - min_y).max(1.0e-6);
    let rows = ((count as f64 * 1.6).sqrt().round_ties_even() as usize).max(2);
    let spacing = diagonal / rows as f64;
    let segments = scanline_segments(contour, angle, spacing, seed);
    let lengths = segments
        .iter()
        .map(|(_, start, end)| (end.x - start.x).hypot(end.y - start.y))
        .collect::<Vec<_>>();
    let total = lengths.iter().sum::<f64>();
    if total <= 0.0 {
        return Vec::new();
    }
    let normal = Point::new(-angle.sin(), angle.cos());
    let mut points = Vec::new();
    for (segment_index, ((_, start, end), length)) in segments.iter().zip(lengths).enumerate() {
        let share = count as f64 * length / total;
        let mut taken = share.floor() as usize;
        if hash01(segment_index as i64, seed, "surface-share") < share - taken as f64 {
            taken += 1;
        }
        for point_index in 0..taken {
            let salt_index = segment_index * 4096 + point_index;
            let u =
                (point_index as f64 + hash01(salt_index as i64, seed, "surface-u")) / taken as f64;
            let point = Point::new(
                start.x + (end.x - start.x) * u,
                start.y + (end.y - start.y) * u,
            );
            let drift = (hash01(salt_index as i64, seed, "surface-n") - 0.5) * spacing * 0.8;
            let shifted = Point::new(point.x + normal.x * drift, point.y + normal.y * drift);
            points.push(if point_in_polygon(shifted, contour) {
                shifted
            } else {
                point
            });
        }
    }
    points
}
