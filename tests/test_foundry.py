"""Unit and HTTP integration tests. Synthetic candles here are TEST FIXTURES ONLY."""

from __future__ import annotations

import copy
import json
import math
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from membra_sdk.foundry.api import make_server
from membra_sdk.foundry.benchmark import (
    Execution,
    Market,
    deflated_sharpe,
    simulate,
    target,
    tournament,
)
from membra_sdk.foundry.receipts import Issuer, open_commitment, verify_chain
from membra_sdk.foundry.registry import Principal, Registry
from membra_sdk.foundry.tfl import baseline, compile_tfl, descendants, digest


def fixture_market(n: int = 2400) -> Market:
    rows = []
    price = 100.0
    for i in range(n):
        closing = price * (1 + 0.0002 + math.sin(i / 50) * 0.001)
        rows.append(
            (
                i * 3600,
                min(price, closing) * 0.999,
                max(price, closing) * 1.001,
                price,
                closing,
                1_000_000.0,
            )
        )
        price = closing
    return Market(
        tuple(rows),
        {
            "source": "SYNTHETIC TEST FIXTURE",
            "instrument": "BTC-USD",
            "granularity": 3600,
        },
    )


def research_evidence() -> dict:
    return {
        "passed": True,
        "sources": ["https://arxiv.org/abs/1802.03042"],
        "novelty": "existing_method",
        "proof_status": "unproven",
        "limitations": ["test fixture; no novelty certification"],
    }


def adversary_evidence() -> dict:
    return {
        "passed": True,
        "checks": {
            k: True
            for k in ("costs", "leakage", "capacity", "regimes", "selection_bias")
        },
        "limitations": ["test fixture only"],
    }


class TFLTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        p = baseline()
        self.assertEqual(compile_tfl(p.spec()), p)
        self.assertEqual(compile_tfl(p.spec()).identity, p.identity)

    def test_unknown_fields(self) -> None:
        spec = baseline().spec()
        spec["execute"] = "import os"
        with self.assertRaises(ValueError):
            compile_tfl(spec)

    def test_bad_risk_and_numbers(self) -> None:
        for value in (-1, 1.1, True, float("nan"), float("inf"), "0.5"):
            spec = baseline().spec()
            spec["constraints"]["max_exposure"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                compile_tfl(spec)

    def test_unsafe_deployment(self) -> None:
        spec = baseline().spec()
        spec["deployment"]["require_risk_approval"] = False
        with self.assertRaises(ValueError):
            compile_tfl(spec)

    def test_bad_policy(self) -> None:
        for key, value in (("family", "eval"), ("lookback", True), ("threshold", "0")):
            spec = baseline().spec()
            spec["policy"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                compile_tfl(spec)

    def test_descendants_preserve_mandate(self) -> None:
        p = baseline()
        children = descendants(p)
        self.assertEqual(len({c.identity for c in children}), 12)
        for child in children:
            self.assertEqual(child.parent, p.identity)
            self.assertEqual(child.capital, p.capital)
            self.assertEqual(child.max_exposure, p.max_exposure)
            self.assertEqual(compile_tfl(child.spec()), child)


class ReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.issuer = Issuer.generate()
        self.receipts, self.openings = [], []
        for i in range(3):
            receipt, opening = self.issuer.issue(
                policy="policy",
                license_id="customer",
                decision_id=str(i),
                timestamp=i,
                action={"wait": True},
                risk_gate="passed",
                kpi={"net_alpha": -0.01},
                market_commitment="market",
                previous=self.receipts[-1] if i else None,
            )
            self.receipts.append(receipt)
            self.openings.append(opening)
        self.checkpoint = dict(
            expected_policy="policy",
            expected_license="customer",
            expected_count=3,
            expected_head=digest(self.receipts[-1]),
        )

    def valid(self, receipts: list[dict], key: str | None = None) -> bool:
        return verify_chain(receipts, key or self.issuer.public_key, **self.checkpoint)

    def test_valid_and_negative_kpi(self) -> None:
        self.assertTrue(self.valid(self.receipts))
        for receipt, opening in zip(self.receipts, self.openings):
            self.assertTrue(
                open_commitment(receipt["body"]["kpi_commitment"], **opening)
            )
            self.assertFalse(
                open_commitment(
                    receipt["body"]["kpi_commitment"], {"net_alpha": 1}, opening["salt"]
                )
            )

    def test_tamper(self) -> None:
        forged = copy.deepcopy(self.receipts)
        forged[1]["body"]["action"] = {"buy": 1000}
        self.assertFalse(self.valid(forged))

    def test_reorder_delete_truncate(self) -> None:
        for receipts in (
            self.receipts[::-1],
            self.receipts[1:],
            self.receipts[:-1],
            [],
        ):
            self.assertFalse(self.valid(receipts))

    def test_untrusted_key_and_wrong_license(self) -> None:
        self.assertFalse(self.valid(self.receipts, Issuer.generate().public_key))
        self.checkpoint["expected_license"] = "somebody-else"
        self.assertFalse(self.valid(self.receipts))

    def test_salted_and_instance_bound(self) -> None:
        self.assertNotEqual(
            self.receipts[0]["body"]["kpi_commitment"],
            self.receipts[1]["body"]["kpi_commitment"],
        )
        self.assertEqual(
            self.receipts[0]["body"]["fingerprint"],
            self.receipts[1]["body"]["fingerprint"],
        )


class BenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.market = fixture_market()
        self.policy = replace(baseline(), capital=1000)

    def test_cash_is_cash(self) -> None:
        result = simulate(
            replace(self.policy, family="cash"), self.market, 168, 600, Execution()
        )
        self.assertEqual(result["net_return"], 0)
        self.assertEqual(result["costs"], 0)
        self.assertEqual(result["max_drawdown"], 0)

    def test_self_financing_and_costs(self) -> None:
        gross = simulate(self.policy, self.market, 168, 600, Execution(0, 0, 0))
        net = simulate(self.policy, self.market, 168, 600, Execution())
        self.assertLess(net["net_return"], gross["net_return"])
        self.assertGreater(net["costs"], 0)
        self.assertTrue(all(0 <= a["weight"] < 0.501 for a in net["actions"]))

    def test_prefix_invariance(self) -> None:
        p = descendants(self.policy)[0]
        full = simulate(p, self.market, 168, 700, Execution())
        prefix = simulate(
            p, Market(self.market.candles[:401], {}), 168, 400, Execution()
        )
        self.assertEqual(prefix["actions"], full["actions"][:232])
        self.assertEqual(
            target(p, self.market.candles[:168], 168),
            target(p, self.market.candles[:168], 9999),
        )

    def test_no_future_price_in_target(self) -> None:
        p = descendants(self.policy)[0]
        altered = list(self.market.candles)
        altered[200:] = [
            tuple([r[0], *[v * 10 for v in r[1:5]], r[5]]) for r in altered[200:]
        ]
        a = simulate(p, self.market, 168, 199, Execution())
        b = simulate(p, Market(tuple(altered), {}), 168, 199, Execution())
        self.assertEqual(a["actions"], b["actions"])

    def test_capacity_and_stop(self) -> None:
        constrained = replace(self.policy, capital=1e9)
        rows = []
        price = 100.0
        for i in range(700):
            rows.append((i * 3600, price * 0.94, price * 1.01, price, price, 10.0))
            price *= 0.98
        stressed = Market(tuple(rows), {})
        result = simulate(constrained, stressed, 168, 600, Execution())
        self.assertGreater(result["capacity_clips"], 0)
        stop = simulate(
            self.policy, stressed, 168, 600, Execution(max_participation=0.1)
        )
        self.assertTrue(stop["risk_stopped"])

    def test_bad_market_and_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candles.json"
            payload = {
                "instrument": "BTC-USD",
                "granularity": 3600,
                "candles": self.market.candles,
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            good = Market.load(path)
            changed = Market(good.candles, {"downloaded": "different timestamp"})
            self.assertEqual(good.identity, changed.identity)
            payload["candles"] = [
                r for i, r in enumerate(self.market.candles) if i != 300
            ]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                Market.load(path)

    def test_dsr_corrects_multiple_testing(self) -> None:
        daily = [0.001 + math.sin(i) * 0.01 for i in range(100)]
        few = deflated_sharpe(daily, [-0.1, 0.1])
        many = deflated_sharpe(daily, [-0.1, 0.1] * 100)
        self.assertLess(many["probability"], few["probability"])
        self.assertEqual(deflated_sharpe([0.0] * 30, [0, 0])["probability"], 0)

    def test_tournament_ledger_and_frozen_holdout(self) -> None:
        cash = replace(self.policy, family="cash", name="cash")
        policies = [cash, self.policy, *descendants(self.policy)]
        report = tournament(policies, cash.identity, self.market, Execution())
        self.assertEqual(len(report["runs"]), 14)
        self.assertLessEqual(len(report["holdout"]), 2)
        self.assertTrue(all(r["prefix_invariant"] for r in report["runs"].values()))
        self.assertTrue(all(r["dsr"]["trials"] == 14 for r in report["runs"].values()))


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = Registry()
        self.inventor = Principal("inventor", "inventor")
        self.governor = Principal("risk", "governor")
        self.researcher = Principal("researcher", "research")
        self.adversary = Principal("adversary", "adversary")
        self.observer = Principal("observer", "observer")
        self.cash = replace(baseline("cash"), author="inventor")
        self.child = replace(descendants(self.cash)[0], author="inventor")
        self.registry.register(self.cash.spec(), self.inventor)
        self.registry.register(self.child.spec(), self.inventor)
        self.registry.bootstrap(self.cash.identity, self.governor)

    def tearDown(self) -> None:
        self.registry.close()

    def seed_test_report(self) -> str:
        # Test-only controlled benchmark output; NEVER used by the real experiment.
        report = {
            "shadow_candidate": self.child.identity,
            "incumbent": self.cash.identity,
        }
        with patch("membra_sdk.foundry.registry.tournament", return_value=report):
            return self.registry.benchmark(
                [self.cash.identity, self.child.identity],
                fixture_market(),
                Execution(),
                Principal("engine", "benchmark"),
            )

    def reviews(self) -> None:
        self.registry.review(self.child.identity, research_evidence(), self.researcher)
        self.registry.review(self.child.identity, adversary_evidence(), self.adversary)

    def test_author_cannot_certify(self) -> None:
        with self.assertRaises(PermissionError):
            self.registry.review(
                self.child.identity,
                research_evidence(),
                Principal("inventor", "research"),
            )
        with self.assertRaises(PermissionError):
            self.registry.promote(
                self.child.identity, 1, "risk-approval-123", self.inventor
            )

    def test_no_promotion_without_shadow(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.promote(
                self.child.identity, 1, "risk-approval-123", self.governor
            )

    def test_reviews_then_shadow_promote_rollback(self) -> None:
        run = self.seed_test_report()
        with self.assertRaises(PermissionError):
            self.registry.shadow(run, 1, self.governor)
        self.reviews()
        self.registry.shadow(run, 1, self.governor)
        with self.assertRaises(PermissionError):
            self.registry.promote(
                self.child.identity, 1, "risk-approval-123", self.governor
            )
        self.registry.review(
            self.child.identity,
            {
                "passed": True,
                "limitations": ["fixture only"],
                "observations": 101,
                "max_drawdown": 0.01,
                "receipt_head": "a" * 64,
                "artifact_sha256": "b" * 64,
                "mode": "operator_shadow_attested",
            },
            self.observer,
        )
        promoted = self.registry.promote(
            self.child.identity, 1, "risk-approval-123", self.governor
        )
        self.assertEqual(promoted, {"incumbent": self.child.identity, "epoch": 2})
        with self.assertRaises(ValueError):
            self.registry.rollback(1, "stale", self.governor)
        rolled = self.registry.rollback(2, "integrity alarm", self.governor)
        self.assertEqual(rolled["incumbent"], self.cash.identity)
        self.assertEqual(rolled["epoch"], 3)

    def test_failed_review_blocks(self) -> None:
        evidence = research_evidence()
        evidence["passed"] = False
        self.registry.review(self.child.identity, evidence, self.researcher)
        self.registry.review(self.child.identity, adversary_evidence(), self.adversary)
        with self.assertRaises(PermissionError):
            self.registry.shadow(self.seed_test_report(), 1, self.governor)

    def test_duplicate_trial_and_holdout_reuse(self) -> None:
        self.seed_test_report()
        with self.assertRaises((ValueError, sqlite3.IntegrityError)):
            self.seed_test_report()
        with self.assertRaises(sqlite3.IntegrityError):
            self.registry.register(self.child.spec(), self.inventor)

    def test_risk_expansion_denied(self) -> None:
        expanded = replace(self.child, name="expanded", max_exposure=0.9)
        with self.assertRaises(ValueError):
            self.registry.register(expanded.spec(), self.inventor)

    def test_unsupported_claim_not_proof(self) -> None:
        evidence = research_evidence()
        evidence["proof_status"] = "theorem_proven"
        with self.assertRaises(ValueError):
            self.registry.review(self.child.identity, evidence, self.researcher)

    def test_events_and_fit(self) -> None:
        events = self.registry.events()
        previous = None
        for event in events:
            self.assertEqual(event["body"]["previous"], previous)
            self.assertEqual(digest(event["body"]), event["hash"])
            previous = event["hash"]
        fit = self.registry.fit(2_000_000, 0.1, 0.5)
        self.assertEqual(len(fit["matches"]), 2)
        self.assertIsNone(fit["allocation"])
        self.assertEqual(self.registry.fit(1_000_000, 0.1, 0.5)["matches"], [])

    def test_restart_durability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "ledger.db")
            r = Registry(db)
            r.register(self.cash.spec(), self.inventor)
            r.bootstrap(self.cash.identity, self.governor)
            r.close()
            reopened = Registry(db)
            self.assertEqual(reopened.authority()["incumbent"], self.cash.identity)
            self.assertEqual(len(reopened.events()), 2)
            reopened.close()


class APITests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = Registry()
        self.token = "inventor-" + "a" * 32
        self.reader = "reader-" + "b" * 32
        self.server = make_server(
            self.registry,
            fixture_market(),
            {
                self.token: Principal("inventor", "inventor"),
                self.reader: Principal("customer", "reader"),
            },
            port=0,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.registry.close()

    def request(
        self, path: str, body: dict | None = None, token: str | None = None
    ) -> tuple[int, dict]:
        req = urllib.request.Request(
            self.url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def test_auth(self) -> None:
        self.assertEqual(self.request("/health")[0], 200)
        self.assertEqual(self.request("/catalogue")[0], 403)
        self.assertEqual(self.request("/catalogue", token=self.reader)[0], 200)
        self.assertEqual(self.request("/events", token=self.reader)[0], 403)

    def test_register_compile_and_private_catalogue(self) -> None:
        p = replace(baseline(), author="inventor")
        self.assertEqual(self.request("/compile", p.spec(), self.token)[0], 200)
        code, result = self.request("/strategies", p.spec(), self.token)
        self.assertEqual(code, 200)
        self.assertEqual(result["id"], p.identity)
        self.assertEqual(self.request("/strategies", p.spec(), self.token)[0], 409)
        code, catalogue = self.request("/catalogue", token=self.reader)
        self.assertEqual(code, 200)
        self.assertNotIn("policy", catalogue[0])
        self.assertNotIn("spec", catalogue[0])
        self.assertEqual(self.request("/strategies", p.spec(), self.reader)[0], 403)
        self.assertEqual(
            self.request(
                "/promote",
                {"policy": p.identity, "epoch": 1, "approval": "test approval"},
                self.token,
            )[0],
            403,
        )


if __name__ == "__main__":
    unittest.main()
