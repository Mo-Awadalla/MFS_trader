"""Clean-date BBO replication for the observable concentration hypotheses."""

from __future__ import annotations

import json
import math
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research_scout" / "navier_stokes_liquidity_v2" / "free_data" / "binance-public" / "futures-um" / "BTCUSDT" / "2024-01-15"
BOOK = DATA / "BTCUSDT-bookTicker-2024-01-15.zip"
TRADES = DATA / "BTCUSDT-aggTrades-2024-01-15.zip"
OUTPUT = ROOT / "research_scout" / "navier_stokes_liquidity_v2" / "bbo_replication_results"
BIN_MS = 10_000
SUBBINS = 100
HORIZON = 6

BASELINE = ["spread_mean", "spread_last", "depth_mean", "depth_min", "imbalance_mean", "imbalance_last", "realized_vol_60s", "trade_volume", "signed_trade_imbalance", "event_rate"]
AUGMENTED = ["return_linf_l2", "event_linf_l2", "spectral_cascade_ratio", "inverse_interevent", "gross_to_net_trade", "opposing_trade_stress", "price_sensitivity", "depth_change", "stress_flow_interaction"]
ORIENTED = {
    "h2_return_norm_concentration": "return_linf_l2",
    "h17_h18_opposing_trade_stress": "opposing_trade_stress",
    "h18_gross_hidden_by_net": "gross_to_net_trade",
    "h23_spectral_migration": "spectral_cascade_ratio",
    "h24_event_acceleration": "inverse_interevent",
    "h51_price_sensitivity": "price_sensitivity",
    "h53_depth_contraction": "negative_depth_change",
}


@dataclass
class Bin:
    count: int = 0
    spread_sum: float = 0.0
    depth_sum: float = 0.0
    imbalance_sum: float = 0.0
    depth_min: float = math.inf
    last_key: tuple[int, int] = (-1, -1)
    last_mid: float = math.nan
    last_spread: float = math.nan
    last_depth: float = math.nan
    last_imbalance: float = math.nan
    sub_counts: np.ndarray = field(default_factory=lambda: np.zeros(SUBBINS, dtype=np.int64))
    sub_keys: np.ndarray = field(default_factory=lambda: np.full(SUBBINS, -1, dtype=np.int64))
    sub_mid: np.ndarray = field(default_factory=lambda: np.full(SUBBINS, np.nan))

    def add(self, update_id: int, bid: float, bid_qty: float, ask: float, ask_qty: float, event_ms: int) -> None:
        mid = (bid + ask) / 2.0
        spread = 10_000.0 * (ask - bid) / mid
        depth = bid_qty + ask_qty
        imbalance = (bid_qty - ask_qty) / max(depth, 1e-12)
        self.count += 1
        self.spread_sum += spread
        self.depth_sum += depth
        self.imbalance_sum += imbalance
        self.depth_min = min(self.depth_min, depth)
        key = (event_ms, update_id)
        if key >= self.last_key:
            self.last_key = key
            self.last_mid, self.last_spread = mid, spread
            self.last_depth, self.last_imbalance = depth, imbalance
        sub = min(SUBBINS - 1, (event_ms % BIN_MS) * SUBBINS // BIN_MS)
        if event_ms >= self.sub_keys[sub]:
            self.sub_keys[sub] = event_ms
            self.sub_mid[sub] = mid
        self.sub_counts[sub] += 1


def lp_ratio(values: np.ndarray) -> float:
    values = np.abs(values[np.isfinite(values)])
    if values.size == 0 or float(np.sqrt(np.mean(values**2))) == 0.0:
        return 0.0
    return float(values.max() / np.sqrt(np.mean(values**2)))


def extract_book() -> tuple[pd.DataFrame, dict[str, int]]:
    bins: dict[int, Bin] = {}
    rows_seen = 0
    event_backtracks = 0
    previous_event = -1
    with zipfile.ZipFile(BOOK) as archive, archive.open(archive.namelist()[0]) as stream:
        header = stream.readline().rstrip(b"\r\n")
        expected = b"update_id,best_bid_price,best_bid_qty,best_ask_price,best_ask_qty,transaction_time,event_time"
        if header != expected:
            raise ValueError(f"unexpected BBO schema: {header!r}")
        for raw in stream:
            fields = raw.rstrip(b"\r\n").split(b",")
            if len(fields) != 7:
                continue
            update_id = int(fields[0])
            event_ms = int(fields[6])
            event_backtracks += int(event_ms < previous_event)
            previous_event = event_ms
            bin_start = event_ms - event_ms % BIN_MS
            bins.setdefault(bin_start, Bin()).add(
                update_id, float(fields[1]), float(fields[2]), float(fields[3]), float(fields[4]), event_ms
            )
            rows_seen += 1
            if rows_seen % 5_000_000 == 0:
                print(f"processed {rows_seen:,} BBO rows", flush=True)

    output_rows = []
    prior_mid = math.nan
    for start, state in sorted(bins.items()):
        mids = state.sub_mid.copy()
        if np.isfinite(prior_mid):
            mids[np.isnan(mids)] = prior_mid
        mids = pd.Series(mids).ffill().bfill().to_numpy(float)
        returns = np.diff(np.log(mids)) * 10_000.0 if np.isfinite(mids).all() else np.asarray([])
        counts = state.sub_counts.astype(float)
        centered = counts - counts.mean()
        power = np.abs(np.fft.rfft(centered)) ** 2
        frequency = np.fft.rfftfreq(SUBBINS, d=0.1)
        high = float(power[(frequency >= 1.0) & (frequency <= 5.0)].sum())
        low = float(power[(frequency >= 0.1) & (frequency < 1.0)].sum())
        event_l2 = float(np.sqrt(np.mean(counts**2)))
        output_rows.append({
            "time": pd.to_datetime(start, unit="ms", utc=True),
            "midpoint": state.last_mid,
            "spread_mean": state.spread_sum / state.count,
            "spread_last": state.last_spread,
            "depth_mean": state.depth_sum / state.count,
            "depth_min": state.depth_min,
            "depth_last": state.last_depth,
            "imbalance_mean": state.imbalance_sum / state.count,
            "imbalance_last": state.last_imbalance,
            "event_rate": state.count / 10.0,
            "return_linf_l2": lp_ratio(returns),
            "event_linf_l2": float(counts.max() / event_l2) if event_l2 else 0.0,
            "spectral_cascade_ratio": high / max(low, 1e-12),
            "inverse_interevent": state.count / 10_000.0,
        })
        prior_mid = state.last_mid
    return pd.DataFrame(output_rows).set_index("time"), {"rows_seen": rows_seen, "event_timestamp_backtracks": event_backtracks}


def load_trades(origin_ms: int) -> pd.DataFrame:
    trades = pd.read_csv(TRADES, compression="zip")
    trades["bin_ms"] = origin_ms + ((trades["transact_time"] - origin_ms) // BIN_MS) * BIN_MS
    trades["buy"] = np.where(~trades["is_buyer_maker"].astype(bool), trades["quantity"], 0.0)
    trades["sell"] = np.where(trades["is_buyer_maker"].astype(bool), trades["quantity"], 0.0)
    grouped = trades.groupby("bin_ms").agg(buy_volume=("buy", "sum"), sell_volume=("sell", "sum"), trade_count=("quantity", "size"))
    grouped.index = pd.to_datetime(grouped.index, unit="ms", utc=True)
    return grouped


def derive(book: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    frame = book.join(trades, how="left").fillna({"buy_volume": 0.0, "sell_volume": 0.0, "trade_count": 0.0})
    frame["trade_volume"] = frame["buy_volume"] + frame["sell_volume"]
    frame["signed_trade_imbalance"] = ((frame["buy_volume"] - frame["sell_volume"]) / frame["trade_volume"].replace(0, np.nan)).fillna(0.0)
    frame["gross_to_net_trade"] = frame["trade_volume"] / (frame["buy_volume"] - frame["sell_volume"]).abs().add(1.0)
    frame["opposing_trade_stress"] = np.sqrt(frame["buy_volume"] * frame["sell_volume"]) / frame["depth_last"].clip(lower=1e-12)
    frame["mid_return_bps"] = np.log(frame["midpoint"]).diff() * 10_000.0
    frame["realized_vol_60s"] = frame["mid_return_bps"].rolling(HORIZON, min_periods=2).std()
    frame["price_sensitivity"] = frame["mid_return_bps"].abs() / frame["trade_volume"].replace(0, np.nan)
    frame["depth_change"] = frame["depth_last"].pct_change()
    frame["negative_depth_change"] = -frame["depth_change"]
    frame["stress_flow_interaction"] = frame["return_linf_l2"] * frame["signed_trade_imbalance"].abs()
    mids = frame["midpoint"].to_numpy(float)
    excursion = np.full(len(frame), np.nan)
    future_return = np.full(len(frame), np.nan)
    for i in range(len(frame) - HORIZON):
        path = np.log(mids[i + 1 : i + HORIZON + 1] / mids[i]) * 10_000.0
        excursion[i], future_return[i] = np.max(np.abs(path)), path[-1]
    frame["future_max_excursion_bps"] = excursion
    frame["future_return_bps"] = future_return
    return frame.replace([np.inf, -np.inf], np.nan)


def estimator() -> Pipeline:
    return Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", RobustScaler(quantile_range=(10, 90))), ("model", LogisticRegression(C=0.25, class_weight="balanced", max_iter=2000))])


def score(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    return {"average_precision": float(average_precision_score(y, p)), "roc_auc": float(roc_auc_score(y, p)), "brier": float(brier_score_loss(y, p))}


def blocked_tests(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, object]:
    rng = np.random.default_rng(20260913)
    work = test.copy()
    work["block"] = np.arange(len(work)) // 60
    output: dict[str, object] = {}
    for label, feature in ORIENTED.items():
        low, high = float(train[feature].quantile(0.2)), float(train[feature].quantile(0.8))
        deltas = []
        for _, block in work.groupby("block"):
            lows = block.loc[block[feature] <= low, "future_max_excursion_bps"]
            highs = block.loc[block[feature] >= high, "future_max_excursion_bps"]
            if len(lows) >= 2 and len(highs) >= 2:
                deltas.append(float(highs.mean() - lows.mean()))
        if deltas:
            values = np.asarray(deltas)
            bootstrap = np.asarray([rng.choice(values, len(values), replace=True).mean() for _ in range(1_000)])
            interval = [float(np.quantile(bootstrap, 0.025)), float(np.quantile(bootstrap, 0.975))]
            delta = float(values.mean())
        else:
            interval, delta = [None, None], None
        rho, naive_p = spearmanr(test[feature], test["future_max_excursion_bps"], nan_policy="omit")
        output[label] = {
            "feature": feature,
            "spearman_rho_test": float(rho),
            "naive_p_not_independence_adjusted": float(naive_p),
            "high_minus_low_excursion_bps": delta,
            "block_bootstrap_95pct_ci": interval,
            "eligible_blocks": len(deltas),
            "directionally_supported": bool(interval[0] is not None and interval[0] > 0 and rho > 0),
        }
    return output


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    panel_path = OUTPUT / "feature_panel.parquet"
    if panel_path.exists():
        frame = pd.read_parquet(panel_path)
        if "negative_depth_change" not in frame:
            frame["negative_depth_change"] = -frame["depth_change"]
        diagnostics = json.loads((OUTPUT / "ingestion_diagnostics.json").read_text())
    else:
        book, diagnostics = extract_book()
        origin_ms = int(book.index[0].timestamp() * 1000)
        frame = derive(book, load_trades(origin_ms))
        frame.to_parquet(panel_path)
        (OUTPUT / "ingestion_diagnostics.json").write_text(json.dumps(diagnostics, indent=2) + "\n")
    usable = frame.dropna(subset=["future_max_excursion_bps"])
    a, b = int(len(usable) * 0.6), int(len(usable) * 0.8)
    train, validation, test = usable.iloc[:a], usable.iloc[a:b], usable.iloc[b:]
    threshold = float(train["future_max_excursion_bps"].quantile(0.95))
    model_results: dict[str, dict[str, dict[str, float]]] = {}
    for name, features in (("baseline", BASELINE), ("augmented", BASELINE + AUGMENTED)):
        fitted = estimator().fit(train[features], train["future_max_excursion_bps"].ge(threshold))
        model_results[name] = {}
        for split_name, split in (("validation", validation), ("test", test)):
            y = split["future_max_excursion_bps"].ge(threshold).to_numpy()
            model_results[name][split_name] = score(y, fitted.predict_proba(split[features])[:, 1])
    base, aug = model_results["baseline"]["test"], model_results["augmented"]["test"]
    incremental = {"average_precision": aug["average_precision"] - base["average_precision"], "roc_auc": aug["roc_auc"] - base["roc_auc"], "brier_improvement": base["brier"] - aug["brier"]}
    tests = {}
    for feature in AUGMENTED:
        rho, naive_p = spearmanr(test[feature], test["future_max_excursion_bps"], nan_policy="omit")
        tests[feature] = {"spearman_rho_test": float(rho), "naive_p": float(naive_p)}
    block_results = blocked_tests(train, test)
    primary = incremental["average_precision"] > 0.02 and incremental["brier_improvement"] > 0
    payload = {"created_at_utc": datetime.now(UTC).isoformat(), "status": "single_day_bbo_replication_not_trading_approval", "diagnostics": diagnostics, "rows": {"panel": len(frame), "train": len(train), "validation": len(validation), "test": len(test)}, "jump_threshold_bps": threshold, "models": model_results, "test_incremental": incremental, "feature_correlations": tests, "blocked_feature_tests": block_results, "primary_gate_passed": primary, "verdict": "BBO_REPLICATION_PASS_REQUIRES_MORE_DAYS" if primary else "BBO_REPLICATION_FAIL"}
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
