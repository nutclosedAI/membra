"""SQLite store for VN numbers, one-time activation codes, devices and messages."""

import hashlib
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS numbers (
    number TEXT PRIMARY KEY,
    label TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS activations (
    code_hash TEXT PRIMARY KEY,
    number TEXT NOT NULL REFERENCES numbers(number),
    expires_at REAL NOT NULL,
    redeemed_at REAL
);
CREATE TABLE IF NOT EXISTS devices (
    token_hash TEXT PRIMARY KEY,
    number TEXT NOT NULL REFERENCES numbers(number),
    created_at REAL NOT NULL,
    revoked_at REAL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at REAL NOT NULL,
    delivered_at REAL
);
CREATE INDEX IF NOT EXISTS messages_recipient ON messages(recipient, delivered_at);
"""


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class Issued:
    number: str
    code: str
    expires_at: float


@dataclass
class Message:
    id: int
    sender: str
    recipient: str
    body: str
    created_at: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.sender,
            "to": self.recipient,
            "body": self.body,
            "at": self.created_at,
        }


class ActivationError(Exception):
    pass


class VNStore:
    """Numbers live in a private range (default prefix +999) until a PSTN trunk is attached."""

    def __init__(self, path: str = "vn.db", prefix: str = "+999", digits: int = 8):
        self.prefix = prefix
        self.digits = digits
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._db.commit()

    def _new_number(self) -> str:
        while True:
            number = self.prefix + "".join(
                secrets.choice("0123456789") for _ in range(self.digits)
            )
            row = self._db.execute(
                "SELECT 1 FROM numbers WHERE number = ?", (number,)
            ).fetchone()
            if not row:
                return number

    def issue(
        self, label: str = "", ttl_seconds: int = 7 * 86400, number: str | None = None
    ) -> Issued:
        """Allocate a number (or reuse an existing one) and mint a one-time activation code."""
        code = secrets.token_urlsafe(18)
        now = time.time()
        with self._lock:
            if number is None:
                number = self._new_number()
                self._db.execute(
                    "INSERT INTO numbers (number, label, created_at) VALUES (?, ?, ?)",
                    (number, label, now),
                )
            elif not self.number_exists(number):
                raise ActivationError(f"unknown number {number}")
            self._db.execute(
                "INSERT INTO activations (code_hash, number, expires_at) VALUES (?, ?, ?)",
                (_hash(code), number, now + ttl_seconds),
            )
            self._db.commit()
        return Issued(number=number, code=code, expires_at=now + ttl_seconds)

    def redeem(self, code: str) -> tuple:
        """Spend an activation code once; returns (number, device_token)."""
        now = time.time()
        with self._lock:
            row = self._db.execute(
                "SELECT number, expires_at, redeemed_at FROM activations WHERE code_hash = ?",
                (_hash(code),),
            ).fetchone()
            if not row:
                raise ActivationError("invalid activation code")
            number, expires_at, redeemed_at = row
            if redeemed_at is not None:
                raise ActivationError("activation code already used")
            if expires_at < now:
                raise ActivationError("activation code expired")
            token = secrets.token_urlsafe(32)
            self._db.execute(
                "UPDATE activations SET redeemed_at = ? WHERE code_hash = ?",
                (now, _hash(code)),
            )
            self._db.execute(
                "INSERT INTO devices (token_hash, number, created_at) VALUES (?, ?, ?)",
                (_hash(token), number, now),
            )
            self._db.commit()
        return number, token

    def authenticate(self, token: str) -> str | None:
        row = self._db.execute(
            "SELECT number FROM devices WHERE token_hash = ? AND revoked_at IS NULL",
            (_hash(token),),
        ).fetchone()
        return row[0] if row else None

    def revoke_number_devices(self, number: str) -> int:
        with self._lock:
            cur = self._db.execute(
                "UPDATE devices SET revoked_at = ? WHERE number = ? AND revoked_at IS NULL",
                (time.time(), number),
            )
            self._db.commit()
            return cur.rowcount

    def revoke_device(self, token: str) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE devices SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (time.time(), _hash(token)),
            )
            self._db.commit()
            return cur.rowcount == 1

    def number_exists(self, number: str) -> bool:
        return (
            self._db.execute(
                "SELECT 1 FROM numbers WHERE number = ?", (number,)
            ).fetchone()
            is not None
        )

    def list_numbers(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT number, label, created_at FROM numbers ORDER BY created_at"
        ).fetchall()
        return [{"number": n, "label": label, "created_at": c} for n, label, c in rows]

    def add_message(self, sender: str, recipient: str, body: str) -> Message:
        now = time.time()
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO messages (sender, recipient, body, created_at) VALUES (?, ?, ?, ?)",
                (sender, recipient, body, now),
            )
            self._db.commit()
        return Message(cur.lastrowid, sender, recipient, body, now)

    def mark_delivered(self, message_id: int, recipient: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE messages SET delivered_at = ? "
                "WHERE id = ? AND recipient = ? AND delivered_at IS NULL",
                (time.time(), message_id, recipient),
            )
            self._db.commit()

    def pending_for(self, number: str) -> list[Message]:
        rows = self._db.execute(
            "SELECT id, sender, recipient, body, created_at FROM messages "
            "WHERE recipient = ? AND delivered_at IS NULL ORDER BY id",
            (number,),
        ).fetchall()
        return [Message(*r) for r in rows]

    def history(self, number: str, limit: int = 200) -> list[Message]:
        rows = self._db.execute(
            "SELECT id, sender, recipient, body, created_at FROM messages "
            "WHERE sender = ? OR recipient = ? ORDER BY id DESC LIMIT ?",
            (number, number, limit),
        ).fetchall()
        return [Message(*r) for r in reversed(rows)]
