"""Point-in-time BTC five-minute probability model research experiment."""

from __future__ import annotations

import hashlib
import json
import math
import pickle
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

SPEC_PATH = Path("research_scout/bitcoin_5m_probability_binance_v1.json")
DATA_ROOT = Path("data/parquet/bitcoin_5m_probability_binance_v1")
METRICS_PATH = Path(
    "data/parquet/binance_bitcoin_derivatives_public_v1/normalized/futures_metrics_5m.parquet"
)
FEATURE_COLUMNS = (
    "log_return_1_bar",
    "log_return_3_bars",
    "log_return_6_bars",
    "log_return_12_bars",
    "log_range_1_bar",
    "log_body_1_bar",
    "volume_zscore_288_bars",
    "trade_count_zscore_288_bars",
    "taker_flow_1_bar",
    "taker_flow_3_bar_mean",
    "open_interest_log_change_12_bars",
    "open_interest_log_change_48_bars",
    "top_trader_long_short_log_ratio",
    "global_long_short_log_ratio",
    "taker_long_short_log_ratio",
)
BAR_DELTA = pd.Timedelta(minutes=5)
METRIC_LAG = pd.Timedelta(minutes=5)
METRIC_MAX_AGE = pd.Timedelta(minutes=10)


def load_spec(path: Path = SPEC_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("probability-model specification must be a JSON object")
    return cast(dict[str, Any], payload)


def _utc_times(values: pd.Series) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(values, utc=True)).as_unit("ns")


def _validate_bars(bars: pd.DataFrame) -> pd.DataFrame:
    required = {
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trade_count",
        "taker_buy_base_volume",
    }
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"5m bars missing required columns: {sorted(missing)}")
    ordered = bars.copy()
    ordered["open_time"] = pd.to_datetime(ordered["open_time"], utc=True).astype(
        "datetime64[ns, UTC]"
    )
    ordered = ordered.sort_values("open_time", kind="stable").reset_index(drop=True)
    if ordered["open_time"].duplicated().any():
        raise ValueError("5m bar timestamps must be unique")
    numeric = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trade_count",
        "taker_buy_base_volume",
    ]
    ordered[numeric] = ordered[numeric].apply(pd.to_numeric, errors="raise")
    if (ordered[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("5m OHLC prices must be positive")
    if (ordered["volume"] < 0).any() or (ordered["trade_count"] < 0).any():
        raise ValueError("5m volume and trade counts must be non-negative")
    return ordered


def _validate_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    required = {
        "create_time",
        "sum_open_interest",
        "count_toptrader_long_short_ratio",
        "sum_toptrader_long_short_ratio",
        "count_long_short_ratio",
        "sum_taker_long_short_vol_ratio",
    }
    missing = required.difference(metrics.columns)
    if missing:
        raise ValueError(f"5m metrics missing required columns: {sorted(missing)}")
    ordered = metrics.copy()
    ordered["create_time"] = pd.to_datetime(ordered["create_time"], utc=True).astype(
        "datetime64[ns, UTC]"
    )
    ordered = ordered.sort_values("create_time", kind="stable").reset_index(drop=True)
    if ordered["create_time"].duplicated().any():
        raise ValueError("5m metrics timestamps must be unique")
    numeric = sorted(required - {"create_time"})
    ordered[numeric] = ordered[numeric].apply(pd.to_numeric, errors="coerce")
    return ordered


def load_inputs(
    data_root: Path = DATA_ROOT, metrics_path: Path = METRICS_PATH
) -> tuple[pd.DataFrame, pd.DataFrame]:
    bars_path = data_root / "bars_5m.parquet"
    if not bars_path.exists():
        raise FileNotFoundError(f"missing 5m bars: {bars_path}")
    if not metrics_path.exists():
        raise FileNotFoundError(f"missing 5m metrics: {metrics_path}")
    return pd.read_parquet(bars_path), pd.read_parquet(metrics_path)


def _zscore(values: pd.Series, window: int) -> pd.Series:
    mean = values.rolling(window, min_periods=window).mean()
    std = values.rolling(window, min_periods=window).std(ddof=1)
    return (values - mean) / std.replace(0.0, np.nan)


def build_dataset(bars: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    """Build eligible, point-in-time rows for one next-bar probability label."""
    price = _validate_bars(bars)
    metric = _validate_metrics(metrics)
    times = _utc_times(price["open_time"])
    close = price["close"].astype(float)
    open_ = price["open"].astype(float)
    high = price["high"].astype(float)
    low = price["low"].astype(float)
    volume = price["volume"].astype(float)
    trade_count = price["trade_count"].astype(float)
    taker_flow = 2.0 * price["taker_buy_base_volume"].astype(float) / volume.replace(0.0, np.nan) - 1.0

    lagged = pd.DataFrame(
        {
            "log_return_1_bar": np.log(close).diff(1),
            "log_return_3_bars": np.log(close).diff(3),
            "log_return_6_bars": np.log(close).diff(6),
            "log_return_12_bars": np.log(close).diff(12),
            "log_range_1_bar": np.log(high / low),
            "log_body_1_bar": np.log(close / open_),
            "volume_log": np.log1p(volume),
            "trade_count_log": np.log1p(trade_count),
            "taker_flow_1_bar": taker_flow,
            "taker_flow_3_bar_mean": taker_flow.rolling(3, min_periods=3).mean(),
        }
    ).shift(1)
    features = pd.DataFrame(index=price.index)
    features["log_return_1_bar"] = lagged["log_return_1_bar"]
    features["log_return_3_bars"] = lagged["log_return_3_bars"]
    features["log_return_6_bars"] = lagged["log_return_6_bars"]
    features["log_return_12_bars"] = lagged["log_return_12_bars"]
    features["log_range_1_bar"] = lagged["log_range_1_bar"]
    features["log_body_1_bar"] = lagged["log_body_1_bar"]
    features["volume_zscore_288_bars"] = _zscore(lagged["volume_log"], 288)
    features["trade_count_zscore_288_bars"] = _zscore(lagged["trade_count_log"], 288)
    features["taker_flow_1_bar"] = lagged["taker_flow_1_bar"]
    features["taker_flow_3_bar_mean"] = lagged["taker_flow_3_bar_mean"]

    left = pd.DataFrame(
        {
            "open_time": times,
            "metric_cutoff": times - METRIC_LAG,
        }
    )
    joined = pd.merge_asof(
        left.sort_values("metric_cutoff"),
        metric,
        left_on="metric_cutoff",
        right_on="create_time",
        direction="backward",
        tolerance=METRIC_MAX_AGE,
    ).sort_values("open_time", kind="stable")
    metric_age = joined["open_time"] - joined["create_time"]
    oi = joined["sum_open_interest"].where(joined["sum_open_interest"] > 0)
    features["open_interest_log_change_12_bars"] = np.log(oi).diff(12).to_numpy()
    features["open_interest_log_change_48_bars"] = np.log(oi).diff(48).to_numpy()
    features["top_trader_long_short_log_ratio"] = np.log(
        joined["count_toptrader_long_short_ratio"].where(
            joined["count_toptrader_long_short_ratio"] > 0
        )
    ).to_numpy()
    features["global_long_short_log_ratio"] = np.log(
        joined["count_long_short_ratio"].where(joined["count_long_short_ratio"] > 0)
    ).to_numpy()
    features["taker_long_short_log_ratio"] = np.log(
        joined["sum_taker_long_short_vol_ratio"].where(
            joined["sum_taker_long_short_vol_ratio"] > 0
        )
    ).to_numpy()

    transitions = times.to_series().diff().eq(BAR_DELTA)
    continuous = transitions.rolling(12, min_periods=12).sum().eq(12).to_numpy()
    non_tie = close.to_numpy() != open_.to_numpy()
    feature_complete = features.loc[:, FEATURE_COLUMNS].notna().all(axis=1).to_numpy()
    metric_available = metric_age.notna().to_numpy() & (metric_age.to_numpy() <= METRIC_MAX_AGE)
    eligible = continuous & non_tie & feature_complete & metric_available

    result = price.loc[eligible, ["open_time", "open", "high", "low", "close"]].copy()
    result = result.reset_index(drop=True)
    result["label"] = (result["close"] > result["open"]).astype(int)
    result["bar_return"] = result["close"] / result["open"] - 1.0
    result = pd.concat(
        [result, features.loc[eligible, list(FEATURE_COLUMNS)].reset_index(drop=True)], axis=1
    )
    result = result.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
    if result.empty:
        raise ValueError("no eligible 5m observations after point-in-time filtering")
    return result


class CalibratedLogisticProbabilityModel:
    """Standardized logistic classifier with a separate Platt calibrator."""

    def __init__(self, *, C: float = 0.1, random_state: int = 42) -> None:
        self.C = C
        self.random_state = random_state
        self.base: Pipeline | None = None
        self.calibrator: LogisticRegression | None = None

    @staticmethod
    def _logit(probabilities: np.ndarray) -> np.ndarray:
        clipped = np.clip(probabilities, 1e-6, 1.0 - 1e-6)
        return np.log(clipped / (1.0 - clipped))

    def fit(self, training: pd.DataFrame, calibration: pd.DataFrame) -> CalibratedLogisticProbabilityModel:
        if training.empty or calibration.empty:
            raise ValueError("training and calibration partitions must not be empty")
        self.base = Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "logistic",
                    LogisticRegression(
                        C=self.C,
                        max_iter=1000,
                        solver="lbfgs",
                        random_state=self.random_state,
                    ),
                ),
            ]
        )
        self.base.fit(training.loc[:, FEATURE_COLUMNS], training["label"].astype(int))
        raw = self.base.predict_proba(calibration.loc[:, FEATURE_COLUMNS])[:, 1]
        self.calibrator = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs")
        self.calibrator.fit(self._logit(raw).reshape(-1, 1), calibration["label"].astype(int))
        return self

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        if self.base is None or self.calibrator is None:
            raise RuntimeError("probability model is not fitted")
        raw = self.base.predict_proba(frame.loc[:, FEATURE_COLUMNS])[:, 1]
        return self.calibrator.predict_proba(self._logit(raw).reshape(-1, 1))[:, 1]


def _calibration_table(labels: pd.Series, probabilities: np.ndarray) -> list[dict[str, float | int]]:
    bins = pd.cut(
        pd.Series(probabilities),
        bins=np.linspace(0.0, 1.0, 11),
        include_lowest=True,
        right=True,
    )
    table: list[dict[str, float | int]] = []
    for _, group in pd.DataFrame(
        {"probability": probabilities, "label": labels.to_numpy(), "bin": bins}
    ).groupby("bin", observed=False):
        if group.empty:
            continue
        table.append(
            {
                "count": int(len(group)),
                "mean_predicted": float(group["probability"].mean()),
                "actual_rate": float(group["label"].mean()),
                "absolute_calibration_error": float(
                    abs(group["probability"].mean() - group["label"].mean())
                ),
            }
        )
    return table


def evaluate_predictions(
    frame: pd.DataFrame, probabilities: np.ndarray, *, baseline_probability: float
) -> dict[str, Any]:
    labels = frame["label"].astype(int).reset_index(drop=True)
    probabilities = np.asarray(probabilities, dtype=float)
    if len(labels) != len(probabilities):
        raise ValueError("labels and probabilities must have equal length")
    predicted = probabilities >= 0.5
    confident = (probabilities >= 0.55) | (probabilities <= 0.45)
    result: dict[str, Any] = {
        "rows": int(len(labels)),
        "actual_up_rate": float(labels.mean()),
        "mean_predicted_probability": float(probabilities.mean()),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "directional_accuracy_at_50pct": float((predicted == labels.to_numpy()).mean()),
        "baseline_brier_score": float(
            brier_score_loss(labels, np.full(len(labels), baseline_probability))
        ),
        "baseline_log_loss": float(
            log_loss(labels, np.full(len(labels), baseline_probability), labels=[0, 1])
        ),
        "confident_rows": int(confident.sum()),
        "confident_coverage": float(confident.mean()),
        "confident_accuracy": float((predicted[confident] == labels.to_numpy()[confident]).mean())
        if confident.any()
        else math.nan,
        "calibration_table": _calibration_table(labels, probabilities),
    }
    if labels.nunique() == 2:
        result["roc_auc"] = float(roc_auc_score(labels, probabilities))
    else:
        result["roc_auc"] = math.nan
    return result


def _partition(frame: pd.DataFrame, bounds: dict[str, str]) -> pd.DataFrame:
    start = pd.Timestamp(bounds["start"], tz="UTC")
    end = pd.Timestamp(bounds["end"], tz="UTC") + pd.Timedelta(days=1)
    times = pd.to_datetime(frame["open_time"], utc=True)
    return frame.loc[(times >= start) & (times < end)].reset_index(drop=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_experiment(
    *,
    data_root: Path = DATA_ROOT,
    metrics_path: Path = METRICS_PATH,
    spec_path: Path = SPEC_PATH,
    output_dir: Path = DATA_ROOT,
) -> dict[str, Any]:
    spec = load_spec(spec_path)
    bars, metrics = load_inputs(data_root, metrics_path)
    dataset = build_dataset(bars, metrics)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "panel.parquet"
    dataset.to_parquet(dataset_path, index=False)

    partitions = spec["partitions"]
    training = _partition(dataset, partitions["training"])
    calibration = _partition(dataset, partitions["calibration"])
    internal = _partition(dataset, partitions["internal_validation"])
    holdout = _partition(dataset, partitions["final_holdout"])
    if min(len(training), len(calibration), len(internal), len(holdout)) == 0:
        raise ValueError("one or more frozen partitions are empty")

    model_spec = spec["model"]
    model = CalibratedLogisticProbabilityModel(
        C=float(model_spec["C"]), random_state=int(model_spec["random_state"])
    ).fit(training, calibration)
    model_path = output_dir / "model.pkl"
    model_path.write_bytes(pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL))

    baseline_probability = float(training["label"].mean())
    prediction_frames = []
    split_reports: dict[str, Any] = {}
    for name, frame in (
        ("training_in_sample", training),
        ("calibration", calibration),
        ("internal_validation", internal),
        ("final_holdout", holdout),
    ):
        probabilities = model.predict_proba(frame)
        predictions = frame[["open_time", "label", "bar_return"]].copy()
        predictions["split"] = name
        predictions["p_up"] = probabilities
        predictions["model_direction"] = (probabilities >= 0.5).astype(int)
        prediction_frames.append(predictions)
        split_reports[name] = evaluate_predictions(
            frame, probabilities, baseline_probability=baseline_probability
        )

    predictions_path = output_dir / "predictions.parquet"
    pd.concat(prediction_frames, ignore_index=True).to_parquet(predictions_path, index=False)
    report = {
        "specification_id": spec["specification_id"],
        "specification_sha256": _sha256(spec_path),
        "source": spec["source"],
        "dataset": {
            "rows": int(len(dataset)),
            "first_open_time": pd.Timestamp(dataset["open_time"].min()).isoformat(),
            "last_open_time": pd.Timestamp(dataset["open_time"].max()).isoformat(),
            "actual_up_rate": float(dataset["label"].mean()),
            "panel_path": str(dataset_path),
        },
        "partitions": {
            name: {"rows": int(len(_partition(dataset, bounds))), "bounds": bounds}
            for name, bounds in partitions.items()
        },
        "baseline_training_up_rate": baseline_probability,
        "metrics": split_reports,
        "artifacts": {
            "panel": str(dataset_path),
            "predictions": str(predictions_path),
            "model": str(model_path),
        },
        "limitations": spec["interpretation"]["not_claimed"],
    }
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, allow_nan=True) + "\n")
    (output_dir / "report.md").write_text(format_report(report), encoding="utf-8")
    return report


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "# BTC 5m Probability Model — Binance Perpetual Proxy",
        "",
        "Research-only calibrated probability model. This is not a Polymarket execution result.",
        "",
        f"- Eligible rows: {report['dataset']['rows']}",
        f"- Data range: {report['dataset']['first_open_time']} to {report['dataset']['last_open_time']}",
        f"- Training up-rate baseline: {report['baseline_training_up_rate']:.6f}",
        "",
        "## Metrics",
        "",
        "| Split | Rows | Brier | Log loss | Direction accuracy | Confident coverage | Confident accuracy |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, values in report["metrics"].items():
        lines.append(
            f"| {name} | {values['rows']} | {values['brier_score']:.6f} | "
            f"{values['log_loss']:.6f} | {values['directional_accuracy_at_50pct']:.4f} | "
            f"{values['confident_coverage']:.4f} | {values['confident_accuracy']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The probability is useful only if calibration rows remain close to their realized YES/up frequency on unseen periods.",
            "No Polymarket quotes, order-book history, fees, or fills are included in this experiment.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_experiment()
    print(format_report(result))
