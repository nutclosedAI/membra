"""Consensus Engine — Layer 4b of MEMBRA Proof-of-Job

Aggregates validator votes and determines if a job is accepted.

Rules:
  - Threshold: 2/3 majority required
  - If consensus fails, job is rejected
  - Rejection reasons are preserved for retry
"""
from typing import Dict, List


class ConsensusEngine:
    """Determines consensus from validator votes."""

    DEFAULT_THRESHOLD = "2/3"

    def __init__(self, threshold: str = None):
        self.threshold = threshold or self.DEFAULT_THRESHOLD

    def evaluate(self, votes: List[Dict]) -> Dict:
        """Evaluate votes and return consensus result."""
        if not votes:
            return {
                "result": "rejected",
                "reason": "No votes received",
                "yes_votes": 0,
                "total_votes": 0,
                "ratio": 0.0,
                "threshold": self.threshold,
                "rejection_reasons": ["No validators ran"],
            }

        total = len(votes)
        yes_votes = sum(1 for v in votes if v.get("vote") == "accept")
        no_votes = total - yes_votes
        ratio = yes_votes / total if total > 0 else 0

        # Parse threshold
        if "/" in self.threshold:
            num, denom = self.threshold.split("/")
            required = int(num) / int(denom)
        else:
            required = float(self.threshold)

        passed = ratio >= required

        rejection_reasons = [
            v["reason"] for v in votes if v.get("vote") == "reject"
        ]

        return {
            "result": "accepted" if passed else "rejected",
            "yes_votes": yes_votes,
            "no_votes": no_votes,
            "total_votes": total,
            "ratio": round(ratio, 3),
            "threshold": self.threshold,
            "rejection_reasons": rejection_reasons if not passed else [],
        }

    def can_retry(self, consensus: Dict) -> bool:
        """Determine if a rejected job can be retried."""
        if consensus["result"] == "accepted":
            return False
        # Can retry if at least one validator accepted
        return consensus.get("yes_votes", 0) > 0
