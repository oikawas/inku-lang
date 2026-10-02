//! Bounded native release comparison for repeated sizes and export tiles.
//! Usage: prepared-scene-profile <public-filter-fixture.svg> [iterations=3]

use std::{env, fs, time::Instant};
use inku_svg_raster::{RasterOptions, RasterRegionOptions, prepare_scene, rasterize, rasterize_region};
use sha2::{Digest, Sha256};

fn dense_public_scene() -> String {
    let mut svg = String::from(r##"<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="0 0 1000 1000"><defs><clipPath id="page"><rect x="10" y="10" width="980" height="980"/></clipPath></defs><g clip-path="url(#page)" fill="none" stroke="#345a70" stroke-width="0.7">"##);
    for index in 0..6000 {
        let x = 10 + (index * 17 % 970); let y = 10 + (index * 31 % 970);
        svg.push_str(&format!("<path d=\"M{x} {y}q5 -3 11 2t13 -1\"/>"));
    }
    svg.push_str("</g></svg>"); svg
}

fn digest(bytes: &[u8]) -> String { Sha256::digest(bytes).iter().map(|byte| format!("{byte:02x}")).collect() }

fn profile(svg: &str, label: &str, iterations: usize, tile_height: u32, tile_side: u32) {
    for iteration in 0..iterations {
        let started = Instant::now();
        let scene = prepare_scene(svg).expect("prepared scene");
        let prepare_ms = started.elapsed().as_secs_f64() * 1000.0;
        let mut once_ms = 0.0; let mut prepared_ms = 0.0;
        let mut hashes = Vec::new();
        for side in [96, 384, 768, 1024] {
            let options = RasterOptions { target_width: Some(side), target_height: Some(side) };
            let started = Instant::now(); let once = rasterize(svg, options).expect("one-shot");
            once_ms += started.elapsed().as_secs_f64() * 1000.0;
            let started = Instant::now(); let prepared = scene.rasterize(options).expect("reuse");
            prepared_ms += started.elapsed().as_secs_f64() * 1000.0;
            assert_eq!(once, prepared, "prepared pixel mismatch at {side}");
            hashes.push(digest(&prepared.pixels));
        }
        println!("label={label} workload=thumbnail-canvas iteration={iteration} source_bytes={} cache_cost_bytes={} prepare_ms={prepare_ms:.3} one_shot_ms={once_ms:.3} reused_render_ms={prepared_ms:.3} prepared_total_ms={:.3} identical=true final_sha256={}",
                 scene.source_bytes(), scene.cache_cost_bytes(), prepare_ms + prepared_ms, hashes.last().unwrap());
        let width = (scene.intrinsic_width() / scene.intrinsic_height() * f64::from(tile_height)).round().max(1.0) as u32;
        let mut once_ms = 0.0; let mut prepared_ms = 0.0; let mut tiles = 0;
        for y in (0..tile_height).step_by(tile_side as usize) {
            for x in (0..width).step_by(tile_side as usize) {
                let region = RasterRegionOptions { full_width: width, full_height: tile_height, x, y, width: tile_side.min(width - x), height: tile_side.min(tile_height - y) };
                let started = Instant::now(); let once = rasterize_region(svg, region).expect("one-shot tile");
                once_ms += started.elapsed().as_secs_f64() * 1000.0;
                let started = Instant::now(); let prepared = scene.region(region).expect("reused tile");
                prepared_ms += started.elapsed().as_secs_f64() * 1000.0;
                assert_eq!(once, prepared, "prepared tile mismatch at {x},{y}"); tiles += 1;
            }
        }
        println!("label={label} workload=tiled iteration={iteration} size={width}x{tile_height} tile_side={tile_side} tiles={tiles} one_shot_ms={once_ms:.3} reused_render_ms={prepared_ms:.3} prepared_total_ms={:.3} identical=true", prepare_ms + prepared_ms);
    }
}

fn main() {
    let args: Vec<_> = env::args().collect();
    assert!((2..=3).contains(&args.len()), "see source usage");
    let iterations: usize = args.get(2).map(|text| text.parse().expect("iterations")).unwrap_or(3);
    assert!((1..=3).contains(&iterations), "bounded measurement: 1-3 iterations");
    let fixture = fs::read_to_string(&args[1]).expect("public reference SVG");
    profile(&fixture, "public-pencil-filter", iterations, 4320, 2048);
    profile(&dense_public_scene(), "synthetic-6000-paths-clip", iterations, 4320, 2048);
}
