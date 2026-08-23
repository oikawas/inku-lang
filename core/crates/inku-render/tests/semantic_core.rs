use inku_render::contact::{contact_fragments, quantize_contact_length, resample_by_length};
use inku_render::determinism::{
    hash_to_unit, hash01, instruction_seed, periodic_value_noise_1d, value_noise_1d, wave_phase,
};
use inku_render::geometry::{
    arc_points, ellipse_perimeter, polygon_points, segment_count, stroke_sample_count,
};
use inku_render::types::{CanvasSize, Score};

fn close(actual: f64, expected: f64) {
    assert!(
        (actual - expected).abs() <= 1.0e-12,
        "{actual} != {expected}"
    );
}

#[test]
fn canonical_score_consumer_preserves_none_and_zero() {
    let score: Score = serde_json::from_str(
        r#"{
            "version":"0.1.0",
            "canvas":{"aspect":"portrait","ground":null},
            "background":"white",
            "presence":null,
            "instructions":[{
                "primitive":"line",
                "from":[0.1,0.2],
                "to":[0.9,0.8],
                "rotation":0.0,
                "carve_depth":null,
                "surface":{"texture":"grain","seed":-7}
            }]
        }"#,
    )
    .expect("canonical Score JSON must deserialize");

    assert_eq!(score.instructions.len(), 1);
    assert_eq!(score.instructions[0].rotation, Some(0.0));
    assert_eq!(score.instructions[0].carve_depth, None);
    assert_eq!(
        score.instructions[0].surface.as_ref().unwrap().seed,
        Some(-7)
    );
}

#[test]
fn instruction_seed_keeps_none_distinct_from_zero() {
    let line: Score = serde_json::from_str(
        r#"{"instructions":[{"primitive":"line","from":[0.1,0.2],"to":[0.9,0.8]}]}"#,
    )
    .unwrap();
    let circle: Score = serde_json::from_str(
        r#"{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.2,
        "variation":{"quality":"wave","frequency":"slow","dimensions":["radius"]}}]}"#,
    )
    .unwrap();

    assert_eq!(
        instruction_seed(&line.instructions[0], None),
        5_010_540_979_992_496_590
    );
    assert_eq!(
        instruction_seed(&line.instructions[0], Some(0)),
        12_153_414_247_091_471_546
    );
    assert_eq!(
        instruction_seed(&line.instructions[0], Some(431)),
        13_591_623_972_881_849_295
    );
    assert_eq!(
        instruction_seed(&circle.instructions[0], None),
        14_500_316_193_031_614_171
    );
}

#[test]
fn representative_hash_and_noise_values_are_fixed() {
    close(hash_to_unit(0, 0), -0.491_442_400_710_706_94);
    close(hash_to_unit(-1, 7), -0.575_133_984_909_466_3);
    close(
        hash_to_unit(42, 9_007_199_254_740_991),
        0.358_360_749_166_571_9,
    );
    close(hash01(-3, 431, "wave-phase"), 0.917_000_912_343_384_9);
    close(value_noise_1d(-0.25, 17), -0.758_799_210_539_633);
    close(wave_phase(431), 2.301_316_673_875_387);

    let above_u64 = i128::from(u64::MAX) + 977;
    assert_ne!(hash_to_unit(0, above_u64), hash_to_unit(0, 976));
}

#[test]
fn periodic_noise_closes_for_positive_and_negative_coordinates() {
    close(
        periodic_value_noise_1d(0.0, 17, 6),
        periodic_value_noise_1d(6.0, 17, 6),
    );
    close(
        periodic_value_noise_1d(-0.25, 17, 6),
        periodic_value_noise_1d(5.75, 17, 6),
    );
}

#[test]
fn python_ties_to_even_controls_discrete_counts_and_quantization() {
    let canvas = CanvasSize::new(1000.0, 500.0);
    assert_eq!(segment_count(162.5, canvas), 32);
    assert_eq!(segment_count(167.5, canvas), 34);
    assert_eq!(segment_count(172.5, canvas), 34);
    assert_eq!(stroke_sample_count(331.632_653_061_224_5, canvas), 32);
    assert_eq!(stroke_sample_count(341.836_734_693_877_53, canvas), 34);
    close(quantize_contact_length(1.234_567_5), 1.234_568);
    close(quantize_contact_length(1.234_568_5), 1.234_568);
    close(quantize_contact_length(-1.234_567_5), -1.234_568);
}

#[test]
fn representative_geometry_and_contact_are_stable() {
    close(ellipse_perimeter(3.0, 2.0), 15.865_439_589_251_233);
    close(ellipse_perimeter(-3.0, 2.0), 15.865_439_589_251_233);
    assert_eq!(ellipse_perimeter(0.0, 0.0), 0.0);

    let arc = arc_points((10.0, 20.0).into(), 5.0, 0.0, 90.0, 3);
    close(arc[1].x, 13.535_533_905_932_738);
    close(arc[1].y, 16.464_466_094_067_262);
    let polygon = polygon_points((0.0, 0.0).into(), 1.0, 5, 0.0);
    assert_eq!(polygon.len(), 5);
    close(polygon[1].x, 0.951_056_516_295_153_5);

    let walk = resample_by_length(&[(0.0, 0.0).into(), (3.0, 0.0).into()], 1.0, false);
    assert_eq!(walk.len(), 4);
    close(walk[2].x, 2.0);

    let fragments = contact_fragments(
        &[(0.0, 0.0).into(), (12.0, 0.0).into()],
        0.5,
        3.0,
        17,
        false,
    );
    assert_eq!(fragments.len(), 2);
    close(fragments[0].points[0].x, 2.667_718_123_070_342_6);
    close(fragments[0].weight, 0.858_541_580_624_464_5);
}
