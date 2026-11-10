"""Shared accounting contract for fully funded, same-day long research.

Signals remain strategy-owned. This module never manufactures a no-trade day
from missing data, applies an extra leverage multiplier, or fits cost settings.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd

NY = "America/New_York"


@dataclass(frozen=True)
class Costs:
    extra_bps_each_side: float = 1.0
    sell_notional_rate: float = 0.0000051
    sell_per_share: float = 0.000119


DEFAULT_COSTS = Costs()


@dataclass(frozen=True)
class Leg:
    day: str
    symbol: str
    signal_available: str
    entry_time: str
    exit_time: str
    weight: float
    entry_bid: float
    entry_ask: float
    exit_bid: float
    exit_ask: float
    price_basis: Literal["actual_quote", "bar_reference"] = "actual_quote"


def validate_leg(leg: Leg) -> None:
    times = [pd.Timestamp(v) for v in (leg.signal_available, leg.entry_time, leg.exit_time)]
    if any(t.tz is None for t in times):
        raise ValueError("Signal, entry and exit timestamps must be timezone-aware")
    if not times[0] < times[1] < times[2]:
        raise ValueError("Require signal availability strictly before entry before exit")
    if any(t.tz_convert(NY).strftime("%Y-%m-%d") != leg.day for t in times[1:]):
        raise ValueError("Overnight position or mislabeled session")
    prices = [leg.entry_bid, leg.entry_ask, leg.exit_bid, leg.exit_ask]
    if not np.isfinite(prices).all() or min(prices) <= 0:
        raise ValueError("Prices must be positive and finite")
    if leg.entry_bid > leg.entry_ask or leg.exit_bid > leg.exit_ask:
        raise ValueError("Crossed quote")
    if not 0 < leg.weight <= 1:
        raise ValueError("Invalid capital allocation")
    if leg.price_basis not in {"actual_quote", "bar_reference"}:
        raise ValueError("Unknown price basis")


def leg_returns(leg: Leg, costs: Costs) -> dict[str, float | None]:
    validate_leg(leg)
    if (
        not np.isfinite(list(asdict(costs).values())).all()
        or not 0 <= costs.extra_bps_each_side < 10000
        or not 0 <= costs.sell_notional_rate < 1
        or costs.sell_per_share < 0
    ):
        raise ValueError("Invalid cost units")
    mid_entry = (leg.entry_bid + leg.entry_ask) / 2
    mid_exit = (leg.exit_bid + leg.exit_ask) / 2
    reference = mid_exit / mid_entry - 1
    crossed = leg.exit_bid / leg.entry_ask - 1
    c = costs.extra_bps_each_side / 10000
    buy = leg.entry_ask * (1 + c)
    sell = leg.exit_bid * (1 - c)
    net = (sell * (1 - costs.sell_notional_rate) - costs.sell_per_share) / buy - 1
    return {
        "reference_return": reference,
        "crossed_return": crossed if leg.price_basis == "actual_quote" else None,
        "net_return": net,
        "observed_spread_drag": reference - crossed if leg.price_basis == "actual_quote" else None,
        "assumed_cost_drag": crossed - net,
    }


def benchmark_returns(frame: pd.DataFrame, days: list[str], *, basis: str) -> pd.Series:
    if basis not in {"split_dividend_adjusted", "legacy_adjusted_proxy"}:
        raise ValueError("SPY total-return comparison requires an explicit adjusted-price basis")
    if frame.index.has_duplicates:
        raise ValueError("Duplicate benchmark sessions")
    if not set(days) <= set(frame.index):
        raise ValueError("Missing benchmark session; do not shorten the comparison")
    prices = frame.loc[days, ["open", "close"]]
    if not np.isfinite(prices).all().all() or (prices <= 0).any().any():
        raise ValueError("Invalid benchmark price")
    returns = prices.close.pct_change(fill_method=None)
    returns.iloc[0] = prices.close.iloc[0] / prices.open.iloc[0] - 1
    return returns


def path_metrics(values: list[float] | np.ndarray, initial_cash: float = 100) -> dict:
    a = np.asarray(values, dtype=float)
    if not np.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("Initial cash must be positive and finite")
    if not len(a) or not np.isfinite(a).all() or (a <= -1).any():
        raise ValueError("Empty, missing or insolvent return path")
    wealth = np.r_[initial_cash, initial_cash * np.cumprod(1 + a)]
    sd = a.std(ddof=1) if len(a) > 1 else 0
    return {
        "ending_cash": float(wealth[-1]),
        "total_return": float(wealth[-1] / initial_cash - 1),
        "fixed_initial_notional_pnl": float(initial_cash * a.sum()),
        "max_daily_drawdown": float((wealth / np.maximum.accumulate(wealth) - 1).min()),
        "sharpe": float(a.mean() / sd * np.sqrt(252)) if sd else 0.0,
    }


def paired_mean_interval(
    a: np.ndarray, b: np.ndarray, *, seed: int = 70926, draws: int = 5000
) -> list[float]:
    if a.shape != b.shape or not len(a) or not np.isfinite(a - b).all():
        raise ValueError("Paired inference requires equal complete daily arrays")
    excess = a - b
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(a), (draws, (len(a) + 4) // 5))
    indices = ((starts[:, :, None] + np.arange(5)) % len(a)).reshape(draws, -1)[:, : len(a)]
    return [float(x) for x in np.quantile(excess[indices].mean(axis=1), [0.025, 0.975])]


def evaluate(
    legs: list[Leg],
    decisions: dict[str, str],
    benchmark: pd.Series,
    *,
    costs: Costs = DEFAULT_COSTS,
    initial_cash: float = 100,
) -> dict:
    """Require one explicit state per calendar day: cash, trade, or missing.

    Legs sharing entry/exit times form a basket. Sequential baskets compound
    from released cash. Partially overlapping baskets are explicitly rejected.
    """
    days = list(benchmark.index)
    if set(decisions) != set(days) or set(decisions.values()) - {"cash", "trade", "missing"}:
        raise ValueError("An explicit decision is required for every benchmark session")
    if (
        not np.isfinite(benchmark).all()
        or benchmark.index.has_duplicates
        or not benchmark.index.is_monotonic_increasing
    ):
        raise ValueError("Invalid benchmark calendar")
    grouped: dict[str, list[Leg]] = {}
    for leg in legs:
        validate_leg(leg)
        if leg.day not in decisions or decisions[leg.day] != "trade":
            raise ValueError("Fill on an unregistered or missing decision day")
        grouped.setdefault(leg.day, []).append(leg)
    data = {name: {} for name in ["reference", "crossed", "net", "cost_stress"]}
    accounting = []
    quote_only = all(leg.price_basis == "actual_quote" for leg in legs)
    for day in days:
        state = decisions[day]
        if state == "missing":
            continue
        rows = grouped.get(day, [])
        if state == "trade" and not rows:
            raise ValueError("Trade decision without fills must be marked missing")
        baskets: dict[tuple[pd.Timestamp, pd.Timestamp], list[Leg]] = {}
        for row in rows:
            baskets.setdefault(
                (pd.Timestamp(row.entry_time), pd.Timestamp(row.exit_time)), []
            ).append(row)
        previous_exit = None
        for (entry, exit_), basket in sorted(baskets.items()):
            if sum(row.weight for row in basket) > 1 + 1e-12 or (
                previous_exit is not None and entry < previous_exit
            ):
                raise ValueError("Leverage/overlapping full-capital allocations are not authorized")
            if len({row.symbol for row in basket}) != len(basket):
                raise ValueError("Duplicate symbol in a basket")
            previous_exit = exit_
        for name in data:
            data[name][day] = 0.0
        for _, basket in sorted(baskets.items()):
            subtotal = dict.fromkeys(data, 0.0)
            for row in basket:
                calc = leg_returns(row, costs)
                stress = leg_returns(
                    row,
                    Costs(
                        2 * costs.extra_bps_each_side,
                        costs.sell_notional_rate,
                        costs.sell_per_share,
                    ),
                )
                for name, key in [("reference", "reference_return"), ("net", "net_return")]:
                    subtotal[name] += row.weight * calc[key]
                if calc["crossed_return"] is not None:
                    subtotal["crossed"] += row.weight * calc["crossed_return"]
                subtotal["cost_stress"] += row.weight * stress["net_return"]
                accounting.append({**asdict(row), **calc})
            for name in data:
                data[name][day] = (1 + data[name][day]) * (1 + subtotal[name]) - 1
    missing = [d for d in days if decisions[d] == "missing"]
    known = [d for d in days if d not in missing]
    net = np.array([data["net"][d] for d in known])
    metrics = {
        key: path_metrics(list(values.values()), initial_cash)
        for key, values in data.items()
        if key != "crossed" or quote_only
    }
    if not quote_only:
        metrics["crossed"] = None
    bm = path_metrics(benchmark.to_numpy(), initial_cash)
    ci = paired_mean_interval(net, benchmark.loc[known].to_numpy()) if not missing else None
    checks = {
        "data_complete": not missing,
        "positive_net": metrics["net"]["ending_cash"] > initial_cash,
        "beats_SPY": not missing and metrics["net"]["ending_cash"] > bm["ending_cash"],
        "positive_excess_lower95": ci is not None and ci[0] > 0,
        "positive_cost_stress": metrics["cost_stress"]["ending_cash"] > initial_cash,
    }
    return {
        "contract_version": 1,
        "costs": asdict(costs),
        "calendar_sessions": len(days),
        "known_sessions": len(known),
        "trade_days": len(grouped),
        "legs": len(legs),
        "missing_dates": missing,
        "complete_equity": not missing,
        "ending_cash": metrics["net"]["ending_cash"] if not missing else None,
        "available_case_metrics": metrics,
        "SPY": bm,
        "excess_mean_daily_95_interval": ci,
        "economic_checks": checks,
        "preliminary_economic_pass": all(checks.values()),
        "execution_evidence": "observed_quotes"
        if quote_only
        else "bar_scenario_not_quote_validated",
        "daily_returns": data,
        "accounting": accounting,
    }
