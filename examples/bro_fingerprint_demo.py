#!/usr/bin/env python3
"""
Example: BRO temporal fingerprint experiment.

Runs the controlled benchmark:

    KNOWN ALGORITHM -> GENERATED BEHAVIOR -> HIDDEN -> Phi -> CLASSIFY
    -> OUT-OF-SAMPLE -> ADVERSARIAL ADAPTATION -> RE-FINGERPRINT

Six known algorithms emit order-flow event streams on a shared price
path; BRO sees only the stream. Then jittered/mimicking variants probe
where the fingerprint breaks, and a robust re-fingerprint measures what
the reorganized representation recovers.

Usage:
    python3 examples/bro_fingerprint_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from membra_sdk.bro import run_experiment
from membra_sdk.bro.recurrence import EvalResult


def show_confusion(title: str, res: EvalResult) -> None:
    labels = sorted(res.confusion)
    cols = sorted({p for row in res.confusion.values() for p in row})
    print(f"  {title}  (accuracy {res.accuracy:.2f})")
    print(f"      {'':<26}" + "".join(f"{c[:9]:>10}" for c in cols))
    for true in labels:
        row = res.confusion[true]
        print(f"      {true:<26}" + "".join(f"{row.get(c, 0):>10}" for c in cols))
    print()


def main() -> None:
    print("=" * 70)
    print("  BRO — temporal fingerprint benchmark")
    print("  hidden algorithm <- observable event stream")
    print("=" * 70)
    print()
    rep = run_experiment()

    print("STAGE 1 — known algorithms, out-of-sample seeds")
    show_confusion("confusion (rows=true, cols=predicted)", rep.base)

    print("STAGE 2 — adversarial variants (jittered cadence/sizes, mimic)")
    show_confusion("confusion", rep.adversarial)

    print("STAGE 3 — bank re-organized: adversarial runs folded into H")
    show_confusion("confusion", rep.refingerprinted)

    print("=" * 70)
    print("  SUMMARY")
    print(f"    base OOS accuracy        {rep.base.accuracy:.2f}")
    print(f"    adversarial accuracy     {rep.adversarial.accuracy:.2f}")
    print(f"    re-organized bank        {rep.refingerprinted.accuracy:.2f}")
    for n in rep.notes:
        print(f"    - {n}")
    print("=" * 70)


if __name__ == "__main__":
    main()
