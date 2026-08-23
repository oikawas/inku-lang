//! Shared minor-arc geometry for planning and rendering.

use crate::types::Point;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct MinorArc {
    pub center: Point,
    pub radius: f64,
    pub angle_start: f64,
    pub angle_end: f64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ArcError {
    ZeroChord,
    InvalidSagitta,
    NonMinorSweep,
}

#[must_use]
pub fn minor_arc_delta(angle_start: f64, angle_end: f64) -> f64 {
    (angle_end - angle_start + 180.0).rem_euclid(360.0) - 180.0
}

#[must_use]
pub fn arc_point(center: Point, radius: f64, angle_degrees: f64) -> Point {
    let angle = angle_degrees.to_radians();
    Point::new(
        center.x + radius * angle.cos(),
        center.y - radius * angle.sin(),
    )
}

pub fn arc_from_endpoints_and_sagitta(
    start: Point,
    end: Point,
    sagitta: f64,
) -> Result<MinorArc, ArcError> {
    let delta = Point::new(end.x - start.x, end.y - start.y);
    let chord = delta.x.hypot(delta.y);
    let height = sagitta.abs();
    if chord <= 1.0e-12 {
        return Err(ArcError::ZeroChord);
    }
    if height <= 1.0e-12 || height >= chord / 2.0 {
        return Err(ArcError::InvalidSagitta);
    }
    let radius = chord * chord / (8.0 * height) + height / 2.0;
    let midpoint = Point::new((start.x + end.x) / 2.0, (start.y + end.y) / 2.0);
    let normal = Point::new(-delta.y / chord, delta.x / chord);
    let sign = if sagitta > 0.0 { 1.0 } else { -1.0 };
    let center = Point::new(
        midpoint.x - sign * (radius - height) * normal.x,
        midpoint.y - sign * (radius - height) * normal.y,
    );
    let angle = |point: Point| {
        (-(point.y - center.y))
            .atan2(point.x - center.x)
            .to_degrees()
    };
    let angle_start = angle(start);
    let delta = minor_arc_delta(angle_start, angle(end));
    if delta.abs() >= 180.0 - 1.0e-9 {
        return Err(ArcError::NonMinorSweep);
    }
    Ok(MinorArc {
        center,
        radius,
        angle_start,
        angle_end: angle_start + delta,
    })
}

pub fn signed_arc_sagitta(arc: MinorArc) -> Result<f64, ArcError> {
    let delta = minor_arc_delta(arc.angle_start, arc.angle_end);
    let start = arc_point(arc.center, arc.radius, arc.angle_start);
    let end = arc_point(arc.center, arc.radius, arc.angle_start + delta);
    let apex = arc_point(arc.center, arc.radius, arc.angle_start + delta / 2.0);
    let chord = Point::new(end.x - start.x, end.y - start.y);
    let length = chord.x.hypot(chord.y);
    if length <= 1.0e-12 {
        return Err(ArcError::ZeroChord);
    }
    let midpoint = Point::new((start.x + end.x) / 2.0, (start.y + end.y) / 2.0);
    let normal = Point::new(-chord.y / length, chord.x / length);
    Ok((apex.x - midpoint.x) * normal.x + (apex.y - midpoint.y) * normal.y)
}
