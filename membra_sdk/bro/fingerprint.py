"""BRO fingerprint — Phi_t: event stream -> temporal feature vector.

A fingerprint is a dict of scalar measurements over an episode (or a
window of it). The point is *observable procedure*: every feature is a
statistic of what the stream did — cadence, size distribution, cancel
behavior, flow-vs-price lead/lag — never of which algorithm produced it.

Feature groups:

  cadence      inter-trade-arrival mean/CV/burstiness/entropy — catches
               fixed-interval slicers (TWAP) and U-shaped profilers (VWAP)
  size         trade-size moments + max/median — GD's geometric decay vs
               uniform slices vs noise
  mix          order/cancel/trade shares — the market maker's churn
  flow         signed-flow autocorrelation, buy share
  leadlag      corr(flow_t, move_{t-1}) vs corr(flow_t, move_{t+1}) —
               reaction vs anticipation; momentum's signature lives here
  stokes       signed-flow x price-move channels through the SpinorStokes
               machinery: mean Pi and s3-sign consistency

Robustness variants (for the adversarial stage): `robust=True` drops
scale-dependent features and keeps rank/shape statistics, which survive
parameter jitter better.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from ..strategy.spinor_stokes import SpinorStokesStrategy
from .agents import Episode

FEATURE_NAMES = [
    # cadence
    "iat_mean",
    "iat_cv",
    "iat_burst",
    "iat_entropy",
    # size
    "size_mean",
    "size_cv",
    "size_skew",
    "size_max_med",
    # mix
    "order_rate",
    "cancel_rate",
    "trade_rate",
    "cancel_per_trade",
    # flow
    "flow_autocorr",
    "buy_share",
    # lead/lag vs price
    "flow_move_lag1",
    "flow_move_lead1",
    "lag_lead_diff",
    # stokes on (flow, move) channels
    "stokes_pi_mean",
    "stokes_s3_consistency",
]

# Rank/shape statistics that survive parameter jitter.
ROBUST_NAMES = [
    "iat_cv",
    "iat_burst",
    "iat_entropy",
    "size_cv",
    "size_skew",
    "cancel_per_trade",
    "flow_autocorr",
    "flow_move_lag1",
    "flow_move_lead1",
    "stokes_pi_mean",
    "stokes_s3_consistency",
]


@dataclass
class Fingerprint:
    """Phi_t for one episode (or window): name -> scalar."""

    values: dict[str, float]

    def vector(self, names: list[str]) -> list[float]:
        return [self.values.get(n, 0.0) for n in names]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _corr(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[:n], b[:n]
    ma, mb = _mean(a), _mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da > 0 and db > 0 else 0.0


def _entropy(xs: list[float], bins: int = 8) -> float:
    if len(xs) < 2:
        return 0.0
    lo, hi = min(xs), max(xs)
    if hi == lo:
        return 0.0
    counts = [0] * bins
    for x in xs:
        counts[min(bins - 1, int((x - lo) / (hi - lo) * bins))] += 1
    n = len(xs)
    h = 0.0
    for c in counts:
        if c:
            p = c / n
            h -= p * math.log(p)
    return h / math.log(bins)  # normalized to [0,1]


def fingerprint(ep: Episode, robust: bool = False) -> Fingerprint:
    """Extract Phi(ep) — the whole-episode fingerprint."""
    trades = [e for e in ep.events if e[1] == "trade"]
    orders = [e for e in ep.events if e[1] == "order"]
    cancels = [e for e in ep.events if e[1] == "cancel"]
    n = len(ep.prices)

    # per-tick signed flow and price moves, aligned
    flow = [0.0] * n
    for t, kind, side, size, _px in ep.events:
        if kind == "trade" and t < n:
            flow[t] += size if side == "buy" else -size
    moves = [(ep.prices[i] - ep.prices[i - 1]) / ep.prices[i - 1] for i in range(1, n)]

    sizes = [e[3] for e in trades]
    iats = [b[0] - a[0] for a, b in pairwise(trades)]
    med = sorted(sizes)[len(sizes) // 2] if sizes else 0.0
    iat_mu, iat_sd = _mean([float(i) for i in iats]), _std([float(i) for i in iats])

    # stokes over (signed flow, price move) channels
    strat = SpinorStokesStrategy(window=16, pi_enter=0.0, pi_exit=-1.0)
    sigs = strat.run(flow, moves + [0.0])
    inm = [s for s in sigs if s.pi > 0]
    pi_mean = _mean([s.pi for s in sigs])
    s3_signs = [1 if s.s_hat[2] >= 0 else -1 for s in inm]
    s3_cons = abs(_mean(s3_signs)) if s3_signs else 0.0

    vals = {
        "iat_mean": iat_mu,
        "iat_cv": iat_sd / iat_mu if iat_mu > 0 else 0.0,
        "iat_burst": (
            (iat_sd - iat_mu) / (iat_sd + iat_mu) if (iat_sd + iat_mu) > 0 else 0.0
        ),
        "iat_entropy": _entropy([float(i) for i in iats]),
        "size_mean": _mean(sizes),
        "size_cv": _std(sizes) / _mean(sizes) if _mean(sizes) > 0 else 0.0,
        "size_skew": (
            _mean([(s - _mean(sizes)) ** 3 for s in sizes]) / (_std(sizes) ** 3)
            if _std(sizes) > 0 and len(sizes) > 2
            else 0.0
        ),
        "size_max_med": max(sizes) / med if med > 0 else 0.0,
        "order_rate": len(orders) / n,
        "cancel_rate": len(cancels) / n,
        "trade_rate": len(trades) / n,
        "cancel_per_trade": len(cancels) / max(1, len(trades)),
        "flow_autocorr": _corr(flow[:-1], flow[1:]),
        "buy_share": (
            sum(1 for e in trades if e[2] == "buy") / len(trades) if trades else 0.0
        ),
        "flow_move_lag1": _corr(flow[1:], moves[:-1]),
        "flow_move_lead1": _corr(flow[:-1], moves[1:]),
        "lag_lead_diff": _corr(flow[1:], moves[:-1]) - _corr(flow[:-1], moves[1:]),
        "stokes_pi_mean": pi_mean,
        "stokes_s3_consistency": s3_cons,
    }
    if robust:
        vals = {k: vals[k] for k in ROBUST_NAMES}
    return Fingerprint(vals)
