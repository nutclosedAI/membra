"""Strict Temporal Finance Language v1; compilation never evaluates supplied code."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, replace
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _keys(obj: dict, keys: set[str]) -> None:
    if not isinstance(obj, dict) or set(obj) != keys:
        raise ValueError(f"expected exactly these fields: {sorted(keys)}")


def number(value: Any, low: float, high: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"expected finite number in [{low}, {high}]")
    return float(value)


@dataclass(frozen=True)
class Policy:
    name: str
    version: str
    parent: str | None
    author: str
    capital: float
    max_drawdown: float
    max_exposure: float
    instrument: str
    family: str
    lookback: int
    rebalance_hours: int
    threshold: float

    @property
    def identity(self) -> str:
        return digest(asdict(self))

    def spec(self) -> dict:
        return {
            "tfl": 1,
            "strategy": {
                "name": self.name,
                "version": self.version,
                "parent": self.parent,
                "author": self.author,
            },
            "constraints": {
                "capital_limit": self.capital,
                "max_drawdown": self.max_drawdown,
                "max_exposure": self.max_exposure,
                "leverage_limit": 1,
                "allowed_instruments": [self.instrument],
            },
            "policy": {
                "family": self.family,
                "lookback": self.lookback,
                "rebalance_hours": self.rebalance_hours,
                "threshold": self.threshold,
            },
            "validation": {
                "prior_art_review": True,
                "out_of_sample_test": True,
                "transaction_costs": True,
                "adversarial_review": True,
            },
            "deployment": {
                "default_mode": "shadow",
                "require_risk_approval": True,
                "rollback_on_integrity_failure": True,
            },
        }


def compile_tfl(spec: dict) -> Policy:
    _keys(
        spec,
        {"tfl", "strategy", "constraints", "policy", "validation", "deployment"},
    )
    if type(spec["tfl"]) is not int or spec["tfl"] != 1:
        raise ValueError("unsupported TFL version")
    s, c, p = (spec[k] for k in ("strategy", "constraints", "policy"))
    _keys(s, {"name", "version", "parent", "author"})
    for field in ("name", "version", "author"):
        if not isinstance(s[field], str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,100}", s[field]
        ):
            raise ValueError(f"invalid {field}")
    if s["parent"] is not None and (
        not isinstance(s["parent"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", s["parent"])
    ):
        raise ValueError("parent must be a SHA-256 policy identity")
    _keys(
        c,
        {
            "capital_limit",
            "max_drawdown",
            "max_exposure",
            "leverage_limit",
            "allowed_instruments",
        },
    )
    if c["allowed_instruments"] != ["BTC-USD"]:
        raise ValueError("v1 supports BTC-USD spot and USD cash only")
    if number(c["leverage_limit"], 1, 1) != 1:
        raise ValueError("no leverage")
    _keys(p, {"family", "lookback", "rebalance_hours", "threshold"})
    if p["family"] not in {"cash", "hold", "inventory", "temporal"}:
        raise ValueError("unregistered policy family")
    for field, low, high in (("lookback", 2, 168), ("rebalance_hours", 1, 24)):
        if type(p[field]) is not int or not low <= p[field] <= high:
            raise ValueError(f"invalid {field}")
    v, d = spec["validation"], spec["deployment"]
    _keys(
        v,
        {
            "prior_art_review",
            "out_of_sample_test",
            "transaction_costs",
            "adversarial_review",
        },
    )
    if any(value is not True for value in v.values()):
        raise ValueError("all validation gates required")
    _keys(d, {"default_mode", "require_risk_approval", "rollback_on_integrity_failure"})
    if (
        d["default_mode"] != "shadow"
        or d["require_risk_approval"] is not True
        or d["rollback_on_integrity_failure"] is not True
    ):
        raise ValueError("unsafe deployment configuration")
    return Policy(
        **s,
        capital=number(c["capital_limit"], 1, 1e9),
        max_drawdown=number(c["max_drawdown"], 0.001, 0.5),
        max_exposure=number(c["max_exposure"], 0, 1),
        instrument="BTC-USD",
        family=p["family"],
        lookback=p["lookback"],
        rebalance_hours=p["rebalance_hours"],
        threshold=number(p["threshold"], 0, 0.1),
    )


def baseline(family: str = "inventory", author: str = "baseline") -> Policy:
    return Policy(
        family,
        "1.0.0",
        None,
        author,
        2_000_000,
        0.10,
        0.5,
        "BTC-USD",
        family,
        24,
        1,
        0.0,
    )


def descendants(parent: Policy, author: str = "mutator") -> list[Policy]:
    """Bounded, deterministic search; these are hypotheses, not invented theorems."""
    return [
        replace(
            parent,
            name=f"temporal-{lookback}-{hours}-{threshold}",
            parent=parent.identity,
            author=author,
            family="temporal",
            lookback=lookback,
            rebalance_hours=hours,
            threshold=threshold,
        )
        for lookback in (12, 24, 72)
        for hours in (1, 6)
        for threshold in (0.0, 0.005)
    ]
