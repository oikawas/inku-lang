//! The Skia scene (`--features skia`, macOS):
//!
//! C1: public works drawn whole match Chrome's pictures of them, fixed once.
//! C2: each compatibility rewrite makes Skia draw what Chrome draws, and without it
//!     Skia does not.
//! C4: a work drawn in tiles on several threads matches the work drawn in one piece.
//!
//! The yardstick is the author's (2026-10-06): both pictures over white, every 16px
//! block's mean difference at most 16, and at most 0.5% of pixels differing by more
//! than 32 in a channel.
#![cfg(feature = "skia")]

use inku_display::geometry::{TILE_SIDE, tiles};
use inku_display::{RasterOptions, RasterOutput, RasterRegionOptions, prepare_scene};
use skia_safe::svg::Dom;
use skia_safe::{AlphaType, ColorType, Data, FontMgr, Image, ImageInfo};

const BLOCK: usize = 16;
const WORST_BLOCK: f64 = 16.0;
const DIFFERING_PIXELS: f64 = 0.005;

fn data(path: &str) -> Vec<u8> {
    std::fs::read(format!("{}/tests/data/{path}", env!("CARGO_MANIFEST_DIR"))).expect(path)
}

/// RGB over white, from Chrome's PNG.
fn chrome(path: &str) -> (usize, usize, Vec<[f64; 3]>) {
    let image = Image::from_encoded(Data::new_copy(&data(path))).expect(path);
    let (width, height) = (image.width() as usize, image.height() as usize);
    let info = ImageInfo::new(
        image.dimensions(),
        ColorType::RGBA8888,
        AlphaType::Unpremul,
        None,
    );
    let mut bytes = vec![0u8; width * height * 4];
    assert!(image.read_pixels(
        &info,
        &mut bytes,
        width * 4,
        (0, 0),
        skia_safe::image::CachingHint::Disallow
    ));
    let pixels = bytes
        .chunks(4)
        .map(|p| {
            let alpha = f64::from(p[3]) / 255.0;
            [0, 1, 2].map(|i| f64::from(p[i]) * alpha + 255.0 * (1.0 - alpha))
        })
        .collect();
    (width, height, pixels)
}

/// RGB over white, from premultiplied RGBA8.
fn over_white(output: &RasterOutput) -> Vec<[f64; 3]> {
    output
        .pixels
        .chunks(4)
        .map(|p| [0, 1, 2].map(|i| f64::from(p[i]) + 255.0 - f64::from(p[3])))
        .collect()
}

#[derive(Debug)]
struct Difference {
    worst_block: f64,
    differing: f64,
}

impl Difference {
    fn passes(&self) -> bool {
        self.worst_block <= WORST_BLOCK && self.differing <= DIFFERING_PIXELS
    }
}

fn difference(width: usize, height: usize, a: &[[f64; 3]], b: &[[f64; 3]]) -> Difference {
    assert_eq!((a.len(), b.len()), (width * height, width * height));
    let columns = width.div_ceil(BLOCK);
    let mut blocks = vec![(0.0, 0usize); columns * height.div_ceil(BLOCK)];
    let mut differing = 0;
    for y in 0..height {
        for x in 0..width {
            let i = y * width + x;
            let channels = [0, 1, 2].map(|c| (a[i][c] - b[i][c]).abs());
            if channels.iter().copied().fold(0.0, f64::max) > 32.5 {
                differing += 1;
            }
            let block = &mut blocks[(y / BLOCK) * columns + x / BLOCK];
            block.0 += channels.iter().sum::<f64>() / 3.0;
            block.1 += 1;
        }
    }
    Difference {
        worst_block: blocks
            .iter()
            .map(|(sum, n)| sum / *n as f64)
            .fold(0.0, f64::max),
        differing: differing as f64 / (width * height) as f64,
    }
}

fn whole(svg: &str, width: usize, height: usize) -> RasterOutput {
    let scene = prepare_scene(svg).expect("the work is inside the support table");
    let output = scene
        .rasterize(RasterOptions {
            target_width: Some(width as u32),
            target_height: Some(height as u32),
        })
        .unwrap();
    assert_eq!(
        (output.width as usize, output.height as usize),
        (width, height)
    );
    output
}

/// Skia drawing the stored SVG as it is, without the support check or the rewrite.
fn unrewritten(svg: &str, width: usize, height: usize) -> Vec<[f64; 3]> {
    let mut dom = Dom::from_str(svg, FontMgr::empty()).expect("Skia reads it");
    dom.set_container_size((width as f32, height as f32));
    let info = ImageInfo::new(
        (width as i32, height as i32),
        ColorType::RGBA8888,
        AlphaType::Premul,
        None,
    );
    let mut pixels = vec![0; width * height * 4];
    {
        let canvas =
            skia_safe::Canvas::from_raster_direct(&info, &mut pixels, width * 4, None).unwrap();
        dom.render(&canvas);
    }
    over_white(&RasterOutput {
        width: width as u32,
        height: height as u32,
        stride: width as u32 * 4,
        pixel_format: inku_display::PIXEL_FORMAT_RGBA8_PREMULTIPLIED,
        pixels,
    })
}

/// C1. Chrome 154.0.8037.98, `<img>`, `--disable-gpu`, device scale 1 (stage 1).
#[test]
fn public_works_match_chrome() {
    let mut compared = Vec::new();
    for id in ["p00", "p02", "p07", "p11"] {
        let svg = String::from_utf8(data(&format!("public/{id}.svg"))).unwrap();
        let (width, height, reference) = chrome(&format!("public/{id}-chrome.png"));
        let drawn = over_white(&whole(&svg, width, height));
        let difference = difference(width, height, &drawn, &reference);
        eprintln!("{id}: {difference:?}");
        assert!(difference.passes(), "{id}: {difference:?}");
        compared.push(id);
    }
    assert_eq!(compared.len(), 4);
}

/// C2. Each small SVG needs its rewrite: Skia matches Chrome with it and not without.
#[test]
fn each_rewrite_is_needed_to_match_chrome() {
    for name in [
        "pattern-href",
        "use-href",
        "ellipse-gradient",
        "seed",
        "alpha-mask-white",
    ] {
        let svg = String::from_utf8(data(&format!("compat/{name}.svg"))).unwrap();
        let (width, height, reference) = chrome(&format!("compat/{name}-chrome.png"));
        let rewritten = difference(
            width,
            height,
            &over_white(&whole(&svg, width, height)),
            &reference,
        );
        let plain = difference(width, height, &unrewritten(&svg, width, height), &reference);
        eprintln!("{name}: rewritten {rewritten:?}, as stored {plain:?}");
        assert!(rewritten.passes(), "{name}: {rewritten:?}");
        assert!(
            !plain.passes(),
            "{name} matches Chrome without the rewrite: {plain:?}"
        );
    }
}

/// C2, the control: with only `href` fixed, a white alpha mask matches Chrome and a grey
/// one does not, because Skia reads every mask as luminance. The support check sends
/// the grey one to resvg.
#[test]
fn a_grey_alpha_mask_would_not_match_chrome() {
    let href_only = |svg: &str| {
        svg.replacen(
            "<svg ",
            "<svg xmlns:xlink=\"http://www.w3.org/1999/xlink\" ",
            1,
        )
        .replace(" href=", " xlink:href=")
    };
    for (name, matches) in [("alpha-mask-white", true), ("alpha-mask-gray", false)] {
        let svg = String::from_utf8(data(&format!("compat/{name}.svg"))).unwrap();
        let (width, height, reference) = chrome(&format!("compat/{name}-chrome.png"));
        let drawn = difference(
            width,
            height,
            &unrewritten(&href_only(&svg), width, height),
            &reference,
        );
        eprintln!("{name}: {drawn:?}");
        assert_eq!(drawn.passes(), matches, "{name}: {drawn:?}");
    }
}

/// C4. 512px tiles drawn on eight threads from one scene, stitched, against one piece
/// (stage 1: the window's position changes filter results slightly, so not identical).
#[test]
fn tiles_match_the_whole() {
    for (id, side) in [("p07", 1000u32), ("p11", 2000)] {
        let svg = String::from_utf8(data(&format!("public/{id}.svg"))).unwrap();
        let scene = prepare_scene(&svg).unwrap();
        let canvas = RasterRegionOptions {
            full_width: side,
            full_height: side,
            x: 0,
            y: 0,
            width: side,
            height: side,
        };
        let one = scene.region(canvas).unwrap();
        let plan = tiles(canvas, TILE_SIDE);
        let drawn: Vec<(RasterRegionOptions, RasterOutput)> = std::thread::scope(|scope| {
            let workers: Vec<_> = plan
                .chunks(plan.len().div_ceil(8))
                .map(|chunk| {
                    let scene = &scene;
                    scope.spawn(move || {
                        chunk
                            .iter()
                            .map(|tile| (*tile, scene.region(*tile).unwrap()))
                            .collect::<Vec<_>>()
                    })
                })
                .collect();
            workers
                .into_iter()
                .flat_map(|worker| worker.join().unwrap())
                .collect()
        });
        let side = side as usize;
        let mut stitched = vec![0; side * side * 4];
        for (tile, output) in &drawn {
            for row in 0..tile.height as usize {
                let at = ((tile.y as usize + row) * side + tile.x as usize) * 4;
                let from = row * output.stride as usize;
                stitched[at..at + output.width as usize * 4]
                    .copy_from_slice(&output.pixels[from..from + output.width as usize * 4]);
            }
        }
        let stitched = RasterOutput {
            pixels: stitched,
            ..one.clone()
        };
        let difference = difference(side, side, &over_white(&stitched), &over_white(&one));
        eprintln!("{id} at {side}px in {} tiles: {difference:?}", drawn.len());
        assert_eq!(drawn.len(), side.div_ceil(TILE_SIDE as usize).pow(2));
        assert!(difference.passes(), "{id}: {difference:?}");
    }
}
