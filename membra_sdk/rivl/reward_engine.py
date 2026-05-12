"""MEMBRA RIVL — Reinforcement Inverted Validator Learning

The reward engine scores outputs based on verification results.
Positive reward = verified success. Negative reward = verified failure.

Formula:
  reward = artifact_score + test_score + receipt_score + consensus_score
           - security_penalty - hallucination_penalty - failed_test_penalty
           - unpaid_work_penalty - financial_loss_penalty - policy_violation_penalty

Doctrine:
  Punishment is not violence. Punishment is negative evidence.
  Reward is not fantasy profit. Reward is verified success.
  Yield is not model confidence. Yield is settled external value.
"""
import hashlib
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class RewardEvent:
    """A single scored output event."""
    prompt_hash: str
    output_hash: str
    reward: float
    verdict: str          # "accepted" or "punished"
    reason: str
    tests_passed: bool
    security_passed: bool
    payment_verified: bool
    consensus_verified: bool
    financial_loss: bool
    policy_violation: bool
    timestamp: float


class RIVLRewardEngine:
    """Scores LLM outputs based on verifier results.

    Every output that survives verification becomes a positive example.
    Every output that fails becomes a negative example.
    """

    # Default weights — harsh on safety/financial, generous on verified success
    DEFAULT_WEIGHTS = {
        "tests_passed": 10.0,
        "tests_failed": -25.0,
        "security_passed": 10.0,
        "security_failed": -50.0,
        "payment_verified": 25.0,
        "payment_missing": -5.0,
        "consensus_verified": 15.0,
        "consensus_missing": -10.0,
        "artifact_downloaded": 5.0,
        "refund_requested": -50.0,
        "financial_loss": -100.0,
        "policy_violation": -100.0,
        "mainnet_without_approval": -1000.0,
        "loss_of_funds": -10000.0,
        "verified_profit_after_fees": 50.0,
        "receipt_confirmed_yield": 100.0,
        "failed_simulation": -25.0,
        "slippage_too_high": -50.0,
        "unauthorized_contract": -100.0,
    }

    def __init__(self, storage_path: str = None, weights: Dict[str, float] = None):
        self.storage_path = Path(storage_path or "~/.membra/reward_events.jsonl")
        self.storage_path = self.storage_path.expanduser()
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()

    def score(
        self,
        prompt: str,
        output: str,
        tests_passed: bool = False,
        security_passed: bool = False,
        payment_verified: bool = False,
        consensus_verified: bool = False,
        financial_loss: bool = False,
        policy_violation: bool = False,
        artifact_downloaded: bool = False,
        refund_requested: bool = False,
        mainnet_without_approval: bool = False,
        loss_of_funds: bool = False,
        slippage_too_high: bool = False,
        unauthorized_contract: bool = False,
    ) -> RewardEvent:
        """Score an output based on verifier results.

        Returns RewardEvent with reward, verdict, and reason.
        """
        reward = 0.0
        reasons = []

        # Tests
        if tests_passed:
            reward += self.weights["tests_passed"]
            reasons.append("tests_passed")
        else:
            reward += self.weights["tests_failed"]
            reasons.append("tests_failed")

        # Security
        if security_passed:
            reward += self.weights["security_passed"]
            reasons.append("security_passed")
        else:
            reward += self.weights["security_failed"]
            reasons.append("security_failed")

        # Payment
        if payment_verified:
            reward += self.weights["payment_verified"]
            reasons.append("payment_verified")
        else:
            reward += self.weights["payment_missing"]
            reasons.append("payment_missing")

        # Consensus
        if consensus_verified:
            reward += self.weights["consensus_verified"]
            reasons.append("consensus_verified")
        else:
            reward += self.weights["consensus_missing"]
            reasons.append("consensus_missing")

        # Artifact delivery
        if artifact_downloaded:
            reward += self.weights["artifact_downloaded"]
            reasons.append("artifact_downloaded")

        # Financial events
        if refund_requested:
            reward += self.weights["refund_requested"]
            reasons.append("refund_requested")
        if financial_loss:
            reward += self.weights["financial_loss"]
            reasons.append("financial_loss")
        if mainnet_without_approval:
            reward += self.weights["mainnet_without_approval"]
            reasons.append("mainnet_without_approval")
        if loss_of_funds:
            reward += self.weights["loss_of_funds"]
            reasons.append("loss_of_funds")
        if slippage_too_high:
            reward += self.weights["slippage_too_high"]
            reasons.append("slippage_too_high")
        if unauthorized_contract:
            reward += self.weights["unauthorized_contract"]
            reasons.append("unauthorized_contract")

        # Verdict
        verdict = "accepted" if reward > 0 else "punished"

        event = RewardEvent(
            prompt_hash=self._hash(prompt),
            output_hash=self._hash(output),
            reward=round(reward, 2),
            verdict=verdict,
            reason=",".join(reasons),
            tests_passed=tests_passed,
            security_passed=security_passed,
            payment_verified=payment_verified,
            consensus_verified=consensus_verified,
            financial_loss=financial_loss,
            policy_violation=policy_violation,
            timestamp=time.time(),
        )

        self._persist(event)
        return event

    def get_stats(self) -> Dict:
        """Get reward engine statistics."""
        events = self._load_all()
        if not events:
            return {"total_events": 0, "accept_rate": 0, "avg_reward": 0}

        total = len(events)
        accepted = sum(1 for e in events if e["verdict"] == "accepted")
        punished = total - accepted
        total_reward = sum(e["reward"] for e in events)
        avg_reward = total_reward / total
        max_reward = max(e["reward"] for e in events)
        min_reward = min(e["reward"] for e in events)

        return {
            "total_events": total,
            "accepted": accepted,
            "punished": punished,
            "accept_rate": round(accepted / total, 3),
            "total_reward": round(total_reward, 2),
            "avg_reward": round(avg_reward, 2),
            "max_reward": max_reward,
            "min_reward": min_reward,
        }

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _persist(self, event: RewardEvent):
        """Append event to JSONL."""
        with self.storage_path.open("a") as f:
            f.write(json.dumps(asdict(event)) + "\n")

    def _load_all(self) -> List[Dict]:
        """Load all events from JSONL."""
        events = []
        if not self.storage_path.exists():
            return events
        with self.storage_path.open("r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return events
