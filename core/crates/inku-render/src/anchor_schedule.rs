//! Dependency order for positioned, non-drawing targets and their transform scopes.

use std::collections::BTreeSet;

use inku_score::{RelationType, Score, TransformGroup};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ScheduleNode {
    Instruction(usize),
    Group(usize),
}

pub(crate) struct AnchorSchedule {
    pub(crate) order: Vec<ScheduleNode>,
    pub(crate) cyclic_relations: Vec<usize>,
    pub(crate) external_groups: Vec<Option<usize>>,
}

/// Empty instruction ranges alone do not establish lexical containment.
pub(crate) fn group_contains(outer: &TransformGroup, inner: &TransformGroup) -> bool {
    inku_score::transform_group_contains(outer, inner)
}

fn group_chain(score: &Score, instruction: Option<usize>, anchor: Option<usize>) -> Vec<usize> {
    score
        .transform_groups
        .iter()
        .enumerate()
        .filter(|(_, group)| {
            instruction.is_some_and(|index| group.start <= index && index < group.end)
                || anchor.is_some_and(|index| group.anchor_indices.contains(&index))
        })
        .map(|(index, _)| index)
        .collect()
}

fn below_common(chain: &[usize], common: Option<usize>) -> Option<usize> {
    chain
        .iter()
        .copied()
        .take_while(|group| Some(*group) != common)
        .last()
}

/// An instruction sees its target after the target's inner transforms, but
/// before any common outer transform. An external relation correction belongs
/// to the outermost source group below that common scope.
pub(crate) fn schedule(score: &Score, omitted_relations: &[bool]) -> AnchorSchedule {
    let count = score.instructions.len();
    let group_count = score.transform_groups.len();
    let node_count = count + group_count;
    let mut dependencies = vec![BTreeSet::<usize>::new(); node_count];
    let mut external_groups = vec![None; count];
    let mut relation_edges = vec![Vec::new(); count];

    for (group_index, group) in score.transform_groups.iter().enumerate() {
        let group_node = count + group_index;
        dependencies[group_node].extend(group.start..group.end.min(count));
        for (inner_index, inner) in score.transform_groups[..group_index].iter().enumerate() {
            if group_contains(group, inner) {
                dependencies[group_node].insert(count + inner_index);
            }
        }
    }

    for (source_index, instruction) in score.instructions.iter().enumerate() {
        if omitted_relations[source_index] {
            continue;
        }
        let Some(relation) = &instruction.relation else {
            continue;
        };
        let source_chain = group_chain(score, Some(source_index), None);
        let targets = if let Some(anchor) = relation.target_anchor_index {
            vec![(None, Some(anchor))]
        } else if let Some(target) = relation.target_instruction_index {
            let mut targets = vec![(Some(target), None)];
            if relation.kind == RelationType::Between
                && let Some(second) = source_index.checked_sub(2)
            {
                targets.push((Some(second), None));
            }
            targets
        } else {
            let needed = if relation.kind == RelationType::Between {
                2
            } else {
                1
            };
            (1..=needed)
                .filter_map(|offset| source_index.checked_sub(offset))
                .map(|target| (Some(target), None))
                .collect()
        };
        for (target_instruction, target_anchor) in targets {
            if target_instruction.is_some_and(|target| target >= count)
                || target_anchor.is_some_and(|target| target >= score.anchors.len())
            {
                // The existing boundary reports a missing reference; no guessed edge.
                continue;
            }
            let target_chain = group_chain(score, target_instruction, target_anchor);
            let common = source_chain
                .iter()
                .copied()
                .find(|group| target_chain.contains(group));
            let source_group = below_common(&source_chain, common);
            let target_final = below_common(&target_chain, common)
                .map(|group| count + group)
                .or(target_instruction);
            // Between may see one target inside the source scope and one
            // outside it. Its correction belongs to the outermost such scope.
            external_groups[source_index] = external_groups[source_index].max(source_group);
            if let Some(source_group) = source_group {
                if let Some(target_final) = target_final {
                    dependencies[count + source_group].insert(target_final);
                    relation_edges[source_index].push((count + source_group, target_final));
                }
            } else if let Some(target_final) = target_final {
                dependencies[source_index].insert(target_final);
                relation_edges[source_index].push((source_index, target_final));
            }
        }
    }

    let dependencies = dependencies
        .into_iter()
        .map(|edges| edges.into_iter().collect::<Vec<_>>())
        .collect::<Vec<_>>();
    let mut state = vec![0_u8; node_count];
    let mut stack_position = vec![None; node_count];
    let mut cyclic = BTreeSet::new();
    let mut order = Vec::with_capacity(node_count);
    // Iterative DFS also accepts deeply nested, bounded definitions without
    // consuming one Rust call frame per generated node.
    for root in 0..node_count {
        if state[root] != 0 {
            continue;
        }
        state[root] = 1;
        stack_position[root] = Some(0);
        let mut stack = vec![(root, 0_usize)];
        while let Some(&(node, cursor)) = stack.last() {
            if let Some(&dependency) = dependencies[node].get(cursor) {
                stack.last_mut().expect("nonempty traversal").1 += 1;
                match state[dependency] {
                    0 => {
                        state[dependency] = 1;
                        stack_position[dependency] = Some(stack.len());
                        stack.push((dependency, 0));
                    }
                    1 => {
                        let start = stack_position[dependency].expect("active dependency");
                        cyclic.extend(stack[start..].iter().map(|(node, _)| *node));
                    }
                    _ => {}
                }
            } else {
                stack.pop();
                stack_position[node] = None;
                state[node] = 2;
                order.push(node);
            }
        }
    }
    let as_node = |node| {
        if node < count {
            ScheduleNode::Instruction(node)
        } else {
            ScheduleNode::Group(node - count)
        }
    };
    AnchorSchedule {
        order: order
            .into_iter()
            .filter(|node| !cyclic.contains(node))
            .map(as_node)
            .collect(),
        cyclic_relations: relation_edges
            .iter()
            .enumerate()
            .filter_map(|(source, edges)| {
                edges
                    .iter()
                    .any(|&(from, to)| {
                        if !cyclic.contains(&from) || !cyclic.contains(&to) {
                            return false;
                        }
                        // Only remove relation edges inside the same cycle, not
                        // edges between otherwise independent cyclic components.
                        let mut pending = vec![to];
                        let mut visited = BTreeSet::new();
                        while let Some(node) = pending.pop() {
                            if node == from {
                                return true;
                            }
                            if visited.insert(node) {
                                pending.extend(dependencies[node].iter().copied());
                            }
                        }
                        false
                    })
                    .then_some(source)
            })
            .collect(),
        external_groups,
    }
}
