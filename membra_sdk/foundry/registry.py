"""Durable evidence ledger and independent research-governance state machine."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlparse

from .benchmark import Execution, Market, tournament
from .tfl import Policy, canonical, compile_tfl, digest, number


@dataclass(frozen=True)
class Principal:
    name: str
    role: str


class Registry:
    """An operator-owned ledger, not a tamper-proof database or broker authority."""

    def __init__(self, path: str = ":memory:") -> None:
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS policies (
                id TEXT PRIMARY KEY, spec TEXT NOT NULL, state TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS authority (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                incumbent TEXT REFERENCES policies(id), epoch INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, data_id TEXT UNIQUE NOT NULL,
                report TEXT NOT NULL, actor TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS seals (
                data_id TEXT PRIMARY KEY, manifest TEXT NOT NULL,
                holdout_start INTEGER NOT NULL, holdout_end INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reviews (
                policy TEXT REFERENCES policies(id), kind TEXT, actor TEXT,
                passed INTEGER, evidence TEXT, created INTEGER,
                PRIMARY KEY(policy,kind)
            );
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY, body TEXT NOT NULL, hash TEXT NOT NULL
            );
            """)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    @staticmethod
    def _role(actor: Principal, role: str) -> None:
        if actor.role != role:
            raise PermissionError(f"{role} role required")

    def _event(self, event: str, actor: Principal, **details: object) -> None:
        last = self.db.execute(
            "SELECT hash FROM events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        body = {
            "event": event,
            "actor": actor.name,
            "role": actor.role,
            "timestamp": time.time_ns(),
            "previous": last["hash"] if last else None,
            **details,
        }
        self.db.execute(
            "INSERT INTO events(body,hash) VALUES(?,?)",
            (canonical(body).decode(), digest(body)),
        )

    def register(self, spec: dict, actor: Principal) -> str:
        self._role(actor, "inventor")
        policy = compile_tfl(spec)
        if policy.author != actor.name:
            raise PermissionError("author must be authenticated inventor")
        with self.transaction():
            if policy.parent:
                parent = self.policy(policy.parent)
                if (
                    policy.capital != parent.capital
                    or policy.instrument != parent.instrument
                    or policy.max_exposure > parent.max_exposure
                    or policy.max_drawdown > parent.max_drawdown
                ):
                    raise ValueError("descendant may not expand parent's risk mandate")
            self.db.execute(
                "INSERT INTO policies VALUES(?,?,?)",
                (policy.identity, canonical(spec).decode(), "unproven"),
            )
            self._event("register", actor, policy=policy.identity, parent=policy.parent)
        return policy.identity

    def policy(self, identity: str) -> Policy:
        with self.lock:
            row = self.db.execute(
                "SELECT spec FROM policies WHERE id=?", (identity,)
            ).fetchone()
            if row is None:
                raise ValueError("unknown policy")
            return compile_tfl(json.loads(row["spec"]))

    def authority(self) -> dict:
        with self.lock:
            row = self.db.execute("SELECT incumbent,epoch FROM authority").fetchone()
            return dict(row) if row else {"incumbent": None, "epoch": 0}

    def bootstrap(self, identity: str, actor: Principal) -> dict:
        self._role(actor, "governor")
        policy = self.policy(identity)
        if actor.name == policy.author or policy.family != "cash":
            raise PermissionError(
                "independent governor must bootstrap cash preservation"
            )
        with self.transaction():
            if self.authority()["incumbent"] is not None:
                raise ValueError("already bootstrapped")
            self.db.execute("INSERT INTO authority VALUES(1,?,1)", (identity,))
            self.db.execute(
                "UPDATE policies SET state='incumbent' WHERE id=?", (identity,)
            )
            self._event("bootstrap", actor, policy=identity)
        return self.authority()

    def benchmark(
        self,
        identities: list[str],
        market: Market,
        execution: Execution,
        actor: Principal,
    ) -> str:
        self._role(actor, "benchmark")
        if not identities or len(identities) > 64:
            raise ValueError("1..64 policies required")
        policies = [self.policy(i) for i in identities]
        authority = self.authority()
        if authority["incumbent"] not in identities:
            raise ValueError("current incumbent must participate")
        incumbent = self.policy(authority["incumbent"])
        if any(
            p.capital != incumbent.capital
            or p.instrument != incumbent.instrument
            or p.max_drawdown > incumbent.max_drawdown
            or p.max_exposure > incumbent.max_exposure
            for p in policies
        ):
            raise ValueError("policies must share capital/instrument and risk envelope")
        manifest = digest([p.spec() for p in policies])
        # Commit this search before computing or exposing any holdout results.
        # Failed runs also consume the dataset; do not silently retry a different search.
        with self.transaction():
            split = int(len(market.candles) * 0.75)
            holdout_start = int(market.candles[split][0])
            holdout_end = int(market.candles[-1][0])
            if self.db.execute(
                "SELECT 1 FROM seals WHERE holdout_start<=? AND holdout_end>=?",
                (holdout_end, holdout_start),
            ).fetchone():
                raise ValueError("overlapping holdout was already consumed")
            self.db.execute(
                "INSERT INTO seals VALUES(?,?,?,?)",
                (market.identity, manifest, holdout_start, holdout_end),
            )
            self._event(
                "seal_search", actor, data_id=market.identity, manifest=manifest
            )
        report = tournament(policies, incumbent.identity, market, execution)
        report["authority_epoch"] = authority["epoch"]
        report["trial_count"] = len(policies)
        run_id = digest(report)
        with self.transaction():
            self.db.execute(
                "INSERT INTO runs VALUES(?,?,?,?)",
                (run_id, market.identity, canonical(report).decode(), actor.name),
            )
            for identity in identities:
                self.db.execute(
                    "UPDATE policies SET state='backtested' WHERE id=? AND state='unproven'",
                    (identity,),
                )
            self._event("benchmark", actor, run=run_id, data_id=market.identity)
        return run_id

    def report(self, run_id: str) -> dict:
        with self.lock:
            row = self.db.execute(
                "SELECT report FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise ValueError("unknown benchmark")
            return json.loads(row["report"])

    def review(self, identity: str, evidence: dict, actor: Principal) -> None:
        if actor.role not in {"research", "adversary", "observer"}:
            raise PermissionError("independent reviewer role required")
        policy = self.policy(identity)
        if actor.name == policy.author:
            raise PermissionError("inventor cannot certify its own policy")
        if type(evidence.get("passed")) is not bool or not evidence.get("limitations"):
            raise ValueError("pass/fail and explicit limitations required")
        if actor.role == "research":
            sources = evidence.get("sources")
            if (
                not isinstance(sources, list)
                or not sources
                or any(
                    not isinstance(s, str)
                    or urlparse(s).scheme != "https"
                    or not urlparse(s).netloc
                    for s in sources
                )
                or evidence.get("novelty") not in {"existing_method", "unresolved"}
                or evidence.get("proof_status") not in {"unproven", "executable_tests"}
            ):
                raise ValueError("sources, novelty and honest proof status required")
        elif actor.role == "adversary":
            required = {"costs", "leakage", "capacity", "regimes", "selection_bias"}
            if set(evidence.get("checks", {})) != required:
                raise ValueError("all adversarial dimensions required")
            if any(type(v) is not bool for v in evidence["checks"].values()):
                raise ValueError("checks must be boolean")
            if evidence["passed"] and not all(evidence["checks"].values()):
                raise ValueError("failed falsification check")
        else:
            if (
                type(evidence.get("observations")) is not int
                or evidence["observations"] < 100
            ):
                raise ValueError("100 real shadow observations required")
            number(evidence.get("max_drawdown"), 0, policy.max_drawdown)
            for key in ("receipt_head", "artifact_sha256"):
                value = evidence.get(key, "")
                if (
                    not isinstance(value, str)
                    or len(value) != 64
                    or any(c not in "0123456789abcdef" for c in value)
                ):
                    raise ValueError("shadow artifact and receipt checkpoint required")
            if evidence.get("mode") != "operator_shadow_attested":
                raise ValueError(
                    "not live validation; operator shadow attestation only"
                )
        with self.transaction():
            self.db.execute(
                "INSERT INTO reviews VALUES(?,?,?,?,?,?)",
                (
                    identity,
                    actor.role,
                    actor.name,
                    int(evidence["passed"]),
                    canonical(evidence).decode(),
                    time.time_ns(),
                ),
            )
            self._event("review", actor, policy=identity, evidence=digest(evidence))

    def _reviews(self, identity: str, kinds: set[str]) -> None:
        rows = self.db.execute(
            "SELECT kind,actor,passed FROM reviews WHERE policy=?", (identity,)
        ).fetchall()
        passed = {r["kind"]: r["actor"] for r in rows if r["passed"]}
        if not kinds <= passed.keys():
            raise PermissionError(
                f"missing independent reviews: {sorted(kinds - passed.keys())}"
            )
        actors = [passed[k] for k in kinds]
        if len(set(actors)) != len(actors):
            raise PermissionError("reviewers must have different identities")

    def shadow(self, run_id: str, expected_epoch: int, actor: Principal) -> str:
        self._role(actor, "governor")
        report = self.report(run_id)
        identity = report["shadow_candidate"]
        if identity is None:
            raise ValueError("no candidate passed tournament")
        with self.transaction():
            current = self.authority()
            if (
                current["epoch"] != expected_epoch
                or report["authority_epoch"] != expected_epoch
                or current["incumbent"] != report["incumbent"]
            ):
                raise ValueError("stale benchmark / authority epoch")
            if self.policy(identity).author == actor.name:
                raise PermissionError("inventor cannot govern itself")
            self._reviews(identity, {"research", "adversary"})
            self.db.execute(
                "UPDATE policies SET state='shadow' WHERE id=?", (identity,)
            )
            self._event(
                "shadow", actor, policy=identity, run=run_id, epoch=expected_epoch
            )
        return identity

    def promote(
        self, identity: str, expected_epoch: int, approval: str, actor: Principal
    ) -> dict:
        self._role(actor, "governor")
        if not isinstance(approval, str) or len(approval.strip()) < 12:
            raise ValueError("explicit risk approval reference required")
        with self.transaction():
            current = self.authority()
            if current["epoch"] != expected_epoch:
                raise ValueError("stale authority epoch")
            state = self.db.execute(
                "SELECT state FROM policies WHERE id=?", (identity,)
            ).fetchone()
            if state is None or state["state"] != "shadow":
                raise ValueError("candidate must be in shadow")
            self._reviews(identity, {"research", "adversary", "observer"})
            reviewers = self.db.execute(
                "SELECT actor FROM reviews WHERE policy=?", (identity,)
            ).fetchall()
            if actor.name == self.policy(identity).author or actor.name in {
                r["actor"] for r in reviewers
            }:
                raise PermissionError(
                    "governor must be independent of inventor and reviewers"
                )
            # Shadow admission must refer to the current epoch, not an earlier incumbent.
            events = self.events()
            admitted = any(
                e["body"]["event"] == "shadow"
                and e["body"].get("policy") == identity
                and e["body"].get("epoch") == expected_epoch
                for e in events
            )
            if not admitted:
                raise ValueError("stale shadow admission")
            self.db.execute(
                "UPDATE policies SET state='retired' WHERE id=?",
                (current["incumbent"],),
            )
            self.db.execute(
                "UPDATE policies SET state='incumbent' WHERE id=?", (identity,)
            )
            self.db.execute(
                "UPDATE authority SET incumbent=?,epoch=epoch+1 WHERE singleton=1",
                (identity,),
            )
            self._event(
                "promote",
                actor,
                policy=identity,
                previous_policy=current["incumbent"],
                approval=approval,
                previous_epoch=expected_epoch,
            )
        return self.authority()

    def rollback(self, expected_epoch: int, reason: str, actor: Principal) -> dict:
        self._role(actor, "governor")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("rollback reason required")
        with self.transaction():
            current = self.authority()
            if current["epoch"] != expected_epoch:
                raise ValueError("stale authority epoch")
            # Always fall back to the approved cash preservation policy.
            cash = next(
                (
                    e["body"]["policy"]
                    for e in self.events()
                    if e["body"]["event"] == "bootstrap"
                ),
                None,
            )
            if cash is None or current["incumbent"] == cash:
                raise ValueError("already at safe fallback")
            self.db.execute(
                "UPDATE policies SET state='retired' WHERE id=?",
                (current["incumbent"],),
            )
            self.db.execute("UPDATE policies SET state='incumbent' WHERE id=?", (cash,))
            self.db.execute("UPDATE authority SET incumbent=?,epoch=epoch+1", (cash,))
            self._event(
                "rollback",
                actor,
                policy=cash,
                reason=reason,
                previous_policy=current["incumbent"],
            )
        return self.authority()

    def catalogue(self) -> list[dict]:
        with self.lock:
            return [
                {
                    "id": r["id"],
                    "state": r["state"],
                    "spec": json.loads(r["spec"]),
                    "license": "not offered; research prototype",
                }
                for r in self.db.execute("SELECT * FROM policies ORDER BY rowid")
            ]

    def events(self) -> list[dict]:
        with self.lock:
            return [
                {"sequence": r["seq"], "body": json.loads(r["body"]), "hash": r["hash"]}
                for r in self.db.execute("SELECT * FROM events ORDER BY seq")
            ]

    def fit(self, capital: float, max_drawdown: float, max_exposure: float) -> dict:
        number(capital, 1, 1e9)
        number(max_drawdown, 0.001, 0.5)
        number(max_exposure, 0, 1)
        eligible = []
        for entry in self.catalogue():
            p = compile_tfl(entry["spec"])
            if (
                p.capital == capital
                and p.max_drawdown <= max_drawdown
                and p.max_exposure <= max_exposure
            ):
                eligible.append(entry)
        return {
            "matches": eligible,
            "allocation": None,
            "warning": "constraint matches only; no portfolio optimization or investment recommendation",
        }

    def close(self) -> None:
        self.db.close()
