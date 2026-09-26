//! The live profile: editable's groups and IDs with display's appearance.

use std::collections::BTreeMap;

use inku_render::render::render;
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, Score, Seed, SvgProfile};

// A textured tool, a print tool (which adds a plate tone) and a scatter, so
// that one instruction draws several marks.
const SCORE: &str = r#"{"instructions":[
    {"primitive":"circle","center":[0.3,0.3],"radius":0.12,"filled":true,
     "weight":"pencil","color":"blue"},
    {"primitive":"line","from":[0.1,0.8],"to":[0.9,0.7],"weight":"burin",
     "color":"black"},
    {"primitive":"square","position":[0.55,0.2],"size":[0.12,0.12],
     "weight":"chalk","color":"green",
     "arrangement":{"count":3,"layout":"scatter"}}
]}"#;

fn svg(profile: SvgProfile, canvas: CanvasSize, render_seed: Option<Seed>) -> String {
    let score: Score = serde_json::from_str(SCORE).unwrap();
    render(RenderRequest {
        score,
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas,
            canvas_aspect_id: "square".to_owned(),
            svg_profile: profile,
            render_seed,
            composition_seed: Some(7),
            wild: false,
            error_policy: Default::default(),
        },
    })
    .unwrap()
    .svg
}

/// Remove every span that starts with `open` and ends with the next `close`.
fn remove_spans(svg: &str, open: &str, close: &str) -> String {
    let mut out = String::with_capacity(svg.len());
    let mut rest = svg;
    while let Some(start) = rest.find(open) {
        out.push_str(&rest[..start]);
        let end = start + rest[start..].find(close).expect("closed span") + close.len();
        rest = &rest[end..];
    }
    out.push_str(rest);
    out
}

/// Empty the bodies of the title, description and metadata elements.
fn without_document_text(svg: &str) -> String {
    let mut out = svg.to_owned();
    for (open, close) in [
        ("<title>", "</title>"),
        ("<desc>", "</desc>"),
        ("<metadata id=\"inku_metadata\">", "</metadata>"),
    ] {
        let start = out.find(open).expect("document text") + open.len();
        let end = start + out[start..].find(close).unwrap();
        out.replace_range(start..end, "");
    }
    out
}

#[test]
fn live_is_editable_plus_the_display_filters() {
    let canvas = CanvasSize::new(1000.0, 1000.0);
    let live = svg(SvgProfile::Live, canvas, Some(431));
    let editable = svg(SvgProfile::Editable, canvas, Some(431));

    assert!(live.contains("{\"generator\":\"inku\",\"svg_profile\":\"live\"}"));
    let mut stripped = without_document_text(&live);
    for (open, close) in [
        ("<filter id=\"texture-", "</filter>"),
        ("<filter id=\"performance_touch_", "</filter>"),
        (" filter=\"url(#texture-", ")\""),
        (" filter=\"url(#performance_touch_", ")\""),
    ] {
        stripped = remove_spans(&stripped, open, close);
    }
    assert_eq!(stripped, without_document_text(&editable));
}

#[test]
fn every_live_instruction_group_carries_the_canvas_touch() {
    // A wide canvas, so that a swapped width and height would show.
    let live = svg(SvgProfile::Live, CanvasSize::new(1200.0, 800.0), Some(431));

    assert_eq!(live.matches("<filter id=\"performance_touch_").count(), 1);
    assert!(live.contains(
        "filterUnits=\"userSpaceOnUse\" x=\"-24\" y=\"-16\" width=\"1248\" height=\"832\""
    ));
    // The opening tag that starts at `start`.
    let tag = |start: usize| &live[start..start + live[start..].find('>').unwrap()];
    let groups: Vec<_> = live
        .match_indices("<g id=\"instruction_")
        .map(|(start, _)| tag(start))
        .collect();
    assert_eq!(groups.len(), 3);
    let plate_tone = tag(live.find("<rect id=\"layer_15_plate_tone\"").unwrap());
    for opening in groups.iter().chain([&plate_tone]) {
        assert!(
            opening.contains("filter=\"url(#performance_touch_"),
            "{opening}"
        );
    }
    assert!(!tag(live.find("<g id=\"layer_10_content\"").unwrap()).contains("filter="));
    assert!(live.contains("filter=\"url(#texture-pencil)\""));
}
