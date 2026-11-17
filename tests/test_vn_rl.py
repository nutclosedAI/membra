"""Tests for membra_sdk.vn.rl: every task is solvable and scored from server state."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from membra_sdk.vn.rl import TASKS, VNEnv, solve


@pytest.fixture(scope="module")
def env():
    e = VNEnv()
    yield e
    e.close()


def _step(env, **action):
    obs, reward, terminated, truncated, _ = env.step(json.dumps(action))
    return json.loads(obs)["result"], reward, terminated or truncated


@pytest.mark.parametrize("task", [t.id for t in TASKS])
def test_oracle_solves_every_task(env, task):
    obs, _ = env.reset(seed=task, options={"task": task})
    assert solve(env, obs) == 1.0


@pytest.mark.parametrize("task", [t.id for t in TASKS])
def test_doing_nothing_scores_zero(env, task):
    env.reset(seed=task, options={"task": task})
    _, reward, over = _step(env, op="done")
    assert reward == 0.0 and over


def test_hanging_up_the_active_call_fails(env):
    obs = json.loads(env.reset(seed=0, options={"task": "decline_second_call"})[0])
    _step(env, op="hangup", call_id=obs["active_call"]["call_id"])
    call = next(
        e
        for e in _step(env, op="events")[0]["events"]
        if e["type"] == "call" and e["from"] == obs["contacts"]["Bob"]
    )
    _, reward, _ = _step(env, op="decline", call_id=call["call_id"])
    assert reward == 0.0


def test_hanging_up_before_pickup_fails(env):
    env.reset(seed=0, options={"task": "place_call"})
    call_id = _step(env, op="call", to="Bob")[0]["call_id"]
    _, reward, _ = _step(env, op="hangup", call_id=call_id)
    assert reward == 0.0
    _, reward, _ = _step(env, op="events")
    assert reward == 0.0


def test_spent_link_is_rejected_and_bad_actions_are_reported(env):
    obs = json.loads(env.reset(seed=3, options={"task": "spent_qr"})[0])
    assert "error" in _step(env, op="send_text", to="x", body="y")[0]
    assert "error" in _step(env, op="activate", url="https://example.com/#nope")[0]
    assert "error" in json.loads(env.step("not json")[0])["result"]
    results = []
    for url in obs["qr_links"]:
        result, reward, over = _step(env, op="activate", url=url)
        results.append((reward, "error" in result))
        if over:
            break
    assert results[-1] == (1.0, False) and all(r == (0.0, True) for r in results[:-1])


def test_wrong_screening_choice_fails(env):
    obs = json.loads(env.reset(seed=0, options={"task": "screen_call"})[0])
    call = next(e for e in _step(env, op="events")[0]["events"] if e["type"] == "call")
    known = call["from"] in obs["contacts"].values()
    _, reward, _ = _step(
        env, op="decline" if known else "answer", call_id=call["call_id"]
    )
    assert reward == 0.0


def test_max_steps_truncates():
    e = VNEnv(task="queued_texts", max_steps=2)
    try:
        e.reset(seed=0)
        assert _step(e, op="contacts")[2] is False
        assert _step(e, op="contacts")[2] is True
    finally:
        e.close()
