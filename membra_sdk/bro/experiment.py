"""BRO experiment — the full controlled loop:

    KNOWN ALGORITHM -> GENERATED BEHAVIOR -> HIDDEN FROM BRO
      -> TEMPORAL FINGERPRINT -> ALGORITHM CLASSIFICATION
      -> OUT-OF-SAMPLE TEST -> ADVERSARIAL ADAPTATION -> RE-FINGERPRINT

Stage 1 (base):       bank fingerprints per known algorithm, classify
                      held-out episodes. Score = algorithm identity.
Stage 2 (adversarial): jittered + mimic variants — same algorithms with
                      parameters noised or signatures blended. Measures
                      where Phi breaks.
Stage 3 (re-fingerprint): rebuild the bank on robust (rank/shape)
                      features and re-score the adversarial set — the
                      representation reorganizes, G_{t+1}.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .agents import (
    ZOO,
    Agent,
    Episode,
    adversarial_zoo,
    base_zoo,
    simulate,
)
from .fingerprint import fingerprint
from .recurrence import Bank, EvalResult, build_bank, evaluate

TRAIN_SEEDS = range(12)
OOS_SEEDS = range(100, 112)
ADV_SEEDS = range(200, 208)


def _base_of(agent: Agent) -> str:
    """The known algorithm an (adversarial) agent is an instance of."""
    for cls in type(agent).mro():
        if cls.__name__ != agent.name and getattr(cls, "name", None) in ZOO:
            return cls.name
    return agent.name


def _episodes(agents: dict[str, Agent], seeds: range, n_ticks: int) -> list[Episode]:
    return [
        simulate(a, n_ticks=n_ticks, seed=s) for a in agents.values() for s in seeds
    ]


def _evaluate_as_base(
    bank: Bank, agents: dict[str, Agent], seeds: range, n_ticks: int, robust: bool
) -> EvalResult:
    """Score adversarial episodes against their base-algorithm labels."""
    eps = _episodes(agents, seeds, n_ticks)
    for ep in eps:
        ep.agent_name = _base_of_lookup(agents, ep.agent_name)
    return evaluate(bank, eps, robust=robust)


def _base_of_lookup(agents: dict[str, Agent], name: str) -> str:
    return _base_of(agents[name])


@dataclass
class ExperimentReport:
    """Numbers for the three stages + the narratives BRO keeps."""

    base: EvalResult
    adversarial: EvalResult
    refingerprinted: EvalResult
    notes: list[str] = field(default_factory=list)


def run_experiment(n_ticks: int = 240, k: int = 3) -> ExperimentReport:
    """Run all three stages; return the report."""
    known = base_zoo()
    adv = adversarial_zoo()
    notes: list[str] = []

    # Stage 1 — bank on known algorithms, score OOS seeds.
    bank = build_bank(known, TRAIN_SEEDS, n_ticks=n_ticks)
    base_eps = _episodes(known, OOS_SEEDS, n_ticks)
    base = evaluate(bank, base_eps, k=k)

    # Stage 2 — adversarial variants classified against the same bank.
    adversarial = _evaluate_as_base(bank, adv, ADV_SEEDS, n_ticks, robust=False)
    drop = base.accuracy - adversarial.accuracy
    if drop > 0:
        notes.append(
            f"adversarial parameter jitter cut accuracy "
            f"{base.accuracy:.2f} -> {adversarial.accuracy:.2f} (-{drop:.2f})"
        )

    # Stage 3 — re-organize: fold observed adversarial behavior back into
    # the bank (G_{t+1}) — the bank updates, not just the features.
    adv_train_seeds = range(ADV_SEEDS.start, ADV_SEEDS.start + 4)
    adv_eval_seeds = range(ADV_SEEDS.start + 4, ADV_SEEDS.stop)
    augmented = build_bank(known, TRAIN_SEEDS, n_ticks=n_ticks)
    for agent in adv.values():
        for seed in adv_train_seeds:
            ep = simulate(agent, n_ticks=n_ticks, seed=seed)
            augmented.add(_base_of(agent), seed, fingerprint(ep))
    refingerprinted = evaluate(
        augmented,
        _labeled_as_base(adv, adv_eval_seeds, n_ticks),
        k=k,
    )
    same_seeds_baseline = evaluate(
        bank,
        _labeled_as_base(adv, adv_eval_seeds, n_ticks),
        k=k,
    )
    recovered = refingerprinted.accuracy - same_seeds_baseline.accuracy
    if recovered > 0:
        notes.append(
            f"bank augmentation recovered +{recovered:.2f} on held-out "
            f"adversarial seeds ({same_seeds_baseline.accuracy:.2f} -> "
            f"{refingerprinted.accuracy:.2f})"
        )

    return ExperimentReport(base, adversarial, refingerprinted, notes)


def _robust_bank(known: dict[str, Agent], n_ticks: int) -> Bank:
    return build_bank(known, TRAIN_SEEDS, n_ticks=n_ticks, robust=True)


def _labeled_as_base(
    agents: dict[str, Agent], seeds: range, n_ticks: int
) -> list[Episode]:
    eps = _episodes(agents, seeds, n_ticks)
    for ep in eps:
        ep.agent_name = _base_of_lookup(agents, ep.agent_name)
    return eps
