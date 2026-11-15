use std::collections::BTreeMap;

use inku_render::render::render;
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, SurfaceIntensity, SvgProfile};

fn request(weight: &str, filled: bool) -> RenderRequest {
    let shape = if filled {
        format!(
            r#"{{"primitive":"circle","center":[0.5,0.5],"radius":0.25,"weight":"{weight}","color":"blue","filled":true}}"#
        )
    } else {
        format!(
            r#"{{"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5],"weight":"{weight}","color":"blue"}}"#
        )
    };
    RenderRequest {
        score: serde_json::from_str(&format!(r#"{{"instructions":[{shape}]}}"#)).unwrap(),
        options: RenderOptions {
            resolved_color_map: BTreeMap::from([("blue".to_owned(), "#2468ac".to_owned())]),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Display,
            render_seed: Some(431),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    }
}

fn hash(svg: &str) -> u64 {
    svg.bytes().fold(14695981039346656037_u64, |h, b| {
        (h ^ u64::from(b)).wrapping_mul(1099511628211)
    })
}

#[test]
fn fills_distinguish_intensities_and_normal_preserves_base_svg() {
    // FNV-1a of the unmarked SVG rendered by the engine-101 base, seed 431.
    for (weight, expected) in [
        ("watercolor", 6665294091976000007),
        ("oil_pastel", 7949877720939916216),
        ("painting_knife", 6131614728404689312),
        ("etching", 8597288176762918704),
    ] {
        let mut req = request(weight, true);
        let normal = render(req.clone()).unwrap().svg;
        assert_eq!(hash(&normal), expected, "{weight}");
        req.score.instructions[0].surface_intensity = SurfaceIntensity::Faint;
        let faint = render(req.clone()).unwrap().svg;
        req.score.instructions[0].surface_intensity = SurfaceIntensity::Dense;
        let dense = render(req).unwrap().svg;
        assert_ne!(faint, normal, "{weight}");
        assert_ne!(dense, normal, "{weight}");
        assert_ne!(faint, dense, "{weight}");
    }
}

#[test]
fn stroke_intensity_changes_its_medium() {
    for weight in ["oil_pastel", "painting_knife", "pen", "oil_paint"] {
        let mut req = request(weight, false);
        let normal = render(req.clone()).unwrap().svg;
        req.score.instructions[0].surface_intensity = SurfaceIntensity::Faint;
        let faint = render(req.clone()).unwrap().svg;
        req.score.instructions[0].surface_intensity = SurfaceIntensity::Dense;
        let dense = render(req).unwrap().svg;
        assert_ne!(normal, faint, "{weight}");
        assert_ne!(normal, dense, "{weight}");
        assert_ne!(faint, dense, "{weight}");
    }
}
