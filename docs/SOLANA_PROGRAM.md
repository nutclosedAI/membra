# MEMBRA Solana On-Chain Program

## Thesis

MEMBRA is an **on-chain proof-of-job protocol** where AI work is represented by Solana accounts, validator votes, consensus records, yield scores, and settlement receipts.

> **On-chain:** state transitions, proofs, votes, receipts, registry entries, settlement events.
> **Off-chain:** raw prompts, private files, API keys, full source code, model outputs, private customer data.
> Those off-chain items are **hashed, compressed into commitments, or stored with on-chain roots.**

## Why Hashes, Not Raw Data

Solana transactions have a **hard serialized size limit of 1,232 bytes**. Full chat logs, source trees, and model outputs do not belong directly inside transaction payloads. Solana programs are **stateless**; mutable state lives in separate data accounts passed into program instructions.

The right design:
- Store **hashes** (32 bytes each) on-chain
- Store **full data** off-chain (IPFS, Arweave, S3, local filesystem)
- Link on-chain to off-chain via **metadata URI hashes**

## Account Architecture

### Program: `membra_core`

| Account | Purpose | Key Data |
|---------|---------|----------|
| `ProtocolConfig` | Global authority, version, threshold | authority, version, consensus_threshold_bps |
| `JobAccount` | Core job record | creator, job_id_hash, chat_hash, job_spec_hash, status |
| `ArtifactManifestAccount` | Artifact registry | artifact_root (Merkle), manifest_hash, metadata_uri_hash, count |
| `ValidatorAccount` | Validator registry | authority, reputation_score, total_votes, active |
| `VoteAccount` | Individual validator vote | job, validator, vote, score, reason_hash |
| `ConsensusAccount` | Final consensus result | yes_votes, no_votes, threshold_bps, result |
| `YieldAccount` | Scored yield | artifact_yield, validation_yield, market_yield, chain_yield, total_score |
| `SettlementAccount` | External settlement proof | payer, recipient, amount_lamports, settlement_type, receipt_hash |

## Instruction Flow

```
initialize                    → ProtocolConfig (authority sets params)
  ↓
register_validator            → ValidatorAccount (authority → validator, no stake v0.1)
  ↓
create_job                    → JobAccount (hashes of chat + spec)
  ↓
submit_artifact_manifest      → ArtifactManifestAccount (Merkle root of artifacts)
  ↓
submit_validator_vote         → VoteAccount (accept/reject + score + reason hash)
  ↓
finalize_consensus            → ConsensusAccount (2/3 quorum check)
  ↓
record_yield                  → YieldAccount (4 yield types scored)
  ↓
record_settlement             → SettlementAccount (receipt hash, no custody)
  ↓
close_job                     → JobAccount.status = Closed
```

## State Machine

```
Created → ArtifactsSubmitted → VotingOpen → ConsensusAccepted → YieldRecorded → Settled → Closed
                    ↓                           ↓
              ConsensusRejected ←──────────────┘
```

## Security Model

### v0.1 (Current): No Custody

- No token custody.
- No escrow.
- No DeFi.
- No automatic payout.
- Just **state transitions** and **hash commitments**.

This is intentionally minimal to prove the protocol works before adding financial risk.

### v0.2 → v1.0 Roadmap

| Version | Feature | Risk Level |
|---------|---------|------------|
| v0.1 | Create job, submit manifest, vote, finalize, record receipt hash | None (no funds) |
| v0.2 | Add SPL payment receipt accounts | Low (no custody, just receipts) |
| v0.3 | Add bounty escrow | Medium (holds funds) |
| v0.4 | Add validator staking / reputation | Medium (slash conditions) |
| v1.0 | Full proof-of-job marketplace | High (full economic activity) |

## Account Structs

```rust
pub struct JobAccount {
    pub creator: Pubkey,
    pub job_id_hash: [u8; 32],
    pub chat_hash: [u8; 32],
    pub job_spec_hash: [u8; 32],
    pub status: u8,
    pub created_at: i64,
}

pub struct ArtifactManifestAccount {
    pub job: Pubkey,
    pub manifest_hash: [u8; 32],
    pub artifact_root: [u8; 32],
    pub metadata_uri_hash: [u8; 32],
    pub artifact_count: u32,
}

pub struct ValidatorAccount {
    pub authority: Pubkey,
    pub reputation_score: u64,
    pub total_votes: u64,
    pub accepted_votes: u64,
    pub slashed_votes: u64,
    pub active: bool,
}

pub struct VoteAccount {
    pub job: Pubkey,
    pub validator: Pubkey,
    pub vote: u8,       // 1 = accept, 0 = reject
    pub score: u16,
    pub reason_hash: [u8; 32],
}

pub struct ConsensusAccount {
    pub job: Pubkey,
    pub yes_votes: u16,
    pub no_votes: u16,
    pub threshold_bps: u16,  // 6667 = 66.67%
    pub result: u8,            // 1 = accepted, 0 = rejected
}

pub struct YieldAccount {
    pub job: Pubkey,
    pub artifact_yield: u16,
    pub validation_yield: u16,
    pub market_yield: u64,
    pub chain_yield: u64,
    pub total_score: u16,
}

pub struct SettlementAccount {
    pub job: Pubkey,
    pub payer: Pubkey,
    pub recipient: Pubkey,
    pub amount_lamports: u64,
    pub settlement_type: u8,  // 0=bounty, 1=grant, 2=invoice, 3=stripe, 4=nft
    pub receipt_hash: [u8; 32],
}
```

## Consensus Formula

```
ratio_bps = (yes_votes * 10000) / total_votes
accepted = ratio_bps >= threshold_bps  // default 6667 (66.67%)
```

No floating point. All arithmetic uses integer basis points.

## Events (for indexing)

| Event | Fields |
|-------|--------|
| `JobCreated` | job, creator, job_id_hash, chat_hash |
| `ArtifactManifestSubmitted` | job, manifest, artifact_root, artifact_count |
| `VoteSubmitted` | job, validator, vote, score |
| `ConsensusFinalized` | job, consensus, result, yes_votes, no_votes |
| `YieldRecorded` | job, yield_account, total_score |
| `SettlementRecorded` | job, settlement, settlement_type, amount_lamports |
| `JobClosed` | job, creator |
| `ValidatorRegistered` | validator, authority |

## Build & Deploy

```bash
# Build
anchor build

# Test (local validator)
anchor test

# Deploy devnet
anchor deploy --provider.cluster devnet

# Initialize protocol
npx tsx scripts/initialize.ts --cluster devnet

# Run E2E test
npx tsx scripts/test_flow.ts
```

## PDA Seeds

| PDA | Seeds |
|-----|-------|
| ProtocolConfig | `["protocol_config"]` |
| JobAccount | `["job", creator_pubkey, job_id_hash]` |
| ArtifactManifest | `["artifact_manifest", job_pubkey]` |
| ValidatorAccount | `["validator", authority_pubkey]` |
| VoteAccount | `["vote", job_pubkey, validator_pubkey]` |
| ConsensusAccount | `["consensus", job_pubkey]` |
| YieldAccount | `["yield", job_pubkey]` |
| SettlementAccount | `["settlement", job_pubkey]` |

## Key Security Rules

1. **LLMs explain and classify.** Solana programs enforce state.
2. **RPC verifies transactions.** Validators vote.
3. **Consensus finalizes.** Receipts prove settlement.
4. **No raw chat dumps on mainnet.** Hashes + commitments only.
5. **v0.1 is no-custody.** No token risk until v0.3+.

## Doctrine

> **"Don't just chat. Ship provable work."**
>
> MEMBRA turns chat into Solana state.
> Chat hash → on-chain.
> Job spec hash → on-chain.
> Artifact Merkle root → on-chain.
> Validator votes → on-chain.
> Consensus result → on-chain.
> Yield scores → on-chain.
> Settlement receipts → on-chain.
>
> Raw prompts, full code, model outputs → off-chain, committed on-chain.
>
> That is the viable version of "on-chain all."
