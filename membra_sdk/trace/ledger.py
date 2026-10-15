"""Transactional local storage; no private keys are persisted by this module."""

import os
import sqlite3
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .crypto import Signer, TraceError, canonical, digest, load_json, require
from .timestamp import make_request, request_digest, submit, verify_timestamp
from .verify import rotation_message, verify_bundle


class Ledger:
    def __init__(self, path: Path, trust: dict, ca: Path | None = None):
        self.trust = load_json(canonical(trust))
        self.ca = ca
        self.db = sqlite3.connect(path, timeout=15)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), trust_digest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, envelope TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS checkpoints (id TEXT PRIMARY KEY, envelope TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS anchors (
                    checkpoint TEXT PRIMARY KEY REFERENCES checkpoints(id),
                    provider TEXT NOT NULL, query BLOB NOT NULL, response BLOB
                );
            """)
            self.db.execute(
                "INSERT OR IGNORE INTO metadata VALUES(1,?)", (digest(self.trust),)
            )
            self.db.commit()
            require(
                self.db.execute("SELECT trust_digest FROM metadata").fetchone()[0]
                == digest(self.trust),
                "database trust changed; explicit migration required",
            )
            require(
                self.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                "SQLite integrity check failed",
            )
            self.validate()
        except Exception:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def bundle(self) -> dict:
        events = []
        for row in self.db.execute("SELECT * FROM events ORDER BY sequence"):
            event = load_json(row["envelope"])
            require(
                event["body"]["sequence"] == row["sequence"]
                and event["body"]["id"] == row["id"],
                "database event index mismatch",
            )
            events.append(event)
        checkpoints = []
        for row in self.db.execute("SELECT * FROM checkpoints ORDER BY rowid"):
            value = load_json(row["envelope"])
            require(digest(value) == row["id"], "database checkpoint index mismatch")
            checkpoints.append(value)
        anchors = {}
        for row in self.db.execute("SELECT * FROM anchors"):
            require(
                isinstance(row["provider"], str)
                and row["provider"].startswith("https://")
                and request_digest(bytes(row["query"])) == row["checkpoint"],
                "corrupt prepared timestamp request",
            )
            if row["response"] is None:
                continue
            anchors[row["checkpoint"]] = {
                "provider": row["provider"],
                "request": bytes(row["query"]).hex(),
                "response": bytes(row["response"]).hex(),
            }
        return {
            "format": "TRACE-bundle-v1",
            "chain": self.trust["chain"],
            "events": events,
            "checkpoints": checkpoints,
            "anchors": anchors,
        }

    def validate(self) -> dict:
        return verify_bundle(
            self.bundle(), self.trust, ca=self.ca, expected_checkpoint=None, draft=True
        )

    def append(
        self,
        signer: Signer,
        kind: str,
        payload: dict,
        event_id: str,
        *,
        observed_ns: int | None = None,
        rotation_key: Signer | None = None,
    ) -> dict:
        with self.transaction():
            self.validate()
            existing = self.db.execute(
                "SELECT envelope FROM events WHERE id=?", (event_id,)
            ).fetchone()
            if existing:
                value = load_json(existing[0])
                b = value["body"]
                require(
                    rotation_key is None
                    and (b["actor"], b["key"], b["kind"], b["payload"])
                    == (
                        signer.actor,
                        signer.public_key,
                        kind,
                        payload,
                    )
                    and (observed_ns is None or b["observed_ns"] == observed_ns),
                    "event id reused with different content",
                )
                return value
            bundle = self.bundle()
            events = bundle["events"]
            now = time.time_ns()
            if events:
                require(
                    now >= events[-1]["body"]["appended_ns"],
                    "local clock regressed; retry after clock recovery",
                )
            body = {
                "domain": "TRACE-event-v1",
                "chain": self.trust["chain"],
                "sequence": len(events),
                "previous": digest(events[-1]) if events else None,
                "id": event_id,
                "kind": kind,
                "actor": signer.actor,
                "key": signer.public_key,
                "observed_ns": now if observed_ns is None else observed_ns,
                "appended_ns": now,
                "payload": payload,
            }
            if rotation_key is not None:
                require(
                    kind == "key_rotate"
                    and signer.actor == rotation_key.actor
                    and payload == {},
                    "rotation principal mismatch",
                )
                proof = rotation_key.key.sign(
                    canonical(rotation_message(body, rotation_key.public_key))
                ).hex()
                body["payload"] = {"new_key": rotation_key.public_key, "proof": proof}
            event = signer.sign(body)
            bundle["events"].append(event)
            verify_bundle(
                bundle, self.trust, ca=self.ca, expected_checkpoint=None, draft=True
            )
            self.db.execute(
                "INSERT INTO events VALUES(?,?,?)",
                (len(events) - 1, event_id, canonical(event).decode()),
            )
        return event

    def checkpoint(self, signer: Signer) -> tuple[str, dict]:
        with self.transaction():
            self.validate()
            bundle = self.bundle()
            require(bool(bundle["events"]), "cannot checkpoint an empty ledger")
            for checkpoint in reversed(bundle["checkpoints"]):
                b = checkpoint["body"]
                if (
                    b["count"] == len(bundle["events"])
                    and b["key"] == signer.public_key
                    and b["actor"] == signer.actor
                ):
                    return digest(checkpoint), checkpoint
            body = {
                "domain": "TRACE-checkpoint-v1",
                "chain": self.trust["chain"],
                "count": len(bundle["events"]),
                "head": digest(bundle["events"][-1]),
                "actor": signer.actor,
                "key": signer.public_key,
                "created_ns": time.time_ns(),
            }
            checkpoint = signer.sign(body)
            bundle["checkpoints"].append(checkpoint)
            verify_bundle(
                bundle, self.trust, ca=self.ca, expected_checkpoint=None, draft=True
            )
            identity = digest(checkpoint)
            self.db.execute(
                "INSERT INTO checkpoints VALUES(?,?)",
                (identity, canonical(checkpoint).decode()),
            )
        return identity, checkpoint

    def prepare_anchor(self, checkpoint: str, provider: str) -> bytes:
        require(provider.startswith("https://"), "TSA provider must use HTTPS")
        with self.transaction():
            self.validate()
            require(
                self.db.execute(
                    "SELECT 1 FROM checkpoints WHERE id=?", (checkpoint,)
                ).fetchone(),
                "unknown checkpoint",
            )
            self.db.execute(
                "INSERT OR IGNORE INTO anchors VALUES(?,?,?,NULL)",
                (checkpoint, provider, make_request(checkpoint)),
            )
            row = self.db.execute(
                "SELECT provider,query FROM anchors WHERE checkpoint=?", (checkpoint,)
            ).fetchone()
            require(
                row["provider"] == provider, "checkpoint provider changed during retry"
            )
            return bytes(row["query"])

    def complete_anchor(self, checkpoint: str, response: bytes) -> dict:
        row = self.db.execute(
            "SELECT * FROM anchors WHERE checkpoint=?", (checkpoint,)
        ).fetchone()
        require(row is not None, "anchor request missing")
        if self.ca is None:
            raise TraceError("anchor CA missing")
        receipt = {
            "provider": row["provider"],
            "request": bytes(row["query"]).hex(),
            "response": response.hex(),
        }
        verify_timestamp(receipt, checkpoint, self.ca, self.trust)
        with self.transaction():
            self.validate()
            # An ambiguous retry can obtain another valid TSA token. Keep the first.
            self.db.execute(
                "UPDATE anchors SET response=? WHERE checkpoint=? AND response IS NULL",
                (response, checkpoint),
            )
        return self.bundle()["anchors"][checkpoint]

    def anchor(self, checkpoint: str, provider: str) -> dict:
        query = self.prepare_anchor(checkpoint, provider)
        existing = self.bundle()["anchors"].get(checkpoint)
        if existing:
            return existing
        response = submit(query, provider)
        return self.complete_anchor(checkpoint, response)

    def export(self, path: Path, checkpoint: str) -> dict:
        with self.transaction():
            bundle = self.bundle()
            report = verify_bundle(
                bundle, self.trust, ca=self.ca, expected_checkpoint=checkpoint
            )
        fd, name = tempfile.mkstemp(prefix=".trace-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(canonical(bundle))
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return report
