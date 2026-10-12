//! Joint relations of Score 0.20.0 and connections to a closed shape.

use inku_render::checked_performance::resolve_checked_performance;
use inku_render::performance::{PerformancePlan, PerformanceRequest};
use inku_render::planning::{Bounds, endpoint_geometry, performed_instruction_bounds_on_canvas};
use inku_render::types::{
    Point, Score, ScoreErrorPolicy, ScoreExecutionDisposition, ScoreExecutionReason,
};
use serde_json::{Value, json};

const SEEDS: [i128; 3] = [1, 7, 42];

fn plan(value: &Value, seed: i128) -> PerformancePlan {
    let score: Score = serde_json::from_value(value.clone()).unwrap();
    score.validate_schema_edition().unwrap();
    resolve_checked_performance(
        PerformanceRequest {
            score: &score,
            performance_seed: Some(seed),
            composition_seed: Some(seed),
            canvas: None,
        },
        ScoreErrorPolicy::Stop,
    )
    .unwrap()
}

fn bounds(plan: &PerformancePlan, index: usize, seed: i128) -> Bounds {
    let bounds = performed_instruction_bounds_on_canvas(
        &plan.score.instructions[index],
        Some(seed),
        index,
        None,
    )
    .unwrap();
    let transform = plan.instruction_transforms()[index];
    Bounds {
        min: transform.apply(bounds.min),
        max: transform.apply(bounds.max),
    }
}

fn joint(prior: Value, current: Value, kind: &str) -> Value {
    let mut current = current;
    current["relation"] = json!({
        "type": kind, "target_instruction_index": 0, "position_authority": "named_movable"
    });
    json!({"version": "0.20.0", "instructions": [prior, current]})
}

fn width(bounds: Bounds) -> f64 {
    bounds.max.x - bounds.min.x
}

fn height(bounds: Bounds) -> f64 {
    bounds.max.y - bounds.min.y
}

#[test]
fn every_joint_holds_after_performance_for_three_seeds() {
    let square = json!({"primitive": "square", "position": [0.3, 0.45], "size": [0.4, 0.2]});
    let circle = json!({"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2});
    let ellipse = json!({"primitive": "ellipse", "center": [0.5, 0.5], "size": [0.4, 0.2]});
    let small = json!({"primitive": "circle", "center": [0.1, 0.1], "radius": 0.03});
    let long = json!({"primitive": "line", "from": [0.05, 0.9], "to": [0.75, 0.9]});
    for seed in SEEDS {
        for prior in [&square, &circle, &ellipse] {
            let resting = plan(&joint(prior.clone(), small.clone(), "resting_on"), seed);
            assert!(resting.execution.is_none(), "{:?}", resting.execution);
            let (own, base) = (bounds(&resting, 1, seed), bounds(&resting, 0, seed));
            assert!(
                (own.max.y - base.min.y).abs() <= 0.002,
                "resting {own:?} {base:?}"
            );
            let center = own.center().x;
            assert!(base.min.x <= center && center <= base.max.x);

            let inside = plan(&joint(prior.clone(), small.clone(), "inside"), seed);
            assert!(inside.execution.is_none(), "{:?}", inside.execution);
            let (own, base) = (bounds(&inside, 1, seed), bounds(&inside, 0, seed));
            let factor = if prior["primitive"] == "square" {
                1.0
            } else {
                std::f64::consts::FRAC_1_SQRT_2
            };
            let (cx, cy) = (base.center().x, base.center().y);
            let (hx, hy) = (width(base) * factor / 2.0, height(base) * factor / 2.0);
            assert!(
                own.min.x >= cx - hx - 1e-6 && own.max.x <= cx + hx + 1e-6,
                "inside x"
            );
            assert!(
                own.min.y >= cy - hy - 1e-6 && own.max.y <= cy + hy + 1e-6,
                "inside y"
            );

            let overlapping = plan(&joint(prior.clone(), small.clone(), "overlapping"), seed);
            assert!(
                overlapping.execution.is_none(),
                "{:?}",
                overlapping.execution
            );
            let (own, base) = (bounds(&overlapping, 1, seed), bounds(&overlapping, 0, seed));
            let w = own.max.x.min(base.max.x) - own.min.x.max(base.min.x);
            let h = own.max.y.min(base.max.y) - own.min.y.max(base.min.y);
            let share = w.max(0.0) * h.max(0.0) / (width(own) * height(own));
            assert!(
                (0.25 - 1e-6..=0.75 + 1e-6).contains(&share),
                "overlap {share}"
            );

            let crossing = plan(&joint(prior.clone(), long.clone(), "crossing"), seed);
            assert!(crossing.execution.is_none(), "{:?}", crossing.execution);
            let (own, base) = (bounds(&crossing, 1, seed), bounds(&crossing, 0, seed));
            assert!(
                own.min.x < base.min.x && own.max.x > base.max.x,
                "crossing x"
            );
            let center = own.center().y;
            assert!(
                base.min.y - 1e-9 <= center && center <= base.max.y + 1e-9,
                "crossing y"
            );
        }
    }
}

#[test]
fn a_joint_the_shapes_cannot_hold_omits_only_its_relation() {
    let small_square = json!({"primitive": "square", "position": [0.45, 0.45], "size": [0.1, 0.1]});
    let large = json!({"primitive": "circle", "center": [0.2, 0.2], "radius": 0.2});
    let short = json!({"primitive": "line", "from": [0.1, 0.9], "to": [0.15, 0.9]});
    let point = json!({"primitive": "point", "position": [0.5, 0.5], "radius": 0.01});
    let small = json!({"primitive": "circle", "center": [0.1, 0.1], "radius": 0.03});
    for (input, kind) in [
        (joint(small_square.clone(), large, "inside"), "inside"),
        (joint(small_square, short, "crossing"), "crossing"),
        (joint(point, small, "resting_on"), "resting_on"),
    ] {
        let failed = plan(&input, 7);
        let execution = failed
            .execution
            .as_ref()
            .unwrap_or_else(|| panic!("{kind}"));
        assert_eq!(execution.diagnostics.len(), 1, "{kind}");
        assert_eq!(
            execution.diagnostics[0].reason,
            ScoreExecutionReason::UnsupportedJointGeometry,
            "{kind}"
        );
        assert_eq!(
            execution.diagnostics[0].disposition,
            ScoreExecutionDisposition::RelationOmitted,
            "{kind}"
        );
        let mut without = input.clone();
        without["instructions"][1]
            .as_object_mut()
            .unwrap()
            .remove("relation");
        let baseline = plan(&without, 7);
        assert_eq!(
            failed.instruction_transforms(),
            baseline.instruction_transforms(),
            "{kind}"
        );
        assert_eq!(
            failed.score.instructions[1].center,
            baseline.score.instructions[1].center
        );
        assert_eq!(
            failed.score.instructions[1].from_,
            baseline.score.instructions[1].from_
        );
    }
}

fn distance_to_segments(points: &[Point], at: Point) -> f64 {
    (0..points.len())
        .map(|index| {
            let (a, b) = (points[index], points[(index + 1) % points.len()]);
            let (dx, dy) = (b.x - a.x, b.y - a.y);
            let t = (((at.x - a.x) * dx + (at.y - a.y) * dy) / (dx * dx + dy * dy)).clamp(0.0, 1.0);
            (a.x + dx * t - at.x).hypot(a.y + dy * t - at.y)
        })
        .fold(f64::INFINITY, f64::min)
}

#[test]
fn a_connection_starts_on_the_outline_of_a_closed_previous_shape() {
    let line = json!({"primitive": "line", "from": [0.05, 0.05], "to": [0.2, 0.1]});
    let cases = [
        json!({"primitive": "square", "position": [0.4, 0.4], "size": [0.2, 0.1]}),
        json!({"primitive": "circle", "center": [0.5, 0.5], "radius": 0.15}),
        json!({"primitive": "ellipse", "center": [0.5, 0.5], "size": [0.3, 0.16]}),
        json!({"primitive": "triangle", "position": [0.4, 0.4], "size": [0.2, 0.2]}),
    ];
    for prior in cases {
        let resolved = plan(&joint(prior.clone(), line.clone(), "connected"), 7);
        assert!(
            resolved.execution.is_none(),
            "{prior} {:?}",
            resolved.execution
        );
        let (start, _, _, _) = endpoint_geometry(&resolved.score.instructions[1], None).unwrap();
        let start = resolved.instruction_transforms()[1].apply(start);
        let distance = match prior["primitive"].as_str().unwrap() {
            "circle" => ((start.x - 0.5).hypot(start.y - 0.5) - 0.15).abs(),
            "ellipse" => {
                let value = ((start.x - 0.5) / 0.15).powi(2) + ((start.y - 0.5) / 0.08).powi(2);
                // A point within 0.002 of the outline keeps the normalized radius near 1.
                (value.sqrt() - 1.0).abs() * 0.08
            }
            "square" => distance_to_segments(
                &[
                    Point::new(0.4, 0.4),
                    Point::new(0.6, 0.4),
                    Point::new(0.6, 0.5),
                    Point::new(0.4, 0.5),
                ],
                start,
            ),
            _ => distance_to_segments(
                &[
                    Point::new(0.4, 0.6),
                    Point::new(0.6, 0.6),
                    Point::new(0.5, 0.4),
                ],
                start,
            ),
        };
        assert!(
            distance <= 0.002,
            "{prior} start {start:?} distance {distance}"
        );
    }
}

#[test]
fn joint_relations_require_score_0_20() {
    let input = joint(
        json!({"primitive": "square", "position": [0.3, 0.45], "size": [0.4, 0.2]}),
        json!({"primitive": "circle", "center": [0.1, 0.1], "radius": 0.03}),
        "resting_on",
    );
    let mut older = input.clone();
    older["version"] = json!("0.19.0");
    let score: Score = serde_json::from_value(older).unwrap();
    assert_eq!(
        score.validate_schema_edition(),
        Err("joint relations require Score version 0.20.0")
    );
    // A saved Score before 0.20.0 that connects to a closed shape stays valid
    // and keeps its older performance: only the relation is omitted.
    let line = json!({"primitive": "line", "from": [0.05, 0.05], "to": [0.2, 0.1]});
    let mut closed = joint(
        json!({"primitive": "circle", "center": [0.5, 0.5], "radius": 0.15}),
        line,
        "connected",
    );
    closed["version"] = json!("0.19.0");
    let older = plan(&closed, 7);
    let execution = older.execution.as_ref().expect("relation omitted");
    assert_eq!(
        execution.diagnostics[0].reason,
        ScoreExecutionReason::UnsupportedConnectedPrimitive
    );
    assert!(older.instruction_transforms()[1].is_identity());
}
