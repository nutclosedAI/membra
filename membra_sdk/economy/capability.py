"""Capability — constrained economic agency for an agent.

Not "you may spend $100" — "you may create economic obligations up to
$100, and those obligations remain governed by observable outcomes."
A grant is finite, typed, evidence-gated, expirable, and revocable.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


class CapabilityError(Exception):
    pass


@dataclass
class Capability:
    """A bounded economic mandate issued to an agent."""

    budget: float  # total value the agent may obligate
    max_exposure: float  # largest single unsettled obligation
    permitted_acts: list[str]  # promise types the agent may create
    currency: str = "USD"
    success_rule: str | None = None  # contract/policy id governing outcomes
    evidence_required: bool = True
    outcome_check_required: bool = True
    compensation_permitted: bool = True
    expires_at: float | None = None
    revoked: bool = False
    capability_id: str = field(default_factory=lambda: f"CAP_{uuid.uuid4().hex[:10]}")
    _obligated: float = field(default=0.0, repr=False)

    def _check_live(self) -> None:
        if self.revoked:
            raise CapabilityError("capability revoked")
        if self.expires_at is not None and time.time() > self.expires_at:
            raise CapabilityError("capability expired")

    def authorize(self, act_type: str, amount: float) -> dict:
        """Gate an intended obligation. Returns the authorization fields
        for an EconomicStateObject, or raises CapabilityError."""
        self._check_live()
        if act_type not in self.permitted_acts:
            raise CapabilityError(f"act type not permitted: {act_type}")
        if amount > self.max_exposure:
            raise CapabilityError(
                f"amount {amount} exceeds max_exposure {self.max_exposure}"
            )
        if self._obligated + amount > self.budget:
            raise CapabilityError(
                f"budget exceeded: {self._obligated + amount} > {self.budget}"
            )
        self._obligated += amount
        return {
            "max_value": amount,
            "currency": self.currency,
            "capability_id": self.capability_id,
        }

    def release(self, amount: float) -> None:
        """Free budget when an obligation concludes."""
        self._obligated = max(0.0, self._obligated - amount)

    def revoke(self) -> None:
        self.revoked = True

    def to_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "budget": self.budget,
            "max_exposure": self.max_exposure,
            "permitted_acts": self.permitted_acts,
            "currency": self.currency,
            "success_rule": self.success_rule,
            "evidence_required": self.evidence_required,
            "outcome_check_required": self.outcome_check_required,
            "compensation_permitted": self.compensation_permitted,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
            "obligated": self._obligated,
        }
