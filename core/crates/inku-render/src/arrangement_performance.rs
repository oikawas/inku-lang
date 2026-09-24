//! Performance of an arrangement's spacing fields on the typed Score 0.10 path.
//!
//! The typed recipe fixes where a group lives (its anchor region and extent).
//! These fields shape how members sit inside that extent: clustering by
//! density, rhythm along a line, positional jitter, fade, and the tool's own
//! member-to-member hand. Every choice is bound to the placement seed and reads
//! only Score fields; nothing depends on source words or subjects.

use crate::determinism::hash01;
use crate::placement::rhythm_parameter;
use crate::types::{
    Arrangement, CanvasSize, Density, Instruction, Point, ResolvedPlacementRecipe, RhythmSpacing,
    Seed,
};

fn pull_for(density: Density) -> f64 {
    match density {
        Density::Low => 0.35,
        Density::None | Density::Medium => 0.6,
        Density::High => 0.82,
    }
}

fn is_line_recipe(recipe: &ResolvedPlacementRecipe) -> bool {
    matches!(
        recipe,
        ResolvedPlacementRecipe::HorizontalLine { .. }
            | ResolvedPlacementRecipe::VerticalLine { .. }
            | ResolvedPlacementRecipe::DiagonalLine { .. }
    )
}

/// Reshape recipe centers (canvas-short-edge units) by the arrangement's spacing fields.
#[must_use]
pub(crate) fn shape_centers(
    arrangement: &Arrangement,
    recipe: &ResolvedPlacementRecipe,
    mut centers: Vec<Point>,
    domain: Point,
    seed: Seed,
) -> Vec<Point> {
    let count = centers.len();
    if count < 2 || matches!(recipe, ResolvedPlacementRecipe::Grid { .. }) {
        return centers;
    }
    if matches!(recipe, ResolvedPlacementRecipe::Place) {
        // Several marks placed at one spot form a bundle around it rather
        // than an exact overlay that reads as a single mark.
        let radius = (0.025 * (count as f64).sqrt()).min(0.18);
        for (index, center) in centers.iter_mut().enumerate() {
            let angle = hash01(index as i64, seed, "place-bundle-angle") * std::f64::consts::TAU;
            let distance = radius * hash01(index as i64, seed, "place-bundle-distance").sqrt();
            center.x += distance * angle.cos();
            center.y += distance * angle.sin();
        }
    }
    if is_line_recipe(recipe) && arrangement.rhythm_spacing != RhythmSpacing::None {
        let first = centers[0];
        let last = centers[count - 1];
        for (index, center) in centers.iter_mut().enumerate() {
            let t = rhythm_parameter(index, count, seed, arrangement.rhythm_spacing);
            *center = Point::new(
                first.x + (last.x - first.x) * t,
                first.y + (last.y - first.y) * t,
            );
        }
    }
    if matches!(
        recipe,
        ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation
    ) {
        let clusters = match (arrangement.cluster_count, arrangement.density) {
            (Some(k), _) if k > 0 => k as usize,
            (_, Density::None) => 0,
            _ => count.div_ceil(10).max(2),
        };
        if clusters > 0 && count > clusters {
            let pull = pull_for(arrangement.density);
            let seeds: Vec<Point> = centers[..clusters].to_vec();
            for (index, center) in centers.iter_mut().enumerate().skip(clusters) {
                let target = seeds[index % clusters];
                *center = Point::new(
                    center.x + (target.x - center.x) * pull,
                    center.y + (target.y - center.y) * pull,
                );
            }
        }
    }
    if arrangement.jitter > 0.0 {
        let cell = if is_line_recipe(recipe) {
            (domain.x.max(domain.y) / count as f64).max(1.0e-6)
        } else {
            (domain.x * domain.y / count as f64).sqrt()
        };
        let amount = arrangement.jitter.min(1.0) * 2.0 * cell;
        for (index, center) in centers.iter_mut().enumerate() {
            center.x += (hash01(index as i64, seed, "perform-jitter-x") - 0.5) * amount;
            center.y += (hash01(index as i64, seed, "perform-jitter-y") - 0.5) * amount;
        }
    }
    centers
}

/// Apply fade and the tool's member hand to one group's performed members.
pub(crate) fn finish_members(
    members: &mut [Instruction],
    arrangement: &Arrangement,
    recipe: &ResolvedPlacementRecipe,
    seed: Seed,
    canvas: Option<CanvasSize>,
) {
    if members.len() < 2 || matches!(recipe, ResolvedPlacementRecipe::Grid { .. }) {
        return;
    }
    let finished =
        crate::group::finish_members_in_place(members.to_vec(), arrangement, seed, canvas);
    members.clone_from_slice(&finished);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{Fade, Layout};

    fn arrangement(density: Density, jitter: f64, rhythm: RhythmSpacing) -> Arrangement {
        Arrangement {
            count: 12,
            group_size: 1,
            layout: Layout::Horizontal,
            rows: None,
            cols: None,
            jitter,
            path: crate::types::ArrangementPath::None,
            color_cycle: Vec::new(),
            margin: 0.0,
            center: None,
            radius: None,
            density,
            cluster_count: None,
            fade: Fade::None,
            preserve_space: false,
            rhythm_spacing: rhythm,
            resolved: None,
        }
    }

    fn grid_points(count: usize) -> Vec<Point> {
        (0..count)
            .map(|index| Point::new(0.1 + 0.07 * index as f64, 0.2 + 0.05 * (index % 5) as f64))
            .collect()
    }

    #[test]
    fn unspecified_spacing_fields_leave_scatter_and_line_centers_unchanged() {
        let plain = arrangement(Density::None, 0.0, RhythmSpacing::None);
        let scatter = ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation;
        let line = ResolvedPlacementRecipe::HorizontalLine { cell_width: 0.07 };
        for recipe in [scatter, line] {
            let centers = grid_points(12);
            assert_eq!(
                shape_centers(&plain, &recipe, centers.clone(), Point::new(1.0, 1.0), 9),
                centers
            );
        }
    }

    #[test]
    fn several_marks_at_one_place_form_a_seeded_bundle() {
        let plain = arrangement(Density::None, 0.0, RhythmSpacing::None);
        let origin = vec![Point::new(0.5, 0.5); 6];
        let first = shape_centers(
            &plain,
            &ResolvedPlacementRecipe::Place,
            origin.clone(),
            Point::new(1.0, 1.0),
            3,
        );
        let again = shape_centers(
            &plain,
            &ResolvedPlacementRecipe::Place,
            origin,
            Point::new(1.0, 1.0),
            3,
        );
        assert_eq!(first, again);
        for (index, a) in first.iter().enumerate() {
            assert!(a.x.hypot(a.y) > 0.0);
            assert!((a.x - 0.5).hypot(a.y - 0.5) <= 0.18 + 1.0e-12);
            for b in &first[index + 1..] {
                assert!((a.x - b.x).hypot(a.y - b.y) > 1.0e-9);
            }
        }
    }

    #[test]
    fn denser_scatter_pulls_members_closer_to_their_clusters() {
        let scatter = ResolvedPlacementRecipe::ScatterUniformWithCentroidTranslation;
        let spread = |density| {
            let centers = shape_centers(
                &arrangement(density, 0.0, RhythmSpacing::None),
                &scatter,
                grid_points(12),
                Point::new(1.0, 1.0),
                5,
            );
            let clusters = 12_usize.div_ceil(10).max(2);
            centers
                .iter()
                .enumerate()
                .skip(clusters)
                .map(|(index, point)| {
                    let seed = centers[index % clusters];
                    (point.x - seed.x).hypot(point.y - seed.y)
                })
                .sum::<f64>()
        };
        assert!(spread(Density::High) < spread(Density::Low));
    }
}
