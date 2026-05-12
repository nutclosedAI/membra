"""Settlement Tracker — Confirms money actually moved.

⚠️ SIMULATION: No real settlement tracking. For production, poll Stripe webhooks
or Solana RPC to confirm funds cleared.

Settlement is NOT the same as a receipt. Settlement means:
- Funds left buyer's account
- Funds arrived in escrow or builder account
- The transaction is irreversible (or within dispute window)
"""
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SettlementRecord:
    settlement_id: str
    job_id: str
    receipt_id: str
    amount_usd: float
    from_account: str
    to_account: str
    processor: str
    status: str          # "pending", "cleared", "settled", "disputed", "reversed"
    confirmed_at: Optional[float] = None
    metadata: Dict = field(default_factory=dict)


class SettlementTracker:
    """Tracks whether payments actually settled (funds moved)."""

    def __init__(self):
        self.settlements: Dict[str, SettlementRecord] = {}

    def record_settlement(self, job_id: str, receipt_id: str, amount: float,
                          from_account: str, to_account: str, processor: str) -> SettlementRecord:
        """Record that a payment settlement occurred."""
        settlement = SettlementRecord(
            settlement_id=f"set-{job_id}",
            job_id=job_id,
            receipt_id=receipt_id,
            amount_usd=amount,
            from_account=from_account,
            to_account=to_account,
            processor=processor,
            status="pending",
        )
        self.settlements[settlement.settlement_id] = settlement
        return settlement

    def confirm_settlement(self, settlement_id: str) -> Optional[SettlementRecord]:
        """Confirm settlement completed (funds cleared)."""
        settlement = self.settlements.get(settlement_id)
        if not settlement:
            return None
        settlement.status = "settled"
        settlement.confirmed_at = time.time()
        return settlement

    def is_settled(self, job_id: str) -> bool:
        """Check if payment for a job is fully settled."""
        settlement = self.settlements.get(f"set-{job_id}")
        return settlement is not None and settlement.status == "settled"

    def get_settlement(self, job_id: str) -> Optional[SettlementRecord]:
        return self.settlements.get(f"set-{job_id}")
