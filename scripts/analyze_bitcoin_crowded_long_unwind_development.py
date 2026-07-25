"""Descriptive logical-end audit of the consumed crowded-long development panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PANEL = Path("data/parquet/bitcoin_crowded_long_unwind_binance_v1/development/panel.parquet")
OUTPUT = Path("data/parquet/bitcoin_crowded_long_unwind_binance_v1/development/descriptive_audit.json")


def _bootstrap_mean(values: np.ndarray, *, seed: int, resamples: int = 20_000) -> list[float]:
    rng = np.random.default_rng(seed)
    means = np.mean(rng.choice(values, size=(resamples, len(values)), replace=True), axis=1)
    return [float(x) for x in np.quantile(means, [0.025, 0.975])]


def _month_block_bootstrap(panel: pd.DataFrame, *, seed: int, resamples: int = 20_000) -> list[float]:
    work = panel.copy()
    work["month"] = pd.to_datetime(work["session_date"]).dt.to_period("M").astype(str)
    months = work["month"].unique()
    groups = {month: work.loc[work["month"] == month] for month in months}
    rng = np.random.default_rng(seed)
    means: list[float] = []
    for _ in range(resamples):
        sampled = rng.choice(months, size=len(months), replace=True)
        returns = pd.concat(
            [groups[month].loc[groups[month]["selected"], "short_return"] for month in sampled],
            ignore_index=True,
        )
        if len(returns):
            means.append(float(returns.mean()))
    return [float(x) for x in np.quantile(means, [0.025, 0.975])]


def _permutation_difference(
    first: np.ndarray, second: np.ndarray, *, seed: int, resamples: int = 50_000
) -> dict[str, float | list[float]]:
    observed = float(np.mean(first) - np.mean(second))
    pooled = np.concatenate([first, second])
    rng = np.random.default_rng(seed)
    differences = np.empty(resamples)
    for index in range(resamples):
        shuffled = rng.permutation(pooled)
        differences[index] = np.mean(shuffled[: len(first)]) - np.mean(shuffled[len(first) :])
    return {
        "observed_difference_bps": observed * 10_000.0,
        "two_sided_pvalue": float((np.abs(differences) >= abs(observed)).mean()),
        "null_95_bps": [float(x * 10_000.0) for x in np.quantile(differences, [0.025, 0.975])],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    panel = pd.read_parquet(args.panel).sort_values("session_date", kind="stable").reset_index(drop=True)
    selected = panel.loc[panel["selected"]].copy()
    funding_without_oi = panel.loc[panel["funding_extreme"] & ~panel["oi_expanding"]].copy()
    selected_values = selected["short_return"].to_numpy(float)
    comparison_values = funding_without_oi["short_return"].to_numpy(float)
    dates = pd.to_datetime(selected["session_date"])
    gaps = dates.diff().dt.days.dropna()
    leave_one_out = np.array(
        [np.delete(selected_values, index).mean() for index in range(len(selected_values))]
    )
    spearman = stats.spearmanr(
        panel.loc[panel["funding_extreme"], "oi_change_8h"],
        panel.loc[panel["funding_extreme"], "short_return"],
    )
    ttest = stats.ttest_1samp(selected_values, popmean=0.0)
    sign_test = stats.binomtest(int((selected_values > 0).sum()), len(selected_values), 0.5)
    welch = stats.ttest_ind(selected_values, comparison_values, equal_var=False)
    positive = selected.loc[selected["short_return"] > 0, "short_return"].sort_values(ascending=False)
    total_positive = float(positive.sum())
    by_year = {}
    for year, group in panel.groupby(pd.to_datetime(panel["session_date"]).dt.year):
        selected_year = group.loc[group["selected"], "short_return"]
        by_year[str(year)] = {
            "complete_days": int(len(group)),
            "funding_extreme_days": int(group["funding_extreme"].sum()),
            "oi_expanding_days": int(group["oi_expanding"].sum()),
            "combined_days": int(group["selected"].sum()),
            "combined_mean_gross_bps": (
                float(selected_year.mean() * 10_000.0) if len(selected_year) else None
            ),
            "combined_mean_after_20bps": (
                float((selected_year - 0.002).mean() * 10_000.0) if len(selected_year) else None
            ),
        }
    output = {
        "scope": "consumed development panel only; no validation or holdout data",
        "purpose": "descriptive mechanism audit, not parameter selection or strategy rescue",
        "days": int(len(panel)),
        "selected_days": int(len(selected)),
        "primary": {
            "mean_gross_bps": float(selected_values.mean() * 10_000.0),
            "median_gross_bps": float(np.median(selected_values) * 10_000.0),
            "iid_bootstrap_95_bps": [x * 10_000.0 for x in _bootstrap_mean(selected_values, seed=101)],
            "month_block_bootstrap_95_bps": [
                x * 10_000.0 for x in _month_block_bootstrap(panel, seed=102)
            ],
            "one_sample_t_pvalue_two_sided": float(ttest.pvalue),
            "exact_sign_test_pvalue_two_sided": float(sign_test.pvalue),
            "wins": int((selected_values > 0).sum()),
            "losses": int((selected_values <= 0).sum()),
            "leave_one_out_mean_bps_range": [
                float(leave_one_out.min() * 10_000.0),
                float(leave_one_out.max() * 10_000.0),
            ],
        },
        "interaction": {
            "funding_extreme_with_rising_oi_days": int(len(selected_values)),
            "funding_extreme_with_rising_oi_mean_bps": float(selected_values.mean() * 10_000.0),
            "funding_extreme_without_rising_oi_days": int(len(comparison_values)),
            "funding_extreme_without_rising_oi_mean_bps": float(
                comparison_values.mean() * 10_000.0
            ),
            "welch_t_pvalue_two_sided": float(welch.pvalue),
            "permutation": _permutation_difference(
                selected_values, comparison_values, seed=103
            ),
            "spearman_oi_change_vs_short_return_within_funding_extremes": {
                "rho": float(spearman.statistic),
                "pvalue_two_sided": float(spearman.pvalue),
            },
        },
        "concentration": {
            "largest_profitable_day_contribution": (
                float(positive.iloc[0] / total_positive) if total_positive else None
            ),
            "top_three_profitable_days_contribution": (
                float(positive.iloc[:3].sum() / total_positive) if total_positive else None
            ),
            "events_within_7_days_of_prior_event": int((gaps <= 7).sum()),
            "median_gap_days": float(gaps.median()),
            "maximum_gap_days": int(gaps.max()),
        },
        "by_year": by_year,
        "events": [
            {
                "session_date": str(row.session_date),
                "funding_rate": float(row.funding_rate),
                "funding_threshold": float(row.funding_threshold),
                "oi_change_8h": float(row.oi_change_8h),
                "short_return_bps": float(row.short_return * 10_000.0),
            }
            for row in selected.itertuples(index=False)
        ],
        "prohibited_inference": [
            "The diagnostics do not authorize changing the threshold, horizon, sign, OI definition, or costs.",
            "The diagnostics do not authorize opening 2023-2025 for this specification.",
            "Event narratives or crisis labels are not causal evidence.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
