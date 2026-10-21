//! A work with more combinations of ranges than the exhaustive search scores is
//! placed layer by layer (2026-10-21): it is solved rather than skipped, the
//! same plan gives the same answer again, and its number of combinations does
//! not overflow.

use inku_ddl::work_plan::WorkPlanLayer;
use inku_pipeline::composition::{self, MAX_COMBINATIONS};
use serde_json::json;

/// A plan of `count` layers: a field filled over the canvas, bundles of shapes
/// of several sizes, colors and counts, and a scatter of points on top.
fn plan(count: usize) -> Vec<WorkPlanLayer> {
    let sizes = ["very_small", "small", "normal_sized", "large"];
    let colors = ["black", "red", "blue", "green", "yellow"];
    let shapes = ["circle", "square", "triangle", "ellipse"];
    (0..count)
        .map(|i| {
            let layer = if i == 0 {
                json!({"action": "fill", "attributes": {"color": "gray", "surface": "flat"},
                       "count": 1, "proportion": null, "shape": "square"})
            } else if i == count - 1 {
                json!({"action": "scatter", "attributes": {"color": "black", "size": "very_small"},
                       "count": 30, "proportion": null, "shape": "point"})
            } else {
                json!({"action": "place",
                       "attributes": {"color": colors[i % colors.len()], "size": sizes[i % sizes.len()],
                                      "surface": "flat"},
                       "count": 1 + i % 3, "proportion": null, "shape": shapes[i % shapes.len()]})
            };
            serde_json::from_value(layer).expect("a plan layer")
        })
        .collect()
}

#[test]
fn a_work_of_many_layers_is_placed_layer_by_layer_and_answers_alike() {
    for count in [12, 20] {
        let layers = plan(count);
        let reading = composition::default_reading(&layers);
        let searched = composition::search(&layers, &reading, "white").expect("the work is solved");
        assert!(
            searched.combinations > MAX_COMBINATIONS,
            "{count} layers: {} combinations",
            searched.combinations
        );
        assert!(!searched.near.is_empty(), "{count} layers");
        assert_eq!(
            composition::search(&layers, &reading, "white").expect("solved again"),
            searched,
            "{count} layers"
        );
        let solution = composition::solve(&layers, &reading, "white", &searched, 1, "work")
            .expect("a placement");
        assert_eq!(solution.regions.len(), count);
        assert_eq!(
            composition::solve(&layers, &reading, "white", &searched, 1, "work")
                .expect("the placement again"),
            solution,
            "{count} layers"
        );
        // Twenty layers have more combinations (13 ranges for each of 18 bundles)
        // than a u64 holds.
        if count == 20 {
            assert_eq!(searched.combinations, u64::MAX);
        }
    }
}
