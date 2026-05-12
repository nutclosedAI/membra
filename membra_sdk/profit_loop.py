"""MEMBRA Profit Loop — Complete revenue flow from buyer deposit to validator payout.

⚠️ SIMULATION: This module demonstrates the logic flow. No real money moves.
For production, integrate Stripe Connect + real escrow + Solana mainnet.

The Formula:
  Yield = verified external revenue − costs − risk reserve

The Flow:
  1. Buyer posts job + deposits funds → escrow
  2. Builder claims + builds artifact
  3. Artifact is hashed + tested
  4. Buyer approves delivery
  5. Payment settles (Stripe/Solana receipt)
  6. Validators verify receipt (2/3 consensus)
  7. Escrow releases → distribution policy applied
  8. Receipt anchored to Solana devnet
  9. Yield is distributed: builder, validators, infrastructure, treasury, risk reserve

Revenue Sources:
  1. Build bounty marketplace
  2. Artifact licensing
  3. Compute marketplace
  4. Proof API subscription
  5. Strategy sandbox (policy-gated)
"""
import hashlib
import json
import time
from typing import Dict, List, Optional

from membra_sdk.marketplace.jobs import JobBoard, JobStatus, BuildJob
from membra_sdk.marketplace.escrow import EscrowManager
from membra_sdk.payments.receipts import ReceiptVerifier, PaymentReceipt
from membra_sdk.payments.settlement import SettlementTracker
from membra_sdk.consensus.poy import ProofOfYieldConsensus


class MembraProfitLoop:
    """Orchestrates the complete profit loop from job posting to yield distribution."""

    def __init__(self):
        self.jobs = JobBoard()
        self.escrow = EscrowManager()
        self.receipts = ReceiptVerifier()
        self.settlements = SettlementTracker()
        self.consensus = ProofOfYieldConsensus(agent_id="profit-loop")

    def post_job(self, title: str, description: str, requirements: List[str],
                 deliverables: List[str], budget: float, buyer_id: str) -> BuildJob:
        """Step 1: Buyer posts job."""
        return self.jobs.post_job(title, description, requirements, deliverables, budget, buyer_id)

    def deposit_escrow(self, job_id: str, buyer_id: str, amount: float) -> Dict:
        """Step 2: Buyer deposits funds into escrow."""
        job = self.jobs.get_job(job_id)
        if not job:
            return {"error": "Job not found"}

        escrow = self.escrow.deposit(
            job_id=job_id,
            buyer_id=buyer_id,
            builder_id=job.builder_id,
            amount_usd=amount,
        )
        return {
            "escrow_id": escrow.escrow_id,
            "amount": amount,
            "state": escrow.state.value,
        }

    def claim_and_build(self, job_id: str, builder_id: str,
                        artifact_path: str, artifact_content: str) -> Optional[BuildJob]:
        """Step 3: Builder claims job and submits artifact."""
        # Claim
        job = self.jobs.claim_job(job_id, builder_id)
        if not job:
            return None

        # Build
        artifact_hash = hashlib.sha256(artifact_content.encode()).hexdigest()
        return self.jobs.submit_artifact(job_id, artifact_path, artifact_hash)

    def run_tests(self, job_id: str, test_command: List[str]) -> Optional[BuildJob]:
        """Step 4: Run tests on artifact."""
        import subprocess
        try:
            result = subprocess.run(
                test_command,
                capture_output=True,
                text=True,
                timeout=60,
            )
            test_result = {
                "passed": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": result.stdout[:1000],
                "stderr": result.stderr[:500],
                "timestamp": time.time(),
            }
        except Exception as e:
            test_result = {
                "passed": False,
                "error": str(e),
                "timestamp": time.time(),
            }

        return self.jobs.submit_tests(job_id, test_result)

    def buyer_approve(self, job_id: str) -> Optional[BuildJob]:
        """Step 5: Buyer approves delivery."""
        return self.jobs.buyer_approve(job_id)

    def settle_payment(self, job_id: str, processor: str, tx_id: str,
                       amount: float, currency: str = "USD") -> Dict:
        """Step 6: Payment settles, receipt created."""
        receipt = PaymentReceipt(
            receipt_id=f"rcpt-{job_id}",
            job_id=job_id,
            processor=processor,
            transaction_id=tx_id,
            amount_usd=amount,
            amount_crypto=None,
            currency=currency,
            status="settled",
            timestamp=time.time(),
            metadata={"source": "profit_loop"},
        )

        # Verify receipt
        verification = self.receipts.verify(receipt)

        # Record settlement
        settlement = self.settlements.record_settlement(
            job_id=job_id,
            receipt_id=receipt.receipt_id,
            amount=amount,
            from_account="buyer",
            to_account="escrow",
            processor=processor,
        )
        self.settlements.confirm_settlement(settlement.settlement_id)

        # Update job
        job = self.jobs.submit_payment_receipt(job_id, {
            "receipt_id": receipt.receipt_id,
            "processor": processor,
            "tx_id": tx_id,
            "amount": amount,
            "verified": verification["valid"],
            "verification_hash": receipt.hash(),
        })

        return {
            "receipt_verified": verification["valid"],
            "settlement_status": settlement.status,
            "job_status": job.status.value if job else "unknown",
        }

    def validator_consensus(self, job_id: str, validator_votes: List[Dict]) -> Dict:
        """Step 7: Validators verify receipt and reach consensus."""
        for vote in validator_votes:
            self.jobs.validator_vote(job_id, vote["validator_id"], vote)

        job = self.jobs.get_job(job_id)
        if not job:
            return {"error": "Job not found"}

        return {
            "consensus_reached": job.status == JobStatus.FINALIZED,
            "votes": len(job.validator_votes),
            "valid_votes": sum(1 for v in job.validator_votes if v.get("receipt_valid")),
            "status": job.status.value,
        }

    def release_and_distribute(self, job_id: str) -> Optional[Dict]:
        """Step 8: Release escrow and distribute yield."""
        job = self.jobs.get_job(job_id)
        if not job or job.status != JobStatus.FINALIZED:
            return None

        escrow = self.escrow.get_escrow(job_id)
        if not escrow:
            return None

        # Release escrow with receipt
        distribution = self.escrow.release(
            escrow.escrow_id,
            receipt={
                "job_id": job_id,
                "artifact_hash": job.artifact_hash,
                "test_passed": job.test_result.get("passed") if job.test_result else False,
                "buyer_approved": job.approved_at is not None,
                "settlement_confirmed": self.settlements.is_settled(job_id),
                "validator_consensus": True,
                "timestamp": time.time(),
            }
        )

        if not distribution:
            return None

        return {
            "job_id": job_id,
            "amount": distribution["amount"],
            "distribution": distribution["distribution"],
            "receipt": distribution["receipt"],
            "status": "yield_distributed",
        }

    def anchor_to_solana(self, job_id: str) -> Optional[str]:
        """Step 9: Anchor finalized receipt to Solana devnet (optional)."""
        job = self.jobs.get_job(job_id)
        if not job:
            return None

        memo = f"MEMBRA|YIELD|{job_id}|{job.artifact_hash[:16]}|{job.budget_usd:.2f}"
        # In production: call Solana client to submit memo
        # For now, return the memo that would be anchored
        return memo

    def run_full_loop(self, job_spec: Dict, builder_id: str,
                      artifact_content: str, validator_votes: List[Dict]) -> Dict:
        """Run the complete profit loop from post to distribution."""
        # 1. Post job
        job = self.post_job(
            title=job_spec["title"],
            description=job_spec["description"],
            requirements=job_spec["requirements"],
            deliverables=job_spec["deliverables"],
            budget=job_spec["budget"],
            buyer_id=job_spec["buyer_id"],
        )

        # 2. Deposit escrow
        self.deposit_escrow(job.job_id, job_spec["buyer_id"], job_spec["budget"])

        # 3. Build artifact
        self.claim_and_build(job.job_id, builder_id, "/tmp/artifact.py", artifact_content)

        # 4. Run tests (dummy)
        self.jobs.submit_tests(job.job_id, {
            "passed": True,
            "exit_code": 0,
            "timestamp": time.time(),
        })

        # 5. Buyer approves
        self.buyer_approve(job.job_id)

        # 6. Settle payment
        self.settle_payment(
            job.job_id,
            processor="stripe",
            tx_id=f"pi_{hashlib.sha256(job.job_id.encode()).hexdigest()[:24]}",
            amount=job_spec["budget"],
        )

        # 7. Validator consensus
        self.validator_consensus(job.job_id, validator_votes)

        # 8. Distribute
        distribution = self.release_and_distribute(job.job_id)

        # 9. Anchor
        anchor_memo = self.anchor_to_solana(job.job_id)

        return {
            "job_id": job.job_id,
            "status": "complete",
            "distribution": distribution,
            "anchor_memo": anchor_memo,
        }
