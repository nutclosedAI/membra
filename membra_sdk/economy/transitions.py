"""State transitions — X_{t+1} = F(X_t, E_t, O_t, P_t).

The transition function turns an evaluated outcome into a new economic
state and, when warranted, a consequence that *spawns the next economic
act* — the recursion A -> B -> O -> C -> A_{t+1}.

Default rules (each is a Policy knob, not hardcoded law):

- FULFILLED            -> no consequence; HELD funds RELEASED in full
- PARTIALLY_FULFILLED  -> if SETTLED: COMPENSATION = settled * deviation
                          * compensation_rate, spawning a child act
                          if HELD: PARTIAL_RELEASE of
                          amount * completeness, remainder RETURNED
- FAILED               -> if SETTLED: DISPUTE + REFUND claim
                          if HELD: RETURNED in full
- UNKNOWN              -> nothing yet; the act stays open for evidence
"""

from __future__ import annotations

from dataclasses import dataclass

from .outcome import evaluate_outcome
from .state import (
    Authorization,
    Consequence,
    ConsequenceType,
    EconomicStateObject,
    OutcomeState,
    Promise,
    SettlementStatus,
)


@dataclass
class Policy:
    """The P_t in X_{t+1} = F(X_t, E_t, O_t, P_t) — governance over
    which state transitions are permitted and how consequences size."""

    compensation_rate: float = 0.25  # damages fraction per unit of deviation
    auto_spawn_consequence_act: bool = True
    dispute_on_failure: bool = True
    min_confidence: float = 0.5  # below this, defer the transition
    policy_id: str = "default"


def _spawn(
    eso: EconomicStateObject,
    consequence_type: ConsequenceType,
    amount: float,
    reason: str,
) -> EconomicStateObject:
    """Create the child economic act the consequence generates
    (C -> A_{t+1}). Wired into the parent's consequence record."""
    child = EconomicStateObject(
        promise=Promise(
            type=consequence_type.value,
            conditions=["executed"],
            terms={"reason": reason},
        ),
        authorization=Authorization(
            max_value=amount,
            currency=eso.authorization.currency,
            authorized_by=f"consequence:{eso.economic_act_id}",
        ),
        parent_act_id=eso.economic_act_id,
    )
    child.record("INTENT", {"spawned_by": eso.economic_act_id, "reason": reason})
    child.record("POLICY", {"governs": consequence_type.value})
    return child


def transition(
    eso: EconomicStateObject,
    policy: Policy | None = None,
    **eval_kwargs: float | None,
) -> tuple[EconomicStateObject, EconomicStateObject | None]:
    """Run one transition step on an evaluated act.

    `eval_kwargs` forwards evaluator hints (quality_hint, etc.).

    Returns (updated_act, spawned_act_or_None). The caller records the
    spawned act into the graph — `eso` itself only links its id.
    """
    policy = policy or Policy()
    outcome = evaluate_outcome(eso, **eval_kwargs)
    eso.classify(outcome)

    if outcome.confidence < policy.min_confidence:
        eso.record(
            "POLICY",
            {"deferred": f"confidence {outcome.confidence} < {policy.min_confidence}"},
        )
        return eso, None

    state = outcome.state
    settled = eso.settlement
    spawned: EconomicStateObject | None = None

    if state == OutcomeState.FULFILLED:
        eso.apply_consequence(
            Consequence(type=ConsequenceType.NONE, reason="fulfilled")
        )
        if settled.status == SettlementStatus.HELD:
            settled.status = SettlementStatus.RELEASED
            eso.record("STATE TRANSITION", {"released": settled.amount})
    elif state == OutcomeState.PARTIALLY_FULFILLED:
        dev = outcome.vector.deviation
        if settled.status == SettlementStatus.HELD:
            released = round(settled.amount * outcome.vector.completeness, 2)
            returned = round(settled.amount - released, 2)
            settled.status = SettlementStatus.RELEASED
            cons = Consequence(
                type=ConsequenceType.PARTIAL_RELEASE,
                amount=released,
                currency=eso.authorization.currency,
                reason=f"partial: completeness {outcome.vector.completeness}",
            )
            eso.apply_consequence(cons)
            eso.record("STATE TRANSITION", {"released": released, "returned": returned})
        elif settled.status in (SettlementStatus.SETTLED, SettlementStatus.RELEASED):
            amount = round(settled.amount * dev * policy.compensation_rate, 2)
            cons = Consequence(
                type=ConsequenceType.COMPENSATION,
                amount=amount,
                currency=eso.authorization.currency,
                reason=f"deviation {dev} of ${settled.amount}",
            )
            if policy.auto_spawn_consequence_act and amount > 0:
                spawned = _spawn(
                    eso, ConsequenceType.COMPENSATION, amount, cons.reason or ""
                )
                cons.next_act_id = spawned.economic_act_id
            eso.apply_consequence(cons)
            eso.record("STATE TRANSITION", {"compensation": amount})
    elif state == OutcomeState.FAILED:
        if settled.status == SettlementStatus.HELD:
            settled.status = SettlementStatus.RETURNED
            eso.apply_consequence(
                Consequence(
                    type=ConsequenceType.REFUND,
                    amount=settled.amount,
                    currency=eso.authorization.currency,
                    reason="outcome failed",
                )
            )
            eso.record("STATE TRANSITION", {"returned": settled.amount})
        else:
            settled.status = SettlementStatus.DISPUTED
            cons = Consequence(
                type=(
                    ConsequenceType.DISPUTE
                    if policy.dispute_on_failure
                    else ConsequenceType.REFUND
                ),
                amount=settled.amount,
                currency=eso.authorization.currency,
                reason="outcome failed after settlement",
            )
            if policy.auto_spawn_consequence_act:
                spawned = _spawn(
                    eso, ConsequenceType.DISPUTE, settled.amount, "outcome failed"
                )
                cons.next_act_id = spawned.economic_act_id
            eso.apply_consequence(cons)
            eso.record("STATE TRANSITION", {"disputed": settled.amount})
    else:  # UNKNOWN
        eso.record("STATE TRANSITION", {"deferred": "outcome unknown"})

    return eso, spawned
