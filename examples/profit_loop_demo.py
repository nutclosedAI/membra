#!/usr/bin/env python3
"""
Example: Complete MEMBRA Profit Loop

Demonstrates the full flow from buyer deposit to validator payout:
  1. Buyer posts job + deposits $50
  2. Builder claims + builds artifact
  3. Artifact is hashed + tested
  4. Buyer approves
  5. Payment settles (Stripe receipt)
  6. Three validators verify receipt
  7. Escrow releases → distribution policy applied
  8. Receipt anchored to Solana devnet

Usage:
    python3 examples/profit_loop_demo.py
"""
import sys
sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.profit_loop import MembraProfitLoop


def main():
    print("=" * 70)
    print("  MEMBRA PROFIT LOOP — Complete Revenue Flow Demo")
    print("  Proof-of-Work + Proof-of-Payment + Proof-of-Consensus = Proof-of-Yield")
    print("=" * 70)
    print()

    loop = MembraProfitLoop()

    # 1. Buyer posts a job
    print("[1/9] Buyer posts job...")
    job = loop.post_job(
        title="Build a Solana SPL token contract",
        description="Create an SPL token with mint, burn, and transfer functionality",
        requirements=["Rust", "Anchor framework", "SPL token program"],
        deliverables=["contract.rs", "tests.rs", "README.md"],
        budget=50.0,
        buyer_id="buyer-alice",
    )
    print(f"  Job ID: {job.job_id}")
    print(f"  Budget: ${job.budget_usd:.2f}")
    print()

    # 2. Deposit escrow
    print("[2/9] Buyer deposits $50 into escrow...")
    escrow_result = loop.deposit_escrow(job.job_id, "buyer-alice", 50.0)
    print(f"  Escrow: {escrow_result['escrow_id']}")
    print(f"  State: {escrow_result['state']}")
    print()

    # 3. Builder claims and builds
    print("[3/9] Builder claims job and submits artifact...")
    artifact = """
use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Mint};

#[program]
pub mod membra_token {
    use super::*;
    pub fn mint_to(ctx: Context<MintTo>, amount: u64) -> Result<()> {
        token::mint_to(ctx.accounts.mint_to_ctx(), amount)?;
        Ok(())
    }
}
"""
    job = loop.claim_and_build(job.job_id, "builder-bob", "/tmp/token_contract.rs", artifact)
    print(f"  Builder: {job.builder_id}")
    print(f"  Artifact hash: {job.artifact_hash[:16]}...")
    print()

    # 4. Tests pass
    print("[4/9] Running tests on artifact...")
    job = loop.run_tests(job.job_id, ["echo", "test passed"])  # Simulated
    print(f"  Test status: {job.test_result.get('passed')}")
    print()

    # 5. Buyer approves
    print("[5/9] Buyer approves delivery...")
    job = loop.buyer_approve(job.job_id)
    print(f"  Approved at: {job.approved_at}")
    print()

    # 6. Payment settles
    print("[6/9] Payment settles via Stripe...")
    settlement = loop.settle_payment(
        job.job_id,
        processor="stripe",
        tx_id="pi_3Oxyz1234567890",
        amount=50.0,
    )
    print(f"  Receipt verified: {settlement['receipt_verified']}")
    print(f"  Settlement: {settlement['settlement_status']}")
    print()

    # 7. Validators verify receipt
    print("[7/9] Three validators verify payment receipt...")
    validator_votes = [
        {"validator_id": "val-1", "receipt_valid": True, "confidence": 0.95},
        {"validator_id": "val-2", "receipt_valid": True, "confidence": 0.92},
        {"validator_id": "val-3", "receipt_valid": True, "confidence": 0.98},
    ]
    consensus = loop.validator_consensus(job.job_id, validator_votes)
    print(f"  Consensus reached: {consensus['consensus_reached']}")
    print(f"  Valid votes: {consensus['valid_votes']}/{consensus['votes']}")
    print()

    # 8. Distribute yield
    print("[8/9] Releasing escrow and distributing yield...")
    distribution = loop.release_and_distribute(job.job_id)
    if distribution:
        d = distribution["distribution"]
        print(f"  Total: ${d['total']:.2f}")
        print(f"  Infrastructure: ${d['infrastructure_cost']:.2f}")
        print(f"  Validators: ${d['validator_reward']:.2f}")
        print(f"  Builder: ${d['builder_reward']:.2f}")
        print(f"  Treasury: ${d['treasury_reserve']:.2f}")
        print(f"  Risk/Legal: ${d['risk_legal_reserve']:.2f}")
    print()

    # 9. Anchor to Solana
    print("[9/9] Anchoring receipt to Solana devnet...")
    memo = loop.anchor_to_solana(job.job_id)
    print(f"  Memo: {memo}")
    print(f"  Explorer: https://explorer.solana.com/?cluster=devnet")
    print()

    print("=" * 70)
    print("  PROFIT LOOP COMPLETE")
    print("=" * 70)
    print()
    print("Summary:")
    print(f"  Job: {job.job_id}")
    print(f"  Revenue: $50.00")
    print(f"  Builder earned: ${d['builder_reward']:.2f}")
    print(f"  Validators earned: ${d['validator_reward']:.2f}")
    print(f"  Net yield distributed: ${d['total'] - d['infrastructure_cost'] - d['treasury_reserve'] - d['risk_legal_reserve']:.2f}")
    print()
    print("  This is the first real profit loop. Everything else is narrative until")
    print("  this loop works with real buyers, real builders, and real settlement.")


if __name__ == "__main__":
    main()
