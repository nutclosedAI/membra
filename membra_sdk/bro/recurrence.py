"""BRO recurrence — H(Phi): the labeled fingerprint bank + classifier.

The bank stores fingerprints from runs whose algorithm is KNOWN. A hidden
episode is classified by k-nearest-neighbors in z-scored feature space —
each feature normalized by the bank's own mean/std, so no raw scale
dominates the distance.

The split is by seed: train episodes and test episodes come from disjoint
seeds, so the classifier never sees the realization it is scored on —
that is the out-of-sample leg of the loop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .agents import Agent, Episode, simulate
from .fingerprint import Fingerprint, fingerprint


@dataclass
class LabeledFingerprint:
    label: str
    seed: int
    fp: Fingerprint


@dataclass
class Bank:
    """H: the historical fingerprint bank."""

    rows: list[LabeledFingerprint] = field(default_factory=list)
    feature_names: list[str] = field(default_factory=list)

    def add(self, label: str, seed: int, fp: Fingerprint) -> None:
        if not self.feature_names:
            self.feature_names = sorted(fp.values)
        self.rows.append(LabeledFingerprint(label, seed, fp))

    def _zscore(self, fp: Fingerprint) -> list[float]:
        mus, sds = [], []
        for name in self.feature_names:
            col = [r.fp.values.get(name, 0.0) for r in self.rows]
            mu = sum(col) / len(col)
            sd = math.sqrt(sum((c - mu) ** 2 for c in col) / max(1, len(col) - 1))
            mus.append(mu)
            sds.append(sd if sd > 1e-12 else 1.0)
        vec = fp.vector(self.feature_names)
        return [(v - m) / s for v, m, s in zip(vec, mus, sds)]

    def classify(self, fp: Fingerprint, k: int = 3) -> tuple[str, dict[str, float]]:
        """kNN in z-scored space -> (predicted label, vote share)."""
        zq = self._zscore(fp)
        dists = []
        for row in self.rows:
            zr = self._zscore(row.fp)
            d = math.sqrt(sum((a - b) ** 2 for a, b in zip(zq, zr)))
            dists.append((d, row.label))
        dists.sort()
        votes: dict[str, int] = {}
        for _, label in dists[:k]:
            votes[label] = votes.get(label, 0) + 1
        total = sum(votes.values())
        share = {l: c / total for l, c in votes.items()}
        return max(votes, key=votes.get), share


@dataclass
class EvalResult:
    """Confusion matrix + accuracy for a labeled eval set."""

    accuracy: float
    confusion: dict[str, dict[str, int]]  # true -> predicted -> count
    per_class: dict[str, float]


def build_bank(
    agents: dict[str, Agent],
    seeds: range,
    n_ticks: int = 240,
    robust: bool = False,
) -> Bank:
    """Simulate every known algorithm across `seeds`; bank the fingerprints."""
    bank = Bank()
    for name, agent in agents.items():
        for seed in seeds:
            ep = simulate(agent, n_ticks=n_ticks, seed=seed)
            bank.add(name, seed, fingerprint(ep, robust=robust))
    return bank


def evaluate(
    bank: Bank,
    episodes: list[Episode],
    k: int = 3,
    robust: bool = False,
) -> EvalResult:
    """Classify each episode's fingerprint; return accuracy + confusion."""
    confusion: dict[str, dict[str, int]] = {}
    correct = 0
    for ep in episodes:
        pred, _share = bank.classify(fingerprint(ep, robust=robust), k=k)
        confusion.setdefault(ep.agent_name, {}).setdefault(pred, 0)
        confusion[ep.agent_name][pred] += 1
        correct += pred == ep.agent_name
    total = len(episodes)
    per_class = {
        name: row.get(name, 0) / max(1, sum(row.values()))
        for name, row in confusion.items()
    }
    return EvalResult(
        accuracy=correct / max(1, total), confusion=confusion, per_class=per_class
    )
