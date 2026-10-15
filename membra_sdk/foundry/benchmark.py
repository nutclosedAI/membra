"""Causal, self-financing spot/cash research benchmark. No broker or synthetic feed."""

from __future__ import annotations

import json
import math
import statistics as st
from dataclasses import asdict, dataclass, replace
from itertools import pairwise
from pathlib import Path

from .tfl import Policy, digest, number


@dataclass(frozen=True)
class Market:
    candles: tuple[tuple[float, ...], ...]
    provenance: dict

    @property
    def identity(self) -> str:
        # A new download timestamp must not make a reused holdout appear unseen.
        return digest(
            {"candles": self.candles, "instrument": "BTC-USD", "granularity": 3600}
        )

    @classmethod
    def load(cls, path: str | Path) -> Market:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = tuple(tuple(row) for row in doc["candles"])
        if (
            len(rows) < 500
            or doc.get("granularity") != 3600
            or doc.get("instrument") != "BTC-USD"
        ):
            raise ValueError("at least 500 hourly candles required")
        for i, row in enumerate(rows):
            if len(row) != 6:
                raise ValueError("Coinbase time/low/high/open/close/volume required")
            t, low, high, opening, close, volume = row
            for value in row:
                number(value, 0, 1e15)
            if (
                int(t) != t
                or low <= 0
                or not low <= opening <= high
                or not low <= close <= high
                or volume <= 0
            ):
                raise ValueError("invalid candle")
            if i and t != rows[i - 1][0] + 3600:
                raise ValueError("missing, duplicated, or unordered hourly candle")
        return cls(rows, {k: v for k, v in doc.items() if k != "candles"})


@dataclass(frozen=True)
class Execution:
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    impact_bps: float = 100.0
    max_participation: float = 0.01
    annual_cash_rate: float = 0.0

    def __post_init__(self) -> None:
        for field in ("fee_bps", "slippage_bps", "impact_bps"):
            number(getattr(self, field), 0, 1000)
        number(self.max_participation, 0.00001, 0.1)
        number(self.annual_cash_rate, 0, 0.2)


def target(policy: Policy, history: tuple[tuple[float, ...], ...], tick: int) -> float:
    """history contains ONLY completed candles, before the executable open."""
    if policy.family == "cash":
        return 0.0
    if policy.family in {"hold", "inventory"}:
        return policy.max_exposure
    if len(history) < policy.lookback:
        return 0.0
    closes = [r[4] for r in history[-policy.lookback :]]
    trend = closes[-1] / closes[0] - 1
    # A causal timing extension to inventory control, not novel mathematics.
    return policy.max_exposure if trend > policy.threshold else 0.0


def simulate(
    policy: Policy, market: Market, start: int, end: int, execution: Execution
) -> dict:
    if not 168 <= start < end < len(market.candles):
        raise ValueError("invalid evaluation window or insufficient warmup")
    rows = market.candles
    cash, units = policy.capital, 0.0
    peak, stopped, turnover, costs = cash, False, 0.0, 0.0
    returns, actions, equity_curve = [], [], []
    max_dd = 0.0
    unfilled = 0
    last_target = 0.0
    risk_violations = 0
    for i in range(start, end):
        price, next_price = rows[i][3], rows[i + 1][3]
        equity = cash + units * price
        peak = max(peak, equity)
        stopped = stopped or 1 - equity / peak >= policy.max_drawdown
        weight = units * price / equity
        if stopped:
            desired = 0.0
        elif (i - start) % policy.rebalance_hours == 0:
            last_target = target(policy, rows[:i], i)
            desired = last_target
        else:
            desired = min(weight, policy.max_exposure)
        wanted = desired * equity - units * price
        volume_notional = rows[i - 1][5] * price
        cap = volume_notional * execution.max_participation
        notional = min(abs(wanted), cap)
        if abs(wanted) > cap + 1e-9:
            unfilled += 1
        # Price impact is a stated proxy, not an order-book fill reconstruction.
        rate = (
            execution.fee_bps
            + execution.slippage_bps
            + execution.impact_bps * notional / volume_notional
        ) / 10000
        if wanted > 0:
            notional = min(notional, cash / (1 + rate))
            units += notional / price
            cash -= notional * (1 + rate)
        else:
            notional = min(notional, units * price)
            units -= notional / price
            cash += notional * (1 - rate)
        fee = notional * rate
        costs += fee
        turnover += notional / policy.capital
        post_equity = cash + units * price
        if post_equity <= 0 or cash < -1e-6:
            raise ValueError("insolvent portfolio")
        actual_weight = units * price / post_equity
        if actual_weight > policy.max_exposure + 0.001:
            risk_violations += 1
        cash *= 1 + execution.annual_cash_rate / 8760
        value = cash + units * next_price
        peak = max(peak, value)
        max_dd = max(max_dd, 1 - value / peak)
        actions.append(
            {
                "time": int(rows[i][0]),
                "target": desired,
                "weight": actual_weight,
                "notional": math.copysign(notional, wanted),
                "risk_gate": "reduce_only" if stopped else "passed",
            }
        )
        returns.append(value / equity - 1)
        equity_curve.append(value)
    # Terminal liquidation is charged equally, including a conservative impact proxy.
    exit_notional = units * rows[end][3]
    exit_rate = (
        execution.fee_bps
        + execution.slippage_bps
        + execution.impact_bps * exit_notional / (rows[end - 1][5] * rows[end][3])
    ) / 10000
    exit_cost = exit_notional * exit_rate
    costs += exit_cost
    turnover += exit_notional / policy.capital
    if equity_curve[-1] <= exit_cost:
        raise ValueError("terminal liquidation exceeds equity")
    before_last = equity_curve[-1] / (1 + returns[-1])
    equity_curve[-1] -= exit_cost
    returns[-1] = equity_curve[-1] / before_last - 1
    max_dd = max(max_dd, 1 - equity_curve[-1] / peak)
    daily = [
        math.prod(1 + r for r in returns[j : j + 24]) - 1
        for j in range(0, len(returns) - 23, 24)
    ]
    return {
        "net_return": equity_curve[-1] / policy.capital - 1,
        "max_drawdown": max_dd,
        "costs": costs,
        "turnover": turnover,
        "risk_stopped": stopped,
        "risk_violations": risk_violations,
        "capacity_clips": unfilled,
        "sharpe_daily": sharpe(daily),
        "daily": daily,
        "returns": returns,
        "actions": actions,
    }


def sharpe(returns: list[float]) -> float:
    sigma = st.stdev(returns) if len(returns) > 1 else 0.0
    return st.mean(returns) / sigma if sigma > 1e-15 else 0.0


def deflated_sharpe(returns: list[float], trial_sharpes: list[float]) -> dict:
    """Bailey/Lopez de Prado DSR approximation on non-overlapping daily returns."""
    n, trials = len(returns), len(trial_sharpes)
    if n < 20 or trials < 2 or st.stdev(returns) <= 1e-15:
        return {"probability": 0.0, "trials": trials, "observations": n}
    norm = st.NormalDist()
    gamma = 0.5772156649015329
    sr0 = st.stdev(trial_sharpes) * (
        (1 - gamma) * norm.inv_cdf(1 - 1 / trials)
        + gamma * norm.inv_cdf(1 - 1 / (trials * math.e))
    )
    mean, sigma = st.mean(returns), st.pstdev(returns)
    skew = st.mean(((r - mean) / sigma) ** 3 for r in returns)
    kurt = st.mean(((r - mean) / sigma) ** 4 for r in returns)
    sr = sharpe(returns)
    variance = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    probability = (
        norm.cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(variance))
        if variance > 0
        else 0.0
    )
    return {
        "probability": probability,
        "expected_max_sharpe": sr0,
        "trials": trials,
        "observations": n,
        "method": "daily-block DSR approximation; not independence proof",
    }


def summarize(result: dict) -> dict:
    return {k: v for k, v in result.items() if k not in {"daily", "returns", "actions"}}


def tournament(
    policies: list[Policy], incumbent: str, market: Market, execution: Execution
) -> dict:
    """Freeze the entire candidate set before opening the final 25% holdout once."""
    if len({p.identity for p in policies}) != len(policies):
        raise ValueError("duplicate policies")
    if incumbent not in {p.identity for p in policies}:
        raise ValueError("incumbent absent")
    warmup, split = 168, int(len(market.candles) * 0.75)
    if split < warmup + 1000 or len(market.candles) - split < 500:
        raise ValueError("insufficient data for folds and holdout")
    boundaries = [warmup + (split - warmup) * k // 3 for k in range(4)]
    runs: dict[str, dict] = {}
    for p in policies:
        folds = [simulate(p, market, a, b, execution) for a, b in pairwise(boundaries)]
        combined = [r for fold in folds for r in fold["daily"]]
        stress = simulate(
            p,
            market,
            warmup,
            split,
            replace(
                execution,
                fee_bps=execution.fee_bps * 2,
                slippage_bps=execution.slippage_bps * 2,
                max_participation=execution.max_participation / 2,
            ),
        )
        # Prefix invariance: same executable decisions when future candles are removed.
        cut = min(split - 1, warmup + 200)
        prefix = Market(market.candles[: cut + 1], market.provenance)
        full = simulate(p, market, warmup, split, execution)
        prefix_run = simulate(p, prefix, warmup, cut, execution)
        causal = prefix_run["actions"] == full["actions"][: cut - warmup]
        runs[p.identity] = {
            "policy": p.spec(),
            "folds": [summarize(f) for f in folds],
            "daily": combined,
            "sharpe_daily": sharpe(combined),
            "stress": summarize(stress),
            "prefix_invariant": causal,
        }
    trial_srs = [r["sharpe_daily"] for r in runs.values()]
    base_folds = runs[incumbent]["folds"]
    for identity, run in runs.items():
        dsr = deflated_sharpe(run.pop("daily"), trial_srs)
        run["dsr"] = dsr
        run["selection_eligible"] = (
            identity != incumbent
            and run["prefix_invariant"]
            and dsr["probability"] >= 0.95
            and all(
                f["max_drawdown"] <= run["policy"]["constraints"]["max_drawdown"]
                and f["risk_violations"] == 0
                for f in run["folds"]
            )
            and all(
                f["net_return"] > b["net_return"]
                for f, b in zip(run["folds"], base_folds)
            )
            and run["stress"]["net_return"] > runs[incumbent]["stress"]["net_return"]
        )
    eligible = [i for i, r in runs.items() if r["selection_eligible"]]
    selected = (
        max(eligible, key=lambda i: runs[i]["sharpe_daily"]) if eligible else None
    )
    # Only this preselected candidate and the incumbent see the untouched segment.
    holdout: dict[str, dict] = {}
    for identity in dict.fromkeys([incumbent] + ([selected] if selected else [])):
        p = next(p for p in policies if p.identity == identity)
        holdout[identity] = summarize(
            simulate(p, market, split, len(market.candles) - 1, execution)
        )
    shadow_candidate = None
    if selected:
        h = holdout[selected]
        p = next(p for p in policies if p.identity == selected)
        if (
            h["net_return"] > holdout[incumbent]["net_return"]
            and h["max_drawdown"] <= p.max_drawdown
            and h["risk_violations"] == 0
        ):
            shadow_candidate = selected
    return {
        "schema": "foundry-benchmark-v1",
        "data_id": market.identity,
        "engine": digest(
            Path(__file__).read_text(encoding="utf-8")
            + Path(__file__).with_name("tfl.py").read_text(encoding="utf-8")
        ),
        "execution": asdict(execution),
        "incumbent": incumbent,
        "candidate_manifest": digest([p.spec() for p in policies]),
        "windows": {"warmup": warmup, "fold_boundaries": boundaries, "holdout": split},
        "runs": runs,
        "preselected": selected,
        "holdout": holdout,
        "shadow_candidate": shadow_candidate,
        "evidence_state": "historical_backtest",
        "limitations": [
            "OHLCV proxy; no order book, queue, intrabar stop guarantee or live fills",
            "fee/slippage/impact and capacity assumptions, not measured venue quotes",
            "spot/cash only; no funding, borrowing, derivatives or taxation",
            "daily DSR is approximate; remaining dependence and selection bias possible",
            "holdout must not be reused for adaptive search on this dataset",
            "no theorem proof, novelty certification or live alpha claim",
        ],
    }
