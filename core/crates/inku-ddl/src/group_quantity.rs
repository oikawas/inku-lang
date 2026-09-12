//! Pure count resolution for a coordinated group; it never allocates instances.

const GROUP_TOTAL_DEFAULT: u64 = 8;

/// Resolves the symbolic count for every source-ordered member of one coordinated group.
///
/// `place` and `line_up` give each omitted member one object. `scatter` and `tile`
/// preserve explicit counts, then use their total of eight for omitted members when
/// possible. Every omitted member receives at least one object; any remainder is
/// allocated in source order. This works for all-omitted and mixed groups alike.
pub(crate) fn coordinated_counts(action: &str, counts: &[Option<u64>]) -> Option<Vec<u64>> {
    if counts.is_empty() {
        return None;
    }
    match action {
        "place" | "line_up" => Some(counts.iter().map(|count| count.unwrap_or(1)).collect()),
        "scatter" | "tile" => {
            let omitted_count = counts.iter().filter(|count| count.is_none()).count() as u64;
            if omitted_count == 0 {
                return Some(counts.iter().map(|count| count.unwrap()).collect());
            }
            let remaining_after_explicit = counts.iter().fold(GROUP_TOTAL_DEFAULT, |remaining, count| {
                count.map_or(remaining, |explicit| remaining.saturating_sub(explicit))
            });
            let distributable = remaining_after_explicit.saturating_sub(omitted_count);
            let base = distributable / omitted_count;
            let remainder = distributable % omitted_count;
            let mut omitted_index = 0;
            Some(
                counts
                    .iter()
                    .map(|count| match count {
                        Some(explicit) => *explicit,
                        None => {
                            let resolved = 1 + base + u64::from(omitted_index < remainder);
                            omitted_index += 1;
                            resolved
                        }
                    })
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
    fn coordinated_counts_preserve_explicit_values_and_allocate_omissions() {
        assert_eq!(
            coordinated_counts("scatter", &[Some(3), None]),
            Some(vec![3, 5])
        );
        assert_eq!(coordinated_counts("tile", &[None; 9]), Some(vec![1; 9]));
        assert_eq!(
            coordinated_counts("scatter", &[Some(u64::MAX), None]),
            Some(vec![u64::MAX, 1])
        );
        assert_eq!(
            coordinated_counts("scatter", &[Some(0), Some(u64::from(u32::MAX) + 1)]),
            Some(vec![0, u64::from(u32::MAX) + 1])
        );
    }
}
