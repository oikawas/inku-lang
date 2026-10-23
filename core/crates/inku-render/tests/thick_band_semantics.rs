//! Thick bands (render engine 92): a thick sweep line's fine streaks, a closed
//! face's few, and every filter of a drawing computed in sRGB.

use std::collections::BTreeMap;

use inku_render::render::render;
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, SvgProfile};

fn drawing(instructions: &str) -> String {
    render(RenderRequest {
        score: serde_json::from_str(&format!(r#"{{"instructions":[{instructions}]}}"#)).unwrap(),
        options: RenderOptions {
            resolved_color_map: BTreeMap::from([("black".to_owned(), "#141210".to_owned())]),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Display,
            render_seed: Some(2176722393071345),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    })
    .unwrap()
    .svg
}

#[test]
fn a_thick_sweep_line_carries_fine_streaks_and_a_swept_face_keeps_its_few() {
    let svg = drawing(
        r#"{"primitive":"line","from":[0.1,0.3],"to":[0.9,0.3],"weight":"brush_thick","thinness":"extra_thick","color":"black","surface":{"texture":"sweep"}},
           {"primitive":"circle","center":[0.5,0.7],"radius":0.2,"weight":"brush_thick","color":"black","surface":{"texture":"sweep"}}"#,
    );
    // The extra-thick line's band is 66 units wide: one fine streak for every
    // four units, rounded, and none of the few.
    assert_eq!(svg.matches("flat-brush-streak-fine-v1").count(), 17);
    // The swept face's passes keep their few streaks.
    assert!(
        svg.contains("flat-brush-streak-dark-v1") || svg.contains("flat-brush-streak-light-v1")
    );
}

#[test]
fn every_filter_of_a_drawing_computes_in_srgb() {
    let svg = drawing(
        r#"{"primitive":"line","from":[0.1,0.2],"to":[0.9,0.2],"weight":"brush_thick","thinness":"thick","color":"black","surface":{"texture":"sweep"}},
           {"primitive":"circle","center":[0.3,0.6],"radius":0.15,"weight":"chalk","color":"black","surface":{"texture":"sweep"}},
           {"primitive":"arc","arc_form":"crescent","center":[0.7,0.6],"size":[0.3,0.25],"weight":"drypoint","color":"black","surface":{"texture":"solid"}},
           {"primitive":"line","from":[0.1,0.9],"to":[0.9,0.9],"weight":"pencil","color":"black"}"#,
    );
    let filters = svg
        .split("<filter ")
        .skip(1)
        .map(|tail| tail.split('>').next().unwrap())
        .collect::<Vec<_>>();
    // The tools' texture filters, a swept face's film and a drypoint's burr,
    // the three that computed in linearRGB before render engine 92.
    for id in [
        "id=\"texture-brush_thick\"",
        "id=\"texture-chalk\"",
        "id=\"texture-pencil\"",
        "id=\"surface_soft_",
        "-burr\"",
    ] {
        assert!(filters.iter().any(|filter| filter.contains(id)), "{id}");
    }
    for filter in &filters {
        assert!(
            filter.contains("color-interpolation-filters=\"sRGB\""),
            "{filter}"
        );
    }
}
