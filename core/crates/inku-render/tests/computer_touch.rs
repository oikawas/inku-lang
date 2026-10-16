//! The computer draws its marks by lattice cells alone (render engine 84): the
//! remainder of sampling of render engines 13 to 40, without the mark's body.

use inku_render::render::render;
use inku_render::types::{CanvasSize, RenderOptions, RenderRequest, Score, SvgProfile};

/// The lattice step on a 1000px square canvas: its short side times 0.018.
const STEP: f64 = 18.0;

fn svg(instruction: &str) -> String {
    let score: Score = serde_json::from_str(&format!(
        r#"{{"version":"0.5.0","instructions":[{instruction}]}}"#
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
            render_seed: Some(84),
            composition_seed: None,
            wild: false,
            error_policy: Default::default(),
        },
    })
    .expect("rendered SVG")
    .svg
}

/// The SVG's one mark group of `class`, which must not hold another group.
fn mark<'a>(svg: &'a str, class: &str) -> &'a str {
    let open = format!("<g class=\"{class}");
    assert_eq!(svg.matches(&open).count(), 1, "one {class} group");
    let start = svg.find(&open).expect("mark group");
    let end = start + svg[start..].find("</g>").expect("end of the mark group");
    let mark = &svg[start..end];
    assert!(
        !mark[1..].contains("<g"),
        "the mark group holds another group"
    );
    mark
}

fn attribute(element: &str, name: &str) -> f64 {
    element
        .split(&format!(" {name}=\""))
        .nth(1)
        .and_then(|tail| tail.split('"').next())
        .unwrap_or_else(|| panic!("no {name}"))
        .parse()
        .unwrap_or_else(|_| panic!("{name} is not a number"))
}

/// The mark's cells as (column, row, tone), in the order they are laid.
fn cells(mark: &str) -> Vec<(f64, f64, f64)> {
    mark.split("<rect ")
        .skip(1)
        .filter(|rect| rect.starts_with("class=\"raster-bleed\""))
        .map(|rect| {
            assert_eq!(attribute(rect, "width"), STEP);
            assert_eq!(attribute(rect, "height"), STEP);
            let column = (attribute(rect, "x") + STEP / 2.0) / STEP;
            let row = (attribute(rect, "y") + STEP / 2.0) / STEP;
            assert!(
                (column - column.round()).abs() < 1.0e-9 && (row - row.round()).abs() < 1.0e-9,
                "a cell off the lattice: {rect}"
            );
            (column.round(), row.round(), attribute(rect, "fill-opacity"))
        })
        .collect()
}

fn lattice(value: f64) -> f64 {
    (value / STEP).round_ties_even()
}

fn assert_joined(cells: &[(f64, f64, f64)], closed: bool) {
    let mut pairs = cells.iter().zip(cells.iter().skip(1)).collect::<Vec<_>>();
    if closed {
        pairs.push((cells.last().expect("cells"), &cells[0]));
    }
    for (a, b) in pairs {
        assert!(
            (a.0 - b.0).abs().max((a.1 - b.1).abs()) <= 1.0,
            "cells {a:?} and {b:?} leave an empty cell between them"
        );
    }
}

#[test]
fn a_computer_line_is_drawn_by_its_lattice_cells_alone() {
    let svg = svg(r#"{"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5],"weight":"computer"}"#);
    let mark = mark(&svg, "stroke-engine-v1");
    assert!(!mark.contains("<path"), "a computer line draws no body");
    let controls: usize = mark
        .split("controls-")
        .nth(1)
        .and_then(|tail| tail.split(' ').next())
        .and_then(|count| count.parse().ok())
        .expect("the stroke's control count");
    let cells = cells(mark);
    assert!(
        cells.len() >= controls,
        "{} cells for {controls} points",
        cells.len()
    );
    for &(_, _, tone) in &cells {
        assert!((0.15..=0.45).contains(&tone), "tone {tone}");
    }
    assert_joined(&cells, false);
    let (first, last) = (cells[0], cells[cells.len() - 1]);
    assert_eq!((first.0, first.1), (lattice(100.0), lattice(500.0)));
    assert_eq!((last.0, last.1), (lattice(900.0), lattice(500.0)));
}

#[test]
fn a_computer_square_keeps_its_corners_and_closes_its_ring() {
    let svg =
        svg(r#"{"primitive":"square","position":[0.3,0.3],"size":[0.4,0.4],"weight":"computer"}"#);
    let mark = mark(&svg, "contour-stroke-v1");
    assert!(!mark.contains("<path"), "a computer contour draws no body");
    let cells = cells(mark);
    assert_joined(&cells, true);
    for (x, y) in [
        (300.0, 300.0),
        (700.0, 300.0),
        (700.0, 700.0),
        (300.0, 700.0),
    ] {
        assert!(
            cells
                .iter()
                .any(|cell| (cell.0, cell.1) == (lattice(x), lattice(y))),
            "no cell at the corner ({x}, {y})"
        );
    }
}

#[test]
fn a_dotted_computer_line_keeps_its_thin_marker() {
    let svg = svg(
        r#"{"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5],"weight":"computer","style":"dotted"}"#,
    );
    let mark = mark(&svg, "stroke-engine-v1");
    assert!(!mark.contains("<path"));
    assert!(!cells(mark).is_empty());
    let marker = mark.split("<line ").nth(1).expect("the line-style marker");
    assert!(marker.contains("stroke-dasharray=\""), "{marker}");
}

#[test]
fn a_pen_line_keeps_its_body_and_lays_no_cells() {
    let svg = svg(r#"{"primitive":"line","from":[0.1,0.5],"to":[0.9,0.5],"weight":"pen"}"#);
    let mark = mark(&svg, "stroke-engine-v1");
    assert!(mark.contains("<path"));
    assert!(!svg.contains("raster-bleed"));
}
