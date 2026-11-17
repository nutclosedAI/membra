"""Yes/no event contracts on the VN network's own stats.

Each contract asks whether a counter reaches a threshold by a deadline and
resolves itself from the store: YES once the count as of the deadline reaches
the threshold, NO once the deadline passes without it, otherwise OPEN. They are
forecasting questions only; nothing is priced, traded or paid out.
"""

import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from membra_sdk.vn.store import VNStore

# metric -> SQL counting rows as of :until (unix seconds)
METRICS = {
    "numbers_issued": "SELECT COUNT(*) FROM numbers WHERE created_at <= :until",
    "devices_activated": "SELECT COUNT(*) FROM devices WHERE created_at <= :until",
    "devices_revoked": "SELECT COUNT(*) FROM devices WHERE revoked_at <= :until",
    "texts_sent": "SELECT COUNT(*) FROM messages WHERE created_at <= :until",
    "texts_delivered": "SELECT COUNT(*) FROM messages WHERE delivered_at <= :until",
    "active_senders": (
        "SELECT COUNT(DISTINCT sender) FROM messages WHERE created_at <= :until"
    ),
    "conversations": (
        "SELECT COUNT(*) FROM (SELECT DISTINCT MIN(sender, recipient), "
        "MAX(sender, recipient) FROM messages WHERE created_at <= :until)"
    ),
}


@dataclass(frozen=True)
class Contract:
    id: str
    question: str
    metric: str
    threshold: int
    deadline: str  # ISO date, end of day UTC
    below: bool = False  # True: YES if the count stays under the threshold


def _end_of_day(day: str) -> float:
    d = datetime.fromisoformat(day).replace(tzinfo=UTC)
    return d.timestamp() + 86400 - 1e-6


CONTRACTS = [
    Contract(
        "VN-01",
        "100 numbers issued by 2026-12-31?",
        "numbers_issued",
        100,
        "2026-12-31",
    ),
    Contract(
        "VN-02",
        "1,000 numbers issued by 2027-06-30?",
        "numbers_issued",
        1000,
        "2027-06-30",
    ),
    Contract(
        "VN-03",
        "50 devices activated by 2026-12-31?",
        "devices_activated",
        50,
        "2026-12-31",
    ),
    Contract(
        "VN-04",
        "500 devices activated by 2027-03-31?",
        "devices_activated",
        500,
        "2027-03-31",
    ),
    Contract(
        "VN-05", "1,000 texts sent by 2026-12-31?", "texts_sent", 1000, "2026-12-31"
    ),
    Contract(
        "VN-06", "100,000 texts sent by 2027-12-31?", "texts_sent", 100000, "2027-12-31"
    ),
    Contract(
        "VN-07",
        "10,000 texts delivered by 2027-03-31?",
        "texts_delivered",
        10000,
        "2027-03-31",
    ),
    Contract(
        "VN-08",
        "25 numbers have sent a text by 2026-12-31?",
        "active_senders",
        25,
        "2026-12-31",
    ),
    Contract(
        "VN-09",
        "250 numbers have sent a text by 2027-06-30?",
        "active_senders",
        250,
        "2027-06-30",
    ),
    Contract(
        "VN-10",
        "100 distinct conversations by 2027-03-31?",
        "conversations",
        100,
        "2027-03-31",
    ),
    Contract(
        "VN-11",
        "1,000 distinct conversations by 2027-12-31?",
        "conversations",
        1000,
        "2027-12-31",
    ),
    Contract(
        "VN-12",
        "Fewer than 10 devices revoked by 2026-12-31?",
        "devices_revoked",
        10,
        "2026-12-31",
        below=True,
    ),
]


def metric(store: VNStore, name: str, until: float) -> int:
    return store.scalar(METRICS[name], {"until": until})


def resolve(store: VNStore, contract: Contract, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    deadline = _end_of_day(contract.deadline)
    value = metric(store, contract.metric, min(now, deadline))
    hit, missed = ("NO", "YES") if contract.below else ("YES", "NO")
    if value >= contract.threshold:
        status = hit
    else:
        status = missed if now > deadline else "OPEN"
    return {**asdict(contract), "value": value, "status": status}


def resolve_all(store: VNStore, now: float | None = None) -> list[dict]:
    return [resolve(store, c, now) for c in CONTRACTS]
