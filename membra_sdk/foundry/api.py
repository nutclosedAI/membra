"""Authenticated, loopback-only developer API. Never accepts executable strategy code."""

from __future__ import annotations

import hmac
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .benchmark import Execution, Market
from .registry import Principal, Registry
from .tfl import compile_tfl, descendants


def make_server(
    registry: Registry,
    market: Market,
    credentials: dict[str, Principal],
    port: int = 8081,
    execution: Execution | None = None,
) -> ThreadingHTTPServer:
    if (
        not credentials
        or any(len(token) < 32 for token in credentials)
        or len({p.name for p in credentials.values()}) != len(credentials)
        or any(
            p.role
            not in {
                "inventor",
                "benchmark",
                "research",
                "adversary",
                "observer",
                "governor",
                "reader",
            }
            for p in credentials.values()
        )
    ):
        raise ValueError("unique principals and >=32 character bearer tokens required")
    execution = execution or Execution()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def reply(self, status: int, body: dict | list) -> None:
            payload = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def principal(self) -> Principal:
            header = self.headers.get("Authorization", "")
            token = (
                header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
            )
            for credential, principal in credentials.items():
                if hmac.compare_digest(token, credential):
                    return principal
            raise PermissionError("valid bearer credential required")

        def body(self) -> dict:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("chunked input unsupported")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 262144:
                raise ValueError("body size must be 1..262144 bytes")
            obj = json.loads(self.rfile.read(length))
            if not isinstance(obj, dict):
                raise ValueError("JSON object required")
            return obj

        def dispatch(self, method: str) -> None:
            try:
                path = self.path.strip("/").split("/")
                if method == "GET" and path == ["health"]:
                    self.reply(
                        200, {"status": "ok", "mode": "research_only", "broker": False}
                    )
                    return
                actor = self.principal()
                if method == "GET":
                    if path == ["catalogue"]:
                        # Publish capabilities and evidence labels, not private parameters.
                        result = [
                            {
                                "id": e["id"],
                                "state": e["state"],
                                "name": e["spec"]["strategy"]["name"],
                                "parent": e["spec"]["strategy"]["parent"],
                                "constraints": e["spec"]["constraints"],
                                "family": e["spec"]["policy"]["family"],
                                "license": e["license"],
                            }
                            for e in registry.catalogue()
                        ]
                    elif path == ["authority"]:
                        result = registry.authority()
                    elif path == ["events"]:
                        registry._role(actor, "governor")
                        result = registry.events()
                    elif len(path) == 2 and path[0] == "runs":
                        if actor.role not in {
                            "benchmark",
                            "research",
                            "adversary",
                            "governor",
                        }:
                            raise PermissionError("evidence review role required")
                        result = registry.report(path[1])
                    else:
                        self.reply(404, {"error": "unknown route"})
                        return
                    self.reply(200, result)
                    return
                obj = self.body()
                if path == ["compile"]:
                    registry._role(actor, "inventor")
                    policy = compile_tfl(obj)
                    result = {
                        "id": policy.identity,
                        "mode": "shadow",
                        "spec": policy.spec(),
                    }
                elif path == ["strategies"]:
                    result = {"id": registry.register(obj, actor)}
                elif len(path) == 3 and path[0] == "strategies" and path[2] == "derive":
                    registry._role(actor, "inventor")
                    result = {
                        "ids": [
                            registry.register(p.spec(), actor)
                            for p in descendants(registry.policy(path[1]), actor.name)
                        ]
                    }
                elif path == ["bootstrap"]:
                    result = registry.bootstrap(obj["policy"], actor)
                elif path == ["tournaments"]:
                    result = {
                        "run": registry.benchmark(
                            obj["policies"], market, execution, actor
                        )
                    }
                elif len(path) == 2 and path[0] == "reviews":
                    registry.review(path[1], obj, actor)
                    result = {"recorded": True}
                elif path == ["shadow"]:
                    result = {
                        "policy": registry.shadow(obj["run"], obj["epoch"], actor)
                    }
                elif path == ["promote"]:
                    result = registry.promote(
                        obj["policy"], obj["epoch"], obj["approval"], actor
                    )
                elif path == ["rollback"]:
                    result = registry.rollback(obj["epoch"], obj["reason"], actor)
                elif path == ["fit"]:
                    fitted = registry.fit(
                        obj["capital"], obj["max_drawdown"], obj["max_exposure"]
                    )
                    result = {
                        "matches": [
                            {"id": e["id"], "state": e["state"]}
                            for e in fitted["matches"]
                        ],
                        "allocation": None,
                        "warning": fitted["warning"],
                    }
                else:
                    self.reply(404, {"error": "unknown route"})
                    return
                self.reply(200, result)
            except PermissionError as exc:
                self.reply(403, {"error": str(exc)})
            except sqlite3.IntegrityError:
                self.reply(
                    409,
                    {
                        "error": "immutable record already exists or dataset already consumed"
                    },
                )
            except (
                ValueError,
                KeyError,
                TypeError,
                OverflowError,
                UnicodeError,
            ) as exc:
                self.reply(400, {"error": str(exc)})

        def do_GET(self) -> None:
            self.dispatch("GET")

        def do_POST(self) -> None:
            self.dispatch("POST")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
