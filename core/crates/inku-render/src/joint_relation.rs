//! Joint relations of Score 0.20.0: resting on, inside, overlapping and
//! crossing the previous shape (SPEC §14.4).
//!
//! Each is placed from the performed bounds of the current and the previous
//! shape by translation only. The previous shape never moves and the current
//! keeps its shape, size and direction; free coordinates come from the
//! performance seed, from the part of the previous shape on the paper when the
//! current shape fits there, and move the least that keeps the current shape
//! on the paper. A previous shape that a fill clips is held to by the part that
//! is seen. A joint that the shapes cannot satisfy is reported and only the
//! relation is omitted.

use crate::planning::Bounds;
use crate::types::{Point, Seed};
use inku_score::{Primitive, RelationType};

/// The share of the current shape's bounds that must overlap the previous one.
const OVERLAP_ACCEPTED: (f64, f64) = (0.25, 0.75);
/// The share the performance chooses from, inside the accepted range.
const OVERLAP_CHOSEN: (f64, f64) = (1.0 / 3.0, 2.0 / 3.0);
/// The directions overlapping tries, in equal steps of a full turn from the
/// seed's direction, when that direction leaves the current shape off the
/// paper.
const OVERLAP_TURNS: usize = 16;
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

/// The part of `bounds` within `area` (the paper, or the target a fill is
/// clipped to), when there is one.
#[must_use]
pub(crate) fn part_within(bounds: Bounds, area: Bounds) -> Option<Bounds> {
    let part = Bounds {
        min: Point::new(bounds.min.x.max(area.min.x), bounds.min.y.max(area.min.y)),
        max: Point::new(bounds.max.x.min(area.max.x), bounds.max.y.min(area.max.y)),
    };
    (part.min.x <= part.max.x && part.min.y <= part.max.y).then_some(part)
}

fn on_the_paper(point: Point, paper: Bounds) -> bool {
    point.x >= paper.min.x
        && point.x <= paper.max.x
        && point.y >= paper.min.y
        && point.y <= paper.max.y
}

fn lies_on_the_paper(bounds: Bounds, paper: Bounds) -> bool {
    bounds.min.x >= paper.min.x - EPSILON
        && bounds.min.y >= paper.min.y - EPSILON
        && bounds.max.x <= paper.max.x + EPSILON
        && bounds.max.y <= paper.max.y + EPSILON
}

/// A free coordinate of the current shape's center, moved the least so that
/// the shape (`half` its extent on that axis) lies on the paper's `span`,
/// within `allowed`, the range that keeps the joint. When no coordinate in
/// `allowed` keeps it on the paper, the one nearest to the paper. A coordinate
/// that already keeps the shape on the paper stays.
fn onto_paper(value: f64, half: f64, allowed: (f64, f64), span: (f64, f64)) -> f64 {
    if value - half >= span.0 - EPSILON && value + half <= span.1 + EPSILON {
        return value;
    }
    let (low, high) = (span.0 + half, span.1 - half);
    let fitted = if low <= high {
        value.clamp(low, high)
    } else {
        (span.0 + span.1) / 2.0
    };
    fitted.clamp(allowed.0, allowed.1.max(allowed.0))
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
        Primitive::Line | Primitive::Arc | Primitive::Point | Primitive::FreeLine => return None,
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
/// shapes cannot satisfy it. `prior` is the part of the previous shape that is
/// seen, and `inside` the rectangle a shape inside it must stay in.
///
/// The free coordinates (where along the previous shape the current one rests
/// or crosses, where inside it the current one goes) are drawn from the part
/// of the previous shape on the paper when the current shape fits there, and
/// from the whole previous shape otherwise. A resting or crossing position
/// that leaves the current shape off the paper then moves the least that keeps
/// it on the paper, within the range that keeps the joint. Overlapping keeps
/// the seed's direction unless it leaves the current shape off the paper; then
/// it takes the first other direction that keeps the shape on the paper, or
/// else the first that keeps its center there.
#[must_use]
#[allow(clippy::too_many_arguments)]
pub(crate) fn preferred(
    kind: RelationType,
    own: Bounds,
    prior: Bounds,
    inside: Option<Bounds>,
    prior_primitive: Primitive,
    paper: Bounds,
    seed: Seed,
    ordinal: usize,
) -> Option<Point> {
    let draw = |label: &str| crate::determinism::hash01(ordinal as i64, seed, label);
    let center = own.center();
    let (span_x, span_y) = ((paper.min.x, paper.max.x), (paper.min.y, paper.max.y));
    let target = match kind {
        RelationType::RestingOn => {
            if prior_primitive == Primitive::Point {
                return None;
            }
            let room = part_within(prior, paper)
                .filter(|room| width(own) <= width(*room))
                .unwrap_or(prior);
            let x = if width(own) <= width(room) {
                room.min.x
                    + width(own) / 2.0
                    + draw("resting-on-position") * (width(room) - width(own))
            } else {
                prior.center().x
            };
            Point::new(
                onto_paper(x, width(own) / 2.0, (prior.min.x, prior.max.x), span_x),
                prior.min.y - height(own) / 2.0,
            )
        }
        RelationType::Inside => {
            let region = inside?;
            if width(own) > width(region) + EPSILON || height(own) > height(region) + EPSILON {
                return None;
            }
            let room = part_within(region, paper)
                .filter(|room| {
                    width(own) <= width(*room) + EPSILON && height(own) <= height(*room) + EPSILON
                })
                .unwrap_or(region);
            let free = Point::new(
                (width(room) - width(own)).max(0.0),
                (height(room) - height(own)).max(0.0),
            );
            Point::new(
                room.min.x + width(own) / 2.0 + draw("inside-x") * free.x,
                room.min.y + height(own) / 2.0 + draw("inside-y") * free.y,
            )
        }
        RelationType::Overlapping => {
            if prior_primitive == Primitive::Point {
                return None;
            }
            let share =
                OVERLAP_CHOSEN.0 + draw("overlap-share") * (OVERLAP_CHOSEN.1 - OVERLAP_CHOSEN.0);
            let toward = |turn: f64| {
                let angle = std::f64::consts::TAU * (draw("overlap-angle") + turn);
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
            };
            let centered = moved(
                own,
                Point::new(prior.center().x - center.x, prior.center().y - center.y),
            );
            if overlap_share(centered, prior) < share {
                return None;
            }
            // The seed's direction first, then the other directions in turn.
            let points: Vec<Point> = (0..OVERLAP_TURNS)
                .map(|turn| toward(turn as f64 / OVERLAP_TURNS as f64))
                .collect();
            let lies = |point: Point| {
                lies_on_the_paper(
                    moved(own, Point::new(point.x - center.x, point.y - center.y)),
                    paper,
                )
            };
            points
                .iter()
                .copied()
                .find(|point| lies(*point))
                .or_else(|| {
                    points
                        .iter()
                        .copied()
                        .find(|point| on_the_paper(*point, paper))
                })
                .unwrap_or(points[0])
        }
        RelationType::Crossing => {
            let across = draw("crossing-across");
            let along = draw("crossing-along") - 0.5;
            let room = part_within(prior, paper).unwrap_or(prior);
            if !crosses_vertically(own, prior) {
                if width(own) <= width(prior) + EPSILON {
                    return None;
                }
                let (cx, reach) = (prior.center().x, (width(own) - width(prior)) / 4.0);
                Point::new(
                    onto_paper(
                        cx + along * (width(own) - width(prior)) / 2.0,
                        width(own) / 2.0,
                        (cx - reach, cx + reach),
                        span_x,
                    ),
                    onto_paper(
                        room.min.y + across * height(room),
                        height(own) / 2.0,
                        (room.min.y, room.max.y),
                        span_y,
                    ),
                )
            } else {
                if height(own) <= height(prior) + EPSILON {
                    return None;
                }
                let (cy, reach) = (prior.center().y, (height(own) - height(prior)) / 4.0);
                Point::new(
                    onto_paper(
                        room.min.x + across * width(room),
                        width(own) / 2.0,
                        (room.min.x, room.max.x),
                        span_x,
                    ),
                    onto_paper(
                        cy + along * (height(own) - height(prior)) / 2.0,
                        height(own) / 2.0,
                        (cy - reach, cy + reach),
                        span_y,
                    ),
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

    fn paper() -> Bounds {
        bounds(0.0, 0.0, 1.0, 1.0)
    }

    /// `preferred` with the inner rectangle the previous shape's primitive holds.
    fn place(
        kind: RelationType,
        own: Bounds,
        prior: Bounds,
        primitive: Primitive,
        paper: Bounds,
        seed: Seed,
        ordinal: usize,
    ) -> Option<Point> {
        preferred(
            kind,
            own,
            prior,
            inside_region(primitive, prior),
            primitive,
            paper,
            seed,
            ordinal,
        )
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
                let delta = place(kind, own, prior, primitive, paper(), seed, 0)
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
        assert!(
            place(
                RelationType::Inside,
                large,
                prior,
                Primitive::Square,
                paper(),
                1,
                0
            )
            .is_none()
        );
        assert!(
            place(
                RelationType::Inside,
                short,
                prior,
                Primitive::Line,
                paper(),
                1,
                0
            )
            .is_none()
        );
        assert!(
            place(
                RelationType::Crossing,
                short,
                prior,
                Primitive::Square,
                paper(),
                1,
                0
            )
            .is_none()
        );
        assert!(
            place(
                RelationType::RestingOn,
                short,
                prior,
                Primitive::Point,
                paper(),
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
            let delta = place(
                RelationType::Crossing,
                wide,
                horizontal,
                Primitive::Line,
                paper(),
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
            let delta = place(
                RelationType::Crossing,
                tall,
                vertical,
                Primitive::Line,
                paper(),
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
    fn a_previous_shape_on_the_paper_keeps_every_translation() {
        // The paper only narrows where the previous shape runs off it, or where
        // the current shape would leave it.
        let prior = bounds(0.3, 0.4, 0.7, 0.6);
        let small = bounds(0.05, 0.05, 0.15, 0.1);
        let tall = bounds(0.0, 0.0, 0.05, 0.6);
        let everywhere = bounds(-10.0, -10.0, 10.0, 10.0);
        for seed in 1_i128..=8 {
            for (kind, own) in [
                (RelationType::RestingOn, small),
                (RelationType::Inside, small),
                (RelationType::Overlapping, small),
                (RelationType::Crossing, tall),
            ] {
                let primitive = Primitive::Ellipse;
                assert_eq!(
                    place(kind, own, prior, primitive, paper(), seed, 0),
                    place(kind, own, prior, primitive, everywhere, seed, 0),
                    "{kind:?} seed {seed}"
                );
            }
        }
    }

    #[test]
    fn free_positions_come_from_the_part_of_the_previous_shape_on_the_paper() {
        let small = bounds(0.0, 0.0, 0.1, 0.1);
        // A square running off the right edge, and a track line running off it.
        let off_right = bounds(0.6, 0.4, 1.6, 0.8);
        let track = bounds(0.3, 0.65, 1.45, 0.65);
        let footprints = bounds(0.0, 0.0, 0.6, 0.5);
        let corner = bounds(0.85, 0.85, 1.2, 1.2);
        for seed in 1_i128..=8 {
            for kind in [RelationType::RestingOn, RelationType::Inside] {
                let delta = place(kind, small, off_right, Primitive::Square, paper(), seed, 0)
                    .unwrap_or_else(|| panic!("{kind:?} seed {seed}"));
                let placed = moved(small, delta);
                assert!(
                    placed.min.x >= 0.6 - 1e-9 && placed.max.x <= 1.0 + 1e-9,
                    "{kind:?} seed {seed} {placed:?}"
                );
                assert!(accepts(
                    kind,
                    small,
                    off_right,
                    inside_region(Primitive::Square, off_right),
                    delta
                ));
            }
            let delta = place(
                RelationType::Crossing,
                footprints,
                track,
                Primitive::Line,
                paper(),
                seed,
                0,
            )
            .unwrap_or_else(|| panic!("crossing seed {seed}"));
            let placed = moved(footprints, delta);
            let x = placed.center().x;
            assert!((0.3..=1.0).contains(&x), "crossing seed {seed} {placed:?}");
            assert!(placed.min.y < 0.65 && placed.max.y > 0.65);
            let delta = place(
                RelationType::Overlapping,
                small,
                corner,
                Primitive::Square,
                paper(),
                seed,
                0,
            )
            .unwrap_or_else(|| panic!("overlapping seed {seed}"));
            let center = moved(small, delta).center();
            assert!(
                center.x <= 1.0 && center.y <= 1.0,
                "overlapping seed {seed} {center:?}"
            );
            assert!(accepts(
                RelationType::Overlapping,
                small,
                corner,
                None,
                delta
            ));
        }
    }

    #[test]
    fn a_joined_shape_that_would_leave_the_paper_moves_the_least_onto_it() {
        // A group wider than the part on the paper of a square running off the
        // right edge, and footprints crossing a long track.
        let off_right = bounds(0.6, 0.6, 1.2, 0.8);
        let wide = bounds(0.0, 0.0, 0.5, 0.1);
        let track = bounds(0.3, 0.65, 1.45, 0.65);
        let footprints = bounds(0.0, 0.0, 0.6, 0.5);
        let mut at_the_edge = 0;
        for seed in 1_i128..=8 {
            let delta = place(
                RelationType::RestingOn,
                wide,
                off_right,
                Primitive::Square,
                paper(),
                seed,
                0,
            )
            .unwrap_or_else(|| panic!("resting seed {seed}"));
            let placed = moved(wide, delta);
            // Every seed's position on the square leaves the group off the
            // paper, so each moves to the right edge and no further.
            assert!(
                (placed.max.x - 1.0).abs() <= 1e-9,
                "resting seed {seed} {placed:?}"
            );
            assert!(accepts(
                RelationType::RestingOn,
                wide,
                off_right,
                None,
                delta
            ));
            let delta = place(
                RelationType::Crossing,
                footprints,
                track,
                Primitive::Line,
                paper(),
                seed,
                0,
            )
            .unwrap_or_else(|| panic!("crossing seed {seed}"));
            let placed = moved(footprints, delta);
            assert!(
                lies_on_the_paper(placed, paper()),
                "crossing seed {seed} {placed:?}"
            );
            assert!(accepts(
                RelationType::Crossing,
                footprints,
                track,
                None,
                delta
            ));
            if (placed.max.x - 1.0).abs() <= 1e-9 || (placed.max.y - 1.0).abs() <= 1e-9 {
                at_the_edge += 1;
            }
        }
        assert!(at_the_edge > 0, "no crossing seed needed the move");
    }

    #[test]
    fn overlapping_takes_a_direction_that_keeps_the_shape_on_the_paper() {
        let corner = bounds(0.6, 0.6, 1.0, 1.0);
        let small = bounds(0.0, 0.0, 0.2, 0.2);
        let everywhere = bounds(-10.0, -10.0, 10.0, 10.0);
        let mut turned = 0;
        for seed in 1_i128..=16 {
            let delta = place(
                RelationType::Overlapping,
                small,
                corner,
                Primitive::Square,
                paper(),
                seed,
                0,
            )
            .unwrap_or_else(|| panic!("seed {seed}"));
            let placed = moved(small, delta);
            assert!(lies_on_the_paper(placed, paper()), "seed {seed} {placed:?}");
            assert!(accepts(
                RelationType::Overlapping,
                small,
                corner,
                None,
                delta
            ));
            // Without a paper edge every seed keeps its own direction.
            let seeded = place(
                RelationType::Overlapping,
                small,
                corner,
                Primitive::Square,
                everywhere,
                seed,
                0,
            )
            .expect("seeded");
            if !lies_on_the_paper(moved(small, seeded), paper()) {
                turned += 1;
            }
        }
        assert!(
            turned > 0,
            "no seed's direction left the shape off the paper"
        );
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
