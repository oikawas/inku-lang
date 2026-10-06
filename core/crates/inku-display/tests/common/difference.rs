//! Development-only display comparison shared by Rust tests and Android's test
//! library. These thresholds are not part of the product display API.

use inku_display::RasterOutput;

const BLOCK: usize = 16;
const WORST_BLOCK: f64 = 16.0;
const DIFFERING_PIXELS: f64 = 0.005;

/// RGB over white, from premultiplied RGBA8 (including host row padding).
pub fn over_white(output: &RasterOutput) -> Vec<[f64; 3]> {
    output
        .pixels
        .chunks_exact(output.stride as usize)
        .flat_map(|row| row[..output.width as usize * 4].chunks_exact(4))
        .map(|p| [0, 1, 2].map(|i| f64::from(p[i]) + 255.0 - f64::from(p[3])))
        .collect()
}

#[derive(Debug)]
pub struct Difference {
    pub worst_block: f64,
    pub differing: f64,
}

impl Difference {
    pub fn passes(&self) -> bool {
        self.worst_block <= WORST_BLOCK && self.differing <= DIFFERING_PIXELS
    }
}

pub fn difference(width: usize, height: usize, a: &[[f64; 3]], b: &[[f64; 3]]) -> Difference {
    assert_eq!((a.len(), b.len()), (width * height, width * height));
    let columns = width.div_ceil(BLOCK);
    let mut blocks = vec![(0.0, 0usize); columns * height.div_ceil(BLOCK)];
    let mut differing = 0;
    for y in 0..height {
        for x in 0..width {
            let i = y * width + x;
            let channels = [0, 1, 2].map(|c| (a[i][c] - b[i][c]).abs());
            // Preserve the existing Chrome comparison's fractional-alpha rounding.
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
