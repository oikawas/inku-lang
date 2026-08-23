use inku_render::arc::{
    arc_from_endpoints_and_sagitta, arc_point, minor_arc_delta, signed_arc_sagitta,
};
use inku_render::types::Point;

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
