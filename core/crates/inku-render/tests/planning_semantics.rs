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
