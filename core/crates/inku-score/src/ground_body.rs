//! What a named support shows under the marks: the body its material lays over
//! the tone. The renderer paints it, the DDL lowering tells an omitted color
//! from it, and the pipeline finds the marks it hides, so all three read one
//! table and one color space (DDL engine 61).

use crate::types::GroundMaterial;

/// How much ink the ink wash lays over the paper. The author found 0.16 too dark and chose
/// 0.09 over 0.05 (2026-10-15).
const INK_WASH_BODY: f64 = 0.09;

impl GroundMaterial {
    /// The material's own tone, laid over the background: colour and opacity.
    #[must_use]
    pub const fn body(self) -> Option<(&'static str, f64)> {
        match self {
            Self::InkWash => Some(("#1e1e1e", INK_WASH_BODY)),
            Self::CharcoalGround => Some(("#2b2b2b", 0.62)),
            Self::Mezzotint => Some(("#0d0d0d", 1.0)),
            _ => None,
        }
    }

    /// Whether the body hides the background under any tone: the mezzotint
    /// plate and the charcoal. The ink wash's thin wash tints it and leaves it
    /// showing.
    #[must_use]
    pub const fn covers_the_background(self) -> bool {
        matches!(self, Self::Mezzotint | Self::CharcoalGround)
    }
}

/// The sRGB channels (0 to 1) of a `#rrggbb` colour.
#[must_use]
pub fn srgb_channels(hex: &str) -> Option<[f64; 3]> {
    let digits = hex.strip_prefix('#')?;
    if digits.len() != 6 || !digits.is_ascii() {
        return None;
    }
    let mut channels = [0.0; 3];
    for (index, channel) in channels.iter_mut().enumerate() {
        let byte = u8::from_str_radix(&digits[index * 2..index * 2 + 2], 16).ok()?;
        *channel = f64::from(byte) / 255.0;
    }
    Some(channels)
}

/// The sRGB colour (channels 0 to 1) a support of `material` shows over
/// `tone`: its body laid over the tone at the body's opacity, as the renderer
/// paints it, or the tone itself for a material without a body.
#[must_use]
pub fn shown_support(material: GroundMaterial, tone: [f64; 3]) -> [f64; 3] {
    let Some((colour, opacity)) = material.body() else {
        return tone;
    };
    let body = srgb_channels(colour).expect("body colours are hex");
    [0, 1, 2].map(|index| tone[index] * (1.0 - opacity) + body[index] * opacity)
}

/// OKLab lightness, a and b of sRGB channels (0 to 1).
#[must_use]
pub fn oklab_from_srgb(channels: [f64; 3]) -> [f64; 3] {
    let [red, green, blue] = channels.map(|channel| {
        if channel <= 0.04045 {
            channel / 12.92
        } else {
            ((channel + 0.055) / 1.055).powf(2.4)
        }
    });
    let light_channel = 0.412_221_470_8 * red + 0.536_332_536_3 * green + 0.051_445_992_9 * blue;
    let medium_channel = 0.211_903_498_2 * red + 0.680_699_545_1 * green + 0.107_396_956_6 * blue;
    let short_channel = 0.088_302_461_9 * red + 0.281_718_837_6 * green + 0.629_978_700_5 * blue;
    let (light_root, medium_root, short_root) = (
        light_channel.cbrt(),
        medium_channel.cbrt(),
        short_channel.cbrt(),
    );
    [
        0.210_454_255_3 * light_root + 0.793_617_785 * medium_root - 0.004_072_046_8 * short_root,
        1.977_998_495_1 * light_root - 2.428_592_205 * medium_root + 0.450_593_709_9 * short_root,
        0.025_904_037_1 * light_root + 0.782_771_766_2 * medium_root - 0.808_675_766 * short_root,
    ]
}

/// The OKLab colour difference (the distance in L, a and b) of two sRGB colours.
#[must_use]
pub fn oklab_difference(left: [f64; 3], right: [f64; 3]) -> f64 {
    let (left, right) = (oklab_from_srgb(left), oklab_from_srgb(right));
    (0..3)
        .map(|index| (left[index] - right[index]).powi(2))
        .sum::<f64>()
        .sqrt()
}
