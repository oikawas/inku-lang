use inku_score::{Canvas, Color, InstructionMode, Score, Weight};
use serde_json::{Value, json};

fn score(json: &str) -> Score {
    serde_json::from_str(json).unwrap()
}

#[test]
fn explicit_score_round_trips_without_renderer() {
    let input = r#"{"version":"0.1.0","canvas":{"aspect":"portrait","ground":{"material":"paper","tone":"warm","grain":"fine","density":0.45,"opacity":0.16,"seed":13579}},"background":"gray","presence":{"kind":"group_like","intensity":"high","center":[0.2,0.8],"symmetry":"radial","gaze_pressure":"medium","contour_density":"high"},"instructions":[{"primitive":"circle","note":"study","from":null,"to":null,"center":[0.5,0.5],"radius":0.27,"sides":null,"position":null,"size":null,"angle_start":null,"angle_end":null,"rotation":null,"filled":true,"style":"dashed","weight":"brush_thick","mode":"carve","carve_depth":"half","color":"blue","color_hint":"indigo","variation":{"amplitude":"broad","frequency":"high","quality":"pink","dimensions":["radius"]},"arrangement":null,"at":null,"relation":null,"thinness":"extra_fine","surface":{"texture":"grain","density":0.4,"scale":0.5,"opacity":0.3,"bleed":0.0,"direction":"diagonal_rising","spacing_gradient":"dense_to_coarse","tone_steps":4,"seed":-7}}]}"#;

    let parsed = score(input);

    assert_eq!(
        serde_json::to_value(&parsed).unwrap(),
        serde_json::from_str::<Value>(input).unwrap()
    );
}

#[test]
fn default_bearing_score_keeps_its_declared_defaults() {
    let parsed = score(r#"{"instructions":[{"primitive":"line"}]}"#);

    assert_eq!(parsed.version, "0.1.0");
    assert_eq!(parsed.canvas, Canvas::Id("square".to_owned()));
    assert_eq!(parsed.background, Color::White);
    assert_eq!(parsed.instructions[0].weight, Weight::Pen);
    assert_eq!(parsed.instructions[0].mode_, InstructionMode::Additive);

    assert_eq!(
        serde_json::to_value(parsed).unwrap(),
        json!({
            "version": "0.1.0",
            "canvas": "square",
            "background": "white",
            "presence": null,
            "instructions": [{
                "primitive": "line",
                "note": null,
                "from": null,
                "to": null,
                "center": null,
                "radius": null,
                "sides": null,
                "position": null,
                "size": null,
                "angle_start": null,
                "angle_end": null,
                "rotation": null,
                "filled": false,
                "style": "solid",
                "weight": "pen",
                "mode": "additive",
                "carve_depth": null,
                "color": "black",
                "color_hint": null,
                "variation": null,
                "arrangement": null,
                "at": null,
                "relation": null,
                "thinness": null,
                "surface": null,
            }],
        })
    );
}
