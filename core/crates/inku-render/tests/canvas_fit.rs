//! Fitting a declared ratio into the paper (render engine 93): the composition
//! is drawn in a centred frame of its ratio, the paper keeps the document, the
//! background and the ground, and nothing is cut at the frame.

use std::collections::BTreeMap;

use inku_render::render::render;
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, SvgProfile};

const MARKS: &str = r#"{"primitive":"circle","center":[0.3,0.4],"radius":0.1,"weight":"pen","color":"black"},
    {"primitive":"line","from":[0.1,0.9],"to":[0.9,0.1],"weight":"brush_thick","color":"black","surface":{"texture":"sweep"}},
    {"primitive":"square","position":[0.7,0.6],"size":[0.2,0.2],"weight":"chalk","color":"black"}"#;

fn drawing(canvas: &str, paper: CanvasSize, aspect: &str, profile: SvgProfile) -> String {
    render(RenderRequest {
        score: serde_json::from_str(&format!(
            r#"{{"canvas":{canvas},"instructions":[{MARKS}]}}"#
        ))
        .unwrap(),
        options: RenderOptions {
            resolved_color_map: BTreeMap::from([("black".to_owned(), "#141210".to_owned())]),
            catalog_id: None,
            canvas: paper,
            canvas_aspect_id: aspect.to_owned(),
            svg_profile: profile,
            render_seed: Some(2176722393071345),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    })
    .unwrap()
    .svg
}

const FITTED: &str = r#"{"aspect":"square","declared_ratio":{"width_units":16,"height_units":9},"fit":"contain","ground":{"material":"washi"}}"#;
const FRAME_PAPER: &str = r#"{"aspect":"hd_monitor","declared_ratio":{"width_units":16,"height_units":9},"ground":{"material":"washi"}}"#;

/// The text of the first element with this id, through its closing tag.
fn element<'a>(svg: &'a str, id: &str) -> &'a str {
    let start = svg.find(&format!("id=\"{id}\"")).expect(id);
    let start = svg[..start].rfind('<').unwrap();
    let mut depth = 0usize;
    let mut index = start;
    while let Some(offset) = svg[index..].find('<') {
        let at = index + offset;
        let close = svg[at..].find('>').unwrap() + at;
        let tag = &svg[at..=close];
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
    panic!("unclosed {id}");
}

#[test]
fn a_fitted_frame_draws_what_the_declared_paper_draws_moved_to_the_middle() {
    // A 16:9 frame in a 1000 square is 1000 x 562.5: the marks are the marks of
    // a 1000 x 562.5 paper, 218.75 down.
    let fitted = drawing(
        FITTED,
        CanvasSize::new(1000.0, 1000.0),
        "square",
        SvgProfile::Compat,
    );
    let framed = drawing(
        FRAME_PAPER,
        CanvasSize::new(1000.0, 562.5),
        "hd_monitor",
        SvgProfile::Compat,
    );
    let frame = element(&fitted, "inku_fitted_frame");
    assert!(
        frame.starts_with(r#"<g id="inku_fitted_frame" transform="translate(0 218.75)">"#),
        "{frame}"
    );
    assert!(frame.contains(element(&framed, "layer_10_content")));
    // The paper keeps the document and the ground.
    assert!(fitted.contains(r#"viewBox="0 0 1000 1000""#));
    assert!(element(&fitted, "background").contains(r#"width="1000" height="1000""#));
}

#[test]
fn marks_reach_the_paper_and_are_not_cut_at_the_frame() {
    let fitted = drawing(
        FITTED,
        CanvasSize::new(1000.0, 1000.0),
        "square",
        SvgProfile::Display,
    );
    // The whole-drawing touch covers the paper in the frame's units: 2% beyond
    // the paper's 1000 x 1000, which starts 218.75 above the frame.
    let touch = fitted
        .split("<filter ")
        .skip(1)
        .find(|tail| tail.starts_with("id=\"performance_touch_"))
        .unwrap();
    let touch = touch.split('>').next().unwrap();
    assert!(
        touch.contains(r#"x="-20" y="-238.75" width="1040" height="1040""#),
        "{touch}"
    );
    // No clip is added at the frame.
    assert_eq!(
        fitted.matches("<clipPath").count(),
        drawing(
            FRAME_PAPER,
            CanvasSize::new(1000.0, 562.5),
            "hd_monitor",
            SvgProfile::Display
        )
        .matches("<clipPath")
        .count()
    );
}

#[test]
fn a_declaration_without_a_fit_draws_as_an_undeclared_score() {
    let paper = CanvasSize::new(1000.0, 1000.0);
    let declared = drawing(
        r#"{"aspect":"square","declared_ratio":{"width_units":16,"height_units":9}}"#,
        paper,
        "square",
        SvgProfile::Display,
    );
    assert_eq!(
        declared,
        drawing(r#""square""#, paper, "square", SvgProfile::Display)
    );
    assert!(!declared.contains("inku_fitted_frame"));
}

#[test]
fn a_fit_needs_a_declared_ratio_and_a_host_sends_no_bleed() {
    let request = |canvas: &str, paper: CanvasSize| RenderRequest {
        score: serde_json::from_str(&format!(
            r#"{{"canvas":{canvas},"instructions":[{MARKS}]}}"#
        ))
        .unwrap(),
        options: RenderOptions {
            resolved_color_map: BTreeMap::new(),
            catalog_id: None,
            canvas: paper,
            canvas_aspect_id: "square".to_owned(),
            svg_profile: SvgProfile::Display,
            render_seed: Some(1),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    };
    assert!(
        render(request(
            r#"{"aspect":"square","fit":"contain"}"#,
            CanvasSize::new(1000.0, 1000.0)
        ))
        .is_err()
    );
    let mut paper = CanvasSize::new(1000.0, 1000.0);
    paper.bleed.x = 10.0;
    assert!(render(request(r#""square""#, paper)).is_err());
}
