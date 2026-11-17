"""A live VN server plus scripted contacts, driven by an agent through JSON actions."""

import asyncio
import json
import os
import secrets
import shutil
import tempfile
import uuid
from urllib.parse import urlsplit

from aiohttp import ClientSession, WSMsgType
from aiohttp.test_utils import TestServer

from membra_sdk.vn.server import CALLS_KEY, activation_uri, create_app
from membra_sdk.vn.store import VNStore

# Calls are signaling-only here: no media flows, so SDP is a placeholder.
OFFER = {"type": "offer", "sdp": "v=0 vn-rl signaling only"}
ANSWER = {"type": "answer", "sdp": "v=0 vn-rl signaling only"}

OPS = {
    "activate": '{"op":"activate","url":"<activation link>"}',
    "contacts": '{"op":"contacts"}',
    "events": '{"op":"events"}  new texts, calls and hangups since last check',
    "inbox": '{"op":"inbox"}  full text history of this number',
    "send_text": '{"op":"send_text","to":"<name or number>","body":"..."}',
    "call": '{"op":"call","to":"<name or number>"}',
    "answer": '{"op":"answer","call_id":"..."}',
    "decline": '{"op":"decline","call_id":"..."}',
    "hangup": '{"op":"hangup","call_id":"..."}',
    "sign_out": '{"op":"sign_out"}',
    "submit": '{"op":"submit","answer":"..."}  ends the episode',
    "done": '{"op":"done"}  ends the episode',
}


class Phone:
    """One activated device on the VN server, connected over /ws."""

    def __init__(self, world: "World", number: str, token: str, on_event=None):
        self.world = world
        self.number = number
        self.token = token
        self.on_event = on_event
        self.events: list[dict] = []
        self.seen = 0
        self.calls: dict[str, str] = {}  # call_id -> peer number
        self.ws = None
        self._reader = None

    async def connect(self) -> None:
        self.ws = await self.world.http.ws_connect(self.world.base + "/ws")
        await self.ws.send_json({"type": "auth", "token": self.token})
        ready = await self.ws.receive_json(timeout=5)
        if ready.get("type") != "ready":
            raise RuntimeError(ready.get("error", "auth failed"))
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        async for raw in self.ws:
            if raw.type != WSMsgType.TEXT:
                continue
            ev = json.loads(raw.data)
            if ev.get("type") == "sms":
                await self.ws.send_json({"type": "ack", "id": ev["message"]["id"]})
            if ev.get("type") == "call":
                self.calls[ev["call_id"]] = ev["from"]
            self.events.append(ev)
            if self.on_event:
                await self.on_event(self, ev)

    async def send(self, payload: dict) -> None:
        await self.ws.send_json(payload)

    async def text(self, to: str, body: str) -> None:
        await self.send({"type": "sms", "to": to, "body": body})

    async def call(self, to: str) -> str:
        call_id = uuid.uuid4().hex[:12]
        self.calls[call_id] = to
        await self.send({"type": "call", "to": to, "call_id": call_id, "sdp": OFFER})
        return call_id

    async def close(self) -> None:
        if self.ws is not None and not self.ws.closed:
            await self.ws.close()
        if self._reader is not None:
            await asyncio.gather(self._reader, return_exceptions=True)


def _public(ev: dict) -> dict:
    return {k: v for k, v in ev.items() if k not in ("sdp", "candidate")}


class World:
    """Fresh server and database per episode. `phone` is the agent's device."""

    def __init__(self, rng, settle: float = 0.15):
        self.rng = rng
        self.settle_s = settle
        self.dir = tempfile.mkdtemp(prefix="vn-rl-")
        self.store = VNStore(os.path.join(self.dir, "vn.db"))
        self.contacts: dict[str, Phone] = {}
        self.others: list[Phone] = []
        self.phone: Phone | None = None
        self.agent: Phone | None = None  # stays set after sign-out, for scoring
        self.submitted: str | None = None
        self.state: dict = {}

    async def start(self) -> None:
        app = create_app(self.store, admin_token=secrets.token_urlsafe(16))
        self.server = TestServer(app, host="127.0.0.1")
        await self.server.start_server()
        self.base = str(self.server.make_url("/")).rstrip("/")
        self.http = ClientSession()

    @property
    def calls(self) -> dict:
        return self.server.app[CALLS_KEY]

    async def settle(self) -> None:
        await asyncio.sleep(self.settle_s)

    def issue(self, label: str = "") -> tuple[str, str, str]:
        """Returns (number, one-time code, activation link)."""
        issued = self.store.issue(label=label)
        uri = activation_uri(urlsplit(self.base).netloc, issued.code)
        return issued.number, issued.code, f"{self.base}/#{uri}"

    async def device(self, label: str, on_event=None) -> Phone:
        _, code, _ = self.issue(label)
        number, token = self.store.redeem(code)
        phone = Phone(self, number, token, on_event)
        await phone.connect()
        self.others.append(phone)
        return phone

    async def contact(self, name: str, on_event=None) -> Phone:
        self.contacts[name] = await self.device(name, on_event)
        return self.contacts[name]

    async def activate_agent(self) -> str:
        _, _, url = self.issue("agent")
        result = await self.act({"op": "activate", "url": url})
        return result["number"]

    def sent(self, sender: str, recipient: str) -> list[str]:
        return [
            m.body
            for m in self.store.history(sender)
            if m.sender == sender and m.recipient == recipient
        ]

    def _resolve(self, to) -> str:
        to = str(to or "").strip()
        for name, phone in self.contacts.items():
            if to.casefold() == name.casefold():
                return phone.number
        return to

    async def act(self, a: dict) -> dict:
        op = a.get("op")
        if op == "submit":
            self.submitted = str(a.get("answer", ""))
            return {"submitted": self.submitted}
        if op == "done":
            return {"ok": True}
        if op == "contacts":
            return {"contacts": {n: p.number for n, p in self.contacts.items()}}
        if op == "activate":
            return await self._activate(str(a.get("url", "")))
        if op not in OPS:
            return {"error": f"unknown op {op!r}", "ops": sorted(OPS)}
        phone = self.phone
        if phone is None:
            return {"error": "this phone has no number; activate one first"}
        if op == "events":
            await self.settle()
            new, phone.seen = phone.events[phone.seen :], len(phone.events)
            return {"events": [_public(e) for e in new]}
        if op == "inbox":
            r = await self.http.get(
                self.base + "/api/messages",
                headers={"Authorization": "Bearer " + phone.token},
            )
            if r.status != 200:
                return {"error": (await r.text()).strip()}
            return {"messages": await r.json()}
        if op == "send_text":
            start = len(phone.events)
            await phone.text(self._resolve(a.get("to")), str(a.get("body", "")))
            await self.settle()
            for ev in phone.events[start:]:
                if ev.get("type") in ("sent", "error"):
                    return _public(ev)
            return {"error": "no reply from server"}
        if op == "call":
            call_id = await phone.call(self._resolve(a.get("to")))
            await self.settle()
            return {"call_id": call_id}
        if op in ("answer", "decline", "hangup"):
            call_id = str(a.get("call_id", ""))
            peer = phone.calls.get(call_id)
            if peer is None:
                return {"error": f"unknown call_id {call_id!r}"}
            kind = {"answer": "answer", "decline": "reject", "hangup": "hangup"}[op]
            payload = {"type": kind, "to": peer, "call_id": call_id}
            if kind == "answer":
                payload["sdp"] = ANSWER
            await phone.send(payload)
            await self.settle()
            return {"ok": True}
        if op == "sign_out":
            r = await self.http.post(
                self.base + "/api/signout",
                headers={"Authorization": "Bearer " + phone.token},
            )
            await phone.close()
            self.phone = None
            return {"ok": r.status == 204}
        return {"error": f"unknown op {op!r}"}

    async def _activate(self, url: str) -> dict:
        if self.phone is not None:
            return {"error": "this phone already has a number"}
        parts = urlsplit(url).fragment.split("$")
        if len(parts) != 3 or parts[0] != "vn:1":
            return {"error": "not a VN activation link"}
        r = await self.http.post(self.base + "/api/activate", json={"code": parts[2]})
        if r.status != 200:
            return {"error": (await r.text()).strip()}
        data = await r.json()
        self.phone = self.agent = Phone(self, data["number"], data["token"])
        await self.phone.connect()
        await self.settle()
        return {"number": data["number"]}

    async def close(self) -> None:
        for phone in [self.phone, *self.others]:
            if phone is not None:
                await phone.close()
        await self.http.close()
        await self.server.close()
        shutil.rmtree(self.dir, ignore_errors=True)
