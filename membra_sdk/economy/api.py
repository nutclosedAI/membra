"""Universal Outcome API — HTTP surface over the economic graph.

Pure stdlib (`http.server`) — no framework dependency, deployable as
`python -m membra_sdk.economy.api` or `serve(graph, port)`.

    POST /promises               {type, conditions[], deadline?, terms?}
                                 -> creates act, returns economic_act_id
    POST /obligations            {act_id, max_value, currency} -> authorize
    POST /evidence               {act_id, source}              -> tag source
    POST /observations           {act_id, values{}, observed_at?}
    POST /outcomes/evaluate      {act_id, quality_hint?, reliability_hint?}
                                 -> classify the outcome
    POST /state-transitions      {act_id, policy?}             -> transition
    POST /consequences           {act_id, type, amount, reason} -> manual

    GET  /acts/:id               -> full EconomicStateObject
    GET  /acts/:id/state         -> settlement.status + outcome.state
    GET  /acts/:id/outcome       -> outcome block
    GET  /acts/:id/evidence      -> observation block
    GET  /acts/:id/causal-chain  -> ordered stage chain  <- the killer route
    GET  /graph/summary          -> counts by outcome/consequence
    GET  /dataset                -> D = {(P,E,O,C)} rows for archetype mining

Not a payment API — an economic causality API.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .graph import EconomicGraph
from .outcome import evaluate_outcome
from .state import Authorization, EconomicStateObject, Promise
from .transitions import Policy, transition


class _Handler(BaseHTTPRequestHandler):
    graph: EconomicGraph  # class attribute set by serve()

    # ---------------- plumbing ----------------

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}

    def _send(self, obj, code: int = 200) -> None:
        data = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _act(self, act_id: str) -> EconomicStateObject | None:
        return self.graph.get(act_id)

    def log_message(self, *args):  # quiet
        return

    # ---------------- GET ----------------

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        parts = [p for p in path.split("/") if p]
        g = self.graph

        if path == "/graph/summary":
            return self._send(g.summary())
        if path == "/dataset":
            return self._send({"rows": g.outcome_dataset()})
        if len(parts) >= 2 and parts[0] == "acts":
            act = self._act(parts[1])
            if act is None:
                return self._send({"error": f"act {parts[1]} not found"}, 404)
            if len(parts) == 2:
                return self._send(act.to_dict())
            sub = parts[2]
            if sub == "state":
                return self._send(
                    {
                        "settlement_status": act.settlement.status.value,
                        "outcome_state": act.outcome.state.value,
                        "consequence": act.consequence.type.value,
                        "open": True,  # S_t != FINAL — never terminal
                    }
                )
            if sub == "outcome":
                return self._send(act.to_dict()["outcome"])
            if sub == "evidence":
                return self._send(act.to_dict()["observation"])
            if sub == "causal-chain":
                chain = g.causal_chain(act.economic_act_id)
                chain["children"] = [
                    c.economic_act_id for c in g.children_of(act.economic_act_id)
                ]
                return self._send(chain)
            return self._send({"error": f"unknown subresource {sub}"}, 404)
        return self._send({"error": "not found"}, 404)

    # ---------------- POST ----------------

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        body = self._body()
        g = self.graph

        if path == "/promises":
            promise = Promise(
                type=body.get("type", "SERVICE"),
                conditions=list(body.get("conditions", [])),
                deadline=body.get("deadline"),
                terms=dict(body.get("terms", {})),
            )
            act = EconomicStateObject(
                promise=promise,
                authorization=Authorization(
                    max_value=float(body.get("max_value", 0.0)),
                    currency=body.get("currency", "USD"),
                ),
            )
            act.record("INTENT", {"via": "POST /promises"})
            g.add(act)
            return self._send({"economic_act_id": act.economic_act_id}, 201)

        if path == "/obligations":
            act = self._act(body.get("act_id", ""))
            if act is None:
                return self._send({"error": "act not found"}, 404)
            act.authorization.max_value = float(body.get("max_value", 0.0))
            act.authorization.currency = body.get(
                "currency", act.authorization.currency
            )
            act.authorize()
            if body.get("hold"):
                act.hold(act.authorization.max_value)
            else:
                act.settle(act.authorization.max_value)
            return self._send(act.to_dict()["settlement"])

        if path == "/evidence":
            act = self._act(body.get("act_id", ""))
            if act is None:
                return self._send({"error": "act not found"}, 404)
            act.observation.source = body.get("source", act.observation.source)
            act.record("EVIDENCE", {"source": act.observation.source})
            return self._send(act.to_dict()["observation"])

        if path == "/observations":
            act = self._act(body.get("act_id", ""))
            if act is None:
                return self._send({"error": "act not found"}, 404)
            act.observe(dict(body.get("values", {})), source=body.get("source"))
            if body.get("observed_at"):
                act.observation.observed_at = float(body["observed_at"])
            return self._send(act.to_dict()["observation"])

        if path == "/outcomes/evaluate":
            act = self._act(body.get("act_id", ""))
            if act is None:
                return self._send({"error": "act not found"}, 404)
            outcome = evaluate_outcome(
                act,
                quality_hint=body.get("quality_hint"),
                reliability_hint=float(body.get("reliability_hint", 0.7)),
            )
            act.classify(outcome)
            return self._send(act.to_dict()["outcome"])

        if path == "/state-transitions":
            act = self._act(body.get("act_id", ""))
            if act is None:
                return self._send({"error": "act not found"}, 404)
            policy = Policy(
                compensation_rate=float(body.get("compensation_rate", 0.25)),
                min_confidence=float(body.get("min_confidence", 0.5)),
                dispute_on_failure=bool(body.get("dispute_on_failure", True)),
            )
            _, spawned = transition(act, policy, quality_hint=body.get("quality_hint"))
            if spawned is not None:
                g.add(spawned)
            return self._send(
                {
                    "act": act.to_dict(),
                    "spawned_act": spawned.economic_act_id if spawned else None,
                }
            )

        if path == "/consequences":
            act = self._act(body.get("act_id", ""))
            if act is None:
                return self._send({"error": "act not found"}, 404)
            from .state import Consequence, ConsequenceType

            cons = Consequence(
                type=ConsequenceType(body.get("type", "COMPENSATION")),
                amount=float(body.get("amount", 0.0)),
                currency=body.get("currency", "USD"),
                reason=body.get("reason"),
            )
            act.apply_consequence(cons)
            return self._send(act.to_dict()["consequence"])

        return self._send({"error": "not found"}, 404)


def make_server(graph: EconomicGraph | None = None, port: int = 8080):
    """Bind a ThreadingHTTPServer sharing `graph`."""
    handler = type("OutcomeHandler", (_Handler,), {"graph": graph or EconomicGraph()})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(
    graph: EconomicGraph | None = None, port: int = 8080
) -> None:  # pragma: no cover
    server = make_server(graph, port)
    print(f"Outcome API on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    serve()
