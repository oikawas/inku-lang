use std::collections::BTreeSet;

use inku_render::render::render;
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, Score, SvgProfile};

fn request(scale_x: f64, scale_y: f64, profile: SvgProfile) -> RenderRequest {
    let score: Score = serde_json::from_str(&format!(
        r#"{{"version":"0.5.0","instructions":[
          {{"primitive":"line","from":[0.08,0.10],"to":[0.24,0.10],"weight":"rotring"}},
          {{"primitive":"circle","center":[0.34,0.20],"radius":0.08,"weight":"pencil","filled":true,"surface":{{"texture":"solid"}}}},
          {{"primitive":"ellipse","center":[0.58,0.20],"size":[0.18,0.10],"weight":"chalk","filled":true,"surface":{{"texture":"solid"}}}},
          {{"primitive":"square","position":[0.72,0.12],"size":[0.14,0.14],"weight":"computer","filled":true,"surface":{{"texture":"solid"}}}},
          {{"primitive":"triangle","position":[0.08,0.48],"size":[0.14,0.14],"weight":"pen"}},
          {{"primitive":"polygon","center":[0.34,0.56],"radius":0.08,"sides":5,"weight":"rotring"}},
          {{"primitive":"arc","center":[0.58,0.56],"radius":0.08,"angle_start":10,"angle_end":190,"weight":"pen"}},
          {{"primitive":"arc","arc_form":"crescent","center":[0.78,0.56],"size":[0.12,0.14],"weight":"rotring","filled":true}},
          {{"primitive":"point","center":[0.82,0.56],"radius":0.02,"weight":"pen"}},
          {{"primitive":"cloudform","center":[0.48,0.80],"size":[0.20,0.12],"weight":"pen"}}
        ],"transform_groups":[{{"start":0,"end":10,"rotation_degrees":0,"scale_x":{scale_x},"scale_y":{scale_y},"fixed_position_indices":[]}}]}}"#
    ))
    .expect("valid affine score");
    RenderRequest {
        score,
        options: RenderOptions {
            resolved_color_map: Default::default(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: profile,
            render_seed: Some(431),
            composition_seed: Some(17),
            wild: false,
            error_policy: Default::default(),
        },
    }
}

fn values(svg: &str, attribute: &str) -> BTreeSet<String> {
    svg.split(&format!(" {attribute}=\""))
        .skip(1)
        .map(|tail| tail.split('"').next().expect("attribute value").to_owned())
        .collect()
}

#[test]
fn affine_geometry_changes_all_primitives_but_keeps_material_metrics_physical() {
    let base = render(request(1.0, 1.0, SvgProfile::Editable))
        .expect("base SVG")
        .svg;
    let uniform = render(request(2.0, 2.0, SvgProfile::Editable))
        .expect("uniform affine SVG")
        .svg;
    let nonuniform = render(request(2.0, 0.5, SvgProfile::Editable))
        .expect("nonuniform affine SVG")
        .svg;

    for svg in [&uniform, &nonuniform] {
        assert!(!svg.contains("NaN"));
        assert!(!svg.contains("inf"));
        assert!(svg.contains("mark_000_line_black"));
        assert!(svg.contains("mark_009_cloudform_black"));
        assert!(svg.contains("baseFrequency=\""));
        assert!(svg.contains("width=\"3\""));
        assert!(svg.contains("height=\"8\""));
    }
    assert_ne!(base, uniform);
    assert_ne!(uniform, nonuniform);
    assert_ne!(values(&base, "stroke-width"), BTreeSet::new());
    assert_eq!(
        values(&base, "stroke-width"),
        values(&uniform, "stroke-width")
    );
    assert_eq!(
        values(&base, "stroke-width"),
        values(&nonuniform, "stroke-width")
    );
    assert_eq!(
        values(&base, "baseFrequency"),
        values(&uniform, "baseFrequency")
    );
    assert_eq!(
        values(&base, "baseFrequency"),
        values(&nonuniform, "baseFrequency")
    );

    for (scale_x, scale_y) in [(2.0, 0.5), (0.0, 1.0), (-1.0, 0.5)] {
        for profile in [
            SvgProfile::Editable,
            SvgProfile::Compat,
            SvgProfile::Display,
        ] {
            let svg = render(request(scale_x, scale_y, profile))
                .expect("finite affine SVG for every profile")
                .svg;
            assert!(svg.starts_with("<svg"));
            assert!(!svg.contains("NaN"));
            assert!(!svg.contains("inf"));
        }
    }
}
