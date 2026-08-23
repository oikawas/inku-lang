//! Deterministic tool grammar and straight-stroke synthesis.

use std::collections::{BTreeMap, BTreeSet};

use sha2::{Digest, Sha256};

use crate::geometry::centerline_normals;
use crate::support::{DEFAULT_SUPPORT, Support, support_response};
use crate::types::{Point, Seed, Weight};

const HAND_GROUP_SIZE: f64 = 0.35;
const HAND_GROUP_ROTATION: f64 = 27.0;
const WILD_GAIN: f64 = 3.5;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ToolGrammar {
    pub stiffness: f64,
    pub damping: f64,
    pub energy_width: f64,
    pub energy_lateral: f64,
    pub event_rate: f64,
    pub taper: f64,
    pub bulge: f64,
    pub gesture: f64,
    pub periodic: bool,
    pub quantize: f64,
    pub width_steps: u8,
    pub fill_hand: f64,
    pub group_hand: f64,
    pub group_rotation: f64,
    pub fill_contrast: f64,
}

macro_rules! hand_grammar {
    ($stiffness:expr, $damping:expr, $energy_width:expr, $energy_lateral:expr,
     $event_rate:expr, $taper:expr, $bulge:expr, $gesture:expr,
     $fill_hand:expr, $fill_contrast:expr) => {
        ToolGrammar {
            stiffness: $stiffness,
            damping: $damping,
            energy_width: $energy_width,
            energy_lateral: $energy_lateral,
            event_rate: $event_rate,
            taper: $taper,
            bulge: $bulge,
            gesture: $gesture,
            periodic: false,
            quantize: 0.0,
            width_steps: 0,
            fill_hand: $fill_hand,
            group_hand: HAND_GROUP_SIZE,
            group_rotation: HAND_GROUP_ROTATION,
            fill_contrast: $fill_contrast,
        }
    };
}

#[must_use]
pub const fn grammar(weight: Weight) -> ToolGrammar {
    match weight {
        Weight::Silverpoint => {
            hand_grammar!(0.93, 0.90, 0.08, 0.05, 0.04, 0.05, 0.02, 0.012, 0.05, 1.0)
        }
        Weight::Pencil => hand_grammar!(0.58, 0.68, 0.34, 0.42, 0.55, 0.12, 0.14, 0.05, 0.60, 1.0),
        Weight::Pen => hand_grammar!(0.82, 0.80, 0.16, 0.12, 0.12, 0.08, 0.06, 0.022, 0.25, 1.0),
        Weight::Rotring => ToolGrammar {
            stiffness: 1.0,
            damping: 1.0,
            energy_width: 0.0,
            energy_lateral: 0.0,
            event_rate: 0.0,
            taper: 0.0,
            bulge: 0.0,
            gesture: 0.0,
            periodic: false,
            quantize: 0.0,
            width_steps: 0,
            fill_hand: 0.0,
            group_hand: 0.0,
            group_rotation: 0.0,
            fill_contrast: 1.0,
        },
        Weight::Crayon => hand_grammar!(0.48, 0.60, 0.38, 0.34, 0.75, 0.14, 0.18, 0.06, 0.72, 1.0),
        Weight::Chalk => hand_grammar!(0.42, 0.56, 0.42, 0.38, 0.90, 0.18, 0.20, 0.07, 0.80, 1.13),
        Weight::BrushThin => {
            hand_grammar!(0.36, 0.52, 0.66, 0.48, 0.48, 0.88, 0.28, 0.10, 0.90, 1.0)
        }
        Weight::BrushThick => {
            hand_grammar!(0.30, 0.48, 0.78, 0.55, 0.58, 0.92, 0.34, 0.13, 1.00, 1.0)
        }
        Weight::Burin => hand_grammar!(0.91, 0.86, 0.58, 0.09, 0.08, 0.98, 1.0, 0.018, 0.10, 1.0),
        Weight::Drypoint => {
            hand_grammar!(0.68, 0.70, 0.44, 0.20, 0.45, 0.55, 0.48, 0.05, 0.45, 1.0)
        }
        Weight::Computer => ToolGrammar {
            stiffness: 1.0,
            damping: 1.0,
            energy_width: 0.30,
            energy_lateral: 0.34,
            event_rate: 0.0,
            taper: 0.0,
            bulge: 0.0,
            gesture: 0.06,
            periodic: true,
            quantize: 0.018,
            width_steps: 4,
            fill_hand: 0.0,
            group_hand: 0.0,
            group_rotation: 0.0,
            fill_contrast: 1.0,
        },
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StrokeEvent {
    Catch,
    Fade,
    Correction,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct StrokeSample {
    pub t: f64,
    pub point: Point,
    pub width: f64,
    pub energy: f64,
    pub lateral: f64,
    pub event: Option<StrokeEvent>,
    pub residual: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct StrokeResult {
    pub samples: Vec<StrokeSample>,
    pub outline: Vec<Point>,
    pub event_count: usize,
    pub burr_side: i8,
    pub burr_opacity: f64,
    pub grid_step: f64,
    pub cuts: Vec<bool>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct StrokeRequest {
    pub start: Point,
    pub end: Point,
    pub base_width: f64,
    pub weight: Weight,
    pub seed: Seed,
    pub sample_count: usize,
    pub wild: bool,
    pub grid_step: f64,
    pub support: Support,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StrokeTerminal {
    Taper,
    Loaded,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ContourStrokeResult {
    pub samples: Vec<StrokeSample>,
    pub left: Vec<Point>,
    pub right: Vec<Point>,
    pub event_count: usize,
    pub burr_side: i8,
    pub burr_opacity: f64,
    pub closed: bool,
    pub grid_step: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ContourStrokeRequest<'a> {
    pub centerline: &'a [Point],
    pub base_width: f64,
    pub weight: Weight,
    pub seed: Seed,
    pub closed: bool,
    pub anchors: &'a BTreeSet<usize>,
    pub grid_step: f64,
    pub wild: bool,
    pub support: Support,
    pub terminal: StrokeTerminal,
}

/// Stable unit value used by all stroke and support event streams.
#[must_use]
pub(crate) fn unit(seed: Seed, label: &str, index: i64) -> f64 {
    let digest = Sha256::digest(format!("{seed}:{label}:{index}").as_bytes());
    let raw = u64::from_le_bytes(digest[..8].try_into().expect("eight digest bytes"));
    raw as f64 / u64::MAX as f64
}

fn smooth_noise(t: f64, seed: Seed, octave: i32) -> f64 {
    let frequency = 2_f64.powi(octave);
    smooth_noise_salted(t, seed, &format!("energy-{octave}"), frequency)
}

fn smooth_noise_salted(t: f64, seed: Seed, salt: &str, frequency: f64) -> f64 {
    let x = t * frequency;
    let index = x.floor() as i64;
    let fraction = x - index as f64;
    let smooth = fraction * fraction * (3.0 - 2.0 * fraction);
    let lower = unit(seed, salt, index) * 2.0 - 1.0;
    let upper = unit(seed, salt, index + 1) * 2.0 - 1.0;
    lower * (1.0 - smooth) + upper * smooth
}

#[must_use]
pub fn latent_energy(t: f64, seed: Seed) -> f64 {
    ((1..=6)
        .map(|octave| smooth_noise(t, seed, octave) / 2_f64.powi(octave).sqrt())
        .sum::<f64>()
        / 1.75)
        .clamp(-1.0, 1.0)
}

fn edge_window(t: f64) -> f64 {
    const EDGE: f64 = 0.16;
    if t <= 0.0 || t >= 1.0 {
        0.0
    } else if t < EDGE {
        0.5 * (1.0 - (std::f64::consts::PI * t / EDGE).cos())
    } else if t > 1.0 - EDGE {
        0.5 * (1.0 - (std::f64::consts::PI * (1.0 - t) / EDGE).cos())
    } else {
        1.0
    }
}

fn swell(t: f64, seed: Seed) -> f64 {
    0.45 + 0.55 * (0.5 + 0.5 * smooth_noise_salted(t, seed, "swell", 1.5))
}

fn gesture_wave(t: f64, seed: Seed, salt: &str) -> f64 {
    (smooth_noise_salted(t, seed, salt, 1.0) * 0.7 + smooth_noise_salted(t, seed, salt, 2.0) * 0.35)
        .clamp(-1.0, 1.0)
}

fn quantize(value: f64, step: f64) -> f64 {
    if step <= 0.0 {
        value
    } else {
        (value / step).round_ties_even() * step
    }
}

#[must_use]
pub fn grid_point(value: f64, step: f64) -> f64 {
    quantize(value, step)
}

fn machine_energy(t: f64) -> f64 {
    0.72 * (t * std::f64::consts::TAU * 5.0).sin() + 0.28 * (t * std::f64::consts::TAU * 10.0).sin()
}

fn machine_swell(t: f64) -> f64 {
    0.45 + 0.55 * (std::f64::consts::PI * t).sin()
}

fn machine_gesture(t: f64) -> f64 {
    (t * std::f64::consts::TAU * 2.0).sin()
}

fn loaded_profile(t: f64) -> f64 {
    const LANDING: f64 = 0.45;
    const SETTLE: f64 = 0.10;
    const LIFT_AT: f64 = 0.94;
    const LIFT_TO: f64 = 0.55;
    let landing = 1.0 + LANDING * (-t / SETTLE).exp();
    if t < LIFT_AT {
        landing
    } else {
        landing * (LIFT_TO + (1.0 - LIFT_TO) * (1.0 - t) / (1.0 - LIFT_AT))
    }
}

fn event_map(seed: Seed, rate: f64, count: usize) -> BTreeMap<usize, StrokeEvent> {
    let mut events = BTreeMap::new();
    let probability = (rate / count.saturating_sub(2).max(1) as f64).min(0.12);
    for index in 3..count.saturating_sub(3) {
        if unit(seed, "event-arrival", index as i64) < probability {
            let kind = (unit(seed, "event-kind", index as i64) * 3.0) as usize % 3;
            events.insert(
                index,
                [
                    StrokeEvent::Catch,
                    StrokeEvent::Fade,
                    StrokeEvent::Correction,
                ][kind],
            );
            if events.len() >= 2 {
                break;
            }
        }
    }
    events
}

fn ink_runs(cuts: &[bool], minimum: usize) -> Vec<Vec<usize>> {
    let mut runs = Vec::new();
    let mut current = Vec::new();
    for (index, cut) in cuts.iter().copied().enumerate() {
        if cut {
            if current.len() >= minimum {
                runs.push(std::mem::take(&mut current));
            }
        } else {
            current.push(index);
        }
    }
    if current.len() >= minimum {
        runs.push(current);
    }
    runs
}

fn arc_length_parameters(points: &[Point], closed: bool) -> Vec<f64> {
    let mut running = Vec::with_capacity(points.len());
    running.push(0.0);
    let mut total = 0.0;
    for pair in points.windows(2) {
        total += (pair[1].x - pair[0].x).hypot(pair[1].y - pair[0].y);
        running.push(total);
    }
    if closed && points.len() > 1 {
        let first = points[0];
        let last = points[points.len() - 1];
        total += (first.x - last.x).hypot(first.y - last.y);
    }
    if total <= 1.0e-9 {
        vec![0.0; points.len()]
    } else {
        running.into_iter().map(|value| value / total).collect()
    }
}

fn banks_for_centerline(
    points: &[Point],
    widths: &[f64],
    closed: bool,
) -> (Vec<Point>, Vec<Point>) {
    let normals = centerline_normals(points, closed);
    let mut left = Vec::with_capacity(points.len());
    let mut right = Vec::with_capacity(points.len());
    for (index, point) in points.iter().copied().enumerate() {
        let normal = normals[index];
        let width = widths[index.min(widths.len() - 1)];
        left.push(Point::new(
            point.x + normal.x * width / 2.0,
            point.y + normal.y * width / 2.0,
        ));
        right.push(Point::new(
            point.x - normal.x * width / 2.0,
            point.y - normal.y * width / 2.0,
        ));
    }
    (left, right)
}

fn correct_closed_seam(samples: &mut [StrokeSample], intended: &[Point], parameters: &[f64]) {
    let span = parameters[parameters.len() - 1];
    if span <= 1.0e-9 {
        return;
    }
    let first = samples[0];
    let last_index = samples.len() - 1;
    let last = samples[last_index];
    let gap = Point::new(
        (last.point.x - intended[last_index].x) - (first.point.x - intended[0].x),
        (last.point.y - intended[last_index].y) - (first.point.y - intended[0].y),
    );
    let width_gap = last.width - first.width;
    for (index, sample) in samples.iter_mut().enumerate() {
        let factor = parameters[index] / span;
        sample.point.x -= gap.x * factor;
        sample.point.y -= gap.y * factor;
        sample.width = (sample.width - width_gap * factor).max(0.015);
    }
}

#[must_use]
pub fn synthesize_stroke(request: StrokeRequest) -> StrokeResult {
    let StrokeRequest {
        start,
        end,
        base_width,
        weight,
        seed,
        sample_count,
        wild,
        grid_step,
        support,
    } = request;
    assert!(sample_count >= 2, "a stroke requires at least two samples");
    let grammar = grammar(weight);
    let delta = Point::new(end.x - start.x, end.y - start.y);
    let length = delta.x.hypot(delta.y).max(1.0e-6);
    let direction = Point::new(delta.x / length, delta.y / length);
    let normal = Point::new(-direction.y, direction.x);
    let events = event_map(seed, grammar.event_rate, sample_count);
    let mut position = start;
    let mut velocity = Point::new(
        delta.x / (sample_count - 1) as f64,
        delta.y / (sample_count - 1) as f64,
    );
    let mut gesture_amplitude = length * grammar.gesture;
    if wild && !grammar.periodic {
        gesture_amplitude *= WILD_GAIN;
    }
    let mut samples = Vec::with_capacity(sample_count);
    for index in 0..sample_count {
        let t = index as f64 / (sample_count - 1) as f64;
        let target = Point::new(start.x + delta.x * t, start.y + delta.y * t);
        if index > 0 {
            velocity.x = velocity.x * grammar.damping + (target.x - position.x) * grammar.stiffness;
            velocity.y = velocity.y * grammar.damping + (target.y - position.y) * grammar.stiffness;
            position.x += velocity.x * 0.72;
            position.y += velocity.y * 0.72;
        }
        let (energy, envelope) = if grammar.periodic {
            (machine_energy(t), machine_swell(t))
        } else {
            (latent_energy(t, seed), edge_window(t) * swell(t, seed))
        };
        let mut lateral = energy * grammar.energy_lateral * base_width * (0.18 + 0.82 * envelope);
        let event = events.get(&index).copied();
        let mut event_width = 1.0;
        match event {
            Some(StrokeEvent::Catch) => {
                event_width = 1.45;
                lateral += (unit(seed, "catch-side", index as i64) * 2.0 - 1.0) * base_width * 0.35;
            }
            Some(StrokeEvent::Fade) => event_width = 0.04,
            Some(StrokeEvent::Correction) => {
                lateral +=
                    (unit(seed, "correction-kick", index as i64) * 2.0 - 1.0) * base_width * 0.25;
            }
            None => {}
        }
        let mut profile = 1.0;
        if grammar.taper != 0.0 {
            profile *= (1.0 - grammar.taper) + grammar.taper * envelope;
        }
        if grammar.bulge != 0.0 {
            profile *= 1.0 + grammar.bulge * envelope;
        }
        let mut width =
            (base_width * profile * (1.0 + grammar.energy_width * energy * 0.45) * event_width)
                .max(0.015);
        let mut gesture = Point::new(0.0, 0.0);
        if gesture_amplitude != 0.0 {
            let (window, lateral_gesture, longitudinal_gesture) = if grammar.periodic {
                (1.0, machine_gesture(t), 0.0)
            } else {
                (
                    edge_window(t),
                    gesture_wave(t, seed, "gesture-lat"),
                    gesture_wave(t, seed, "gesture-lon"),
                )
            };
            gesture.x = gesture_amplitude
                * window
                * (normal.x * lateral_gesture + direction.x * longitudinal_gesture);
            gesture.y = gesture_amplitude
                * window
                * (normal.y * lateral_gesture + direction.y * longitudinal_gesture);
        }
        let mut point = Point::new(
            position.x + normal.x * lateral + gesture.x,
            position.y + normal.y * lateral + gesture.y,
        );
        let mut residual = 0.0;
        if grid_step > 0.0 {
            let quantized = Point::new(quantize(point.x, grid_step), quantize(point.y, grid_step));
            residual = (point.x - quantized.x).hypot(point.y - quantized.y);
            point = quantized;
        }
        if grammar.width_steps > 0 {
            width = quantize(width, base_width / f64::from(grammar.width_steps)).max(0.015);
        }
        samples.push(StrokeSample {
            t,
            point,
            width,
            energy,
            lateral,
            event,
            residual,
        });
    }
    samples[0].point = start;
    samples[0].lateral = 0.0;
    samples[0].event = None;
    samples[0].residual = 0.0;
    samples[sample_count - 1].point = end;
    samples[sample_count - 1].lateral = 0.0;
    samples[sample_count - 1].event = None;
    samples[sample_count - 1].residual = 0.0;

    let widths: Vec<f64> = samples.iter().map(|sample| sample.width).collect();
    let (widths, cuts) = support_response(&widths, weight, seed, support);
    for (sample, width) in samples.iter_mut().zip(&widths) {
        sample.width = *width;
    }
    let mut outline = Vec::new();
    if cuts.iter().any(|cut| *cut) {
        for run in ink_runs(&cuts, 2) {
            if !outline.is_empty() {
                outline.push(Point::new(f64::NAN, f64::NAN));
            }
            outline.extend(run.iter().map(|index| {
                let sample = samples[*index];
                Point::new(
                    sample.point.x + normal.x * sample.width / 2.0,
                    sample.point.y + normal.y * sample.width / 2.0,
                )
            }));
            outline.extend(run.iter().rev().map(|index| {
                let sample = samples[*index];
                Point::new(
                    sample.point.x - normal.x * sample.width / 2.0,
                    sample.point.y - normal.y * sample.width / 2.0,
                )
            }));
        }
    } else {
        outline.extend(samples.iter().map(|sample| {
            Point::new(
                sample.point.x + normal.x * sample.width / 2.0,
                sample.point.y + normal.y * sample.width / 2.0,
            )
        }));
        outline.extend(samples.iter().rev().map(|sample| {
            Point::new(
                sample.point.x - normal.x * sample.width / 2.0,
                sample.point.y - normal.y * sample.width / 2.0,
            )
        }));
    }
    let burr_side = if unit(seed, "burr-side", 0) < 0.5 {
        -1
    } else {
        1
    };
    let slow_energy =
        samples.iter().map(|sample| sample.energy).sum::<f64>() / samples.len() as f64;
    let burr_opacity =
        (0.15 + 0.12 * (1.0 - slow_energy) + 0.08 * unit(seed, "burr-ink", 0)).min(0.35);
    StrokeResult {
        samples,
        outline,
        event_count: events.len(),
        burr_side,
        burr_opacity,
        grid_step,
        cuts,
    }
}

/// Synthesize one performed stroke along an arbitrary intended centerline.
#[must_use]
pub fn synthesize_contour(request: ContourStrokeRequest<'_>) -> ContourStrokeResult {
    let ContourStrokeRequest {
        centerline,
        base_width,
        weight,
        seed,
        closed,
        anchors,
        grid_step,
        wild,
        support,
        terminal,
    } = request;
    assert!(
        !centerline.is_empty(),
        "a contour requires at least one point"
    );
    let grammar = grammar(weight);
    if centerline.len() < 2 {
        let sample = StrokeSample {
            t: 0.0,
            point: centerline[0],
            width: base_width,
            energy: 0.0,
            lateral: 0.0,
            event: None,
            residual: 0.0,
        };
        return ContourStrokeResult {
            samples: vec![sample],
            left: centerline.to_vec(),
            right: centerline.to_vec(),
            event_count: 0,
            burr_side: 1,
            burr_opacity: 0.0,
            closed,
            grid_step: 0.0,
        };
    }

    let count = centerline.len();
    let normals = centerline_normals(centerline, closed);
    let parameters = arc_length_parameters(centerline, closed);
    let events = event_map(seed, grammar.event_rate, count);
    let mut gesture_amplitude = 0.0;
    if wild && !grammar.periodic {
        let total_length = centerline
            .windows(2)
            .map(|pair| (pair[1].x - pair[0].x).hypot(pair[1].y - pair[0].y))
            .sum::<f64>()
            .max(1.0e-6);
        let size = if closed {
            total_length / std::f64::consts::TAU
        } else {
            total_length
        };
        gesture_amplitude = size * grammar.gesture * WILD_GAIN;
    }
    let mut gestures = vec![0.0; count];
    if gesture_amplitude != 0.0 {
        gestures = parameters
            .iter()
            .map(|t| gesture_wave(*t, seed, "gesture-lat"))
            .collect();
        if closed {
            let mean = gestures.iter().sum::<f64>() / count as f64;
            for gesture in &mut gestures {
                *gesture -= mean;
            }
        }
    }

    let mut position = centerline[0];
    let mut velocity = Point::new(0.0, 0.0);
    let mut samples = Vec::with_capacity(count);
    for (index, target) in centerline.iter().copied().enumerate() {
        let t = parameters[index];
        if index > 0 {
            let previous = centerline[index - 1];
            let step = Point::new(target.x - previous.x, target.y - previous.y);
            velocity.x =
                velocity.x * grammar.damping + (target.x - position.x - step.x) * grammar.stiffness;
            velocity.y =
                velocity.y * grammar.damping + (target.y - position.y - step.y) * grammar.stiffness;
            position.x += step.x + velocity.x * 0.72;
            position.y += step.y + velocity.y * 0.72;
        }
        let (energy, envelope) = if grammar.periodic {
            (
                machine_energy(t),
                if closed { 1.0 } else { machine_swell(t) },
            )
        } else if closed {
            (latent_energy(t, seed), swell(t, seed))
        } else {
            (latent_energy(t, seed), edge_window(t) * swell(t, seed))
        };
        let mut lateral = energy * grammar.energy_lateral * base_width * (0.18 + 0.82 * envelope);
        let mut event = events.get(&index).copied();
        let mut event_width = 1.0;
        match event {
            Some(StrokeEvent::Catch) => {
                event_width = 1.45;
                lateral += (unit(seed, "catch-side", index as i64) * 2.0 - 1.0) * base_width * 0.35;
            }
            Some(StrokeEvent::Fade) => event_width = 0.04,
            Some(StrokeEvent::Correction) => {
                lateral +=
                    (unit(seed, "correction-kick", index as i64) * 2.0 - 1.0) * base_width * 0.25;
            }
            None => {}
        }
        let mut profile = 1.0;
        if terminal == StrokeTerminal::Loaded && !grammar.periodic {
            profile = loaded_profile(t);
        } else {
            if grammar.taper != 0.0 {
                profile *= (1.0 - grammar.taper) + grammar.taper * envelope;
            }
            if grammar.bulge != 0.0 {
                profile *= 1.0 + grammar.bulge * envelope;
            }
        }
        let mut width =
            (base_width * profile * (1.0 + grammar.energy_width * energy * 0.45) * event_width)
                .max(0.015);
        let mut gesture = 0.0;
        if gesture_amplitude != 0.0 {
            let mut window = if closed { 1.0 } else { edge_window(t) };
            if !anchors.is_empty() {
                let distance = anchors
                    .iter()
                    .map(|anchor| index.abs_diff(*anchor))
                    .min()
                    .expect("anchors are nonempty");
                window *= (distance as f64 / 12.0).min(1.0);
            }
            gesture = gesture_amplitude * window * gestures[index];
        }
        let normal = normals[index];
        let mut point = Point::new(
            position.x + normal.x * (lateral + gesture),
            position.y + normal.y * (lateral + gesture),
        );
        let mut residual = 0.0;
        if grid_step > 0.0 {
            let quantized = Point::new(quantize(point.x, grid_step), quantize(point.y, grid_step));
            residual = (point.x - quantized.x).hypot(point.y - quantized.y);
            point = quantized;
        }
        if grammar.width_steps > 0 {
            width = quantize(width, base_width / f64::from(grammar.width_steps)).max(0.015);
        }
        if anchors.contains(&index) {
            point = target;
            lateral = 0.0;
            event = None;
            position = target;
            residual = 0.0;
        }
        samples.push(StrokeSample {
            t,
            point,
            width,
            energy,
            lateral,
            event,
            residual,
        });
    }

    if !closed {
        samples[0].point = centerline[0];
        samples[0].lateral = 0.0;
        samples[0].event = None;
        samples[0].residual = 0.0;
        samples[count - 1].point = centerline[count - 1];
        samples[count - 1].lateral = 0.0;
        samples[count - 1].event = None;
        samples[count - 1].residual = 0.0;
    } else if anchors.is_empty() && count > 2 {
        correct_closed_seam(&mut samples, centerline, &parameters);
    }

    let widths: Vec<f64> = samples.iter().map(|sample| sample.width).collect();
    let (widths, cuts) = support_response(&widths, weight, seed, support);
    for (sample, width) in samples.iter_mut().zip(&widths) {
        sample.width = *width;
    }
    let performed: Vec<Point> = samples.iter().map(|sample| sample.point).collect();
    let (mut left, mut right) = banks_for_centerline(&performed, &widths, closed);
    if !closed && cuts.iter().any(|cut| *cut) {
        for ((left, right), cut) in left.iter_mut().zip(&mut right).zip(cuts) {
            if cut {
                *left = Point::new(f64::NAN, f64::NAN);
                *right = Point::new(f64::NAN, f64::NAN);
            }
        }
    }
    let burr_side = if unit(seed, "burr-side", 0) < 0.5 {
        -1
    } else {
        1
    };
    let slow_energy =
        samples.iter().map(|sample| sample.energy).sum::<f64>() / samples.len() as f64;
    let burr_opacity =
        (0.15 + 0.12 * (1.0 - slow_energy) + 0.08 * unit(seed, "burr-ink", 0)).min(0.35);
    ContourStrokeResult {
        samples,
        left,
        right,
        event_count: events.len(),
        burr_side,
        burr_opacity,
        closed,
        grid_step,
    }
}

#[must_use]
pub fn synthesize_default_stroke(
    start: Point,
    end: Point,
    base_width: f64,
    weight: Weight,
    seed: Seed,
) -> StrokeResult {
    synthesize_stroke(StrokeRequest {
        start,
        end,
        base_width,
        weight,
        seed,
        sample_count: 49,
        wild: false,
        grid_step: 0.0,
        support: DEFAULT_SUPPORT,
    })
}
