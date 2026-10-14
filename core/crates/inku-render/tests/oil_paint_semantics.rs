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
    // Bristle marks counted for normal, dense and faint.
    let mut marks = [0_usize; 3];
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
            let expected_opacity = if index >= 2 && intensity == SurfaceIntensity::Faint {
                0.54
            } else {
                1.0
            };
            // The selected pigment and its bristle marks share one deposited-paint opacity.
            assert!(
                (attr(group, "opacity").parse::<f64>().unwrap() - expected_opacity).abs() < 0.00001
            );
            let shadows = elements(group, "path", "oil-paint-ridge-shadow-v1");
            let lights = elements(group, "path", "oil-paint-ridge-light-v1");
            // A pass carries at most five seeded marks and one lit partner; an
            // outline at most two and the partner. Never the old four full pairs.
            assert!(shadows.len() + lights.len() <= if outline { 3 } else { 6 });
            let (body_lightness, body_chroma, body_hue) = oklch(attr(body, "fill"));
            for (ridges, darker) in [(shadows, true), (lights, false)] {
                for ridge in ridges {
                    let (lightness, chroma, hue) = oklch(attr(ridge, "fill"));
                    // A mark steps a little in lightness and keeps the pigment's
                    // colour: no greying towards black, no mixing with white.
                    let step = lightness - body_lightness;
                    assert!(if darker { step < 0.0 } else { step > 0.0 }, "{step}");
                    assert!(step.abs() <= 0.08, "{step}");
                    assert!(chroma >= body_chroma * 0.85, "{chroma} {body_chroma}");
                    let turn = (hue - body_hue + 540.0).rem_euclid(360.0) - 180.0;
                    assert!(turn.abs() <= 6.0, "{turn}");
                    marks[match intensity {
                        SurfaceIntensity::Normal => 0,
                        SurfaceIntensity::Dense => 1,
                        SurfaceIntensity::Faint => 2,
                    }] += 1;
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
    // Dense lays one more mark on each pass, and some passes a lit partner.
    assert!(marks[0] > 0);
    assert_eq!(marks[2], marks[0], "{marks:?}");
    assert!(marks[1] > marks[0], "{marks:?}");
    assert!(tags(dense, "path").len() > tags(normal, "path").len());
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

/// OKLCH lightness, chroma and hue (degrees) of a `#rrggbb` colour.
fn oklch(color: &str) -> (f64, f64, f64) {
    let [r, g, b] = rgb(color).map(|channel| {
        let channel = channel / 255.0;
        if channel <= 0.04045 {
            channel / 12.92
        } else {
            ((channel + 0.055) / 1.055).powf(2.4)
        }
    });
    let l = (0.412_221_470_8 * r + 0.536_332_536_3 * g + 0.051_445_992_9 * b).cbrt();
    let m = (0.211_903_498_2 * r + 0.680_699_545_1 * g + 0.107_396_956_6 * b).cbrt();
    let s = (0.088_302_461_9 * r + 0.281_718_837_6 * g + 0.629_978_700_5 * b).cbrt();
    let lightness = 0.210_454_255_3 * l + 0.793_617_785_0 * m - 0.004_072_046_8 * s;
    let a = 1.977_998_495_1 * l - 2.428_592_205_0 * m + 0.450_593_709_9 * s;
    let b = 0.025_904_037_1 * l + 0.782_771_766_2 * m - 0.808_675_766_0 * s;
    (
        lightness,
        a.hypot(b),
        b.atan2(a).to_degrees().rem_euclid(360.0),
    )
}
