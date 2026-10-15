//! The free line in the composition (I-715 stage B2): a free line layer without
//! a direction takes one from how the reading moves it, the placement is the
//! same with or without that direction, and a free line is joined only by the
//! connection.

use std::collections::BTreeMap;

use inku_ddl::ResolvedInstructionLanguage;
use inku_ddl::work_plan::{
    WorkPlan, WorkPlanLayer, WorkPlanSlot, print_work_plan_composed_with_joints,
    work_plan_source_compiles_cleanly,
};
use inku_pipeline::composition::{
    self, CheckedReading, Joint, JointKind, Jointed, Relation, RelationKind, Role, check_joints,
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

fn drawn(shape: &str, angle: Option<&str>) -> WorkPlanLayer {
    let mut drawn = layer(
        json!({"action": "draw", "shape": shape, "count": 1, "proportion": null,
        "attributes": {"color": "black", "tool": "pen"}}),
    );
    if let Some(angle) = angle {
        drawn
            .attributes
            .insert(WorkPlanSlot::Angle, angle.to_owned());
    }
    drawn
}

fn bundle(shape: &str) -> WorkPlanLayer {
    layer(
        json!({"action": "place", "shape": shape, "count": 1, "proportion": null,
        "attributes": {"color": "black", "size": "small", "tool": "pen"}}),
    )
}

fn motion(kind: RelationKind, a: usize) -> Relation {
    Relation {
        kind,
        a,
        b: None,
        c: None,
        side: None,
        toward: None,
    }
}

fn reading(roles: Vec<Role>, relations: Vec<Relation>, joints: Vec<Joint>) -> CheckedReading {
    CheckedReading {
        roles,
        relations,
        joints,
        ..CheckedReading::default()
    }
}

fn place(layers: &[WorkPlanLayer], reading: &CheckedReading) -> Jointed {
    let searched = composition::search(layers, reading, "white").expect("searched");
    let solution = composition::solve(layers, reading, "white", &searched, 1, "free-line-test")
        .expect("solved");
    composition::join(layers, reading, "white", &solution, 1, "free-line-test")
}

/// The composed source as `machine.rs` prints it: the directions are written
/// on the plan the reading saw, then the layers are moved into print order.
fn print(
    layers: &[WorkPlanLayer],
    reading: &CheckedReading,
    jointed: &Jointed,
    language: ResolvedInstructionLanguage,
) -> String {
    let plan = WorkPlan {
        layers: layers.to_vec(),
        ..WorkPlan::default()
    };
    print_plan(
        &composition::with_free_line_angles(&plan, reading),
        jointed,
        language,
    )
}

fn print_plan(plan: &WorkPlan, jointed: &Jointed, language: ResolvedInstructionLanguage) -> String {
    let (plan, ranges, joints) = composition::composed_plan_with_joints(plan, jointed);
    print_work_plan_composed_with_joints(&plan, language, &[], &ranges, &joints)
}

/// The sentence of the free line, and how many times it holds `word`.
fn free_line_sentence_count(source: &str, name: &str, word: &str) -> usize {
    source
        .lines()
        .find(|line| line.contains(name))
        .expect("the free line's sentence")
        .matches(word)
        .count()
}

fn angle_of(plan: &WorkPlan, index: usize) -> Option<&str> {
    plan.layers[index]
        .attributes
        .get(&WorkPlanSlot::Angle)
        .map(String::as_str)
}

#[test]
fn a_free_line_is_written_in_the_direction_the_reading_moves_it() {
    for (kind, angle, ja, en) in [
        (RelationKind::Rising, "rising", "右上がり", "rising"),
        (RelationKind::Falling, "falling", "右下がり", "falling"),
        (RelationKind::Flowing, "horizontal", "水平", "horizontal"),
    ] {
        let layers = vec![band(), drawn("free_line", None)];
        let reading = reading(
            vec![Role::Field, Role::Focal],
            vec![motion(kind, 1)],
            Vec::new(),
        );
        let plan = WorkPlan {
            layers: layers.clone(),
            ..WorkPlan::default()
        };
        assert_eq!(
            angle_of(&composition::with_free_line_angles(&plan, &reading), 1),
            Some(angle)
        );
        let jointed = place(&layers, &reading);
        for (language, word, name) in [
            (ResolvedInstructionLanguage::Ja, ja, "自由線"),
            (ResolvedInstructionLanguage::En, en, "free line"),
        ] {
            // The range is written in words too ("horizontal 0 to 1/3"), so the
            // direction is the one more the sentence holds than without it.
            let source = print(&layers, &reading, &jointed, language);
            let plain = print_plan(&plan, &jointed, language);
            assert_eq!(
                free_line_sentence_count(&source, name, word),
                free_line_sentence_count(&plain, name, word) + 1,
                "{source}"
            );
            assert!(
                work_plan_source_compiles_cleanly(&source, language),
                "{source}"
            );
        }
    }
}

#[test]
fn a_stated_direction_another_shape_and_a_still_free_line_are_left_alone() {
    let layers = vec![
        band(),
        drawn("free_line", Some("vertical")),
        drawn("line", None),
        drawn("free_line", None),
        drawn("free_line", None),
    ];
    let reading = reading(
        vec![
            Role::Field,
            Role::Focal,
            Role::Secondary,
            Role::Accent,
            Role::Accent,
        ],
        vec![
            motion(RelationKind::Rising, 1),
            motion(RelationKind::Rising, 2),
            motion(RelationKind::Piling, 3),
            // The first motion the reading names for a layer is the one written.
            motion(RelationKind::Falling, 4),
            motion(RelationKind::Flowing, 4),
        ],
        Vec::new(),
    );
    let plan = WorkPlan {
        layers,
        ..WorkPlan::default()
    };
    let written = composition::with_free_line_angles(&plan, &reading);
    assert_eq!(angle_of(&written, 1), Some("vertical"));
    assert_eq!(angle_of(&written, 2), None);
    assert_eq!(angle_of(&written, 3), None);
    assert_eq!(angle_of(&written, 4), Some("falling"));
    for index in [0, 2, 3] {
        assert_eq!(written.layers[index], plan.layers[index]);
    }
}

#[test]
fn the_direction_does_not_move_the_placement() {
    let layers = vec![band(), drawn("free_line", None), bundle("circle")];
    let reading = reading(
        vec![Role::Field, Role::Focal, Role::Secondary],
        vec![motion(RelationKind::Rising, 1)],
        Vec::new(),
    );
    let plan = WorkPlan {
        layers: layers.clone(),
        ..WorkPlan::default()
    };
    let angled = composition::with_free_line_angles(&plan, &reading).layers;
    assert_ne!(angled, layers);
    let before = place(&layers, &reading);
    let after = place(&angled, &reading);
    assert_eq!(after.regions, before.regions);
    assert_eq!(after.order, before.order);
}

#[test]
fn a_free_line_is_joined_by_the_connection_on_either_side() {
    let layers = vec![
        bundle("circle"),
        drawn("free_line", None),
        drawn("line", None),
        bundle("point"),
        drawn("free_line", None),
    ];
    let joints = [
        joint(JointKind::ContinuesFrom, 1, 0),
        joint(JointKind::ContinuesFrom, 2, 1),
        joint(JointKind::ContinuesFrom, 4, 2),
        joint(JointKind::ContinuesFrom, 3, 4),
    ];
    let (kept, findings) = check_joints(&joints, &layers, &BTreeMap::new());
    assert_eq!(kept, joints.to_vec());
    assert!(findings.is_empty(), "{findings:?}");
    let reading = reading(
        vec![
            Role::Focal,
            Role::Secondary,
            Role::Secondary,
            Role::Accent,
            Role::Secondary,
        ],
        Vec::new(),
        kept,
    );
    let jointed = place(&layers, &reading);
    for (language, phrase) in [
        (ResolvedInstructionLanguage::Ja, "、前の形につながる。"),
        (
            ResolvedInstructionLanguage::En,
            " connected to the previous shape.",
        ),
    ] {
        let source = print(&layers, &reading, &jointed, language);
        assert_eq!(
            source.lines().filter(|line| line.ends_with(phrase)).count(),
            4,
            "{source}"
        );
        assert!(
            work_plan_source_compiles_cleanly(&source, language),
            "{source}"
        );
    }
}

#[test]
fn a_free_line_takes_no_joint_but_the_connection() {
    let layers = vec![
        bundle("circle"),
        drawn("free_line", None),
        bundle("square"),
        drawn("line", None),
    ];
    for kind in [
        JointKind::RestsOn,
        JointKind::Inside,
        JointKind::Overlaps,
        JointKind::Crosses,
    ] {
        let joints = [joint(kind, 1, 0), joint(kind, 3, 1), joint(kind, 2, 0)];
        let (kept, findings) = check_joints(&joints, &layers, &BTreeMap::new());
        assert_eq!(kept, vec![joints[2]], "{kind:?}");
        let codes: Vec<&str> = findings.iter().map(|finding| finding.code).collect();
        assert_eq!(
            codes,
            ["joint_not_writable", "joint_not_writable"],
            "{kind:?}"
        );
    }
}

fn joint(kind: JointKind, a: usize, b: usize) -> Joint {
    Joint { kind, a, b }
}
