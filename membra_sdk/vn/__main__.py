"""CLI: python -m membra_sdk.vn {serve,issue,list,revoke}"""

import argparse
import json
import os
import secrets
import sys
from urllib.parse import urlsplit

from aiohttp import web

from membra_sdk.vn.contracts import resolve_all
from membra_sdk.vn.server import activation_uri, create_app, qr_png
from membra_sdk.vn.store import VNStore


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m membra_sdk.vn")
    p.add_argument("--db", default=os.environ.get("VN_DB", "vn.db"))
    p.add_argument("--prefix", default=os.environ.get("VN_PREFIX", "+999"))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the VN server")
    s.add_argument(
        "--host",
        default=os.environ.get("VN_HOST", "127.0.0.1"),
        help="bind address; put a TLS proxy in front before exposing it publicly",
    )
    s.add_argument("--port", type=int, default=int(os.environ.get("VN_PORT", "8088")))
    s.add_argument("--public-url", default=os.environ.get("VN_PUBLIC_URL"))
    s.add_argument(
        "--contact",
        default=os.environ.get("VN_CONTACT"),
        help="email shown on the /landing pages",
    )
    s.add_argument(
        "--ice",
        default=os.environ.get("VN_ICE_SERVERS"),
        help='JSON list of RTCIceServer, e.g. [{"urls":"turn:host:3478","username":"u","credential":"p"}]',
    )

    i = sub.add_parser(
        "issue", help="allocate a number and write its one-time activation QR"
    )
    i.add_argument(
        "--public-url", required=True, help="https URL the phone page is served at"
    )
    i.add_argument("--label", default="")
    i.add_argument("--number", help="re-issue an activation for an existing number")
    i.add_argument(
        "--qr", default=None, help="PNG output path (default vn-<number>.png)"
    )

    sub.add_parser("list", help="list numbers")
    sub.add_parser("contracts", help="resolve the 12 VN event contracts")
    r = sub.add_parser("revoke", help="sign out every device on a number")
    r.add_argument("number")

    args = p.parse_args(argv)
    store = VNStore(args.db, prefix=args.prefix)

    if args.cmd == "serve":
        admin = os.environ.get("VN_ADMIN_TOKEN") or secrets.token_urlsafe(24)
        if "VN_ADMIN_TOKEN" not in os.environ:
            print(
                f"VN_ADMIN_TOKEN not set; generated for this run: {admin}",
                file=sys.stderr,
            )
        ice = json.loads(args.ice) if args.ice else None
        app = create_app(
            store,
            admin_token=admin,
            public_url=args.public_url,
            ice_servers=ice,
            contact=args.contact,
        )
        web.run_app(app, host=args.host, port=args.port)
    elif args.cmd == "issue":
        issued = store.issue(label=args.label, number=args.number)
        base = args.public_url.rstrip("/")
        url = f"{base}/#{activation_uri(urlsplit(base).netloc, issued.code)}"
        path = args.qr or f"vn-{issued.number.lstrip('+')}.png"
        with open(path, "wb") as f:
            f.write(qr_png(url))
        print(
            json.dumps(
                {"number": issued.number, "activation_url": url, "qr": path}, indent=2
            )
        )
    elif args.cmd == "list":
        print(json.dumps(store.list_numbers(), indent=2))
    elif args.cmd == "contracts":
        for c in resolve_all(store):
            print(
                f"{c['id']}  {c['status']:<4}  {c['value']:>7} / {c['threshold']:<7}"
                f"  {c['question']}"
            )
    elif args.cmd == "revoke":
        print(f"revoked {store.revoke_number_devices(args.number)} device(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
