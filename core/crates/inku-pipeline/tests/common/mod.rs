//! Shared by this package's integration tests.

use std::panic;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::thread;

/// Maps every item on all cores and returns the results in the items' order.
/// An item that fails does not stop the others: each failure prints its own
/// message, and the first is raised again once every worker has finished, so
/// one run names every failing item.
pub fn par_map<T: Sync, R: Send>(items: &[T], map: impl Fn(&T) -> R + Sync) -> Vec<R> {
    let next = AtomicUsize::new(0);
    let workers = thread::available_parallelism()
        .map_or(1, usize::from)
        .min(items.len())
        .max(1);
    let mut done = Vec::with_capacity(items.len());
    let mut failure = None;
    thread::scope(|scope| {
        let workers: Vec<_> = (0..workers)
            .map(|_| {
                scope.spawn(|| {
                    let mut done = Vec::new();
                    loop {
                        let index = next.fetch_add(1, Ordering::Relaxed);
                        let Some(item) = items.get(index) else {
                            break done;
                        };
                        done.push((index, map(item)));
                    }
                })
            })
            .collect();
        for worker in workers {
            match worker.join() {
                Ok(part) => done.extend(part),
                Err(payload) => failure = failure.or(Some(payload)),
            }
        }
    });
    if let Some(payload) = failure {
        panic::resume_unwind(payload);
    }
    done.sort_unstable_by_key(|&(index, _)| index);
    done.into_iter().map(|(_, result)| result).collect()
}
