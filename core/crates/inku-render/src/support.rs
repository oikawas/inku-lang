//! Support properties and deterministic interaction between tools and paper.

use crate::stroke::unit;
use crate::types::{GroundMaterial, Seed, SurfaceTexture, Weight};

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Support {
    pub absorb: f64,
    pub tooth: f64,
}

pub const DEFAULT_SUPPORT: Support = Support {
    absorb: 1.0,
    tooth: 1.0,
};

const MARK_SUPPORT_GAIN: f64 = 2.0;
const SUPPORT_CAP: f64 = 3.0;
const SKIP_CUT_LEVEL: f64 = 0.55;

#[derive(Clone, Copy)]
struct Resistance {
    bleed_amp: f64,
    bleed_span: f64,
    bleed_rate: f64,
    skip_depth: f64,
    skip_span: f64,
    skip_rate: f64,
}

const RESISTANCE: Resistance = Resistance {
    bleed_amp: 0.70,
    bleed_span: 0.16,
    bleed_rate: 1.5,
    skip_depth: 0.88,
    skip_span: 0.07,
    skip_rate: 1.5,
};

#[must_use]
pub const fn support_for_ground(material: GroundMaterial) -> Support {
    match material {
        GroundMaterial::Plain | GroundMaterial::Paper => DEFAULT_SUPPORT,
        GroundMaterial::Washi => Support {
            absorb: 2.2,
            tooth: 0.5,
        },
        GroundMaterial::InkWash => Support {
            absorb: 1.4,
            tooth: 0.8,
        },
        GroundMaterial::CharcoalGround => Support {
            absorb: 0.7,
            tooth: 1.8,
        },
        GroundMaterial::Canvas => Support {
            absorb: 0.5,
            tooth: 2.4,
        },
        GroundMaterial::DrawingPaper => Support {
            absorb: 0.8,
            tooth: 1.4,
        },
        GroundMaterial::Mezzotint => Support {
            absorb: 0.2,
            tooth: 0.7,
        },
    }
}

/// Apply a mark-specific surface word to the physical support.
#[must_use]
pub fn support_with_mark_word(support: Support, texture: SurfaceTexture) -> Support {
    match texture {
        SurfaceTexture::Grain => Support {
            absorb: support.absorb,
            tooth: (support.tooth * MARK_SUPPORT_GAIN).min(SUPPORT_CAP),
        },
        SurfaceTexture::Bleed => Support {
            absorb: (support.absorb * MARK_SUPPORT_GAIN).min(SUPPORT_CAP),
            tooth: support.tooth,
        },
        _ => support,
    }
}

const fn tool_support_bias(weight: Weight) -> (f64, f64) {
    match weight {
        Weight::BrushThin | Weight::BrushThick => (1.0, 0.15),
        Weight::Crayon | Weight::Pencil => (0.10, 1.0),
        Weight::Chalk => (0.10, 1.30),
        Weight::Pen => (0.15, 0.15),
        Weight::Silverpoint => (0.05, 0.25),
        Weight::Drypoint => (0.0, 0.35),
        Weight::Burin => (0.0, 0.10),
        Weight::Rotring | Weight::Computer => (0.0, 0.0),
    }
}

fn support_envelope(
    count: usize,
    seed: Seed,
    label: &str,
    bias: f64,
    rate: f64,
    span_ratio: f64,
) -> Vec<f64> {
    if bias <= 0.0 || rate <= 0.0 || span_ratio <= 0.0 || count < 8 {
        return vec![0.0; count];
    }
    let span = ((count as f64 * span_ratio).round_ties_even() as usize).max(2);
    let probability = (rate * bias / (count.saturating_sub(4).max(1)) as f64).min(0.35);
    let mut centres = Vec::new();
    for index in 2..count - 2 {
        if unit(seed, &format!("{label}-arrival"), index as i64) < probability {
            centres.push(index);
            if centres.len() >= 3 {
                break;
            }
        }
    }
    let mut envelope = vec![0.0_f64; count];
    for centre in centres {
        let size = 0.6 + 0.4 * unit(seed, &format!("{label}-size"), centre as i64);
        for offset in -(span as isize)..=span as isize {
            let index = centre as isize + offset;
            if (0..count as isize).contains(&index) {
                let window =
                    0.5 * (1.0 + (std::f64::consts::PI * offset as f64 / span as f64).cos());
                envelope[index as usize] = envelope[index as usize].max(size * window);
            }
        }
    }
    envelope
}

/// Modify widths and mark samples where the support leaves bare paper.
#[must_use]
pub fn support_response(
    widths: &[f64],
    weight: Weight,
    seed: Seed,
    support: Support,
) -> (Vec<f64>, Vec<bool>) {
    let (mut absorb, mut tooth) = tool_support_bias(weight);
    absorb *= support.absorb;
    tooth *= support.tooth;
    let swell = support_envelope(
        widths.len(),
        seed,
        "bleed",
        absorb,
        RESISTANCE.bleed_rate,
        RESISTANCE.bleed_span,
    );
    let pinch = support_envelope(
        widths.len(),
        seed ^ 0x5BD1,
        "skip",
        tooth,
        RESISTANCE.skip_rate,
        RESISTANCE.skip_span,
    );
    let strength = RESISTANCE.skip_depth * tooth;
    let adjusted = widths
        .iter()
        .zip(&swell)
        .zip(&pinch)
        .map(|((width, swell), pinch)| {
            (width * (1.0 + RESISTANCE.bleed_amp * absorb * swell) * (1.0 - strength * pinch))
                .max(0.015)
        })
        .collect();
    let cuts = pinch
        .iter()
        .map(|pinch| strength * pinch >= SKIP_CUT_LEVEL)
        .collect();
    (adjusted, cuts)
}
