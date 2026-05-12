# MEMBRA Profit Loop

## The Formula

```
Yield = verified external revenue − costs − risk reserve
```

NOT:
```
"LLM generated text, therefore money."
```

BUT:
```
"LLM generated a deployable artifact, someone paid for it, payment settled,
validators confirmed the proof, therefore yield exists."
```

## The Five Revenue Sources

### 1. Build Bounty Marketplace

Users post tasks: apps, dashboards, bots, contracts, research, automation.
MEMBRA agents build them. Payment goes into escrow. Validators confirm delivery. Yield is released.

**Status:** MVP implemented. See `membra_sdk/marketplace/jobs.py`.

### 2. Artifact Licensing

Every generated artifact has a hash, license, creator, model trace, test result, and price. Buyers pay for access, reuse, API rights, or commercial license.

**Status:** Architecture. Hash + metadata tracking ready in `membra_sdk/core/artifacts.py`.

### 3. Compute Marketplace

Mac nodes sell verified compute: file analysis, local inference, test running, build compilation, crawling, embeddings, audits. Nodes earn only when jobs are accepted.

**Status:** Architecture. Node module in `membra_sdk/core/node.py`.

### 4. Proof API Subscription

Companies pay monthly for MEMBRA proof services: artifact hashing, timestamping, LLM-output verification, audit trails, Solana anchors, provenance packets.

**Status:** Architecture. Receipt verifier in `membra_sdk/payments/receipts.py`.

### 5. Strategy Sandbox (NOT Autonomous Yield)

DeFi strategies can be simulated and policy-gated. Real funds only move after human approval, risk limits, and external receipts. Yield is counted only after protocol receipt confirms it.

**Status:** Policy-gated stub. Disabled by default. See `membra_sdk/defi/operator.py`.

## The Complete Profit Loop

```
[Buyer]          [Builder]         [Validators]       [Solana]
   │                  │                   │                │
   │ 1. Post job      │                   │                │
   │ 2. Deposit $50   │                   │                │
   │ ──────────────>  │                   │                │
   │                  │ 3. Claim job      │                │
   │                  │ 4. Build artifact │                │
   │                  │ 5. Submit hash    │                │
   │                  │ ──────────────>   │                │
   │                  │                   │ 6. Test artifact│
   │                  │                   │ 7. Hash tests   │
   │                  │ <───────────────  │                │
   │ 8. Approve       │                   │                │
   │ 9. Payment settles│                   │                │
   │ ──────────────────────────────────>  │                │
   │                  │                   │ 10. Verify receipt│
   │                  │                   │ 11. Vote        │
   │                  │                   │ 12. 2/3 consensus│
   │                  │ <─────────────────────────────────  │
   │                  │ 13. Release escrow│                │
   │                  │ 14. Distribute    │                │
   │                  │     yield         │                │
   │                  │ ──────────────────────────────────>│
   │                  │                   │                │ 15. Anchor memo
```

## Distribution Policy

When escrow releases, yield is split according to published policy:

| Category | Share | Purpose |
|----------|-------|---------|
| Infrastructure cost | 15% | Compute, API, storage, bandwidth |
| Validator reward | 20% | Validators who confirmed receipt |
| Builder reward | 45% | Agent that built the artifact |
| Treasury reserve | 10% | Protocol development, community |
| Risk/legal reserve | 10% | Insurance, disputes, compliance |

**Example for $50 job:**
- Infrastructure: $7.50
- Validators: $10.00
- Builder: $22.50
- Treasury: $5.00
- Risk/legal: $5.00

## Consensus Rules for Profit

A batch/job finalizes only if validators agree on:

1. **Artifact hash** — The build artifact was submitted and hashed
2. **Test result** — Tests passed (or buyer waived tests)
3. **Cost basis** — The budget matches the work complexity
4. **Payment receipt** — External payment settled and verified
5. **Settlement status** — Funds cleared into escrow
6. **Distribution policy** — Yield split matches published policy

## The Token Does NOT Mean Profit

MEMBRA token represents:

- **Access** — Priority queue for compute jobs
- **Work credits** — Pre-paid compute time
- **Validator reputation** — Historical consensus participation
- **Proof receipts** — Anchored contribution records
- **Governance** — Vote on accepted job types and policies
- **Fee discounts** — Lower marketplace fees for token holders
- **Staking** — Bond against validator honesty (legally reviewed)

It does NOT represent:
- Guaranteed yield
- Profit share
- Investment contract
- Securities offering

## The Practical MVP

Build one job flow:

1. Buyer deposits $50
2. Agent builds artifact
3. System hashes artifact
4. Tests pass
5. Buyer approves
6. Stripe/Solana payment settles
7. Three validators verify receipt
8. MEMBRA distributes payout
9. Receipt is anchored to Solana devnet

That is the first real profit loop. Everything else is narrative until that loop works.

## Honest Claims

| Incorrect Claim | Correct Claim |
|-----------------|---------------|
| "MEMBRA guarantees $100/day" | "MEMBRA's marketplace could theoretically generate $100/day if buyers consistently pay for verified builds" |
| "LLM consensus creates money" | "LLM consensus creates proof records. Money comes from external buyers" |
| "Autonomous DeFi yield" | "Policy-gated DeFi simulation. Real funds require human approval" |
| "Files are money" | "File analysis estimates potential yield. Actual yield requires verified work + payment" |

## Next Steps

1. Deploy marketplace with real Stripe Connect integration
2. Add artifact IPFS pinning for licensing
3. Build compute job matching engine
4. Launch Proof API with subscription billing
5. Legal review of token design before any launch

## Read More

- `docs/PROOF_OF_YIELD.md` — What yield means in MEMBRA
- `docs/BENCHMARKS.md` — How throughput is measured
- `docs/SECURITY.md` — Key handling and policy gates
- `examples/profit_loop_demo.py` — Complete demo script
