use std::collections::BTreeMap;

use inku_render::render::{build_render_metadata, render};
use inku_render::svg::{Document, Element, format_number};
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, Score, SvgProfile};

fn score(json: &str) -> Score {
    serde_json::from_str(json).unwrap()
}

#[test]
fn canonical_python_score_accepts_explicit_null_fields() {
    let input = score(
        r#"{"version":"0.1.0","canvas":{"aspect":"square","ground":null},
        "background":"white","presence":null,"instructions":[{
        "primitive":"arc","note":null,"from":null,"to":null,
        "center":[0.5,0.5],"radius":0.27,"sides":null,"position":null,
        "size":null,"angle_start":15.0,"angle_end":285.0,"rotation":null,
        "filled":false,"style":"solid","weight":"brush_thick",
        "mode":"additive","carve_depth":null,"color":"black",
        "color_hint":null,"variation":null,"arrangement":null,"at":null,
        "relation":null,"thinness":null,"surface":null}]}"#,
    );

    assert_eq!(input.instructions.len(), 1);
}

#[test]
fn canonical_python_render_request_accepts_the_reference_shape() {
    let request: RenderRequest = serde_json::from_str(
        r##"{"score":{"version":"0.1.0","canvas":{"aspect":"square","ground":null},
        "background":"white","presence":null,"instructions":[{
        "primitive":"arc","note":null,"from":null,"to":null,
        "center":[0.5,0.5],"radius":0.27,"sides":null,"position":null,
        "size":null,"angle_start":15.0,"angle_end":285.0,"rotation":null,
        "filled":false,"style":"solid","weight":"brush_thick",
        "mode":"additive","carve_depth":null,"color":"black",
        "color_hint":null,"variation":null,"arrangement":null,"at":null,
        "relation":null,"thinness":null,"surface":null}]},"options":{
        "resolved_color_map":{"white":"#ffffff","black":"#111111",
        "blue":"#2c3e91","red":"#a2342a","green":"#2f6b3a",
        "gray":"#888888"},"catalog_id":null,"canvas":{"width":1000.0,
        "height":1000.0},"canvas_aspect_id":"square",
        "svg_profile":"editable","render_seed":12345,
        "composition_seed":null,"wild":false}}"##,
    )
    .unwrap();

    assert_eq!(request.score.instructions.len(), 1);
}

#[test]
fn canonical_python_canvas_ground_accepts_the_full_explicit_shape() {
    let ground: inku_render::types::CanvasGroundSpec = serde_json::from_str(
        r#"{"material":"canvas","tone":"off_white","grain":"medium",
        "density":0.45,"opacity":0.16,"seed":13579}"#,
    )
    .unwrap();
    let input = score(
        r#"{"canvas":{"aspect":"square","ground":{"material":"canvas",
        "tone":"off_white","grain":"medium","density":0.45,
        "opacity":0.16,"seed":13579}},"instructions":[]}"#,
    );

    assert_eq!(ground.density, 0.45);
    assert!(matches!(input.canvas, inku_render::types::Canvas::Spec(_)));
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

#[test]
fn candidate_renders_every_primitive_through_one_request() {
    let request = RenderRequest {
        score: score(
            r#"{"instructions":[
              {"primitive":"line","from":[0.1,0.1],"to":[0.9,0.1],"weight":"pencil"},
              {"primitive":"circle","center":[0.2,0.3],"radius":0.06,"weight":"rotring"},
              {"primitive":"ellipse","center":[0.5,0.3],"size":[0.2,0.1],"weight":"pen"},
              {"primitive":"square","position":[0.7,0.2],"size":[0.12,0.12],"weight":"rotring"},
              {"primitive":"triangle","position":[0.1,0.55],"size":[0.15,0.15],"weight":"pen"},
              {"primitive":"polygon","center":[0.4,0.65],"radius":0.08,"sides":6,"weight":"rotring"},
              {"primitive":"arc","center":[0.65,0.65],"radius":0.1,"angle_start":20,"angle_end":150,"weight":"pen"},
              {"primitive":"cloudform","center":[0.85,0.7],"size":[0.18,0.12],"weight":"rotring"}
            ]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Compat,
            render_seed: Some(431),
            composition_seed: Some(17),
            wild: false,
        },
    };
    let first = render(request.clone()).unwrap();
    let second = render(request).unwrap();
    assert_eq!(first, second);
    assert_eq!(first.metadata.render_engine_version, "41");
    assert!(first.svg.starts_with("<svg"));
    assert!(first.svg.ends_with("</svg>"));
    assert!(first.svg.contains("stroke-engine-v1"));
    assert!(first.svg.contains("contour-stroke-v1"));
    assert!(first.svg.contains("cloudform contour-v1"));
    assert!(!first.svg.contains("NaN"));
    assert!(!first.svg.contains("<filter"));
    assert!(!first.svg.contains("<clipPath"));
}

#[test]
fn render_request_has_a_stable_json_wire_shape() {
    let request = RenderRequest {
        score: score(r#"{"instructions":[]}"#),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 500.0),
            canvas_aspect_id: "landscape".to_owned(),
            svg_profile: SvgProfile::Editable,
            render_seed: None,
            composition_seed: Some(-7),
            wild: false,
        },
    };
    let wire = serde_json::to_string(&request).unwrap();
    let decoded: RenderRequest = serde_json::from_str(&wire).unwrap();
    assert_eq!(decoded, request);
    let output = render(decoded).unwrap();
    assert!(output.svg.contains("id=\"inku_artboard\""));
    assert!(output.svg.contains("id=\"inku_metadata\""));
}

#[test]
fn abstract_presence_is_emitted_in_its_owned_layer() {
    let request = RenderRequest {
        score: score(
            r#"{"presence":{"kind":"group_like","intensity":"high",
            "symmetry":"radial","gaze_pressure":"medium","contour_density":"medium"},
            "instructions":[]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Editable,
            render_seed: Some(431),
            composition_seed: None,
            wild: false,
        },
    };
    let output = render(request).unwrap();
    let presence_layer = output.svg.find("id=\"layer_20_presence\"").unwrap();
    let presence = output.svg.find("id=\"presence_layer\"").unwrap();
    assert!(presence > presence_layer);
    assert!(output.svg[presence..].contains("<circle"));
    assert!(!output.svg.contains("NaN"));
}

#[test]
fn candidate_renders_every_surface_without_profile_only_geometry() {
    let request = RenderRequest {
        score: score(
            r#"{"instructions":[
              {"primitive":"circle","center":[0.15,0.18],"radius":0.08,"weight":"pencil","surface":{"texture":"stipple","density":0.4}},
              {"primitive":"ellipse","center":[0.40,0.18],"size":[0.16,0.11],"weight":"rotring","surface":{"texture":"paper_grain"}},
              {"primitive":"square","position":[0.60,0.10],"size":[0.16,0.16],"weight":"pen","surface":{"texture":"wash"}},
              {"primitive":"triangle","position":[0.08,0.40],"size":[0.18,0.16],"weight":"rotring","surface":{"texture":"hatch","direction":"vertical"}},
              {"primitive":"polygon","center":[0.40,0.49],"radius":0.10,"sides":6,"weight":"pencil","surface":{"texture":"crosshatch","spacing_gradient":"coarse_to_dense"}},
              {"primitive":"cloudform","center":[0.68,0.49],"size":[0.18,0.14],"weight":"pen","surface":{"texture":"aquatint","tone_steps":4}},
              {"primitive":"circle","center":[0.20,0.76],"radius":0.09,"weight":"pen","surface":{"texture":"bleed","bleed":0.5}},
              {"primitive":"square","position":[0.42,0.68],"size":[0.17,0.17],"weight":"pencil","surface":{"texture":"grain"}}
            ]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Compat,
            render_seed: Some(431),
            composition_seed: Some(17),
            wild: false,
        },
    };
    let first = render(request.clone()).unwrap();
    let second = render(request).unwrap();
    assert_eq!(first, second);
    for texture in [
        "stipple",
        "paper_grain",
        "wash",
        "hatch",
        "crosshatch",
        "aquatint",
        "bleed",
        "grain",
    ] {
        assert!(
            first.svg.contains(&format!("_{texture}\"")),
            "missing surface {texture}"
        );
    }
    assert!(first.svg.contains("<pattern"));
    assert!(first.svg.contains("surface-grain-carrier-v1"));
    assert_eq!(first.metadata.render_surface_textures.len(), 8);
    assert!(!first.svg.contains("<filter"));
    assert!(!first.svg.contains("<clipPath"));
    assert!(!first.svg.contains("NaN"));
    assert!(!first.svg.contains("inf"));
}

#[test]
fn candidate_preserves_every_ground_between_background_and_content() {
    for material in [
        "paper",
        "washi",
        "ink_wash",
        "charcoal_ground",
        "canvas",
        "drawing_paper",
        "mezzotint",
    ] {
        for profile in [
            SvgProfile::Display,
            SvgProfile::Editable,
            SvgProfile::Compat,
        ] {
            let request = RenderRequest {
                score: score(&format!(
                    r#"{{"canvas":{{"aspect":"square","ground":{{"material":"{material}","tone":"warm","grain":"medium"}}}},"instructions":[]}}"#
                )),
                options: RenderOptions {
                    resolved_color_map: BTreeMap::new(),
                    catalog_id: None,
                    canvas: CanvasSize::new(1000.0, 1000.0),
                    canvas_aspect_id: "square".to_owned(),
                    svg_profile: profile,
                    render_seed: Some(431),
                    composition_seed: None,
                    wild: false,
                },
            };
            let output = render(request).unwrap();
            let background = output.svg.find("id=\"background\"").unwrap();
            let ground = output.svg.find("id=\"layer_01_canvas_ground\"").unwrap();
            let content = output.svg.find("id=\"layer_10_content\"").unwrap();
            assert!(
                background < ground && ground < content,
                "ground order: {material}"
            );
            assert!(
                output.svg.contains("<pattern"),
                "ground pattern: {material}"
            );
            if profile == SvgProfile::Display {
                assert!(output.svg.contains("<filter"));
                assert!(output.svg.contains("url(#performance_touch_431)"));
            } else {
                assert!(!output.svg.contains("<filter"));
            }
            assert!(!output.svg.contains("<clipPath"));
            assert_eq!(
                serde_json::to_string(
                    &output
                        .metadata
                        .render_canvas_ground
                        .as_ref()
                        .unwrap()
                        .material
                )
                .unwrap(),
                format!("\"{material}\"")
            );
        }
    }
}

#[test]
fn print_tools_add_plate_tone_after_marks_only_with_a_render_seed() {
    let make_request = |render_seed| RenderRequest {
        score: score(
            r#"{"instructions":[{"primitive":"line","from":[0.1,0.2],"to":[0.9,0.8],"weight":"drypoint"}]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Compat,
            render_seed,
            composition_seed: None,
            wild: false,
        },
    };
    let seeded = render(make_request(Some(431))).unwrap();
    let mark = seeded.svg.find("stroke-engine-v1").unwrap();
    let plate = seeded.svg.find("id=\"layer_15_plate_tone\"").unwrap();
    assert!(mark < plate);
    assert!(!seeded.svg.contains("<filter"));
    assert!(
        !render(make_request(None))
            .unwrap()
            .svg
            .contains("layer_15_plate_tone")
    );
}

#[test]
fn hand_fills_are_tool_fields_while_machine_fills_remain_regions() {
    let request = RenderRequest {
        score: score(
            r#"{"instructions":[
              {"primitive":"circle","center":[0.3,0.5],"radius":0.18,"weight":"pencil","filled":true},
              {"primitive":"square","position":[0.58,0.32],"size":[0.30,0.30],"weight":"rotring","filled":true},
              {"primitive":"triangle","position":[0.10,0.10],"size":[0.16,0.16],"weight":"brush_thick","surface":{"texture":"solid"}}
            ]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Compat,
            render_seed: Some(431),
            composition_seed: None,
            wild: false,
        },
    };
    let output = render(request).unwrap();
    assert!(output.svg.contains("class=\"fill-v2\""));
    assert!(output.svg.contains("fill-stroke-v1 strokes-"));
    assert!(output.svg.contains("class=\"solid-fill-v1\""));
    assert!(output.svg.contains("<polygon"));
    assert!(!output.svg.contains("<clipPath"));
    assert!(!output.svg.contains("NaN"));
}

#[test]
fn display_owns_material_filters_but_compat_remains_filter_free() {
    let make_request = |profile| RenderRequest {
        score: score(
            r#"{"instructions":[{"primitive":"line","from":[0.1,0.2],"to":[0.9,0.8],"weight":"pencil"}]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: profile,
            render_seed: Some(431),
            composition_seed: None,
            wild: false,
        },
    };
    let display = render(make_request(SvgProfile::Display)).unwrap();
    assert!(display.svg.contains("id=\"texture-pencil\""));
    assert!(display.svg.contains("filter=\"url(#texture-pencil)\""));
    assert!(display.svg.contains("id=\"performance_touch_431\""));
    let compat = render(make_request(SvgProfile::Compat)).unwrap();
    assert!(!compat.svg.contains("<filter"));
    assert!(!compat.svg.contains("filter=\""));
}

#[test]
fn display_grain_tile_is_reusable_and_not_filtered_per_dab() {
    let request = RenderRequest {
        score: score(
            r#"{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.2,"weight":"pencil","surface":{"texture":"grain"}}]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Display,
            render_seed: Some(431),
            composition_seed: None,
            wild: false,
        },
    };
    let output = render(request).unwrap();
    let pattern_start = output.svg.find("<pattern id=\"surface_pattern_").unwrap();
    let pattern_end = pattern_start + output.svg[pattern_start..].find("</pattern>").unwrap();
    assert!(!output.svg[pattern_start..pattern_end].contains("filter=\""));
    assert!(output.svg.contains("surface-grain-carrier-v1"));
}
