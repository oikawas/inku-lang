//! The forest-based transform-group validation must decide exactly what the
//! group-by-group rule decides, including which conflict it reports first.

use std::collections::HashSet;

use inku_score::{Score, TransformGroup, transform_group_contains};

/// The group-by-group rule that validation used before it kept a forest.
fn pairwise(score: &Score) -> Result<(), &'static str> {
    score.validate_placement_groups()?;
    if score.transform_groups.is_empty() {
        return Ok(());
    }
    let version = score.version.as_str();
    if !matches!(version, "0.4.0" | "0.5.0" | "0.6.0" | "0.9.0") {
        return Err("transform_groups requires Score version 0.4.0");
    }
    for (group_index, group) in score.transform_groups.iter().enumerate() {
        if group.start > group.end || (group.start == group.end && group.anchor_indices.is_empty())
        {
            return Err("transform group range must be nonempty unless it owns anchors");
        }
        if group.end > score.instructions.len() {
            return Err("transform group range exceeds the instruction list");
        }
        if !group.rotation_degrees.is_finite() {
            return Err("transform group rotation_degrees must be finite");
        }
        if !group.scale_x.is_finite() || !group.scale_y.is_finite() {
            return Err("transform group scale must be finite");
        }
        if !group.translate_x.is_finite() || !group.translate_y.is_finite() {
            return Err("transform group translation must be finite");
        }
        if version == "0.4.0"
            && (group.scale_x != 1.0
                || group.scale_y != 1.0
                || group.translate_x != 0.0
                || group.translate_y != 0.0)
        {
            return Err("scale or translation requires Score version 0.5.0");
        }
        if score.instructions[group.start..group.end]
            .iter()
            .any(|instruction| {
                instruction
                    .arrangement
                    .as_ref()
                    .is_some_and(|arrangement| arrangement.resolved.is_none())
            })
        {
            return Err("transform group members cannot carry arrangements");
        }
        let mut fixed_indices = HashSet::new();
        for &fixed_index in &group.fixed_position_indices {
            if fixed_index < group.start || fixed_index >= group.end {
                return Err("transform group fixed_position_indices must be within its range");
            }
            if !fixed_indices.insert(fixed_index) {
                return Err("transform group fixed_position_indices must be unique");
            }
        }
        let mut anchor_indices = HashSet::new();
        for &anchor_index in &group.anchor_indices {
            if anchor_index >= score.anchors.len() {
                return Err("transform group anchor_indices exceeds anchors");
            }
            if !anchor_indices.insert(anchor_index) {
                return Err("transform group anchor_indices must be unique");
            }
        }
        if !group.anchor_indices.is_empty() && matches!(version, "0.4.0" | "0.5.0") {
            return Err("transform group anchor_indices requires Score version 0.6.0");
        }
        for prior in &score.transform_groups[..group_index] {
            let current_contains_prior = transform_group_contains(group, prior);
            let prior_contains_current = transform_group_contains(prior, group);
            let anchor_overlap = prior
                .anchor_indices
                .iter()
                .any(|index| anchor_indices.contains(index));
            let drawable_overlap = group.start < group.end
                && prior.start < prior.end
                && group.start < prior.end
                && prior.start < group.end;
            if !drawable_overlap && !anchor_overlap {
                continue;
            }
            if !current_contains_prior {
                if prior_contains_current {
                    return Err("transform groups must be stored inner-before-outer");
                }
                return Err("transform group ranges cannot cross");
            }
            if !prior
                .fixed_position_indices
                .iter()
                .all(|index| fixed_indices.contains(index))
            {
                return Err(
                    "outer transform groups must include descendant fixed_position_indices",
                );
            }
            if !prior
                .anchor_indices
                .iter()
                .all(|index| anchor_indices.contains(index))
            {
                return Err("outer transform groups must include descendant anchor_indices");
            }
        }
    }
    Ok(())
}

struct Random(u64);

impl Random {
    fn next(&mut self) -> u64 {
        // xorshift64*
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }

    fn below(&mut self, bound: u64) -> usize {
        usize::try_from(self.next() % bound).expect("small bound")
    }

    fn chance(&mut self, numerator: u64, denominator: u64) -> bool {
        self.next() % denominator < numerator
    }
}

fn indices(random: &mut Random, count: usize, bound: usize) -> Vec<usize> {
    (0..count).map(|_| random.below(bound as u64 + 1)).collect()
}

fn random_score(random: &mut Random, base: &Score) -> Score {
    let mut score = base.clone();
    score.version =
        ["0.9.0", "0.9.0", "0.9.0", "0.6.0", "0.5.0", "0.4.0"][random.below(6)].to_owned();
    let instruction_count = random.below(7);
    score.instructions = (0..instruction_count)
        .map(|_| {
            let mut instruction = base.instructions[0].clone();
            if random.chance(1, 12) {
                instruction.arrangement = base.instructions[1].arrangement.clone();
            }
            instruction
        })
        .collect();
    let anchor_count = random.below(5);
    score.anchors = (0..anchor_count).map(|_| base.anchors[0].clone()).collect();
    let group_count = random.below(8);
    // Build mostly nested intervals stored inner before outer, then disturb them.
    let mut groups = Vec::new();
    for _ in 0..group_count {
        let (start, end) = if !groups.is_empty() && random.chance(1, 2) {
            let inner: &TransformGroup = &groups[random.below(groups.len() as u64)];
            let start = inner.start.saturating_sub(random.below(2));
            (start, (inner.end + random.below(2)).max(start))
        } else {
            let start = random.below(instruction_count as u64 + 1);
            (start, start + random.below(3))
        };
        let (start, end) = if random.chance(1, 20) {
            (end, start)
        } else {
            (start, end)
        };
        let anchor_count_in_group = random.below(3);
        let mut anchor_indices = indices(random, anchor_count_in_group, anchor_count);
        if random.chance(1, 2) && !groups.is_empty() {
            let inner: &TransformGroup = &groups[random.below(groups.len() as u64)];
            anchor_indices.extend(inner.anchor_indices.iter().copied());
        }
        let mut seen = HashSet::new();
        if !random.chance(1, 15) {
            anchor_indices.retain(|index| *index < anchor_count && seen.insert(*index));
        }
        let mut fixed_position_indices = if end > start && random.chance(1, 4) {
            vec![start + random.below((end - start) as u64)]
        } else {
            Vec::new()
        };
        if random.chance(1, 2) && !groups.is_empty() {
            let inner: &TransformGroup = &groups[random.below(groups.len() as u64)];
            fixed_position_indices.extend(inner.fixed_position_indices.iter().copied());
        }
        let mut seen = HashSet::new();
        if !random.chance(1, 15) {
            fixed_position_indices
                .retain(|index| (start..end).contains(index) && seen.insert(*index));
        }
        groups.push(TransformGroup {
            start,
            end,
            rotation_degrees: 0.0,
            scale_x: if random.chance(1, 10) { 2.0 } else { 1.0 },
            scale_y: 1.0,
            translate_x: 0.0,
            translate_y: 0.0,
            fixed_position_indices,
            anchor_indices,
        });
    }
    if groups.len() > 1 && random.chance(1, 6) {
        let (left, right) = (
            random.below(groups.len() as u64),
            random.below(groups.len() as u64),
        );
        groups.swap(left, right);
    }
    score.transform_groups = groups;
    score
}

#[test]
fn forest_validation_matches_the_group_by_group_rule() {
    let base: Score = serde_json::from_str(
        r#"{"version":"0.9.0","instructions":[
            {"primitive":"point","center":[0.5,0.5],"radius":0.01},
            {"primitive":"point","center":[0.5,0.5],"radius":0.01,"arrangement":{"count":2}}],
          "anchors":[{"position":[0.5,0.5]}]}"#,
    )
    .expect("base Score");
    let mut random = Random(0x9E37_79B9_7F4A_7C15);
    let mut outcomes = std::collections::BTreeMap::<&str, usize>::new();
    for case in 0..200_000 {
        let score = random_score(&mut random, &base);
        let expected = pairwise(&score);
        assert_eq!(
            score.validate_transform_groups(),
            expected,
            "case {case}: {score:?}"
        );
        *outcomes.entry(expected.err().unwrap_or("ok")).or_default() += 1;
    }
    // The generator reaches valid forests and every pairwise conflict.
    for outcome in [
        "ok",
        "transform groups must be stored inner-before-outer",
        "transform group ranges cannot cross",
        "outer transform groups must include descendant fixed_position_indices",
    ] {
        assert!(
            outcomes.get(outcome).copied().unwrap_or(0) > 100,
            "{outcome}: {outcomes:?}"
        );
    }
}
