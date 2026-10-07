"""Economic State Object — the canonical unit of the BRO outcome runtime.

A payment record does not disappear after settlement; it remains alive.
The object accumulates promise -> authorization -> settlement ->
observation -> outcome -> consequence, and every transition appends to
its causal chain, so `causal_chain()` always reconstructs

    INTENT -> POLICY -> AUTHORITY -> EVENT -> EVIDENCE -> CLEARING
        -> SETTLEMENT -> OBSERVED OUTCOME -> OUTCOME CLASSIFICATION
        -> CONSEQUENCE -> CURRENT STATE

States: the act is never FINAL — `SettlementStatus.SETTLED` is merely
one state in the loop; S_t != FINAL.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class SettlementStatus(str, Enum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    HELD = "HELD"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    RETURNED = "RETURNED"
    DISPUTED = "DISPUTED"


class OutcomeState(str, Enum):
    UNKNOWN = "UNKNOWN"
    FULFILLED = "FULFILLED"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    FAILED = "FAILED"


class ConsequenceType(str, Enum):
    NONE = "NONE"
    COMPENSATION = "COMPENSATION"
    PARTIAL_RELEASE = "PARTIAL_RELEASE"
    REFUND = "REFUND"
    DISPUTE = "DISPUTE"
    PENALTY = "PENALTY"


@dataclass
class Promise:
    """What was promised, in machine-checkable conditions."""

    type: str  # e.g. "DELIVERY", "SERVICE", "DATA", "SETTLEMENT"
    conditions: list[str] = field(default_factory=list)
    deadline: float | None = None  # unix time, optional
    terms: dict = field(default_factory=dict)  # extra machine-readable terms


@dataclass
class Authorization:
    """Bound authority — created from a Capability grant, never exceeds it."""

    max_value: float
    currency: str
    capability_id: str | None = None
    authorized_by: str | None = None


@dataclass
class Settlement:
    amount: float = 0.0
    status: SettlementStatus = SettlementStatus.PENDING
    settled_at: float | None = None


@dataclass
class Observation:
    """Observed reality, one entry per promise condition plus free keys."""

    values: dict = field(default_factory=dict)
    observed_at: float = field(default_factory=time.time)
    source: str | None = None


@dataclass
class OutcomeVector:
    """Multidimensional outcome O = (Q, T, C, R, D, U)."""

    quality: float = 0.0  # Q — how good the delivered thing was
    timeliness: float = 0.0  # T — 1.0 on time, decays with lateness
    completeness: float = 0.0  # C — fraction of conditions met
    reliability: float = 0.0  # R — consistency of the counterparty/evidence
    deviation: float = 0.0  # D — magnitude of promise-vs-reality gap
    uncertainty: float = 0.0  # U — 1 - confidence in the evaluation

    def weighted(self, w: dict[str, float] | None = None) -> float:
        w = w or {
            "quality": 1.0,
            "timeliness": 1.0,
            "completeness": 1.0,
            "reliability": 1.0,
        }
        num = (
            w.get("quality", 0.0) * self.quality
            + w.get("timeliness", 0.0) * self.timeliness
        )
        num += (
            w.get("completeness", 0.0) * self.completeness
            + w.get("reliability", 0.0) * self.reliability
        )
        num -= w.get("deviation", 0.5) * self.deviation
        den = sum(v for v in w.values() if v > 0) or 1.0
        return max(0.0, min(1.0, num / den))


@dataclass
class Outcome:
    state: OutcomeState = OutcomeState.UNKNOWN
    confidence: float = 0.0
    vector: OutcomeVector = field(default_factory=OutcomeVector)


@dataclass
class Consequence:
    type: ConsequenceType = ConsequenceType.NONE
    amount: float = 0.0
    currency: str = "USD"
    reason: str | None = None
    next_act_id: str | None = None  # the spawned economic act (recursion)


@dataclass
class EconomicStateObject:
    """The living record of one economic act (A -> B -> O -> C -> A_{t+1})."""

    promise: Promise
    authorization: Authorization
    economic_act_id: str = field(
        default_factory=lambda: f"EA_{uuid.uuid4().int % 10**8:08d}"
    )
    settlement: Settlement = field(default_factory=Settlement)
    observation: Observation = field(default_factory=Observation)
    outcome: Outcome = field(default_factory=Outcome)
    consequence: Consequence = field(default_factory=Consequence)
    causal_log: list[dict] = field(default_factory=list)
    parent_act_id: str | None = None  # set when spawned as a consequence

    def record(self, stage: str, detail: dict | None = None) -> None:
        """Append to the causal chain. Every mutation goes through here."""
        self.causal_log.append({"stage": stage, "at": time.time(), **(detail or {})})

    # ---- stage helpers (each writes the causal chain) ----
    def authorize(self) -> None:
        self.settlement.status = SettlementStatus.AUTHORIZED
        self.record("AUTHORITY", {"max_value": self.authorization.max_value})

    def settle(self, amount: float) -> None:
        self.settlement.amount = amount
        self.settlement.status = SettlementStatus.SETTLED
        self.settlement.settled_at = time.time()
        self.record("SETTLEMENT", {"amount": amount})

    def hold(self, amount: float) -> None:
        self.settlement.amount = amount
        self.settlement.status = SettlementStatus.HELD
        self.record("SETTLEMENT", {"amount": amount, "held": True})

    def observe(self, values: dict, source: str | None = None) -> None:
        self.observation.values.update(values)
        self.observation.observed_at = time.time()
        self.observation.source = source
        self.record("OBSERVED OUTCOME", {"values": values, "source": source})

    def classify(self, outcome: Outcome) -> None:
        self.outcome = outcome
        self.record(
            "OUTCOME CLASSIFICATION",
            {"state": outcome.state.value, "confidence": outcome.confidence},
        )

    def apply_consequence(self, consequence: Consequence) -> None:
        self.consequence = consequence
        self.record(
            "CONSEQUENCE",
            {"type": consequence.type.value, "amount": consequence.amount},
        )
        if consequence.next_act_id:
            self.record("CURRENT STATE", {"spawns": consequence.next_act_id})

    def causal_chain(self) -> list[str]:
        """The ordered stage names — the economic causality API view."""
        return [e["stage"] for e in self.causal_log]

    def to_dict(self) -> dict:
        return {
            "economic_act_id": self.economic_act_id,
            "parent_act_id": self.parent_act_id,
            "promise": {
                "type": self.promise.type,
                "conditions": self.promise.conditions,
                "deadline": self.promise.deadline,
                "terms": self.promise.terms,
            },
            "authorization": {
                "max_value": self.authorization.max_value,
                "currency": self.authorization.currency,
                "capability_id": self.authorization.capability_id,
            },
            "settlement": {
                "amount": self.settlement.amount,
                "status": self.settlement.status.value,
                "settled_at": self.settlement.settled_at,
            },
            "observation": {
                "values": self.observation.values,
                "observed_at": self.observation.observed_at,
                "source": self.observation.source,
            },
            "outcome": {
                "state": self.outcome.state.value,
                "confidence": self.outcome.confidence,
                "vector": vars(self.outcome.vector),
            },
            "consequence": {
                "type": self.consequence.type.value,
                "amount": self.consequence.amount,
                "reason": self.consequence.reason,
                "next_act_id": self.consequence.next_act_id,
            },
            "causal_chain": self.causal_chain(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
