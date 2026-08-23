//! Deterministic contact geometry between a tool outline and the support.

use crate::determinism::value_noise_1d;
use crate::types::{Point, Seed};

pub const CONTACT_LENGTH_QUANTUM: u32 = 6;

fn distance(a: Point, b: Point) -> f64 {
    (b.x - a.x).hypot(b.y - a.y)
}

/// Coverage and natural wavelength represented by an SVG dash specification.
#[must_use]
pub fn dash_spec_stats(dash: Option<&str>) -> (f64, f64) {
    let Some(dash) = dash else {
        return (1.0, 0.0);
    };
    let mut values: Vec<f64> = dash
        .split(',')
        .filter(|value| !value.trim().is_empty())
        .map(|value| {
            value
                .trim()
                .parse::<f64>()
                .expect("dash specification must contain numbers")
        })
        .map(f64::abs)
        .collect();
    let sum: f64 = values.iter().sum();
    if values.is_empty() || sum <= 0.0 {
        return (1.0, 0.0);
    }
    if values.len() % 2 == 1 {
        values.extend_from_within(..);
    }
    let marks: Vec<f64> = values.iter().step_by(2).copied().collect();
    let gaps: Vec<f64> = values.iter().skip(1).step_by(2).copied().collect();
    let coverage = marks.iter().sum::<f64>() / values.iter().sum::<f64>();
    let grain = marks.iter().sum::<f64>() / marks.len() as f64
        + gaps.iter().sum::<f64>() / gaps.len() as f64;
    (coverage, grain)
}

fn contact_field(t: f64, seed: Seed) -> f64 {
    0.62 * value_noise_1d(t, seed) + 0.38 * value_noise_1d(t * 2.7 + 13.1, seed + 977)
}

/// Quantize an arc-length value with Python-compatible decimal ties-to-even.
#[must_use]
pub fn quantize_contact_length(value: f64) -> f64 {
    let scale = 10_f64.powi(CONTACT_LENGTH_QUANTUM as i32);
    (value * scale).round_ties_even() / scale
}

/// Walk a polyline and emit one point per quantized arc-length step.
#[must_use]
pub fn resample_by_length(points: &[Point], step: f64, closed: bool) -> Vec<Point> {
    let step = quantize_contact_length(step);
    if step <= 0.0 || points.len() < 2 {
        return points.to_vec();
    }
    let mut path = points.to_vec();
    if closed {
        path.push(points[0]);
    }
    let mut result = vec![path[0]];
    let mut carry = 0.0;
    for pair in path.windows(2) {
        let (start, end) = (pair[0], pair[1]);
        let segment = quantize_contact_length(distance(start, end));
        if segment <= 1.0e-9 {
            continue;
        }
        let mut travelled = step - carry;
        while travelled <= segment {
            let fraction = travelled / segment;
            result.push(Point::new(
                start.x + (end.x - start.x) * fraction,
                start.y + (end.y - start.y) * fraction,
            ));
            travelled += step;
        }
        carry = (carry + segment) % step;
    }
    result
}

#[derive(Clone, Debug, PartialEq)]
pub struct ContactFragment {
    pub points: Vec<Point>,
    pub weight: f64,
}

fn path_length(points: &[Point], closed: bool) -> f64 {
    let open: f64 = points
        .windows(2)
        .map(|pair| quantize_contact_length(distance(pair[0], pair[1])))
        .sum();
    let seam = if closed && points.len() > 1 {
        quantize_contact_length(distance(*points.last().expect("nonempty"), points[0]))
    } else {
        0.0
    };
    quantize_contact_length(open + seam)
}

fn crossing(walk: &[Point], field: &[f64], threshold: f64, outside: usize, inside: usize) -> Point {
    let (outside_value, inside_value) = (field[outside], field[inside]);
    if (inside_value - outside_value).abs() < 1.0e-9 {
        return walk[inside];
    }
    let fraction = ((threshold - outside_value) / (inside_value - outside_value)).clamp(0.0, 1.0);
    Point::new(
        walk[outside].x + (walk[inside].x - walk[outside].x) * fraction,
        walk[outside].y + (walk[inside].y - walk[outside].y) * fraction,
    )
}

/// Return the non-periodic pieces where the tool clears its contact threshold.
#[must_use]
pub fn contact_fragments(
    points: &[Point],
    coverage: f64,
    grain_px: f64,
    seed: Seed,
    closed: bool,
) -> Vec<ContactFragment> {
    if points.len() < 2 {
        return Vec::new();
    }
    if grain_px <= 0.0 || coverage >= 0.999 {
        return vec![ContactFragment {
            points: points.to_vec(),
            weight: 1.0,
        }];
    }
    let total = path_length(points, closed);
    if total <= 1.0e-6 {
        return Vec::new();
    }
    let grain_px = quantize_contact_length(grain_px);
    let step = quantize_contact_length((grain_px / 3.0).max(total / 600.0).max(0.8));
    let walk = resample_by_length(points, step, closed);
    if walk.len() < 3 {
        return vec![ContactFragment {
            points: points.to_vec(),
            weight: 1.0,
        }];
    }

    let field: Vec<f64> = (0..walk.len())
        .map(|index| contact_field(index as f64 * step / grain_px, seed))
        .collect();
    let mut ordered = field.clone();
    ordered.sort_by(f64::total_cmp);
    let threshold_index =
        (((1.0 - coverage) * ordered.len() as f64) as usize).min(ordered.len() - 1);
    let threshold = ordered[threshold_index];
    let span = (ordered[ordered.len() - 1] - threshold).max(1.0e-6);

    let mut runs: Vec<Vec<usize>> = Vec::new();
    let mut current = Vec::new();
    for (index, value) in field.iter().copied().enumerate() {
        if value >= threshold {
            current.push(index);
        } else if !current.is_empty() {
            runs.push(std::mem::take(&mut current));
        }
    }
    if !current.is_empty() {
        runs.push(current);
    }
    if closed
        && runs.len() > 1
        && runs[0].first() == Some(&0)
        && runs.last().and_then(|run| run.last()) == Some(&(field.len() - 1))
    {
        let mut joined = runs.pop().expect("last run exists");
        joined.extend_from_slice(&runs[0]);
        runs[0] = joined;
    }

    let mut fragments = Vec::new();
    for run in runs {
        let mut piece: Vec<Point> = run.iter().map(|index| walk[*index]).collect();
        let first = run[0];
        let last = *run.last().expect("run is nonempty");
        if first > 0 {
            piece.insert(0, crossing(&walk, &field, threshold, first - 1, first));
        }
        if last + 1 < field.len() {
            piece.push(crossing(&walk, &field, threshold, last + 1, last));
        }
        if piece.len() < 2 || path_length(&piece, false) < 0.6 {
            continue;
        }
        let margin = run
            .iter()
            .map(|index| field[*index] - threshold)
            .sum::<f64>()
            / run.len() as f64;
        fragments.push(ContactFragment {
            points: piece,
            weight: (0.55 + 0.75 * (margin / span)).min(1.0),
        });
    }
    fragments
}
