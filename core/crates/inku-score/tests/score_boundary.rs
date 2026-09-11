use inku_score::{Canvas, Color, InstructionMode, Score, SurfaceIntensity, Weight};
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

    assert_eq!(parsed.version, "0.2.0");
    assert_eq!(parsed.canvas, Canvas::Id("square".to_owned()));
    assert_eq!(parsed.background, Color::White);
    assert_eq!(parsed.instructions[0].weight, Weight::Pen);
    assert_eq!(parsed.instructions[0].mode_, InstructionMode::Additive);

    assert_eq!(
        serde_json::to_value(parsed).unwrap(),
        json!({
            "version": "0.2.0",
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

#[test]
fn surface_intensity_keeps_normal_bytes_and_rejects_unaccepted_texture_meanings() {
    let old = score(r#"{"instructions":[{"primitive":"circle","filled":true}]}"#);
    let old_bytes = serde_json::to_vec(&old).unwrap();
    assert!(
        !String::from_utf8(old_bytes.clone())
            .unwrap()
            .contains("surface_intensity")
    );
    for (value, expected) in [
        ("normal", SurfaceIntensity::Normal),
        ("dense", SurfaceIntensity::Dense),
        ("faint", SurfaceIntensity::Faint),
    ] {
        let mut wire = serde_json::to_value(&old).unwrap();
        wire["instructions"][0]["surface_intensity"] = json!(value);
        let parsed: Score = serde_json::from_value(wire).unwrap();
        assert_eq!(parsed.instructions[0].surface_intensity, expected);
        assert!(parsed.validate_schema_edition().is_ok());
        if expected == SurfaceIntensity::Normal {
            assert_eq!(serde_json::to_vec(&parsed).unwrap(), old_bytes);
        } else {
            assert_eq!(
                serde_json::to_value(&parsed).unwrap()["instructions"][0]["surface_intensity"],
                value
            );
        }
    }
    for primitive in ["circle", "point"] {
        let parsed = score(&format!(
            r#"{{"instructions":[{{"primitive":"{primitive}","filled":true,"surface_intensity":"dense"}}]}}"#
        ));
        assert!(parsed.validate_schema_edition().is_ok());
    }
    for instruction in [
        json!({"primitive":"line","filled":true,"surface_intensity":"dense"}),
        json!({"primitive":"circle","surface_intensity":"dense"}),
        json!({"primitive":"circle","filled":true,"surface":{"texture":"wash"},"surface_intensity":"dense"}),
    ] {
        let parsed: Score = serde_json::from_value(json!({"instructions":[instruction]})).unwrap();
        assert_eq!(
            parsed.validate_schema_edition(),
            Err("surface_intensity requires a closed solid fill")
        );
    }
    assert!(
        serde_json::from_str::<Score>(
            r#"{"instructions":[{"primitive":"circle","surface_intensity":"unknown"}]}"#
        )
        .is_err()
    );
}
