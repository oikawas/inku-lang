use std::collections::BTreeMap;

use inku_render::render::build_render_metadata;
use inku_render::svg::{Document, Element, format_number};
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, Score, SvgProfile};

fn score(json: &str) -> Score {
    serde_json::from_str(json).unwrap()
}

#[test]
fn render_boundary_is_one_owned_request_and_output_shape() {
    let request = RenderRequest {
        score: score(r#"{"instructions":[]}"#),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Display,
            render_seed: None,
            composition_seed: None,
            wild: false,
        },
    };
    assert_eq!(request.options.render_seed, None);
}

#[test]
fn texture_metadata_matches_the_visible_surface_policy() {
    let input = score(
        r#"{"canvas":{"aspect":"square","ground":{"material":"paper"}},
        "instructions":[
          {"primitive":"circle","center":[0.5,0.5],"radius":0.1,
           "surface":{"texture":"grain","density":0.4,"opacity":0.3}},
          {"primitive":"line","from":[0.1,0.1],"to":[0.9,0.9],
           "surface":{"texture":"grain"}}
        ]}"#,
    );
    let metadata = build_render_metadata(&input, SvgProfile::Compat);
    assert_eq!(metadata.render_engine_version, "41");
    assert!(metadata.texture_degraded);
    assert!(metadata.render_canvas_ground.is_some());
    assert_eq!(metadata.render_surface_textures.len(), 1);
    assert_eq!(metadata.render_surface_textures[0].instruction_index, 0);
}

#[test]
fn svg_tree_escapes_values_and_serializes_once() {
    let mut document = Document::new(CanvasSize::new(1000.0, 500.0));
    let mut group = Element::new("g").attr("id", "a&b\"c");
    group.push(Element::new("path").attr("d", "M 0 0 L 1 1"));
    group.push_text("<safe>");
    document.push(group);
    let svg = document.serialize();
    assert!(svg.contains("viewBox=\"0 0 1000 500\""));
    assert!(svg.contains("id=\"a&amp;b&quot;c\""));
    assert!(svg.contains("&lt;safe&gt;"));
    assert_eq!(svg.matches("<svg").count(), 1);
    assert_eq!(format_number(-0.0), "0");
}
