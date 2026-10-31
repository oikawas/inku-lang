use inku_score::read_saved_score_json;
use serde_json::json;

#[test]
fn new_weights_require_score_024_and_retired_weights_remain_readable() {
    for weight in [
        "gouache",
        "watercolor",
        "oil_pastel",
        "painting_knife",
        "etching",
    ] {
        for version in ["0.9.0", "0.17.0", "0.23.0"] {
            let data =
                json!({"version":version,"instructions":[{"primitive":"line","weight":weight}]});
            assert!(
                read_saved_score_json(&serde_json::to_vec(&data).unwrap()).is_err(),
                "{version} {weight}"
            );
        }
        let data =
            json!({"version":"0.24.0","instructions":[{"primitive":"line","weight":weight}]});
        let score = read_saved_score_json(&serde_json::to_vec(&data).unwrap()).unwrap();
        assert_eq!(score.instructions[0].weight.as_str(), weight);
    }
    for weight in [
        "rotring",
        "crayon",
        "brush_thin",
        "brush_thick",
        "burin",
        "drypoint",
    ] {
        let data = json!({"version":"0.9.0","instructions":[{"primitive":"line","weight":weight}]});
        let score = read_saved_score_json(&serde_json::to_vec(&data).unwrap()).unwrap();
        assert_eq!(score.instructions[0].weight.as_str(), weight);
    }
}
