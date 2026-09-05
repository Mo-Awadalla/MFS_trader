"""Candidate C12: DispersionGated TSMOM (weekly ETF universe).

Hypothesis: the failure mode of the weekly 12-week TSMOM base is not signal
speed (C5 DMA falsified that); it is trading through high cross-sectional
dispersion regimes where asset-selection lag is worst. C12 keeps the base
signal untouched and gates exposure when smoothed weekly cross-sectional
dispersion exceeds a threshold estimated on the training window only.

Pre-declared variants (no parameter search):
  - C12_v1_hard_cash:    4-week smoothing, q=0.80, gate -> 100% cash proxy
  - C12_v2_soft_shrink:  4-week smoothing, q=0.80, gate -> 50% exposure
  - C12_v3_8w_hard_cash: 8-week smoothing, q=0.80, gate -> 100% cash proxy

Gate timing convention matches the base signal: each weekly label uses only
daily closes strictly before the label; execution is next session's open.
The threshold is frozen from the first ``threshold_train_weeks`` weekly
observations; the gate is inactive (pure baseline) inside that window so the
threshold is never applied to data that produced it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.candidate_metrics import (
    STRESS_WINDOWS,
    dsr_check,
    mc_check,
    standard_metrics,
    stress_window_report,
    wfa_check,
)
from research.etf_tsmom_pipeline import (
    INITIAL_CAPITAL,
    _allocated_costs,
    _trade_costs,
    etf_cost_config,
    load_etf_panel,
)
from strategies.etf_tsmom.signal import DEFAULT_UNIVERSE

RISK_ASSETS = ("SPY", "QQQ", "IWM", "IEF", "GLD", "DBC", "EFA", "EEM", "VNQ", "TLT")
CASH_PROXY = "SHY"
ARTIFACT_ROOT = Path("research/artifacts/c12")
GATE_ACTIONS = ("cash", "50_percent_exposure")


@dataclass(frozen=True)
class C12Params:
    variant_id: str
    rolling_dispersion_window_weeks: int
    threshold_quantile: float
    gate_action: str
    threshold_train_weeks: int = 52
    rebalance_freq: str = "W-FRI"
    momentum_lookback_days: int = 63  # existing 12-week TSMOM base signal
    realized_vol_days: int = 20
    max_weight: float = 0.50
    max_gross_exposure: float = 1.0
    cash_proxy: str = CASH_PROXY

    def __post_init__(self) -> None:
        if self.gate_action not in GATE_ACTIONS:
            raise ValueError(f"gate_action must be one of {GATE_ACTIONS}")


VARIANTS: dict[str, C12Params] = {
    "C12_v1_hard_cash": C12Params(
        variant_id="C12_v1_hard_cash",
        rolling_dispersion_window_weeks=4,
        threshold_quantile=0.80,
        gate_action="cash",
    ),
    "C12_v2_soft_shrink": C12Params(
        variant_id="C12_v2_soft_shrink",
        rolling_dispersion_window_weeks=4,
        threshold_quantile=0.80,
        gate_action="50_percent_exposure",
    ),
    "C12_v3_8w_hard_cash": C12Params(
        variant_id="C12_v3_8w_hard_cash",
        rolling_dispersion_window_weeks=8,
        threshold_quantile=0.80,
        gate_action="cash",
    ),
}


def weekly_dispersion(prices: pd.DataFrame, params: C12Params) -> pd.DataFrame:
    """Weekly cross-sectional dispersion diagnostics, no lookahead.

    Each weekly label's values use only daily closes strictly before the
    label, so the value at a rebalance date is known at decision time.
    """
    weekly_index = prices.resample(params.rebalance_freq).last().index
    signal_close = pd.DataFrame(np.nan, index=weekly_index, columns=prices.columns)
    for ts in weekly_index:
        loc = _last_daily_loc_before(prices.index, ts)
        if loc is not None:
            signal_close.loc[ts] = prices.iloc[loc]
    weekly_returns = signal_close.loc[:, list(RISK_ASSETS)].pct_change(fill_method=None)
    dispersion = weekly_returns.std(axis=1)
    smoothed = dispersion.rolling(params.rolling_dispersion_window_weeks).mean()
    return pd.DataFrame({"dispersion": dispersion, "smoothed_dispersion": smoothed})


def dispersion_threshold(smoothed: pd.Series, params: C12Params) -> tuple[float, pd.Timestamp]:
    """Frozen gate threshold from the training window only.

    Uses the first ``threshold_train_weeks`` weekly labels; values after the
    training window cannot influence the threshold.
    """
    train = smoothed.iloc[: params.threshold_train_weeks].dropna()
    if train.empty:
        return float("inf"), smoothed.index[min(params.threshold_train_weeks, len(smoothed)) - 1]
    train_end = smoothed.index[min(params.threshold_train_weeks, len(smoothed)) - 1]
    return float(train.quantile(params.threshold_quantile)), train_end


def c12_weekly_signal(
    prices: pd.DataFrame,
    params: C12Params,
    *,
    gate_enabled: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Weekly C12 target weights plus gate diagnostics.

    With ``gate_enabled=False`` this is exactly the ungated weekly 12-week
    TSMOM base (baseline behavior unchanged).
    """
    prices = prices.sort_index().astype(float)
    symbols = list(prices.columns)
    _validate_columns(symbols)
    weekly_index = prices.resample(params.rebalance_freq).last().index
    positions = pd.DataFrame(0.0, index=weekly_index, columns=symbols)
    momentum = (
        prices.loc[:, list(RISK_ASSETS)]
        .div(prices.loc[:, list(RISK_ASSETS)].shift(params.momentum_lookback_days))
        .sub(1.0)
    )
    realized_vol = prices.pct_change(fill_method=None).rolling(params.realized_vol_days).std() * np.sqrt(252)
    diagnostics = weekly_dispersion(prices, params)
    threshold, train_end = dispersion_threshold(diagnostics["smoothed_dispersion"], params)
    diagnostics["threshold"] = threshold
    diagnostics["in_train"] = diagnostics.index <= train_end
    diagnostics["gate_active"] = (
        gate_enabled
        & ~diagnostics["in_train"]
        & (diagnostics["smoothed_dispersion"] > threshold)
    ).fillna(False)

    min_history = max(params.momentum_lookback_days, params.realized_vol_days)
    for ts in weekly_index:
        signal_loc = _last_daily_loc_before(prices.index, ts)
        if signal_loc is None or signal_loc <= min_history:
            positions.loc[ts, params.cash_proxy] = 1.0
            continue
        signal_ts = prices.index[signal_loc]
        target = _base_target(momentum.loc[signal_ts], realized_vol.loc[signal_ts], symbols, params)
        if bool(diagnostics.loc[ts, "gate_active"]):
            target = _apply_gate(target, params)
        positions.loc[ts] = target
    return positions, diagnostics


def c12_daily_weights(
    prices: pd.DataFrame,
    params: C12Params,
    *,
    gate_enabled: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Daily weights (weekly targets held with next-session effect), trades, diagnostics."""
    weekly_positions, diagnostics = c12_weekly_signal(prices, params, gate_enabled=gate_enabled)
    weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    current = pd.Series(0.0, index=prices.columns)
    weekly_idx = 0
    for ts in prices.index:
        while (
            weekly_idx < len(weekly_positions.index)
            and weekly_positions.index[weekly_idx].normalize() < ts.normalize()
        ):
            current = weekly_positions.iloc[weekly_idx]
            weekly_idx += 1
        weights.loc[ts] = current
    trades = weights.diff().fillna(weights)
    return weights, trades, diagnostics


def backtest_c12(
    panel: pd.DataFrame,
    params: C12Params,
    *,
    gate_enabled: bool = True,
) -> dict[str, Any]:
    open_px = panel.xs("open", axis=1, level=1).astype(float)
    close = panel.xs("close", axis=1, level=1).astype(float)
    close = close.loc[:, list(RISK_ASSETS) + [CASH_PROXY]]
    open_px = open_px.loc[:, close.columns]
    weights, trades, diagnostics = c12_daily_weights(close, params, gate_enabled=gate_enabled)
    symbol_returns = open_px.shift(-1).div(open_px).sub(1.0).fillna(0.0)
    gross_returns = (weights * symbol_returns).sum(axis=1)
    costs = _trade_costs(trades, open_px, etf_cost_config())
    returns = gross_returns - costs
    symbol_pnl = (weights * symbol_returns).sub(_allocated_costs(costs, weights), axis=0).sum().sort_values()
    return {
        "weights": weights,
        "trades": trades,
        "returns": returns,
        "gross_returns": gross_returns,
        "diagnostics": diagnostics,
        "pnl_by_symbol": {str(index): float(value) for index, value in symbol_pnl.items()},
    }


def run_variant(variant_id: str, *, artifact_root: Path = ARTIFACT_ROOT) -> dict[str, Any]:
    """One-command evaluation of a pre-declared C12 variant."""
    params = VARIANTS[variant_id]
    panel = load_etf_panel()
    result = backtest_c12(panel, params)
    baseline = backtest_c12(panel, params, gate_enabled=False)
    returns = result["returns"]
    net_metrics = standard_metrics(
        returns,
        weights=result["weights"],
        trades=result["trades"],
        initial_capital=INITIAL_CAPITAL,
    )
    artifact: dict[str, Any] = {
        "candidate": variant_id,
        "family": "C12_DispersionGated_TSMOM",
        "status": "research_backtest_complete",
        "hypothesis": (
            "Avoiding trades during high cross-sectional dispersion regimes improves "
            "stability of the 12-week weekly TSMOM base without speeding up the signal."
        ),
        "data": {
            "source": "Massive adjusted daily flatfiles",
            "symbols": list(DEFAULT_UNIVERSE),
            "risk_assets": list(RISK_ASSETS),
            "rows": int(len(panel)),
            "start": str(panel.index.min()),
            "end": str(panel.index.max()),
            "limitation": "Massive flatfile access denied before 2021-06-30 under current credentials",
        },
        "params": asdict(params),
        "gross_metrics": standard_metrics(result["gross_returns"], initial_capital=INITIAL_CAPITAL),
        "net_metrics": net_metrics,
        "baseline_net_metrics": standard_metrics(
            baseline["returns"],
            weights=baseline["weights"],
            trades=baseline["trades"],
            initial_capital=INITIAL_CAPITAL,
        ),
        "pnl_by_symbol": result["pnl_by_symbol"],
        "stress_windows": _stress_report(result, baseline),
        "gate_diagnostics": gate_diagnostics(result, baseline),
    }
    artifact["wfa_primary"] = wfa_check(
        panel,
        lambda truncated: backtest_c12(truncated, params)["returns"],
        initial_capital=INITIAL_CAPITAL,
    )
    artifact["monte_carlo"] = mc_check(returns, initial_capital=INITIAL_CAPITAL)
    artifact["dsr"] = dsr_check(returns, net_metrics["sharpe"], candidate=variant_id)
    artifact["verdict"] = _verdict(artifact)
    artifact["promotion_status"] = (
        "validation_partial_pass" if artifact["verdict"].startswith("prioritize") else "validation_failed"
    )
    _write_outputs(artifact, result, artifact_root / variant_id)
    return artifact


def gate_diagnostics(result: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """C12-specific diagnostics: gate activity, split performance, drawdown overlap."""
    diagnostics = result["diagnostics"]
    returns = result["returns"]
    scored = diagnostics.loc[~diagnostics["in_train"]]
    gate_dates = list(scored.index[scored["gate_active"]])
    daily_gate = _daily_gate_state(diagnostics, returns.index)
    gate_on_returns = returns.loc[daily_gate]
    gate_off_returns = returns.loc[~daily_gate]
    baseline_equity = (1.0 + baseline["returns"]).cumprod()
    baseline_dd = baseline_equity / baseline_equity.cummax() - 1.0
    return {
        "threshold": float(scored["threshold"].iloc[0]) if not scored.empty else None,
        "train_end": str(diagnostics.index[diagnostics["in_train"]].max()),
        "scored_weeks": int(len(scored)),
        "gate_on_weeks": int(scored["gate_active"].sum()),
        "gate_on_percentage": float(scored["gate_active"].mean()) if not scored.empty else 0.0,
        "average_exposure": float(result["weights"].abs().sum(axis=1).mean()),
        "average_risk_exposure": float(
            result["weights"].drop(columns=[CASH_PROXY]).abs().sum(axis=1).mean()
        ),
        "gate_active_dates": [str(ts.date()) for ts in gate_dates],
        "performance_gate_on": standard_metrics(gate_on_returns, initial_capital=INITIAL_CAPITAL),
        "performance_gate_off": standard_metrics(gate_off_returns, initial_capital=INITIAL_CAPITAL),
        "baseline_performance_during_gate_on": standard_metrics(
            baseline["returns"].loc[daily_gate], initial_capital=INITIAL_CAPITAL
        ),
        "baseline_drawdown_overlap": {
            "mean_baseline_drawdown_gate_on": float(baseline_dd.loc[daily_gate].mean())
            if daily_gate.any()
            else 0.0,
            "mean_baseline_drawdown_gate_off": float(baseline_dd.loc[~daily_gate].mean()),
            "gate_on_days_in_baseline_drawdown_5pct": float((baseline_dd.loc[daily_gate] < -0.05).mean())
            if daily_gate.any()
            else 0.0,
            "gate_off_days_in_baseline_drawdown_5pct": float((baseline_dd.loc[~daily_gate] < -0.05).mean()),
        },
    }


def _stress_report(result: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    gated = stress_window_report(result["returns"], initial_capital=INITIAL_CAPITAL)
    ungated = stress_window_report(baseline["returns"], initial_capital=INITIAL_CAPITAL)
    diagnostics = result["diagnostics"]
    report: dict[str, Any] = {}
    for name, (start, end) in STRESS_WINDOWS.items():
        window = diagnostics.loc[start:end]
        report[name] = {
            "candidate": gated[name],
            "baseline": ungated[name],
            "gate_on_fraction": float(window["gate_active"].mean()) if not window.empty else 0.0,
        }
    return report


def _daily_gate_state(diagnostics: pd.DataFrame, daily_index: pd.DatetimeIndex) -> pd.Series:
    """Map weekly gate state to daily bars with the same next-session lag as weights."""
    state = pd.Series(False, index=daily_index)
    current = False
    weekly_idx = 0
    weekly_index = diagnostics.index
    for ts in daily_index:
        while weekly_idx < len(weekly_index) and weekly_index[weekly_idx].normalize() < ts.normalize():
            current = bool(diagnostics["gate_active"].iloc[weekly_idx])
            weekly_idx += 1
        state.loc[ts] = current
    return state


def _base_target(
    momentum: pd.Series,
    vol: pd.Series,
    symbols: list[str],
    params: C12Params,
) -> pd.Series:
    signal = momentum.replace([np.inf, -np.inf], np.nan).dropna()
    selected = list(signal[signal > 0.0].index)
    target = pd.Series(0.0, index=symbols)
    if not selected:
        target.loc[params.cash_proxy] = 1.0
        return target
    target = _inverse_vol_weights(vol.reindex(selected), symbols, params.cash_proxy)
    target = _cap_and_redistribute(target, params.max_weight)
    gross = float(target.abs().sum())
    if gross > params.max_gross_exposure:
        target = target * params.max_gross_exposure / gross
    return target


def _apply_gate(target: pd.Series, params: C12Params) -> pd.Series:
    gated = pd.Series(0.0, index=target.index)
    if params.gate_action == "cash":
        gated.loc[params.cash_proxy] = 1.0
        return gated
    risk = target.drop(params.cash_proxy) * 0.5
    gated.loc[risk.index] = risk
    gated.loc[params.cash_proxy] = 1.0 - float(risk.sum())
    return gated


def _verdict(artifact: dict[str, Any]) -> str:
    candidate = artifact["net_metrics"]
    baseline = artifact["baseline_net_metrics"]
    improves_stability = (
        candidate["rolling_12wk_negative_fraction"] < baseline["rolling_12wk_negative_fraction"]
    )
    improves_drawdown = candidate["max_drawdown"] > baseline["max_drawdown"]
    holds_sharpe = candidate["sharpe"] >= baseline["sharpe"] - 0.10
    if improves_stability and improves_drawdown and holds_sharpe:
        return "prioritize_c12_gate_for_review"
    if improves_stability or improves_drawdown:
        return "partial_improvement_not_priority"
    return "reject_c12_variant"


def _write_outputs(artifact: dict[str, Any], result: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(_json_safe(artifact), indent=2, allow_nan=False))
    result["returns"].to_frame("returns").to_parquet(out_dir / "returns.parquet")
    result["gross_returns"].to_frame("gross_returns").to_parquet(out_dir / "gross_returns.parquet")
    result["weights"].to_parquet(out_dir / "weights.parquet")
    result["diagnostics"].to_parquet(out_dir / "gate_diagnostics.parquet")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.floating, float)):
        v = float(value)
        return v if np.isfinite(v) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def _validate_columns(symbols: list[str]) -> None:
    missing = [symbol for symbol in (*RISK_ASSETS, CASH_PROXY) if symbol not in symbols]
    if missing:
        raise ValueError(f"missing required C12 symbols: {missing}")


def _last_daily_loc_before(index: pd.DatetimeIndex, signal_ts: pd.Timestamp) -> int | None:
    eligible = np.flatnonzero(index.normalize() < signal_ts.normalize())
    if len(eligible) == 0:
        return None
    return int(eligible[-1])


def _inverse_vol_weights(vol: pd.Series, symbols: list[str], cash_proxy: str) -> pd.Series:
    weights = pd.Series(0.0, index=symbols)
    inv = 1.0 / vol.replace(0.0, np.nan).dropna()
    if inv.empty:
        weights.loc[cash_proxy] = 1.0
        return weights
    weights.loc[list(inv.index)] = inv / inv.sum()
    return weights


def _cap_and_redistribute(weights: pd.Series, cap: float) -> pd.Series:
    capped = weights.copy()
    for _ in range(len(capped)):
        over = capped > cap
        if not bool(over.any()):
            break
        excess = float((capped[over] - cap).sum())
        capped[over] = cap
        under = (capped > 0.0) & (capped < cap)
        if not bool(under.any()) or excess <= 0.0:
            break
        capped.loc[under] += excess * capped.loc[under] / capped.loc[under].sum()
    gross = float(capped.sum())
    if 0.0 < gross < 1.0 and bool((capped > 0.0).any()):
        capped.loc[capped > 0.0] /= gross
    return capped
