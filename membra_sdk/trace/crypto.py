"""Versioned canonical encoding and actor signatures."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


class TraceError(ValueError):
    """Invalid evidence; callers must fail closed."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise TraceError(message)


def canonical(value: Any) -> bytes:
    """TRACE-v1 JSON: sorted ASCII keys, integers only, no duplicate keys."""

    def check(item: Any) -> None:
        if isinstance(item, dict):
            require(all(isinstance(k, str) for k in item), "non-string key")
            for v in item.values():
                check(v)
        elif isinstance(item, list):
            for v in item:
                check(v)
        else:
            require(
                item is None or type(item) in (str, int, bool),
                "TRACE numbers must be integers; encode decimals as strings",
            )

    check(value)
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def load_json(data: bytes | str) -> Any:
    def pairs(items: list) -> dict:
        result: dict = {}
        for k, v in items:
            require(k not in result, f"duplicate JSON key: {k}")
            result[k] = v
        return result

    try:
        value = json.loads(data, object_pairs_hook=pairs)
        canonical(value)
        return value
    except (ValueError, TypeError, RecursionError) as exc:
        raise TraceError(f"invalid JSON: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def fields(value: Any, names: str, location: str) -> None:
    require(
        isinstance(value, dict) and set(value) == set(names.split()),
        f"{location}: fields",
    )


def integer(value: Any, location: str, minimum: int = 0) -> int:
    require(type(value) is int and value >= minimum, f"{location}: invalid integer")
    return value


def hexadecimal(value: Any, size: int = 32) -> bytes:
    require(isinstance(value, str) and len(value) == size * 2, "invalid hex length")
    try:
        result = bytes.fromhex(value)
    except ValueError as exc:
        raise TraceError("invalid hexadecimal") from exc
    require(len(result) == size and result.hex() == value, "noncanonical hex")
    return result


def verify_signature(public_key: str, body: dict, signature: str) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(hexadecimal(public_key)).verify(
            hexadecimal(signature, 64), canonical(body)
        )
    except InvalidSignature as exc:
        raise TraceError("invalid actor signature") from exc


@dataclass(frozen=True)
class Signer:
    actor: str
    key: Ed25519PrivateKey

    @classmethod
    def generate(cls, actor: str) -> "Signer":
        return cls(actor, Ed25519PrivateKey.generate())

    @property
    def public_key(self) -> str:
        return self.key.public_key().public_bytes_raw().hex()

    def sign(self, body: dict) -> dict:
        return {"body": body, "signature": self.key.sign(canonical(body)).hex()}


def commitment(forecast: dict, salt: str) -> str:
    hexadecimal(salt)
    return digest({"domain": "TRACE-forecast-v1", "forecast": forecast, "salt": salt})
