use std::collections::BTreeMap;

use inku_render::render::render;
use inku_render::stroke::{StrokeRequest, synthesize_stroke};
use inku_render::support::DEFAULT_SUPPORT;
use inku_render::types::{CanvasSize, Point, RenderOptions, RenderRequest, SvgProfile, Weight};

#[test]
fn oil_retains_loaded_ends_and_a_seeded_body_distinct_from_ink_brush() {
    let request = StrokeRequest {
        start: Point::new(0.0, 0.0),
        end: Point::new(200.0, 30.0),
        base_width: 12.0,
        weight: Weight::OilPaint,
        seed: 431,
        sample_count: 49,
        wild: false,
        grid_step: 0.0,
        support: DEFAULT_SUPPORT,
    };
    let oil = synthesize_stroke(request);
    assert_eq!(oil, synthesize_stroke(request));
    let brush = synthesize_stroke(StrokeRequest {
        weight: Weight::BrushThick,
        ..request
    });
    assert_ne!(oil.outline, brush.outline);
    assert!(oil.samples[0].width > brush.samples[0].width * 4.0);
    assert_eq!(oil.samples[0].point, request.start);
    assert_eq!(oil.samples.last().unwrap().point, request.end);
    assert!(oil.cuts.iter().all(|cut| !cut));
    assert_ne!(
        oil.outline,
        synthesize_stroke(StrokeRequest {
            seed: 432,
            ..request
        })
        .outline
    );
}

#[test]
fn oil_relief_survives_all_profiles_for_lines_arcs_and_large_and_small_fills() {
    let score = serde_json::from_str(
        r#"{"instructions":[
          {"primitive":"line","from":[0.1,0.1],"to":[0.9,0.1],"weight":"oil_paint","color":"blue"},
          {"primitive":"arc","center":[0.5,0.35],"radius":0.15,"angle_start":0,"angle_end":180,"weight":"oil_paint","color":"blue"},
          {"primitive":"circle","center":[0.3,0.7],"radius":0.18,"weight":"oil_paint","color":"blue","surface":{"texture":"solid"}},
          {"primitive":"circle","center":[0.8,0.7],"radius":0.009,"weight":"oil_paint","color":"blue","filled":true}
        ]}"#,
    ).unwrap();
    let request = RenderRequest {
        score,
        options: RenderOptions {
            resolved_color_map: BTreeMap::from([("blue".to_owned(), "#2468ac".to_owned())]),
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
    let compat = render(request.clone()).unwrap().svg;
    assert_eq!(compat, render(request.clone()).unwrap().svg);
    let mut changed_seed = request.clone();
    changed_seed.options.render_seed = Some(432);
    assert_ne!(compat, render(changed_seed).unwrap().svg);
    for profile in [
        SvgProfile::Display,
        SvgProfile::Editable,
        SvgProfile::Compat,
    ] {
        let mut current = request.clone();
        current.options.svg_profile = profile;
        let svg = if profile == SvgProfile::Compat {
            compat.clone()
        } else {
            render(current).unwrap().svg
        };
        assert_eq!(svg.matches("class=\"oil-paint-fill-v1\"").count(), 2);
        assert!(svg.matches("oil-paint-ridge-shadow-v1").count() > 16);
        assert_eq!(
            svg.matches("oil-paint-ridge-shadow-v1").count(),
            svg.matches("oil-paint-ridge-light-v1").count()
        );
        assert!(svg.contains("fill=\"#2468ac\""));
        assert!(svg.contains("fill=\"#1c5084\""));
        assert!(svg.contains("fill=\"#5086bd\""));
        assert!(!svg.contains("solid-mottle"));
        assert!(!svg.contains("<clipPath"));
        assert!(!svg.contains("NaN"));
        assert!(svg.matches("<path").count() < 1000);
        if profile != SvgProfile::Display {
            assert!(!svg.contains("<filter"));
        }
    }
    let mut brush = request;
    for instruction in &mut brush.score.instructions {
        instruction.weight = Weight::BrushThick;
    }
    let brush_svg = render(brush).unwrap().svg;
    assert!(!brush_svg.contains("oil-paint-"));
    assert!(brush_svg.contains("solid-fill-v1"));
}
