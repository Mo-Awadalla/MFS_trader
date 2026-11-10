"""Exploratory test of state-dependent impact hypotheses 36-38 and 41."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from research.impact_regimes import impact_features, log_impact_fit
from research_scout.test_multiscale_liquidity_v4 import estimator, scores

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout" / "navier_stokes_liquidity_v2"
PANEL = BASE / "executable_liquidity_results" / "feature_panel.parquet"
OUTPUT = BASE / "impact_regime_results"
BASELINE = [
    "spread_bps",
    "total_depth",
    "imbalance",
    "realized_vol_60s",
    "event_rate",
    "trade_count",
    "trade_volume",
    "signed_trade_imbalance",
]
AUGMENTED = [
    "prior_stress",
    "rolling_impact_exponent",
    "rolling_impact_convexity",
    "impact_exponent_change_60s",
    "known_permanence_5m",
    "stress_flow_interaction",
]


def bootstrap_interval(values: list[float], seed: int) -> tuple[float | None, list[float | None]]:
    array = np.asarray(values)
    if not len(array):
        return None, [None, None]
    rng = np.random.default_rng(seed)
    boot = np.asarray([rng.choice(array, len(array), replace=True).mean() for _ in range(1000)])
    return float(array.mean()), [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]


def state_effects(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, object]:
    low = float(train["prior_stress"].quantile(0.2))
    high = float(train["prior_stress"].quantile(0.8))
    work = test.copy()
    work["block"] = np.arange(len(work)) // 60
    effects: dict[str, list[float]] = {"h36_susceptibility": [], "h37_exponent": [], "h37_convexity": [], "h41_permanence": []}
    for _, block in work.groupby("block"):
        eligible = block.loc[block["signed_trade_volume"].abs().gt(0)].dropna(
            subset=["prior_stress", "impact_susceptibility", "participation", "immediate_aligned_impact", "episode_permanence"]
        )
        lows = eligible.loc[eligible["prior_stress"].le(low)]
        highs = eligible.loc[eligible["prior_stress"].ge(high)]
        if len(lows) < 5 or len(highs) < 5:
            continue
        effects["h36_susceptibility"].append(float(highs["impact_susceptibility"].mean() - lows["impact_susceptibility"].mean()))
        low_exp, low_curve = log_impact_fit(
            np.log(lows["participation"].clip(lower=1e-6)).to_numpy(),
            np.log(lows["immediate_aligned_impact"].abs().add(0.01)).to_numpy(),
        )
        high_exp, high_curve = log_impact_fit(
            np.log(highs["participation"].clip(lower=1e-6)).to_numpy(),
            np.log(highs["immediate_aligned_impact"].abs().add(0.01)).to_numpy(),
        )
        effects["h37_exponent"].append(high_exp - low_exp)
        effects["h37_convexity"].append(high_curve - low_curve)
        effects["h41_permanence"].append(float(highs["episode_permanence"].mean() - lows["episode_permanence"].mean()))
    output = {}
    for offset, (name, values) in enumerate(effects.items()):
        mean, interval = bootstrap_interval(values, 20260913 + offset)
        output[name] = {
            "high_minus_low_mean": mean,
            "block_bootstrap_95pct_ci": interval,
            "eligible_blocks": len(values),
            "supported": bool(interval[0] is not None and interval[0] > 0),
        }
    return output


def exponent_change_test(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, object]:
    feature = "impact_exponent_change_60s"
    low, high = float(train[feature].quantile(0.2)), float(train[feature].quantile(0.8))
    work = test.copy()
    work["block"] = np.arange(len(work)) // 60
    deltas = []
    for _, block in work.groupby("block"):
        lows = block.loc[block[feature].le(low), "future_max_excursion_bps"].dropna()
        highs = block.loc[block[feature].ge(high), "future_max_excursion_bps"].dropna()
        if len(lows) >= 2 and len(highs) >= 2:
            deltas.append(float(highs.mean() - lows.mean()))
    mean, interval = bootstrap_interval(deltas, 20261001)
    rho, naive_p = spearmanr(test[feature], test["future_max_excursion_bps"], nan_policy="omit")
    return {
        "spearman_rho_test": float(rho),
        "naive_p_not_independence_adjusted": float(naive_p),
        "high_minus_low_excursion_bps": mean,
        "block_bootstrap_95pct_ci": interval,
        "eligible_blocks": len(deltas),
        "supported": bool(rho > 0 and interval[0] is not None and interval[0] > 0),
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(PANEL).copy()
    raw_stress = frame["spread_bps"] / frame["near_qty_1bps_total"].clip(lower=1e-6)
    features = impact_features(
        frame["midpoint"],
        frame["signed_trade_volume"],
        frame["trade_volume"],
        raw_stress.shift(1),
    )
    frame = frame.join(features).replace([np.inf, -np.inf], np.nan)
    usable = frame.dropna(subset=["future_max_excursion_bps"])
    first, second = int(len(usable) * 0.6), int(len(usable) * 0.8)
    train, validation, test = usable.iloc[:first], usable.iloc[first:second], usable.iloc[second:]
    threshold = float(train["future_max_excursion_bps"].quantile(0.95))
    y_train = train["future_max_excursion_bps"].ge(threshold)
    model_results = {}
    for name, columns in (("baseline", BASELINE), ("augmented", BASELINE + AUGMENTED)):
        fitted = estimator().fit(train[columns], y_train)
        model_results[name] = {}
        for split_name, split in (("validation", validation), ("test", test)):
            y = split["future_max_excursion_bps"].ge(threshold).to_numpy()
            model_results[name][split_name] = scores(y, fitted.predict_proba(split[columns])[:, 1])
    base_test, augmented_test = model_results["baseline"]["test"], model_results["augmented"]["test"]
    incremental = {
        "average_precision": augmented_test["average_precision"] - base_test["average_precision"],
        "roc_auc": augmented_test["roc_auc"] - base_test["roc_auc"],
        "brier_improvement": base_test["brier"] - augmented_test["brier"],
    }
    direct = state_effects(train, test)
    h38 = exponent_change_test(train, test)
    primary = incremental["average_precision"] > 0.02 and incremental["brier_improvement"] > 0
    survivors = [name for name, result in direct.items() if result["supported"]]
    if h38["supported"]:
        survivors.append("h38_exponent_change")
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "exploratory_reuse_of_seen_clean_day_not_confirmation_or_trading_approval",
        "hypotheses": [36, 37, 38, 41],
        "paid_requests_made": False,
        "rows": {"panel": len(frame), "train": len(train), "validation": len(validation), "test": len(test)},
        "jump_threshold_bps": threshold,
        "models": model_results,
        "test_incremental": incremental,
        "primary_gate_passed": primary,
        "direct_state_tests": direct,
        "h38_exponent_change_test": h38,
        "survivors_requiring_2024_replication": survivors,
        "verdict": "IMPACT_CANDIDATES_REQUIRE_REPLICATION" if survivors else "IMPACT_IMPLEMENTATIONS_NOT_SUPPORTED",
    }
    frame.to_parquet(OUTPUT / "feature_panel.parquet")
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
