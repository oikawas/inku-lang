//! Pure count resolution for a coordinated group; it never allocates instances.

const GROUP_TOTAL_DEFAULT: u64 = 8;

/// Resolves the symbolic count for every source-ordered member of one coordinated group.
///
/// `place` and `line_up` give each omitted member one object. `scatter` and `tile`
/// share their omitted total evenly in source order. Mixed explicit and omitted
/// `scatter`/`tile` groups deliberately remain unresolved until their policy is chosen.
pub(crate) fn coordinated_counts(action: &str, counts: &[Option<u64>]) -> Option<Vec<u64>> {
    if counts.is_empty() {
        return None;
    }
    match action {
        "place" | "line_up" => Some(counts.iter().map(|count| count.unwrap_or(1)).collect()),
        "scatter" | "tile" => {
            if counts.iter().all(Option::is_some) {
                return Some(counts.iter().map(|count| count.unwrap()).collect());
            }
            if counts.iter().any(Option::is_some) || counts.len() > GROUP_TOTAL_DEFAULT as usize {
                return None;
            }
            let member_count = counts.len() as u64;
            let base = GROUP_TOTAL_DEFAULT / member_count;
            let remainder = GROUP_TOTAL_DEFAULT % member_count;
            Some(
                (0..member_count)
                    .map(|index| base + u64::from(index < remainder))
                    .collect(),
            )
        }
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::coordinated_counts;

    #[test]
    fn coordinated_counts_resolve_the_adopted_group_rules() {
        assert_eq!(
            coordinated_counts("place", &[None, Some(2), None]),
            Some(vec![1, 2, 1])
        );
        assert_eq!(
            coordinated_counts("line_up", &[None, None]),
            Some(vec![1, 1])
        );
        assert_eq!(
            coordinated_counts("scatter", &[None, None]),
            Some(vec![4, 4])
        );
        assert_eq!(
            coordinated_counts("tile", &[None, None, None]),
            Some(vec![3, 3, 2])
        );
        assert_eq!(
            coordinated_counts("scatter", &[Some(2), Some(9)]),
            Some(vec![2, 9])
        );
    }

    #[test]
    fn coordinated_counts_reject_unresolved_groups_but_preserve_explicit_values() {
        assert_eq!(coordinated_counts("scatter", &[Some(2), None]), None);
        assert_eq!(coordinated_counts("tile", &[None; 9]), None);
        assert_eq!(
            coordinated_counts("scatter", &[Some(0), Some(u64::from(u32::MAX) + 1)]),
            Some(vec![0, u64::from(u32::MAX) + 1])
        );
    }
}
