"""BRO agent zoo — synthetic market + known algorithms.

Controlled experiment substrate (BRO stage 1): each agent is a KNOWN
algorithm. It emits an observable event stream — orders, cancels, trades —
on a shared price path with small impact. The fingerprint stage then
tries to recover the algorithm's identity from the stream alone, with
the implementation hidden.

Event = (t, kind, side, size, price)
    kind in {"order", "cancel", "trade"}
    side in {"buy", "sell"}  (cancels carry the side of the resting order)

The price path is a shared object: mid random-walks plus a small
permanent impact proportional to signed trade size, so agent behavior
leaves a faint but real footprint.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import ClassVar

Event = tuple[int, str, str, float, float]  # (t, kind, side, size, price)


@dataclass
class Episode:
    """One hidden run: the observable stream + the realized price path."""

    agent_name: str
    seed: int
    events: list[Event]
    prices: list[float]


@dataclass
class Market:
    """Shared price path. impact = kappa * signed_size, permanent."""

    start: float = 100.0
    vol: float = 0.05
    impact_kappa: float = 0.002
    drift: float = 0.0

    def path(self, n: int, rng: random.Random) -> list[float]:
        return []  # filled by simulate(); path emerges from events

    def step(self, price: float, signed_flow: float, rng: random.Random) -> float:
        shock = rng.gauss(0.0, self.vol)
        return max(
            0.01, price * math.exp(shock + self.drift) + self.impact_kappa * signed_flow
        )


@dataclass
class Agent:
    """Base class: known algorithm producing events each tick."""

    name: ClassVar[str] = "agent"  # subclasses override the class attribute
    rng: random.Random = field(default_factory=random.Random)

    def reset(self, rng: random.Random) -> None:
        self.rng = rng

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        raise NotImplementedError


def _trade(evt: list[Event], t: int, side: str, size: float, price: float) -> None:
    if size > 0:
        evt.append((t, "order", side, size, price))
        evt.append((t, "trade", side, size, price))


# ---------------------------------------------------------------------------
# The zoo
# ---------------------------------------------------------------------------


class TwapAgent(Agent):
    """TWAP slicer: split a parent order into uniform child orders at a
    fixed cadence — the classic execution signature."""

    name = "twap"

    def __init__(
        self, parent_size: float = 200.0, interval: int = 4, side: str = "buy"
    ):
        super().__init__()
        self.parent = parent_size
        self.interval = interval
        self.side = side
        self._done = 0.0

    def reset(self, rng: random.Random) -> None:
        super().reset(rng)
        self._done = 0.0

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        if self._done >= self.parent or t % self.interval != 0:
            return []
        child = self.parent / 10.0  # parent split into 10 uniform slices
        self._done += child
        out: list[Event] = []
        _trade(out, t, self.side, child, price)
        return out


class VwapAgent(Agent):
    """VWAP follower: child sizes track an intraday U-shaped volume
    profile — bigger at open/close, thin mid-session."""

    name = "vwap"

    def __init__(
        self, parent_size: float = 200.0, horizon: int = 200, side: str = "buy"
    ):
        super().__init__()
        self.parent = parent_size
        self.horizon = horizon
        self.side = side
        self._t = 0

    def reset(self, rng: random.Random) -> None:
        super().reset(rng)
        self._t = 0

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        if self._t >= self.horizon:
            return []
        u = self._t / self.horizon  # 0..1
        profile = 0.3 + 2.2 * (u - 0.5) ** 2  # U-shape, min 0.3 mid-session
        child = (
            self.parent
            * profile
            / sum(
                0.3 + 2.2 * (i / self.horizon - 0.5) ** 2 for i in range(self.horizon)
            )
        )
        self._t += 1
        out: list[Event] = []
        _trade(out, t, self.side, child, price)
        return out


class MomentumAgent(Agent):
    """Positive-feedback trader: buys after up-moves, sells after
    down-moves; size proportional to |recent move|. The signature the BIS
    positive-feedback literature studies."""

    name = "momentum"

    def __init__(self, sensitivity: float = 40.0, threshold: float = 0.0005):
        super().__init__()
        self.k = sensitivity
        self.eps = threshold

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        if abs(prev_move) < self.eps:
            return []
        side = "buy" if prev_move > 0 else "sell"
        size = self.k * abs(prev_move)
        out: list[Event] = []
        _trade(out, t, side, size, price)
        return out


class MarketMakerAgent(Agent):
    """Two-sided quoter: posts bid+ask each tick, cancels+replaces stale
    quotes — leaves a high cancel:trade ratio and symmetric flow."""

    name = "market_maker"

    def __init__(self, quote_size: float = 5.0, spread: float = 0.02, refresh: int = 2):
        super().__init__()
        self.q = quote_size
        self.spread = spread
        self.refresh = refresh
        self._resting: list[tuple[str, float]] = []

    def reset(self, rng: random.Random) -> None:
        super().reset(rng)
        self._resting = []

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        out: list[Event] = []
        if t % self.refresh == 0:
            for side, p in self._resting:
                out.append((t, "cancel", side, self.q, p))
            self._resting = []
            for side, px in (
                ("buy", price - self.spread),
                ("sell", price + self.spread),
            ):
                out.append((t, "order", side, self.q, px))
                self._resting.append((side, px))
                # marketable hits arrive stochastically against the quotes
                if self.rng.random() < 0.35:
                    out.append(
                        (t, "trade", "sell" if side == "buy" else "buy", self.q, px)
                    )
        return out


class GradientDescentAgent(Agent):
    """The 'hidden algorithm' canary: minimizes a convex cost
    C(p) = (p - target)^2 + fees*trades² via gradient steps
    size_t = -eta * grad(C). Step sizes shrink geometrically toward the
    target — a recognizably GD trajectory, if BRO can see it."""

    name = "gradient_descent"

    def __init__(self, target: float = 150.0, eta: float = 0.4):
        super().__init__()
        self.target = target
        self.eta = eta
        self._pos = 0.0

    def reset(self, rng: random.Random) -> None:
        super().reset(rng)
        self._pos = 0.0

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        grad = 2.0 * (self._pos - self.target)
        step_size = -self.eta * grad
        if abs(step_size) < 0.5:
            return []
        side = "buy" if step_size > 0 else "sell"
        out: list[Event] = []
        _trade(out, t, side, abs(step_size), price)
        self._pos += step_size
        return out


class NoiseAgent(Agent):
    """Uniform random orders — the null algorithm."""

    name = "noise"

    def __init__(self, rate: float = 0.5, mean_size: float = 8.0):
        super().__init__()
        self.rate = rate
        self.mean = mean_size

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        if self.rng.random() > self.rate:
            return []
        out: list[Event] = []
        _trade(
            out,
            t,
            "buy" if self.rng.random() < 0.5 else "sell",
            abs(self.rng.gauss(self.mean, self.mean * 0.4)),
            price,
        )
        return out


ZOO: dict[str, type[Agent]] = {
    a.name: a
    for a in (
        TwapAgent,
        VwapAgent,
        MomentumAgent,
        MarketMakerAgent,
        GradientDescentAgent,
        NoiseAgent,
    )
}


# ---------------------------------------------------------------------------
# Adversarial variants — same algorithms, parameter-jittered or mimicking.
# These are what the fingerprint must survive in stage 2 of the experiment.
# ---------------------------------------------------------------------------


class JitteredTwapAgent(TwapAgent):
    """TWAP with noisy cadence and slice sizes — the slicer hiding."""

    name = "twap_jittered"

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        if self._done >= self.parent:
            return []
        jitter = max(1, round(self.interval + self.rng.gauss(0, 1.5)))
        if t % jitter != 0:
            return []
        child = (self.parent / 10.0) * max(0.2, 1 + self.rng.gauss(0, 0.35))
        self._done += child
        out: list[Event] = []
        _trade(out, t, self.side, child, price)
        return out


class JitteredVwapAgent(VwapAgent):
    """VWAP with a noisy intraday profile."""

    name = "vwap_jittered"

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        if self._t >= self.horizon:
            return []
        u = self._t / self.horizon
        profile = (0.3 + 2.2 * (u - 0.5) ** 2) * math.exp(self.rng.gauss(0, 0.4))
        child = (
            self.parent
            * profile
            / sum(
                0.3 + 2.2 * (i / self.horizon - 0.5) ** 2 for i in range(self.horizon)
            )
        )
        self._t += 1
        out: list[Event] = []
        _trade(out, t, self.side, child, price)
        return out


class FadedMomentumAgent(MomentumAgent):
    """Momentum chaser that sometimes sleeps — reaction threshold jitters."""

    name = "momentum_faded"

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        if self.rng.random() < 0.35:  # misses a third of triggers
            return []
        return super().step(t, price, prev_move)


class JitteredMakerAgent(MarketMakerAgent):
    """Market maker with variable refresh and spread."""

    name = "market_maker_jittered"

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        self.refresh = max(1, 2 + int(self.rng.gauss(0, 1.2)))
        self.spread = 0.02 * math.exp(self.rng.gauss(0, 0.3))
        return super().step(t, price, prev_move)


class JitteredGdAgent(GradientDescentAgent):
    """Gradient descent with per-step learning-rate jitter."""

    name = "gradient_descent_jittered"

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        self.eta = 0.4 * math.exp(self.rng.gauss(0, 0.25))
        return super().step(t, price, prev_move)


class MimicTwapAgent(TwapAgent):
    """A TWAP slicer tilting slice sizes with price momentum — built to
    sit between twap and momentum in fingerprint space."""

    name = "twap_mimic"

    def step(self, t: int, price: float, prev_move: float) -> list[Event]:
        if self._done >= self.parent or t % self.interval != 0:
            return []
        tilt = 1.0 + 30.0 * prev_move  # momentum tilt on the slice
        child = (self.parent / 10.0) * max(0.2, tilt)
        self._done += child
        out: list[Event] = []
        _trade(out, t, self.side, child, price)
        return out


ADVERSARIAL_ZOO: dict[str, type[Agent]] = {
    a.name: a
    for a in (
        JitteredTwapAgent,
        JitteredVwapAgent,
        FadedMomentumAgent,
        JitteredMakerAgent,
        JitteredGdAgent,
        MimicTwapAgent,
    )
}


def adversarial_zoo() -> dict[str, Agent]:
    """Instantiated adversarial agents, keyed by their hidden name."""
    return {name: cls() for name, cls in ADVERSARIAL_ZOO.items()}


def base_zoo() -> dict[str, Agent]:
    """Instantiated known algorithms, keyed by name."""
    return {name: cls() for name, cls in ZOO.items()}


def simulate(agent: Agent, n_ticks: int = 240, seed: int = 0) -> Episode:
    """Run one agent on a fresh price path; return stream + price path."""
    rng = random.Random(seed)
    agent.reset(random.Random(seed))
    market = Market()
    price = market.start
    events: list[Event] = []
    prices: list[float] = []
    prev = 0.0
    for t in range(n_ticks):
        events.extend(agent.step(t, price, prev))
        signed = sum(
            (s if sd == "buy" else -s)
            for (et, k, sd, s, _px) in events
            if k == "trade" and et == t
        )
        prices.append(price)
        new_price = market.step(price, signed, rng)
        prev = (new_price - price) / price
        price = new_price
    return Episode(agent.name, seed, events, prices)
