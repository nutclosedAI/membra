# MEMBRA SDK — Local Proof-of-Yield Validator Kit

**A MacBook becomes a validator of human-compute contribution — not by pretending files are money, but by proving work, inference, corpus analysis, and settlement receipts.**

⚠️ **WARNING:** MEMBRA does not guarantee income. It measures contribution, computes local proofs, benchmarks internal throughput, and anchors receipts. Any yield claim requires external protocol receipts, realized settlement, and legal/compliance review.

> **📋 HONEST STATUS:** See `docs/STATUS.md` for exactly what is real, what is simulated, and what needs building before real money moves.

## What This Is

MEMBRA SDK is a **local validator toolkit** that converts Mac compute, file-corpus analysis, LLM inference, and proof-of-yield records into verifiable network contributions, with optional testnet settlement and DeFi strategy simulation under explicit policy controls.

**The doctrine:**
- Human intent enters chat.
- LLM structures the intent.
- Terminal executes the plan.
- Code, documents, contracts, dashboards, agents, tests, and proofs are generated.
- Each artifact is hashed.
- Each build step is logged.
- Each successful output becomes a proof-of-build record.
- Only verified outputs can be counted as system yield.

**Important boundary:**
| Not Yield | Can Become Yield |
|-----------|-----------------|
| LLM text | LLM-built systems with tests |
| File scan | Verified build artifact with receipt |
| Strategy idea | Backtest with confirmed metrics |
| Prompt | Deployment with explorer hash |

## What This Is NOT

| Incorrect Claim | Truth |
|-----------------|-------|
| "Guarantee $100/day from MacBook" | $100/day is a target scenario, not a guarantee. |
| "1M TPS on Solana" | Internal ledger: 1M+ ops/sec. Solana settlement: constrained by Solana devnet. |
| "Autonomous DeFi yield extraction" | DeFi operator is policy-gated, disabled by default, testnet-first. |
| "LLM consensus creates money" | LLM consensus creates proof records. Money requires external settlement. |
| "Outperform Anchor/Solana" | This is a local validator kit, not a Solana competitor. |
| "Real liquidity pools" | No AMM pools deployed. Simulation only until policy-gated testnet execution. |

## Architecture

```
Human Intent
    ↓
LLM Structures → Build Plan
    ↓
Terminal Executes → Artifacts Generated
    ↓
┌─────────────────────────────────────────────────────────────┐
│  MEMBRA SDK on M5 Pro Mac                                   │
│  ┌─────────────┐ ┌──────────────┐ ┌─────────────────┐   │
│  │ File Corpus │ │ LLM Validator│ │ Build Tracker   │   │
│  │  Miner      │ │ (inference)  │ │ (artifacts)     │   │
│  └──────┬──────┘ └───────┬──────┘ └────────┬────────┘   │
│         │                │                   │            │
│         └────────────────┼───────────────────┘            │
│                          │                                │
│                   ┌──────┴──────┐                         │
│                   │  PoY         │  ← 2/3 on inference + yield│
│                   │  Consensus   │                         │
│                   └──────┬──────┘                         │
│                          │                                │
│                   ┌──────┴──────┐                         │
│                   │  Internal    │  ← 1M+ ops/sec local    │
│                   │  Ledger      │                         │
│                   └──────┬──────┘                         │
│                          │                                │
│                   ┌──────┴──────┐                         │
│                   │  Solana      │  ← devnet anchor        │
│                   │  Anchor      │  (memo tx with root)    │
│                   └─────────────┘                           │
│                          │                                │
│  ┌───────────────────────┴───────────────────┐             │
│  │  Policy-Gated DeFi Operator (opt-in)   │             │
│  │  Disabled by default. Testnet-only.    │             │
│  └─────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

## Verified Evidence

| Component | Status | Evidence |
|-----------|--------|----------|
| 3-Agent Proof-of-Yield Consensus | ✅ | `test_3_agent_consensus.py` — 2/3 hash agreement finalizes batch |
| C++ Hot Path | ✅ | Compiles with g++, batch finalization <1ms |
| Python SDK | ✅ | `py_compile` passes all modules |
| Rust CLI | ✅ | `cargo build --release` succeeds, benchmarks run |
| Rust Benchmark | ✅ | 13.3M ops/sec on 100K batch (lock-free SegQueue) |
| Solana Devnet Anchor | ⚠️ | Wallet created, needs devnet SOL for real tx |
| DeFi Operator | ⚠️ | Architecture only. Disabled by default. No real positions. |

## Quick Start

### Install Python SDK

```bash
cd membra-sdk
pip install -e ".[dev]"
```

### CLI Commands

```bash
# Start validator node
membra start --autonomous

# Benchmark internal ledger
membra benchmark --ops 1000000

# Mine files for corpus analysis
membra mine-files ~/Documents

# Validate a prompt (LLM inference → hash)
membra validate-prompt "Analyze this smart contract"

# Anchor finalized root to Solana devnet
membra anchor --memo "batch-root-0xabc..."

# Show status
membra status
```

### Rust CLI (M5 Pro Optimized)

```bash
cd rust_cli
cargo build --release

# Benchmark
./target/release/membra benchmark --ops 1000000

# Consensus demo
./target/release/membra consensus
```

## Benchmarks

| Metric | Value | Context |
|--------|-------|---------|
| Internal ledger submit | ~16.7M ops/sec | Lock-free SegQueue, single-thread |
| Internal ledger drain | ~66M ops/sec | amortized batch drain |
| **Total internal throughput** | **~13.3M ops/sec** | Mac M5 Pro, release build |
| Consensus finality | ~100ms | LLM inference latency (Groq/Ollama) |
| Solana devnet settlement | ~2s | Constrained by Solana block time |

**Critical distinction:** Internal ledger throughput measures local operation buffering. Solana settlement throughput is capped by Solana's own limits. These are separate metrics.

See `docs/BENCHMARKS.md` for methodology.

## Proof-of-Yield Doctrine

Proof-of-Yield is NOT "files = money." It is:

> A cryptographic attestation that validators agree on the economic value of a batch of verified work, where value is derived from build artifacts, test results, and external receipts — not from the existence of files alone.

Read `docs/PROOF_OF_YIELD.md` for the full doctrine.

## Security

- **Never commit `.env` files.** Use macOS Keychain or 1Password.
- **Never store seed phrases in code.** Wallet JSON files are `.gitignore`d.
- **DeFi execution is policy-gated.** Disabled by default. Requires explicit `--enable-defi` flag and testnet-only mode.
- See `docs/SECURITY.md` for full key handling rules.

## Project Structure

```
membra-sdk/
├── membra_sdk/
│   ├── core/
│   │   ├── node.py          # Validator orchestrator
│   │   ├── ledger.py        # High-throughput internal ledger
│   │   ├── yield_engine.py  # File corpus analysis
│   │   └── artifacts.py     # Build artifact tracker
│   ├── consensus/
│   │   └── poy.py           # Proof-of-Yield consensus
│   ├── defi/
│   │   └── operator.py      # Policy-gated DeFi (disabled by default)
│   └── cli/
│       └── main.py          # Typer CLI
├── rust_cli/
│   ├── src/
│   │   ├── main.rs          # CLI entry
│   │   ├── ledger.rs        # Lock-free ledger (SegQueue)
│   │   └── consensus.rs     # Rust PoY consensus
│   └── Cargo.toml
├── tests/
│   ├── test_consensus.py    # 3-agent consensus
│   └── test_artifacts.py    # Build artifact tracking
├── examples/
│   ├── 3_agent_demo.py      # Multi-agent consensus
│   ├── mine_files.py        # File corpus mining
│   └── validate_prompt.py   # LLM validation
├── docs/
│   ├── PROOF_OF_YIELD.md    # Yield doctrine
│   ├── BENCHMARKS.md        # Benchmark methodology
│   └── SECURITY.md          # Key handling & policies
├── pyproject.toml
└── README.md
```

## Next Milestone

1. Run 3 `membra start` agents on same LAN
2. Each agent processes same file batch
3. P2P gossip shares inference + yield hashes
4. 2/3 agreement → batch finalizes locally
5. Anchor finalized root to Solana devnet (requires devnet SOL)
6. Display Solana explorer receipt

## License

MIT — Local validator toolkit. No guaranteed income. See SECURITY.md before handling keys.
