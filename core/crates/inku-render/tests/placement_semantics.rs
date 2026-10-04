use inku_render::placement::{
    ClusterPlacement, cells_centers, clustered_position, path_position, region_in_short_side_units,
    rhythm_parameter, scatter_position,
};
use inku_render::types::{ArrangementPath, CanvasSize, Density, Point, RhythmSpacing};

#[test]
fn placement_is_deterministic_and_bounded() {
    let first = scatter_position(3, -17, 0.1);
    assert_eq!(first, scatter_position(3, -17, 0.1));
    assert!((0.1..=0.9).contains(&first.x));
    assert!((0.1..=0.9).contains(&first.y));
    assert_eq!(rhythm_parameter(2, 5, 7, RhythmSpacing::None), 0.5);
    assert!(rhythm_parameter(2, 5, 7, RhythmSpacing::Accelerando) < 0.5);
}

#[test]
fn cross_axis_path_spread_uses_the_canvas_short_side() {
    let square = path_position(
        2,
        5,
        431,
        0.1,
        ArrangementPath::Wave,
        RhythmSpacing::Loose,
        Some(CanvasSize::new(1000.0, 1000.0)),
    );
    let pillar = path_position(
        2,
        5,
        431,
        0.1,
        ArrangementPath::Wave,
        RhythmSpacing::Loose,
        Some(CanvasSize::new(200.0, 1000.0)),
    );
    assert!((square.x - pillar.x).abs() < 1.0e-12);
    assert!((pillar.y - 0.5).abs() < (square.y - 0.5).abs());
}

#[test]
fn clusters_and_regions_preserve_normalized_bounds() {
    let point = clustered_position(ClusterPlacement {
        index: 11,
        count: 24,
        seed: 99,
        margin: 0.08,
        path: ArrangementPath::Diagonal,
        cluster_count: 4,
        density: Density::High,
        preserve_space: true,
        rhythm_spacing: RhythmSpacing::Syncopated,
        canvas: Some(CanvasSize::new(1000.0, 400.0)),
    });
    assert!((0.0..=1.0).contains(&point.x));
    assert!((0.0..=1.0).contains(&point.y));
    assert_eq!(
        region_in_short_side_units([0.6, 0.18, 0.82, 0.4], None),
        [0.6, 0.18, 0.82, 0.4]
    );
    let region =
        region_in_short_side_units([0.6, 0.18, 0.82, 0.4], Some(CanvasSize::new(200.0, 1000.0)));
    assert!((region[0] - 0.6).abs() < 1.0e-12);
    assert!((region[2] - 0.82).abs() < 1.0e-12);
    assert!(region[3] - region[1] < 0.22);
}

/// Copies of `copy` at `centers` stay inside the domain from the origin, and
/// no two of them overlap.
fn assert_apart_inside(centers: &[Point], copy: Point, domain: Point) {
    let epsilon = 1.0e-9;
    for (index, center) in centers.iter().enumerate() {
        assert!(
            center.x - copy.x / 2.0 >= -epsilon && center.x + copy.x / 2.0 <= domain.x + epsilon
        );
        assert!(
            center.y - copy.y / 2.0 >= -epsilon && center.y + copy.y / 2.0 <= domain.y + epsilon
        );
        for other in &centers[..index] {
            assert!(
                (center.x - other.x).abs() >= copy.x - epsilon
                    || (center.y - other.y).abs() >= copy.y - epsilon,
                "{center:?} overlaps {other:?}"
            );
        }
    }
}

#[test]
fn cells_give_each_copy_its_own_cell_until_every_cell_holds_one() {
    // A maple leaf is about 0.305 wide and 0.47 tall: a square canvas holds
    // three columns and two rows of it.
    let leaf = Point::new(0.305, 0.47);
    let square = Point::new(1.0, 1.0);
    for count in 2..=6 {
        for seed in [0, 7, -31] {
            let centers = cells_centers(square, Point::new(0.0, 0.0), leaf, count, seed);
            assert_eq!(centers.len(), count);
            assert_apart_inside(&centers, leaf, square);
            assert_eq!(
                centers,
                cells_centers(square, Point::new(0.0, 0.0), leaf, count, seed)
            );
        }
    }
    let six = cells_centers(square, Point::new(0.0, 0.0), leaf, 6, 7);
    let columns = |centers: &[Point]| {
        let mut cells = centers
            .iter()
            .map(|center| {
                (
                    (center.x * 3.0).floor() as i32,
                    (center.y * 2.0).floor() as i32,
                )
            })
            .collect::<Vec<_>>();
        cells.sort_unstable();
        cells
    };
    assert_eq!(
        columns(&six),
        [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)]
    );
    // Two copies have two columns and two rows, each cell half the canvas: a
    // copy shifts at most half the room its cell leaves (0.195 by 0.03).
    let two = cells_centers(square, Point::new(0.0, 0.0), leaf, 2, 7);
    let near = |value: f64, centers: [f64; 2], room: f64| {
        centers
            .iter()
            .any(|center| (value - center).abs() <= room / 2.0 + 1.0e-9)
    };
    assert!(two.iter().all(|center| near(center.x, [0.25, 0.75], 0.195)
        && near(center.y, [0.25, 0.75], 0.03)));
    // Past the six cells, the seventh and eighth copies take the first cells again.
    let eight = cells_centers(square, Point::new(0.0, 0.0), leaf, 8, 7);
    assert_apart_inside(&eight[..6], leaf, square);
    for (later, first) in eight[6..].iter().zip(&eight[..2]) {
        assert_eq!(
            ((later.x * 3.0).floor(), (later.y * 2.0).floor()),
            ((first.x * 3.0).floor(), (first.y * 2.0).floor())
        );
    }
    // The seed chooses the cells; a wide canvas has more columns, from its origin.
    assert_ne!(six, cells_centers(square, Point::new(0.0, 0.0), leaf, 6, 8));
    let wide = Point::new(1.5, 1.0);
    let shifted = cells_centers(wide, Point::new(0.25, 0.0), leaf, 8, 7);
    let at_origin = cells_centers(wide, Point::new(0.0, 0.0), leaf, 8, 7);
    assert_apart_inside(&at_origin, leaf, wide);
    for (shifted, at_origin) in shifted.iter().zip(&at_origin) {
        assert!((shifted.x - at_origin.x - 0.25).abs() < 1.0e-12 && shifted.y == at_origin.y);
    }
    // Copies with no size, and copies larger than the canvas, still get one center each.
    assert_eq!(
        cells_centers(square, Point::new(0.0, 0.0), Point::new(0.0, 0.0), 5, 7).len(),
        5
    );
    assert_eq!(
        cells_centers(square, Point::new(0.0, 0.0), Point::new(2.0, 2.0), 3, 7).len(),
        3
    );
    assert!(cells_centers(square, Point::new(0.0, 0.0), leaf, 0, 7).is_empty());
}
