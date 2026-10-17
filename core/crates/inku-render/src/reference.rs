//! Renderer-owned values exposed to the host reference document.

use serde::Serialize;
use serde_json::{Value, json};

use crate::accepted_fills::{
    CHALK_FILMS, CHALK_INTERCEPTS, CHALK_PASS_FREQUENCY, CHALK_PRESS_WEIGHT, CHALK_SLOPE,
    CHALK_TOOTH_FREQUENCY, CHALK_TOOTH_WEIGHT,
};
use crate::geometry::{
    SEGMENT_COUNT_MAX, SEGMENT_COUNT_MIN, SEGMENT_TARGET_RATIO, frequency_cycles,
};
use crate::mark_paths::{
    COMPUTER_CELL_OPACITY, COMPUTER_CELL_OPACITY_FLOOR, amplitude_width, line_path_share,
};
use crate::marks::{
    MIN_STROKE_WIDTH, extra_thick_width, style_dash, thick_width, thinness_scale, weight_linecap,
    weight_opacity, weight_width,
};
use crate::materials::texture_filter_id;
use crate::stroke::grammar;
use crate::types::{Amplitude, Frequency, LineStyle, Thinness, Weight};

const WEIGHTS: [Weight; 12] = [
    Weight::Silverpoint,
    Weight::Pencil,
    Weight::Pen,
    Weight::Rotring,
    Weight::Crayon,
    Weight::Chalk,
    Weight::BrushThin,
    Weight::BrushThick,
    Weight::OilPaint,
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
                "thick_stroke_width": thick_width(weight),
                "extra_thick_stroke_width": extra_thick_width(weight),
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
            "computer_cells": {
                "lattice_ratio": grammar(Weight::Computer).quantize,
                "opacity": COMPUTER_CELL_OPACITY,
                "opacity_floor": COMPUTER_CELL_OPACITY_FLOOR,
            },
            "chalk_fill": {
                "tooth_weight": CHALK_TOOTH_WEIGHT,
                "tooth_frequency": CHALK_TOOTH_FREQUENCY,
                "press_weight": CHALK_PRESS_WEIGHT,
                "pass_frequency": [CHALK_PASS_FREQUENCY.0, CHALK_PASS_FREQUENCY.1],
                "slope": CHALK_SLOPE,
                "intercept": {
                    "normal": CHALK_INTERCEPTS[0],
                    "dense": CHALK_INTERCEPTS[1],
                    "faint": CHALK_INTERCEPTS[2],
                },
                "film": {
                    "normal": CHALK_FILMS[0],
                    "dense": CHALK_FILMS[1],
                    "faint": CHALK_FILMS[2],
                },
            },
        },
        "performance": {
            "amplitude_widths": {
                "fine": amplitude_width(Amplitude::Fine),
                "medium": amplitude_width(Amplitude::Medium),
                "broad": amplitude_width(Amplitude::Broad),
            },
            "line_path_shares": {
                "fine": line_path_share(Amplitude::Fine),
                "medium": line_path_share(Amplitude::Medium),
                "broad": line_path_share(Amplitude::Broad),
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
        assert_eq!(weights.len(), 12);
        let oil = weights
            .iter()
            .find(|weight| weight["weight"] == "oil_paint")
            .unwrap();
        assert_eq!(oil["stroke_width"], 12.0);
        assert_eq!(oil["texture_filter"], false);
        assert_eq!(weights[0]["weight"], "silverpoint");
        assert_eq!(weights[0]["stroke_width"], 0.5);
        assert_eq!(reference["performance"]["frequency_cycles"]["high"], 14.0);
        assert_eq!(
            reference["performance"]["line_path_shares"]["medium"],
            0.054
        );
        assert_eq!(reference["performance"]["blur_ratio"]["broad"], 0.07);
        assert_eq!(
            reference["weight_properties"]["computer_cells"]["opacity_floor"],
            0.15
        );
        assert_eq!(
            reference["weight_properties"]["chalk_fill"]["film"]["normal"],
            0.35
        );
    }
}
