use inku_render::group::{fade_levels, finish_group};
use inku_render::planning::instruction_anchor;
use inku_render::types::{Arrangement, Fade, Instruction, Point, Score};

fn instruction(json: &str) -> Instruction {
    let score: Score = serde_json::from_str(&format!(r#"{{"instructions":[{json}]}}"#)).unwrap();
    score.instructions.into_iter().next().unwrap()
}

#[test]
fn member_size_and_rotation_keep_each_anchor_fixed() {
    let item = instruction(
        r#"{"primitive":"square","position":[0.4,0.4],"size":[0.2,0.2],"weight":"pencil"}"#,
    );
    let arrangement: Arrangement =
        serde_json::from_str(r#"{"count":3,"layout":"scatter","fade":"directional"}"#).unwrap();
    let items = vec![item.clone(), item.clone(), item];
    let anchors: Vec<Point> = items.iter().map(instruction_anchor).collect();
    let finished = finish_group(items, &arrangement, None, Some(431));
    assert_eq!(finished.len(), 3);
    assert_eq!(
        finished.iter().map(instruction_anchor).collect::<Vec<_>>(),
        anchors
    );
    assert!(finished.iter().all(|item| item.rotation.is_some()));
    assert!(
        finished
            .iter()
            .all(|item| item.color_hint.as_deref().unwrap().contains("fade_level="))
    );
}

#[test]
fn outward_fade_does_not_invent_a_gradient_around_a_ring() {
    let arrangement: Arrangement = serde_json::from_str(
        r#"{"count":4,"layout":"radial","fade":"outward","center":[0.5,0.5]}"#,
    )
    .unwrap();
    let items = [[0.8, 0.5], [0.5, 0.8], [0.2, 0.5], [0.5, 0.2]]
        .into_iter()
        .map(|center| {
            instruction(&format!(
                r#"{{"primitive":"circle","center":[{},{}],"radius":0.05}}"#,
                center[0], center[1]
            ))
        })
        .collect::<Vec<_>>();
    assert_eq!(arrangement.fade, Fade::Outward);
    assert_eq!(fade_levels(&items, &arrangement, None), None);
}
