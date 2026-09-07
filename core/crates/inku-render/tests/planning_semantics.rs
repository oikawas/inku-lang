use inku_render::geometry::point_to_short_side_units;
use inku_render::planning::{
    ensure_line_coordinates, instruction_anchor, move_anchor_to,
    performed_instruction_bounds_on_canvas, resolve_at_region, resolve_relation,
    resolve_relation_on_canvas,
};
use inku_render::types::{CanvasSize, Instruction, Point, Score};

fn instruction(json: &str) -> Instruction {
    let score: Score = serde_json::from_str(&format!(r#"{{"instructions":[{json}]}}"#)).unwrap();
    score.instructions.into_iter().next().unwrap()
}

#[test]
fn missing_line_coordinates_follow_the_arrangement_axis() {
    let vertical =
        instruction(r#"{"primitive":"line","arrangement":{"layout":"vertical","count":3}}"#);
    let resolved = ensure_line_coordinates(&vertical);
    assert_eq!(resolved.from_, Some(Point::new(0.0, 0.5)));
    assert_eq!(resolved.to, Some(Point::new(1.0, 0.5)));
}

#[test]
fn region_resolution_consumes_at_but_preserves_relation() {
    let original = instruction(
        r#"{"primitive":"circle","center":[0.5,0.5],"radius":0.1,
        "at":{"region":[0.6,0.2,0.9,0.4]},
        "relation":{"type":"not_touching","gap":"narrow"}}"#,
    );
    let resolved = resolve_at_region(&original, -7, 2, None);
    assert!(resolved.at.is_none());
    assert!(resolved.relation.is_some());
    let anchor = instruction_anchor(&resolved);
    assert!((0.6..=0.9).contains(&anchor.x));
    assert!((0.2..=0.4).contains(&anchor.y));
}

#[test]
fn wide_canvas_square_region_resolution_preserves_the_physical_anchor() {
    let circle = instruction(
        r#"{"primitive":"circle","center":[0.2,0.2],"radius":0.1,
        "at":{"region":[0.39,0.39,0.61,0.61]}}"#,
    );
    let square = instruction(
        r#"{"primitive":"square","position":[0.1,0.1],"size":[0.2,0.2],
        "at":{"region":[0.39,0.39,0.61,0.61]}}"#,
    );

    for canvas in [
        CanvasSize::new(1_000.0, 500.0),
        CanvasSize::new(500.0, 1_000.0),
        CanvasSize::new(500.0, 500.0),
    ] {
        let target = resolve_at_region(&circle, 37, 0, Some(canvas))
            .center
            .unwrap();
        let resolved = resolve_at_region(&square, 37, 0, Some(canvas));
        let position = resolved.position.unwrap();
        let size = resolved.size.unwrap();
        let physical_anchor = Point::new(
            position.x + size.x * canvas.unit() / canvas.width / 2.0,
            position.y + size.y * canvas.unit() / canvas.height / 2.0,
        );

        assert!((physical_anchor.x - target.x).abs() < 1.0e-12);
        assert!((physical_anchor.y - target.y).abs() < 1.0e-12);
    }
}

#[test]
fn wide_canvas_relation_uses_physical_square_bounds() {
    let canvas = CanvasSize::new(1_000.0, 500.0);
    let prior = instruction(r#"{"primitive":"square","position":[0.45,0.4],"size":[0.2,0.2]}"#);
    let current = instruction(
        r#"{"primitive":"circle","center":[0.5,0.5],"radius":0.04,
        "relation":{"type":"not_touching","gap":"narrow"}}"#,
    );
    let result = resolve_relation_on_canvas(&current, &[prior.clone()], 17, 1, Some(canvas));
    assert!(result.warning.is_none());
    let prior_bounds =
        performed_instruction_bounds_on_canvas(&prior, Some(17), 0, Some(canvas)).unwrap();
    let current_bounds =
        performed_instruction_bounds_on_canvas(&result.instruction, Some(17), 1, Some(canvas))
            .unwrap();
    let delta = Point::new(
        current_bounds.center().x - prior_bounds.center().x,
        current_bounds.center().y - prior_bounds.center().y,
    );
    let distance = delta.x.hypot(delta.y);
    assert!(distance > prior_bounds.radius() + current_bounds.radius());
    assert_eq!(
        point_to_short_side_units(result.instruction.center.unwrap(), Some(canvas)),
        current_bounds.center()
    );
}

#[test]
fn named_region_then_direct_relation_resolves_lowerer_shaped_instructions() {
    let prior_one =
        instruction(r#"{"primitive":"circle","center":[0.2,0.3],"radius":0.08,"color":"red"}"#);
    let prior_two = instruction(
        r#"{"primitive":"ellipse","center":[0.7,0.6],"size":[0.24,0.12],"color":"blue"}"#,
    );

    for (relation, priors, index) in [
        (
            r#"{"type":"not_touching","gap":"medium"}"#,
            vec![prior_one.clone()],
            1,
        ),
        (
            r#"{"type":"between","gap":"medium"}"#,
            vec![prior_one.clone(), prior_two.clone()],
            2,
        ),
    ] {
        let current = instruction(&format!(
            r#"{{"primitive":"circle","radius":0.06,"color":"green",
            "at":{{"region":[0.39,0.39,0.61,0.61]}},"relation":{relation}}}"#
        ));
        assert_eq!(current.center, None);
        let prior_snapshot = priors.clone();

        let region_resolved = resolve_at_region(&current, 37, index, None);
        assert!(region_resolved.center.is_some());
        assert_eq!(region_resolved.radius, Some(0.06));
        assert!(region_resolved.at.is_none());
        assert!(region_resolved.relation.is_some());

        let related = resolve_relation(&region_resolved, &priors, 37, index);
        assert!(related.warning.is_none());
        assert!(related.instruction.center.is_some());
        assert_eq!(related.instruction.radius, Some(0.06));
        assert!(related.instruction.relation.is_none());
        assert_eq!(priors, prior_snapshot);
    }
}

#[test]
fn touching_line_reuses_the_rotated_prior_endpoints() {
    let mut prior =
        instruction(r#"{"primitive":"line","from":[0.2,0.5],"to":[0.8,0.5],"rotation":90}"#);
    prior = move_anchor_to(&prior, Point::new(0.5, 0.5), false);
    let current = instruction(
        r#"{"primitive":"line","from":[0.1,0.1],"to":[0.2,0.2],
        "relation":{"type":"touching"}}"#,
    );
    let result = resolve_relation(&current, &[prior], 17, 1);
    assert!(result.warning.is_none());
    assert!((result.instruction.from_.unwrap().x - 0.5).abs() < 1.0e-12);
    assert!((result.instruction.to.unwrap().x - 0.5).abs() < 1.0e-12);
    assert_eq!(result.instruction.rotation, None);
}

#[test]
fn endpoint_family_anchor_adapter_preserves_old_arc_and_independent_point_semantics() {
    let typed_arc = instruction(
        r#"{"primitive":"arc","center":[0.5,0.59],"position":[0.5,0.5],
        "radius":0.15,"angle_start":143.13010235415598,
        "angle_end":36.86989764584402,"rotation":30}"#,
    );
    assert_eq!(instruction_anchor(&typed_arc), Point::new(0.5, 0.5));
    let moved = move_anchor_to(&typed_arc, Point::new(0.7, 0.6), false);
    assert_eq!(moved.position, Some(Point::new(0.7, 0.6)));
    assert_eq!(moved.center, Some(Point::new(0.7, 0.69)));

    let legacy_arc = instruction(
        r#"{"primitive":"arc","center":[0.5,0.59],"radius":0.15,
        "angle_start":143.13010235415598,"angle_end":36.86989764584402,
        "rotation":30}"#,
    );
    assert_eq!(instruction_anchor(&legacy_arc), Point::new(0.5, 0.59));
    let legacy_moved = move_anchor_to(&legacy_arc, Point::new(0.7, 0.6), false);
    assert_eq!(legacy_moved.center, Some(Point::new(0.7, 0.6)));
    assert_eq!(legacy_moved.position, None);

    let point =
        instruction(r#"{"primitive":"point","center":[0.3,0.4],"radius":0.006,"filled":true}"#);
    assert_eq!(instruction_anchor(&point), Point::new(0.3, 0.4));
    let bounds = performed_instruction_bounds_on_canvas(
        &point,
        None,
        0,
        Some(CanvasSize::new(1_000.0, 500.0)),
    )
    .unwrap();
    assert_eq!(bounds.min, Point::new(0.594, 0.394));
    assert_eq!(bounds.max, Point::new(0.606, 0.406));
}

#[test]
fn unresolved_relation_is_dropped_with_structured_warning() {
    let current = instruction(
        r#"{"primitive":"circle","center":[0.5,0.5],"radius":0.1,
        "relation":{"type":"between"}}"#,
    );
    let result = resolve_relation(&current, &[], 17, 0);
    assert!(result.instruction.relation.is_none());
    assert_eq!(
        result.warning.unwrap().reason,
        "between requires two priors"
    );
}

#[test]
fn canonically_silent_relation_fallbacks_do_not_create_warnings() {
    let missing_second_bounds = instruction(
        r#"{"primitive":"circle","center":[0.5,0.5],"radius":0.03,
        "relation":{"type":"between"}}"#,
    );
    let no_bounds = instruction(r#"{"primitive":"line"}"#);
    let valid_prior = instruction(r#"{"primitive":"circle","center":[0.5,0.5],"radius":0.1}"#);
    let between = resolve_relation(&missing_second_bounds, &[no_bounds, valid_prior], 17, 2);
    assert!(between.instruction.relation.is_none());
    assert!(between.warning.is_none());

    let along = instruction(
        r#"{"primitive":"circle","center":[0.5,0.5],"radius":0.03,
        "relation":{"type":"along"}}"#,
    );
    let degenerate_line = instruction(r#"{"primitive":"line","from":[0.5,0.5],"to":[0.5,0.5]}"#);
    let along_result = resolve_relation(&along, &[degenerate_line], 17, 1);
    assert!(along_result.instruction.relation.is_none());
    assert!(along_result.warning.is_none());
}

#[test]
fn along_cloudform_uses_the_performed_contour() {
    let prior = instruction(
        r#"{"primitive":"cloudform","center":[0.5,0.5],"size":[0.5,0.3],
        "weight":"pencil"}"#,
    );
    let current = instruction(
        r#"{"primitive":"circle","center":[0.5,0.5],"radius":0.03,
        "relation":{"type":"along","gap":"narrow"}}"#,
    );
    let result = resolve_relation(&current, &[prior], 431, 1);
    assert!(result.warning.is_none());
    let center = result.instruction.center.unwrap();
    assert!((center.x - 0.5).abs() > 0.1 || (center.y - 0.5).abs() > 0.05);
}
