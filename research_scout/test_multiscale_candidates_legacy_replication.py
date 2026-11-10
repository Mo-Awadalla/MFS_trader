"""Frozen free replication of the H28/H30 candidates on the legacy L2 day."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from research_scout.test_multiscale_liquidity_v4 import (
    estimator,
    extract_trade_features,
    scores,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout" / "navier_stokes_liquidity_v2"
PANEL = BASE / "crypto_l2_results" / "feature_panel.parquet"
TRADES = BASE / "free_data" / "tardis" / "binance-futures" / "trades" / "2020-02-01" / "BTCUSDT.csv.gz"
OUTPUT = BASE / "multiscale_candidate_legacy_replication_results"
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
CANDIDATES = {
    "h28_wavelet_high_frequency_energy": "haar_high_low_ratio",
    "h30_cross_scale_coupling": "cross_scale_coupling",
}


def blocked_test(train: pd.DataFrame, test: pd.DataFrame, feature: str) -> dict[str, object]:
    low, high = float(train[feature].quantile(0.2)), float(train[feature].quantile(0.8))
    work = test.copy()
    work["block"] = np.arange(len(work)) // 60
    deltas = []
    for _, block in work.groupby("block"):
        lows = block.loc[block[feature].le(low), "future_max_excursion_bps"].dropna()
        highs = block.loc[block[feature].ge(high), "future_max_excursion_bps"].dropna()
        if len(lows) >= 2 and len(highs) >= 2:
            deltas.append(float(highs.mean() - lows.mean()))
    values = np.asarray(deltas)
    rng = np.random.default_rng(20260913)
    boot = np.asarray([rng.choice(values, len(values), replace=True).mean() for _ in range(1000)])
    interval = [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]
    rho, naive_p = spearmanr(test[feature], test["future_max_excursion_bps"], nan_policy="omit")
    return {
        "spearman_rho_test": float(rho),
        "naive_p_not_independence_adjusted": float(naive_p),
        "high_minus_low_excursion_bps": float(values.mean()),
        "block_bootstrap_95pct_ci": interval,
        "eligible_blocks": len(values),
        "replicated": bool(rho > 0 and interval[0] > 0),
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base = pd.read_parquet(PANEL).rename(columns={"top_depth": "total_depth", "book_imbalance": "imbalance"})
    trade_features = extract_trade_features(base.index, TRADES)[list(CANDIDATES.values())]
    frame = base.join(trade_features, how="left").replace([np.inf, -np.inf], np.nan)
    usable = frame.dropna(subset=["future_max_excursion_bps"])
    first, second = int(len(usable) * 0.6), int(len(usable) * 0.8)
    train, validation, test = usable.iloc[:first], usable.iloc[first:second], usable.iloc[second:]
    threshold = float(train["future_max_excursion_bps"].quantile(0.95))
    y_train = train["future_max_excursion_bps"].ge(threshold)
    model_results = {}
    for name, features in (("baseline", BASELINE), ("augmented", BASELINE + list(CANDIDATES.values()))):
        fitted = estimator().fit(train[features], y_train)
        model_results[name] = {}
        for split_name, split in (("validation", validation), ("test", test)):
            y = split["future_max_excursion_bps"].ge(threshold).to_numpy()
            model_results[name][split_name] = scores(y, fitted.predict_proba(split[features])[:, 1])
    base_test, augmented_test = model_results["baseline"]["test"], model_results["augmented"]["test"]
    incremental = {
        "average_precision": augmented_test["average_precision"] - base_test["average_precision"],
        "roc_auc": augmented_test["roc_auc"] - base_test["roc_auc"],
        "brier_improvement": base_test["brier"] - augmented_test["brier"],
    }
    candidate_results = {name: blocked_test(train, test, feature) for name, feature in CANDIDATES.items()}
    combined = incremental["average_precision"] > 0.02 and incremental["brier_improvement"] > 0
    survivors = [name for name, result in candidate_results.items() if result["replicated"]]
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "exploratory_replication_on_pre_quality_cutoff_day_not_trading_approval",
        "paid_requests_made": False,
        "known_limitation": "date precedes Tardis 2020-05-14 collection-quality cutoff",
        "rows": {"panel": len(frame), "train": len(train), "validation": len(validation), "test": len(test)},
        "jump_threshold_bps": threshold,
        "models": model_results,
        "test_incremental": incremental,
        "combined_gate_passed": combined,
        "candidate_results": candidate_results,
        "survivors_requiring_clean_new_day": survivors,
        "verdict": "LEGACY_REPLICATION_SURVIVORS" if survivors else "CANDIDATES_DID_NOT_REPLICATE",
    }
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
