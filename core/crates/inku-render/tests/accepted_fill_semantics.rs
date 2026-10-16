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
    assert!(!compat_dense.contains("<clipPath"));
    assert!(!compat_dense.contains("clip-path="));
    assert!(compat_dense.contains("tool-fill-compat-v1"));
    assert!(compat_dense.contains("computer-crt-fill-v1"));
    assert!(compat_dense.contains("<pattern"));
    assert!(compat_dense.contains("tool-fill-2-0-grille"));
    assert!(compat_dense.contains("tool-fill-2-0-scanlines"));
    assert!(compat_faint.contains("opacity=\"0.35\""));
    assert_eq!(values(&compat_dense, "d"), values(&compat_faint, "d"));
    assert_ne!(compat_dense, compat_faint);
}

#[test]
fn brush_fills_share_one_band_tile_and_rotate_it_per_mark() {
    let request = RenderRequest {
        score: serde_json::from_str(r#"{"instructions":[
          {"primitive":"circle","center":[0.3,0.3],"radius":0.12,"weight":"brush_thin","color":"blue","filled":true},
          {"primitive":"square","position":[0.6,0.2],"size":[0.2,0.2],"weight":"brush_thin","color":"blue","filled":true},
          {"primitive":"circle","center":[0.5,0.7],"radius":0.15,"weight":"brush_thick","color":"blue","filled":true}
        ]}"#).unwrap(),
        options: RenderOptions {
            resolved_color_map: BTreeMap::from([("blue".to_owned(), "#2468ac".to_owned())]),
            catalog_id: None, canvas: CanvasSize::new(1000.0, 1000.0), canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Display, render_seed: Some(431), composition_seed: None,
            wild: false, error_policy: Default::default(),
        },
    };
    let svg = render(request.clone()).unwrap().svg;
    // One tile per brush, however many marks use it; no per-mark grain filter.
    assert_eq!(svg.matches("id=\"brush-tile-brush_thin\"").count(), 1);
    assert_eq!(svg.matches("id=\"brush-tile-brush_thick\"").count(), 1);
    assert!(!svg.contains("feTurbulence type=\"fractalNoise\" baseFrequency=\"0.11 0.002\""));
    assert_eq!(svg.matches("href=\"#brush-tile-brush_thin\"").count(), 2);
    assert_eq!(svg.matches("href=\"#brush-tile-brush_thick\"").count(), 1);
    let rotations: BTreeSet<_> = values(&svg, "patternTransform").into_iter().collect();
    assert_eq!(rotations.len(), 3);
    assert_eq!(svg, render(request.clone()).unwrap().svg);
    let mut compat = request;
    compat.options.svg_profile = SvgProfile::Compat;
    assert!(!render(compat).unwrap().svg.contains("brush-tile-"));
}

/// The text of the element that opens at `start`, through its matching end.
fn element_at(svg: &str, start: usize) -> &str {
    let mut depth = 0usize;
    let mut index = start;
    loop {
        let open = index + svg[index..].find('<').unwrap();
        let close = open + svg[open..].find('>').unwrap();
        let tag = &svg[open..=close];
        if tag.starts_with("</") {
            depth -= 1;
        } else if !tag.ends_with("/>") {
            depth += 1;
        }
        index = close + 1;
        if depth == 0 {
            return &svg[start..index];
        }
    }
}

#[test]
fn a_faint_fill_keeps_its_density_on_the_face_and_draws_its_edge_after_it() {
    // Render engine 83: a faint flat fill is see-through behind a clear edge.
    let mut request = RenderRequest {
        score: serde_json::from_str(r#"{"instructions":[
          {"primitive":"circle","center":[0.2,0.3],"radius":0.12,"weight":"rotring","color":"blue","filled":true},
          {"primitive":"circle","center":[0.5,0.3],"radius":0.12,"weight":"pen","color":"blue","filled":true},
          {"primitive":"circle","center":[0.8,0.3],"radius":0.12,"weight":"brush_thin","color":"blue","filled":true}
        ]}"#).unwrap(),
        options: RenderOptions {
            resolved_color_map: BTreeMap::from([("blue".to_owned(), "#2468ac".to_owned())]),
            catalog_id: None, canvas: CanvasSize::new(1000.0, 1000.0), canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Display, render_seed: Some(431), composition_seed: None,
            wild: false, error_policy: Default::default(),
        },
    };
    let normal = render(request.clone()).unwrap().svg;
    for instruction in &mut request.score.instructions {
        instruction.surface_intensity = SurfaceIntensity::Faint;
    }
    let faint = render(request).unwrap().svg;
    // The rotring's face holds its opacity, the pen's its grain filter and the
    // thin brush's its mask; each edge is the tool's faint line opacity.
    for (normal_face, faint_face, edge, opacity) in [
        (
            r#"<g opacity="0.9">"#,
            r#"<g opacity="0.3">"#,
            "<circle ",
            r#"stroke-opacity="0.5225""#,
        ),
        (
            r#"<g filter="url(#tool-fill-1-0)">"#,
            r#"<g filter="url(#tool-fill-1-0)">"#,
            r#"<g class="contour-stroke-v1"#,
            r#"fill-opacity="0.55""#,
        ),
        (
            r#"<g mask="url(#tool-fill-2-0-mask)">"#,
            r#"<g mask="url(#tool-fill-2-0-mask)">"#,
            r#"<g class="contour-stroke-v1"#,
            r#"fill-opacity="0.495""#,
        ),
    ] {
        let start = faint.find(faint_face).unwrap();
        let face = element_at(&faint, start);
        assert!(
            !face.contains(edge),
            "{faint_face}: the edge is outside the face"
        );
        let after = start + face.len();
        assert!(
            faint[after..].starts_with(edge),
            "{faint_face}: the edge follows the face"
        );
        assert!(
            element_at(&faint, after).contains(opacity),
            "{faint_face}: {opacity}"
        );
        // A fill at its usual intensity keeps the edge inside its face.
        let face = element_at(&normal, normal.find(normal_face).unwrap());
        assert!(
            face.contains(edge),
            "{normal_face}: the edge is inside the face"
        );
    }
}
