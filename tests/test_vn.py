"""Tests for membra_sdk.vn: one-time activation, texts, and call signaling."""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aiohttp.test_utils import TestClient, TestServer

from membra_sdk.vn import ActivationError, VNStore, create_app

ADMIN = "admin-test-token"


def _store():
    return VNStore(os.path.join(tempfile.mkdtemp(), "vn.db"))


async def _client(store):
    client = TestClient(TestServer(create_app(store, admin_token=ADMIN)))
    await client.start_server()
    return client


async def _issue(client):
    r = await client.post(
        "/api/numbers", json={}, headers={"Authorization": f"Bearer {ADMIN}"}
    )
    assert r.status == 200, await r.text()
    return await r.json()


async def _activate(client, issued):
    code = issued["activation_uri"].split("$", 2)[2]
    r = await client.post("/api/activate", json={"code": code})
    assert r.status == 200, await r.text()
    return await r.json()


async def _phone(client, token):
    ws = await client.ws_connect("/ws")
    await ws.send_json({"type": "auth", "token": token})
    ready = await ws.receive_json(timeout=5)
    assert ready["type"] == "ready"
    return ws


def test_store_code_is_single_use():
    store = _store()
    issued = store.issue()
    assert issued.number.startswith("+999") and len(issued.number) == 12
    number, token = store.redeem(issued.code)
    assert number == issued.number and store.authenticate(token) == number
    try:
        store.redeem(issued.code)
        raise AssertionError("code redeemed twice")
    except ActivationError:
        pass
    assert store.revoke_number_devices(number) == 1
    assert store.authenticate(token) is None


def test_store_expired_code():
    store = _store()
    issued = store.issue(ttl_seconds=-1)
    try:
        store.redeem(issued.code)
        raise AssertionError("expired code accepted")
    except ActivationError as exc:
        assert "expired" in str(exc)


async def _api_flow():
    client = await _client(_store())
    try:
        r = await client.post("/api/numbers", json={})
        assert r.status == 401
        issued = await _issue(client)
        assert issued["activation_url"].endswith("#" + issued["activation_uri"])
        assert issued["qr_png"].startswith("data:image/png;base64,")
        dev = await _activate(client, issued)
        code = issued["activation_uri"].split("$", 2)[2]
        r = await client.post("/api/activate", json={"code": code})
        assert r.status == 403
        r = await client.get(
            "/api/messages", headers={"Authorization": f"Bearer {dev['token']}"}
        )
        assert r.status == 200 and await r.json() == []
        r = await client.get("/")
        assert r.status == 200 and "VN phone" in await r.text()
    finally:
        await client.close()


async def _messaging_and_calls():
    client = await _client(_store())
    try:
        a = await _activate(client, await _issue(client))
        b = await _activate(client, await _issue(client))
        wa = await _phone(client, a["token"])

        await wa.send_json({"type": "sms", "to": b["number"], "body": "hello"})
        sent = await wa.receive_json(timeout=5)
        assert sent["type"] == "sent" and sent["message"]["to"] == b["number"]

        wb = await _phone(client, b["token"])
        queued = await wb.receive_json(timeout=5)
        assert queued["type"] == "sms" and queued["message"]["body"] == "hello"
        assert queued["message"]["from"] == a["number"]
        await wb.close()
        wb = await _phone(client, b["token"])
        resent = await wb.receive_json(timeout=5)
        assert resent["message"]["id"] == queued["message"]["id"]
        await wb.send_json({"type": "ack", "id": resent["message"]["id"]})

        await wb.send_json({"type": "sms", "to": a["number"], "body": "hi back"})
        assert (await wb.receive_json(timeout=5))["type"] == "sent"
        live = await wa.receive_json(timeout=5)
        assert live["type"] == "sms" and live["message"]["body"] == "hi back"

        offer = {"type": "offer", "sdp": "v=0"}
        await wa.send_json(
            {"type": "call", "to": b["number"], "call_id": "c1", "sdp": offer}
        )
        ring = await wb.receive_json(timeout=5)
        assert ring == {
            "type": "call",
            "from": a["number"],
            "call_id": "c1",
            "sdp": offer,
        }
        await wb.send_json(
            {"type": "answer", "to": a["number"], "call_id": "c1", "sdp": offer}
        )
        assert (await wa.receive_json(timeout=5))["type"] == "answer"

        await wb.close()
        dropped = await wa.receive_json(timeout=5)
        assert dropped["type"] == "hangup" and dropped["call_id"] == "c1"
        await wa.send_json(
            {"type": "call", "to": b["number"], "call_id": "c2", "sdp": offer}
        )
        miss = await wa.receive_json(timeout=5)
        assert miss == {"type": "hangup", "call_id": "c2", "reason": "unavailable"}

        await wa.send_json({"type": "sms", "to": "+99900000000", "body": "x"})
        assert (await wa.receive_json(timeout=5))["type"] == "error"

        bad = await client.ws_connect("/ws")
        await bad.send_json({"type": "auth", "token": "nope"})
        assert (await bad.receive_json(timeout=5))["error"] == "unauthorized"
        await wa.close()
    finally:
        await client.close()


async def _devices_and_calls():
    client = await _client(_store())
    try:
        a = await _activate(client, await _issue(client))
        b_issued = await _issue(client)
        b1 = await _activate(client, b_issued)
        b2 = await _activate(
            client,
            await (
                await client.post(
                    "/api/numbers",
                    json={"number": b_issued["number"]},
                    headers={"Authorization": f"Bearer {ADMIN}"},
                )
            ).json(),
        )
        r = await client.get("/api/config")
        assert r.status == 401
        r = await client.get(
            "/api/config", headers={"Authorization": f"Bearer {a['token']}"}
        )
        assert r.status == 200 and "ice_servers" in await r.json()

        wa = await _phone(client, a["token"])
        w1 = await _phone(client, b1["token"])
        w2 = await _phone(client, b2["token"])
        to_b = b_issued["number"]

        # one busy device must not decline for the other; answering stops the rest
        await wa.send_json({"type": "call", "to": to_b, "call_id": "c1", "sdp": {}})
        assert (await w1.receive_json(timeout=5))["type"] == "call"
        assert (await w2.receive_json(timeout=5))["type"] == "call"
        await w2.send_json(
            {"type": "reject", "to": a["number"], "call_id": "c1", "busy": True}
        )
        await w1.send_json({"type": "answer", "to": a["number"], "call_id": "c1"})
        assert (await wa.receive_json(timeout=5))["type"] == "answer"
        stop = await w2.receive_json(timeout=5)
        assert stop["type"] == "hangup" and stop["call_id"] == "c1"
        await w2.send_json({"type": "reject", "to": a["number"], "call_id": "c1"})
        await wa.send_json({"type": "ping"})
        assert (await wa.receive_json(timeout=5))["type"] == "pong"

        # caller closing mid-ring hangs up both ringing devices
        wa2 = await _phone(client, a["token"])
        await wa2.send_json({"type": "call", "to": to_b, "call_id": "c2", "sdp": {}})
        assert (await w1.receive_json(timeout=5))["call_id"] == "c2"
        assert (await w2.receive_json(timeout=5))["call_id"] == "c2"
        await wa2.close()
        for w in (w1, w2):
            gone = await w.receive_json(timeout=5)
            assert gone["type"] == "hangup" and gone["call_id"] == "c2"

        # sign-out revokes the token; a live socket of a revoked device is dropped
        r = await client.post(
            "/api/signout", headers={"Authorization": f"Bearer {b2['token']}"}
        )
        assert r.status == 204
        r = await client.get(
            "/api/messages", headers={"Authorization": f"Bearer {b2['token']}"}
        )
        assert r.status == 401
        await w2.send_json({"type": "sms", "to": a["number"], "body": "x"})
        assert (await w2.receive_json(timeout=5))["error"] == "unauthorized"
        for w in (wa, w1, w2):
            await w.close()
    finally:
        await client.close()


def test_contracts_resolve():
    from membra_sdk.vn.contracts import CONTRACTS, resolve, resolve_all

    store = _store()
    assert len(CONTRACTS) == 12 and len({c.id for c in CONTRACTS}) == 12
    a, b = store.issue().number, store.issue().number
    store.add_message(a, b, "hi")
    store.add_message(b, a, "yo")
    by_id = {c.id: c for c in CONTRACTS}
    early = resolve(store, by_id["VN-01"], now=0)
    assert early["status"] == "OPEN" and early["value"] == 0
    assert resolve(store, by_id["VN-01"])["value"] == 2
    late = resolve(store, by_id["VN-01"], now=4102444800)
    assert late["status"] == "NO"
    assert resolve(store, by_id["VN-10"])["value"] == 1
    assert resolve(store, by_id["VN-12"], now=4102444800)["status"] == "YES"
    assert {r["status"] for r in resolve_all(store)} <= {"OPEN", "YES", "NO"}


async def _landing_and_contracts_api():
    client = TestClient(
        TestServer(create_app(_store(), admin_token=ADMIN, contact="hi@example.com"))
    )
    await client.start_server()
    try:
        for path in ("/landing", "/landing/7", "/landing/12"):
            r = await client.get(path)
            text = await r.text()
            assert r.status == 200 and 'content="hi@example.com"' in text
        assert (await client.get("/api/contracts")).status == 401
        r = await client.get(
            "/api/contracts", headers={"Authorization": f"Bearer {ADMIN}"}
        )
        assert r.status == 200 and len(await r.json()) == 12
    finally:
        await client.close()


def test_landing_and_contracts_api():
    asyncio.run(_landing_and_contracts_api())


def test_api_flow():
    asyncio.run(_api_flow())


def test_messaging_and_calls():
    asyncio.run(_messaging_and_calls())


def test_devices_and_calls():
    asyncio.run(_devices_and_calls())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
