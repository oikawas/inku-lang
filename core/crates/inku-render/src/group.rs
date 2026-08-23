//! Per-member variation and fade semantics for expanded groups.

use crate::determinism::hash01;
use crate::planning::instruction_anchor;
use crate::stroke::grammar;
use crate::types::{Arrangement, Color, Fade, Instruction, Layout, Point, Primitive, Seed};

fn scale_member(instruction: &Instruction, scale: f64) -> Instruction {
    let mut scaled = instruction.clone();
    match instruction.primitive {
        Primitive::Line => {
            if let (Some(start), Some(end)) = (instruction.from_, instruction.to) {
                let middle = Point::new((start.x + end.x) / 2.0, (start.y + end.y) / 2.0);
                scaled.from_ = Some(Point::new(
                    middle.x + (start.x - middle.x) * scale,
                    middle.y + (start.y - middle.y) * scale,
                ));
                scaled.to = Some(Point::new(
                    middle.x + (end.x - middle.x) * scale,
                    middle.y + (end.y - middle.y) * scale,
                ));
            }
        }
        Primitive::Square | Primitive::Triangle => {
            if let (Some(position), Some(size)) = (instruction.position, instruction.size) {
                let scaled_size = Point::new(size.x * scale, size.y * scale);
                scaled.size = Some(scaled_size);
                scaled.position = Some(Point::new(
                    position.x - (scaled_size.x - size.x) / 2.0,
                    position.y - (scaled_size.y - size.y) / 2.0,
                ));
            }
        }
        _ if instruction.radius.is_some() => {
            scaled.radius = instruction.radius.map(|radius| radius * scale);
        }
        _ if instruction.size.is_some() => {
            scaled.size = instruction
                .size
                .map(|size| Point::new(size.x * scale, size.y * scale));
        }
        _ => {}
    }
    scaled
}

fn member_sizes(
    items: Vec<Instruction>,
    arrangement: &Arrangement,
    member_seed: Option<Seed>,
) -> Vec<Instruction> {
    let Some(seed) = member_seed else {
        return items;
    };
    if arrangement.layout == Layout::Grid || items.len() < 2 {
        return items;
    }
    let hand = grammar(items[0].weight).group_hand;
    if hand <= 0.0 {
        return items;
    }
    items
        .into_iter()
        .enumerate()
        .map(|(index, item)| {
            let scale = 1.0 + (hash01(index as i64, seed, "member-size") - 0.5) * 2.0 * hand;
            scale_member(&item, scale)
        })
        .collect()
}

fn member_rotations(
    items: Vec<Instruction>,
    arrangement: &Arrangement,
    member_seed: Option<Seed>,
) -> Vec<Instruction> {
    let Some(seed) = member_seed else {
        return items;
    };
    if arrangement.layout == Layout::Grid || items.len() < 2 {
        return items;
    }
    let stated = &items[0];
    if matches!(stated.primitive, Primitive::Line | Primitive::Circle) || stated.rotation.is_some()
    {
        return items;
    }
    let spread = grammar(stated.weight).group_rotation;
    if spread <= 0.0 {
        return items;
    }
    items
        .into_iter()
        .enumerate()
        .map(|(index, mut item)| {
            let delta = (hash01(index as i64, seed, "member-rot") - 0.5) * 2.0 * spread;
            item.rotation = Some(item.rotation.unwrap_or(0.0) + delta);
            item
        })
        .collect()
}

#[must_use]
pub fn fade_levels(
    items: &[Instruction],
    arrangement: &Arrangement,
    layout_center: Option<Point>,
) -> Option<Vec<f64>> {
    let (near, far) = match arrangement.fade {
        Fade::Outward => (0.62, 0.18),
        Fade::Directional => (0.70, 0.26),
        Fade::None => return None,
    };
    if items.len() < 2 {
        return None;
    }
    let ratios: Vec<f64> = if arrangement.fade == Fade::Directional {
        (0..items.len())
            .map(|index| index as f64 / (items.len() - 1) as f64)
            .collect()
    } else {
        let anchors: Vec<Point> = items.iter().map(instruction_anchor).collect();
        let center = arrangement.center.or(layout_center).unwrap_or_else(|| {
            Point::new(
                anchors.iter().map(|point| point.x).sum::<f64>() / anchors.len() as f64,
                anchors.iter().map(|point| point.y).sum::<f64>() / anchors.len() as f64,
            )
        });
        let distances: Vec<f64> = anchors
            .iter()
            .map(|point| (point.x - center.x).hypot(point.y - center.y))
            .collect();
        let nearest = distances.iter().copied().fold(f64::INFINITY, f64::min);
        let farthest = distances.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        let span = farthest - nearest;
        if span < 1.0e-9 {
            return None;
        }
        distances
            .into_iter()
            .map(|distance| (distance - nearest) / span)
            .collect()
    };
    Some(
        ratios
            .into_iter()
            .map(|ratio| near + (far - near) * ratio)
            .collect(),
    )
}

fn normalized_hint(value: &str) -> String {
    let mut normalized = String::new();
    let mut separator = false;
    for character in value.to_lowercase().chars() {
        if character.is_whitespace() || ":_()'\".,/-".contains(character) {
            separator = !normalized.is_empty();
        } else {
            if separator {
                normalized.push(' ');
                separator = false;
            }
            normalized.push(character);
        }
    }
    normalized.trim().to_owned()
}

fn render_effect_hint(hint: Option<&str>) -> Option<String> {
    const TOKENS: &[&str] = &[
        "membrane",
        "haze",
        "fog",
        "mist",
        "atmosphere",
        "膜",
        "霞",
        "霧",
        "靄",
        "soft light",
        "柔らかな光",
        "陽光",
        "日差し",
        "scent",
        "fragrance",
        "香り",
        "匂",
        "waiting buds",
        "開花を待つ蕾",
        "蕾",
        "つぼみ",
        "five-sense",
        "五感",
        "fade directional",
        "fade=directional",
        "fade outward",
        "fade=outward",
        "reflection",
        "反射",
        "映り",
    ];
    let normalized = normalized_hint(hint?);
    let kept: Vec<&str> = TOKENS
        .iter()
        .copied()
        .filter(|token| normalized.contains(token))
        .collect();
    (!kept.is_empty()).then(|| kept.join("; "))
}

fn apply_color_cycle(items: &mut [Instruction], cycle: &[Color]) {
    if cycle.is_empty() {
        return;
    }
    for (index, item) in items.iter_mut().enumerate() {
        item.color = cycle[index % cycle.len()];
        item.color_hint = render_effect_hint(item.color_hint.as_deref());
    }
}

fn apply_fade_levels(
    items: &mut [Instruction],
    arrangement: &Arrangement,
    layout_center: Option<Point>,
) {
    let Some(levels) = fade_levels(items, arrangement, layout_center) else {
        return;
    };
    for (item, level) in items.iter_mut().zip(levels) {
        let tag = format!("fade_level={level:.4}");
        item.color_hint = Some(
            item.color_hint
                .as_ref()
                .map_or(tag.clone(), |hint| format!("{hint}; {tag}")),
        );
    }
}

/// Apply group color, fade, size, and rotation in their canonical order.
#[must_use]
pub fn finish_group(
    mut items: Vec<Instruction>,
    arrangement: &Arrangement,
    layout_center: Option<Point>,
    member_seed: Option<Seed>,
) -> Vec<Instruction> {
    apply_color_cycle(&mut items, &arrangement.color_cycle);
    apply_fade_levels(&mut items, arrangement, layout_center);
    member_rotations(
        member_sizes(items, arrangement, member_seed),
        arrangement,
        member_seed,
    )
}
