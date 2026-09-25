//! Independent outward ink spread applied to the final performed mark.

use sha2::{Digest, Sha256};

use crate::marks::{MarkContext, mark_style};
use crate::svg::{Element, format_number};
use crate::types::{InkSpread, Instruction, SvgProfile};

fn identity(instruction: &Instruction, context: MarkContext<'_>) -> (String, u32) {
    let material = format!(
        "{}:{}:{}:ink-spread",
        context.seed_for(instruction),
        context.instruction_index,
        context.mark_index
    );
    let digest = Sha256::digest(material.as_bytes());
    let seed = u32::from_le_bytes(digest[..4].try_into().expect("four digest bytes"));
    (
        format!(
            "ink-spread-{:03}-{:03}-{seed:08x}",
            context.instruction_index, context.mark_index
        ),
        seed,
    )
}

fn filter(
    instruction: &Instruction,
    context: MarkContext<'_>,
    identifier: &str,
    seed: u32,
) -> Element {
    let scale = context.canvas.unit() / 1000.0;
    let extent = 12.0 * scale;
    let mut filter = Element::new("filter")
        .attr("id", identifier)
        .attr("filterUnits", "userSpaceOnUse")
        .attr("primitiveUnits", "userSpaceOnUse")
        .attr("x", format_number(-extent))
        .attr("y", format_number(-extent))
        .attr("width", format_number(context.canvas.width + extent * 2.0))
        .attr(
            "height",
            format_number(context.canvas.height + extent * 2.0),
        )
        .attr("color-interpolation-filters", "sRGB");
    filter.push(
        Element::new("feTurbulence")
            .attr("type", "fractalNoise")
            .attr("baseFrequency", format_number(0.026 / scale.max(1.0e-9)))
            .attr("numOctaves", "2")
            .attr("seed", seed.to_string())
            .attr("stitchTiles", "stitch")
            .attr("result", "inkSpreadNoise"),
    );
    filter.push(
        Element::new("feDisplacementMap")
            .attr("in", "SourceAlpha")
            .attr("in2", "inkSpreadNoise")
            .attr("scale", format_number(3.2 * scale))
            .attr("xChannelSelector", "R")
            .attr("yChannelSelector", "G")
            .attr("result", "inkSpreadDisplaced"),
    );
    filter.push(
        Element::new("feMorphology")
            .attr("in", "inkSpreadDisplaced")
            .attr("operator", "dilate")
            .attr("radius", format_number(4.2 * scale))
            .attr("result", "inkSpreadExpanded"),
    );
    filter.push(
        Element::new("feComposite")
            .attr("in", "inkSpreadExpanded")
            .attr("in2", "SourceAlpha")
            .attr("operator", "out")
            .attr("result", "inkSpreadOuter"),
    );
    filter.push(
        Element::new("feGaussianBlur")
            .attr("in", "inkSpreadOuter")
            .attr("stdDeviation", format_number(0.8 * scale))
            .attr("result", "inkSpreadSoft"),
    );
    filter.push(
        Element::new("feFlood")
            .attr("flood-color", mark_style(instruction, context).color)
            .attr("flood-opacity", "0.3")
            .attr("result", "inkSpreadColor"),
    );
    filter.push(
        Element::new("feComposite")
            .attr("in", "inkSpreadColor")
            .attr("in2", "inkSpreadSoft")
            .attr("operator", "in")
            .attr("result", "inkSpreadInk"),
    );
    let mut merge = Element::new("feMerge");
    merge.push(Element::new("feMergeNode").attr("in", "inkSpreadInk"));
    merge.push(Element::new("feMergeNode").attr("in", "SourceGraphic"));
    filter.push(merge);
    filter
}

/// Adds a deterministic halo without changing performed geometry or mark count.
pub(crate) fn wrap(mark: Element, instruction: &Instruction, context: MarkContext<'_>) -> Element {
    if instruction.ink_spread != Some(InkSpread::Bleed) || context.profile == SvgProfile::Compat {
        return mark;
    }
    let (identifier, seed) = identity(instruction, context);
    let mut definitions = Element::new("defs");
    definitions.push(filter(instruction, context, &identifier, seed));
    let mut painted = Element::new("g")
        .attr("class", "ink-spread-paint-v1")
        .attr("filter", format!("url(#{identifier})"));
    painted.push(mark);
    let mut group = Element::new("g").attr("class", "ink-spread-v1");
    group.push(definitions);
    group.push(painted);
    group
}
