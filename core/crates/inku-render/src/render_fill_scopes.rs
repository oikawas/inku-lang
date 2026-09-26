//! Preserve paint order while applying each fill boundary after its appearance.

use std::collections::BTreeMap;

use crate::compat_clip::{ClipError, ClipLimits, ClipOptions, clip_element};
use crate::performance::{PerformedFillScope, PerformedInstruction};
use crate::svg::{Element, Node};
use crate::types::SvgProfile;
use inku_score::{ScoreExecutionDiagnostic, ScoreExecutionDisposition, ScoreExecutionReason};

/// Explicit caller-owned cost and accuracy policy for one complete fill scope.
/// These bounds do not raise the Score's logical or primitive-count limits.
#[derive(Clone, Copy, Debug)]
pub struct CompatFillClipPolicy {
    pub tolerance_pixels: f64,
    pub limits: ClipLimits,
}

enum Paint {
    Element(Element, usize),
    Scope(usize),
}

struct ResolvedPaint {
    element: Element,
    instruction_indices: Vec<usize>,
}

pub(crate) struct FillPaintForest {
    roots: Vec<Paint>,
    children: Vec<Vec<Paint>>,
    registered: Vec<bool>,
    paint_order: BTreeMap<String, (usize, usize)>,
}

impl FillPaintForest {
    pub fn new(scope_count: usize) -> Self {
        Self {
            roots: Vec::new(),
            children: (0..scope_count).map(|_| Vec::new()).collect(),
            registered: vec![false; scope_count],
            paint_order: BTreeMap::new(),
        }
    }

    pub fn push(
        &mut self,
        element: Element,
        performed_index: usize,
        scope: Option<usize>,
        scopes: &[PerformedFillScope],
    ) {
        let id = format!("fill_paint_{performed_index}");
        self.paint_order
            .insert(id.clone(), (self.paint_order.len(), performed_index));
        let mut wrapper = Element::new("g").attr("id", id);
        wrapper.push(element);
        if let Some(index) = scope {
            self.register(index, scopes);
            self.children[index].push(Paint::Element(wrapper, performed_index));
        } else {
            self.roots.push(Paint::Element(wrapper, performed_index));
        }
    }

    fn register(&mut self, index: usize, scopes: &[PerformedFillScope]) {
        if self.registered[index] {
            return;
        }
        self.registered[index] = true;
        if let Some(parent) = scopes[index].parent_scope_index {
            self.register(parent, scopes);
            self.children[parent].push(Paint::Scope(index));
        } else {
            self.roots.push(Paint::Scope(index));
        }
    }

    pub fn finish(
        mut self,
        scopes: &[PerformedFillScope],
        profile: SvgProfile,
        definitions: &mut Vec<Element>,
        clip_policy: CompatFillClipPolicy,
        performed: &[PerformedInstruction],
    ) -> (Vec<Element>, Vec<ScoreExecutionDiagnostic>, Vec<usize>) {
        let roots = std::mem::take(&mut self.roots);
        let mut failures = BTreeMap::new();
        let mut elements = Vec::new();
        for paint in roots {
            if let Some(element) = self.resolve(
                paint,
                scopes,
                profile,
                definitions,
                clip_policy,
                &mut failures,
            ) {
                elements.push(element);
            }
        }
        // A clip refusal discards the complete admitted placement, including
        // earlier/later repetitions and sibling Emits outside this fill scope.
        let mut paints = Vec::new();
        for paint in elements {
            if !paint
                .instruction_indices
                .iter()
                .any(|index| failures.contains_key(index))
            {
                collect_paints(
                    &paint.element,
                    &mut Vec::new(),
                    &self.paint_order,
                    &mut paints,
                );
            }
        }
        // Whole-scope clipping must not regroup paint and carve instructions.
        // Recover their original paint order after the bounded tree operation.
        paints.sort_by_key(|(order, _)| *order);
        let elements = paints.into_iter().map(|(_, element)| element).collect();
        let mut originals = BTreeMap::new();
        for (index, reason) in failures {
            originals
                .entry(performed[index].original_instruction_index)
                .or_insert(reason);
        }
        let omitted = originals.keys().copied().collect();
        let diagnostics = originals
            .into_iter()
            .map(|(instruction_index, reason)| ScoreExecutionDiagnostic {
                instruction_index,
                anchor_index: None,
                dependency_instruction_index: None,
                reason,
                disposition: ScoreExecutionDisposition::Omitted,
            })
            .collect();
        (elements, diagnostics, omitted)
    }

    fn resolve(
        &mut self,
        paint: Paint,
        scopes: &[PerformedFillScope],
        profile: SvgProfile,
        definitions: &mut Vec<Element>,
        clip_policy: CompatFillClipPolicy,
        failures: &mut BTreeMap<usize, ScoreExecutionReason>,
    ) -> Option<ResolvedPaint> {
        let Paint::Scope(index) = paint else {
            let Paint::Element(element, performed_index) = paint else {
                unreachable!()
            };
            return Some(ResolvedPaint {
                element,
                instruction_indices: vec![performed_index],
            });
        };
        let scope = &scopes[index];
        let mut group = Element::new("g").attr("id", format!("fill_{index}"));
        for child in std::mem::take(&mut self.children[index]) {
            if let Some(element) =
                self.resolve(child, scopes, profile, definitions, clip_policy, failures)
            {
                group.push(element.element);
            }
        }
        if profile != SvgProfile::Compat {
            let id = format!("fill_target_{index}");
            let points = crate::svg::points_list(scope.prepared_region.contour());
            let mut clip = Element::new("clipPath")
                .attr("id", &id)
                .attr("clipPathUnits", "userSpaceOnUse");
            clip.push(Element::new("polygon").attr("points", points));
            definitions.push(clip);
            group.set_attr("clip-path", format!("url(#{id})"));
            return Some(ResolvedPaint {
                element: group,
                instruction_indices: scope.instruction_indices.clone(),
            });
        }
        let prefix = format!("fill_clip_{index}");
        match clip_element(
            &group,
            &scope.prepared_region,
            definitions,
            ClipOptions {
                tolerance: clip_policy.tolerance_pixels,
                id_prefix: &prefix,
                limits: clip_policy.limits,
            },
        ) {
            Ok(clipped) => Some(ResolvedPaint {
                element: clipped,
                instruction_indices: scope.instruction_indices.clone(),
            }),
            Err(error) => {
                let reason = match error {
                    ClipError::LimitExceeded(_) => ScoreExecutionReason::FillClipLimitExceeded,
                    _ => ScoreExecutionReason::FillClipUnsupported,
                };
                for &performed_index in scope
                    .atomic_instruction_groups
                    .last()
                    .unwrap_or(&scope.instruction_indices)
                {
                    failures.entry(performed_index).or_insert(reason);
                }
                None
            }
        }
    }
}

fn collect_paints(
    element: &Element,
    clips: &mut Vec<String>,
    order: &BTreeMap<String, (usize, usize)>,
    output: &mut Vec<(usize, Element)>,
) {
    if let Some(&(paint_order, _)) = element.attribute("id").and_then(|id| order.get(id)) {
        let mut paint = element.clone();
        for clip in clips.iter().rev() {
            let mut wrapper = Element::new("g").attr("clip-path", clip);
            wrapper.push(paint);
            paint = wrapper;
        }
        output.push((paint_order, paint));
        return;
    }
    let clip = element.attribute("clip-path");
    if let Some(clip) = clip {
        clips.push(clip.to_owned());
    }
    for child in element.children() {
        if let Node::Element(child) = child {
            collect_paints(child, clips, order, output);
        }
    }
    if clip.is_some() {
        clips.pop();
    }
}
