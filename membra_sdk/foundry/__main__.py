"""python -m membra_sdk.foundry --help"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import secrets
import sys
import urllib.parse
import urllib.request
from dataclasses import replace
from pathlib import Path

from .api import make_server
from .benchmark import Execution, Market, simulate
from .receipts import Issuer, verify_chain
from .registry import Principal, Registry
from .research import prior_art
from .tfl import baseline, canonical, descendants, digest


def save(path: str | Path, obj: object) -> None:
    Path(path).write_bytes(canonical(obj) + b"\n")


def fetch(path: str, hours: int) -> None:
    if not 2000 <= hours <= 12000:
        raise ValueError("2000..12000 hours required")
    now = dt.datetime.now(dt.timezone.utc)
    end = now.replace(minute=0, second=0, microsecond=0) - dt.timedelta(hours=1)
    rows: dict[int, list] = {}
    for offset in range(0, hours, 300):
        stop = end - dt.timedelta(hours=offset)
        start = stop - dt.timedelta(hours=min(300, hours - offset))
        url = (
            "https://api.exchange.coinbase.com/products/BTC-USD/candles?"
            + urllib.parse.urlencode(
                {
                    "granularity": 3600,
                    "start": start.isoformat(),
                    "end": stop.isoformat(),
                }
            )
        )
        req = urllib.request.Request(url, headers={"User-Agent": "membra-foundry/1"})
        with urllib.request.urlopen(req, timeout=30) as response:
            for row in json.load(response):
                if start.timestamp() <= row[0] <= end.timestamp():
                    rows[row[0]] = row
    raw = sorted(rows.values())[-hours:]
    cut = 0
    for i in range(1, len(raw)):
        if raw[i][0] - raw[i - 1][0] != 3600:
            cut = i
    save(
        path,
        {
            "instrument": "BTC-USD",
            "source": "https://api.exchange.coinbase.com/products/BTC-USD/candles",
            "granularity": 3600,
            "fields": ["time", "low", "high", "open", "close", "volume"],
            "fetched_at": now.isoformat(),
            "requested_hours": hours,
            "excluded_before_last_gap": cut,
            "raw_candles_sha256": digest(raw),
            "candles": raw[cut:],
        },
    )


def experiment(data: str, db: str, output: str, research: bool) -> dict:
    market = Market.load(data)
    registry = Registry(db)
    # Roles describe actual deterministic code, not invented LLM agents.
    inventor = Principal("bounded-search", "inventor")
    governor = Principal("initial-risk-operator", "governor")
    evaluator = Principal("deterministic-benchmark", "benchmark")
    cash = replace(baseline("cash"), author=inventor.name)
    inventory = replace(baseline("inventory"), author=inventor.name)
    policies = [cash, inventory, *descendants(inventory, inventor.name)]
    for policy in policies:
        registry.register(policy.spec(), inventor)
    registry.bootstrap(cash.identity, governor)
    run_id = registry.benchmark(
        [p.identity for p in policies], market, Execution(), evaluator
    )
    report = registry.report(run_id)
    report["run_id"] = run_id
    report["environment"] = {
        "python": sys.version,
        "platform": platform.platform(),
        "dataset_file_sha256": hashlib.sha256(Path(data).read_bytes()).hexdigest(),
    }
    if research:
        try:
            report["prior_art_retrieval"] = prior_art()
        except (OSError, ValueError) as exc:
            report["prior_art_retrieval"] = {
                "status": "unavailable",
                "error": str(exc),
                "certified": False,
            }
    # Real backtest decisions get audit receipts, explicitly NOT live-use receipts.
    result = simulate(cash, market, 168, min(200, len(market.candles) - 1), Execution())
    issuer, receipts, openings = Issuer.generate(), [], []
    for i, action in enumerate(result["actions"]):
        receipt, opening = issuer.issue(
            policy=cash.identity,
            license_id="historical-research-only",
            decision_id=f"{run_id}:{i}",
            timestamp=action["time"],
            action=action,
            risk_gate=action["risk_gate"],
            kpi={"net_bar_return": result["returns"][i]},
            market_commitment=digest(market.candles[168 + i - 1]),
            previous=receipts[-1] if receipts else None,
        )
        receipts.append(receipt)
        openings.append(opening)
    checkpoint = {
        "expected_policy": cash.identity,
        "expected_license": "historical-research-only",
        "expected_count": len(receipts),
        "expected_head": digest(receipts[-1]),
    }
    report["taw"] = {
        "public_key": issuer.public_key,
        "checkpoint": checkpoint,
        "verified": verify_chain(receipts, issuer.public_key, **checkpoint),
        "scope": "ephemeral local issuer; pin key and checkpoint independently in production",
    }
    report["authority"] = registry.authority()
    report["governance"] = (
        "no independent reviews or real shadow observations; no promotion"
    )
    save(output, report)
    save(
        str(Path(output).with_suffix(".receipts.json")),
        {
            "receipts": receipts,
            "authorized_auditor_openings": openings,
            "public_key": issuer.public_key,
            "checkpoint": checkpoint,
        },
    )
    registry.close()
    return {
        "run": run_id,
        "trials": len(policies),
        "shadow_candidate": report["shadow_candidate"],
        "promotion": False,
        "taw_verified": report["taw"]["verified"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser(
        "fetch", help="download real Coinbase BTC-USD hourly history"
    )
    download.add_argument("--output", required=True)
    download.add_argument("--hours", type=int, default=6000)
    run = commands.add_parser(
        "run", help="one sealed historical experiment; never trades"
    )
    run.add_argument("--data", required=True)
    run.add_argument("--db", required=True)
    run.add_argument("--output", required=True)
    run.add_argument(
        "--research", action="store_true", help="retrieve live arXiv prior-art metadata"
    )
    api = commands.add_parser(
        "serve", help="loopback developer API; tokens from FOUNDRY_CREDENTIALS"
    )
    api.add_argument("--data", required=True)
    api.add_argument("--db", required=True)
    api.add_argument("--port", type=int, default=8081)
    commands.add_parser(
        "token", help="generate a credential; keep it out of source control"
    )
    args = parser.parse_args()
    if args.command == "fetch":
        fetch(args.output, args.hours)
    elif args.command == "run":
        print(json.dumps(experiment(args.data, args.db, args.output, args.research)))
    elif args.command == "token":
        print(secrets.token_urlsafe(32))
    else:
        config = json.loads(os.environ["FOUNDRY_CREDENTIALS"])
        credentials = {
            token: Principal(record["name"], record["role"])
            for token, record in config.items()
        }
        registry = Registry(args.db)
        server = make_server(registry, Market.load(args.data), credentials, args.port)
        try:
            print("Research-only API; no broker integration. Ctrl-C to stop.")
            server.serve_forever()
        finally:
            server.server_close()
            registry.close()


if __name__ == "__main__":
    main()
