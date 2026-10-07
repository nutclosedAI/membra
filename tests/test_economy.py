"""Tests for membra_sdk.economy — the outcome transition runtime.

Run:  python tests/test_economy.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from membra_sdk.economy import (
    Authorization,
    Capability,
    EconomicGraph,
    EconomicStateObject,
    Policy,
    Promise,
    SettlementStatus,
    transition,
)
from membra_sdk.economy.capability import CapabilityError
from membra_sdk.economy.state import ConsequenceType, OutcomeState


def make_act(conditions=None, deadline=None):
    return EconomicStateObject(
        promise=Promise(
            type="DELIVERY",
            conditions=conditions or ["item_received"],
            deadline=deadline,
        ),
        authorization=Authorization(max_value=100.0, currency="USD"),
    )


def t_outcome_fulfilled():
    act = make_act(["item_received"])
    act.settle(100.0)
    act.observe({"item_received": True}, source="sensor")
    act, child = transition(act)
    assert act.outcome.state == OutcomeState.FULFILLED
    assert act.consequence.type == ConsequenceType.NONE and child is None
    print("  ✅ fulfilled outcome -> no consequence")


def t_outcome_partial_compensation():
    deadline = time.time() - 20 * 60
    act = make_act(["item_received", "before_deadline"], deadline=deadline)
    act.settle(100.0)
    act.observe({"item_received": True, "before_deadline": False}, source="sensor")
    act, child = transition(act)
    assert act.outcome.state == OutcomeState.PARTIALLY_FULFILLED
    assert act.consequence.type == ConsequenceType.COMPENSATION
    assert act.consequence.amount == 12.5, act.consequence.amount
    assert child is not None and child.parent_act_id == act.economic_act_id
    print("  ✅ partial outcome -> compensation consequence + spawned act")


def t_outcome_failed_dispute():
    act = make_act(["item_received"])
    act.settle(100.0)
    act.observe({"item_received": False}, source="sensor")
    act, child = transition(act)
    assert act.outcome.state == OutcomeState.FAILED
    assert act.settlement.status == SettlementStatus.DISPUTED
    assert act.consequence.type == ConsequenceType.DISPUTE
    assert child is not None and child.promise.type == "DISPUTE"
    print("  ✅ failed outcome -> dispute + spawned dispute act")


def t_held_partial_release():
    act = make_act(["item_received", "before_deadline"], deadline=time.time() - 1200)
    act.hold(100.0)
    act.observe({"item_received": True, "before_deadline": False}, source="sensor")
    act, _ = transition(act)
    assert act.settlement.status == SettlementStatus.RELEASED
    assert act.consequence.type == ConsequenceType.PARTIAL_RELEASE
    assert act.consequence.amount == 50.0  # completeness 0.5 * 100
    print("  ✅ held + partial -> partial release of completeness share")


def t_capability_gates():
    cap = Capability(budget=40.0, max_exposure=25.0, permitted_acts=["DELIVERY"])
    try:
        cap.authorize("DELIVERY", 30.0)
        raise AssertionError("over-exposure accepted")
    except CapabilityError:
        pass
    cap.authorize("DELIVERY", 25.0)
    try:
        cap.authorize("DELIVERY", 20.0)
        raise AssertionError("over-budget accepted")
    except CapabilityError:
        pass
    cap.revoke()
    try:
        cap.authorize("DELIVERY", 1.0)
        raise AssertionError("revoked capability still authorized")
    except CapabilityError:
        pass
    print("  ✅ capability gates exposure/budget/revocation")


def t_causal_chain_and_dataset():
    g = EconomicGraph()
    deadline = time.time() - 600
    act = make_act(["item_received", "before_deadline"], deadline=deadline)
    act.record("INTENT", {})
    act.record("POLICY", {})
    g.add(act)
    act.authorize()
    act.settle(100.0)
    act.observe({"item_received": True, "before_deadline": False})
    act, child = transition(act, Policy())
    g.add(child)
    chain = g.causal_chain(act.economic_act_id)["stages"]
    assert chain[:2] == ["INTENT", "POLICY"] and "SETTLEMENT" in chain
    assert (
        chain.index("OBSERVED OUTCOME")
        < chain.index("OUTCOME CLASSIFICATION")
        < chain.index("CONSEQUENCE")
    )
    ds = g.outcome_dataset()
    assert len(ds) == 2 and all("promise" in r and "outcome" in r for r in ds)
    print("  ✅ causal chain ordered + D = {(P,E,O,C)} export")


def t_policy_min_confidence_defers():
    act = make_act(["item_received", "before_deadline"], deadline=time.time() - 600)
    act.settle(100.0)
    # only one of two conditions observed -> coverage halves confidence
    act.observe({"item_received": True})
    act, child = transition(act, Policy(min_confidence=0.9))
    assert act.consequence.type == ConsequenceType.NONE and child is None
    assert any(e["stage"] == "POLICY" and "deferred" in e for e in act.causal_log)
    print("  ✅ low-confidence outcome defers the transition")


def main():
    print("=" * 60)
    print("  BRO ECONOMY — outcome transition runtime")
    print("=" * 60)
    for t in (
        t_outcome_fulfilled,
        t_outcome_partial_compensation,
        t_outcome_failed_dispute,
        t_held_partial_release,
        t_capability_gates,
        t_causal_chain_and_dataset,
        t_policy_min_confidence_defers,
    ):
        t()
    print("=" * 60)
    print("  ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
