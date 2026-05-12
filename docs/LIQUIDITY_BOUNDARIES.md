# MEMBRA Liquidity Boundaries

## The Honest Truth About Money in MEMBRA

This document exists because crypto projects frequently misrepresent their financial status. MEMBRA does not.

## Current State (v0.1)

| Item | Status | Amount |
|------|--------|--------|
| Token Mint | **NOT CREATED** | $0.00 |
| Mainnet Liquidity Pool | **NOT CREATED** | $0.00 |
| Devnet Test Pool | **NOT CREATED** | $0.00 |
| Official Treasury | **NOT CREATED** | $0.00 |
| Escrow Contract | **SIMULATED** | JSON files in `/tmp` |
| Real Money Moved | **ZERO** | $0.00 |
| Stripe Connect Live | **NOT CONFIGURED** | $0.00 |
| Solana Mainnet SOL | **ZERO** | 0 SOL |

## What Does NOT Exist

- **No token.** There is no MEMBRA token. No mint address. No supply. No market cap.
- **No liquidity pool.** No DEX pair. No AMM. No LP tokens.
- **No staking.** No validator staking rewards. No slashing conditions active.
- **No automatic payout.** No smart contract releases funds. No yield farming.
- **No guaranteed return.** No APY. No ROI. No "passive income."

## What Is Simulated

The `examples/profit_loop_demo.py` and `membra_sdk/job/settlement.py` contain **simulated** financial flows:

```python
# SIMULATED — this is math on paper, not real money
escrow_amount = 50.00  # No $50 exists
builder_payout = 22.50   # No $22.50 is transferred
validator_reward = 15.00 # No $15.00 is paid
platform_fee = 7.50      # No $7.50 is collected
```

## What Could Become Real

| Path | Requirements | Risk Level |
|------|-------------|------------|
| Stripe Connect payments | Business entity, KYC, test mode first | Low |
| Solana SPL payment receipts | Devnet testing, no custody | Low |
| Bounty escrow (v0.3) | Smart contract audit, testnet | Medium |
| Validator staking (v0.4) | Token design, legal review, audit | High |
| Full marketplace (v1.0) | Securities compliance, regulatory review | Very High |

## The Rule

> **"Money only moves when a human signs a transaction, an external payment processor confirms receipt, and a validator network independently verifies the proof-of-job. Until then, all numbers are projections."**

## For Investors / Funders

### What You Are Funding
- Open-source protocol development
- Validator infrastructure software
- On-chain proof-of-job research
- Multi-language AI validator tooling

### What You Are NOT Funding
- A token sale
- A liquidity pool
- Guaranteed returns
- Passive income
- An already-profitable business

### What Would Make Money Real
1. A buyer deposits $50 via Stripe
2. A builder completes a job and submits artifacts
3. Tests pass, validators vote ACCEPT
4. Buyer clicks "Approve"
5. Stripe webhook fires `payment_intent.succeeded`
6. Builder receives $22.50 in their bank account
7. Solana devnet records the proof hash

Until step 6 happens, all financial claims are projections.

## Legal Protections

- No securities are offered.
- No investment contract exists.
- Contributors receive no equity, tokens, or guaranteed payments.
- MIT license: use at your own risk.
- See `docs/YIELD_DEFINITIONS.md` for honest yield terminology.

## Contact

For questions about financial status: read this file.
For questions about protocol architecture: read `docs/SOLANA_PROGRAM.md`.
For questions about legal boundaries: read `docs/YIELD_DEFINITIONS.md`.

## Version

v0.1 — No-custody, no-token, no-pool, no-guarantee.

Last updated: 2026-05-11
