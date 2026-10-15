"""Acceptance tests with an explicitly LOCAL test TSA and oracle, not live data."""

import copy
import hashlib
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from asn1crypto import cms, tsp
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from membra_sdk.trace.__main__ import main
from membra_sdk.trace.crypto import (
    Signer,
    TraceError,
    canonical,
    commitment,
    digest,
    load_json,
)
from membra_sdk.trace.ledger import Ledger
from membra_sdk.trace.timestamp import make_request, verify_timestamp
from membra_sdk.trace.verify import verify_bundle

NS = 1_000_000_000


class LocalTestTSA:
    """A real CMS signature from an untrusted-by-default, ephemeral test CA."""

    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "TRACE TEST ONLY CA")]
        )
        name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "TRACE TEST ONLY TSA")]
        )
        now = datetime.now(UTC)
        self.ca = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=2))
            .not_valid_after(now + timedelta(days=2))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    False, False, False, False, False, True, True, False, False
                ),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(ca_name)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .add_extension(
                x509.KeyUsage(
                    True, False, False, False, False, False, False, False, False
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )
        self.cert = asn1_x509.Certificate.load(
            cert.public_bytes(serialization.Encoding.DER)
        )

    @property
    def ca_pem(self):
        return self.ca.public_bytes(serialization.Encoding.PEM)

    def respond(self, query, generated_ns):
        request = tsp.TimeStampReq.load(query)
        info = tsp.TSTInfo(
            {
                "version": "v1",
                "policy": "1.2.3.4.1",
                "message_imprint": request["message_imprint"],
                "serial_number": secrets.randbits(64),
                "gen_time": datetime.fromtimestamp(generated_ns // NS, UTC),
                "accuracy": {"seconds": 1},
                "ordering": False,
                "nonce": request["nonce"],
            }
        )
        attrs = cms.CMSAttributes(
            [
                {"type": "content_type", "values": ["tst_info"]},
                {
                    "type": "signing_certificate_v2",
                    "values": [
                        {
                            "certs": [
                                {"cert_hash": hashlib.sha256(self.cert.dump()).digest()}
                            ]
                        }
                    ],
                },
                {
                    "type": "message_digest",
                    "values": [hashlib.sha256(info.dump()).digest()],
                },
            ]
        )
        signature = self.key.sign(attrs.dump(), padding.PKCS1v15(), hashes.SHA256())
        signer = cms.SignerInfo(
            {
                "version": "v1",
                "sid": {
                    "issuer_and_serial_number": {
                        "issuer": self.cert.issuer,
                        "serial_number": self.cert.serial_number,
                    }
                },
                "digest_algorithm": {"algorithm": "sha256"},
                "signed_attrs": attrs,
                "signature_algorithm": {"algorithm": "rsassa_pkcs1v15"},
                "signature": signature,
            }
        )
        token = cms.ContentInfo(
            {
                "content_type": "signed_data",
                "content": {
                    "version": "v3",
                    "digest_algorithms": [{"algorithm": "sha256"}],
                    "encap_content_info": {"content_type": "tst_info", "content": info},
                    "certificates": [self.cert],
                    "signer_infos": [signer],
                },
            }
        )
        return tsp.TimeStampResp(
            {"status": {"status": "granted"}, "time_stamp_token": token}
        ).dump()


class TraceAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tsa = LocalTestTSA()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="trace-tests-")
        self.path = Path(self.temp.name)
        self.ca = self.path / "ca.pem"
        self.ca.write_bytes(self.tsa.ca_pem)
        self.signers = {
            role: Signer.generate(role)
            for role in (
                "research",
                "oracle",
                "evaluator",
                "governor",
                "executor",
                "recorder",
            )
        }
        self.trust = {
            "format": "TRACE-trust-v1",
            "chain": "LOCAL-TEST-FIXTURE",
            "actors": {
                name: {"key": s.public_key, "role": name}
                for name, s in self.signers.items()
            },
            "policy": digest({"test": "policy"}),
            "epoch": 0,
            "risk_limits": digest({"test": "no-capital"}),
            "max_evidence_age_ns": 3600 * NS,
            "tsa_ca_sha256": hashlib.sha256(self.tsa.ca_pem).hexdigest(),
            "tsa_uncertainty_ns": NS,
        }
        self.now = (time.time_ns() // NS - 1000) * NS
        self.clock = patch(
            "membra_sdk.trace.ledger.time.time_ns", side_effect=lambda: self.now
        )
        self.clock.start()
        self.db_path = self.path / "trace.db"
        self.ledger = Ledger(self.db_path, self.trust, self.ca)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.clock.stop)
        self.addCleanup(lambda: self.ledger.close())

    def append(self, role, kind, payload, identity):
        return self.ledger.append(self.signers[role], kind, payload, identity)

    def observation(self, identity="obs"):
        return self.append(
            "research",
            "observation",
            {
                "source": "LOCAL TEST DATA",
                "version": "1",
                "data_commitment": digest({"test": identity}),
            },
            identity,
        )

    def anchor(self):
        cp, _ = self.ledger.checkpoint(self.signers["recorder"])
        query = self.ledger.prepare_anchor(cp, "https://local-test.invalid/tsr")
        response = self.tsa.respond(query, self.now + 2 * NS)
        self.ledger.complete_anchor(cp, response)
        self.now += 4 * NS
        return cp

    def check(self, bundle, cp, trust=None):
        return verify_bundle(
            bundle, trust or self.trust, expected_checkpoint=cp, ca=self.ca
        )

    def forecast(self):
        self.observation()
        self.target = self.now + 100 * NS
        self.deadline = self.target + 100 * NS
        self.prediction = {"probability_ppm": 700_000}
        self.salt = secrets.token_hex(32)
        content = {
            "observation": "obs",
            "policy": self.trust["policy"],
            "target_ns": self.target,
            "prediction": self.prediction,
        }
        self.append(
            "research",
            "forecast",
            {
                "observation": "obs",
                "policy": self.trust["policy"],
                "commitment": commitment(content, self.salt),
                "target_ns": self.target,
                "deadline_ns": self.deadline,
                "score": "brier-ppm-v1",
            },
            "forecast",
        )

    def resolve(self, late=False):
        self.now = max(
            self.now, self.deadline + 5 * NS if late else self.target + 5 * NS
        )
        self.append(
            "oracle",
            "outcome",
            {
                "forecast": "forecast",
                "release_ns": self.now - NS,
                "source": "LOCAL TEST ORACLE",
                "value": 1,
            },
            "outcome",
        )
        self.append(
            "research",
            "reveal",
            {
                "forecast": "forecast",
                "prediction": self.prediction,
                "salt": self.salt,
            },
            "reveal",
        )
        self.outcome_cp = self.anchor()

    def score(self, identity="score", value=90_000_000_000):
        outcome_time = self.ledger.validate()["timestamps"][self.outcome_cp]
        return self.append(
            "evaluator",
            "score",
            {
                "forecast": "forecast",
                "reveal": "reveal",
                "outcome": "outcome",
                "outcome_checkpoint": self.outcome_cp,
                "anchor_digest": outcome_time["receipt_digest"],
                "squared_error": value,
            },
            identity,
        )

    def governance(self):
        self.forecast()
        self.anchor()
        self.resolve()
        self.score()
        self.append(
            "evaluator",
            "decision",
            {
                "policy": self.trust["policy"],
                "epoch": 0,
                "evidence": ["score"],
                "action": {"kind": "shadow", "capital": "0"},
            },
            "decision",
        )
        evidence_cp = self.anchor()
        times = self.ledger.validate()["timestamps"][evidence_cp]
        self.authorization = {
            "decision": "decision",
            "subject": "executor",
            "evidence_checkpoint": evidence_cp,
            "anchor_digest": times["receipt_digest"],
            "policy": self.trust["policy"],
            "epoch": 0,
            "risk_limits": self.trust["risk_limits"],
            "valid_from_ns": self.now,
            "valid_until_ns": self.now + 300 * NS,
        }
        self.append("governor", "authorization", self.authorization, "auth")
        auth_cp = self.anchor()
        auth_time = self.ledger.validate()["timestamps"][auth_cp]
        self.action = {
            "authorization": "auth",
            "authorization_checkpoint": auth_cp,
            "anchor_digest": auth_time["receipt_digest"],
            "policy": self.trust["policy"],
            "epoch": 0,
            "risk_limits": self.trust["risk_limits"],
        }

    def test_tampering_deletion_insertion_reordering_and_truncation(self):
        self.observation()
        self.observation("obs2")
        cp = self.anchor()
        original = self.ledger.bundle()
        self.assertTrue(self.check(original, cp)["valid"])
        changes = {}
        b = copy.deepcopy(original)
        b["events"][0]["body"]["payload"]["source"] = "changed"
        changes["body"] = b
        b = copy.deepcopy(original)
        b["events"].pop(0)
        changes["delete"] = b
        b = copy.deepcopy(original)
        b["events"].append(copy.deepcopy(b["events"][0]))
        changes["insert"] = b
        b = copy.deepcopy(original)
        b["events"].reverse()
        changes["reorder"] = b
        b = copy.deepcopy(original)
        b["events"].pop()
        changes["terminal deletion"] = b
        b = copy.deepcopy(original)
        b["events"][1]["body"]["previous"] = "0" * 64
        changes["predecessor"] = b
        b = copy.deepcopy(original)
        b["events"][1]["body"]["id"] = "obs"
        changes["duplicate id"] = b
        b = copy.deepcopy(original)
        b["events"][0]["signature"] = "0" * 128
        changes["signature"] = b
        b = copy.deepcopy(original)
        b["events"][0]["body"]["kind"] = "arbitrary-code"
        changes["kind"] = b
        b = copy.deepcopy(original)
        b["events"][0]["body"]["sequence"] = True
        changes["sequence bool"] = b
        b = copy.deepcopy(original)
        b["checkpoints"][0]["body"]["head"] = "0" * 64
        changes["root"] = b
        b = copy.deepcopy(original)
        b["anchors"].clear()
        changes["missing time"] = b
        for name, bundle in changes.items():
            with self.subTest(mutation=name), self.assertRaises(TraceError):
                self.check(bundle, cp)
        with self.assertRaises(TraceError):
            self.check(original, "0" * 64)

    def test_external_receipt_imprint_nonce_signature_and_root(self):
        self.observation()
        cp = self.anchor()
        receipt = self.ledger.bundle()["anchors"][cp]
        valid = verify_timestamp(receipt, cp, self.ca, self.trust)
        self.assertEqual(valid["latest_ns"] - valid["earliest_ns"], 2 * NS)
        self.assertEqual(
            valid["signer_certificate_sha256"],
            hashlib.sha256(self.tsa.cert.dump()).hexdigest(),
        )
        mutations = []
        r = dict(receipt)
        r["request"] = make_request(cp).hex()
        mutations.append(r)
        r = dict(receipt)
        r["response"] = (bytes.fromhex(receipt["response"])[:-1] + b"\0").hex()
        mutations.append(r)
        r = dict(receipt)
        r["response"] = receipt["response"][:80]
        mutations.append(r)
        for r in mutations:
            with self.assertRaises(TraceError):
                verify_timestamp(r, cp, self.ca, self.trust)
        with self.assertRaises(TraceError):
            verify_timestamp(receipt, "0" * 64, self.ca, self.trust)
        wrong_trust = dict(self.trust, tsa_ca_sha256="0" * 64)
        with self.assertRaises(TraceError):
            verify_timestamp(receipt, cp, self.ca, wrong_trust)
        other = LocalTestTSA()
        untrusted = dict(
            receipt,
            response=other.respond(bytes.fromhex(receipt["request"]), self.now).hex(),
        )
        with self.assertRaises(TraceError):
            verify_timestamp(untrusted, cp, self.ca, self.trust)

    def test_valid_prequential_score_and_independent_oracle(self):
        self.forecast()
        self.anchor()
        self.resolve()
        self.score()
        cp = self.anchor()
        result = self.check(self.ledger.bundle(), cp)
        self.assertEqual(result["forecast_status"], {"forecast": "scored"})
        self.assertTrue(result["independent_time"])
        with self.assertRaisesRegex(TraceError, "duplicate score"):
            self.score("duplicate-score")

    def test_no_unanchored_or_backdated_forecasts_scored(self):
        self.forecast()
        with self.assertRaisesRegex(TraceError, "external commitment"):
            self.resolve()
        self.now = self.target + 10 * NS
        self.anchor()
        with self.assertRaisesRegex(TraceError, "external commitment"):
            self.resolve()

    def test_score_requires_independently_witnessed_outcome(self):
        self.forecast()
        self.anchor()
        self.now = self.target + 5 * NS
        self.append(
            "oracle",
            "outcome",
            {
                "forecast": "forecast",
                "release_ns": self.now - NS,
                "source": "LOCAL TEST ORACLE",
                "value": 1,
            },
            "outcome",
        )
        self.append(
            "research",
            "reveal",
            {"forecast": "forecast", "prediction": self.prediction, "salt": self.salt},
            "reveal",
        )
        cp, _ = self.ledger.checkpoint(self.signers["recorder"])
        payload = {
            "forecast": "forecast",
            "reveal": "reveal",
            "outcome": "outcome",
            "outcome_checkpoint": cp,
            "anchor_digest": "0" * 64,
            "squared_error": 90_000_000_000,
        }
        with self.assertRaisesRegex(TraceError, "lacks independent timestamp"):
            self.append("evaluator", "score", payload, "score")
        self.outcome_cp = self.anchor()
        self.score()
        cp = self.anchor()
        self.assertEqual(
            self.check(self.ledger.bundle(), cp)["forecast_status"]["forecast"],
            "scored",
        )

    def test_clock_regression_across_checkpoint_rejected(self):
        self.observation()
        self.now += 5 * NS
        self.anchor()
        self.now -= 5 * NS
        with self.assertRaisesRegex(TraceError, "local clock order"):
            self.observation("after-clock-regression")
        self.assertEqual(len(self.ledger.bundle()["events"]), 1)

    def test_forecaster_cannot_supply_oracle_or_authorization(self):
        self.forecast()
        self.anchor()
        self.now = max(self.now, self.target + 5 * NS)
        with self.assertRaisesRegex(TraceError, "role"):
            self.append(
                "research",
                "outcome",
                {
                    "forecast": "forecast",
                    "release_ns": self.target,
                    "source": "self",
                    "value": 1,
                },
                "forged-outcome",
            )
        with self.assertRaisesRegex(TraceError, "role"):
            self.append("research", "authorization", {}, "forged-auth")

    def test_late_outcome_explicit_and_not_scorable(self):
        self.forecast()
        self.anchor()
        self.resolve(late=True)
        with self.assertRaisesRegex(TraceError, "late outcome"):
            self.score()
        cp = self.anchor()
        self.assertEqual(
            self.check(self.ledger.bundle(), cp)["forecast_status"]["forecast"], "late"
        )

    def test_missing_pending_and_overdue_are_explicit(self):
        self.forecast()
        cp = self.anchor()
        self.assertEqual(
            self.check(self.ledger.bundle(), cp)["forecast_status"]["forecast"],
            "pending",
        )
        self.now = self.deadline + 10 * NS
        self.observation("post-deadline-observation")
        cp = self.anchor()
        self.assertEqual(
            self.check(self.ledger.bundle(), cp)["forecast_status"]["forecast"],
            "overdue_without_resolution",
        )
        self.append(
            "oracle",
            "missing",
            {
                "forecast": "forecast",
                "release_ns": self.now,
                "source": "LOCAL TEST ORACLE",
                "reason": "timeout",
            },
            "missing",
        )
        cp = self.anchor()
        self.assertEqual(
            self.check(self.ledger.bundle(), cp)["forecast_status"]["forecast"],
            "missing",
        )

    def test_reveal_and_arithmetic_not_self_certified(self):
        self.forecast()
        self.anchor()
        self.resolve()
        with self.assertRaisesRegex(TraceError, "incorrect Brier"):
            self.score(value=1)
        with self.assertRaisesRegex(TraceError, "reveal mismatch"):
            self.append(
                "research",
                "reveal",
                {
                    "forecast": "forecast",
                    "prediction": {"probability_ppm": 999999},
                    "salt": self.salt,
                },
                "bad-reveal",
            )

    def test_out_of_order_references_and_duplicate_resolutions(self):
        with self.assertRaisesRegex(TraceError, "missing evidence"):
            self.append(
                "research",
                "forecast",
                {
                    "observation": "not-yet-observed",
                    "policy": self.trust["policy"],
                    "commitment": "0" * 64,
                    "target_ns": self.now + 100 * NS,
                    "deadline_ns": self.now + 200 * NS,
                    "score": "brier-ppm-v1",
                },
                "bad-forecast",
            )
        self.forecast()
        self.anchor()
        self.resolve()
        with self.assertRaisesRegex(TraceError, "duplicate resolution"):
            self.append(
                "oracle",
                "outcome",
                {
                    "forecast": "forecast",
                    "release_ns": self.target,
                    "source": "test",
                    "value": 0,
                },
                "duplicate-outcome",
            )

    def test_valid_governance_and_single_use(self):
        self.governance()
        self.append("executor", "authorized_action", self.action, "action")
        cp = self.anchor()
        self.assertEqual(self.check(self.ledger.bundle(), cp)["authorized_actions"], 1)
        with self.assertRaisesRegex(TraceError, "used/revoked"):
            self.append("executor", "authorized_action", self.action, "replay")

    def test_scope_epoch_and_risk_expansion_fail_closed(self):
        self.governance()
        for field, value in (
            ("policy", "0" * 64),
            ("epoch", 1),
            ("risk_limits", "0" * 64),
            ("anchor_digest", "0" * 64),
        ):
            action = dict(self.action, **{field: value})
            with self.subTest(field=field), self.assertRaises(TraceError):
                self.append("executor", "authorized_action", action, f"bad-{field}")

    def test_revocation_and_rollback_invalidate_authorizations(self):
        self.governance()
        self.append(
            "governor",
            "revoke",
            {"authorization": "auth", "reason": "test revoke"},
            "revoke",
        )
        with self.assertRaisesRegex(TraceError, "revoked"):
            self.append("executor", "authorized_action", self.action, "revoked-action")
        self.append(
            "governor",
            "epoch",
            {"policy": self.trust["policy"], "epoch": 1, "reason": "rollback"},
            "rollback",
        )
        with self.assertRaises(TraceError):
            self.append("executor", "authorized_action", self.action, "old-epoch")

    def test_authorization_expiry_and_stale_evidence(self):
        self.governance()
        self.now = self.authorization["valid_until_ns"] + NS
        with self.assertRaisesRegex(TraceError, "expired"):
            self.append("executor", "authorized_action", self.action, "expired-action")
        self.now = self.authorization["valid_from_ns"] + 20 * NS
        self.append("executor", "authorized_action", self.action, "action")
        cp = self.anchor()
        stale = dict(self.trust, max_evidence_age_ns=NS)
        with self.assertRaisesRegex(TraceError, "stale"):
            self.check(self.ledger.bundle(), cp, stale)

    def test_rotated_keys_historical_verification_and_restart(self):
        self.observation()
        old = self.signers["research"]
        new = Signer.generate("research")
        self.ledger.append(old, "key_rotate", {}, "rotation", rotation_key=new)
        with self.assertRaisesRegex(TraceError, "inactive"):
            self.observation("old-key")
        self.signers["research"] = new
        self.observation("new-key")
        cp = self.anchor()
        self.assertTrue(self.check(self.ledger.bundle(), cp)["valid"])
        self.ledger.close()
        self.ledger = Ledger(self.db_path, self.trust, self.ca)
        self.assertEqual(len(self.ledger.bundle()["events"]), 3)
        self.observation("after-restart")

    def test_rotation_requires_both_keys_and_no_role_changes(self):
        self.observation()
        with self.assertRaises(TraceError):
            self.append(
                "research",
                "key_rotate",
                {"new_key": Signer.generate("research").public_key, "proof": "0" * 128},
                "bad-rotation",
            )
        self.append(
            "governor",
            "key_revoke",
            {"actor": "research", "reason": "test compromise"},
            "key-revoke",
        )
        with self.assertRaisesRegex(TraceError, "inactive"):
            self.observation("revoked-key")

    def test_duplicate_event_is_idempotent_but_conflict_rejected(self):
        original = self.observation()
        self.now += NS
        self.assertEqual(self.observation(), original)
        with self.assertRaisesRegex(TraceError, "different content"):
            self.append(
                "research",
                "observation",
                {
                    "source": "changed",
                    "version": "1",
                    "data_commitment": "0" * 64,
                },
                "obs",
            )
        self.assertEqual(len(self.ledger.bundle()["events"]), 1)

    def test_interrupted_transaction_and_process_crash_rollback(self):
        self.observation()
        with self.assertRaises(RuntimeError), self.ledger.transaction():
            self.ledger.db.execute("INSERT INTO events VALUES(1,'uncommitted','{}')")
            raise RuntimeError("injected interrupted write")
        self.assertEqual(len(self.ledger.bundle()["events"]), 1)
        self.ledger.close()
        script = (
            "import os,sqlite3,sys; c=sqlite3.connect(sys.argv[1]); "
            "c.execute('BEGIN IMMEDIATE'); "
            "c.execute(\"INSERT INTO events VALUES(1,'crash','{}')\"); os._exit(9)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.db_path)], check=False
        )
        self.assertEqual(result.returncode, 9)
        self.ledger = Ledger(self.db_path, self.trust, self.ca)
        self.assertEqual(len(self.ledger.bundle()["events"]), 1)

    def test_corruption_is_not_silently_skipped(self):
        self.observation()
        self.ledger.db.execute("UPDATE events SET envelope='{'")
        self.ledger.db.commit()
        self.ledger.close()
        with self.assertRaises(TraceError):
            Ledger(self.db_path, self.trust, self.ca)

    def test_prepared_request_survives_timeout_restart_and_duplicate_reply(self):
        self.observation()
        cp, _ = self.ledger.checkpoint(self.signers["recorder"])
        provider = "https://local-test.invalid/tsr"
        query = self.ledger.prepare_anchor(cp, provider)
        with (
            patch(
                "membra_sdk.trace.ledger.submit",
                side_effect=TimeoutError("test timeout"),
            ),
            self.assertRaises(TimeoutError),
        ):
            self.ledger.anchor(cp, provider)
        self.ledger.close()
        self.ledger = Ledger(self.db_path, self.trust, self.ca)
        self.assertEqual(query, self.ledger.prepare_anchor(cp, provider))
        first = self.ledger.complete_anchor(
            cp, self.tsa.respond(query, self.now + 2 * NS)
        )
        second = self.ledger.complete_anchor(
            cp, self.tsa.respond(query, self.now + 3 * NS)
        )
        self.assertEqual(first, second)
        with patch(
            "membra_sdk.trace.ledger.submit",
            side_effect=AssertionError("unexpected network"),
        ):
            self.assertEqual(first, self.ledger.anchor(cp, provider))

    def test_corrupt_tsa_response_stays_pending_and_retryable(self):
        self.observation()
        cp, _ = self.ledger.checkpoint(self.signers["recorder"])
        query = self.ledger.prepare_anchor(cp, "https://local-test.invalid/tsr")
        with self.assertRaises(TraceError):
            self.ledger.complete_anchor(cp, b"broken")
        self.assertEqual(self.ledger.bundle()["anchors"], {})
        self.ledger.complete_anchor(cp, self.tsa.respond(query, self.now + 2 * NS))
        self.assertTrue(self.check(self.ledger.bundle(), cp)["valid"])

    def test_atomic_export_preserves_previous_file_on_failure(self):
        self.observation()
        cp = self.anchor()
        path = self.path / "bundle.json"
        self.ledger.export(path, cp)
        before = path.read_bytes()
        with (
            patch(
                "membra_sdk.trace.ledger.os.replace",
                side_effect=OSError("interrupted replace"),
            ),
            self.assertRaises(OSError),
        ):
            self.ledger.export(path, cp)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.path.glob(".trace-*")), [])

    def test_offline_cli_without_database_and_malformed_bundles(self):
        self.observation()
        cp = self.anchor()
        bundle = self.path / "bundle.json"
        trust = self.path / "trust.json"
        self.ledger.export(bundle, cp)
        trust.write_bytes(canonical(self.trust))
        self.ledger.close()
        self.db_path.unlink()
        args = [
            "verify",
            str(bundle),
            "--trust",
            str(trust),
            "--checkpoint",
            cp,
            "--tsa-ca",
            str(self.ca),
        ]
        with patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("verification must stay offline"),
        ):
            self.assertEqual(main(args), 0)
        for data in (
            b"{",
            b'{"format":1,"format":2}',
            b"null",
            b"[]",
            b'{"x":NaN}',
            b'{"x":1.0}',
        ):
            bundle.write_bytes(data)
            with self.subTest(data=data):
                self.assertEqual(main(args), 1)

    def test_altered_trust_is_not_accepted_on_restart(self):
        self.observation()
        self.ledger.close()
        changed = copy.deepcopy(self.trust)
        changed["actors"]["research"]["role"] = "governor"
        with self.assertRaisesRegex(TraceError, "trust changed"):
            Ledger(self.db_path, changed, self.ca)

    def test_json_canonical_rejects_duplicate_nonfinite_and_float(self):
        for value in (float("nan"), 1.2, {1: "bad key"}):
            with self.assertRaises(TraceError):
                canonical(value)
        with self.assertRaises(TraceError):
            load_json('{"a":1,"a":2}')


if __name__ == "__main__":
    unittest.main()
