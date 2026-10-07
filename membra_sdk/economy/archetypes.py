"""Archetype discovery — temporal fingerprints over economic outcomes.

The bridge: `membra_sdk.bro`'s fingerprint machinery applied to the
outcome graph. Synthetic economic agents with KNOWN outcome patterns
generate acts through the runtime; the fingerprint Φ over each series'
outcome vectors + consequence cadence is computed blind, and a labeled
bank classifies which *archetype* produced a new series — out-of-sample.

P(O_{t+τ} | EA_t, Φ_t, S_t): for each archetype the bank also carries
the empirical distribution of its consequence types — the measured
probabilistic outcome model, not a guaranteed prediction.

Agent zoo (observable signature -> expected Φ):
  ReliableMerchant   -> all FULFILLED, T~1, tiny D, no consequences
  ChronicLateShipper -> PARTIALLY_FULFILLED, low T, COMPENSATION stream
  QualityDrifter     -> declining Q over time, deviation trending up
  FlakyEvidence      -> high U, deferred transitions, sparse confidence
"""

from __future__ import annotations

import random
import time
from collections import Counter
from dataclasses import dataclass

from ..bro.fingerprint import Fingerprint
from ..bro.recurrence import Bank
from .state import Authorization, EconomicStateObject, Promise
from .transitions import Policy, transition

# ---------------------------------------------------------------- agent zoo


class EconomicAgent:
    """Base: emits acts through the runtime with a characteristic
    outcome pattern. Implementation hidden from the fingerprint."""

    name: str = "agent"

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def make_act(self, i: int) -> EconomicStateObject:
        deadline = time.time() + self.rng.choice([-3600.0, -600.0, 3600.0])
        return EconomicStateObject(
            promise=Promise(
                type="DELIVERY",
                conditions=["item_received", "before_deadline"],
                deadline=deadline,
            ),
            authorization=Authorization(max_value=100.0, currency="USD"),
        )

    def reality(self, i: int) -> tuple[dict, float | None, float]:
        """(observations, quality_hint, observed_at_offset_hours)."""
        raise NotImplementedError


class ReliableMerchant(EconomicAgent):
    name = "reliable_merchant"

    def reality(self, i):
        return {"item_received": True, "before_deadline": True}, 0.95, -1.0


class ChronicLateShipper(EconomicAgent):
    name = "chronic_late_shipper"

    def reality(self, i):
        late = self.rng.random() < 0.8
        return (
            {"item_received": True, "before_deadline": not late},
            0.9,
            self.rng.uniform(1.5, 5.0) if late else -0.5,
        )


class QualityDrifter(EconomicAgent):
    name = "quality_drifter"

    def reality(self, i):
        drift = min(1.0, i / 40.0)  # quality erodes across the series
        ok = self.rng.random() > drift * 0.7
        return (
            {"item_received": ok, "before_deadline": self.rng.random() > 0.3},
            0.95 - 0.6 * drift,
            self.rng.uniform(-1.0, 3.0),
        )


class FlakyEvidence(EconomicAgent):
    name = "flaky_evidence"

    def reality(self, i):
        obs: dict = {}
        if self.rng.random() < 0.7:
            obs["item_received"] = self.rng.random() < 0.85
        if self.rng.random() < 0.4:
            obs["before_deadline"] = self.rng.random() < 0.7
        return obs, None, self.rng.uniform(-1.0, 2.0)


AGENT_ZOO = [ReliableMerchant, ChronicLateShipper, QualityDrifter, FlakyEvidence]


def run_series(
    agent: EconomicAgent, n_acts: int = 30, seed: int = 0
) -> list[EconomicStateObject]:
    """Simulate one agent's history through the runtime — acts evaluated
    and transitioned under default policy. Each act runs the full loop:
    INTENT -> AUTHORITY -> SETTLEMENT -> OBSERVED -> OUTCOME -> CONSEQUENCE."""
    agent.rng = random.Random(seed)
    policy = Policy()
    acts = []
    for i in range(n_acts):
        act = agent.make_act(i)
        act.record("INTENT", {"agent": agent.name})
        act.authorize()
        act.settle(act.authorization.max_value)
        obs, qh, late_h = agent.reality(i)
        act.observe(obs, source="sim")
        # honor the simulated observation time (lateness drives timeliness)
        if act.promise.deadline is not None and late_h:
            act.observation.observed_at = act.promise.deadline + late_h * 3600.0
        _, spawned = transition(act, policy, quality_hint=qh)
        if spawned is not None:
            act.consequence.next_act_id = spawned.economic_act_id
        acts.append(act)
    return acts


# ---------------------------------------------------------------- Φ

FEATURE_NAMES = [
    "fulfilled_share",
    "partial_share",
    "failed_share",
    "unknown_share",
    "q_mean",
    "t_mean",
    "c_mean",
    "r_mean",
    "d_mean",
    "u_mean",
    "confidence_mean",
    "consequence_rate",
    "comp_share",
    "dispute_share",
    "settled_mean",
    "consequence_amount_mean",
    "q_trend",  # slope of quality across the series
    "d_trend",
]


def fingerprint_series(acts: list[EconomicStateObject]) -> Fingerprint:
    """Φ over one agent's outcome series — blind to the agent code."""

    def mean(xs) -> float:
        xs = list(xs)
        return sum(xs) / len(xs) if xs else 0.0

    n = len(acts) or 1
    states = Counter(a.outcome.state.value for a in acts)
    vecs = [a.outcome.vector for a in acts]
    cons = [a.consequence for a in acts]
    cons_types = Counter(c.type.value for c in cons)
    qs = [v.quality for v in vecs]
    ds = [v.deviation for v in vecs]
    xs = list(range(len(qs)))

    def trend(ys: list[float]) -> float:
        if len(ys) < 2:
            return 0.0
        mx, my = sum(xs) / len(ys), sum(ys) / len(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = sum((x - mx) ** 2 for x in xs) or 1.0
        return num / den

    vals = {
        "fulfilled_share": states.get("FULFILLED", 0) / n,
        "partial_share": states.get("PARTIALLY_FULFILLED", 0) / n,
        "failed_share": states.get("FAILED", 0) / n,
        "unknown_share": states.get("UNKNOWN", 0) / n,
        "q_mean": mean(v.quality for v in vecs),
        "t_mean": mean(v.timeliness for v in vecs),
        "c_mean": mean(v.completeness for v in vecs),
        "r_mean": mean(v.reliability for v in vecs),
        "d_mean": mean(v.deviation for v in vecs),
        "u_mean": mean(v.uncertainty for v in vecs),
        "confidence_mean": mean(a.outcome.confidence for a in acts),
        "consequence_rate": mean(c.type.value != "NONE" for c in cons),
        "comp_share": cons_types.get("COMPENSATION", 0) / n,
        "dispute_share": cons_types.get("DISPUTE", 0) / n,
        "settled_mean": mean(a.settlement.amount for a in acts) / 100.0,
        "consequence_amount_mean": mean(c.amount for c in cons) / 100.0,
        "q_trend": trend(qs),
        "d_trend": trend(ds),
    }
    assert set(vals) == set(FEATURE_NAMES), "feature drift"
    return Fingerprint(values=vals)


# ---------------------------------------------------------------- H + eval


@dataclass
class ArchetypeReport:
    """OOS classification result + the per-archetype next-state model."""

    accuracy: float
    confusion: dict[str, dict[str, int]]
    per_class: dict[str, float]
    conditional: dict[str, dict[str, float]]  # archetype -> P(consequence)


def build_archetype_bank(seeds_per_agent: int = 6, n_acts: int = 30) -> Bank:
    """H: bank fingerprints from runs whose archetype is KNOWN."""
    bank = Bank()
    for cls in AGENT_ZOO:
        for seed in range(seeds_per_agent):
            acts = run_series(cls(seed), n_acts=n_acts, seed=seed)
            bank.add(cls.name, seed, fingerprint_series(acts))
    return bank


def conditional_outcomes(bank_seeds: int = 6, n_acts: int = 30) -> dict:
    """P(consequence | archetype) — empirical next-state distribution,
    the measured outcome model P(O_{t+τ} | EA_t, Φ_t, S_t)."""
    dist = {}
    for cls in AGENT_ZOO:
        counts: Counter = Counter()
        total = 0
        for seed in range(bank_seeds):
            for act in run_series(cls(seed), n_acts=n_acts, seed=seed):
                counts[act.consequence.type.value] += 1
                total += 1
        dist[cls.name] = {
            k: round(v / total, 3) for k, v in counts.most_common() if total
        }
    return dist


def evaluate_archetypes(
    bank: Bank,
    seeds: tuple[int, ...] = (100, 200),
    n_acts: int = 30,
    k: int = 3,
) -> ArchetypeReport:
    """OOS classification: fresh seeds, true label = archetype name."""
    confusion: dict[str, dict[str, int]] = {}
    correct = 0
    total = 0
    for cls in AGENT_ZOO:
        for seed in seeds:
            fp = fingerprint_series(run_series(cls(seed), n_acts=n_acts, seed=seed))
            pred, _share = bank.classify(fp, k=k)
            confusion.setdefault(cls.name, {}).setdefault(pred, 0)
            confusion[cls.name][pred] += 1
            correct += pred == cls.name
            total += 1
    per_class = {
        name: row.get(name, 0) / max(1, sum(row.values()))
        for name, row in confusion.items()
    }
    return ArchetypeReport(
        accuracy=correct / max(1, total),
        confusion=confusion,
        per_class=per_class,
        conditional=conditional_outcomes(),
    )
