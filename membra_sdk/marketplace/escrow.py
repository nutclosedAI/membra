"""Escrow Manager — Holds buyer funds until delivery is confirmed.

⚠️ SIMULATION: No real money is held. For production, integrate Stripe Connect
or smart-contract escrow with real payment webhooks.

Funds are released only after:
1. Artifact is delivered
2. Tests pass
3. Buyer approves
4. Payment settles
5. Validators confirm receipt
"""
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class EscrowState(Enum):
    HELD = "held"           # Funds deposited, waiting for delivery
    RELEASED = "released"   # Funds released to builder after approval
    REFUNDED = "refunded"   # Funds returned to buyer (cancelled/disputed)
    FROZEN = "frozen"       # Funds frozen during dispute resolution


@dataclass
class Escrow:
    escrow_id: str
    job_id: str
    buyer_id: str
    builder_id: Optional[str]
    amount_usd: float
    state: EscrowState = EscrowState.HELD
    deposits: List[Dict] = field(default_factory=list)
    releases: List[Dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    released_at: Optional[float] = None


class EscrowManager:
    """Manages escrow for build bounty marketplace."""

    # Distribution policy: where yield goes after release
    DISTRIBUTION_POLICY = {
        "infrastructure_cost": 0.15,   # 15% — compute, API, storage
        "validator_reward": 0.20,      # 20% — validators who confirmed
        "builder_reward": 0.45,        # 45% — agent that built artifact
        "treasury_reserve": 0.10,      # 10% — protocol treasury
        "risk_legal_reserve": 0.10,    # 10% — insurance, legal, disputes
    }

    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or "/tmp/membra_escrow.json"
        self.escrows: Dict[str, Escrow] = {}
        self._load()

    def deposit(self, job_id: str, buyer_id: str, builder_id: str,
                amount_usd: float, payment_method: str = "stripe") -> Escrow:
        """Buyer deposits funds into escrow."""
        escrow = Escrow(
            escrow_id=f"esc-{job_id}",
            job_id=job_id,
            buyer_id=buyer_id,
            builder_id=builder_id,
            amount_usd=amount_usd,
        )
        escrow.deposits.append({
            "amount": amount_usd,
            "method": payment_method,
            "timestamp": time.time(),
            "status": "confirmed",
        })
        self.escrows[escrow.escrow_id] = escrow
        self._persist()
        return escrow

    def release(self, escrow_id: str, receipt: Dict) -> Optional[Dict]:
        """Release escrow funds after all conditions met."""
        escrow = self.escrows.get(escrow_id)
        if not escrow or escrow.state != EscrowState.HELD:
            return None

        escrow.state = EscrowState.RELEASED
        escrow.released_at = time.time()
        escrow.releases.append(receipt)

        # Calculate distribution according to policy
        distribution = self._calculate_distribution(escrow.amount_usd)

        self._persist()
        return {
            "escrow_id": escrow_id,
            "amount": escrow.amount_usd,
            "distribution": distribution,
            "receipt": receipt,
        }

    def refund(self, escrow_id: str, reason: str) -> Optional[Escrow]:
        """Refund buyer (cancelled job or dispute resolution)."""
        escrow = self.escrows.get(escrow_id)
        if not escrow or escrow.state != EscrowState.HELD:
            return None
        escrow.state = EscrowState.REFUNDED
        escrow.releases.append({
            "type": "refund",
            "reason": reason,
            "timestamp": time.time(),
        })
        self._persist()
        return escrow

    def freeze(self, escrow_id: str, reason: str) -> Optional[Escrow]:
        """Freeze escrow during dispute."""
        escrow = self.escrows.get(escrow_id)
        if not escrow or escrow.state != EscrowState.HELD:
            return None
        escrow.state = EscrowState.FROZEN
        self._persist()
        return escrow

    def _calculate_distribution(self, amount: float) -> Dict:
        """Split revenue according to published policy."""
        return {
            "infrastructure_cost": round(amount * self.DISTRIBUTION_POLICY["infrastructure_cost"], 2),
            "validator_reward": round(amount * self.DISTRIBUTION_POLICY["validator_reward"], 2),
            "builder_reward": round(amount * self.DISTRIBUTION_POLICY["builder_reward"], 2),
            "treasury_reserve": round(amount * self.DISTRIBUTION_POLICY["treasury_reserve"], 2),
            "risk_legal_reserve": round(amount * self.DISTRIBUTION_POLICY["risk_legal_reserve"], 2),
            "total": round(amount, 2),
        }

    def get_escrow(self, job_id: str) -> Optional[Escrow]:
        return self.escrows.get(f"esc-{job_id}")

    def _persist(self):
        data = {}
        for eid, esc in self.escrows.items():
            data[eid] = {
                "escrow_id": esc.escrow_id,
                "job_id": esc.job_id,
                "buyer_id": esc.buyer_id,
                "builder_id": esc.builder_id,
                "amount_usd": esc.amount_usd,
                "state": esc.state.value,
                "deposits": esc.deposits,
                "releases": esc.releases,
                "created_at": esc.created_at,
                "released_at": esc.released_at,
            }
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path) as f:
                data = json.load(f)
            for eid, edata in data.items():
                self.escrows[eid] = Escrow(
                    escrow_id=edata["escrow_id"],
                    job_id=edata["job_id"],
                    buyer_id=edata["buyer_id"],
                    builder_id=edata.get("builder_id"),
                    amount_usd=edata["amount_usd"],
                    state=EscrowState(edata["state"]),
                    deposits=edata.get("deposits", []),
                    releases=edata.get("releases", []),
                    created_at=edata["created_at"],
                    released_at=edata.get("released_at"),
                )
        except Exception:
            pass
