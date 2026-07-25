"""Evaluate one frozen partition of the ES close-flow hypothesis.

Run development first (2021-2023). Evaluating any date in 2024 or later
requires the explicit ``--confirm-holdout`` flag so the holdout cannot be
opened accidentally while iterating on preprocessing.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

MES_MULTIPLIER = 5.0
BASE_COMMISSION = 1.24
BOOTSTRAP_SAMPLES = 10_000
RNG_SEED = 20260725


@dataclass(frozen=True)
class Variant:
    name: str
    mask: pd.Series
    direction: pd.Series


def _execution_gross(frame: pd.DataFrame, direction: pd.Series) -> pd.Series:
    long_mask = direction.gt(0)
    entry = pd.Series(
        np.where(long_mask, frame["entry_ask"], frame["entry_bid"]),
        index=frame.index,
        dtype=float,
    )
    exit_ = pd.Series(
        np.where(long_mask, frame["exit_bid"], frame["exit_ask"]),
        index=frame.index,
        dtype=float,
    )
    return direction.astype(float) * (exit_ - entry) * MES_MULTIPLIER


def _month_cluster_ci(
    values: pd.Series, dates: pd.Series, rng: np.random.Generator
) -> list[float | None]:
    if len(values) < 2:
        return [None, None]
    months = pd.to_datetime(dates).dt.to_period("M").astype(str)
    groups = {
        month: values.loc[months.eq(month)].to_numpy(dtype=float)
        for month in sorted(months.unique())
    }
    keys = np.array(list(groups))
    means = np.empty(BOOTSTRAP_SAMPLES)
    for index in range(BOOTSTRAP_SAMPLES):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        means[index] = np.concatenate([groups[key] for key in sampled]).mean()
    low, high = np.quantile(means, [0.025, 0.975])
    return [float(low), float(high)]


def _max_drawdown(values: pd.Series) -> float:
    cumulative = values.cumsum()
    drawdown = cumulative - cumulative.cummax()
    return float(drawdown.min()) if len(drawdown) else 0.0


def _variant_metrics(
    frame: pd.DataFrame,
    variant: Variant,
    commission: float,
    rng: np.random.Generator,
) -> dict[str, Any]:
    traded = frame.loc[variant.mask].copy()
    direction = variant.direction.loc[variant.mask].astype(int)
    gross = _execution_gross(traded, direction)
    net = gross - commission

    valid_daily = pd.Series(0.0, index=frame.index)
    valid_daily.loc[variant.mask] = net
    daily_std = float(valid_daily.std(ddof=1))
    annualized_sharpe = (
        float(valid_daily.mean() / daily_std * np.sqrt(252))
        if daily_std > 0
        else None
    )
    positive = float(net[net > 0].sum())
    negative = float(-net[net < 0].sum())
    t_stat = (
        float(net.mean() / (net.std(ddof=1) / np.sqrt(len(net))))
        if len(net) > 1 and net.std(ddof=1) > 0
        else None
    )
    return {
        "name": variant.name,
        "trades": int(len(traded)),
        "long_trades": int(direction.gt(0).sum()),
        "short_trades": int(direction.lt(0).sum()),
        "gross_mean_usd": float(gross.mean()) if len(gross) else None,
        "net_mean_usd": float(net.mean()) if len(net) else None,
        "net_median_usd": float(net.median()) if len(net) else None,
        "net_total_usd": float(net.sum()),
        "net_win_rate": float(net.gt(0).mean()) if len(net) else None,
        "profit_factor": positive / negative if negative > 0 else None,
        "trade_mean_t_stat": t_stat,
        "month_cluster_95pct_ci_mean_net_usd": _month_cluster_ci(
            net, traded["date"], rng
        ),
        "annualized_daily_sharpe_zero_when_flat": annualized_sharpe,
        "max_drawdown_usd": _max_drawdown(net),
        "commission_usd_round_trip": commission,
        "yearly": {
            str(year): {
                "trades": int(len(group)),
                "net_total_usd": float(
                    (
                        _execution_gross(
                            group,
                            variant.direction.loc[group.index].astype(int),
                        )
                        - commission
                    ).sum()
                ),
            }
            for year, group in traded.groupby(pd.to_datetime(traded["date"]).dt.year)
        },
    }


def _interaction_test(frame: pd.DataFrame) -> dict[str, Any]:
    candidate = frame[
        frame["data_valid"] & frame["large_move"] & frame["spread_ok"]
    ].copy()
    aligned = candidate["flow_aligned"].astype(bool)
    net = candidate["gross_usd"].astype(float) - BASE_COMMISSION
    aligned_values = net[aligned].to_numpy()
    opposed_values = net[~aligned].to_numpy()
    if len(aligned_values) == 0 or len(opposed_values) == 0:
        return {"candidate_sessions": int(len(candidate)), "test_available": False}

    observed = float(aligned_values.mean() - opposed_values.mean())
    rng = np.random.default_rng(RNG_SEED)
    labels = aligned.to_numpy()
    values = net.to_numpy()
    permuted = np.empty(BOOTSTRAP_SAMPLES)
    for index in range(BOOTSTRAP_SAMPLES):
        shuffled = rng.permutation(labels)
        permuted[index] = values[shuffled].mean() - values[~shuffled].mean()
    p_value = float((1 + np.sum(permuted >= observed)) / (BOOTSTRAP_SAMPLES + 1))

    aligned_wins = int((aligned_values > 0).sum())
    aligned_losses = int((aligned_values <= 0).sum())
    opposed_wins = int((opposed_values > 0).sum())
    opposed_losses = int((opposed_values <= 0).sum())
    odds_ratio, fisher_p = stats.fisher_exact(
        [[aligned_wins, aligned_losses], [opposed_wins, opposed_losses]],
        alternative="greater",
    )
    return {
        "test_available": True,
        "candidate_sessions": int(len(candidate)),
        "aligned_sessions": int(aligned.sum()),
        "opposed_sessions": int((~aligned).sum()),
        "aligned_mean_net_usd": float(aligned_values.mean()),
        "opposed_mean_net_usd": float(opposed_values.mean()),
        "aligned_minus_opposed_mean_net_usd": observed,
        "one_sided_permutation_p": p_value,
        "aligned_net_win_rate": float((aligned_values > 0).mean()),
        "opposed_net_win_rate": float((opposed_values > 0).mean()),
        "fisher_odds_ratio": float(odds_ratio),
        "fisher_one_sided_p": float(fisher_p),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-holdout", action="store_true")
    args = parser.parse_args()

    if pd.Timestamp(args.end) > pd.Timestamp("2024-01-01") and not args.confirm_holdout:
        raise RuntimeError(
            "This partition reaches the frozen 2024-2025 holdout. "
            "Pass --confirm-holdout only after development is final."
        )

    all_features = pd.read_parquet(args.features)
    date_values = pd.to_datetime(all_features["date"])
    frame = all_features[
        date_values.ge(pd.Timestamp(args.start))
        & date_values.lt(pd.Timestamp(args.end))
        & all_features["data_valid"]
    ].copy()
    frame = frame.sort_values("date").reset_index(drop=True)
    price_direction = frame["direction"].astype(int)
    flow_direction = np.sign(frame["signed_volume"]).astype(int)
    variants = [
        Variant(
            "price_only",
            frame["large_move"],
            price_direction,
        ),
        Variant(
            "price_plus_spread",
            frame["large_move"] & frame["spread_ok"],
            price_direction,
        ),
        Variant(
            "frozen_aligned_flow",
            frame["large_move"] & frame["spread_ok"] & frame["flow_aligned"],
            price_direction,
        ),
        Variant(
            "opposed_flow_control",
            frame["large_move"] & frame["spread_ok"] & ~frame["flow_aligned"],
            price_direction,
        ),
        Variant(
            "flow_only_control",
            frame["spread_ok"] & flow_direction.ne(0),
            flow_direction,
        ),
    ]
    results: dict[str, Any] = {}
    for commission in (0.0, BASE_COMMISSION, 2.0):
        rng = np.random.default_rng(RNG_SEED + int(commission * 100))
        results[f"commission_{commission:.2f}"] = {
            variant.name: _variant_metrics(frame, variant, commission, rng)
            for variant in variants
        }

    frozen = results[f"commission_{BASE_COMMISSION:.2f}"]["frozen_aligned_flow"]
    interaction = _interaction_test(frame)
    minimum_evidence_gate = {
        "at_least_30_frozen_trades": frozen["trades"] >= 30,
        "positive_frozen_mean_net": (
            frozen["net_mean_usd"] is not None and frozen["net_mean_usd"] > 0
        ),
        "positive_aligned_minus_opposed": (
            interaction.get("aligned_minus_opposed_mean_net_usd", 0) > 0
        ),
    }
    payload = {
        "label": args.label,
        "start": args.start,
        "end": args.end,
        "valid_sessions": int(len(frame)),
        "parameters_frozen": True,
        "performance": results,
        "interaction_test": interaction,
        "minimum_evidence_gate": minimum_evidence_gate,
        "minimum_evidence_gate_passed": all(minimum_evidence_gate.values()),
        "interpretation_rule": (
            "A live-trading recommendation additionally requires the untouched "
            "2024-2025 holdout to have >=30 trades, positive mean net P&L, "
            "positive aligned-minus-opposed difference, and a positive lower "
            "95% clustered confidence bound for mean net P&L."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
