//! Measure parsing and rasterization separately without changing the SVG.
//! Usage: raster-profile <svg> <maximum-side-px> <iterations> [output.png]

use std::{env, fs, time::Instant};

use resvg::{tiny_skia, usvg};
use sha2::{Digest, Sha256};

fn main() {
    let args: Vec<_> = env::args().collect();
    assert!((4..=5).contains(&args.len()), "see usage in source");
    let svg = fs::read_to_string(&args[1]).expect("SVG input");
    let side: f32 = args[2].parse().expect("maximum side");
    let iterations: usize = args[3].parse().expect("iterations");
    assert!(side > 0.0 && side <= 8192.0 && iterations > 0);
    for iteration in 0..iterations {
        let started = Instant::now();
        let tree = usvg::Tree::from_str(&svg, &usvg::Options::default()).expect("parse SVG");
        let parse_ms = started.elapsed().as_secs_f64() * 1000.0;
        let scale = side / tree.size().width().max(tree.size().height());
        let width = (tree.size().width() * scale).round().max(1.0) as u32;
        let height = (tree.size().height() * scale).round().max(1.0) as u32;
        let started = Instant::now();
        let mut pixmap = tiny_skia::Pixmap::new(width, height).expect("pixel allocation");
        resvg::render(
            &tree,
            tiny_skia::Transform::from_scale(scale, scale),
            &mut pixmap.as_mut(),
        );
        let render_ms = started.elapsed().as_secs_f64() * 1000.0;
        let digest: String = Sha256::digest(pixmap.data())
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect();
        println!(
            "iteration={iteration} size={width}x{height} parse_ms={parse_ms:.3} render_ms={render_ms:.3} sha256={digest}"
        );
        if iteration + 1 == iterations && args.len() == 5 {
            pixmap.save_png(&args[4]).expect("PNG output");
        }
    }
}
