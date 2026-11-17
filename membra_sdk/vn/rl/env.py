"""Gymnasium environment: text observations and JSON-string actions on a live VN phone.

    env = VNEnv()
    obs, info = env.reset(seed=0, options={"task": "place_call"})
    obs, reward, terminated, truncated, info = env.step('{"op":"call","to":"Bob"}')

Reward is 1.0 on the step where the task's check passes against server state, else 0.
The episode ends on success, on `submit`/`done`, or after `max_steps`.
"""

import argparse
import asyncio
import json
import random
import string
import sys
import threading
from typing import ClassVar

from membra_sdk.vn.rl.tasks import TASKS, get_task, solve
from membra_sdk.vn.rl.world import OPS, World

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # the environment works without gymnasium, just unregistered
    gym = None

_Base = gym.Env if gym else object


class VNEnv(_Base):
    metadata: ClassVar[dict] = {"render_modes": []}

    def __init__(self, task=None, max_steps: int = 25, settle: float = 0.15):
        if gym:
            text = spaces.Text(max_length=16384, charset=string.printable)
            self.observation_space = self.action_space = text
        self.task_key = task
        self.max_steps = max_steps
        self.settle = settle
        self.world: World | None = None
        self.task = None
        self.steps = 0
        self.over = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=60)

    def reset(self, *, seed=None, options=None):
        if gym:
            super().reset(seed=seed)
        rng = random.Random(seed)
        key = (options or {}).get("task", self.task_key)
        self.task = get_task(key) if key is not None else rng.choice(TASKS)
        if self.world is not None:
            self._run(self.world.close())
        self.world = World(rng, self.settle)
        self._run(self.world.start())
        extras = self._run(self.task.setup(self.world))
        self.steps, self.over = 0, False
        obs = {"task": self.task.name, **extras, "ops": OPS}
        return json.dumps(obs), {"task": self.task.name}

    def step(self, action):
        if self.over:
            raise RuntimeError("episode is over; call reset()")
        try:
            a = json.loads(action) if isinstance(action, str) else dict(action)
        except (TypeError, ValueError):
            a = None
        if isinstance(a, dict):
            result = self._run(self.world.act(a))
        else:
            a, result = {}, {"error": "action must be a JSON object"}
        self.steps += 1
        success = bool(self.task.check(self.world))
        terminated = success or a.get("op") in ("submit", "done")
        truncated = not terminated and self.steps >= self.max_steps
        self.over = terminated or truncated
        obs = json.dumps({"result": result, "step": self.steps})
        info = {"task": self.task.name, "success": success}
        return obs, float(success), terminated, truncated, info

    def close(self):
        if self.world is not None:
            self._run(self.world.close())
            self.world = None
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
            self._loop.close()


if gym:
    gym.register(id="membra/VN-v0", entry_point="membra_sdk.vn.rl.env:VNEnv")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m membra_sdk.vn env")
    p.add_argument("--task", help="1-12 or task name (default: random)")
    p.add_argument("--seed", type=int)
    p.add_argument("--list", action="store_true", help="list the tasks")
    p.add_argument("--oracle", action="store_true", help="run the scripted solver")
    args = p.parse_args(argv)
    if args.list:
        for t in TASKS:
            print(f"{t.id:>2}  {t.name}")
        return 0
    env = VNEnv()
    try:
        if args.oracle:
            tasks = [get_task(args.task)] if args.task else TASKS
            for t in tasks:
                obs, _ = env.reset(seed=args.seed, options={"task": t.id})
                print(f"{t.id:>2}  {t.name:<20} reward {solve(env, obs):.1f}")
            return 0
        obs, _ = env.reset(seed=args.seed, options={"task": args.task})
        print(json.dumps(json.loads(obs), indent=2))
        for line in sys.stdin:
            if not line.strip():
                continue
            obs, reward, terminated, truncated, _ = env.step(line)
            print(obs, f"reward={reward}", flush=True)
            if terminated or truncated:
                break
        return 0
    finally:
        env.close()
