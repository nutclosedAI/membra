"""BRO — temporal observation and reorganization machine.

    agents       synthetic market + a zoo of KNOWN algorithms
    fingerprint  Phi_t: event stream -> temporal feature vector
    recurrence   H(Phi): labeled bank + z-scored kNN classifier
    experiment   KNOWN -> BEHAVIOR -> HIDDEN -> Phi -> CLASSIFY
                 -> OOS -> ADVERSARIAL -> RE-Phi

The point is not prediction. It is whether temporal fingerprints of an
agent's observable behavior identify the hidden algorithm — and whether
the representation can reorganize itself when adversarial variants break
the first fingerprint.
"""

from .agents import Agent, Episode, adversarial_zoo, base_zoo, simulate
from .experiment import ExperimentReport, run_experiment
from .fingerprint import Fingerprint, fingerprint
from .recurrence import Bank, EvalResult, build_bank, evaluate

__all__ = [
    "Agent",
    "Bank",
    "Episode",
    "EvalResult",
    "ExperimentReport",
    "Fingerprint",
    "adversarial_zoo",
    "base_zoo",
    "build_bank",
    "evaluate",
    "fingerprint",
    "run_experiment",
    "simulate",
]
