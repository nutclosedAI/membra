"""BRO economy demo — the $100-for-6pm-delivery scenario, end to end.

    INTENT -> OBLIGATION -> AUTHORITY -> SETTLEMENT
        -> OBSERVATION -> OUTCOME -> CONSEQUENCE -> ACT 2 -> ...

Shows: a Capability grant constrains the agent; settlement is not
terminal; the late delivery evaluates PARTIALLY_FULFILLED; a
COMPENSATION consequence spawns the next economic act; the causal
chain stays legible throughout.

Usage:
    python examples/economy_demo.py
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
    transition,
)
from membra_sdk.economy.capability import CapabilityError


def show(label: str, text: str) -> None:
    print(f"  {label:<18} {text}")


def main() -> None:
    print("=" * 72)
    print("  BRO ECONOMY — outcome transition infrastructure")
    print("  S_t != FINAL: settlement is one state in the loop")
    print("=" * 72)

    g = EconomicGraph()
    policy = Policy(min_confidence=0.5)

    # --- Capability: constrained economic agency for the agent -------
    cap = Capability(
        budget=100.0,
        max_exposure=100.0,
        permitted_acts=["DELIVERY"],
        success_rule="contract #81",
        expires_at=time.time() + 24 * 3600,
    )
    print("\nCAPABILITY")
    show(
        "grant",
        f"budget ${cap.budget}  max_exposure ${cap.max_exposure}  acts={cap.permitted_acts}",
    )
    show("rules", "evidence + outcome check required; expiry 24h; revocation immediate")

    # over-limit is refused
    try:
        cap.authorize("DELIVERY", 150.0)
    except CapabilityError as e:
        show("rejected", f"$150 -> {e}")

    # --- ACT 1: the delivery promise ---------------------------------
    deadline = time.time() - 20 * 60  # 6pm was 20 minutes ago
    auth = cap.authorize("DELIVERY", 100.0)
    act = EconomicStateObject(
        promise=Promise(
            type="DELIVERY",
            conditions=["item_received", "before_deadline"],
            deadline=deadline,
            terms={"price": 100.0, "service": "contract #81"},
        ),
        authorization=Authorization(**auth),
    )
    act.record("INTENT", {"prompt": "deliver item by 6pm for $100"})
    act.record(
        "POLICY", {"policy_id": policy.policy_id, "success_rule": cap.success_rule}
    )
    g.add(act)

    act.authorize()
    act.settle(100.0)
    print(
        f"\nACT 1  {act.economic_act_id}  promise={act.promise.type}  settled=${act.settlement.amount}"
    )

    # --- reality: item arrived, 20 minutes late ----------------------
    act.observe(
        {"item_received": True, "before_deadline": False},
        source="courier-tracking:v2",
    )
    show("observed", str(act.observation.values))

    act2, spawned = transition(act, policy)
    v = act2.outcome.vector
    print("\nOUTCOME")
    show("state", f"{act2.outcome.state.value}  (confidence {act2.outcome.confidence})")
    show(
        "vector",
        f"Q={v.quality} T={v.timeliness} C={v.completeness} R={v.reliability} D={v.deviation} U={v.uncertainty}",
    )
    show(
        "consequence",
        f"{act2.consequence.type.value} ${act2.consequence.amount}  ->  {act2.consequence.next_act_id}",
    )

    # --- ACT 2: the compensation act, born of the outcome ------------
    if spawned is not None:
        g.add(spawned)
        print(
            f"\nACT 2  {spawned.economic_act_id}  spawned by consequence of {act.economic_act_id}"
        )
        spawned.authorize()
        spawned.settle(spawned.authorization.max_value)
        spawned.observe({"executed": True}, source="payout-rail")
        spawned, _ = transition(spawned, policy)
        show(
            "outcome",
            f"{spawned.outcome.state.value} -> consequence {spawned.consequence.type.value}",
        )

    # --- the killer view: causal chain -------------------------------
    print("\nCAUSAL CHAIN  (GET /acts/:id/causal-chain)")
    for stage in g.causal_chain(act.economic_act_id)["stages"]:
        print(f"    {stage}")

    print("\nGRAPH SUMMARY")
    s = g.summary()
    show("acts", str(s["acts"]))
    show("outcomes", str(s["by_outcome"]))
    show("settled", f"${s['total_settled']}  consequences ${s['total_consequences']}")

    print("\nDATASET  D = {(P_i, E_i, O_i, C_i)}  (promise vs reality)")
    for row in g.outcome_dataset():
        p, o, c = row["promise"], row["outcome"], row["consequence"]
        print(
            f"    {row['act']}  {p['type']:<14} -> {o['state']:<19} -> {c['type']} ${c['amount']}"
        )

    print("\n" + "=" * 72)


if __name__ == "__main__":
    main()
