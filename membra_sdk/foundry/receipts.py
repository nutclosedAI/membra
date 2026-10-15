"""TAW audit receipts, not behavioral watermarks or proof of alpha."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .tfl import canonical, digest

DOMAIN = "membra-taw-v1"


def commitment(kpi: dict, salt: str) -> str:
    if len(bytes.fromhex(salt)) != 32:
        raise ValueError("KPI salt must be 32 bytes")
    return digest({"domain": DOMAIN + "-kpi", "salt": salt, "kpi": kpi})


def open_commitment(committed: str, kpi: dict, salt: str) -> bool:
    return hmac.compare_digest(committed, commitment(kpi, salt))


@dataclass
class Issuer:
    key: Ed25519PrivateKey
    watermark_key: bytes

    @classmethod
    def generate(cls) -> Issuer:
        return cls(Ed25519PrivateKey.generate(), secrets.token_bytes(32))

    @property
    def public_key(self) -> str:
        return self.key.public_key().public_bytes_raw().hex()

    def issue(
        self,
        *,
        policy: str,
        license_id: str,
        decision_id: str,
        timestamp: int,
        action: dict,
        risk_gate: str,
        kpi: dict,
        market_commitment: str,
        previous: dict | None = None,
    ) -> tuple[dict, dict]:
        salt = secrets.token_hex(32)
        fingerprint = hmac.new(
            self.watermark_key,
            canonical([DOMAIN, policy, license_id]),
            hashlib.sha256,
        ).hexdigest()
        body = {
            "domain": DOMAIN,
            "sequence": previous["body"]["sequence"] + 1 if previous else 0,
            "previous": digest(previous) if previous else None,
            "policy": policy,
            "license_id": license_id,
            "fingerprint": fingerprint,
            "decision_id": decision_id,
            "timestamp": timestamp,
            "action": action,
            "risk_gate": risk_gate,
            "market_commitment": market_commitment,
            "kpi_commitment": commitment(kpi, salt),
        }
        return {
            "body": body,
            "signature": self.key.sign(canonical(body)).hex(),
        }, {"salt": salt, "kpi": kpi}


def verify_chain(
    receipts: list[dict],
    trusted_public_key: str,
    *,
    expected_policy: str,
    expected_license: str,
    expected_count: int,
    expected_head: str,
) -> bool:
    """Requires an external trust anchor and checkpoint; truncation is otherwise invisible."""
    try:
        if not receipts or len(receipts) != expected_count:
            return False
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(trusted_public_key))
        previous = None
        last_time = -1
        ids: set[str] = set()
        for i, receipt in enumerate(receipts):
            body: dict[str, Any] = receipt["body"]
            key.verify(bytes.fromhex(receipt["signature"]), canonical(body))
            if (
                body["domain"] != DOMAIN
                or body["sequence"] != i
                or body["previous"] != previous
                or body["policy"] != expected_policy
                or body["license_id"] != expected_license
                or body["timestamp"] < last_time
                or body["decision_id"] in ids
                or (i > 0 and body["fingerprint"] != receipts[0]["body"]["fingerprint"])
            ):
                return False
            ids.add(body["decision_id"])
            previous = digest(receipt)
            last_time = body["timestamp"]
        return hmac.compare_digest(previous or "", expected_head)
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return False
