use inku_render::performance::{PerformanceRequest, resolve_performance};
use inku_render::types::{CanvasSize, Score};

fn score(json: &str) -> Score {
    serde_json::from_str(json).unwrap()
}

#[test]
fn absent_performance_seed_preserves_unresolved_fields() {
    let input = score(
        r#"{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.1,
        "at":{"region":[0.1,0.1,0.3,0.3]},"relation":{"type":"along"}}]}"#,
    );
    let result = resolve_performance(PerformanceRequest {
        score: &input,
        performance_seed: None,
        composition_seed: None,
        canvas: None,
    });
    assert!(result.score.instructions[0].at.is_some());
    assert!(result.score.instructions[0].relation.is_some());
}

#[test]
fn performance_resolves_regions_then_relations_in_sequence() {
    let input = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5]},
        {"primitive":"circle","center":[0.5,0.5],"radius":0.05,
         "at":{"region":[0.2,0.2,0.4,0.4]},"relation":{"type":"along"}}
        ]}"#,
    );
    let result = resolve_performance(PerformanceRequest {
        score: &input,
        performance_seed: Some(431),
        composition_seed: Some(17),
        canvas: Some(CanvasSize::new(1000.0, 500.0)),
    });
    assert!(result.warnings.is_empty());
    assert!(result.score.instructions[1].at.is_none());
    assert!(result.score.instructions[1].relation.is_none());
}

#[test]
fn composite_arrangement_copies_the_ordered_instruction_unit() {
    let input = score(
        r#"{"instructions":[
        {"primitive":"circle","center":[0.4,0.5],"radius":0.08,"weight":"pencil",
         "arrangement":{"count":3,"group_size":2,"layout":"horizontal"}},
        {"primitive":"line","from":[0.35,0.5],"to":[0.45,0.5],"weight":"pencil"}
        ]}"#,
    );
    let result = resolve_performance(PerformanceRequest {
        score: &input,
        performance_seed: None,
        composition_seed: Some(17),
        canvas: None,
    });
    assert_eq!(result.score.instructions.len(), 6);
    assert!(
        result
            .score
            .instructions
            .iter()
            .all(|instruction| instruction.arrangement.is_none())
    );
}

#[test]
fn grid_relation_is_dropped_with_structured_warning() {
    let input = score(
        r#"{"instructions":[{"primitive":"square","position":[0.4,0.4],"size":[0.1,0.1],
        "arrangement":{"count":4,"layout":"grid"},"relation":{"type":"between"}}]}"#,
    );
    let result = resolve_performance(PerformanceRequest {
        score: &input,
        performance_seed: Some(9),
        composition_seed: None,
        canvas: None,
    });
    assert!(result.score.instructions[0].relation.is_none());
    assert_eq!(result.warnings[0].reason, "grid layout consumes relation");
}
