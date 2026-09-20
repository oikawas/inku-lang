//! Compiler-owned context and deliberately conservative partial patch boundaries.

use std::collections::{BTreeMap, BTreeSet};

use inku_ddl::{
    SemanticDeliveryOwner as Owner, SemanticFillTarget, SemanticHead, SemanticPreviousReference,
    SourceSpan, TypedDdlCompilation, TypedHole,
};
use serde_json::{Value, json};

fn contains(outer: SourceSpan, inner: SourceSpan) -> bool {
    outer.start_byte <= inner.start_byte && inner.end_byte <= outer.end_byte
}

pub(crate) fn confirmed_bindings(
    compilation: &TypedDdlCompilation,
    span: SourceSpan,
) -> Vec<Value> {
    let Some(semantic) = &compilation.semantic_document else {
        return vec![];
    };
    let source = compilation.document.source();
    let text = |span: SourceSpan| &source[span.start_byte..span.end_byte];
    semantic.ast.instructions.iter().enumerate().filter(|(_, instruction)| contains(span, instruction.entity.head.source().span)).map(|(index, instruction)| {
        let entity = &instruction.entity;
        let mut facts = Vec::new();
        for (role, term) in [
            (Owner::Color, &entity.color), (Owner::Touch, &entity.touch),
            (Owner::Continuity, &entity.continuity), (Owner::Angle, &entity.angle),
            (Owner::SurfaceQuality, &entity.surface.quality), (Owner::SurfaceIntensity, &entity.surface.intensity),
            (Owner::InkSpread, &entity.fluctuation.spread), (Owner::FluctuationAmplitude, &entity.fluctuation.amplitude),
            (Owner::FluctuationFrequency, &entity.fluctuation.frequency), (Owner::FluctuationQuality, &entity.fluctuation.quality),
            (Owner::ProportionAspect, &entity.proportion.aspect), (Owner::ProportionWidthExtent, &entity.proportion.width_extent),
            (Owner::ProportionArcForm, &entity.proportion.arc_form), (Owner::Action, &instruction.action),
            (Owner::Position, &instruction.position), (Owner::LayoutDirection, &instruction.layout_direction),
        ] {
            if let Some(term) = term { facts.push(json!({"role":role.as_str(),"source":text(term.provenance.source.span)})); }
        }
        if let Some(quantity) = &entity.quantity { facts.push(json!({"role":Owner::Quantity.as_str(),"source":text(quantity.provenance.span),"value":quantity.value})); }
        if let Some(thinness) = &entity.thinness { facts.push(json!({"role":Owner::Thinness.as_str(),"source":text(thinness.provenance.span)})); }
        if let Some(scale) = &entity.relative_scale { facts.push(json!({"role":Owner::RelativeScale.as_str(),"source":text(scale.provenance.span)})); }
        if let Some(relation) = &instruction.relation { facts.push(json!({"role":Owner::Relation.as_str(),"source":text(relation.provenance.span)})); }
        json!({"owner":format!("o{}", index+1),"head":text(entity.head.source().span),"facts":facts})
    }).collect()
}

pub(crate) fn confirmed_context_spans(
    compilation: &TypedDdlCompilation,
    selected: &[&TypedHole],
) -> Vec<SourceSpan> {
    let Some(semantic) = &compilation.semantic_document else {
        return vec![];
    };
    let ast = &semantic.ast;
    let clauses = &semantic
        .instruction_association
        .association
        .clause_stream
        .clauses;
    let clause_for = |span| {
        clauses
            .iter()
            .position(|clause| contains(clause.span, span))
    };
    let instruction_clauses = ast
        .instructions
        .iter()
        .map(|instruction| clause_for(instruction.entity.head.source().span))
        .collect::<Vec<_>>();
    let mut edges = Vec::new();
    let mut connect = |left: Option<usize>, right: Option<usize>| {
        if let (Some(left), Some(right)) = (left, right) {
            edges.push((left, right));
        }
    };
    for continuation in &ast.continuations {
        connect(
            clause_for(continuation.predicate_span),
            instruction_clauses
                .get(continuation.target_instruction_index)
                .copied()
                .flatten(),
        );
    }
    for (index, instruction) in ast.instructions.iter().enumerate() {
        if let Some(SemanticFillTarget::InlineShape {
            target_instruction_index,
            ..
        }) = instruction.fill_target
        {
            connect(
                instruction_clauses[index],
                instruction_clauses
                    .get(target_instruction_index)
                    .copied()
                    .flatten(),
            );
        }
        // With no coordinated groups, the compiler's previous-reference ordinal
        // is exactly the source-ordered instruction ordinal.
        if ast.coordinated_head_groups.is_empty()
            && semantic.instruction_association.relation_issues.is_empty()
            && semantic.continuation_issues.is_empty()
            && !compilation.holes.iter().any(|hole| {
                hole.allowed_span.start_byte < instruction.entity.head.source().span.start_byte
            })
            && let Some(relation) = &instruction.relation
        {
            let depth = match relation.reference {
                SemanticPreviousReference::PreviousOne => 1,
                SemanticPreviousReference::PreviousTwo => 2,
            };
            if index >= depth {
                for target in index - depth..index {
                    connect(instruction_clauses[index], instruction_clauses[target]);
                }
            }
        }
    }
    for group in &ast.coordinated_head_groups {
        for pair in group.member_instruction_indices.windows(2) {
            connect(
                instruction_clauses.get(pair[0]).copied().flatten(),
                instruction_clauses.get(pair[1]).copied().flatten(),
            );
        }
    }
    let mut reached = selected
        .iter()
        .filter_map(|hole| clause_for(hole.allowed_span))
        .collect::<BTreeSet<_>>();
    // Finite graph closure; no provider retries or candidate subset exploration.
    loop {
        let before = reached.len();
        for &(left, right) in &edges {
            if reached.contains(&left) || reached.contains(&right) {
                reached.extend([left, right]);
            }
        }
        if reached.len() == before {
            break;
        }
    }
    reached
        .into_iter()
        .map(|index| clauses[index].span)
        .collect()
}

/// Split only compiler-owned single-instruction clauses with no cross-clause
/// dependencies. Any uncertain boundary stays in one atomic request unit.
pub(crate) fn independent_units(
    compilation: &TypedDdlCompilation,
    holes: &[&TypedHole],
) -> Vec<Vec<String>> {
    // Support repair cannot change drawable ordinals: the validator requires the
    // same support owner and rejects added drawable/other explicit owners. Keep
    // declarations of the same support kind together and revalidate the union.
    let mut supports = BTreeMap::<Owner, Vec<String>>::new();
    let mut drawing_holes = Vec::new();
    for hole in holes {
        let support = compilation.semantic_document.as_ref().and_then(|semantic| {
            semantic
                .instruction_association
                .association
                .clause_stream
                .clauses
                .iter()
                .find(|clause| clause.span == hole.allowed_span)
                .and_then(inku_ddl::compiler_lock::isolated_support_clause_owner)
        });
        if let Some(owner) = support {
            supports.entry(owner).or_default().push(hole.id.clone());
        } else {
            drawing_holes.push(*hole);
        }
    }
    let mut units = supports.into_values().collect::<Vec<_>>();
    let mut coupled = Vec::new();
    for hole in drawing_holes {
        if standalone_instruction_index(compilation, hole).is_some() {
            // Provisional until the candidate's reference namespace is checked.
            units.push(vec![hole.id.clone()]);
        } else {
            coupled.push(hole);
        }
    }
    if !coupled.is_empty() {
        units.extend(independent_drawing_units(compilation, &coupled));
    }
    units
}

fn simple_reference_namespace(compilation: &TypedDdlCompilation) -> bool {
    compilation
        .semantic_document
        .as_ref()
        .is_some_and(|semantic| {
            semantic.continuation_issues.is_empty()
                && semantic.ast.continuations.is_empty()
                && semantic.ast.coordinated_head_groups.is_empty()
                && semantic.ast.group_predicates.is_empty()
                && semantic
                    .instruction_association
                    .coordination_issues
                    .is_empty()
                && semantic
                    .instruction_association
                    .association
                    .ast
                    .sequences
                    .is_empty()
                && semantic.ast.instructions.iter().all(|instruction| {
                    matches!(instruction.entity.head, SemanticHead::Primitive(_))
                        && instruction.sequence.is_none()
                        && instruction.fill_target.is_none()
                })
        })
}

/// One existing drawable owner with a bound count or no numeric occurrence
/// or recognized unresolved diagnostic (which may denote a qualitative count).
/// Unresolved wording is not itself a dependency edge; the candidate still
/// needs the post-compile proof, including preservation of an omitted count.
fn standalone_instruction_index(
    compilation: &TypedDdlCompilation,
    hole: &TypedHole,
) -> Option<usize> {
    if hole.kind != "unresolved_clause" || !simple_reference_namespace(compilation) {
        return None;
    }
    let semantic = compilation.semantic_document.as_ref()?;
    let ast = &semantic.ast;
    let mut owners = ast
        .instructions
        .iter()
        .enumerate()
        .filter(|(_, instruction)| {
            contains(hole.allowed_span, instruction.entity.head.source().span)
        });
    let (index, instruction) = owners.next()?;
    if owners.next().is_some()
        || instruction.relation.is_some()
        || !instruction
            .action
            .as_ref()
            .is_some_and(|action| contains(hole.allowed_span, action.provenance.source.span))
        || match instruction.entity.quantity.as_ref() {
            Some(quantity) => !contains(hole.allowed_span, quantity.provenance.span),
            None => semantic
                .instruction_association
                .association
                .clause_stream
                .clauses
                .iter()
                .flat_map(|clause| &clause.atoms)
                .any(|atom| {
                    contains(hole.allowed_span, atom.span())
                        && (matches!(
                            atom,
                            inku_ddl::ClauseAtom::UnattachedExactNumber(_)
                                | inku_ddl::ClauseAtom::FunctionWord {
                                    exact_decimal: Some(_),
                                    ..
                                }
                        ) || matches!(
                            atom,
                            inku_ddl::ClauseAtom::UnresolvedDiagnostic(diagnostic)
                                if diagnostic.recognized
                        ))
                }),
        }
    {
        return None;
    }
    Some(index)
}

/// A later incoming reference does not require rolling back a repaired earlier
/// owner. Its source-ordered identity is unchanged, and the repaired owner must
/// not acquire an outgoing dependency on another unresolved clause.
pub(crate) fn standalone_repair_preserves_namespace(
    base: &TypedDdlCompilation,
    candidate: &TypedDdlCompilation,
    hole: &TypedHole,
) -> bool {
    let Some(index) = standalone_instruction_index(base, hole) else {
        return true;
    };
    if !simple_reference_namespace(candidate) {
        return false;
    }
    let before = &base.semantic_document.as_ref().unwrap().ast.instructions;
    let after = &candidate
        .semantic_document
        .as_ref()
        .unwrap()
        .ast
        .instructions;
    before.len() == after.len()
        && before.iter().zip(after).all(|(before, after)| {
            let (SemanticHead::Primitive(left), SemanticHead::Primitive(right)) =
                (&before.entity.head, &after.entity.head)
            else {
                return false;
            };
            left.identity == right.identity
                && before
                    .entity
                    .quantity
                    .as_ref()
                    .map(|quantity| quantity.value)
                    == after
                        .entity
                        .quantity
                        .as_ref()
                        .map(|quantity| quantity.value)
                && before.action.as_ref().map(|action| &action.identity)
                    == after.action.as_ref().map(|action| &action.identity)
        })
        && after[index].relation.is_none()
}

fn independent_drawing_units(
    compilation: &TypedDdlCompilation,
    holes: &[&TypedHole],
) -> Vec<Vec<String>> {
    let atomic = || vec![holes.iter().map(|hole| hole.id.clone()).collect()];
    let Some(semantic) = &compilation.semantic_document else {
        return atomic();
    };
    let ast = &semantic.ast;
    let association = &semantic.instruction_association;
    if compilation
        .holes
        .iter()
        .any(|hole| hole.kind == "unresolved_clause")
        || !semantic.issues.is_empty()
        || !semantic.continuation_issues.is_empty()
        || !association.issues.is_empty()
        || !association.relation_issues.is_empty()
        || !association.coordination_issues.is_empty()
        || !ast.continuations.is_empty()
        || !ast.coordinated_head_groups.is_empty()
        || !ast.group_predicates.is_empty()
        || ast.instructions.iter().any(|instruction| {
            instruction.relation.is_some()
                || instruction.fill_target.is_some()
                || instruction.sequence.is_some()
                || !matches!(instruction.entity.head, SemanticHead::Primitive(_))
        })
        || !association.association.ast.sequences.is_empty()
    {
        return atomic();
    }
    let clauses = &association.association.clause_stream.clauses;
    let mut units = BTreeMap::<usize, Vec<String>>::new();
    for hole in holes {
        let Some((index, clause)) = clauses
            .iter()
            .enumerate()
            .find(|(_, clause)| contains(clause.span, hole.allowed_span))
        else {
            return atomic();
        };
        if ast
            .instructions
            .iter()
            .filter(|instruction| contains(clause.span, instruction.entity.head.source().span))
            .count()
            != 1
        {
            return atomic();
        }
        units.entry(index).or_default().push(hole.id.clone());
    }
    units.into_values().collect()
}
