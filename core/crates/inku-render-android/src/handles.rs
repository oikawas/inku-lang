//! Integer handles own Arc references. Calls clone under the table lock and use
//! the clone outside it; removing a handle rejects new calls but keeps old calls
//! alive. No address or JNI environment is stored in the table.

use std::collections::HashMap;
use std::sync::Arc;

pub(crate) struct Handles<T> {
    next: i64,
    entries: HashMap<i64, Arc<T>>,
}

impl<T> Default for Handles<T> {
    fn default() -> Self {
        Self {
            next: 1,
            entries: HashMap::new(),
        }
    }
}

impl<T> Handles<T> {
    pub(crate) fn insert(&mut self, value: T) -> Result<i64, &'static str> {
        let id = self.next;
        let next = id.checked_add(1).ok_or("handle_id_exhausted")?;
        self.entries
            .try_reserve(1)
            .map_err(|_| "allocation_failed")?;
        self.entries.insert(id, Arc::new(value));
        self.next = next;
        Ok(id)
    }

    pub(crate) fn get(&self, id: i64) -> Option<Arc<T>> {
        self.entries.get(&id).cloned()
    }

    pub(crate) fn remove(&mut self, id: i64) -> bool {
        self.entries.remove(&id).is_some()
    }

    pub(crate) fn len(&self) -> usize {
        self.entries.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Close racing with an already-acquired call must retain that call's object,
    // refuse new calls, and release the last allocation when the call ends.
    #[test]
    fn display_handle_close_keeps_only_the_call_in_flight() {
        let mut table = Handles::default();
        let id = table.insert(String::from("scene")).unwrap();
        let in_flight = table.get(id).unwrap();
        let weak = Arc::downgrade(&in_flight);
        assert!(table.remove(id));
        assert!(table.get(id).is_none());
        assert_eq!(table.len(), 0);
        let worker = std::thread::spawn(move || {
            assert_eq!(in_flight.as_str(), "scene");
        });
        worker.join().unwrap();
        assert!(weak.upgrade().is_none());
        assert!(table.insert(String::from("next")).unwrap() > id);
    }
}
