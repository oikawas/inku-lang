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
            error_policy: Default::default(),
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
    assert_eq!(metadata.render_engine_version, "44");
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
fn engine_renders_every_primitive_through_one_request() {
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
            error_policy: Default::default(),
        },
    };
    let first = render(request.clone()).unwrap();
    let second = render(request).unwrap();
    assert_eq!(first, second);
    assert_eq!(first.metadata.render_engine_version, "44");
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
fn wide_canvas_square_rotation_uses_the_physical_center() {
    let request = RenderRequest {
        score: score(
            r#"{"instructions":[{"primitive":"square","position":[0.45,0.4],
            "size":[0.2,0.2],"rotation":30,"weight":"rotring"}]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1_000.0, 500.0),
            canvas_aspect_id: "wide".to_owned(),
            svg_profile: SvgProfile::Compat,
            render_seed: Some(431),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    };
    let output = render(request).unwrap();
    assert!(output.svg.contains("rotate(30 500 250)"));
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
            error_policy: Default::default(),
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
fn connected_stop_returns_no_output_and_continue_reports_original_indices() {
    let connected_score = score(
        r#"{"instructions":[
        {"primitive":"line","from":[0.1,0.2],"to":[0.4,0.2],"color":"red"},
        {"primitive":"line","from":[0.5,0.2],"to":[0.8,0.2],"color":"blue",
         "relation":{"type":"connected","target_instruction_index":0,"position_authority":"numeric_fixed"}},
        {"primitive":"point","center":[0.7,0.5],"radius":0.006,"color":"green",
         "relation":{"type":"connected","target_instruction_index":1,"position_authority":"named_movable"}},
        {"primitive":"point","center":[0.8,0.8],"radius":0.006,"color":"black"}
        ]}"#,
    );
    let options = RenderOptions {
        resolved_color_map: BTreeMap::new(),
        catalog_id: None,
        canvas: CanvasSize::new(1000.0, 1000.0),
        canvas_aspect_id: "square".to_owned(),
        svg_profile: SvgProfile::Editable,
        render_seed: Some(31),
        composition_seed: None,
        wild: false,
        error_policy: Default::default(),
    };

    let stopped = render(RenderRequest {
        score: connected_score.clone(),
        options: options.clone(),
    });
    assert!(matches!(
        stopped,
        Err(inku_render::render::RenderError::CheckedPerformance(_))
    ));

    let mut continued_options = options;
    continued_options.error_policy = inku_render::types::ScoreErrorPolicy::OmitAndContinue;
    let continued = render(RenderRequest {
        score: connected_score,
        options: continued_options,
    })
    .expect("independent instructions render with omission metadata");
    assert!(continued.svg.contains("instruction_000_line_red"));
    assert!(continued.svg.contains("instruction_003_point_black"));
    assert!(!continued.svg.contains("instruction_001_line_blue"));
    assert!(!continued.svg.contains("instruction_002_point_green"));
    let execution = continued.metadata.execution.expect("typed omissions");
    assert_eq!(execution.rendered_instruction_indices, [0, 3]);
    assert_eq!(execution.diagnostics.len(), 2);
}

#[test]
fn connected_elsewhere_keeps_composite_svg_ids_on_expanded_drawing_ordinals() {
    let request = RenderRequest {
        score: score(
            r#"{"instructions":[
            {"primitive":"square","position":[0.35,0.4],"size":[0.2,0.2],"weight":"pencil",
             "arrangement":{"count":2,"group_size":2,"layout":"radial","center":[0.5,0.5],
                            "radius":0.25,"color_cycle":["blue","red"]}},
            {"primitive":"circle","center":[0.45,0.5],"radius":0.03,"weight":"pencil"},
            {"primitive":"line","from":[0.1,0.8],"to":[0.3,0.8]},
            {"primitive":"line","from":[0.6,0.8],"to":[0.8,0.8],
             "relation":{"type":"connected","target_instruction_index":2,
                         "position_authority":"numeric_fixed"}},
            {"primitive":"point","center":[0.8,0.2],"radius":0.006}
            ]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1_000.0, 500.0),
            canvas_aspect_id: "wide".to_owned(),
            svg_profile: SvgProfile::Editable,
            render_seed: Some(41),
            composition_seed: Some(17),
            wild: false,
            error_policy: inku_render::types::ScoreErrorPolicy::OmitAndContinue,
        },
    };

    let output = render(request).expect("composite and independent Connected pair render");
    for id in [
        "instruction_000_square_blue",
        "instruction_001_circle_blue",
        "instruction_002_square_red",
        "instruction_003_circle_red",
        "instruction_004_line_black",
        "instruction_006_point_black",
        "mark_000_000_square",
        "mark_001_000_circle",
        "mark_002_000_square",
        "mark_003_000_circle",
        "mark_004_000_line",
        "mark_006_000_point",
    ] {
        assert_eq!(
            output.svg.matches(&format!("id=\"{id}\"")).count(),
            1,
            "missing or duplicate SVG id {id}"
        );
    }
    assert!(!output.svg.contains("instruction_005_line_black"));
    assert!(!output.svg.contains("mark_005_000_line"));
    let execution = output.metadata.execution.expect("typed Connected omission");
    assert_eq!(execution.rendered_instruction_indices, [0, 1, 0, 1, 2, 4]);
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
            error_policy: Default::default(),
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
fn engine_renders_every_surface_without_profile_only_geometry() {
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
            error_policy: Default::default(),
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
fn engine_preserves_every_ground_between_background_and_content() {
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
                    error_policy: Default::default(),
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
            error_policy: Default::default(),
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
            error_policy: Default::default(),
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
            error_policy: Default::default(),
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
            error_policy: Default::default(),
        },
    };
    let output = render(request).unwrap();
    let pattern_start = output.svg.find("<pattern id=\"surface_pattern_").unwrap();
    let pattern_end = pattern_start + output.svg[pattern_start..].find("</pattern>").unwrap();
    assert!(!output.svg[pattern_start..pattern_end].contains("filter=\""));
    assert!(output.svg.contains("surface-grain-carrier-v1"));
}

#[test]
fn solid_fill_profile_boundary_keeps_base_and_scopes_mottle() {
    let make_request = |profile| RenderRequest {
        score: score(
            r#"{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.25,"weight":"pen","filled":true,"surface":{"texture":"solid"}}]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: profile,
            render_seed: Some(2718),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    };
    for profile in [SvgProfile::Display, SvgProfile::Editable] {
        let output = render(make_request(profile)).unwrap();
        assert!(output.svg.contains("class=\"solid-base-fill-v1\""));
        assert!(output.svg.contains("class=\"solid-mottle-overlay-v1\""));
        assert!(output.svg.contains("baseFrequency=\"0.035000\""));
        assert!(output.svg.contains("tableValues=\"0.310000 1\""));
    }
    let compat = render(make_request(SvgProfile::Compat)).unwrap();
    assert!(compat.svg.contains("class=\"solid-base-fill-v1\""));
    assert!(!compat.svg.contains("solid-mottle-overlay-v1"));
    assert!(!compat.svg.contains("<filter"));
}

#[test]
fn computer_solid_remains_a_periodic_fill_field() {
    let request = RenderRequest {
        score: score(
            r#"{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.25,"weight":"computer","filled":true,"surface":{"texture":"solid"}}]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Editable,
            render_seed: Some(2718),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    };
    let output = render(request).unwrap();
    assert!(output.svg.contains("fill-stroke-v1 strokes-"));
    assert!(!output.svg.contains("solid-mottle-overlay-v1"));
}

#[test]
fn tiny_hand_fill_is_one_dab_instead_of_scanlines() {
    let request = RenderRequest {
        score: score(
            r#"{"instructions":[{"primitive":"circle","center":[0.5,0.5],"radius":0.005,"weight":"pen","filled":true}]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Editable,
            render_seed: Some(12345),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    };
    let output = render(request).unwrap();
    assert!(output.svg.contains("class=\"fill-dab-v1\""));
    assert!(!output.svg.contains("fill-stroke-v1 strokes-"));
}

#[test]
fn compat_grain_omits_the_nonportable_pattern_class() {
    let request = RenderRequest {
        score: score(
            r#"{"instructions":[{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"weight":"pen","filled":true,"surface":{"texture":"grain"}}]}"#,
        ),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Compat,
            render_seed: Some(73),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    };
    let output = render(request).unwrap();
    assert!(output.svg.contains("<pattern"));
    assert!(!output.svg.contains("class=\"surface-grain-pattern-v1\""));
    assert!(!output.svg.contains("<filter"));
}
