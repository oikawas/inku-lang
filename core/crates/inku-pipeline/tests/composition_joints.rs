//! Joints in the composition (I-711 stage C): the check keeps the joints a
//! composition can write, a work without joints is placed as before, a joined
//! layer keeps its range and is printed right after its partner with the joint
//! phrase, and the partner leaves room on the canvas for the joined layer.

use std::collections::BTreeMap;

use inku_ddl::ResolvedInstructionLanguage;
use inku_ddl::work_plan::{
    WorkPlan, WorkPlanLayer, print_work_plan_composed, print_work_plan_composed_with_joints,
    work_plan_source_compiles_cleanly,
};
use inku_pipeline::composition::{
    self, CheckedReading, Joint, JointKind, Jointed, Role, check_joints,
};
use serde_json::json;

fn layer(value: serde_json::Value) -> WorkPlanLayer {
    serde_json::from_value(value).expect("a work-plan layer")
}

fn band() -> WorkPlanLayer {
    layer(
        json!({"action": "fill", "shape": "square", "count": 1, "proportion": "wide",
        "attributes": {"color": "gray", "size": "huge", "tool": "thick_brush"}}),
    )
}

fn circles() -> WorkPlanLayer {
    layer(
        json!({"action": "scatter", "shape": "circle", "count": 24, "proportion": null,
        "attributes": {"color": "yellow", "size": "small", "tool": "crayon"}}),
    )
}

fn lines() -> WorkPlanLayer {
    layer(
        json!({"action": "draw", "shape": "line", "count": 6, "proportion": null,
        "attributes": {"color": "black", "size": "large", "tool": "pen"}}),
    )
}

fn bundle(shape: &str) -> WorkPlanLayer {
    layer(
        json!({"action": "place", "shape": shape, "count": 1, "proportion": null,
        "attributes": {"color": "black", "size": "small", "tool": "pen"}}),
    )
}

fn reading(roles: Vec<Role>, joints: Vec<Joint>) -> CheckedReading {
    CheckedReading {
        roles,
        joints,
        ..CheckedReading::default()
    }
}

fn joint(kind: JointKind, a: usize, b: usize) -> Joint {
    Joint { kind, a, b }
}

fn place(layers: &[WorkPlanLayer], reading: &CheckedReading) -> Jointed {
    let searched = composition::search(layers, reading, "white").expect("searched");
    let solution =
        composition::solve(layers, reading, "white", &searched, 1, "joint-test").expect("solved");
    composition::join(layers, reading, "white", &solution, 1, "joint-test")
}

fn print(
    layers: &[WorkPlanLayer],
    jointed: &Jointed,
    language: ResolvedInstructionLanguage,
) -> String {
    let plan = WorkPlan {
        layers: layers.to_vec(),
        ..WorkPlan::default()
    };
    let (plan, ranges, joints) = composition::composed_plan_with_joints(&plan, jointed);
    print_work_plan_composed_with_joints(&plan, language, &[], &ranges, &joints)
}

#[test]
fn the_check_keeps_the_joints_a_composition_can_write() {
    let layers = vec![
        band(),
        circles(),
        bundle("line"),
        bundle("cloudform"),
        bundle("point"),
    ];
    let fixed = BTreeMap::from([(4, "top".to_owned())]);
    let joints = [
        joint(JointKind::RestsOn, 1, 0),
        joint(JointKind::Inside, 2, 0),
        joint(JointKind::Crosses, 2, 2),
        joint(JointKind::Overlaps, 2, 7),
        joint(JointKind::ContinuesFrom, 2, 3),
        joint(JointKind::Overlaps, 2, 1),
        joint(JointKind::RestsOn, 0, 2),
        joint(JointKind::RestsOn, 4, 3),
    ];
    let (kept, findings) = check_joints(&joints, &layers, &fixed);
    assert_eq!(kept, vec![joints[0], joints[5]]);
    let codes: Vec<&str> = findings.iter().map(|finding| finding.code).collect();
    assert_eq!(
        codes,
        [
            "joint_partner_taken",
            "joint_layer",
            "joint_layer",
            "joint_not_writable",
            "joint_cycle",
            "joint_stated",
        ]
    );
}

#[test]
fn a_work_without_joints_is_placed_and_printed_as_before() {
    let layers = vec![band(), lines(), circles()];
    let reading = reading(
        vec![Role::Field, Role::Secondary, Role::Scattered],
        Vec::new(),
    );
    let searched = composition::search(&layers, &reading, "white").expect("searched");
    let solution =
        composition::solve(&layers, &reading, "white", &searched, 1, "joint-test").expect("solved");
    let jointed = composition::join(&layers, &reading, "white", &solution, 1, "joint-test");
    assert_eq!(jointed.regions, solution.regions);
    assert_eq!(jointed.order, vec![0, 1, 2]);
    assert_eq!(jointed.joints, vec![None; 3]);
    let plan = WorkPlan {
        layers: layers.clone(),
        ..WorkPlan::default()
    };
    let (composed, ranges) = composition::composed_plan(&plan, &solution.regions);
    for language in [
        ResolvedInstructionLanguage::Ja,
        ResolvedInstructionLanguage::En,
    ] {
        assert_eq!(
            print(&layers, &jointed, language),
            print_work_plan_composed(&composed, language, &[], &ranges)
        );
    }
    let stored = serde_json::to_value(&reading).expect("JSON");
    assert!(stored.get("joints").is_none(), "{stored}");
}

#[test]
fn a_group_resting_on_a_band_is_printed_after_it_with_room_above_it() {
    let layers = vec![band(), lines(), circles()];
    let mut reading = reading(
        vec![Role::Field, Role::Secondary, Role::Scattered],
        vec![joint(JointKind::RestsOn, 2, 0)],
    );
    // Wide empty space (the composition's default until 2026-10-21) keeps the
    // circles' range low enough for the band to leave room above it.
    reading
        .tension
        .insert("void".to_owned(), "strong".to_owned());
    let jointed = place(&layers, &reading);
    assert_eq!(jointed.order, vec![0, 2, 1]);
    assert_eq!(jointed.joints, vec![None, None, Some(JointKind::RestsOn)]);
    let bounds = |index: usize| {
        let range = composition::written_range(jointed.regions[index]).expect("a range");
        range
            .bounds
            .map(|(numerator, denominator)| f64::from(numerator) / f64::from(denominator))
    };
    // The circles keep the range of the placement without joints, and the band
    // leaves room above it for them.
    let (band_top, circles) = (bounds(0)[1], bounds(2));
    assert!(
        band_top + 1e-9 >= circles[3] - circles[1],
        "band top {band_top}, circles {circles:?}"
    );
    for (language, phrase) in [
        (ResolvedInstructionLanguage::Ja, "、前の形に載る。"),
        (
            ResolvedInstructionLanguage::En,
            " resting on the previous shape.",
        ),
    ] {
        let source = print(&layers, &jointed, language);
        let printed: Vec<&str> = source.lines().collect();
        let joined = printed.len() - 2;
        assert!(printed[joined].ends_with(phrase), "{source}");
        assert_eq!(
            printed.iter().filter(|line| line.contains(phrase)).count(),
            1,
            "{source}"
        );
        assert!(
            work_plan_source_compiles_cleanly(&source, language),
            "{source}"
        );
    }
    let stored = serde_json::to_value(&reading).expect("JSON");
    assert_eq!(
        stored["joints"],
        json!([{"type": "rests_on", "a": 2, "b": 0}])
    );
    let read: CheckedReading = serde_json::from_value(stored).expect("read back");
    assert_eq!(read, reading);
}

#[test]
fn a_chain_of_joints_prints_each_joined_layer_after_its_partner() {
    let layers = vec![
        bundle("square"),
        bundle("circle"),
        bundle("line"),
        bundle("ellipse"),
    ];
    let reading = reading(
        vec![
            Role::Focal,
            Role::Secondary,
            Role::Secondary,
            Role::Secondary,
        ],
        vec![
            joint(JointKind::Overlaps, 3, 0),
            joint(JointKind::ContinuesFrom, 2, 3),
        ],
    );
    let jointed = place(&layers, &reading);
    assert_eq!(jointed.order, vec![0, 3, 2, 1]);
    let source = print(&layers, &jointed, ResolvedInstructionLanguage::Ja);
    let printed: Vec<&str> = source.lines().collect();
    assert!(printed[1].ends_with("、前の形に重なる。"), "{source}");
    assert!(printed[2].ends_with("、前の形につながる。"), "{source}");
    assert!(
        work_plan_source_compiles_cleanly(&source, ResolvedInstructionLanguage::Ja),
        "{source}"
    );
}
