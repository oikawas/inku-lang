//! Renderer-owned values exposed to the host reference document.

use serde::Serialize;
use serde_json::{Value, json};

use crate::geometry::{
    SEGMENT_COUNT_MAX, SEGMENT_COUNT_MIN, SEGMENT_TARGET_RATIO, frequency_cycles,
};
use crate::mark_paths::amplitude_width;
use crate::marks::{
    MIN_STROKE_WIDTH, style_dash, thinness_scale, weight_linecap, weight_opacity, weight_width,
};
use crate::materials::texture_filter_id;
use crate::types::{Amplitude, Frequency, LineStyle, Thinness, Weight};

const WEIGHTS: [Weight; 11] = [
    Weight::Silverpoint,
    Weight::Pencil,
    Weight::Pen,
    Weight::Rotring,
    Weight::Crayon,
    Weight::Chalk,
    Weight::BrushThin,
    Weight::BrushThick,
    Weight::Burin,
    Weight::Drypoint,
    Weight::Computer,
];

fn enum_name<T: Serialize>(value: T) -> String {
    serde_json::to_value(value)
        .expect("render enum must serialize")
        .as_str()
        .expect("render enum must serialize as a string")
        .to_owned()
}

/// Return the renderer-owned portion of the public implementation reference.
#[must_use]
pub fn renderer_reference() -> Value {
    let weights = WEIGHTS
        .into_iter()
        .map(|weight| {
            json!({
                "weight": enum_name(weight),
                "stroke_width": weight_width(weight),
                "stroke_opacity": weight_opacity(weight),
                "stroke_dasharray": style_dash(LineStyle::Solid, weight, 1.0),
                "stroke_linecap": weight_linecap(weight),
                "texture_filter": texture_filter_id(weight).is_some(),
            })
        })
        .collect::<Vec<_>>();
    let texture_filter_weights = WEIGHTS
        .into_iter()
        .filter(|weight| texture_filter_id(*weight).is_some())
        .map(enum_name)
        .collect::<Vec<_>>();

    json!({
        "weight_properties": {
            "weights": weights,
            "line_style_dash": {
                "solid": style_dash(LineStyle::Solid, Weight::Pen, 1.0),
                "dashed": style_dash(LineStyle::Dashed, Weight::Pen, 1.0),
                "dotted": style_dash(LineStyle::Dotted, Weight::Pen, 1.0),
                "dash_dot": style_dash(LineStyle::DashDot, Weight::Pen, 1.0),
            },
            "texture_filter_weights": texture_filter_weights,
            "thinness_width_scale": {
                "None": thinness_scale(None),
                "fine": thinness_scale(Some(Thinness::Fine)),
                "extra_fine": thinness_scale(Some(Thinness::ExtraFine)),
            },
            "min_stroke_width": MIN_STROKE_WIDTH,
            "canvas_px": 1000,
        },
        "performance": {
            "amplitude_widths": {
                "fine": amplitude_width(Amplitude::Fine),
                "medium": amplitude_width(Amplitude::Medium),
                "broad": amplitude_width(Amplitude::Broad),
            },
            "amplitude_clamp_ratio": 0.40,
            "representative_min_ratio": 0.02,
            "frequency_cycles": {
                "slow": frequency_cycles(Frequency::Slow),
                "medium": frequency_cycles(Frequency::Medium),
                "high": frequency_cycles(Frequency::High),
            },
            // Preserve the stable public reference shape after retiring the
            // unused Engine 40 Python table. These values are compatibility
            // documentation, not a runtime fallback or a second renderer.
            "blur_ratio": {
                "fine": 0.009,
                "medium": 0.03,
                "broad": 0.07,
            },
            "segment_target_ratio": SEGMENT_TARGET_RATIO,
            "segment_count_range": [SEGMENT_COUNT_MIN, SEGMENT_COUNT_MAX],
        },
    })
}

#[cfg(test)]
mod tests {
    use super::renderer_reference;

    #[test]
    fn reference_is_derived_from_the_render_tables() {
        let reference = renderer_reference();
        let weights = reference["weight_properties"]["weights"]
            .as_array()
            .expect("weight table");
        assert_eq!(weights.len(), 11);
        assert_eq!(weights[0]["weight"], "silverpoint");
        assert_eq!(weights[0]["stroke_width"], 0.5);
        assert_eq!(reference["performance"]["frequency_cycles"]["high"], 14.0);
        assert_eq!(reference["performance"]["blur_ratio"]["broad"], 0.07);
    }
}
