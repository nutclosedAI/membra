"""Demo: archetype discovery over the economic outcome graph.

Four KNOWN archetypes emit acts through the runtime (hidden impls);
a fingerprint bank learned on train seeds classifies held-out seeds,
and the per-archetype consequence distribution plays
P(O_{t+t} | EA_t, Phi_t, S_t).

Run: python examples/archetype_demo.py
"""

from membra_sdk.economy.archetypes import (
    AGENT_ZOO,
    build_archetype_bank,
    evaluate_archetypes,
    fingerprint_series,
    run_series,
)


def main() -> None:
    print("BRO economic archetype discovery")
    print("=" * 56)

    # one sample fingerprint per archetype for intuition
    for cls in AGENT_ZOO:
        acts = run_series(cls(0), n_acts=30, seed=0)
        fp = fingerprint_series(acts)
        top = sorted(fp.values.items(), key=lambda kv: -abs(kv[1]))[:4]
        sig = ", ".join(f"{k}={v:.2f}" for k, v in top)
        print(f"{cls.name:22s} Phi: {sig}")

    print("\nH: bank on seeds 0-5, eval on seeds 100,200 (OOS)")
    bank = build_archetype_bank(seeds_per_agent=6)
    report = evaluate_archetypes(bank)

    print(f"OOS archetype accuracy: {report.accuracy:.2f}")
    print("\nconfusion (true -> predicted):")
    for true, row in report.confusion.items():
        print(f"  {true:22s} {row}")

    print("\nP(consequence | archetype) -- measured next-state model:")
    for name, dist in report.conditional.items():
        print(f"  {name:22s} {dist}")

    print(
        "\nG_{t+1}: the bank now carries the outcome-history substrate --\n"
        "D = {(P,E,O,C)} rows accumulate on the graph for re-mining."
    )


if __name__ == "__main__":
    main()
