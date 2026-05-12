"""Yield Meter — Layer 3 of MEMBRA Proof-of-Job

Measures 4 kinds of yield:
  1. Artifact Yield    — files, code, docs produced
  2. Validation Yield  — tests, benchmarks, policy checks passed
  3. Market Yield      — bounty accepted, invoice paid, grant approved (external)
  4. Chain Yield       — blockchain receipt, escrow, staking (external)

MEMBRA generates the first two directly.
MEMBRA documents the third and fourth only when external receipts exist.
"""
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class YieldReport:
    """A complete yield measurement for a job."""
    artifact_yield: float = 0.0
    validation_yield: float = 0.0
    market_yield: float = 0.0
    chain_yield: float = 0.0
    total_score: float = 0.0
    files_created: int = 0
    tests_passed: int = 0
    tests_total: int = 0
    lint_passed: bool = False
    security_flags: int = 0
    economic_status: str = "unsettled"
    real_revenue: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


class YieldMeter:
    """Measures yield for completed jobs."""

    def score_artifact_yield(self, artifacts: List[Dict]) -> float:
        """Score based on number, size, and diversity of artifacts."""
        if not artifacts:
            return 0.0
        count = len(artifacts)
        total_bytes = sum(a.get("bytes", 0) for a in artifacts)
        # Normalize: 4 files ≈ 100, more files diminishing returns
        score = min(100, 20 * count + min(20, total_bytes / 10000))
        return round(score, 1)

    def score_validation_yield(self, tests_passed: int, tests_total: int,
                                lint_passed: bool, security_flags: int) -> float:
        """Score based on validation checks."""
        if tests_total == 0:
            test_score = 50  # No tests is neutral
        else:
            test_score = (tests_passed / tests_total) * 100

        lint_bonus = 10 if lint_passed else 0
        security_penalty = min(50, security_flags * 10)

        score = test_score + lint_bonus - security_penalty
        return max(0, round(score, 1))

    def score_market_yield(self, receipts: List[Dict]) -> float:
        """Score market yield from external receipts.

        MEMBRA does not generate this directly.
        It only scores what external systems confirm.
        """
        if not receipts:
            return 0.0
        total = sum(r.get("amount", 0) for r in receipts if r.get("status") == "confirmed")
        # Normalize: $100 ≈ 50 score
        score = min(100, total / 2)
        return round(score, 1)

    def score_chain_yield(self, chain_receipts: List[Dict]) -> float:
        """Score blockchain yield from on-chain receipts."""
        if not chain_receipts:
            return 0.0
        confirmed = [r for r in chain_receipts if r.get("confirmed", False)]
        score = min(100, len(confirmed) * 25)
        return round(score, 1)

    def measure(self, artifacts: List[Dict] = None,
                tests_passed: int = 0, tests_total: int = 0,
                lint_passed: bool = False, security_flags: int = 0,
                market_receipts: List[Dict] = None,
                chain_receipts: List[Dict] = None) -> YieldReport:
        """Measure all yield types and return a YieldReport."""
        artifacts = artifacts or []
        market_receipts = market_receipts or []
        chain_receipts = chain_receipts or []

        artifact = self.score_artifact_yield(artifacts)
        validation = self.score_validation_yield(
            tests_passed, tests_total, lint_passed, security_flags
        )
        market = self.score_market_yield(market_receipts)
        chain = self.score_chain_yield(chain_receipts)

        # Weighted total: artifact and validation matter most for internal scoring
        total = (
            artifact * 0.35 +
            validation * 0.35 +
            market * 0.15 +
            chain * 0.15
        )

        real_revenue = sum(
            r.get("amount", 0) for r in market_receipts if r.get("status") == "confirmed"
        )

        return YieldReport(
            artifact_yield=artifact,
            validation_yield=validation,
            market_yield=market,
            chain_yield=chain,
            total_score=round(total, 1),
            files_created=len(artifacts),
            tests_passed=tests_passed,
            tests_total=tests_total,
            lint_passed=lint_passed,
            security_flags=security_flags,
            economic_status="settled" if real_revenue > 0 else "unsettled",
            real_revenue=real_revenue,
        )
