//! Deterministic hashes, seed payloads, and scalar noise.

use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::types::{
    Amplitude, Arrangement, CarveDepth, Dimension, Frequency, Instruction, InstructionMode,
    LineStyle, Point, Primitive, Quality, Seed, SurfaceDirection, SurfaceSpacingGradient,
    SurfaceSpec, SurfaceTexture, Thinness, Variation, Weight,
};

fn sha256(payload: &[u8]) -> [u8; 32] {
    Sha256::digest(payload).into()
}

/// Map an integer and seed to the same signed unit interval used by Engine 40.
#[must_use]
pub fn hash_to_unit(index: i64, seed: Seed) -> f64 {
    let digest = sha256(format!("{seed}:{index}").as_bytes());
    let value = i64::from_le_bytes(digest[..8].try_into().expect("eight digest bytes"));
    value as f64 / 2_f64.powi(63)
}

/// Map a salted integer and seed to the closed interval from zero to one.
#[must_use]
pub fn hash01(index: i64, seed: Seed, salt: &str) -> f64 {
    let digest = sha256(format!("{seed}:{salt}:{index}").as_bytes());
    let value = u32::from_le_bytes(digest[..4].try_into().expect("four digest bytes"));
    f64::from(value) / f64::from(u32::MAX)
}

/// Smoothly interpolate deterministic lattice values around `x`.
#[must_use]
pub fn value_noise_1d(x: f64, seed: Seed) -> f64 {
    let xi = x.floor();
    let xf = x - xi;
    let lower = hash_to_unit(xi as i64, seed);
    let upper = hash_to_unit(xi as i64 + 1, seed);
    let smooth = xf * xf * (3.0 - 2.0 * xf);
    lower * (1.0 - smooth) + upper * smooth
}

/// Value noise whose lattice closes after `period` cells.
#[must_use]
pub fn periodic_value_noise_1d(x: f64, seed: Seed, period: i64) -> f64 {
    assert!(period > 0, "periodic noise requires a positive period");
    let xi = x.floor() as i64;
    let xf = x - xi as f64;
    let lower = hash_to_unit(xi.rem_euclid(period), seed);
    let upper = hash_to_unit((xi + 1).rem_euclid(period), seed);
    let smooth = xf * xf * (3.0 - 2.0 * xf);
    lower * (1.0 - smooth) + upper * smooth
}

/// Seed-derived phase that preserves an integer-frequency periodic seam.
#[must_use]
pub fn wave_phase(seed: Seed) -> f64 {
    hash01(0, seed, "wave-phase") * std::f64::consts::TAU
}

#[derive(Clone, Copy)]
enum VariationSeedFields {
    None,
    AmplitudeQuality,
    AmplitudeFrequencyQuality,
    All,
}

#[must_use]
pub fn needs_blur(variation: &Variation) -> bool {
    variation.quality == Quality::Pink
}

#[must_use]
pub fn needs_path_variation(variation: &Variation) -> bool {
    !matches!(variation.quality, Quality::None | Quality::Pink)
        && variation
            .dimensions
            .iter()
            .any(|dimension| matches!(dimension, Dimension::PositionX | Dimension::PositionY))
}

#[must_use]
pub fn needs_contour_variation(variation: &Variation) -> bool {
    !matches!(variation.quality, Quality::None | Quality::Pink)
        && variation.dimensions.iter().any(|dimension| {
            matches!(
                dimension,
                Dimension::PositionX | Dimension::PositionY | Dimension::Radius
            )
        })
}

fn variation_seed_fields(instruction: &Instruction) -> VariationSeedFields {
    let Some(variation) = instruction.variation.as_ref() else {
        return VariationSeedFields::None;
    };
    if instruction.primitive == Primitive::Cloudform {
        return VariationSeedFields::AmplitudeFrequencyQuality;
    }
    if needs_blur(variation) {
        return VariationSeedFields::AmplitudeQuality;
    }
    if instruction.primitive == Primitive::Line {
        return if needs_path_variation(variation) {
            VariationSeedFields::All
        } else {
            VariationSeedFields::None
        };
    }
    if needs_contour_variation(variation) {
        VariationSeedFields::All
    } else {
        VariationSeedFields::None
    }
}

#[derive(Serialize)]
struct SeedVariation {
    #[serde(skip_serializing_if = "Option::is_none")]
    amplitude: Option<Amplitude>,
    #[serde(skip_serializing_if = "Option::is_none")]
    frequency: Option<Frequency>,
    #[serde(skip_serializing_if = "Option::is_none")]
    quality: Option<Quality>,
    #[serde(skip_serializing_if = "Option::is_none")]
    dimensions: Option<Vec<Dimension>>,
}

impl SeedVariation {
    fn filtered(variation: &Variation, fields: VariationSeedFields) -> Option<Self> {
        match fields {
            VariationSeedFields::None => None,
            VariationSeedFields::AmplitudeQuality => Some(Self {
                amplitude: Some(variation.amplitude),
                frequency: None,
                quality: Some(variation.quality),
                dimensions: None,
            }),
            VariationSeedFields::AmplitudeFrequencyQuality => Some(Self {
                amplitude: Some(variation.amplitude),
                frequency: Some(variation.frequency),
                quality: Some(variation.quality),
                dimensions: None,
            }),
            VariationSeedFields::All => Some(Self {
                amplitude: Some(variation.amplitude),
                frequency: Some(variation.frequency),
                quality: Some(variation.quality),
                dimensions: Some(variation.dimensions.clone()),
            }),
        }
    }
}

#[derive(Serialize)]
struct SeedArrangement {
    jitter: f64,
}

impl From<&Arrangement> for SeedArrangement {
    fn from(value: &Arrangement) -> Self {
        Self {
            jitter: value.jitter,
        }
    }
}

#[derive(Serialize)]
struct SeedSurface {
    texture: SurfaceTexture,
    density: f64,
    scale: f64,
    opacity: f64,
    bleed: f64,
    direction: SurfaceDirection,
    #[serde(skip_serializing_if = "Option::is_none")]
    spacing_gradient: Option<SurfaceSpacingGradient>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tone_steps: Option<u8>,
    seed: Option<Seed>,
}

impl From<&SurfaceSpec> for SeedSurface {
    fn from(value: &SurfaceSpec) -> Self {
        Self {
            texture: value.texture,
            density: value.density,
            scale: value.scale,
            opacity: value.opacity,
            bleed: value.bleed,
            direction: value.direction,
            spacing_gradient: (value.spacing_gradient != SurfaceSpacingGradient::None)
                .then_some(value.spacing_gradient),
            tone_steps: (value.tone_steps != 3).then_some(value.tone_steps),
            seed: value.seed,
        }
    }
}

#[derive(Serialize)]
struct SeedPayload {
    primitive: Primitive,
    from_: Option<Point>,
    to: Option<Point>,
    center: Option<Point>,
    radius: Option<f64>,
    sides: Option<u8>,
    position: Option<Point>,
    size: Option<Point>,
    angle_start: Option<f64>,
    angle_end: Option<f64>,
    rotation: Option<f64>,
    filled: bool,
    style: LineStyle,
    weight: Weight,
    thinness: Option<Thinness>,
    #[serde(skip_serializing_if = "Option::is_none")]
    mode: Option<InstructionMode>,
    #[serde(skip_serializing_if = "Option::is_none")]
    carve_depth: Option<CarveDepth>,
    variation: Option<SeedVariation>,
    arrangement: Option<SeedArrangement>,
    surface: Option<SeedSurface>,
}

impl From<&Instruction> for SeedPayload {
    fn from(instruction: &Instruction) -> Self {
        let solid = instruction
            .surface
            .as_ref()
            .is_some_and(|surface| surface.texture == SurfaceTexture::Solid);
        Self {
            primitive: instruction.primitive,
            from_: instruction.from_,
            to: instruction.to,
            center: instruction.center,
            radius: instruction.radius,
            sides: instruction.sides,
            position: instruction.position,
            size: instruction.size,
            angle_start: instruction.angle_start,
            angle_end: instruction.angle_end,
            rotation: instruction.rotation,
            filled: instruction.filled || solid,
            style: instruction.style,
            weight: instruction.weight,
            thinness: instruction.thinness,
            mode: (instruction.mode_ != InstructionMode::Additive).then_some(instruction.mode_),
            carve_depth: instruction.carve_depth,
            variation: instruction.variation.as_ref().and_then(|variation| {
                SeedVariation::filtered(variation, variation_seed_fields(instruction))
            }),
            arrangement: instruction.arrangement.as_ref().map(SeedArrangement::from),
            surface: if solid {
                None
            } else {
                instruction.surface.as_ref().map(SeedSurface::from)
            },
        }
    }
}

/// Derive the stable instruction seed from Engine 40's canonical payload.
#[must_use]
pub fn instruction_seed(instruction: &Instruction, performance_seed: Option<Seed>) -> Seed {
    let mut key = serde_json::to_vec(&SeedPayload::from(instruction))
        .expect("seed payload contains only serializable canonical values");
    if let Some(seed) = performance_seed {
        key.extend_from_slice(format!(":render:{seed}").as_bytes());
    }
    let digest = sha256(&key);
    i128::from(u64::from_le_bytes(
        digest[..8].try_into().expect("eight digest bytes"),
    ))
}
