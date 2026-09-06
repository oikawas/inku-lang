use std::collections::BTreeMap;

use inku_render::palette::{
    PaletteObservationError, default_color_map, render_effect_hint, resolve_color,
    work_color_assignment, work_palette_context,
};
use inku_render::types::Color;

fn map() -> BTreeMap<String, String> {
    [
        ("white", "#ffffff"),
        ("black", "#111111"),
        ("gray", "#888888"),
        ("red", "#a2342a"),
        ("orange", "#a95a00"),
        ("yellow", "#a18308"),
        ("green", "#2f6b3a"),
        ("blue", "#2c3e91"),
        ("purple", "#583a84"),
        ("palette:z", "#ff0000"),
        ("palette:a", "#ee2200"),
        ("palette:b", "#00aa00"),
        ("palette:c", "#101010"),
        ("palette:d", "#f8f8f8"),
        ("palette:e", "#777777"),
    ]
    .into_iter()
    .map(|(key, value)| (key.to_owned(), value.to_owned()))
    .collect()
}

#[test]
fn work_assignment_matches_engine_40_seed_selection() {
    let colors = map();
    let assignment = work_color_assignment(&colors, Some(431), Some("fixture"));
    assert_eq!(assignment["black"], "#101010");
    assert_eq!(assignment["gray"], "#777777");
    assert_eq!(assignment["white"], "#f8f8f8");
    assert_eq!(assignment["red"], "#ee2200");
    assert_eq!(assignment["yellow"], "#00aa00");
    assert_eq!(assignment["purple"], "#ff0000");
}

#[test]
fn nuance_and_effect_hints_keep_distinct_ownership() {
    let colors = map();
    let assignment = work_color_assignment(&colors, Some(431), Some("fixture"));
    assert_eq!(
        resolve_color(Color::Black, Some("桜色"), &colors, &assignment),
        "#ee2200"
    );
    assert_eq!(
        resolve_color(Color::Black, Some("brown umber"), &colors, &assignment),
        "#ee2200"
    );
    assert_eq!(
        render_effect_hint(Some("soft light and reflection")),
        Some("soft light; reflection".to_owned())
    );
    assert_eq!(render_effect_hint(Some("青緑の霧")), Some("霧".to_owned()));
}

#[test]
fn score_lowering_palette_context_observes_the_existing_actual_assignment() {
    let colors = map();
    let context = work_palette_context(&colors, Some(431), Some("fixture"), Color::Red).unwrap();
    assert_eq!(context.background().abstract_color(), Color::Red);
    assert_eq!(context.background().concrete_rgb(), [0xee, 0x22, 0x00]);
    assert_eq!(context.black().abstract_color(), Color::Black);
    assert_eq!(context.black().concrete_rgb(), [0x10, 0x10, 0x10]);
    assert_eq!(context.white().abstract_color(), Color::White);
    assert_eq!(context.white().concrete_rgb(), [0xf8, 0xf8, 0xf8]);
    for lightness in [
        context.background().oklch_lightness(),
        context.black().oklch_lightness(),
        context.white().oklch_lightness(),
    ] {
        assert!(lightness.is_finite() && (0.0..=1.0).contains(&lightness));
    }

    let neutral = default_color_map();
    let neutral_context = work_palette_context(&neutral, None, None, Color::White).unwrap();
    assert_eq!(
        neutral_context.background().concrete_rgb(),
        [0xff, 0xff, 0xff]
    );
    assert_eq!(neutral_context.black().concrete_rgb(), [0x11, 0x11, 0x11]);
    assert_eq!(neutral_context.white().concrete_rgb(), [0xff, 0xff, 0xff]);
}

#[test]
fn score_lowering_palette_context_rejects_an_unobservable_concrete_color() {
    let mut colors = default_color_map();
    colors.insert("black".to_owned(), "not-a-color".to_owned());
    assert_eq!(
        work_palette_context(&colors, None, None, Color::White),
        Err(PaletteObservationError::InvalidResolvedColor {
            abstract_color: Color::Black,
        })
    );
}
