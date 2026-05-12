# Benchmark Methodology

## Critical Distinction

**Internal Ledger Ops/sec ≠ Solana TPS**

These are separate metrics with different constraints:

| Metric | What it measures | Limiting factor |
|--------|-----------------|-------------------|
| Internal ledger ops/sec | How fast the local buffer accepts operations | CPU, memory bandwidth |
| Solana settlement TPS | How fast batches anchor to Solana | Solana network capacity |

## Internal Ledger Benchmark

### Methodology

```rust
let ledger = InternalLedger::new();
let start = Instant::now();

// Phase 1: Submit 100,000 string ops
for i in 0..100_000 {
    ledger.submit_string(&format!("op-{}", i));
}
let submit_time = start.elapsed();

// Phase 2: Drain all ops into batches
let drain_start = Instant::now();
loop {
    let batch = ledger.drain_batch(10_000);
    if batch.is_empty() { break; }
}
let drain_time = drain_start.elapsed();
```

### Results (Apple M5 Pro, Release Build)

| Operation | Time | Throughput |
|-----------|------|------------|
| Submit 100K ops | 5.97ms | **16.7M ops/sec** |
| Drain 100K ops | 1.51ms | **66.1M ops/sec** |
| Total (submit + drain) | 7.48ms | **13.3M ops/sec** |

### What This Means

- The ledger can accept 16.7M operations per second into a lock-free queue.
- It can drain 66M operations per second into batches.
- The bottleneck is batch formation and consensus, not the queue itself.
- **These are local buffer metrics, not blockchain TPS.**

## Solana Settlement Benchmark

### Methodology

1. Form a batch of 100-1000 operations
2. Compute Keccak256 root hash
3. Submit memo transaction to Solana devnet
4. Measure time from batch formation to on-chain confirmation

### Expected Results

| Step | Time | Notes |
|------|------|-------|
| Batch formation | <1ms | Local computation |
| RPC request | 50-200ms | Network latency |
| Block inclusion | 400-800ms | Solana block time |
| Confirmation | 2-4s | Devnet finality |
| **Total settlement** | **~2-4s** | **Constrained by Solana** |

### Honest Claim

> "Internal ledger buffers 1M+ ops/sec. Solana settlement is ~2s per batch."

NOT: "MEMBRA does 1M TPS on Solana."

## Consensus Benchmark

### Methodology

1. 3 agents receive same batch
2. Each runs LLM inference (or deterministic fallback)
3. Hash inference output + yield estimate
4. Gossip votes via local network
5. Measure time to 2/3 agreement

### Results

| Scenario | Time | Notes |
|----------|------|-------|
| Deterministic fallback | <1ms | No network call |
| Local Ollama (7B) | 500ms-2s | Model-dependent |
| Groq API (70B) | 100-500ms | API latency |
| Network gossip (local) | 10-50ms | TCP/WS overhead |

## Reproducing Benchmarks

### Rust CLI

```bash
cd rust_cli
cargo build --release

# Internal ledger
./target/release/membra benchmark --ops 100000

# With different batch sizes
./target/release/membra benchmark --ops 1000000
```

### Python SDK

```bash
cd membra-sdk
python3 -m membra_sdk.benchmark --ops 100000
```

## Hardware Notes

All benchmarks run on Apple M5 Pro (2026) with:
- 16-core CPU
- 32GB unified memory
- macOS 15.x
- Rust 1.95.0
- Python 3.12

Results will vary on different hardware. The Rust CLI uses `crossbeam::queue::SegQueue` which is architecture-agnostic but benefits from Apple Silicon's memory bandwidth.

## Reporting Benchmarks

When sharing benchmarks, always include:
1. Hardware spec
2. Software versions
3. Exact command run
4. Whether metric is internal ops or chain settlement
5. Number of samples and variance
