"""membra-trace: no server connection is used by verify or inspect."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .crypto import TraceError, load_json, require
from .ledger import Ledger
from .verify import verify_bundle

MAX_BUNDLE_BYTES = 32_000_000


def read(path: Path) -> dict:
    require(path.stat().st_size <= MAX_BUNDLE_BYTES, "input exceeds 32 MB limit")
    with path.open("rb") as stream:
        data = stream.read(MAX_BUNDLE_BYTES + 1)
    require(len(data) <= MAX_BUNDLE_BYTES, "input exceeds 32 MB limit")
    value = load_json(data)
    require(isinstance(value, dict), "input must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="membra-trace")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Unverified bundle inventory")
    inspect.add_argument("bundle", type=Path)
    verify = sub.add_parser(
        "verify", help="Strict offline verification, including external time"
    )
    verify.add_argument("bundle", type=Path)
    verify.add_argument("--trust", required=True, type=Path)
    verify.add_argument(
        "--checkpoint", required=True, help="Expected digest obtained independently"
    )
    verify.add_argument("--tsa-ca", required=True, type=Path)
    anchor = sub.add_parser(
        "anchor", help="Explicit network operation; resume a prepared timestamp request"
    )
    anchor.add_argument("database", type=Path)
    anchor.add_argument("--trust", required=True, type=Path)
    anchor.add_argument("--checkpoint", required=True)
    anchor.add_argument("--tsa-ca", required=True, type=Path)
    anchor.add_argument("--provider", required=True)
    export = sub.add_parser("export", help="Atomically export a fully verified bundle")
    export.add_argument("database", type=Path)
    export.add_argument("output", type=Path)
    export.add_argument("--trust", required=True, type=Path)
    export.add_argument("--checkpoint", required=True)
    export.add_argument("--tsa-ca", required=True, type=Path)
    args = parser.parse_args(argv)
    ledger = None
    try:
        if args.command == "inspect":
            bundle = read(args.bundle)
            result = {
                "verified": False,
                "format": bundle.get("format"),
                "events": len(bundle.get("events", [])),
                "checkpoints": len(bundle.get("checkpoints", [])),
                "anchors": len(bundle.get("anchors", {})),
            }
        elif args.command == "verify":
            result = verify_bundle(
                read(args.bundle),
                read(args.trust),
                expected_checkpoint=args.checkpoint,
                ca=args.tsa_ca,
            )
        else:
            require(args.database.is_file(), "database does not exist")
            ledger = Ledger(args.database, read(args.trust), args.tsa_ca)
            if args.command == "anchor":
                ledger.anchor(args.checkpoint, args.provider)
                result = {"anchored_checkpoint": args.checkpoint}
            else:
                result = ledger.export(args.output, args.checkpoint)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (
        TraceError,
        OSError,
        sqlite3.DatabaseError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        RecursionError,
    ) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}), file=sys.stderr)
        return 1
    finally:
        if ledger:
            ledger.close()


if __name__ == "__main__":
    sys.exit(main())
