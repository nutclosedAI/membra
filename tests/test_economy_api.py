"""Tests for the Outcome API + archetype layer."""

import json
import threading
import time
import urllib.request

from membra_sdk.economy.api import make_server
from membra_sdk.economy.archetypes import (
    AGENT_ZOO,
    build_archetype_bank,
    conditional_outcomes,
    evaluate_archetypes,
    fingerprint_series,
    run_series,
)
from membra_sdk.economy.graph import EconomicGraph


def _post(url, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def _get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url)) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


class _Server:
    def __enter__(self):
        self.server = make_server(EconomicGraph(), port=0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        time.sleep(0.05)
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *a):
        self.server.shutdown()


def test_api_full_lifecycle():
    """POST promise -> obligation -> observation -> evaluate ->
    transition -> causal-chain, end to end over real HTTP."""
    with _Server() as base:
        act = _post(
            f"{base}/promises",
            {
                "type": "DELIVERY",
                "conditions": ["item_received", "before_deadline"],
                "deadline": time.time() - 1200,  # 20 min ago
                "max_value": 100.0,
            },
        )
        aid = act["economic_act_id"]

        st = _post(f"{base}/obligations", {"act_id": aid, "max_value": 100.0})
        assert st["status"] == "SETTLED"

        _post(
            f"{base}/observations",
            {
                "act_id": aid,
                "values": {"item_received": True, "before_deadline": False},
            },
        )
        out = _post(f"{base}/outcomes/evaluate", {"act_id": aid, "quality_hint": 0.5})
        assert out["state"] == "PARTIALLY_FULFILLED"

        res = _post(f"{base}/state-transitions", {"act_id": aid})
        assert res["act"]["consequence"]["type"] == "COMPENSATION"
        assert res["spawned_act"] is not None

        chain = _get(f"{base}/acts/{aid}/causal-chain")
        assert "CONSEQUENCE" in chain["stages"]
        assert chain["children"] == [res["spawned_act"]]

        ds = _get(f"{base}/dataset")
        assert any(r["act"] == aid for r in ds["rows"])


def test_api_act_not_found():
    with _Server() as base:
        for route in ("outcomes/evaluate", "state-transitions", "observations"):
            res = _post(f"{base}/{route}", {"act_id": "EA_00000000"})
            assert res.get("error")


def test_archetypes_separate():
    """The four archetypes' fingerprints are distinguishable OOS."""
    bank = build_archetype_bank(seeds_per_agent=4, n_acts=20)
    report = evaluate_archetypes(bank, seeds=(500, 600), n_acts=20)
    assert report.accuracy >= 0.75, report.confusion
    for cls in AGENT_ZOO:
        assert cls.name in report.per_class


def test_archetype_fingerprint_features():
    """Late shippers look late; reliable merchants look clean."""
    late = fingerprint_series(run_series(AGENT_ZOO[1](7), n_acts=25, seed=7))
    good = fingerprint_series(run_series(AGENT_ZOO[0](7), n_acts=25, seed=7))
    assert late.values["partial_share"] > good.values["partial_share"]
    assert late.values["comp_share"] > good.values["comp_share"]
    assert good.values["fulfilled_share"] > late.values["fulfilled_share"]


def test_conditional_outcomes_model():
    """P(consequence|archetype): reliable ~ NONE, late ~ COMPENSATION."""
    cond = conditional_outcomes(bank_seeds=3, n_acts=20)
    reliable = cond["reliable_merchant"]
    late = cond["chronic_late_shipper"]
    assert reliable.get("NONE", 0) > reliable.get("COMPENSATION", 0)
    assert late.get("COMPENSATION", 0) > late.get("NONE", 0)


if __name__ == "__main__":
    test_api_full_lifecycle()
    test_api_act_not_found()
    test_archetypes_separate()
    test_archetype_fingerprint_features()
    test_conditional_outcomes_model()
    print("all economy-api tests passed")
