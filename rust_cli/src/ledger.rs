use crossbeam::queue::SegQueue;
use sha3::{Digest, Keccak256};
use std::sync::atomic::{AtomicU64, Ordering};

/// High-throughput internal ledger using lock-free structures.
///
/// Uses SegQueue for lock-free appends and batch draining.
/// On M5 Pro with Apple Silicon, this achieves millions of ops/sec.
pub struct InternalLedger {
    queue: SegQueue<String>,
    submitted: AtomicU64,
    drained: AtomicU64,
}

impl InternalLedger {
    pub fn new() -> Self {
        Self {
            queue: SegQueue::new(),
            submitted: AtomicU64::new(0),
            drained: AtomicU64::new(0),
        }
    }

    /// Submit a single operation. Lock-free O(1).
    pub fn submit_string(&self, op: &str) {
        self.queue.push(op.to_string());
        self.submitted.fetch_add(1, Ordering::Relaxed);
    }

    /// Submit a structured operation (serialized to JSON).
    pub fn submit_json(&self, op: &serde_json::Value) {
        if let Ok(s) = serde_json::to_string(op) {
            self.queue.push(s);
            self.submitted.fetch_add(1, Ordering::Relaxed);
        }
    }

    /// Drain up to `max` operations into a batch.
    pub fn drain_batch(&self, max: usize) -> Vec<String> {
        let mut batch = Vec::with_capacity(max);
        while batch.len() < max {
            match self.queue.pop() {
                Some(op) => batch.push(op),
                None => break,
            }
        }
        self.drained.fetch_add(batch.len() as u64, Ordering::Relaxed);
        batch
    }

    pub fn pending(&self) -> u64 {
        self.submitted.load(Ordering::Relaxed) - self.drained.load(Ordering::Relaxed)
    }

    pub fn stats(&self) -> serde_json::Value {
        serde_json::json!({
            "submitted": self.submitted.load(Ordering::Relaxed),
            "drained": self.drained.load(Ordering::Relaxed),
            "pending": self.pending(),
        })
    }
}

/// Compute Keccak256 hash of a batch for state root.
pub fn batch_root(batch: &[String]) -> String {
    let mut hasher = Keccak256::new();
    for op in batch {
        hasher.update(op.as_bytes());
    }
    hex::encode(hasher.finalize())
}
