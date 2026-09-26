use inku_render::arc::{
    arc_from_endpoints_and_sagitta, arc_point, minor_arc_delta, signed_arc_sagitta,
};
use inku_render::types::{
    CRESCENT_REFERENCE_ASPECT_RATIO, CRESCENT_REFERENCE_HEIGHT, CRESCENT_REFERENCE_WIDTH, Point,
    crescent_contour_bounds, crescent_reference_aspect_ratio,
};

#[test]
fn signed_minor_sweep_uses_python_modulo_semantics() {
    assert_eq!(minor_arc_delta(350.0, 10.0), 20.0);
    assert_eq!(minor_arc_delta(10.0, 350.0), -20.0);
    assert_eq!(minor_arc_delta(0.0, 180.0), -180.0);
}

#[test]
fn endpoint_reconstruction_preserves_signed_sagitta() {
    let start = Point::new(0.1, 0.3);
    let end = Point::new(0.9, 0.3);
    let arc = arc_from_endpoints_and_sagitta(start, end, 0.2).unwrap();
    let rebuilt_start = arc_point(arc.center, arc.radius, arc.angle_start);
    let rebuilt_end = arc_point(arc.center, arc.radius, arc.angle_end);
    assert!((rebuilt_start.x - start.x).abs() < 1.0e-12);
    assert!((rebuilt_start.y - start.y).abs() < 1.0e-12);
    assert!((rebuilt_end.x - end.x).abs() < 1.0e-12);
    assert!((rebuilt_end.y - end.y).abs() < 1.0e-12);
    assert!((signed_arc_sagitta(arc).unwrap() - 0.2).abs() < 1.0e-12);
}

#[test]
fn crescent_uses_the_actual_saijiki_cubic_bbox() {
    assert!((crescent_reference_aspect_ratio() - CRESCENT_REFERENCE_ASPECT_RATIO).abs() < 1.0e-15);
    assert!((CRESCENT_REFERENCE_ASPECT_RATIO - 0.777_434_378_277_882).abs() < 1.0e-15);
    const {
        assert!(CRESCENT_REFERENCE_WIDTH > 47.25);
        assert!(CRESCENT_REFERENCE_HEIGHT > 60.78);
    }

    let center = Point::new(0.5, 0.4);
    let size = Point::new(0.2, 0.2 / CRESCENT_REFERENCE_ASPECT_RATIO);
    let (min, max) = crescent_contour_bounds(center, size, 0.0);
    assert!((min.x - (center.x - size.x / 2.0)).abs() < 1.0e-12);
    assert!((min.y - (center.y - size.y / 2.0)).abs() < 1.0e-12);
    assert!((max.x - (center.x + size.x / 2.0)).abs() < 1.0e-12);
    assert!((max.y - (center.y + size.y / 2.0)).abs() < 1.0e-12);
}
