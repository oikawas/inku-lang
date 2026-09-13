use std::collections::BTreeMap;

use inku_render::render::render;
use inku_render::stroke::{StrokeRequest, synthesize_stroke};
use inku_render::support::DEFAULT_SUPPORT;
use inku_render::types::{
    CanvasSize, Point, RenderOptions, RenderRequest, SurfaceIntensity, SvgProfile, Weight,
};

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
fn oil_accepted_intensities_preserve_pigment_and_shape_without_compat_clipping() {
    let score = serde_json::from_str(
        r#"{"instructions":[
          {"primitive":"line","from":[0.1,0.1],"to":[0.9,0.1],"weight":"oil_paint","color":"blue"},
          {"primitive":"arc","center":[0.5,0.35],"radius":0.15,"angle_start":0,"angle_end":180,"weight":"oil_paint","color":"blue"},
          {"primitive":"circle","center":[0.3,0.7],"radius":0.18,"weight":"oil_paint","color":"blue","surface":{"texture":"solid"}},
          {"primitive":"polygon","center":[0.8,0.7],"radius":0.019,"sides":3,"rotation":23,"weight":"oil_paint","color":"blue","filled":true}
        ]}"#,
    ).unwrap();
    let request = RenderRequest {
        score,
        options: RenderOptions {
            resolved_color_map: BTreeMap::from([("blue".to_owned(), "#2468ac".to_owned())]),
            catalog_id: None,
            canvas: CanvasSize::new(1200.0, 800.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Compat,
            render_seed: Some(431),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    };
    let mut results = Vec::new();
    for intensity in [
        SurfaceIntensity::Normal,
        SurfaceIntensity::Dense,
        SurfaceIntensity::Faint,
    ] {
        let mut current = request.clone();
        for instruction in current.score.instructions.iter_mut().skip(2) {
            instruction.surface_intensity = intensity;
        }
        let svg = render(current).unwrap().svg;
        let bases = elements(&svg, "path", "oil-paint-fill-body-v1");
        assert_eq!(bases.len(), 2);
        assert!(!svg.contains("<clipPath"));
        assert!(!svg.contains("clip-path="));
        assert!(!svg.contains("oil-intensity-width-field-v1"));
        for base in &bases {
            assert_eq!(attr(base, "fill"), "#2468ac");
        }
        let groups = svg
            .split("<g class=\"oil-paint-stroke-v1\"")
            .skip(1)
            .map(|tail| tail.split_once("</g>").unwrap().0)
            .collect::<Vec<_>>();
        assert!(groups.len() > 4);
        for (index, group) in groups.iter().enumerate() {
            let body = elements(group, "path", "oil-paint-body-v1")[0];
            let outline = attr(body, "fill-rule") == "evenodd";
            let relief = if index < 2 {
                1.0
            } else {
                (if intensity == SurfaceIntensity::Dense {
                    1.75
                } else {
                    1.0
                }) * if outline { 1.0 } else { 0.6 }
            };
            let expected_opacity = if index >= 2 && intensity == SurfaceIntensity::Faint {
                0.54
            } else {
                1.0
            };
            // The selected pigment and ridge banks share one deposited-paint opacity.
            assert!(
                (attr(group, "opacity").parse::<f64>().unwrap() - expected_opacity).abs() < 0.00001
            );
            for (class, shade) in [
                ("oil-paint-ridge-shadow-v1", -0.23 * relief),
                ("oil-paint-ridge-light-v1", 0.20 * relief),
            ] {
                let ridges = elements(group, "path", class);
                assert_eq!(ridges.len(), 4);
                for ridge in ridges {
                    for (base, value) in rgb(attr(body, "fill"))
                        .into_iter()
                        .zip(rgb(attr(ridge, "fill")))
                    {
                        let expected = if shade < 0.0 {
                            base * (1.0 + shade)
                        } else {
                            base + (255.0 - base) * shade
                        };
                        assert!((value - expected).abs() <= 0.500001);
                    }
                }
            }
        }
        assert!(!svg.contains("solid-mottle"));
        assert!(!svg.contains("<filter"));
        assert!(!svg.contains("NaN"));
        assert!(svg.matches("<path").count() < 1000);
        results.push(svg);
    }
    let [normal, dense, faint] = &results[..] else {
        unreachable!()
    };
    for class in ["oil-paint-fill-body-v1", "oil-paint-body-v1"] {
        assert_eq!(
            elements(normal, "path", class),
            elements(dense, "path", class)
        );
        assert_eq!(
            elements(normal, "path", class),
            elements(faint, "path", class)
        );
    }
    assert_eq!(
        elements(normal, "g", "oil-paint-fill-v1"),
        elements(faint, "g", "oil-paint-fill-v1")
    );
    assert_eq!(
        elements(normal, "g", "oil-intensity-width-field-v1"),
        elements(dense, "g", "oil-intensity-width-field-v1")
    );
    assert_eq!(tags(normal, "path"), tags(faint, "path"));
    assert_eq!(tags(normal, "path").len(), tags(dense, "path").len());
    assert!(dense.matches(" L ").count() < normal.matches(" L ").count());
    assert!(dense.len() < normal.len());
}

fn tags<'a>(svg: &'a str, name: &str) -> Vec<&'a str> {
    svg.split(&format!("<{name} "))
        .skip(1)
        .map(|tail| tail.split_once('>').unwrap().0)
        .collect()
}

fn elements<'a>(svg: &'a str, name: &str, class: &str) -> Vec<&'a str> {
    tags(svg, name)
        .into_iter()
        .filter(|tag| tag.contains(&format!("class=\"{class}\"")))
        .collect()
}

fn attr<'a>(tag: &'a str, name: &str) -> &'a str {
    tag.split_once(&format!("{name}=\""))
        .unwrap()
        .1
        .split_once('"')
        .unwrap()
        .0
}

fn rgb(color: &str) -> [f64; 3] {
    [1, 3, 5].map(|start| f64::from(u8::from_str_radix(&color[start..start + 2], 16).unwrap()))
}
