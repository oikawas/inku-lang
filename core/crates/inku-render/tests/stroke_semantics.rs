use std::collections::BTreeSet;

use inku_render::stroke::{
    BandHand, ContourStrokeRequest, StrokeRequest, StrokeResult, StrokeTerminal, grammar,
    grid_point, synthesize_contour, synthesize_stroke, synthesize_stroke_by,
};
use inku_render::support::{DEFAULT_SUPPORT, support_for_ground, support_with_mark_word};
use inku_render::types::{GroundMaterial, Point, SurfaceTexture, Weight};

#[test]
fn support_resolution_is_typed_and_capped() {
    let washi = support_for_ground(GroundMaterial::Washi);
    assert_eq!(washi.absorb, 2.2);
    assert_eq!(washi.tooth, 0.5);
    let bleeding = support_with_mark_word(washi, SurfaceTexture::Bleed);
    assert_eq!(bleeding.absorb, 3.0);
    assert_eq!(bleeding.tooth, 0.5);
    let grain = support_with_mark_word(washi, SurfaceTexture::Grain);
    assert_eq!(grain.absorb, 2.2);
    assert_eq!(grain.tooth, 1.0);
}

#[test]
fn machine_grammar_keeps_exact_group_repetition() {
    let computer = grammar(Weight::Computer);
    assert!(computer.periodic);
    assert_eq!(computer.group_hand, 0.0);
    assert_eq!(computer.group_rotation, 0.0);
    assert_eq!(grammar(Weight::Pencil).group_hand, 0.35);
}

#[test]
fn machine_samples_are_seed_independent_and_endpoints_are_pinned() {
    let args = (Point::new(0.0, 0.0), Point::new(100.0, 20.0));
    let request = |seed| StrokeRequest {
        start: args.0,
        end: args.1,
        base_width: 2.0,
        weight: Weight::Computer,
        seed,
        sample_count: 17,
        wild: false,
        grid_step: 3.0,
        support: DEFAULT_SUPPORT,
    };
    let first = synthesize_stroke(request(-7));
    let second = synthesize_stroke(request(99));
    assert_eq!(first.samples, second.samples);
    assert_eq!(first.outline, second.outline);
    assert_eq!(first.samples[0].point, args.0);
    assert_eq!(first.samples.last().unwrap().point, args.1);
    assert_eq!(first.samples.first().unwrap().residual, 0.0);
    assert_eq!(first.samples.last().unwrap().residual, 0.0);
    assert!(first.samples.iter().all(|sample| sample.event.is_none()));
}

#[test]
fn a_band_hand_sways_by_its_share_and_draws_only_the_octaves_its_samples_can() {
    let request = StrokeRequest {
        start: Point::new(0.0, 0.0),
        end: Point::new(800.0, 0.0),
        base_width: 150.0,
        weight: Weight::BrushThick,
        seed: 41,
        sample_count: 41,
        wild: false,
        grid_step: 0.0,
        support: DEFAULT_SUPPORT,
    };
    let plain = synthesize_stroke(request);
    assert_eq!(synthesize_stroke_by(request, BandHand::ROUND), plain);
    // A band's sway and kicks follow a share of its width (render engine 92).
    let third = synthesize_stroke_by(
        request,
        BandHand {
            sway_share: 1.0 / 3.0,
            smooth: false,
        },
    );
    for (round, band) in plain.samples.iter().zip(&third.samples) {
        assert!(
            (band.lateral - round.lateral / 3.0).abs() < 1.0e-9,
            "{} {}",
            round.lateral,
            band.lateral
        );
        assert_eq!(band.energy, round.energy);
    }
    // Without the octaves finer than its samples, the energy no longer turns
    // at every sample.
    let smooth = synthesize_stroke_by(
        request,
        BandHand {
            sway_share: 1.0,
            smooth: true,
        },
    );
    let turning = |result: &StrokeResult| {
        result
            .samples
            .windows(3)
            .map(|window| (window[0].energy - 2.0 * window[1].energy + window[2].energy).abs())
            .sum::<f64>()
    };
    assert!(turning(&smooth) < 0.5 * turning(&plain));
}

#[test]
fn stroke_grid_uses_python_ties_to_even() {
    assert_eq!(grid_point(2.5, 1.0), 2.0);
    assert_eq!(grid_point(3.5, 1.0), 4.0);
    assert_eq!(grid_point(-2.5, 1.0), -2.0);
}

#[test]
fn contour_pins_endpoints_and_declared_anchors() {
    let points = [
        Point::new(0.0, 0.0),
        Point::new(20.0, 5.0),
        Point::new(40.0, 0.0),
    ];
    let anchors = BTreeSet::from([1]);
    let result = synthesize_contour(ContourStrokeRequest {
        centerline: &points,
        base_width: 2.0,
        weight: Weight::Pencil,
        seed: 431,
        closed: false,
        anchors: &anchors,
        grid_step: 0.0,
        wild: true,
        support: DEFAULT_SUPPORT,
        terminal: StrokeTerminal::Taper,
    });
    assert_eq!(result.samples[0].point, points[0]);
    assert_eq!(result.samples[1].point, points[1]);
    assert_eq!(result.samples[2].point, points[2]);
    assert_eq!(result.left.len(), points.len());
    assert_eq!(result.right.len(), points.len());
}

#[test]
fn closed_contour_corrects_the_seam_without_opening_the_band() {
    let points = [
        Point::new(0.0, 0.0),
        Point::new(10.0, 0.0),
        Point::new(10.0, 10.0),
        Point::new(0.0, 10.0),
    ];
    let anchors = BTreeSet::new();
    let result = synthesize_contour(ContourStrokeRequest {
        centerline: &points,
        base_width: 2.0,
        weight: Weight::BrushThin,
        seed: 17,
        closed: true,
        anchors: &anchors,
        grid_step: 0.0,
        wild: true,
        support: support_for_ground(GroundMaterial::Canvas),
        terminal: StrokeTerminal::Loaded,
    });
    let first_offset = Point::new(
        result.samples[0].point.x - points[0].x,
        result.samples[0].point.y - points[0].y,
    );
    let last = result.samples.len() - 1;
    let last_offset = Point::new(
        result.samples[last].point.x - points[last].x,
        result.samples[last].point.y - points[last].y,
    );
    assert!((first_offset.x - last_offset.x).abs() < 1.0e-12);
    assert!((first_offset.y - last_offset.y).abs() < 1.0e-12);
    assert!((result.samples[0].width - result.samples[last].width).abs() < 1.0e-12);
    assert!(result.left.iter().all(|point| point.x.is_finite()));
    assert!(result.right.iter().all(|point| point.x.is_finite()));
}
