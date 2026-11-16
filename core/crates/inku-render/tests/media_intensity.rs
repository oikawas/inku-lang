use std::collections::BTreeMap;

use inku_render::render::render;
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, SurfaceIntensity, SvgProfile};
use inku_score::math::DetFloat;

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

// Read the actual 8-bit SVG pigments, so gamut handling and rounding are checked too.
fn oklch(color: &str) -> (f64, f64, f64) {
    let channel = |at| {
        let v = f64::from(u8::from_str_radix(&color[at..at + 2], 16).unwrap()) / 255.0;
        if v <= 0.04045 {
            v / 12.92
        } else {
            ((v + 0.055) / 1.055).dpowf(2.4)
        }
    };
    let (r, g, b) = (channel(1), channel(3), channel(5));
    let l = (0.412_221_470_8 * r + 0.536_332_536_3 * g + 0.051_445_992_9 * b).dcbrt();
    let m = (0.211_903_498_2 * r + 0.680_699_545_1 * g + 0.107_396_956_6 * b).dcbrt();
    let s = (0.088_302_461_9 * r + 0.281_718_837_6 * g + 0.629_978_700_5 * b).dcbrt();
    let lightness = 0.210_454_255_3 * l + 0.793_617_785_0 * m - 0.004_072_046_8 * s;
    let a = 1.977_998_495_1 * l - 2.428_592_205_0 * m + 0.450_593_709_9 * s;
    let b = 0.025_904_037_1 * l + 0.782_771_766_2 * m - 0.808_675_766_0 * s;
    (lightness, a.dhypot(b), b.datan2(a).to_degrees())
}

#[test]
fn dense_fill_layers_keep_pigment_in_bounded_oklch() {
    for (ground, name, color) in [("paper", "blue", "#2c3e91"), ("washi", "red", "#a2342a")] {
        let (base_l, base_c, base_h) = oklch(color);
        for (weight, class) in [
            ("oil_pastel", "pastel-dense-pigment-layer"),
            ("painting_knife", "knife-dense-pigment-ridge"),
        ] {
            let mut req = request(weight, true);
            req.score = serde_json::from_value(serde_json::json!({
                "canvas": {"ground": {"material": ground}},
                "instructions": [{"primitive":"circle", "center":[0.5,0.5], "radius":0.36,
                    "weight":weight, "color":name, "filled":true, "surface_intensity":"dense"}]
            }))
            .unwrap();
            req.options.resolved_color_map = BTreeMap::from([(name.to_owned(), color.to_owned())]);
            let svg = render(req).unwrap().svg;
            let mut count = 0;
            let mut darker = false;
            let mut lighter = false;
            for path in svg
                .split("<path ")
                .filter(|part| part.split('>').next().unwrap().contains(class))
            {
                let tag = path.split('>').next().unwrap();
                let pigment = tag
                    .split(" stroke=\"")
                    .nth(1)
                    .unwrap()
                    .split('"')
                    .next()
                    .unwrap();
                let (l, c, h) = oklch(pigment);
                let hue_delta = ((h - base_h + 180.0).rem_euclid(360.0) - 180.0).abs();
                assert!(
                    hue_delta <= 2.0,
                    "{ground} {weight}: {pigment} hue {hue_delta}"
                );
                assert!(
                    c + 0.000_002 >= base_c,
                    "{ground} {weight}: {pigment} chroma {c} < {base_c}"
                );
                assert!(
                    l >= base_l - (base_l * 0.20).min(0.10) - 0.000_002
                        && l <= base_l + 0.06 + 0.000_002,
                    "{ground} {weight}: {pigment} lightness {l} from {base_l}"
                );
                assert!(
                    (0.15..=0.95).contains(&l),
                    "{ground} {weight}: {pigment} lightness {l}"
                );
                darker |= l < base_l - 0.005;
                lighter |= l > base_l + 0.005;
                count += 1;
            }
            assert!(
                count > 0 && darker,
                "{ground} {weight}: missing dense pigment"
            );
            if weight == "painting_knife" {
                assert!(lighter, "{ground}: missing light ridge");
            }
        }
    }
}
