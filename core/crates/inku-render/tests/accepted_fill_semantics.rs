use std::collections::{BTreeMap, BTreeSet};

use inku_render::render::render;
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, SurfaceIntensity, SvgProfile};

fn values<'a>(svg: &'a str, attribute: &str) -> Vec<&'a str> {
    svg.split(&format!(" {attribute}=\""))
        .skip(1)
        .map(|tail| tail.split('"').next().unwrap())
        .collect()
}

#[test]
fn representative_mask_crt_shapes_and_compat_preserve_geometry_and_local_definitions() {
    let mut request = RenderRequest {
        score: serde_json::from_str(r#"{"instructions":[
          {"primitive":"circle","center":[0.25,0.25],"radius":0.16,"weight":"pen","color":"blue","filled":true},
          {"primitive":"arc","arc_form":"crescent","center":[0.7,0.25],"size":[0.35,0.3],"weight":"drypoint","color":"blue","surface":{"texture":"solid"}},
          {"primitive":"ellipse","center":[0.5,0.7],"size":[0.65,0.3],"weight":"computer","color":"blue","surface":{"texture":"solid"}}
        ]}"#).unwrap(),
        options: RenderOptions {
            resolved_color_map: BTreeMap::from([("blue".to_owned(), "#2468ac".to_owned())]),
            catalog_id: None, canvas: CanvasSize::new(1200.0, 1000.0), canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Display, render_seed: Some(431), composition_seed: None,
            wild: false, error_policy: Default::default(),
        },
    };
    let normal = render(request.clone()).unwrap().svg;
    for instruction in &mut request.score.instructions {
        instruction.surface_intensity = SurfaceIntensity::Dense;
    }
    let dense = render(request.clone()).unwrap().svg;
    assert_eq!(values(&normal, "d"), values(&dense, "d"));
    assert!(normal.contains("mask-type:alpha"));
    assert!(normal.contains("computer-crt-fill-v1"));
    assert!(normal.contains("fill-opacity=\"0.82\""));
    assert!(normal.contains("fill-opacity=\"0.62\""));
    assert!(normal.contains("fill=\"#2468ac\""));
    assert!(!normal.contains("solid-mottle"));
    assert!(!normal.contains("fill-stroke-v1"));
    assert!(normal.matches("<path").count() < 20);
    assert!(normal.len() < 90_000);
    let identifiers = values(&normal, "id");
    assert_eq!(
        identifiers.len(),
        identifiers.iter().collect::<BTreeSet<_>>().len()
    );
    assert_ne!(normal, dense);
    request.options.render_seed = Some(432);
    assert_ne!(
        values(&dense, "d"),
        values(&render(request.clone()).unwrap().svg, "d")
    );
    request.options.svg_profile = SvgProfile::Compat;
    let compat_dense = render(request.clone()).unwrap().svg;
    for instruction in &mut request.score.instructions {
        instruction.surface_intensity = SurfaceIntensity::Faint;
    }
    let compat_faint = render(request).unwrap().svg;
    assert!(!compat_dense.contains("<filter"));
    assert!(!compat_dense.contains("<mask"));
    assert!(compat_dense.contains("tool-fill-compat-v1"));
    assert!(compat_dense.contains("<pattern"));
    assert!(compat_faint.contains("opacity=\"0.35\""));
    assert_eq!(values(&compat_dense, "d"), values(&compat_faint, "d"));
    assert_ne!(compat_dense, compat_faint);
}
