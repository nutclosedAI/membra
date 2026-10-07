"""Economic Outcome Graph — the accumulating machine-readable history
of economic promises versus observed outcomes.

Every act contributes PROMISE vs REALITY; the graph is where
D = {(P_i, E_i, O_i, C_i)} accumulates — the substrate for later
archetype discovery (temporal fingerprinting over outcome sequences)
and P(O_{t+τ} | EA_t, Φ_t, S_t).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import EconomicStateObject


@dataclass
class EconomicGraph:
    """Registry of economic acts plus their consequence edges."""

    acts: dict[str, EconomicStateObject] = field(default_factory=dict)

    def add(self, eso: EconomicStateObject) -> EconomicStateObject:
        self.acts[eso.economic_act_id] = eso
        return eso

    def get(self, act_id: str) -> EconomicStateObject | None:
        return self.acts.get(act_id)

    def causal_chain(self, act_id: str) -> dict:
        """GET /acts/:id/causal-chain — the full chain including the
        parent links that explain why this act exists at all."""
        eso = self.acts[act_id]
        chain = {
            "economic_act_id": act_id,
            "stages": eso.causal_chain(),
            "log": eso.causal_log,
            "parents": [],
        }
        pid = eso.parent_act_id
        while pid:
            parent = self.acts.get(pid)
            if parent is None:
                break
            chain["parents"].append(
                {
                    "economic_act_id": pid,
                    "outcome": parent.outcome.state.value,
                    "consequence": parent.consequence.type.value,
                    "stages": parent.causal_chain(),
                }
            )
            pid = parent.parent_act_id
        return chain

    def children_of(self, act_id: str) -> list[EconomicStateObject]:
        return [a for a in self.acts.values() if a.parent_act_id == act_id]

    def outcome_dataset(self) -> list[dict]:
        """D = {(P_i, E_i, O_i, C_i)} — promise/evidence/outcome/
        consequence tuples, the training/evaluation substrate."""
        rows = []
        for a in self.acts.values():
            rows.append(
                {
                    "act": a.economic_act_id,
                    "promise": {
                        "type": a.promise.type,
                        "conditions": a.promise.conditions,
                        "deadline": a.promise.deadline,
                    },
                    "evidence": {
                        "observed": a.observation.values,
                        "source": a.observation.source,
                    },
                    "outcome": {
                        "state": a.outcome.state.value,
                        "confidence": a.outcome.confidence,
                        "vector": vars(a.outcome.vector),
                    },
                    "consequence": {
                        "type": a.consequence.type.value,
                        "amount": a.consequence.amount,
                    },
                }
            )
        return rows

    def summary(self) -> dict:
        from collections import Counter

        states = Counter(a.outcome.state.value for a in self.acts.values())
        cons = Counter(a.consequence.type.value for a in self.acts.values())
        return {
            "acts": len(self.acts),
            "by_outcome": dict(states),
            "by_consequence": dict(cons),
            "total_settled": round(
                sum(a.settlement.amount for a in self.acts.values()), 2
            ),
            "total_consequences": round(
                sum(a.consequence.amount for a in self.acts.values()), 2
            ),
        }
