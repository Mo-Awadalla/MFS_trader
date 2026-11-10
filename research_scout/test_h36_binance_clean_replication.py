"""Clean-date official Binance replication of state-dependent impact H36."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.impact_regimes import impact_features
from research_scout.test_impact_regimes_v5 import bootstrap_interval
from research_scout.test_multiscale_liquidity_v4 import estimator, scores

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout" / "navier_stokes_liquidity_v2"
PANEL = BASE / "bbo_replication_results" / "feature_panel.parquet"
OUTPUT = BASE / "h36_binance_clean_replication_results"
BASELINE = [
    "spread_mean",
    "spread_last",
    "depth_mean",
    "depth_min",
    "imbalance_mean",
    "imbalance_last",
    "realized_vol_60s",
    "trade_volume",
    "signed_trade_imbalance",
    "event_rate",
]
AUGMENTED = ["impact_susceptibility", "prior_stress", "stress_flow_interaction"]


def direct_test(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, object]:
    low, high = float(train["prior_stress"].quantile(0.2)), float(train["prior_stress"].quantile(0.8))
    work = test.copy()
    work["block"] = np.arange(len(work)) // 60
    deltas = []
    for _, block in work.groupby("block"):
        eligible = block.loc[block["signed_trade_volume"].abs().gt(0)].dropna(
            subset=["prior_stress", "impact_susceptibility"]
        )
        lows = eligible.loc[eligible["prior_stress"].le(low), "impact_susceptibility"]
        highs = eligible.loc[eligible["prior_stress"].ge(high), "impact_susceptibility"]
        if len(lows) >= 5 and len(highs) >= 5:
            deltas.append(float(highs.mean() - lows.mean()))
    mean, interval = bootstrap_interval(deltas, 20260913)
    return {
        "high_minus_low_susceptibility_bps": mean,
        "block_bootstrap_95pct_ci": interval,
        "eligible_blocks": len(deltas),
        "replicated": bool(interval[0] is not None and interval[0] > 0),
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(PANEL).iloc[:8_640].copy()
    frame["signed_trade_volume"] = frame["buy_volume"] - frame["sell_volume"]
    raw_stress = frame["spread_mean"] / frame["depth_mean"].clip(lower=1e-6)
    features = impact_features(
        frame["midpoint"],
        frame["signed_trade_volume"],
        frame["trade_volume"],
        raw_stress.shift(1),
    )
    frame = frame.drop(columns=["stress_flow_interaction"], errors="ignore")
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
    direct = direct_test(train, test)
    predictive = incremental["average_precision"] > 0.02 and incremental["brier_improvement"] > 0
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "clean_independent_date_replication_but_not_trading_approval",
        "hypothesis": 36,
        "paid_requests_made": False,
        "rows": {"panel": len(frame), "train": len(train), "validation": len(validation), "test": len(test)},
        "jump_threshold_bps": threshold,
        "models": model_results,
        "test_incremental": incremental,
        "predictive_gate_passed": predictive,
        "direct_state_test": direct,
        "h36_clean_date_replicated": direct["replicated"],
        "verdict": "H36_MECHANISM_REPLICATED_NOT_ALPHA" if direct["replicated"] else "H36_REJECTED",
    }
    frame.to_parquet(OUTPUT / "feature_panel.parquet")
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
