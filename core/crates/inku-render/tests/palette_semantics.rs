use std::collections::BTreeMap;

use inku_render::palette::{render_effect_hint, resolve_color, work_color_assignment};
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
