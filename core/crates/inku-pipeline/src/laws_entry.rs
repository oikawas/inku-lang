//! The laws stage from a saved work: the AI refinement's laws move (the
//! author's decisions of 2026-10-20).
//!
//! The laws stage applies laws to a composed plan and prints the whole plan
//! again (SPEC §12.6.4). A saved work keeps no plan, only its instructions: a
//! work without laws keeps the composed document as its DDL, and a work whose
//! laws were applied keeps the composed document the laws read
//! ([`crate::laws_record::LawsBasis`]). [`composed_plan_of`] reads such a
//! document back as the plan it was printed from: every word a plan writes of
//! each layer, its range as written, and its joint. The laws stage then runs as
//! in a description run, and [`spliced`] puts the document's own lines back
//! where the laws changed nothing, so that the older wording of a saved work
//! stays wherever the laws did not touch it.
//!
//! Whether the plan draws what the document draws is the machine's check (the
//! two compile to the same Score): a word the plan cannot carry would be lost
//! from a layer the laws print again.

use inku_ddl::work_plan::{
    ComposedRange, WorkPlan, WorkPlanPlugin, WorkPlanPluginCall, composition_background,
    plan_ground, plan_layer,
};
use inku_ddl::{
    MacroDefinition, MacroExpansionLimits, ResolvedInstructionLanguage, SemanticHead,
    SemanticInstruction, SemanticNumericRange,
};

use crate::composition::{region_of_bounds, written_range};
use crate::laws::{ComposedPlan, LawsPrint};
use crate::recompose::{canonical, written_joint};

/// Read a document back as the composed plan it was printed from: its ground
/// and background, its plugin sentences (before the layers, as a plan prints
/// them), and one layer for each other sentence with its range as written and
/// the joint it ends with. `Err` names why it cannot be read, with the reasons
/// "change the layout" gives.
pub fn composed_plan_of(
    source: &str,
    language: ResolvedInstructionLanguage,
    definitions: &[MacroDefinition],
    limits: MacroExpansionLimits,
    plugins: &[WorkPlanPlugin],
) -> Result<ComposedPlan, &'static str> {
    let compilation = canonical(source, language, definitions, limits).ok_or("not_canonical")?;
    let ast = &compilation
        .semantic_document
        .as_ref()
        .ok_or("not_canonical")?
        .ast;
    if !ast.coordinated_head_groups.is_empty()
        || !ast.group_predicates.is_empty()
        || !ast.continuations.is_empty()
    {
        return Err("unsupported_sentence");
    }
    let ground = ast
        .ground
        .as_ref()
        .map(|ground| plan_ground(ground).ok_or("unsupported_sentence"))
        .transpose()?;
    let background = ast
        .background
        .as_ref()
        .map(|background| composition_background(background).ok_or("unsupported_sentence"))
        .transpose()?;
    let mut plan = WorkPlan {
        ground,
        background,
        plugins: Vec::new(),
        layers: Vec::new(),
    };
    let mut ranges = Vec::new();
    let mut joints = Vec::new();
    for instruction in &ast.instructions {
        if let SemanticHead::MacroInvocation(head) = &instruction.entity.head {
            if !plan.layers.is_empty()
                || instruction.position.is_some()
                || instruction.relation.is_some()
                || instruction.entity.numeric_range.is_some()
            {
                return Err("unsupported_sentence");
            }
            plan.plugins.push(plugin_call(
                &head.qualified_name,
                instruction
                    .entity
                    .quantity
                    .as_ref()
                    .map(|quantity| quantity.value),
                plugins,
            )?);
            continue;
        }
        let joint = match &instruction.relation {
            None => None,
            Some(relation) => Some(
                written_joint(relation)
                    .filter(|_| !plan.layers.is_empty())
                    .ok_or("unsupported_sentence")?
                    .relation_type()
                    .to_owned(),
            ),
        };
        let layer = plan_layer(&SemanticInstruction {
            relation: None,
            ..instruction.clone()
        })
        .ok_or("unsupported_sentence")?;
        let range = instruction
            .entity
            .numeric_range
            .as_ref()
            .map(|range| composed_range(source, range, language))
            .transpose()?;
        plan.layers.push(layer);
        ranges.push(range);
        joints.push(joint);
    }
    if plan.layers.is_empty() {
        return Err("nothing_to_move");
    }
    Ok(ComposedPlan {
        plan,
        ranges,
        joints,
    })
}

/// The plan's call of a plugin sentence: its canonical name and the count it
/// writes, when the plugin receives one.
fn plugin_call(
    name: &str,
    count: Option<u64>,
    plugins: &[WorkPlanPlugin],
) -> Result<WorkPlanPluginCall, &'static str> {
    let plugin = plugins
        .iter()
        .find(|plugin| plugin.name == name || plugin.aliases.iter().any(|alias| alias == name))
        .ok_or("unsupported_sentence")?;
    if count.is_some() && plugin.counter.is_none() {
        return Err("unsupported_sentence");
    }
    Ok(WorkPlanPluginCall {
        name: plugin.name.clone(),
        count,
    })
}

/// A range as the document writes it: its words in the document's language
/// (with an old mark, which the words print again) and its bounds. The other
/// language's words are the composition's for one of its ranges, else the same.
fn composed_range(
    source: &str,
    range: &SemanticNumericRange,
    language: ResolvedInstructionLanguage,
) -> Result<ComposedRange, &'static str> {
    let span = range.source().span;
    let text = source
        .get(span.start_byte..span.end_byte)
        .ok_or("unsupported_sentence")?
        .trim();
    let words = match language {
        ResolvedInstructionLanguage::Ja => text.split_once('（').map(|(words, _)| words),
        ResolvedInstructionLanguage::En => text
            .strip_prefix("the ")
            .and_then(|text| text.split_once(" (").map(|(words, _)| words)),
    }
    .filter(|words| !words.is_empty())
    .ok_or("unsupported_sentence")?
    .to_owned();
    let exact = range
        .bounds
        .map(|value| (value.numerator(), value.denominator()));
    let narrow = |(numerator, denominator): (u64, u64)| {
        Some((
            u32::try_from(numerator).ok()?,
            u32::try_from(denominator).ok()?,
        ))
    };
    let bounds = [
        narrow(exact[0]).ok_or("unsupported_sentence")?,
        narrow(exact[1]).ok_or("unsupported_sentence")?,
        narrow(exact[2]).ok_or("unsupported_sentence")?,
        narrow(exact[3]).ok_or("unsupported_sentence")?,
    ];
    let table = region_of_bounds(exact).and_then(written_range);
    let (words_ja, words_en) = match language {
        ResolvedInstructionLanguage::Ja => {
            let other = table
                .filter(|table| table.words_ja == words)
                .map_or_else(|| words.clone(), |table| table.words_en);
            (words, other)
        }
        ResolvedInstructionLanguage::En => {
            let other = table
                .filter(|table| table.words_en == words)
                .map_or_else(|| words.clone(), |table| table.words_ja);
            (other, words)
        }
    };
    Ok(ComposedRange {
        words_ja,
        words_en,
        bounds,
    })
}

/// The document the laws printed, with the base document's own lines where
/// the laws changed nothing: its ground, background and plugin lines, and the
/// line of each layer the laws did not change. `composed` is the composed
/// plan's print of the base (`layers` layers), `printed` the laws' print.
/// `None` when the base is not one line a sentence as the plan prints it, or a
/// line the laws did not change is not the plan's line of that layer.
#[must_use]
pub fn spliced(
    base: &str,
    composed: &str,
    layers: usize,
    printed: &str,
    print: &LawsPrint,
) -> Option<String> {
    let base_lines: Vec<&str> = base.split('\n').collect();
    let composed_lines: Vec<&str> = composed.split('\n').collect();
    let printed_lines: Vec<&str> = printed.split('\n').collect();
    if base_lines.len() != composed_lines.len() || composed_lines.len() < layers {
        return None;
    }
    let head = composed_lines.len() - layers;
    if printed_lines.len() != head + print.composed.len()
        || printed_lines[..head] != composed_lines[..head]
    {
        return None;
    }
    let mut lines: Vec<&str> = base_lines[..head].to_vec();
    for (line, layer) in printed_lines[head..].iter().zip(&print.composed) {
        if print.changed.contains(layer) {
            lines.push(line);
        } else if *line == composed_lines[head + layer] {
            lines.push(base_lines[head + layer]);
        } else {
            return None;
        }
    }
    Some(lines.join("\n"))
}
