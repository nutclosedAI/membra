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

### Proof-of-Job Runtime

```
User chat prompt
   ↓
Intent Parser (Chat Compiler)
   ↓
Job Spec — structured executable unit
   ↓
Container Plan — runtime, model, tools, policy
   ↓
Execution Sandbox — Docker / local / dry-run
   ↓
Artifacts + Logs + Tests
   ↓
Yield Meter — 4 yield types scored
   ↓
Validator Consensus — 2/3 majority required
   ↓
Proof Bundle — root hash, portable, verifiable
   ↓
Settlement Adapter — invoice, bounty, grant, NFT, anchor
```

### Protocol Stack

| Layer | Name | Purpose |
|-------|------|---------|
| 5 | Settlement | Payments, bounties, grants, NFTs, devnet receipts |
| 4 | Consensus | Validator votes, quorum, rejection reasons |
| 3 | Yield | Artifact score, test score, benchmark score |
| 2 | Job | Container plan, model backend, tools, policy |
| 1 | Chat | Human intent, prompt chain, task context |

### Legacy Architecture (Still Active)

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

### Proof-of-Job CLI

```bash
# Turn chat into a structured job spec
membra chat "Build a Python FastAPI app for my proof runtime"

# Create job from latest chat
membra job create --from-chat latest

# Run job (dry run / local execution)
membra job run --job-id job_0001 --container python:3.11-slim

# Score yield
membra yield score --job-id job_0001 --tests-passed 18 --tests-total 18

# Run consensus validation
membra consensus validate --job-id job_0001 --validators 3

# Export proof bundle
membra proof export --job-id job_0001 --format zip

# Preview settlement options
membra settle preview --job-id job_0001
```

### Legacy CLI Commands

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

# Distributed Brain Server (M5 + M1 LAN)
membra brain start --host 0.0.0.0 --port 7777
membra worker start --brain http://M5_IP:7777 --worker-id m1 --role reviewer
membra job submit --brain http://127.0.0.1:7777 --type code-review "Review this repo"
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

## Solana On-Chain Program

MEMBRA is an **on-chain proof-of-job protocol** on Solana.

> **On-chain:** state transitions, hashes, votes, receipts, yield scores, consensus results.
> **Off-chain:** raw prompts, full source code, model outputs, private data.
> Off-chain data is **hashed and committed** on-chain via Merkle roots and metadata URI hashes.

### Why Hashes, Not Raw Data

Solana transactions have a **hard limit of 1,232 bytes**. Programs are stateless; mutable data lives in separate accounts. Full chat logs and source trees do not belong in transactions.

The design stores **32-byte hashes** on-chain and **full data** off-chain (IPFS, Arweave, S3).

### Program: `membra_core` (Anchor v0.30.1)

| Account | Stores |
|---------|--------|
| `ProtocolConfig` | Authority, version, consensus threshold (66.67%) |
| `JobAccount` | Creator, job_id_hash, chat_hash, job_spec_hash, status |
| `ArtifactManifestAccount` | Artifact Merkle root, manifest hash, metadata URI hash |
| `ValidatorAccount` | Authority, reputation, vote counts, active flag |
| `VoteAccount` | Job, validator, accept/reject, score, reason_hash |
| `ConsensusAccount` | yes_votes, no_votes, threshold_bps, result |
| `YieldAccount` | artifact_yield, validation_yield, market_yield, chain_yield, total_score |
| `SettlementAccount` | payer, recipient, amount_lamports, settlement_type, receipt_hash |

### Instruction Flow

```
initialize → create_job → submit_artifact_manifest → submit_validator_vote →
finalize_consensus → record_yield → record_settlement → close_job
```

### Build & Deploy

```bash
cd membra-sdk/programs/membra_core
anchor build
anchor deploy --provider.cluster devnet
npx tsx scripts/initialize.ts --cluster devnet
npx tsx scripts/test_flow.ts
```

### Security Model

**v0.1 (Current): No Custody**
- No token custody. No escrow. No DeFi. No automatic payout.
- Just state transitions and hash commitments.

**Roadmap:**
| Version | Feature |
|---------|---------|
| v0.1 | State transitions + hash commitments |
| v0.2 | SPL payment receipt accounts |
| v0.3 | Bounty escrow |
| v0.4 | Validator staking / reputation |
| v1.0 | Full proof-of-job marketplace |

Read `docs/SOLANA_PROGRAM.md` for full architecture.

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
│   ├── job/                     # Proof-of-Job Runtime (NEW)
│   │   ├── chat_compiler.py   # Chat → JobSpec
│   │   ├── job_spec.py        # Structured executable unit
│   │   ├── artifact_hasher.py # SHA-256 for all outputs
│   │   ├── yield_meter.py     # 4 yield types scored
│   │   ├── validators.py      # Multi-role validation
│   │   ├── consensus.py       # Quorum evaluation
│   │   ├── proof_bundle.py    # Portable proof export
│   │   └── settlement.py      # External receipt adapter
│   ├── brain/                   # MoA Brain (Router/Judge/Synthesizer)
│   │   ├── router.py
│   │   ├── judge.py
│   │   ├── synthesizer.py
│   │   └── moa_orchestrator.py
│   ├── rivl/                    # RIVL — Reinforcement Inverted Validator Learning
│   │   ├── reward_engine.py   # +reward / -punishment scoring
│   │   ├── punishment_memory.py # Retrieve past failures
│   │   ├── verifier_stack.py  # Deterministic checks
│   │   └── rivl_brain.py      # Full RIVL-MoA integration
│   ├── brain_server/            # Distributed brain server
│   │   └── server.py          # Flask REST API for LAN workers
│   ├── worker/                  # Distributed worker client
│   │   └── worker_client.py   # Poll brain, execute tasks
│   ├── core/
│   │   ├── node.py            # Validator orchestrator
│   │   ├── ledger.py          # High-throughput internal ledger
│   │   ├── yield_engine.py    # File corpus analysis
│   │   └── artifacts.py       # Build artifact tracker
│   ├── consensus/
│   │   └── poy.py             # Proof-of-Yield consensus
│   ├── defi/
│   │   └── operator.py        # Policy-gated DeFi (disabled by default)
│   └── cli/
│       └── main.py            # Typer CLI
├── rust_cli/
│   ├── src/
│   │   ├── main.rs            # CLI entry
│   │   ├── ledger.rs          # Lock-free ledger (SegQueue)
│   │   └── consensus.rs       # Rust PoY consensus
│   └── Cargo.toml
├── tests/
│   ├── test_consensus.py      # 3-agent consensus
│   └── test_artifacts.py      # Build artifact tracking
├── examples/
│   ├── 3_agent_demo.py        # Multi-agent consensus
│   ├── mine_files.py          # File corpus mining
│   ├── validate_prompt.py     # LLM validation
│   ├── moa_brain_demo.py      # MoA Brain demo
│   ├── rivl_demo.py           # RIVL reward/punishment demo
│   └── lan_two_mac_test.py    # M5 + M1 LAN test
├── docs/
│   ├── PROOF_OF_JOB.md        # Proof-of-Job architecture (NEW)
│   ├── YIELD_DEFINITIONS.md   # Legal yield definitions (NEW)
│   ├── MOA_BRAIN.md           # Mixture-of-Agents brain
│   ├── RIVL.md                # Reinforcement Inverted Validator Learning
│   ├── LAN_TEST.md            # Two-Mac LAN test guide
│   ├── PROOF_OF_YIELD.md      # Yield doctrine
│   ├── BENCHMARKS.md          # Benchmark methodology
│   └── SECURITY.md            # Key handling & policies
├── app.py                       # Hugging Face 6-tab Gradio demo
├── pyproject.toml
└── README.md
```

## Next Milestone

### Proof-of-Job Pipeline (M5 Pro)
1. `membra chat "Build a proof-of-job demo app"` → job spec created
2. `membra job run --job-id <id>` → local execution with Ollama
3. `membra yield score --job-id <id>` → artifacts + tests scored
4. `membra consensus validate --job-id <id>` → validators vote 2/3
5. `membra proof export --job-id <id>` → proof bundle with root hash
6. `membra settle preview --job-id <id>` → invoice, bounty, or anchor options

### Distributed Test (M5 Pro + M1 Pro LAN)
1. M5 Pro: `membra brain start --host 0.0.0.0 --port 7777`
2. M5 Pro: `membra worker start --brain http://127.0.0.1:7777 --role coder`
3. M1 Pro: `membra worker start --brain http://M5_IP:7777 --role reviewer`
4. Submit job: `membra job submit --prompt "Review this repo"`
5. Verify: both workers execute, results merge, artifact hash created

### Solana Settlement
1. Anchor proof root to Solana devnet (requires devnet SOL)
2. Display Solana explorer receipt
3. Verify on-chain proof of job completion

## License

MIT — Local validator toolkit. No guaranteed income. See SECURITY.md before handling keys.
