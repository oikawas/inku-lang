use inku_render::planning::{
    ensure_line_coordinates, instruction_anchor, move_anchor_to, resolve_at_region,
    resolve_relation,
};
use inku_render::types::{Instruction, Point, Score};

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
