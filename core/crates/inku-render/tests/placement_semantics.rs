use inku_render::placement::{
    ClusterPlacement, clustered_position, path_position, region_in_short_side_units,
    rhythm_parameter, scatter_position,
};
use inku_render::types::{ArrangementPath, CanvasSize, Density, RhythmSpacing};

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
