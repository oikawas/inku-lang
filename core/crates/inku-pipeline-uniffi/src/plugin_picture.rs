//! Saijiki picture decoding, cropping and fitting.
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use std::io::Cursor;

const MAX_BYTES: usize = 2 * 1024 * 1024;

fn issue(code: &str, detail: &str) -> Value {
    json!({"path":"image","code":code,"detail":detail})
}

struct Image {
    width: usize,
    height: usize,
    rgb: Vec<u8>,
}

fn decode(data: &[u8]) -> Result<Image, Value> {
    if data.len() > MAX_BYTES {
        return Err(issue("image_too_large", &MAX_BYTES.to_string()));
    }
    if !data.starts_with(b"\x89PNG\r\n\x1a\n") {
        return Err(issue("not_a_png", ""));
    }
    let mut decoder = png::Decoder::new(Cursor::new(data));
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = decoder.read_info().map_err(|_| issue("not_a_png", ""))?;
    let info = reader.info();
    if u64::from(info.width) * u64::from(info.height) > 4096 * 4096 {
        return Err(issue("image_too_large", ""));
    }
    let mut buf = vec![
        0;
        reader
            .output_buffer_size()
            .ok_or_else(|| issue("not_a_png", ""))?
    ];
    let frame = reader
        .next_frame(&mut buf)
        .map_err(|_| issue("not_a_png", ""))?;
    let channels = match frame.color_type {
        png::ColorType::Rgb => 3,
        png::ColorType::Rgba => 4,
        png::ColorType::Grayscale => 1,
        png::ColorType::GrayscaleAlpha => 2,
        _ => return Err(issue("not_a_png", "")),
    };
    let mut rgb = Vec::with_capacity(frame.width as usize * frame.height as usize * 3);
    for pixel in buf[..frame.buffer_size()].chunks_exact(channels) {
        let (r, g, b, a) = match channels {
            1 => (pixel[0], pixel[0], pixel[0], 255),
            2 => (pixel[0], pixel[0], pixel[0], pixel[1]),
            3 => (pixel[0], pixel[1], pixel[2], 255),
            _ => (pixel[0], pixel[1], pixel[2], pixel[3]),
        };
        for c in [r, g, b] {
            rgb.push(
                ((u32::from(c) * u32::from(a) + 255 * (255 - u32::from(a)) + 127) / 255) as u8,
            );
        }
    }
    Ok(Image {
        width: frame.width as usize,
        height: frame.height as usize,
        rgb,
    })
}

fn kernel(x: f64) -> f64 {
    let x = x.abs();
    if x < 1e-8 {
        1.0
    } else if x >= 3.0 {
        0.0
    } else {
        let p = std::f64::consts::PI * x;
        (p.sin() / p) * ((p / 3.0).sin() / (p / 3.0))
    }
}

fn weights(source: usize, target: usize) -> Vec<Vec<(usize, f64)>> {
    let scale = source as f64 / target as f64;
    let filter = scale.max(1.0);
    (0..target)
        .map(|i| {
            let center = (i as f64 + 0.5) * scale;
            let first = ((center - 3.0 * filter - 0.5).ceil() as isize).max(0) as usize;
            let last = ((center + 3.0 * filter - 0.5).floor() as usize).min(source - 1);
            let mut row: Vec<_> = (first..=last)
                .map(|j| (j, kernel(((j as f64 + 0.5) - center) / filter)))
                .collect();
            let sum: f64 = row.iter().map(|(_, w)| w).sum();
            for (_, w) in &mut row {
                *w /= sum;
            }
            row
        })
        .collect()
}

fn fit(image: &Image, paper: &[u8], width: usize, height: usize) -> Result<String, Value> {
    let ratio = (width as f64 / image.width as f64).min(height as f64 / image.height as f64);
    let w = (image.width as f64 * ratio).round_ties_even().max(1.0) as usize;
    let h = (image.height as f64 * ratio).round_ties_even().max(1.0) as usize;
    let wx = weights(image.width, w);
    let wy = weights(image.height, h);
    let mut horizontal = vec![0f64; w * image.height * 3];
    for y in 0..image.height {
        for x in 0..w {
            for c in 0..3 {
                horizontal[(y * w + x) * 3 + c] = wx[x]
                    .iter()
                    .map(|(sx, a)| f64::from(image.rgb[(y * image.width + sx) * 3 + c]) * a)
                    .sum();
            }
        }
    }
    let mut out = vec![0; width * height * 3];
    for p in out.as_chunks_mut::<3>().0 {
        p.copy_from_slice(paper);
    }
    let ox = (width - w) / 2;
    let oy = (height - h) / 2;
    for y in 0..h {
        for x in 0..w {
            for c in 0..3 {
                let value: f64 = wy[y]
                    .iter()
                    .map(|(sy, a)| horizontal[(sy * w + x) * 3 + c] * a)
                    .sum();
                out[((y + oy) * width + x + ox) * 3 + c] = value.round().clamp(0.0, 255.0) as u8;
            }
        }
    }
    let mut bytes = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut bytes, width as u32, height as u32);
        encoder.set_color(png::ColorType::Rgb);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().map_err(|_| issue("not_a_png", ""))?;
        writer
            .write_image_data(&out)
            .map_err(|_| issue("not_a_png", ""))?;
    }
    Ok(STANDARD.encode(bytes))
}

fn fitted(image: &Image, paper: &[u8]) -> Result<Value, Value> {
    Ok(json!({"png":fit(image,paper,216,92)?,"png_2x":fit(image,paper,432,184)?}))
}

pub(crate) fn uploaded(data: &[u8]) -> Result<Value, Value> {
    let image = decode(data)?;
    fitted(&image, &image.rgb[..3])
}

pub(crate) fn drawn(svg: &str) -> Result<Value, Value> {
    let raster = inku_svg_raster::rasterize(
        svg,
        inku_svg_raster::RasterOptions {
            target_width: Some(768),
            target_height: Some(768),
        },
    )
    .map_err(|_| issue("not_a_png", ""))?;
    let mut rgb = Vec::with_capacity(raster.width as usize * raster.height as usize * 3);
    for p in raster.pixels.as_chunks::<4>().0 {
        for c in &p[..3] {
            rgb.push(c.saturating_add(255 - p[3]));
        }
    }
    let w = raster.width as usize;
    let h = raster.height as usize;
    let paper = [rgb[0], rgb[1], rgb[2]];
    let (mut x0, mut y0, mut x1, mut y1) = (w, h, 0, 0);
    for y in 0..h {
        for x in 0..w {
            let p = &rgb[(y * w + x) * 3..][..3];
            let diff = (299 * i32::from(p[0].abs_diff(paper[0]))
                + 587 * i32::from(p[1].abs_diff(paper[1]))
                + 114 * i32::from(p[2].abs_diff(paper[2]))
                + 500)
                / 1000;
            if diff > 12 {
                x0 = x0.min(x);
                y0 = y0.min(y);
                x1 = x1.max(x + 1);
                y1 = y1.max(y + 1);
            }
        }
    }
    if x1 == 0 {
        x0 = 0;
        y0 = 0;
        x1 = w;
        y1 = h;
    }
    x0 = x0.saturating_sub(24);
    y0 = y0.saturating_sub(24);
    x1 = (x1 + 24).min(w);
    y1 = (y1 + 24).min(h);
    let mut cropped = Vec::with_capacity((x1 - x0) * (y1 - y0) * 3);
    for y in y0..y1 {
        cropped.extend_from_slice(&rgb[(y * w + x0) * 3..(y * w + x1) * 3]);
    }
    // Padding uses the original paper, not the crop's top-left pixel.
    let image = Image {
        width: x1 - x0,
        height: y1 - y0,
        rgb: cropped,
    };
    fitted(&image, &paper)
}
