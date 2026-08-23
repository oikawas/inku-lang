use inku_render::arrangement::{ArrangementRequest, expand_arrangement, quantize_instruction};
use inku_render::planning::instruction_anchor;
use inku_render::types::{CanvasSize, Instruction, Score};

fn instruction(json: &str) -> Instruction {
    let score: Score = serde_json::from_str(&format!(r#"{{"instructions":[{json}]}}"#)).unwrap();
    score.instructions.into_iter().next().unwrap()
}

#[test]
fn horizontal_group_is_fitted_to_the_declared_anchor_and_frame() {
    let original = instruction(
        r#"{"primitive":"circle","center":[0.7,0.3],"radius":0.05,
        "arrangement":{"count":3,"layout":"horizontal","margin":0.1}}"#,
    );
    let expanded = expand_arrangement(ArrangementRequest {
        instruction: &original,
        placement_seed: Some(17),
        performance_seed: Some(431),
        canvas: None,
    });
    assert_eq!(expanded.len(), 3);
    assert!(expanded.iter().all(|item| item.arrangement.is_none()));
    let anchors: Vec<_> = expanded.iter().map(instruction_anchor).collect();
    assert!(anchors.iter().all(|point| (0.02..=0.98).contains(&point.x)));
    assert_eq!(anchors[1].y, 0.3);
}

#[test]
fn explicit_grid_shape_owns_its_full_cell_count() {
    let original = instruction(
        r#"{"primitive":"square","position":[0.4,0.4],"size":[0.1,0.1],
        "arrangement":{"count":3,"layout":"grid","rows":2,"cols":2}}"#,
    );
    let expanded = expand_arrangement(ArrangementRequest {
        instruction: &original,
        placement_seed: None,
        performance_seed: Some(-7),
        canvas: Some(CanvasSize::new(1000.0, 500.0)),
    });
    assert_eq!(expanded.len(), 4);
    assert!(
        expanded
            .iter()
            .all(|item| item.at.is_none() && item.relation.is_none())
    );
}

#[test]
fn arrangement_quantization_uses_python_ties_to_even() {
    let original =
        instruction(r#"{"primitive":"circle","center":[0.1234567895,0.1234567885],"radius":0.1}"#);
    let quantized = quantize_instruction(&original);
    assert_eq!(quantized.center.unwrap().x, 0.123_456_79);
    assert_eq!(quantized.center.unwrap().y, 0.123_456_788);
}

#[test]
fn quantization_reaches_nested_arrangement_values() {
    let original = instruction(
        r#"{"primitive":"circle","center":[0.5,0.5],"radius":0.1,
        "arrangement":{"count":2,"jitter":0.1234567895,"margin":0.1234567885,
        "center":[0.1234567895,0.1234567885],"radius":0.1234567895}}"#,
    );
    let quantized = quantize_instruction(&original);
    let arrangement = quantized.arrangement.unwrap();
    assert_eq!(arrangement.jitter, 0.123_456_79);
    assert_eq!(arrangement.margin, 0.123_456_788);
    assert_eq!(arrangement.center.unwrap().x, 0.123_456_79);
    assert_eq!(arrangement.radius, Some(0.123_456_79));
}

#[test]
fn expansion_moves_only_the_geometry_owned_by_the_primitive() {
    let original = instruction(
        r#"{"primitive":"circle","center":[0.5,0.5],"radius":0.05,
        "position":[0.12,0.34],"arrangement":{"count":2,"layout":"horizontal"}}"#,
    );
    let expanded = expand_arrangement(ArrangementRequest {
        instruction: &original,
        placement_seed: Some(17),
        performance_seed: Some(431),
        canvas: None,
    });
    assert_eq!(expanded.len(), 2);
    assert!(
        expanded
            .iter()
            .all(|item| item.position == original.position)
    );
    assert!(
        expanded.iter().any(|item| item.center != original.center),
        "the circle center should still receive the arrangement shift"
    );
}
