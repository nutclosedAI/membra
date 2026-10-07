"""BRO economy — Outcome Transition Infrastructure.

Clearing asks: should this obligation be allowed to settle?
This layer asks the harder next question: what does the settled
economic act mean after the world continues changing?

    INTENT -> OBLIGATION -> EVIDENCE -> CLEARING -> AUTHORIZATION
        -> SETTLEMENT -> OUTCOME OBSERVATION -> OUTCOME EVALUATION
        -> STATE TRANSITION -> NEW ECONOMIC CONSEQUENCE -> (repeat)

An economic act is a stateful process, not a terminal event:

    X_{t+1} = F(X_t, E_t, O_t, P_t)

where X is the economic state, E new evidence, O the evaluated
outcome, and P the governing policy. See docs/ECONOMIC_STATE_GRAPH.md.
"""

from .api import make_server, serve
from .archetypes import (
    AGENT_ZOO,
    build_archetype_bank,
    conditional_outcomes,
    evaluate_archetypes,
    fingerprint_series,
    run_series,
)
from .capability import Capability
from .graph import EconomicGraph
from .outcome import OutcomeVector, evaluate_outcome
from .state import (
    Authorization,
    Consequence,
    EconomicStateObject,
    Observation,
    Outcome,
    Promise,
    Settlement,
    SettlementStatus,
)
from .transitions import Policy, transition

__all__ = [
    "AGENT_ZOO",
    "Authorization",
    "Capability",
    "Consequence",
    "EconomicGraph",
    "EconomicStateObject",
    "Observation",
    "Outcome",
    "OutcomeVector",
    "Policy",
    "Promise",
    "Settlement",
    "SettlementStatus",
    "build_archetype_bank",
    "conditional_outcomes",
    "evaluate_archetypes",
    "evaluate_outcome",
    "fingerprint_series",
    "make_server",
    "run_series",
    "serve",
    "transition",
]
