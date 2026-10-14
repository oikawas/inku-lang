//! CLI-only adapter. Linked against the selected checkout's exact Cargo artifacts.
use std::io::{self, Read};
use std::time::Instant;

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).map(String::as_str) == Some("--describe") {
        println!(
            "{}",
            serde_json::json!({
                "canvas_registry": serde_json::from_str::<serde_json::Value>(
                    &inku_pipeline_uniffi::canvas_registry())?,
                "default_color_map": inku_render::palette::default_color_map(),
                "render_engine_id": inku_render::RENDER_ENGINE_ID,
                "render_engine_version": inku_render::RENDER_ENGINE_VERSION,
            })
        );
        return Ok(());
    }
    if args.len() != 4 {
        return Err("expected SVG path, PNG path (or empty), and raster height".into());
    }
    let mut input = Vec::new();
    io::stdin()
        .take(16 * 1024 * 1024 + 1)
        .read_to_end(&mut input)?;
    // Pass the original JSON bytes directly: a Value roundtrip would lose i128 seeds.
    let started = Instant::now();
    let (metadata, svg) = inku_pipeline_uniffi::render_saved_with_svg_limit(input, 32 << 20);
    let render_ms = started.elapsed().as_secs_f64() * 1000.0;
    let metadata: serde_json::Value = serde_json::from_slice(&metadata)?;
    let Some(svg) = svg else {
        return Err(format!("core refused saved replay: {metadata}").into());
    };
    let mut raster_ms = None;
    let mut png_size = None;
    if !args[2].is_empty() {
        let started = Instant::now();
        let raster = inku_svg_raster::rasterize(
            &svg,
            inku_svg_raster::RasterOptions {
                target_width: None,
                target_height: Some(args[3].parse()?),
            },
        )?;
        let size = resvg::tiny_skia::IntSize::from_wh(raster.width, raster.height)
            .ok_or("invalid raster dimensions")?;
        let pixmap = resvg::tiny_skia::Pixmap::from_vec(raster.pixels, size)
            .ok_or("invalid raster payload")?;
        std::fs::write(&args[2], pixmap.encode_png()?)?;
        raster_ms = Some(started.elapsed().as_secs_f64() * 1000.0);
        png_size = Some(serde_json::json!({"width": raster.width, "height": raster.height}));
    }
    std::fs::write(&args[1], svg.as_bytes())?;
    println!(
        "{}",
        serde_json::json!({
            "metadata": metadata.get("metadata"), "render_ms": render_ms,
            "raster_ms": raster_ms, "png_size": png_size,
        })
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
