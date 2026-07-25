"""Frozen, public-data test of a visually proposed IREN two-month reversal cycle."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

DISCOVERY_START = "2025-07-23"
TEST_END = "2025-07-22"
SEED = 20260723
PERMUTATIONS = 50_000


def download_adjusted_close(symbol: str) -> pd.Series:
    period1 = int(dt.datetime(2021, 1, 1, tzinfo=dt.UTC).timestamp())
    period2 = int(dt.datetime(2026, 7, 24, tzinfo=dt.UTC).timestamp())
    url = (
        "https://query2.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?period1={period1}&period2={period2}&interval=1d&events=div%2Csplits"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"].get("adjclose", [{}])[0].get(
        "adjclose", quote["close"]
    )
    index = pd.to_datetime(result["timestamp"], unit="s", utc=True).normalize().tz_localize(None)
    return pd.Series(adjusted, index=index, name=symbol, dtype=float).dropna().sort_index()


def corr_or_nan(values: np.ndarray) -> float:
    if len(values) < 3 or np.std(values[:-1]) == 0 or np.std(values[1:]) == 0:
        return math.nan
    return float(np.corrcoef(values[:-1], values[1:])[0, 1])


def permutation_p_negative(values: np.ndarray, observed: float, rng: np.random.Generator) -> float:
    if math.isnan(observed):
        return math.nan
    count = 0
    for _ in range(PERMUTATIONS):
        permuted = rng.permutation(values)
        if corr_or_nan(permuted) <= observed:
            count += 1
    return (count + 1) / (PERMUTATIONS + 1)


def make_blocks(daily_log_returns: pd.Series, horizon: int, offset: int = 0) -> np.ndarray:
    values = daily_log_returns.iloc[offset:].to_numpy()
    complete = len(values) // horizon
    if complete == 0:
        return np.array([], dtype=float)
    return values[: complete * horizon].reshape(complete, horizon).sum(axis=1)


def summarize_blocks(blocks: np.ndarray, rng: np.random.Generator) -> dict[str, float | int]:
    observed = corr_or_nan(blocks)
    transitions = len(blocks) - 1
    opposite = int(np.sum(np.sign(blocks[:-1]) != np.sign(blocks[1:]))) if transitions else 0
    midpoint = len(blocks) // 2
    return {
        "blocks": len(blocks),
        "lag_correlation": observed,
        "permutation_p_negative": permutation_p_negative(blocks, observed, rng),
        "opposite_sign_transitions": opposite,
        "transitions": transitions,
        "opposite_sign_rate": opposite / transitions if transitions else math.nan,
        "first_half_lag_correlation": corr_or_nan(blocks[:midpoint]),
        "second_half_lag_correlation": corr_or_nan(blocks[midpoint:]),
    }


def ols_residuals(frame: pd.DataFrame) -> tuple[pd.Series, dict[str, float]]:
    y = frame["IREN"].to_numpy()
    x = np.column_stack([np.ones(len(frame)), frame["BTC-USD"], frame["QQQ"]])
    coefficients, *_ = np.linalg.lstsq(x, y, rcond=None)
    residuals = y - x @ coefficients
    return pd.Series(residuals, index=frame.index), {
        "intercept_daily": float(coefficients[0]),
        "btc_beta": float(coefficients[1]),
        "qqq_beta": float(coefficients[2]),
        "daily_r_squared": float(1 - np.sum(residuals**2) / np.sum((y - y.mean()) ** 2)),
    }


def run(input_prices: pd.DataFrame | None = None) -> tuple[dict[str, object], pd.DataFrame]:
    prices = input_prices
    if prices is None:
        prices = pd.concat(
            [download_adjusted_close(symbol) for symbol in ("IREN", "BTC-USD", "QQQ")],
            axis=1,
            sort=True,
        )
    prices = prices.loc[:TEST_END].dropna()
    prices_csv = prices.to_csv(index_label="date", float_format="%.17g", lineterminator="\n")
    prices_sha256 = hashlib.sha256(prices_csv.encode()).hexdigest()
    returns = np.log(prices).diff().dropna()
    iren_returns = returns["IREN"]
    residuals, factor_fit = ols_residuals(returns)
    rng = np.random.default_rng(SEED)

    raw_primary = summarize_blocks(make_blocks(iren_returns, 42), rng)
    adjusted_primary = summarize_blocks(make_blocks(residuals, 42), rng)
    alternate = {
        str(horizon): {
            "raw": summarize_blocks(make_blocks(iren_returns, horizon), rng),
            "factor_adjusted": summarize_blocks(make_blocks(residuals, horizon), rng),
        }
        for horizon in (21, 63)
    }
    phase_correlations = [corr_or_nan(make_blocks(iren_returns, 42, offset)) for offset in range(42)]
    valid_phases = np.array([value for value in phase_correlations if not math.isnan(value)])

    gate_checks = {
        "raw_negative_p_lt_0_05": bool(
            raw_primary["lag_correlation"] < 0
            and raw_primary["permutation_p_negative"] < 0.05
        ),
        "adjusted_negative_p_lt_0_05": bool(
            adjusted_primary["lag_correlation"] < 0
            and adjusted_primary["permutation_p_negative"] < 0.05
        ),
        "opposite_sign_rate_gte_0_60": bool(raw_primary["opposite_sign_rate"] >= 0.60),
        "both_halves_negative": bool(
            raw_primary["first_half_lag_correlation"] < 0
            and raw_primary["second_half_lag_correlation"] < 0
        ),
    }
    return {
        "data": {
            "source": "Yahoo Finance public chart endpoint",
            "test_start": str(returns.index.min().date()),
            "test_end": str(returns.index.max().date()),
            "daily_observations": len(returns),
            "discovery_start_excluded": DISCOVERY_START,
            "input_prices_sha256": prices_sha256,
        },
        "factor_fit": factor_fit,
        "primary_42_day": {"raw": raw_primary, "factor_adjusted": adjusted_primary},
        "success_gate_checks": gate_checks,
        "success_gate_passed": all(gate_checks.values()),
        "robustness_alternate_horizons": alternate,
        "phase_sensitivity_42_day_raw": {
            "valid_phases": len(valid_phases),
            "negative_fraction": float(np.mean(valid_phases < 0)),
            "median_correlation": float(np.median(valid_phases)),
            "min_correlation": float(np.min(valid_phases)),
            "max_correlation": float(np.max(valid_phases)),
            "correlations": phase_correlations,
        },
    }, prices


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-prices", type=Path)
    args = parser.parse_args()
    input_prices = None
    if args.input_prices:
        input_prices = pd.read_csv(
            args.input_prices,
            index_col="date",
            parse_dates=["date"],
            float_precision="round_trip",
        )
    result, prices = run(input_prices)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(
        args.output.parent / "input_prices.csv",
        index_label="date",
        float_format="%.17g",
        lineterminator="\n",
    )
    args.output.write_text(json.dumps(result, indent=2, allow_nan=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=True))


if __name__ == "__main__":
    main()
