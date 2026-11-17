"""Twelve VN tasks. Each is scored from server state, and each has a scripted
oracle that solves it through the same JSON actions an agent uses."""

import asyncio
import json
import re
import string
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from membra_sdk.vn.rl.world import ANSWER, Phone, World

TEXTS = [
    "Running 10 minutes late, start without me.",
    "Can you pick up milk on the way home?",
    "The package arrived, thanks!",
    "Meeting room changed to 4B.",
]
FORWARDS = [
    "Dinner at Luigi's, 7:30, table under Sam.",
    "Flight AA 2291 lands 6:05pm at gate C14.",
    "Wifi is vn-guest, password is orchard-42.",
]
BROADCASTS = ["Standup moved to 3pm.", "Office closed Friday.", "Party is on!"]
SIGNOFF = "I'm switching phones, this number is going quiet."


@dataclass(frozen=True)
class Task:
    id: int
    name: str
    setup: Callable[[World], Awaitable[dict]]
    check: Callable[[World], bool]
    oracle: Callable[[Callable[..., dict], dict], None]


async def _phone_with(w: World, *names: str, hooks: dict | None = None) -> dict:
    number = await w.activate_agent()
    for name in names:
        await w.contact(name, (hooks or {}).get(name))
    await w.settle()
    return {
        "your_number": number,
        "contacts": {n: p.number for n, p in w.contacts.items()},
    }


def _sent(w: World, name: str, exact: str | None = None, has: str | None = None):
    if w.agent is None:
        return False
    bodies = [b.strip() for b in w.sent(w.agent.number, w.contacts[name].number)]
    if exact is not None:
        return exact in bodies
    return any(has in b for b in bodies)


def _signal(phone: Phone, kind: str, call_id: str) -> bool:
    return any(
        e.get("type") == kind and e.get("call_id") == call_id for e in phone.events
    )


def _quoted(obs: dict) -> str:
    return re.search(r'"(.+)"', obs["instruction"]).group(1)


def _wait(do, pred, tries: int = 20) -> dict:
    for _ in range(tries):
        for ev in do(op="events").get("events", []):
            if pred(ev):
                return ev
    return {}


def _inbox(do) -> list[dict]:
    return do(op="inbox").get("messages", [])


# 1. activate
async def activate_setup(w: World) -> dict:
    number, _, url = w.issue("agent")
    w.state["target"] = number
    return {"instruction": "Activate this phone with the QR link below.", "qr": url}


def activated(w: World) -> bool:
    a = w.agent
    return (
        bool(a)
        and a.number == w.state["target"]
        and bool(w.store.authenticate(a.token))
    )


def activate_oracle(do, obs):
    do(op="activate", url=obs["qr"])


# 2. spent QR
async def spent_setup(w: World) -> dict:
    _, used_code, used = w.issue("old phone")
    w.store.redeem(used_code)
    number, _, fresh = w.issue("agent")
    w.state["target"] = number
    links = [used, fresh]
    w.rng.shuffle(links)
    return {
        "instruction": "One of these QR links was already used on another phone. "
        "Activate this phone with the one that still works.",
        "qr_links": links,
    }


def spent_oracle(do, obs):
    for url in obs["qr_links"]:
        if "number" in do(op="activate", url=url):
            return


# 3. send a text
async def text_setup(w: World) -> dict:
    obs = await _phone_with(w, "Alice")
    w.state["body"] = w.rng.choice(TEXTS)
    return {"instruction": f'Text Alice exactly: "{w.state["body"]}"', **obs}


def text_oracle(do, obs):
    do(op="send_text", to="Alice", body=_quoted(obs))


# 4. answer a question using another contact's text
async def relay_setup(w: World) -> dict:
    obs = await _phone_with(w, "Alice", "Bob")
    code = w.state["code"] = f"{w.rng.randrange(10000):04d}"
    await w.contacts["Bob"].text(obs["your_number"], f"Gate code for Friday is {code}.")
    await w.settle()
    await w.contacts["Alice"].text(
        obs["your_number"], "Hey! What's the gate code? Bob should have sent it to you."
    )
    await w.settle()
    return {"instruction": "Alice texted you a question. Text her the answer.", **obs}


def relay_oracle(do, obs):
    bob = obs["contacts"]["Bob"]
    for m in _inbox(do):
        found = re.search(r"\b\d{4}\b", m["body"])
        if m["from"] == bob and found:
            do(op="send_text", to="Alice", body=found.group())


# 5. texts queued while the phone had no number
async def queued_setup(w: World) -> dict:
    number, _, url = w.issue("agent")
    bob = await w.contact("Bob")
    alnum = string.ascii_uppercase + string.digits
    conf = w.state["conf"] = "VN-" + "".join(w.rng.choice(alnum) for _ in range(6))
    w.state["number"] = number
    for body in (
        "Hi, this is Bob from the front desk.",
        f"Your confirmation number is {conf}.",
        "Text me if you need anything.",
    ):
        await bob.text(number, body)
    await w.settle()
    return {
        "instruction": "While this phone had no number, Bob texted it a confirmation "
        "number. Activate the QR link, find the confirmation number and submit it.",
        "qr": url,
        "contacts": {"Bob": bob.number},
    }


def queued_done(w: World) -> bool:
    return (
        (w.submitted or "").strip().upper() == w.state["conf"]
        and w.agent is not None
        and not w.store.pending_for(w.state["number"])
    )


def queued_oracle(do, obs):
    do(op="activate", url=obs["qr"])
    for m in _inbox(do):
        found = re.search(r"VN-[A-Z0-9]{6}", m["body"])
        if found:
            do(op="submit", answer=found.group())


# 6. answer an incoming call
async def answer_setup(w: World) -> dict:
    obs = await _phone_with(w, "Alice")
    w.state["call"] = await w.contacts["Alice"].call(obs["your_number"])
    await w.settle()
    return {"instruction": "Your phone is ringing. Answer it.", **obs}


def answered(w: World) -> bool:
    return _signal(w.contacts["Alice"], "answer", w.state["call"])


def answer_oracle(do, obs):
    ev = _wait(do, lambda e: e.get("type") == "call")
    do(op="answer", call_id=ev.get("call_id"))


# 7. screen a call: answer contacts, decline strangers
async def screen_setup(w: World) -> dict:
    obs = await _phone_with(w, "Alice", "Bob")
    stranger = await w.device("stranger")
    caller = w.rng.choice([stranger, w.contacts["Bob"]])
    w.state.update(
        caller=caller,
        expect="reject" if caller is stranger else "answer",
        call=await caller.call(obs["your_number"]),
    )
    await w.settle()
    return {
        "instruction": "Someone is calling. Answer if it's one of your contacts; "
        "otherwise decline.",
        **obs,
    }


def screened(w: World) -> bool:
    caller, call = w.state["caller"], w.state["call"]
    took = {k for k in ("answer", "reject") if _signal(caller, k, call)}
    return took == {w.state["expect"]}


def screen_oracle(do, obs):
    ev = _wait(do, lambda e: e.get("type") == "call")
    known = ev.get("from") in obs["contacts"].values()
    do(op="answer" if known else "decline", call_id=ev.get("call_id"))


# 8. place a call and hang up after it connects
def _picks_up_after(delay: float, bg: list):
    async def on_event(phone: Phone, ev: dict) -> None:
        if ev.get("type") != "call":
            return

        async def pick_up():
            await asyncio.sleep(delay)
            if not _signal(phone, "hangup", ev["call_id"]):
                await phone.send(
                    {
                        "type": "answer",
                        "to": ev["from"],
                        "call_id": ev["call_id"],
                        "sdp": ANSWER,
                    }
                )
                phone.events.append({"type": "_answered", "call_id": ev["call_id"]})

        bg.append(asyncio.create_task(pick_up()))

    return on_event


async def call_setup(w: World) -> dict:
    bg = w.state["bg"] = []
    obs = await _phone_with(w, "Bob", hooks={"Bob": _picks_up_after(0.4, bg)})
    return {"instruction": "Call Bob. Once he picks up, hang up.", **obs}


def called(w: World) -> bool:
    if w.agent is None:
        return False
    answered_at = {}
    for i, ev in enumerate(w.contacts["Bob"].events):
        if ev.get("type") == "_answered":
            answered_at[ev["call_id"]] = i
        elif (
            ev.get("type") == "hangup"
            and ev.get("from") == w.agent.number
            and ev.get("call_id") in answered_at
        ):
            return True
    return False


def call_oracle(do, obs):
    call_id = do(op="call", to="Bob")["call_id"]
    _wait(do, lambda e: e.get("type") == "answer" and e.get("call_id") == call_id)
    do(op="hangup", call_id=call_id)


# 9. forward a text
async def forward_setup(w: World) -> dict:
    obs = await _phone_with(w, "Alice", "Bob")
    w.state["body"] = w.rng.choice(FORWARDS)
    await w.contacts["Alice"].text(obs["your_number"], w.state["body"])
    await w.settle()
    return {"instruction": "Forward Alice's latest text to Bob, word for word.", **obs}


def forward_oracle(do, obs):
    alice = obs["contacts"]["Alice"]
    last = [m for m in _inbox(do) if m["from"] == alice][-1]
    do(op="send_text", to="Bob", body=last["body"])


# 10. broadcast
async def broadcast_setup(w: World) -> dict:
    obs = await _phone_with(w, "Alice", "Bob", "Carol")
    w.state["body"] = w.rng.choice(BROADCASTS)
    return {
        "instruction": f'Tell every one of your contacts: "{w.state["body"]}"',
        **obs,
    }


def broadcast_oracle(do, obs):
    for name in obs["contacts"]:
        do(op="send_text", to=name, body=_quoted(obs))


# 11. text, then sign out
async def signout_setup(w: World) -> dict:
    obs = await _phone_with(w, "Carol")
    return {
        "instruction": f'Text Carol "{SIGNOFF}" and then sign out of this phone.',
        **obs,
    }


def signed_out(w: World) -> bool:
    if w.agent is None:
        return False
    revoked = w.store.scalar(
        "SELECT MAX(revoked_at) FROM devices WHERE number = ?", (w.agent.number,)
    )
    carol = w.contacts["Carol"].number
    return revoked is not None and any(
        m.recipient == carol and m.body.strip() == SIGNOFF and m.created_at < revoked
        for m in w.store.history(w.agent.number)
    )


def signout_oracle(do, obs):
    do(op="send_text", to="Carol", body=_quoted(obs))
    do(op="sign_out")


# 12. decline a second call while on a call
async def hold_setup(w: World) -> dict:
    obs = await _phone_with(w, "Alice", "Bob")
    first = await w.contacts["Alice"].call(obs["your_number"])
    await w.settle()
    await w.act({"op": "answer", "call_id": first})
    w.phone.seen = len(w.phone.events)
    second = await w.contacts["Bob"].call(obs["your_number"])
    await w.settle()
    w.state.update(first=first, second=second)
    return {
        "instruction": "You're on a call with Alice. Bob is calling too: decline Bob "
        "without ending your call with Alice.",
        "active_call": {"call_id": first, "with": "Alice"},
        **obs,
    }


def held(w: World) -> bool:
    first, second = w.state["first"], w.state["second"]
    return (
        _signal(w.contacts["Bob"], "reject", second)
        and not _signal(w.contacts["Alice"], "hangup", first)
        and first in w.calls
    )


def hold_oracle(do, obs):
    bob = obs["contacts"]["Bob"]
    ev = _wait(do, lambda e: e.get("type") == "call" and e.get("from") == bob)
    do(op="decline", call_id=ev.get("call_id"))


TASKS = [
    Task(1, "activate", activate_setup, activated, activate_oracle),
    Task(2, "spent_qr", spent_setup, activated, spent_oracle),
    Task(
        3,
        "send_text",
        text_setup,
        lambda w: _sent(w, "Alice", exact=w.state["body"]),
        text_oracle,
    ),
    Task(
        4,
        "relay_code",
        relay_setup,
        lambda w: _sent(w, "Alice", has=w.state["code"]),
        relay_oracle,
    ),
    Task(5, "queued_texts", queued_setup, queued_done, queued_oracle),
    Task(6, "answer_call", answer_setup, answered, answer_oracle),
    Task(7, "screen_call", screen_setup, screened, screen_oracle),
    Task(8, "place_call", call_setup, called, call_oracle),
    Task(
        9,
        "forward_text",
        forward_setup,
        lambda w: _sent(w, "Bob", exact=w.state["body"]),
        forward_oracle,
    ),
    Task(
        10,
        "broadcast",
        broadcast_setup,
        lambda w: all(_sent(w, n, exact=w.state["body"]) for n in w.contacts),
        broadcast_oracle,
    ),
    Task(11, "text_then_sign_out", signout_setup, signed_out, signout_oracle),
    Task(12, "decline_second_call", hold_setup, held, hold_oracle),
]


def get_task(key) -> Task:
    for task in TASKS:
        if str(key) in (str(task.id), task.name):
            return task
    raise KeyError(f"unknown task {key!r}; choose 1-12 or one of the names")


def solve(env, obs: str) -> float:
    """Run the scripted oracle for the current episode; returns the reward earned."""
    task = get_task(json.loads(obs)["task"])
    total, over = 0.0, False

    def do(**action) -> dict:
        nonlocal total, over
        if over:
            return {}
        out, reward, terminated, truncated, _ = env.step(json.dumps(action))
        total += reward
        over = terminated or truncated
        return json.loads(out)["result"]

    task.oracle(do, json.loads(obs))
    if not over:
        do(op="done")
    return total
