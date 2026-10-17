//! Chalk powder catches on the paper's tooth (render engine 85): one tooth for
//! the whole work, deepened by a rough support, two crossing passes of the
//! hand, and a thin film of powder under the piled powder.

use inku_render::render::render;
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, Score, SvgProfile};

fn svg(canvas: &str, instructions: &str) -> String {
    let score: Score = serde_json::from_str(&format!(
        r#"{{"version":"0.17.0",{canvas}"instructions":[{instructions}]}}"#
    ))
    .expect("valid score");
    render(RenderRequest {
        score,
        options: RenderOptions {
            resolved_color_map: Default::default(),
            catalog_id: None,
            canvas: CanvasSize::new(1000.0, 1000.0),
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Editable,
            render_seed: Some(85),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    })
    .expect("rendered SVG")
    .svg
}

fn circle(weight: &str, center: &str, intensity: &str) -> String {
    format!(
        r#"{{"primitive":"circle","center":{center},"radius":0.15,"filled":true,"weight":"{weight}","color":"yellow"{intensity}}}"#
    )
}

/// The tool-fill filters of the SVG, in document order.
fn fill_filters(svg: &str) -> Vec<&str> {
    svg.split("<filter id=\"tool-fill-")
        .skip(1)
        .map(|tail| &tail[..tail.find("</filter>").expect("end of the filter")])
        .collect()
}

/// The value of `name` on the first element of the filter carrying `marker`.
fn attribute<'a>(filter: &'a str, marker: &str, name: &str) -> &'a str {
    let at = filter.find(marker).unwrap_or_else(|| panic!("no {marker}"));
    let element = &filter[filter[..at].rfind('<').expect("element start")..];
    let element = &element[..element.find('>').expect("element end")];
    element
        .split(&format!(" {name}=\""))
        .nth(1)
        .and_then(|tail| tail.split('"').next())
        .unwrap_or_else(|| panic!("no {name} on {marker}"))
}

#[test]
fn two_chalk_fills_of_a_work_read_one_paper_tooth() {
    let drawn = svg(
        "",
        &format!(
            "{},{}",
            circle("chalk", "[0.3,0.3]", ""),
            circle("chalk", "[0.7,0.7]", "")
        ),
    );
    let filters = fill_filters(&drawn);
    assert_eq!(filters.len(), 2);
    assert_eq!(
        attribute(filters[0], "result=\"tooth\"", "seed"),
        attribute(filters[1], "result=\"tooth\"", "seed")
    );
    assert_ne!(
        attribute(filters[0], "result=\"press0\"", "seed"),
        attribute(filters[1], "result=\"press0\"", "seed")
    );
}

#[test]
fn a_rougher_support_deepens_the_tooth() {
    let weight = |material: &str| {
        let drawn = svg(
            &format!(r#""canvas":{{"aspect":"square","ground":{{"material":"{material}"}}}},"#),
            &circle("chalk", "[0.5,0.5]", ""),
        );
        let filters = fill_filters(&drawn);
        assert_eq!(filters.len(), 1);
        attribute(filters[0], "result=\"catchAlpha0\"", "k2")
            .parse::<f64>()
            .expect("k2")
    };
    assert_eq!(weight("paper"), 0.6);
    assert!((weight("drawing_paper") - 0.84).abs() < 1e-9);
}

#[test]
fn chalk_weighs_alpha_only_fields_and_lays_a_film_by_intensity() {
    let film = |intensity: &str| {
        let drawn = svg(
            "",
            &circle(
                "chalk",
                "[0.5,0.5]",
                &format!(r#","surface_intensity":"{intensity}""#),
            ),
        );
        let filters = fill_filters(&drawn);
        assert_eq!(filters.len(), 1);
        let filter = filters[0];
        // feComposite's arithmetic works on premultiplied colour, so the
        // fields are weighed as alpha-only images.
        for pass in ["0", "1"] {
            let marker = format!("result=\"catchAlpha{pass}\"");
            assert_eq!(attribute(filter, &marker, "in"), "toothAlpha");
            assert_eq!(
                attribute(filter, &marker, "in2"),
                format!("pressAlpha{pass}")
            );
        }
        let tail = &filter[filter.find("result=\"filmDeposit\"").expect("film")..];
        let film = &tail[tail.find("<feFuncA").expect("film function")..];
        film.split(" intercept=\"")
            .nth(1)
            .and_then(|tail| tail.split('"').next())
            .expect("film intercept")
            .parse::<f64>()
            .expect("film")
    };
    assert_eq!(film("dense"), 0.45);
    assert_eq!(film("normal"), 0.35);
    assert_eq!(film("faint"), 0.2);
}

#[test]
fn crayon_fill_keeps_its_grain() {
    let drawn = svg("", &circle("crayon", "[0.5,0.5]", ""));
    let filters = fill_filters(&drawn);
    assert_eq!(filters.len(), 1);
    assert!(filters[0].contains("result=\"fine\""));
    assert!(filters[0].contains("result=\"coarse\""));
    assert!(!filters[0].contains("result=\"tooth\""));
}
