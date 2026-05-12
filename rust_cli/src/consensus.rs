use sha3::{Digest, Keccak256};
use std::collections::HashMap;

/// Proof-of-Yield consensus engine.
///
/// Validators must agree on BOTH inference hash AND yield hash.
pub struct ConsensusEngine {
    node_id: String,
    votes: HashMap<String, Vec<Vote>>, // state_root -> votes
}

struct Vote {
    inference_hash: String,
    yield_hash: String,
    confidence: f64,
}

impl ConsensusEngine {
    pub fn new(node_id: &str) -> Self {
        Self {
            node_id: node_id.to_string(),
            votes: HashMap::new(),
        }
    }

    pub fn submit_vote(&mut self, state_root: &str, inf_hash: &str, yield_hash: &str, confidence: f64) {
        let entry = self.votes.entry(state_root.to_string()).or_insert_with(Vec::new);
        entry.push(Vote {
            inference_hash: inf_hash.to_string(),
            yield_hash: yield_hash.to_string(),
            confidence,
        });
    }

    pub fn check_consensus(&self, state_root: &str) -> bool {
        let votes = match self.votes.get(state_root) {
            Some(v) if v.len() >= 3 => v,
            _ => return false,
        };

        let mut inf_counts: HashMap<&str, usize> = HashMap::new();
        let mut yield_counts: HashMap<&str, usize> = HashMap::new();

        for v in votes {
            *inf_counts.entry(&v.inference_hash).or_insert(0) += 1;
            *yield_counts.entry(&v.yield_hash).or_insert(0) += 1;
        }

        let top_inf = inf_counts.values().max().copied().unwrap_or(0);
        let top_yield = yield_counts.values().max().copied().unwrap_or(0);
        let total = votes.len();

        // Exact 2/3 on BOTH dimensions
        top_inf * 3 >= total * 2 && top_yield * 3 >= total * 2
    }

    pub fn form_batch_root(&self, batch: &[String]) -> String {
        let mut hasher = Keccak256::new();
        for op in batch {
            hasher.update(op.as_bytes());
        }
        hex::encode(hasher.finalize())
    }

    pub fn vote_count(&self, state_root: &str) -> usize {
        self.votes.get(state_root).map(|v| v.len()).unwrap_or(0)
    }
}

pub struct ProofOfYield;

impl ProofOfYield {
    pub fn compute_yield_hash(total_yield: f64) -> String {
        let mut hasher = Keccak256::new();
        hasher.update(format!("{:.6}", total_yield).as_bytes());
        hex::encode(hasher.finalize())
    }
}
