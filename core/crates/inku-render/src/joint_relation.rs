//! Joint relations of Score 0.20.0: resting on, inside, overlapping and
//! crossing the previous shape (SPEC §14.4).
//!
//! Each is placed from the performed bounds of the current and the previous
//! shape by translation only. The previous shape never moves and the current
//! keeps its shape, size and direction; free coordinates come from the
//! performance seed. A joint that the shapes cannot satisfy is reported and
//! only the relation is omitted.

use crate::planning::Bounds;
use crate::types::{Point, Seed};
use inku_score::{Primitive, RelationType};

/// The share of the current shape's bounds that must overlap the previous one.
const OVERLAP_ACCEPTED: (f64, f64) = (0.25, 0.75);
/// The share the performance chooses from, inside the accepted range.
const OVERLAP_CHOSEN: (f64, f64) = (1.0 / 3.0, 2.0 / 3.0);
const EPSILON: f64 = 1e-9;

fn width(bounds: Bounds) -> f64 {
    bounds.max.x - bounds.min.x
}

fn height(bounds: Bounds) -> f64 {
    bounds.max.y - bounds.min.y
}

fn moved(bounds: Bounds, delta: Point) -> Bounds {
    Bounds {
        min: Point::new(bounds.min.x + delta.x, bounds.min.y + delta.y),
        max: Point::new(bounds.max.x + delta.x, bounds.max.y + delta.y),
    }
}

fn overlap_share(own: Bounds, prior: Bounds) -> f64 {
    let area = width(own) * height(own);
    if area <= EPSILON {
        return 0.0;
    }
    let w = own.max.x.min(prior.max.x) - own.min.x.max(prior.min.x);
    let h = own.max.y.min(prior.max.y) - own.min.y.max(prior.min.y);
    if w <= 0.0 || h <= 0.0 {
        return 0.0;
    }
    w * h / area
}

/// Whether crossing goes across the height of the previous shape: across its
/// thinner direction, or along the current shape's longer direction when the
/// previous shape is as wide as tall.
fn crosses_vertically(own: Bounds, prior: Bounds) -> bool {
    let (wide, tall) = (width(prior), height(prior));
    if (wide - tall).abs() <= EPSILON {
        height(own) > width(own)
    } else {
        wide > tall
    }
}

/// The rectangle a shape inside the previous one must stay in: the bounds of
/// a square, and the bounds shrunk about their center by 1/√2 for the other
/// closed shapes (the largest rectangle inside an ellipse). Open shapes and
/// points hold nothing.
#[must_use]
pub(crate) fn inside_region(prior_primitive: Primitive, prior: Bounds) -> Option<Bounds> {
    let factor = match prior_primitive {
        Primitive::Square => 1.0,
        Primitive::Circle
        | Primitive::Ellipse
        | Primitive::Triangle
        | Primitive::Polygon
        | Primitive::Cloudform => std::f64::consts::FRAC_1_SQRT_2,
        Primitive::Line | Primitive::Arc | Primitive::Point => return None,
    };
    let center = prior.center();
    let half = Point::new(width(prior) * factor / 2.0, height(prior) * factor / 2.0);
    Some(Bounds {
        min: Point::new(center.x - half.x, center.y - half.y),
        max: Point::new(center.x + half.x, center.y + half.y),
    })
}

/// Whether the current bounds, translated by `delta`, satisfy the joint.
#[must_use]
pub(crate) fn accepts(
    kind: RelationType,
    own: Bounds,
    prior: Bounds,
    inside: Option<Bounds>,
    delta: Point,
) -> bool {
    let own = moved(own, delta);
    let center = own.center();
    match kind {
        RelationType::RestingOn => {
            (own.max.y - prior.min.y).abs() <= 1e-6
                && center.x >= prior.min.x - EPSILON
                && center.x <= prior.max.x + EPSILON
        }
        RelationType::Inside => inside.is_some_and(|region| {
            own.min.x >= region.min.x - 1e-6
                && own.min.y >= region.min.y - 1e-6
                && own.max.x <= region.max.x + 1e-6
                && own.max.y <= region.max.y + 1e-6
        }),
        RelationType::Overlapping => {
            let share = overlap_share(own, prior);
            share >= OVERLAP_ACCEPTED.0 - 1e-6 && share <= OVERLAP_ACCEPTED.1 + 1e-6
        }
        RelationType::Crossing => {
            if !crosses_vertically(own, prior) {
                own.min.x < prior.min.x
                    && own.max.x > prior.max.x
                    && center.y >= prior.min.y - EPSILON
                    && center.y <= prior.max.y + EPSILON
            } else {
                own.min.y < prior.min.y
                    && own.max.y > prior.max.y
                    && center.x >= prior.min.x - EPSILON
                    && center.x <= prior.max.x + EPSILON
            }
        }
        _ => false,
    }
}

/// The translation the performance prefers for the joint, or `None` when the
/// shapes cannot satisfy it.
#[must_use]
pub(crate) fn preferred(
    kind: RelationType,
    own: Bounds,
    prior: Bounds,
    prior_primitive: Primitive,
    seed: Seed,
    ordinal: usize,
) -> Option<Point> {
    let draw = |label: &str| crate::determinism::hash01(ordinal as i64, seed, label);
    let center = own.center();
    let target = match kind {
        RelationType::RestingOn => {
            if prior_primitive == Primitive::Point {
                return None;
            }
            let x = if width(own) <= width(prior) {
                prior.min.x
                    + width(own) / 2.0
                    + draw("resting-on-position") * (width(prior) - width(own))
            } else {
                prior.center().x
            };
            Point::new(x, prior.min.y - height(own) / 2.0)
        }
        RelationType::Inside => {
            let region = inside_region(prior_primitive, prior)?;
            if width(own) > width(region) + EPSILON || height(own) > height(region) + EPSILON {
                return None;
            }
            let free = Point::new(
                (width(region) - width(own)).max(0.0),
                (height(region) - height(own)).max(0.0),
            );
            Point::new(
                region.min.x + width(own) / 2.0 + draw("inside-x") * free.x,
                region.min.y + height(own) / 2.0 + draw("inside-y") * free.y,
            )
        }
        RelationType::Overlapping => {
            if prior_primitive == Primitive::Point {
                return None;
            }
            let share =
                OVERLAP_CHOSEN.0 + draw("overlap-share") * (OVERLAP_CHOSEN.1 - OVERLAP_CHOSEN.0);
            let angle = std::f64::consts::TAU * draw("overlap-angle");
            let direction = Point::new(angle.cos(), angle.sin());
            let at = |distance: f64| {
                let point = Point::new(
                    prior.center().x + direction.x * distance,
                    prior.center().y + direction.y * distance,
                );
                overlap_share(
                    moved(own, Point::new(point.x - center.x, point.y - center.y)),
                    prior,
                )
            };
            if at(0.0) < share {
                return None;
            }
            // The share never grows as the center moves away along one ray.
            let (mut near, mut far) =
                (0.0, width(own) + height(own) + width(prior) + height(prior));
            for _ in 0..64 {
                let middle = (near + far) / 2.0;
                if at(middle) >= share {
                    near = middle;
                } else {
                    far = middle;
                }
            }
            Point::new(
                prior.center().x + direction.x * near,
                prior.center().y + direction.y * near,
            )
        }
        RelationType::Crossing => {
            let across = draw("crossing-across");
            let along = draw("crossing-along") - 0.5;
            if !crosses_vertically(own, prior) {
                if width(own) <= width(prior) + EPSILON {
                    return None;
                }
                Point::new(
                    prior.center().x + along * (width(own) - width(prior)) / 2.0,
                    prior.min.y + across * height(prior),
                )
            } else {
                if height(own) <= height(prior) + EPSILON {
                    return None;
                }
                Point::new(
                    prior.min.x + across * width(prior),
                    prior.center().y + along * (height(own) - height(prior)) / 2.0,
                )
            }
        }
        _ => return None,
    };
    let delta = Point::new(target.x - center.x, target.y - center.y);
    (delta.x.is_finite() && delta.y.is_finite()).then_some(delta)
}

/// The point of a closed outline (consecutive points, closing back to the
/// first) nearest to `from`.
#[must_use]
pub(crate) fn nearest_on_outline(outline: &[Point], from: Point) -> Option<Point> {
    let mut best: Option<(f64, Point)> = None;
    for (index, &start) in outline.iter().enumerate() {
        let end = outline[(index + 1) % outline.len()];
        let segment = Point::new(end.x - start.x, end.y - start.y);
        let length = segment.x * segment.x + segment.y * segment.y;
        let t = if length <= EPSILON {
            0.0
        } else {
            (((from.x - start.x) * segment.x + (from.y - start.y) * segment.y) / length)
                .clamp(0.0, 1.0)
        };
        let point = Point::new(start.x + segment.x * t, start.y + segment.y * t);
        let distance = (point.x - from.x).hypot(point.y - from.y);
        if best.is_none_or(|(nearest, _)| distance < nearest) {
            best = Some((distance, point));
        }
    }
    best.map(|(_, point)| point)
        .filter(|point| point.x.is_finite() && point.y.is_finite())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bounds(x0: f64, y0: f64, x1: f64, y1: f64) -> Bounds {
        Bounds {
            min: Point::new(x0, y0),
            max: Point::new(x1, y1),
        }
    }

    #[test]
    fn every_joint_accepts_its_preferred_translation_for_several_seeds() {
        let prior = bounds(0.3, 0.4, 0.7, 0.6);
        let own = bounds(0.05, 0.05, 0.15, 0.1);
        let tall = bounds(0.0, 0.0, 0.05, 0.6);
        for seed in [1_i128, 7, 42] {
            for (kind, own) in [
                (RelationType::RestingOn, own),
                (RelationType::Inside, own),
                (RelationType::Overlapping, own),
                (RelationType::Crossing, tall),
            ] {
                let primitive = Primitive::Ellipse;
                let delta = preferred(kind, own, prior, primitive, seed, 0)
                    .unwrap_or_else(|| panic!("{kind:?} seed {seed}"));
                assert!(
                    accepts(kind, own, prior, inside_region(primitive, prior), delta),
                    "{kind:?} seed {seed}"
                );
            }
        }
    }

    #[test]
    fn joints_the_shapes_cannot_satisfy_have_no_translation() {
        let prior = bounds(0.4, 0.4, 0.6, 0.6);
        let large = bounds(0.0, 0.0, 0.5, 0.5);
        let short = bounds(0.0, 0.0, 0.1, 0.02);
        assert!(preferred(RelationType::Inside, large, prior, Primitive::Square, 1, 0).is_none());
        assert!(preferred(RelationType::Inside, short, prior, Primitive::Line, 1, 0).is_none());
        assert!(
            preferred(
                RelationType::Crossing,
                short,
                prior,
                Primitive::Square,
                1,
                0
            )
            .is_none()
        );
        assert!(
            preferred(
                RelationType::RestingOn,
                short,
                prior,
                Primitive::Point,
                1,
                0
            )
            .is_none()
        );
    }

    #[test]
    fn crossing_goes_across_the_thinner_direction_of_the_previous_shape() {
        // A wide shape crosses a horizontal line from above to below, and a
        // tall shape crosses a vertical line from left to right.
        let wide = bounds(0.0, 0.0, 0.3, 0.1);
        let horizontal = bounds(0.1, 0.5, 0.9, 0.5);
        let tall = bounds(0.0, 0.0, 0.1, 0.3);
        let vertical = bounds(0.5, 0.1, 0.5, 0.9);
        for seed in [1_i128, 7, 42] {
            let delta = preferred(
                RelationType::Crossing,
                wide,
                horizontal,
                Primitive::Line,
                seed,
                0,
            )
            .unwrap_or_else(|| panic!("horizontal seed {seed}"));
            assert!(accepts(
                RelationType::Crossing,
                wide,
                horizontal,
                None,
                delta
            ));
            let placed = moved(wide, delta);
            assert!(placed.min.y < 0.5 && placed.max.y > 0.5, "{placed:?}");
            let delta = preferred(
                RelationType::Crossing,
                tall,
                vertical,
                Primitive::Line,
                seed,
                0,
            )
            .unwrap_or_else(|| panic!("vertical seed {seed}"));
            assert!(accepts(RelationType::Crossing, tall, vertical, None, delta));
            let placed = moved(tall, delta);
            assert!(placed.min.x < 0.5 && placed.max.x > 0.5, "{placed:?}");
        }
    }

    #[test]
    fn nearest_outline_point_lies_on_the_closed_outline() {
        let square = [
            Point::new(0.0, 0.0),
            Point::new(1.0, 0.0),
            Point::new(1.0, 1.0),
            Point::new(0.0, 1.0),
        ];
        let point = nearest_on_outline(&square, Point::new(0.5, -0.3)).expect("point");
        assert!((point.x - 0.5).abs() < 1e-12 && point.y.abs() < 1e-12);
        let point = nearest_on_outline(&square, Point::new(-0.2, 0.4)).expect("point");
        assert!(point.x.abs() < 1e-12 && (point.y - 0.4).abs() < 1e-12);
    }
}
