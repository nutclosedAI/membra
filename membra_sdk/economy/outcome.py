"""Outcome evaluation — how reality diverged from the economic promise.

Not SUCCESS/FAILURE — a continuous vector O = (Q, T, C, R, D, U).
Payment becomes f(Q, T, C, R) rather than f(completed).

`evaluate_outcome(eso)` reads the promise conditions and the observed
values, scores each dimension, and classifies the act. Every condition
expects a truthy/float observation under the same key; numeric
conditions may also be partially satisfied (0 < value < 1).

Confidence reflects evidence coverage: unknown conditions lower it;
an explicit `observation.source` raises reliability.
"""

from __future__ import annotations

from .state import (
    EconomicStateObject,
    Observation,
    Outcome,
    OutcomeState,
    OutcomeVector,
    Promise,
)


def _condition_score(cond: str, obs: Observation) -> float | None:
    """Score one condition 0..1, or None if it was never observed."""
    if cond not in obs.values:
        return None
    v = obs.values[cond]
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return max(0.0, min(1.0, float(v)))
    return 1.0 if v else 0.0


def evaluate_outcome(
    eso: EconomicStateObject,
    *,
    quality_hint: float | None = None,
    reliability_hint: float = 0.7,
    late_decay_per_hour: float = 0.15,
) -> Outcome:
    """Evaluate the act's observed outcome against its promise.

    quality_hint: external 0..1 quality signal (e.g. inspection score);
        defaults to the all-conditions score when not supplied.
    reliability_hint: base reliability of the evidence source.
    late_decay_per_hour: timeliness decay slope past deadline.
    """
    promise: Promise = eso.promise
    obs: Observation = eso.observation

    scores = {c: _condition_score(c, obs) for c in promise.conditions}
    observed = [s for s in scores.values() if s is not None]
    missing = [c for c, s in scores.items() if s is None]

    completeness = (
        sum(observed) / len(promise.conditions) if promise.conditions else 1.0
    )
    coverage = len(observed) / len(promise.conditions) if promise.conditions else 0.0

    # timeliness: deadline missed -> decayed by observed lateness
    if promise.deadline is None:
        timeliness = 1.0
    else:
        late_hours = max(0.0, (obs.observed_at - promise.deadline) / 3600.0)
        met = obs.values.get("before_deadline", obs.values.get("deadline_met"))
        if met is False and late_hours == 0.0:
            late_hours = 1.0  # flagged late but no timestamp detail
        timeliness = (
            1.0 if met is True else max(0.0, 1.0 - late_decay_per_hour * late_hours)
        )

    quality = quality_hint if quality_hint is not None else completeness
    reliability = reliability_hint + (0.2 if obs.source else 0.0)
    reliability = min(1.0, reliability)
    deviation = 1.0 - completeness
    uncertainty = 1.0 - (coverage * (0.6 + 0.4 * reliability))
    confidence = 1.0 - uncertainty

    if not promise.conditions or missing and not observed:
        state = OutcomeState.UNKNOWN
    elif completeness >= 0.999:
        state = OutcomeState.FULFILLED
    elif completeness <= 0.001:
        state = OutcomeState.FAILED
    else:
        state = OutcomeState.PARTIALLY_FULFILLED

    return Outcome(
        state=state,
        confidence=round(confidence, 4),
        vector=OutcomeVector(
            quality=round(quality, 4),
            timeliness=round(timeliness, 4),
            completeness=round(completeness, 4),
            reliability=round(reliability, 4),
            deviation=round(deviation, 4),
            uncertainty=round(uncertainty, 4),
        ),
    )
