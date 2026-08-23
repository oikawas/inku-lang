//! Deterministic, bounded cloudform contour synthesis.

use sha2::{Digest, Sha256};

use crate::stroke::{grammar, unit};
use crate::types::{Amplitude, Frequency, Point, Quality, Seed, Variation, Weight};

fn cloudform_seed(
    performance_seed: Option<Seed>,
    instruction_index: usize,
    mark_index: usize,
) -> Seed {
    let performance_seed =
        performance_seed.map_or_else(|| "None".to_owned(), |seed| seed.to_string());
    let digest = Sha256::digest(
        format!("cloudform-v1:{performance_seed}:{instruction_index}:{mark_index}").as_bytes(),
    );
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}

fn frequency_range(variation: Option<&Variation>) -> std::ops::Range<i32> {
    match variation.map_or(Frequency::Medium, |variation| variation.frequency) {
        Frequency::Slow => 2..6,
        Frequency::Medium => 3..8,
        Frequency::High => 5..11,
    }
}

fn variation_gain(variation: Option<&Variation>) -> f64 {
    match variation.map(|variation| variation.amplitude) {
        None => 0.16,
        Some(Amplitude::Fine) => 0.10,
        Some(Amplitude::Medium) => 0.17,
        Some(Amplitude::Broad) => 0.25,
    }
}

fn spectrum_power(variation: Option<&Variation>) -> f64 {
    match variation.map_or(Quality::Pink, |variation| variation.quality) {
        Quality::Wave => 1.15,
        Quality::Pink => 0.50,
        Quality::Perlin => 0.72,
        Quality::White => 0.0,
        Quality::None => 0.58,
    }
}

fn harmonic_signal(
    theta: f64,
    seed: Seed,
    label: &str,
    frequencies: impl Iterator<Item = i32>,
    power: f64,
) -> f64 {
    let mut total = 0.0;
    let mut normalizer = 0.0;
    for harmonic in frequencies {
        let amplitude = 1.0 / f64::from(harmonic).powf(power);
        let phase = std::f64::consts::TAU * unit(seed, &format!("{label}-phase"), harmonic.into());
        let sign = if unit(seed, &format!("{label}-sign"), harmonic.into()) < 0.5 {
            -1.0
        } else {
            1.0
        };
        total += sign * amplitude * (f64::from(harmonic) * theta + phase).cos();
        normalizer += amplitude;
    }
    total / normalizer.max(1.0e-9)
}

fn base_radius(theta: f64, seed: Seed, variation: Option<&Variation>, weight: Weight) -> f64 {
    let primary = harmonic_signal(
        theta,
        seed,
        "contour",
        frequency_range(variation),
        spectrum_power(variation),
    );
    let touch = harmonic_signal(theta, seed ^ 0x7001, "touch", 9..15, 0.65);
    (0.88 + variation_gain(variation) * primary + grammar(weight).energy_lateral * 0.018 * touch)
        .clamp(0.58, 1.12)
}

fn distance(first: Point, second: Point) -> f64 {
    (second.x - first.x).hypot(second.y - first.y)
}

fn curvature_radius(before: Point, point: Point, after: Point) -> f64 {
    let twice_area = ((point.x - before.x) * (after.y - before.y)
        - (point.y - before.y) * (after.x - before.x))
        .abs();
    if twice_area < 1.0e-9 {
        f64::INFINITY
    } else {
        distance(before, point) * distance(point, after) * distance(after, before)
            / (2.0 * twice_area)
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CloudformRequest<'a> {
    pub center: Point,
    pub size: Point,
    pub performance_seed: Option<Seed>,
    pub instruction_index: usize,
    pub mark_index: usize,
    pub variation: Option<&'a Variation>,
    pub weight: Weight,
    pub point_count: usize,
}

#[must_use]
pub fn generate_cloudform_contour(request: CloudformRequest<'_>) -> Vec<Point> {
    let point_count = request.point_count.clamp(24, 72);
    let seed = cloudform_seed(
        request.performance_seed,
        request.instruction_index,
        request.mark_index,
    );
    let radius_x = (request.size.x / 2.0).max(1.0e-6);
    let radius_y = (request.size.y / 2.0).max(1.0e-6);
    let angles: Vec<f64> = (0..point_count)
        .map(|index| std::f64::consts::TAU * index as f64 / point_count as f64)
        .collect();
    let base_points: Vec<Point> = angles
        .iter()
        .map(|theta| {
            let radius = base_radius(*theta, seed, request.variation, request.weight);
            Point::new(
                request.center.x + radius_x * radius * theta.cos(),
                request.center.y + radius_y * radius * theta.sin(),
            )
        })
        .collect();
    let lengths: Vec<f64> = (0..point_count)
        .map(|index| distance(base_points[index], base_points[(index + 1) % point_count]))
        .collect();
    let perimeter = lengths.iter().sum::<f64>().max(1.0e-9);
    let mut travelled = 0.0;
    let arc_positions: Vec<f64> = lengths
        .iter()
        .map(|length| {
            let position = travelled / perimeter;
            travelled += length;
            position
        })
        .collect();
    let gain = variation_gain(request.variation);
    let nominal_scale = radius_x.min(radius_y);
    (0..point_count)
        .map(|index| {
            let point = base_points[index];
            let before = base_points[(index + point_count - 1) % point_count];
            let after = base_points[(index + 1) % point_count];
            let tangent = Point::new(after.x - before.x, after.y - before.y);
            let tangent_length = tangent.x.hypot(tangent.y).max(1.0e-9);
            let mut normal = Point::new(-tangent.y / tangent_length, tangent.x / tangent_length);
            let toward_center = Point::new(request.center.x - point.x, request.center.y - point.y);
            if normal.x * toward_center.x + normal.y * toward_center.y < 0.0 {
                normal.x = -normal.x;
                normal.y = -normal.y;
            }
            let waist = harmonic_signal(
                std::f64::consts::TAU * arc_positions[index],
                seed ^ 0xC10D5EED,
                "waist",
                2..5,
                0.72,
            );
            let requested = (-waist).max(0.0).powi(2) * (0.08 + gain * 0.36) * nominal_scale;
            let nonlocal_separation = base_points
                .iter()
                .copied()
                .enumerate()
                .filter(|(other, _)| {
                    let forward = (*other + point_count - index) % point_count;
                    let backward = (index + point_count - *other) % point_count;
                    forward.min(backward) > 3
                })
                .map(|(_, other)| distance(point, other))
                .fold(f64::INFINITY, f64::min);
            let radial_clearance =
                (distance(point, request.center) - nominal_scale * 0.48).max(0.0);
            let maximum = (curvature_radius(before, point, after) * 0.20)
                .min(nonlocal_separation * 0.18)
                .min(radial_clearance * 0.50)
                .min(nominal_scale * (0.08 + gain * 0.36));
            let displacement = requested.min(maximum);
            Point::new(
                point.x + normal.x * displacement,
                point.y + normal.y * displacement,
            )
        })
        .collect()
}

/// Densely sample the closed Catmull-Rom curve used by the SVG cloudform path.
#[must_use]
pub fn sample_closed_catmull_rom(points: &[Point], samples_per_segment: usize) -> Vec<Point> {
    let count = points.len();
    if count < 3 {
        return points.to_vec();
    }
    let samples_per_segment = samples_per_segment.max(2);
    let mut sampled = Vec::with_capacity(count * samples_per_segment);
    for index in 0..count {
        let p0 = points[(index + count - 1) % count];
        let p1 = points[index];
        let p2 = points[(index + 1) % count];
        let p3 = points[(index + 2) % count];
        let c1 = Point::new(p1.x + (p2.x - p0.x) / 6.0, p1.y + (p2.y - p0.y) / 6.0);
        let c2 = Point::new(p2.x - (p3.x - p1.x) / 6.0, p2.y - (p3.y - p1.y) / 6.0);
        for step in 0..samples_per_segment {
            let t = step as f64 / samples_per_segment as f64;
            let inverse = 1.0 - t;
            sampled.push(Point::new(
                inverse.powi(3) * p1.x
                    + 3.0 * inverse.powi(2) * t * c1.x
                    + 3.0 * inverse * t.powi(2) * c2.x
                    + t.powi(3) * p2.x,
                inverse.powi(3) * p1.y
                    + 3.0 * inverse.powi(2) * t * c1.y
                    + 3.0 * inverse * t.powi(2) * c2.y
                    + t.powi(3) * p2.y,
            ));
        }
    }
    sampled
}

#[must_use]
pub fn polygon_self_intersects(points: &[Point]) -> bool {
    let orientation =
        |a: Point, b: Point, c: Point| (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
    for first in 0..points.len() {
        let a = points[first];
        let b = points[(first + 1) % points.len()];
        for second in first + 1..points.len() {
            if second == first || second == (first + 1) % points.len() {
                continue;
            }
            if first == 0 && second == points.len() - 1 {
                continue;
            }
            let c = points[second];
            let d = points[(second + 1) % points.len()];
            if orientation(a, b, c) * orientation(a, b, d) < -1.0e-9
                && orientation(c, d, a) * orientation(c, d, b) < -1.0e-9
            {
                return true;
            }
        }
    }
    false
}
