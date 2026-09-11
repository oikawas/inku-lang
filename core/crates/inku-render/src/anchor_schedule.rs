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
    pub(crate) cyclic: Vec<ScheduleNode>,
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
/// before any common outer transform. An external Connected correction belongs
/// to the outermost source group below that common scope.
pub(crate) fn schedule(score: &Score) -> AnchorSchedule {
    let count = score.instructions.len();
    let group_count = score.transform_groups.len();
    let node_count = count + group_count;
    let mut dependencies = vec![BTreeSet::<usize>::new(); node_count];
    let mut external_groups = vec![None; count];

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
        let Some(relation) = &instruction.relation else {
            continue;
        };
        let source_chain = group_chain(score, Some(source_index), None);
        let targets = if let Some(anchor) = relation.target_anchor_index {
            vec![(None, Some(anchor))]
        } else if let Some(target) = relation.target_instruction_index {
            vec![(Some(target), None)]
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
            if relation.kind == RelationType::Connected {
                external_groups[source_index] = source_group;
            }
            if let Some(source_group) = source_group
                && relation.kind == RelationType::Connected
            {
                if let Some(target_final) = target_final {
                    dependencies[count + source_group].insert(target_final);
                }
                // Existing instruction checks require the original target to
                // exist; its enclosing transform is awaited by the correction.
                if let Some(target_instruction) = target_instruction {
                    dependencies[source_index].insert(target_instruction);
                }
            } else if let Some(target_final) = target_final {
                dependencies[source_index].insert(target_final);
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
        cyclic: cyclic.into_iter().map(as_node).collect(),
        external_groups,
    }
}
