use inku_render::cloudform::{
    CloudformRequest, generate_cloudform_contour, polygon_self_intersects,
};
use inku_render::types::{Point, Weight};

#[test]
fn cloudform_is_bounded_seamless_and_deterministic() {
    let request = CloudformRequest {
        center: Point::new(0.5, 0.5),
        size: Point::new(0.6, 0.4),
        performance_seed: Some(-7),
        instruction_index: 2,
        mark_index: 0,
        variation: None,
        weight: Weight::Pencil,
        point_count: 49,
    };
    let points = generate_cloudform_contour(request);
    assert_eq!(points, generate_cloudform_contour(request));
    assert_eq!(points.len(), 49);
    assert!(
        points
            .iter()
            .all(|point| point.x.is_finite() && point.y.is_finite())
    );
    assert!(!polygon_self_intersects(&points));
}

#[test]
fn cloudform_point_count_is_clamped() {
    let request = CloudformRequest {
        center: Point::new(0.5, 0.5),
        size: Point::new(0.4, 0.4),
        performance_seed: None,
        instruction_index: 0,
        mark_index: 0,
        variation: None,
        weight: Weight::Pen,
        point_count: 3,
    };
    assert_eq!(generate_cloudform_contour(request).len(), 24);
}
