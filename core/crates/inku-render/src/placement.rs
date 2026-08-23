//! Deterministic normalized placement for repeated marks.

use sha2::{Digest, Sha256};

use crate::determinism::hash01;
use crate::types::{ArrangementPath, CanvasSize, Density, Point, RhythmSpacing, Seed};

const PATH_WAVE_AMPLITUDE: f64 = 0.22;
const PATH_JITTER: f64 = 0.08;
const PATH_SPREAD: f64 = 0.30;

fn clamp01(value: f64) -> f64 {
    value.clamp(0.0, 1.0)
}

/// Per-axis factors that express a normalized distance in short-side units.
#[must_use]
pub fn short_side_scales(canvas: Option<CanvasSize>) -> Point {
    canvas.map_or(Point::new(1.0, 1.0), |canvas| {
        Point::new(canvas.unit() / canvas.width, canvas.unit() / canvas.height)
    })
}

#[must_use]
pub fn scatter_position(index: usize, seed: Seed, margin: f64) -> Point {
    let digest = Sha256::digest(format!("{seed}:s:{index}").as_bytes());
    let x = u32::from_le_bytes(digest[..4].try_into().expect("four digest bytes"));
    let y = u32::from_le_bytes(digest[4..8].try_into().expect("four digest bytes"));
    let span = 1.0 - 2.0 * margin;
    Point::new(
        margin + f64::from(x) / f64::from(u32::MAX) * span,
        margin + f64::from(y) / f64::from(u32::MAX) * span,
    )
}

#[must_use]
pub fn rhythm_parameter(index: usize, count: usize, seed: Seed, spacing: RhythmSpacing) -> f64 {
    if count <= 1 {
        return 0.0;
    }
    let base = index as f64 / (count - 1) as f64;
    match spacing {
        RhythmSpacing::Accelerando => base.powf(1.35),
        RhythmSpacing::Loose => {
            let jitter = (hash01(index as i64, seed, "rhythm-loose") - 0.5) * 0.16;
            clamp01(base + jitter)
        }
        RhythmSpacing::Syncopated => {
            let beat = if index % 2 == 1 { 0.09 } else { -0.045 };
            clamp01(base + beat * (base * std::f64::consts::PI).sin())
        }
        RhythmSpacing::None => base,
    }
}

#[must_use]
pub fn path_position(
    index: usize,
    count: usize,
    seed: Seed,
    margin: f64,
    path: ArrangementPath,
    spacing: RhythmSpacing,
    canvas: Option<CanvasSize>,
) -> Point {
    let span = 1.0 - 2.0 * margin;
    let t = rhythm_parameter(index, count, seed, spacing);
    let jitter_a = hash01(index as i64, seed, "a") - 0.5;
    let jitter_b = hash01(index as i64, seed, "b") - 0.5;
    let scale = short_side_scales(canvas);
    match path {
        ArrangementPath::Diagonal => Point::new(
            clamp01(margin + t * span + jitter_a * PATH_JITTER * scale.x),
            clamp01(1.0 - margin - t * span + jitter_b * PATH_JITTER * scale.y),
        ),
        ArrangementPath::Wave => Point::new(
            clamp01(margin + t * span),
            clamp01(
                0.5 + ((t * std::f64::consts::TAU).sin() * PATH_WAVE_AMPLITUDE
                    + jitter_b * PATH_JITTER)
                    * scale.y,
            ),
        ),
        ArrangementPath::TopToBottom => Point::new(
            clamp01(0.5 + jitter_a * PATH_SPREAD * scale.x),
            clamp01(margin + t * span),
        ),
        ArrangementPath::LeftToRight => Point::new(
            clamp01(margin + t * span),
            clamp01(0.5 + jitter_b * PATH_SPREAD * scale.y),
        ),
        ArrangementPath::RightHalf => Point::new(
            clamp01(0.56 + hash01(index as i64, seed, "x") * (0.44 - margin)),
            clamp01(margin + hash01(index as i64, seed, "y") * span),
        ),
        ArrangementPath::None => scatter_position(index, seed, margin),
    }
}

fn density_radius(density: Density, preserve_space: bool) -> f64 {
    let radius = match density {
        Density::Low => 0.035,
        Density::Medium => 0.060,
        Density::High => 0.085,
        Density::None => 0.045,
    };
    radius * if preserve_space { 0.85 } else { 1.0 }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ClusterPlacement {
    pub index: usize,
    pub count: usize,
    pub seed: Seed,
    pub margin: f64,
    pub path: ArrangementPath,
    pub cluster_count: usize,
    pub density: Density,
    pub preserve_space: bool,
    pub rhythm_spacing: RhythmSpacing,
    pub canvas: Option<CanvasSize>,
}

#[must_use]
pub fn clustered_position(request: ClusterPlacement) -> Point {
    let cluster_count = request.cluster_count.clamp(1, request.count);
    let cluster_index = request.index % cluster_count;
    let local_index = request.index / cluster_count;
    let local_total = request.count.div_ceil(cluster_count).max(1);
    let center_margin = if request.preserve_space {
        request.margin.max(0.20)
    } else {
        request.margin
    };
    let cluster_seed = request.seed ^ 0xC1A57;
    let center = if request.path == ArrangementPath::None {
        scatter_position(cluster_index, cluster_seed, center_margin)
    } else {
        path_position(
            cluster_index,
            cluster_count,
            cluster_seed,
            center_margin,
            request.path,
            request.rhythm_spacing,
            None,
        )
    };
    let angle = match request.path {
        ArrangementPath::Diagonal => -std::f64::consts::FRAC_PI_4,
        ArrangementPath::TopToBottom => std::f64::consts::FRAC_PI_2,
        ArrangementPath::LeftToRight | ArrangementPath::RightHalf | ArrangementPath::Wave => 0.0,
        ArrangementPath::None => {
            hash01(cluster_index as i64, request.seed, "cluster-axis") * std::f64::consts::TAU
        }
    };
    let tangent = Point::new(angle.cos(), angle.sin());
    let normal = Point::new(-tangent.y, tangent.x);
    let mut local_t = (local_index as f64 + 0.5) / local_total as f64;
    if request.rhythm_spacing != RhythmSpacing::None && local_total > 1 {
        local_t = rhythm_parameter(
            local_index,
            local_total,
            request.seed ^ cluster_index as Seed,
            request.rhythm_spacing,
        );
    }
    let centered = (local_t - 0.5) * 2.0;
    let radius = density_radius(request.density, request.preserve_space);
    let long_span =
        radius * (1.45 + hash01(cluster_index as i64, request.seed, "cluster-long") * 0.95);
    let cross_span =
        radius * (0.28 + hash01(cluster_index as i64, request.seed, "cluster-cross") * 0.32);
    let along = centered * long_span
        + (hash01(request.index as i64, request.seed, "cluster-along") - 0.5) * radius * 0.20;
    let cross = (hash01(request.index as i64, request.seed, "cluster-cross-jitter") - 0.5)
        * cross_span
        * (1.25 - 0.45 * centered.abs());
    let bend = (local_t * std::f64::consts::PI).sin()
        * (hash01(cluster_index as i64, request.seed, "cluster-bend") - 0.5)
        * radius
        * 0.55;
    let offset = Point::new(
        tangent.x * along + normal.x * (cross + bend),
        tangent.y * along + normal.y * (cross + bend),
    );
    let scale = short_side_scales(request.canvas);
    Point::new(
        clamp01(center.x + offset.x * scale.x),
        clamp01(center.y + offset.y * scale.y),
    )
}

/// Keep a region's center proportional while expressing its extents on the short side.
#[must_use]
pub fn region_in_short_side_units(region: [f64; 4], canvas: Option<CanvasSize>) -> [f64; 4] {
    let [x0, y0, x1, y1] = region;
    let scale = short_side_scales(canvas);
    if scale == Point::new(1.0, 1.0) {
        return region;
    }
    let center = Point::new((x0 + x1) / 2.0, (y0 + y1) / 2.0);
    let half = Point::new((x1 - x0) / 2.0, (y1 - y0) / 2.0);
    [
        center.x - half.x * scale.x,
        center.y - half.y * scale.y,
        center.x + half.x * scale.x,
        center.y + half.y * scale.y,
    ]
}
