//! Pure point and scalar geometry used by the render core.

use std::collections::BTreeSet;

use crate::determinism::{hash_to_unit, periodic_value_noise_1d, value_noise_1d, wave_phase};
use crate::types::{
    CRESCENT_REFERENCE_CUBICS, CanvasSize, Dimension, Frequency, Point, Quality, Seed, Variation,
    crescent_transform_point,
};

pub const SEGMENT_TARGET_RATIO: f64 = 0.01;
pub const SEGMENT_COUNT_MIN: usize = 32;
pub const SEGMENT_COUNT_MAX: usize = 200;
pub const STROKE_SAMPLE_TARGET_RATIO: f64 = 1.0 / 49.0;
pub const STROKE_SAMPLE_MIN: usize = 17;
pub const STROKE_SAMPLE_MAX: usize = 129;

pub(crate) fn frequency_cycles(frequency: Frequency) -> f64 {
    match frequency {
        Frequency::Slow => 2.0,
        Frequency::Medium => 6.0,
        Frequency::High => 14.0,
    }
}

fn distance(a: Point, b: Point) -> f64 {
    (b.x - a.x).hypot(b.y - a.y)
}

/// Ramanujan's second approximation of an ellipse perimeter.
#[must_use]
pub fn ellipse_perimeter(rx: f64, ry: f64) -> f64 {
    let (a, b) = (rx.abs(), ry.abs());
    if a + b <= 0.0 {
        return 0.0;
    }
    let h = ((a - b) / (a + b)).powi(2);
    std::f64::consts::PI * (a + b) * (1.0 + 3.0 * h / (10.0 + (4.0 - 3.0 * h).sqrt()))
}

/// Segment count with Python-compatible ties-to-even rounding.
#[must_use]
pub fn segment_count(path_length_px: f64, canvas: CanvasSize) -> usize {
    let target = canvas.unit() * SEGMENT_TARGET_RATIO;
    if target <= 0.0 {
        return SEGMENT_COUNT_MIN;
    }
    (path_length_px / target)
        .round_ties_even()
        .clamp(SEGMENT_COUNT_MIN as f64, SEGMENT_COUNT_MAX as f64) as usize
}

/// Hand-stroke sample count with Python-compatible ties-to-even rounding.
#[must_use]
pub fn stroke_sample_count(length_px: f64, canvas: CanvasSize) -> usize {
    let target = canvas.unit() * STROKE_SAMPLE_TARGET_RATIO;
    if target <= 0.0 {
        return STROKE_SAMPLE_MIN;
    }
    (length_px / target)
        .round_ties_even()
        .clamp(STROKE_SAMPLE_MIN as f64, STROKE_SAMPLE_MAX as f64) as usize
}

#[must_use]
pub fn sample_offset(
    t: f64,
    variation: &Variation,
    seed: Seed,
    segment: usize,
    amplitude: f64,
) -> f64 {
    let frequency = frequency_cycles(variation.frequency);
    match variation.quality {
        Quality::Wave => {
            (t * std::f64::consts::TAU * frequency + wave_phase(seed)).sin() * amplitude
        }
        Quality::Perlin => value_noise_1d(t * frequency, seed) * amplitude,
        Quality::Pink => {
            (value_noise_1d(t * frequency, seed) * amplitude
                + value_noise_1d(t * frequency * 2.0, seed ^ 0x9E37) * amplitude * 0.5)
                / 1.5
        }
        Quality::White => hash_to_unit(segment as i64, seed) * amplitude,
        Quality::None => 0.0,
    }
}

/// The share of an open stroke, at each end, over which its variation settles:
/// the 0.16 over which a hand stroke tapers (`stroke.rs`), or half a wave when
/// the wave is shorter.
fn settle_span(variation: &Variation) -> f64 {
    (0.5 / frequency_cycles(variation.frequency)).min(0.16)
}

/// Raised-cosine weight: 0 at both ends, 1 from `span` inwards.
fn settle(t: f64, span: f64) -> f64 {
    let edge = t.min(1.0 - t);
    if edge >= span {
        1.0
    } else {
        0.5 * (1.0 - (std::f64::consts::PI * edge / span).cos())
    }
}

/// A polygon edge's varied centerline. The variation keeps its full size up to
/// the corners, which the contour stroke anchors and continues through.
#[must_use]
pub fn line_with_variation(
    start: Point,
    end: Point,
    variation: &Variation,
    seed: Seed,
    amplitude: f64,
    canvas: CanvasSize,
) -> Vec<Point> {
    varied_line(start, end, variation, seed, amplitude, canvas, None)
}

/// An open line's varied centerline. Its ends stay where the Score put them,
/// and the variation settles to nothing towards both: the seeded wave phase
/// and the noise are rarely zero at the ends, and a pinned end otherwise made
/// the first and last segment jump sideways, a thin straight whisker on a
/// tapered brush (render engine 76).
#[must_use]
pub fn open_line_with_variation(
    start: Point,
    end: Point,
    variation: &Variation,
    seed: Seed,
    amplitude: f64,
    canvas: CanvasSize,
) -> Vec<Point> {
    let span = settle_span(variation);
    varied_line(start, end, variation, seed, amplitude, canvas, Some(span))
}

fn varied_line(
    start: Point,
    end: Point,
    variation: &Variation,
    seed: Seed,
    amplitude: f64,
    canvas: CanvasSize,
    settle_within: Option<f64>,
) -> Vec<Point> {
    let dx = end.x - start.x;
    let dy = end.y - start.y;
    let length = dx.hypot(dy);
    if length < 1.0e-6 {
        return vec![start, end];
    }
    let perpendicular = Point::new(-dy / length, dx / length);
    let axis_x = variation.dimensions.contains(&Dimension::PositionX);
    let axis_y = variation.dimensions.contains(&Dimension::PositionY);
    let segments = segment_count(length, canvas);
    let mut points = Vec::with_capacity(segments + 1);
    points.push(start);
    for index in 1..segments {
        let t = index as f64 / segments as f64;
        let mut point = Point::new(start.x + t * dx, start.y + t * dy);
        let mut offset = sample_offset(t, variation, seed, index, amplitude);
        if let Some(span) = settle_within {
            offset *= settle(t, span);
        }
        if axis_x && !axis_y {
            point.x += offset;
        } else if axis_y && !axis_x {
            point.y += offset;
        } else {
            point.x += offset * perpendicular.x;
            point.y += offset * perpendicular.y;
        }
        points.push(point);
    }
    points.push(end);
    points
}

#[must_use]
pub fn sample_offset_periodic(
    t: f64,
    variation: &Variation,
    seed: Seed,
    segment: usize,
    amplitude: f64,
) -> f64 {
    let frequency = frequency_cycles(variation.frequency);
    match variation.quality {
        Quality::Wave => {
            (t * std::f64::consts::TAU * frequency + wave_phase(seed)).sin() * amplitude
        }
        Quality::Perlin => {
            let period = frequency.round_ties_even().max(1.0) as i64;
            periodic_value_noise_1d(t * frequency, seed, period) * amplitude
        }
        Quality::White => hash_to_unit(segment as i64, seed) * amplitude,
        Quality::None | Quality::Pink => 0.0,
    }
}

#[must_use]
pub fn offset_contour_point(
    point: Point,
    offset: f64,
    center: Point,
    axis_x: bool,
    axis_y: bool,
) -> Point {
    if axis_x && !axis_y {
        return Point::new(point.x + offset, point.y);
    }
    if axis_y && !axis_x {
        return Point::new(point.x, point.y + offset);
    }
    let dx = point.x - center.x;
    let dy = point.y - center.y;
    let norm = dx.hypot(dy);
    if norm <= 1.0e-6 {
        return point;
    }
    Point::new(point.x + offset * dx / norm, point.y + offset * dy / norm)
}

#[must_use]
pub fn closed_contour_with_variation(
    points: &[Point],
    center: Point,
    variation: &Variation,
    seed: Seed,
    amplitude: f64,
) -> Vec<Point> {
    let axis_x = variation.dimensions.contains(&Dimension::PositionX);
    let axis_y = variation.dimensions.contains(&Dimension::PositionY);
    let count = points.len();
    points
        .iter()
        .enumerate()
        .map(|(index, point)| {
            let offset = sample_offset_periodic(
                index as f64 / count as f64,
                variation,
                seed,
                index,
                amplitude,
            );
            offset_contour_point(*point, offset, center, axis_x, axis_y)
        })
        .collect()
}

#[derive(Clone, Debug, PartialEq)]
pub struct AnchoredContour {
    pub points: Vec<Point>,
    pub anchors: BTreeSet<usize>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ArcGeometry {
    pub center: Point,
    pub radius: f64,
    pub start_degrees: f64,
    pub end_degrees: f64,
}

#[must_use]
pub fn edge_contour_with_anchors(
    corners: &[Point],
    variation: Option<&Variation>,
    seed: Seed,
    amplitude: f64,
    canvas: CanvasSize,
) -> AnchoredContour {
    let mut points = Vec::new();
    let mut anchors = BTreeSet::new();
    for index in 0..corners.len() {
        let start = corners[index];
        let end = corners[(index + 1) % corners.len()];
        anchors.insert(points.len());
        let edge = if let Some(variation) = variation {
            line_with_variation(
                start,
                end,
                variation,
                seed + (index as Seed + 1) * 7_919,
                amplitude,
                canvas,
            )
        } else {
            let segments = stroke_sample_count(distance(start, end), canvas);
            (0..=segments)
                .map(|step| {
                    let t = step as f64 / segments as f64;
                    Point::new(
                        start.x + (end.x - start.x) * t,
                        start.y + (end.y - start.y) * t,
                    )
                })
                .collect()
        };
        points.extend_from_slice(&edge[..edge.len().saturating_sub(1)]);
    }
    AnchoredContour { points, anchors }
}

/// An arc's varied centerline. Both ends stay on the arc for the touching
/// contract, and, as on an open line, the variation settles towards them.
#[must_use]
pub fn arc_points_with_variation(
    arc: ArcGeometry,
    variation: &Variation,
    seed: Seed,
    amplitude: f64,
    canvas: CanvasSize,
) -> Vec<Point> {
    let arc_length =
        arc.radius * (arc.end_degrees.to_radians() - arc.start_degrees.to_radians()).abs();
    let base = arc_points(
        arc.center,
        arc.radius,
        arc.start_degrees,
        arc.end_degrees,
        segment_count(arc_length, canvas) + 1,
    );
    let axis_x = variation.dimensions.contains(&Dimension::PositionX);
    let axis_y = variation.dimensions.contains(&Dimension::PositionY);
    let last = base.len() - 1;
    let span = settle_span(variation);
    let mut result = Vec::with_capacity(base.len());
    result.push(base[0]);
    for (index, point) in base.iter().copied().enumerate().take(last).skip(1) {
        let t = index as f64 / last as f64;
        let offset = sample_offset(t, variation, seed, index, amplitude) * settle(t, span);
        result.push(offset_contour_point(
            point, offset, arc.center, axis_x, axis_y,
        ));
    }
    result.push(base[last]);
    result
}

#[must_use]
pub fn line_direction(start: Point, end: Point) -> Point {
    let dx = end.x - start.x;
    let dy = end.y - start.y;
    let length = dx.hypot(dy);
    if length < 1.0e-6 {
        Point::new(1.0, 0.0)
    } else {
        Point::new(dx / length, dy / length)
    }
}

#[must_use]
pub fn offset_polyline(
    points: &[Point],
    amount: f64,
    wander: f64,
    wander_period: f64,
    seed: Seed,
) -> Vec<Point> {
    if points.len() < 2 {
        return points.to_vec();
    }
    let mut result = Vec::with_capacity(points.len());
    let mut arc = 0.0;
    for index in 0..points.len() {
        let tangent = if index == 0 {
            Point::new(points[1].x - points[0].x, points[1].y - points[0].y)
        } else if index == points.len() - 1 {
            Point::new(
                points[index].x - points[index - 1].x,
                points[index].y - points[index - 1].y,
            )
        } else {
            Point::new(
                points[index + 1].x - points[index - 1].x,
                points[index + 1].y - points[index - 1].y,
            )
        };
        let length = tangent.x.hypot(tangent.y);
        let length = if length == 0.0 { 1.0 } else { length };
        let normal = Point::new(-tangent.y / length, tangent.x / length);
        let offset = amount
            + if wander == 0.0 {
                0.0
            } else {
                wander * (value_noise_1d(arc / wander_period.max(1.0e-6), seed) * 2.0 - 1.0)
            };
        result.push(Point::new(
            points[index].x + normal.x * offset,
            points[index].y + normal.y * offset,
        ));
        if index + 1 < points.len() {
            arc += distance(points[index], points[index + 1]);
        }
    }
    result
}

#[must_use]
pub fn polyline_sample(points: &[Point], t: f64) -> (Point, Point) {
    if points.len() < 2 {
        return (
            points.first().copied().unwrap_or(Point::new(0.0, 0.0)),
            Point::new(1.0, 0.0),
        );
    }
    let lengths: Vec<f64> = points
        .windows(2)
        .map(|pair| distance(pair[0], pair[1]))
        .collect();
    let total: f64 = lengths.iter().sum();
    if total < 1.0e-9 {
        return (points[0], Point::new(1.0, 0.0));
    }
    let target = t * total;
    let mut accumulated = 0.0;
    for (index, length) in lengths.iter().copied().enumerate() {
        if accumulated + length >= target || index == lengths.len() - 1 {
            let fraction = if length > 1.0e-9 {
                (target - accumulated) / length
            } else {
                0.0
            };
            let start = points[index];
            let end = points[index + 1];
            let divisor = if length > 0.0 { length } else { 1.0 };
            return (
                Point::new(
                    start.x + (end.x - start.x) * fraction,
                    start.y + (end.y - start.y) * fraction,
                ),
                Point::new((end.x - start.x) / divisor, (end.y - start.y) / divisor),
            );
        }
        accumulated += length;
    }
    (
        *points.last().expect("nonempty polyline"),
        Point::new(1.0, 0.0),
    )
}

#[must_use]
pub fn circle_points(center: Point, rx: f64, ry: f64, count: usize) -> Vec<Point> {
    (0..count)
        .map(|index| {
            let angle = index as f64 * std::f64::consts::TAU / count as f64;
            Point::new(center.x + angle.cos() * rx, center.y + angle.sin() * ry)
        })
        .collect()
}

/// Sample the fixed Saijiki crescent after scaling it to its physical bounding box.
#[must_use]
pub fn crescent_contour_points(center: Point, size: Point, samples_per_cubic: usize) -> Vec<Point> {
    let samples = samples_per_cubic.max(2);
    let mut points = Vec::with_capacity(CRESCENT_REFERENCE_CUBICS.len() * samples);
    for (segment_index, cubic) in CRESCENT_REFERENCE_CUBICS.iter().enumerate() {
        for sample in 0..samples {
            if segment_index > 0 && sample == 0 {
                continue;
            }
            let t = sample as f64 / (samples - 1) as f64;
            let inverse = 1.0 - t;
            let reference = Point::new(
                inverse.powi(3) * cubic[0].x
                    + 3.0 * inverse.powi(2) * t * cubic[1].x
                    + 3.0 * inverse * t.powi(2) * cubic[2].x
                    + t.powi(3) * cubic[3].x,
                inverse.powi(3) * cubic[0].y
                    + 3.0 * inverse.powi(2) * t * cubic[1].y
                    + 3.0 * inverse * t.powi(2) * cubic[2].y
                    + t.powi(3) * cubic[3].y,
            );
            points.push(crescent_transform_point(reference, center, size, 0.0));
        }
    }
    points
}

#[must_use]
pub fn rect_points(origin: Point, width: f64, height: f64, count: usize) -> Vec<Point> {
    let perimeter = (2.0 * (width + height)).max(1.0);
    (0..count)
        .map(|index| {
            let distance = (index as f64 + 0.5) / count as f64 * perimeter;
            if distance <= width {
                Point::new(origin.x + distance, origin.y)
            } else if distance <= width + height {
                Point::new(origin.x + width, origin.y + distance - width)
            } else if distance <= 2.0 * width + height {
                Point::new(
                    origin.x + width - (distance - width - height),
                    origin.y + height,
                )
            } else {
                Point::new(
                    origin.x,
                    origin.y + height - (distance - 2.0 * width - height),
                )
            }
        })
        .collect()
}

#[must_use]
pub fn arc_points(
    center: Point,
    radius: f64,
    start_degrees: f64,
    end_degrees: f64,
    count: usize,
) -> Vec<Point> {
    let count = count.max(2);
    let start = start_degrees.to_radians();
    let end = end_degrees.to_radians();
    (0..count)
        .map(|index| {
            let angle = start + (end - start) * index as f64 / (count - 1) as f64;
            Point::new(
                center.x + angle.cos() * radius,
                center.y - angle.sin() * radius,
            )
        })
        .collect()
}

#[must_use]
pub fn polygon_points(
    center: Point,
    radius: f64,
    sides: usize,
    rotation_degrees: f64,
) -> Vec<Point> {
    let sides = sides.clamp(5, 8);
    let start = (rotation_degrees - 90.0).to_radians();
    (0..sides)
        .map(|index| {
            let angle = start + std::f64::consts::TAU * index as f64 / sides as f64;
            Point::new(
                center.x + angle.cos() * radius,
                center.y + angle.sin() * radius,
            )
        })
        .collect()
}

#[must_use]
pub fn resample_points(path: &[Point], count: usize) -> Vec<Point> {
    if count == 0 || path.is_empty() {
        return Vec::new();
    }
    (0..count)
        .map(|index| path[(index * path.len() / count).min(path.len() - 1)])
        .collect()
}

#[must_use]
pub fn centerline_normals(points: &[Point], closed: bool) -> Vec<Point> {
    if points.is_empty() {
        return Vec::new();
    }
    let last = points.len() - 1;
    (0..points.len())
        .map(|index| {
            let before = if closed {
                points[(index + last) % points.len()]
            } else {
                points[index.saturating_sub(1)]
            };
            let after = if closed {
                points[(index + 1) % points.len()]
            } else {
                points[(index + 1).min(last)]
            };
            let dx = after.x - before.x;
            let dy = after.y - before.y;
            let length = dx.hypot(dy).max(1.0e-6);
            Point::new(-dy / length, dx / length)
        })
        .collect()
}

#[must_use]
pub fn offset_performed_path(
    path: &[Point],
    amount: f64,
    closed: bool,
    center: Point,
    wander: f64,
    wander_period: f64,
    seed: Seed,
) -> Vec<Point> {
    let normals = centerline_normals(path, closed);
    let votes: i64 = path
        .iter()
        .zip(&normals)
        .map(|(point, normal)| {
            if normal.x * (point.x - center.x) + normal.y * (point.y - center.y) >= 0.0 {
                1
            } else {
                -1
            }
        })
        .sum();
    let sign = if votes >= 0 { 1.0 } else { -1.0 };
    let mut arc = 0.0;
    let mut result = Vec::with_capacity(path.len());
    for (index, (point, normal)) in path.iter().zip(normals).enumerate() {
        let offset = amount
            + if wander == 0.0 {
                0.0
            } else {
                wander * (value_noise_1d(arc / wander_period.max(1.0e-6), seed) * 2.0 - 1.0)
            };
        result.push(Point::new(
            point.x + normal.x * offset * sign,
            point.y + normal.y * offset * sign,
        ));
        if index + 1 < path.len() {
            arc += distance(*point, path[index + 1]);
        }
    }
    result
}

#[must_use]
pub fn closed_path_length(path: &[Point]) -> f64 {
    if path.len() < 2 {
        return 0.0;
    }
    path.iter()
        .copied()
        .zip(path.iter().copied().cycle().skip(1))
        .take(path.len())
        .map(|(a, b)| distance(a, b))
        .sum()
}

#[must_use]
pub fn points_center(path: &[Point]) -> Point {
    if path.is_empty() {
        return Point::new(0.0, 0.0);
    }
    Point::new(
        path.iter().map(|point| point.x).sum::<f64>() / path.len() as f64,
        path.iter().map(|point| point.y).sum::<f64>() / path.len() as f64,
    )
}

/// Per-axis factors that express a short-side distance in normalized canvas axes.
#[must_use]
pub fn short_side_scales(canvas: Option<CanvasSize>) -> Point {
    canvas.map_or(Point::new(1.0, 1.0), |canvas| {
        Point::new(canvas.unit() / canvas.width, canvas.unit() / canvas.height)
    })
}

/// Convert an axes-normalized point into coordinates measured on the canvas short side.
#[must_use]
pub fn point_to_short_side_units(point: Point, canvas: Option<CanvasSize>) -> Point {
    let scale = short_side_scales(canvas);
    Point::new(point.x / scale.x, point.y / scale.y)
}

/// Convert a point measured on the canvas short side into normalized canvas axes.
#[must_use]
pub fn point_from_short_side_units(point: Point, canvas: Option<CanvasSize>) -> Point {
    let scale = short_side_scales(canvas);
    Point::new(point.x * scale.x, point.y * scale.y)
}

/// Express a short-side-sized vector in normalized canvas axes.
#[must_use]
pub fn size_in_normalized_axes(size: Point, canvas: Option<CanvasSize>) -> Point {
    point_from_short_side_units(size, canvas)
}

#[must_use]
pub fn point_to_pixels(point: Point, canvas: CanvasSize) -> Point {
    Point::new(point.x * canvas.width, point.y * canvas.height)
}

#[must_use]
pub fn size_to_pixels(size: Point, canvas: CanvasSize) -> Point {
    Point::new(size.x * canvas.unit(), size.y * canvas.unit())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn variation(json: &str) -> Variation {
        serde_json::from_str(json).expect("a variation")
    }

    const BROAD_SLOW_WAVE: &str = r#"{"amplitude":"broad","frequency":"slow","quality":"wave",
        "dimensions":["position_x","position_y"]}"#;

    #[test]
    fn the_settling_share_is_the_tapered_end_or_half_a_wave() {
        for (frequency, span) in [("slow", 0.16), ("medium", 0.5 / 6.0), ("high", 0.5 / 14.0)] {
            let json = format!(
                r#"{{"amplitude":"broad","frequency":"{frequency}","quality":"wave",
                    "dimensions":["position_x","position_y"]}}"#
            );
            assert_eq!(settle_span(&variation(&json)), span, "{frequency}");
        }
    }

    #[test]
    fn an_open_line_keeps_its_ends_and_settles_its_variation_towards_them() {
        let canvas = CanvasSize::new(1000.0, 1000.0);
        let (start, end) = (Point::new(100.0, 500.0), Point::new(766.7, 500.0));
        let amplitude = 48.0;
        let variation = variation(BROAD_SLOW_WAVE);
        let span = settle_span(&variation);
        for seed in [7, 431, 4_434_821_668_328_665] {
            let edge = line_with_variation(start, end, &variation, seed, amplitude, canvas);
            let open = open_line_with_variation(start, end, &variation, seed, amplitude, canvas);
            assert_eq!(open.len(), edge.len());
            assert_eq!((open[0], open[open.len() - 1]), (start, end));
            // The chord is horizontal, so a point's variation is its height off it.
            let last = open.len() - 1;
            for neighbour in [open[1], open[last - 1]] {
                assert!(
                    (neighbour.y - start.y).abs() <= 0.03 * amplitude,
                    "{seed}: {neighbour:?}"
                );
            }
            for (index, (open, edge)) in open.iter().zip(&edge).enumerate() {
                let t = index as f64 / last as f64;
                if (span..=1.0 - span).contains(&t) {
                    assert_eq!(open, edge, "{seed}: the middle keeps the full variation");
                }
            }
        }
    }

    #[test]
    fn an_arc_keeps_its_ends_and_settles_its_variation_towards_them() {
        let canvas = CanvasSize::new(1000.0, 1000.0);
        let arc = ArcGeometry {
            center: Point::new(500.0, 500.0),
            radius: 300.0,
            start_degrees: 0.0,
            end_degrees: 180.0,
        };
        let amplitude = 48.0;
        let variation = variation(BROAD_SLOW_WAVE);
        let span = settle_span(&variation);
        let length = arc.radius * std::f64::consts::PI;
        let base = arc_points(
            arc.center,
            arc.radius,
            arc.start_degrees,
            arc.end_degrees,
            segment_count(length, canvas) + 1,
        );
        let last = base.len() - 1;
        for seed in [7, 431, 4_434_821_668_328_665] {
            let points = arc_points_with_variation(arc, &variation, seed, amplitude, canvas);
            assert_eq!((points[0], points[last]), (base[0], base[last]));
            for neighbour in [points[1], points[last - 1]] {
                let off_the_arc = (distance(neighbour, arc.center) - arc.radius).abs();
                assert!(off_the_arc <= 0.03 * amplitude, "{seed}: {off_the_arc}");
            }
            for index in 1..last {
                let t = index as f64 / last as f64;
                if (span..=1.0 - span).contains(&t) {
                    let offset = sample_offset(t, &variation, seed, index, amplitude);
                    let full = offset_contour_point(base[index], offset, arc.center, true, true);
                    assert_eq!(
                        points[index], full,
                        "{seed}: the middle keeps the full variation"
                    );
                }
            }
        }
    }
}
