"""VN server: issues virtual numbers behind one-time QR activations and routes
texts and WebRTC call signaling between activated browser phones."""

import base64
import html
import io
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

import qrcode
from aiohttp import WSMsgType, web

from membra_sdk.vn.contracts import resolve_all
from membra_sdk.vn.store import ActivationError, VNStore

log = logging.getLogger("membra.vn")

STATIC_DIR = Path(__file__).parent / "static"
MAX_BODY = 1600
SIGNAL_TYPES = {"call", "answer", "ice", "hangup", "reject"}
DEFAULT_ICE = [{"urls": "stun:stun.l.google.com:19302"}]

STORE_KEY = web.AppKey("store", VNStore)
CONFIG_KEY = web.AppKey("config", dict)
ONLINE_KEY = web.AppKey("online", dict)
SESSIONS_KEY = web.AppKey("sessions", dict)
CALLS_KEY = web.AppKey("calls", dict)


def activation_uri(host: str, code: str) -> str:
    """eSIM-style activation string: vn:1$<server>$<one-time code>."""
    return f"vn:1${host}${code}"


def qr_png(text: str) -> bytes:
    buf = io.BytesIO()
    qrcode.make(text).save(buf, format="PNG")
    return buf.getvalue()


def _base_url(request: web.Request, configured: str | None) -> str:
    if configured:
        return configured.rstrip("/")
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    return f"{proto}://{host}"


def _bearer(request: web.Request) -> str:
    header = request.headers.get("Authorization", "")
    return header[7:] if header.startswith("Bearer ") else ""


def _require_admin(request: web.Request) -> None:
    admin = request.app[CONFIG_KEY]["admin_token"]
    if not admin or _bearer(request) != admin:
        raise web.HTTPUnauthorized(text="admin token required")


async def index(request: web.Request) -> web.Response:
    return web.FileResponse(STATIC_DIR / "index.html")


async def admin_page(request: web.Request) -> web.Response:
    return web.FileResponse(STATIC_DIR / "admin.html")


async def landing(request: web.Request) -> web.Response:
    page = (STATIC_DIR / "landing.html").read_text()
    contact = request.app[CONFIG_KEY].get("contact")
    if contact:
        meta = f'<meta name="vn-contact" content="{html.escape(contact, quote=True)}">'
        page = page.replace("<title>", meta + "\n<title>", 1)
    return web.Response(text=page, content_type="text/html")


async def contracts(request: web.Request) -> web.Response:
    _require_admin(request)
    return web.json_response(resolve_all(request.app[STORE_KEY]))


async def config(request: web.Request) -> web.Response:
    if not request.app[STORE_KEY].authenticate(_bearer(request)):
        raise web.HTTPUnauthorized(text="device token required")
    return web.json_response({"ice_servers": request.app[CONFIG_KEY]["ice_servers"]})


async def issue_number(request: web.Request) -> web.Response:
    _require_admin(request)
    data = await request.json() if request.can_read_body else {}
    store = request.app[STORE_KEY]
    try:
        issued = store.issue(
            label=str(data.get("label", ""))[:80], number=data.get("number")
        )
    except ActivationError as exc:
        raise web.HTTPNotFound(text=str(exc))
    base = _base_url(request, request.app[CONFIG_KEY]["public_url"])
    uri = activation_uri(urlsplit(base).netloc, issued.code)
    url = f"{base}/#{uri}"
    return web.json_response(
        {
            "number": issued.number,
            "activation_uri": uri,
            "activation_url": url,
            "expires_at": issued.expires_at,
            "qr_png": "data:image/png;base64," + base64.b64encode(qr_png(url)).decode(),
        }
    )


async def list_numbers(request: web.Request) -> web.Response:
    _require_admin(request)
    store = request.app[STORE_KEY]
    online = request.app[ONLINE_KEY]
    numbers = store.list_numbers()
    for n in numbers:
        n["online"] = bool(online.get(n["number"]))
    return web.json_response(numbers)


async def activate(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise web.HTTPBadRequest(text="json body required")
    try:
        number, token = request.app[STORE_KEY].redeem(str(data.get("code", "")))
    except ActivationError as exc:
        raise web.HTTPForbidden(text=str(exc))
    return web.json_response({"number": number, "token": token})


async def messages(request: web.Request) -> web.Response:
    store = request.app[STORE_KEY]
    number = store.authenticate(_bearer(request))
    if not number:
        raise web.HTTPUnauthorized(text="device token required")
    return web.json_response([m.to_dict() for m in store.history(number)])


async def signout(request: web.Request) -> web.Response:
    if not request.app[STORE_KEY].revoke_device(_bearer(request)):
        raise web.HTTPUnauthorized(text="device token required")
    return web.Response(status=204)


def _authorized(app: web.Application, ws) -> bool:
    sess = app[SESSIONS_KEY].get(ws)
    return bool(sess) and app[STORE_KEY].authenticate(sess["token"]) == sess["number"]


async def _kick(ws) -> None:
    try:
        await ws.send_json({"type": "error", "error": "unauthorized"})
    except (ConnectionResetError, RuntimeError):
        pass
    await ws.close()


async def _send_to(
    app: web.Application, number: str, payload: dict, exclude=None
) -> int:
    sent = 0
    for ws in list(app[ONLINE_KEY].get(number, ())):
        if ws is exclude:
            continue
        if not _authorized(app, ws):
            await _kick(ws)
            continue
        try:
            await ws.send_json(payload)
            sent += 1
        except (ConnectionResetError, RuntimeError):
            pass
    return sent


def _forget_call(app: web.Application, call_id: str) -> None:
    app[CALLS_KEY].pop(call_id, None)
    for sess in app[SESSIONS_KEY].values():
        sess["calls"].pop(call_id, None)


async def _deliver(app: web.Application, msg) -> None:
    # Stays pending until a phone acks it, so a half-dead socket can't swallow it.
    await _send_to(app, msg.recipient, {"type": "sms", "message": msg.to_dict()})


async def _handle(app: web.Application, number: str, ws, data: dict) -> None:
    store = app[STORE_KEY]
    kind = data.get("type")
    to = str(data.get("to", ""))
    if kind == "sms":
        body = str(data.get("body", ""))
        if not body or len(body) > MAX_BODY:
            await ws.send_json(
                {"type": "error", "error": f"body must be 1-{MAX_BODY} chars"}
            )
            return
        if not store.number_exists(to):
            await ws.send_json({"type": "error", "error": f"unknown number {to}"})
            return
        msg = store.add_message(number, to, body)
        await ws.send_json({"type": "sent", "message": msg.to_dict()})
        await _deliver(app, msg)
    elif kind in SIGNAL_TYPES:
        calls = app[CALLS_KEY]
        call_id = str(data.get("call_id", ""))
        ring = calls.get(call_id)
        if kind in ("answer", "reject") and ring and ring["callee"] == number:
            if ring["by"] is not None and ring["by"] is not ws:
                return  # another device on this number already took the call
            ring["ringing"].discard(ws)
            if kind == "reject" and data.get("busy"):
                if ring["ringing"]:
                    return  # other devices on this number are still ringing
            else:
                ring["by"] = ws
                ring["ringing"].clear()
                note = "answered" if kind == "answer" else "declined"
                await _send_to(
                    app,
                    number,
                    {
                        "type": "hangup",
                        "call_id": call_id,
                        "reason": f"{note} on another device",
                    },
                    exclude=ws,
                )
        payload = {
            k: v for k, v in data.items() if k in ("call_id", "sdp", "candidate")
        }
        payload.update(type=kind, **{"from": number})
        if kind == "reject" and data.get("busy"):
            payload["reason"] = "busy"
        if kind == "call":
            calls[call_id] = {
                "caller": number,
                "callee": to,
                "by": None,
                "ringing": set(app[ONLINE_KEY].get(to, ())),
            }
            app[SESSIONS_KEY][ws]["calls"][call_id] = to
        delivered = await _send_to(app, to, payload)
        if kind == "call" and not delivered:
            _forget_call(app, call_id)
            reason = "unknown number" if not store.number_exists(to) else "unavailable"
            await ws.send_json(
                {"type": "hangup", "call_id": data.get("call_id"), "reason": reason}
            )
        elif kind == "answer":
            app[SESSIONS_KEY][ws]["calls"][call_id] = to
        elif kind in ("hangup", "reject") and (
            ring is None or number in (ring["caller"], ring["callee"])
        ):
            _forget_call(app, call_id)
    elif kind == "ack":
        try:
            store.mark_delivered(int(data.get("id")), number)
        except (TypeError, ValueError):
            pass
    elif kind == "ping":
        await ws.send_json({"type": "pong"})
    else:
        await ws.send_json({"type": "error", "error": f"unknown type {kind}"})


async def websocket(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=25)
    await ws.prepare(request)
    app = request.app
    store = app[STORE_KEY]
    online: dict[str, set] = app[ONLINE_KEY]
    sessions: dict = app[SESSIONS_KEY]
    number = None
    try:
        first = await ws.receive(timeout=15)
        if first.type == WSMsgType.TEXT:
            auth = json.loads(first.data)
            if auth.get("type") == "auth":
                number = store.authenticate(str(auth.get("token", "")))
        if not number:
            await _kick(ws)
            return ws
        sessions[ws] = {"token": str(auth["token"]), "number": number, "calls": {}}
        online.setdefault(number, set()).add(ws)
        await ws.send_json({"type": "ready", "number": number})
        for msg in store.pending_for(number):
            await _deliver(app, msg)
        async for raw in ws:
            if raw.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(raw.data)
            except json.JSONDecodeError:
                continue
            if not _authorized(app, ws):
                await _kick(ws)
                break
            await _handle(app, number, ws, data)
    finally:
        sess = sessions.pop(ws, None)
        if number and ws in online.get(number, ()):
            online[number].discard(ws)
            if not online[number]:
                del online[number]
        if sess:
            await _drop_calls(app, number, ws, sess["calls"])
    return ws


async def _drop_calls(app: web.Application, number: str, ws, mine: dict) -> None:
    """Hang up calls a closed socket was in, so the other side doesn't ring on."""
    for call_id, peer in list(mine.items()):
        _forget_call(app, call_id)
        await _send_to(
            app,
            peer,
            {"type": "hangup", "call_id": call_id, "from": number, "reason": "ended"},
        )
    for call_id, ring in list(app[CALLS_KEY].items()):
        if ws in ring["ringing"]:
            ring["ringing"].discard(ws)
            if not ring["ringing"] and ring["by"] is None:
                _forget_call(app, call_id)
                await _send_to(
                    app,
                    ring["caller"],
                    {"type": "hangup", "call_id": call_id, "reason": "unavailable"},
                )


@web.middleware
async def security_headers(request: web.Request, handler):
    resp = await handler(request)
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Cache-Control", "no-store")
    return resp


def create_app(
    store: VNStore,
    admin_token: str | None = None,
    public_url: str | None = None,
    ice_servers: list[dict] | None = None,
    contact: str | None = None,
) -> web.Application:
    app = web.Application(middlewares=[security_headers])
    app[STORE_KEY] = store
    app[CONFIG_KEY] = {
        "admin_token": admin_token,
        "public_url": public_url,
        "ice_servers": ice_servers or DEFAULT_ICE,
        "contact": contact,
    }
    app[ONLINE_KEY] = {}
    app[SESSIONS_KEY] = {}
    app[CALLS_KEY] = {}
    app.router.add_get("/", index)
    app.router.add_get("/admin", admin_page)
    app.router.add_get("/landing", landing)
    app.router.add_get(r"/landing/{n:\d+}", landing)
    app.router.add_get("/api/contracts", contracts)
    app.router.add_get("/api/config", config)
    app.router.add_post("/api/numbers", issue_number)
    app.router.add_get("/api/numbers", list_numbers)
    app.router.add_post("/api/activate", activate)
    app.router.add_get("/api/messages", messages)
    app.router.add_post("/api/signout", signout)
    app.router.add_get("/ws", websocket)
    return app
