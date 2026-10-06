//! The pure part, without Skia (CI runs it).
//!
//! C2: each compatibility rewrite does what it should on a small SVG.
//! C6: the current core, drawing the public DDL, writes nothing outside the support table.

use std::collections::BTreeMap;

use inku_ddl::MacroDefinition;
use inku_display::{DisplayError, Rewrites, display_svg};
use inku_pipeline::core_boundary::{
    ClipPolicy, CompilerOptions, compile_committed, render_delivery,
};
use inku_pipeline::machine::{PipelineRenderOptions, VisibleDocument};
use serde_json::Value;

fn compat(name: &str) -> String {
    std::fs::read_to_string(format!(
        "{}/tests/data/compat/{name}.svg",
        env!("CARGO_MANIFEST_DIR")
    ))
    .expect("compat SVG")
}

#[test]
fn pattern_and_use_href_become_xlink_href() {
    for (name, count) in [
        ("pattern-href", 1),
        ("use-href", 3),
        ("alpha-mask-white", 1),
    ] {
        let display = display_svg(&compat(name)).unwrap();
        assert_eq!(display.rewrites.href, count, "{name}");
        assert!(!display.svg.contains(" href="), "{name}");
        assert_eq!(
            display.svg.matches(" xlink:href=\"#").count(),
            count,
            "{name}"
        );
        assert!(display.svg.starts_with(
            "<svg xmlns:xlink=\"http://www.w3.org/1999/xlink\" xmlns=\"http://www.w3.org/2000/svg\""
        ));
    }
}

#[test]
fn an_ellipse_becomes_the_same_path() {
    let display = display_svg(&compat("ellipse-gradient")).unwrap();
    assert_eq!(
        display.rewrites,
        Rewrites {
            href: 0,
            ellipse: 1,
            seed: 0
        }
    );
    let path = display.svg.find("<path ").expect("a path");
    let tag = &display.svg[path..path + display.svg[path..].find("/>").unwrap()];
    assert!(tag.contains(" d=\"M 20 100 A 80 45 0 1 0 180 100 A 80 45 0 1 0 20 100 Z\""));
    assert!(tag.contains(" fill=\"url(#g)\""));
    assert!(!display.svg.contains("ellipse"));
}

#[test]
fn a_large_seed_becomes_the_integer_blink_reads() {
    let display = display_svg(&compat("seed")).unwrap();
    assert_eq!(
        display.rewrites,
        Rewrites {
            href: 0,
            ellipse: 0,
            seed: 1
        }
    );
    assert!(display.svg.contains(" seed=\"253038816\""));
}

/// The control: Skia reads every mask as luminance, so an alpha mask that draws grey
/// would come out fainter than in Chrome. Such a work goes to resvg.
#[test]
fn an_alpha_mask_that_is_not_white_is_left_to_resvg() {
    assert!(display_svg(&compat("alpha-mask-white")).is_ok());
    match display_svg(&compat("alpha-mask-gray")) {
        Err(DisplayError::Unsupported(unsupported)) => {
            assert_eq!(unsupported.code, "alpha_mask_content");
        }
        other => panic!("grey alpha mask accepted: {other:?}"),
    }
}

#[test]
fn what_the_table_does_not_hold_is_left_to_resvg() {
    let head = r#"<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">"#;
    for (body, code) in [
        ("<text>a</text>", "element"),
        (
            r#"<rect width="1" height="1" stroke-dashoffset="1"/>"#,
            "attribute",
        ),
        (r#"<rect width="1" height="1" style="fill:red"/>"#, "style"),
        (
            r##"<defs><pattern id="p" width="1" height="1"/></defs>"##,
            "pattern_units",
        ),
        (r##"<defs><linearGradient id="g"/></defs>"##, "element"),
        (r##"<line x2="5" stroke="url(#g)"/>"##, "bounding_box"),
        (r##"<use href="#missing"/>"##, "reference"),
        (
            r#"<ellipse cx="5" cy="5" rx="50%" ry="2"/>"#,
            "ellipse_geometry",
        ),
        (
            r#"<filter id="f"><feTurbulence seed="1.5"/></filter>"#,
            "seed",
        ),
    ] {
        match display_svg(&format!("{head}{body}</svg>")) {
            Err(DisplayError::Unsupported(unsupported)) => {
                assert_eq!(unsupported.code, code, "{body}")
            }
            other => panic!("{body}: {other:?}"),
        }
    }
}

/// C6. The public DDL chosen in stage 1 makes the core write every compatibility case.
/// Drawn again by the current core, through the same compile and render boundary the
/// macOS app uses and with the inputs it built, none of it may fall outside the table.
#[test]
fn the_current_core_draws_the_public_ddl_inside_the_table() {
    let fixture: Value = serde_json::from_str(include_str!("data/public-requests.json"))
        .expect("the fixture is JSON");
    let shared = &fixture["shared"];
    let definitions: Vec<MacroDefinition> =
        serde_json::from_value(shared["definitions"].clone()).expect("macro definitions");
    let clip: ClipPolicy = serde_json::from_value(shared["clip"].clone()).expect("clip policy");
    let mut totals = Rewrites::default();
    let mut compared = 0;
    let mut written = BTreeMap::<&str, usize>::new();
    for work in fixture["works"].as_array().expect("works") {
        let id = work["id"].as_str().unwrap();
        let mut compiler = shared["compiler"].clone();
        compiler["host"] = work["host"].clone();
        let compiler: CompilerOptions = serde_json::from_value(compiler).expect("compiler options");
        let document: VisibleDocument = serde_json::from_value(serde_json::json!({
            "source": work["ddl"],
            "language": work["language"],
            "macro_locks": shared["macro_locks"],
            "saijiki": shared["saijiki"],
        }))
        .expect("visible document");
        let delivery = compile_committed(
            document.document().expect("current document"),
            &definitions,
            &compiler,
        )
        .unwrap_or_else(|error| panic!("{id}: {error}"));
        let options: PipelineRenderOptions =
            serde_json::from_value(work["render_options"].clone()).expect("render options");
        let output = render_delivery(&delivery, options.into(), &compiler, clip)
            .unwrap_or_else(|error| panic!("{id}: {error}"));
        for (case, needle) in [
            ("pattern href", "<pattern "),
            ("use href", "<use href="),
            ("alpha mask", "mask-type:alpha"),
            ("stitchTiles", "stitchTiles=\"stitch\""),
            ("ellipse", "<ellipse "),
        ] {
            if output.svg.contains(needle) {
                *written.entry(case).or_default() += 1;
            }
        }
        let display = display_svg(&output.svg).unwrap_or_else(|error| panic!("{id}: {error}"));
        totals.href += display.rewrites.href;
        totals.ellipse += display.rewrites.ellipse;
        totals.seed += display.rewrites.seed;
        compared += 1;
    }
    assert_eq!(compared, 17);
    // The material still reaches every case the table and the rewrites are for.
    for case in [
        "pattern href",
        "use href",
        "alpha mask",
        "stitchTiles",
        "ellipse",
    ] {
        assert!(
            written.get(case).is_some_and(|works| *works > 0),
            "no public work writes {case}: {written:?}"
        );
    }
    assert!(
        totals.href > 0 && totals.ellipse > 0 && totals.seed > 0,
        "{totals:?}"
    );
}
