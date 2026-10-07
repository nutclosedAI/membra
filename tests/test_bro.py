#!/usr/bin/env python3
"""Test suite for BRO: agent zoo, fingerprints, recurrence, experiment."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from membra_sdk.bro import (
    adversarial_zoo,
    base_zoo,
    run_experiment,
    simulate,
)
from membra_sdk.bro.fingerprint import FEATURE_NAMES, fingerprint
from membra_sdk.bro.recurrence import build_bank, evaluate


def test_zoo_emits_distinct_streams():
    """TWAP and market maker streams differ in cancel rate — sanity."""
    twap_ep = simulate(base_zoo()["twap"], seed=1)
    mm_ep = simulate(base_zoo()["market_maker"], seed=1)
    twap_cancels = sum(1 for e in twap_ep.events if e[1] == "cancel")
    mm_cancels = sum(1 for e in mm_ep.events if e[1] == "cancel")
    assert twap_cancels == 0 and mm_cancels > 0
    print("✅ zoo emits distinct streams (maker cancels, twap doesn't)")


def test_twap_cadence_fingerprint():
    """Fixed-interval slicing -> near-zero IAT entropy and CV."""
    fp = fingerprint(simulate(base_zoo()["twap"], seed=2))
    assert fp.values["iat_cv"] < 0.1, fp.values
    assert fp.values["iat_entropy"] < 0.3, fp.values
    print("✅ twap fingerprint: regular cadence detected")


def test_gd_size_decay_fingerprint():
    """Gradient descent shrinks its steps -> high size skew + max/med."""
    fp = fingerprint(simulate(base_zoo()["gradient_descent"], seed=3))
    assert fp.values["size_max_med"] > 1.5
    assert fp.values["size_skew"] > 0.3
    print("✅ gradient descent fingerprint: geometric size decay detected")


def test_fingerprint_has_all_features():
    ep = simulate(base_zoo()["noise"], seed=4)
    fp = fingerprint(ep)
    assert all(k in fp.values for k in FEATURE_NAMES)
    print("✅ fingerprint covers all features")


def test_bank_classifies_oos():
    """Bank built on seeds 0-11 should classify seeds 100-107 above chance."""
    known = base_zoo()
    bank = build_bank(known, range(12), n_ticks=160)
    eps = [
        simulate(a, n_ticks=160, seed=s)
        for a in known.values()
        for s in range(100, 108)
    ]
    res = evaluate(bank, eps, k=3)
    assert res.accuracy > 0.5, res.accuracy
    print(f"✅ OOS classification accuracy {res.accuracy:.2f} (> chance)")


def test_experiment_runs_all_stages():
    rep = run_experiment(n_ticks=160)
    assert rep.base.accuracy > 0.5
    assert 0.0 <= rep.adversarial.accuracy <= 1.0
    assert 0.0 <= rep.refingerprinted.accuracy <= 1.0
    print(
        f"✅ experiment: base {rep.base.accuracy:.2f} "
        f"-> adv {rep.adversarial.accuracy:.2f} "
        f"-> re-fp {rep.refingerprinted.accuracy:.2f}"
    )


def test_adversarial_zoo_maps_to_base():
    """Every adversarial agent resolves to a known base algorithm."""
    from membra_sdk.bro.agents import ZOO
    from membra_sdk.bro.experiment import _base_of

    for name, agent in adversarial_zoo().items():
        base = _base_of(agent)
        assert base in ZOO, f"{name} -> {base}"
    print("✅ adversarial agents resolve to base algorithms")


if __name__ == "__main__":
    print("=" * 60)
    print("  BRO TEMPORAL FINGERPRINT TESTS")
    print("=" * 60)
    print()

    test_zoo_emits_distinct_streams()
    test_twap_cadence_fingerprint()
    test_gd_size_decay_fingerprint()
    test_fingerprint_has_all_features()
    test_bank_classifies_oos()
    test_experiment_runs_all_stages()
    test_adversarial_zoo_maps_to_base()

    print()
    print("=" * 60)
    print("  ALL TESTS PASSED")
    print("=" * 60)
