"""Reproducible MA operational shakedown.

This module uses synthetic data so a developer can prove the local system path
works without broker credentials or downloaded market data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config.schema import (
    AssetClass,
    BrokerConfig,
    Config,
    CostModelConfig,
    DataConfig,
    EngineConfig,
    LiveDeploymentConfig,
    Mode,
    MonitoringConfig,
    PortfolioConfig,
    RiskLimits,
)
from data.validate import validate_ohlcv
from engine.replay import ReplayResult, run_replay
from execution.sim_broker.broker import SimBrokerConfig
from monitoring.reports import (
    OperationalReport,
    build_operational_report,
    format_operational_report,
)
from research.runner import BacktestResult, run_single_asset_backtest
from strategies.ma.signal import MAParams, generate_signals


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    replay: ReplayResult
    report: OperationalReport
    db_path: str
    expected_event: str | None = None
    passed: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "db_path": self.db_path,
            "expected_event": self.expected_event,
            "passed": self.passed,
            "notes": self.notes,
            "replay": {
                "bar_count": self.replay.bar_count,
                "cycle_count": self.replay.cycle_count,
                "orders_submitted": self.replay.orders_submitted,
                "orders_filled": self.replay.orders_filled,
                "orders_rejected": self.replay.orders_rejected,
                "orders_timed_out": self.replay.orders_timed_out,
                "final_positions": self.replay.final_positions,
                "error": self.replay.error,
            },
            "operational_report": self.report.to_dict(),
        }


@dataclass(frozen=True)
class MAShakedownResult:
    output_dir: str
    bars: int
    seed: int
    data_quality: dict[str, Any]
    research_metrics: dict[str, float]
    research_trade_count: int
    scenarios: list[ScenarioResult]
    report_path: str
    json_path: str
    passed: bool
    blockers: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "bars": self.bars,
            "seed": self.seed,
            "data_quality": self.data_quality,
            "research_metrics": self.research_metrics,
            "research_trade_count": self.research_trade_count,
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
            "report_path": self.report_path,
            "json_path": self.json_path,
            "passed": self.passed,
            "blockers": self.blockers,
        }


def run_ma_shakedown(
    *,
    out_dir: str | Path,
    bars: int = 300,
    seed: int = 42,
    fast_window: int = 20,
    slow_window: int = 100,
    trend_filter_active: bool = True,
    initial_capital: float = 10000.0,
) -> MAShakedownResult:
    """Run local MA research + replay + failure-mode shakedown and write reports."""

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)

    params = MAParams(
        fast_ma_window=fast_window,
        slow_ma_window=slow_window,
        trend_filter_active=trend_filter_active,
        long_only=True,
    )
    strategy_params = {
        "fast_ma_window": fast_window,
        "slow_ma_window": slow_window,
        "trend_filter_active": trend_filter_active,
        "long_only": True,
    }

    bars_df = make_synthetic_bars(n=bars, seed=seed)
    validation = validate_ohlcv(
        bars_df,
        "AAPL",
        "synthetic",
        frequency="1d",
        expected_interval_seconds=86400,
        now_ts=bars_df.index[-1] + pd.Timedelta(days=1),
    )
    signals = generate_signals(bars_df, params)
    research = run_single_asset_backtest(
        bars_df,
        signals,
        strategy_name="dual_ma_crossover",
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        cost_config=CostModelConfig(slippage_fixed_pct=0.0005),
        initial_capital=initial_capital,
        params=strategy_params,
    )

    config = make_replay_config(strategy_version="0.1.0")
    scenario_specs = [
        ("baseline", SimBrokerConfig(seed=seed), None),
        ("rejection", SimBrokerConfig(reject_probability=1.0, seed=seed), "BROKER_REJECT"),
        ("timeout", SimBrokerConfig(timeout_probability=1.0, seed=seed), "BROKER_TIMEOUT"),
        (
            "partial_fill",
            SimBrokerConfig(partial_fill_probability=1.0, seed=seed),
            "PARTIALLY_FILLED",
        ),
    ]
    scenarios: list[ScenarioResult] = []
    for name, broker_config, expected_event in scenario_specs:
        db_path = output / f"{name}.sqlite"
        replay = run_replay(
            bars=bars_df,
            config=config,
            strategy_fn=ma_strategy_fn,
            strategy_name="dual_ma_crossover",
            strategy_params=strategy_params,
            broker_config=broker_config,
            db_path=db_path,
            initial_capital=initial_capital,
            bar_frequency="1D",
        )
        report = build_operational_report(db_path)
        passed, notes = _scenario_passed(name, replay, report, expected_event)
        scenarios.append(
            ScenarioResult(
                name=name,
                replay=replay,
                report=report,
                db_path=str(db_path),
                expected_event=expected_event,
                passed=passed,
                notes=notes,
            )
        )

    blockers = _build_shakedown_blockers(validation.result.value, research, scenarios)
    passed = not blockers

    result_stub = MAShakedownResult(
        output_dir=str(output),
        bars=bars,
        seed=seed,
        data_quality={
            "result": validation.result.value,
            "bars_checked": validation.bars_checked,
            "bars_failed": validation.bars_failed,
            "latest_bar_timestamp": validation.latest_bar_timestamp,
            "issues": validation.issues_json,
        },
        research_metrics=research.metrics,
        research_trade_count=research.trade_count,
        scenarios=scenarios,
        report_path=str(output / "ma_shakedown_report.md"),
        json_path=str(output / "ma_shakedown_report.json"),
        passed=passed,
        blockers=blockers,
    )
    _write_shakedown_reports(result_stub)
    return result_stub


def make_synthetic_bars(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Generate deterministic daily OHLCV data that normally produces MA trades."""

    if n < 60:
        raise ValueError("MA shakedown needs at least 60 bars")
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")

    # Piecewise trend profile: up, down, up. This reliably exercises MA entries/exits.
    segments = np.array_split(np.arange(n), 3)
    drift = np.zeros(n)
    drift[segments[0]] = 0.0018
    drift[segments[1]] = -0.0020
    drift[segments[2]] = 0.0015
    returns = drift + rng.normal(0.0, 0.006, n)
    close = 150.0 * np.cumprod(1 + returns)

    df = pd.DataFrame(
        {
            "symbol": "AAPL",
            "open": close * (1 + rng.normal(0, 0.0005, n)),
            "high": close * (1 + np.abs(rng.normal(0, 0.001, n))),
            "low": close * (1 - np.abs(rng.normal(0, 0.001, n))),
            "close": close,
            "volume": rng.integers(500000, 5000000, n).astype(float),
        },
        index=idx,
    )
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    return df


def ma_strategy_fn(bars: pd.DataFrame, params: dict[str, Any]) -> dict[str, float]:
    """Engine strategy wrapper for the MA baseline."""

    ma_params = MAParams(
        fast_ma_window=int(params.get("fast_ma_window", 20)),
        slow_ma_window=int(params.get("slow_ma_window", 100)),
        trend_filter_active=bool(params.get("trend_filter_active", True)),
        long_only=bool(params.get("long_only", True)),
    )
    signals = generate_signals(bars, ma_params)
    if signals.empty or "position" not in signals:
        return {}
    latest_position = signals["position"].iloc[-1]
    return {"AAPL": float(latest_position)}


def make_replay_config(*, strategy_version: str = "0.1.0") -> Config:
    """Build a local sim-broker config for MA replay/shakedown."""

    return Config(
        mode=Mode.RESEARCH,
        brokers=[
            BrokerConfig(
                name="sim_broker",
                asset_class=AssetClass.EQUITY,
                api_key_env="SIM_API_KEY",
                api_secret_env="SIM_API_SECRET",
                base_url="sim",
            )
        ],
        data=[DataConfig(symbols=["AAPL"], asset_class=AssetClass.EQUITY)],
        risk_limits=RiskLimits(
            per_position_pct=0.05,
            max_daily_loss_pct=0.99,
            max_monthly_loss_pct=0.99,
            max_open_positions=10,
        ),
        portfolio=PortfolioConfig(per_position_risk_pct=0.05),
        cost_model=CostModelConfig(slippage_fixed_pct=0.0005),
        monitoring=MonitoringConfig(),
        engine=EngineConfig(startup_reconciliation_required=False),
        live_deployment=LiveDeploymentConfig(),
        strategy_name="dual_ma_crossover",
        strategy_version=strategy_version,
        strategies_enabled=["ma"],
    )


def _scenario_passed(
    name: str,
    replay: ReplayResult,
    report: OperationalReport,
    expected_event: str | None,
) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if replay.error:
        notes.append(f"Replay returned error: {replay.error}")
    if replay.orders_submitted == 0 and name != "baseline":
        notes.append("Scenario did not submit any orders.")

    if name == "baseline":
        if replay.orders_filled <= 0:
            notes.append("Baseline did not produce any fills.")
        if report.broker_timeouts or report.broker_rejections or report.reconciliation_mismatches:
            notes.append("Baseline recorded broker failures or reconciliation mismatches.")
        return not notes, notes

    if expected_event == "BROKER_REJECT" and replay.orders_rejected <= 0:
        notes.append("Rejection scenario did not record rejected orders.")
    elif expected_event == "BROKER_TIMEOUT" and replay.orders_timed_out <= 0:
        notes.append("Timeout scenario did not record timed-out orders.")
    elif expected_event == "PARTIALLY_FILLED" and not report.order_state_counts.get("PARTIALLY_FILLED", 0):
        notes.append("Partial-fill scenario did not leave/record partially filled orders.")

    return not notes, notes


def _build_shakedown_blockers(
    data_quality: str,
    research: BacktestResult,
    scenarios: list[ScenarioResult],
) -> list[str]:
    blockers: list[str] = []
    if data_quality == "FAIL":
        blockers.append("Synthetic data validation failed.")
    if research.bar_count <= 0:
        blockers.append("Research backtest did not process bars.")
    if "final_equity" not in research.metrics or research.metrics["final_equity"] <= 0:
        blockers.append("Research backtest final equity is invalid.")
    for scenario in scenarios:
        if not scenario.passed:
            blockers.append(f"Scenario {scenario.name} failed: {'; '.join(scenario.notes)}")
    return blockers


def _write_shakedown_reports(result: MAShakedownResult) -> None:
    json_path = Path(result.json_path)
    report_path = Path(result.report_path)
    json_path.write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")
    report_path.write_text(format_ma_shakedown_report(result), encoding="utf-8")


def format_ma_shakedown_report(result: MAShakedownResult) -> str:
    """Render the MA shakedown result as Markdown."""

    status = "PASS" if result.passed else "BLOCKED"
    lines = [
        "# MA Operational Shakedown Report",
        "",
        f"Status: {status}",
        f"Output directory: `{result.output_dir}`",
        f"Synthetic bars: {result.bars}",
        f"Seed: {result.seed}",
        "",
        "## Data Quality",
        "",
        f"- Result: {result.data_quality['result']}",
        f"- Bars checked: {result.data_quality['bars_checked']}",
        f"- Bars failed: {result.data_quality['bars_failed']}",
        "",
        "## Research Backtest",
        "",
        f"- Trades: {result.research_trade_count}",
    ]
    for key in ("total_return", "cagr", "sharpe", "sortino", "max_drawdown", "final_equity"):
        if key in result.research_metrics:
            lines.append(f"- {key}: {result.research_metrics[key]:.6f}")

    lines.extend(["", "## Scenario Results", ""])
    for scenario in result.scenarios:
        lines.extend(
            [
                f"### {scenario.name}",
                "",
                f"- Passed: {scenario.passed}",
                f"- DB: `{scenario.db_path}`",
                f"- Bars: {scenario.replay.bar_count}",
                f"- Orders submitted: {scenario.replay.orders_submitted}",
                f"- Orders filled: {scenario.replay.orders_filled}",
                f"- Orders rejected: {scenario.replay.orders_rejected}",
                f"- Orders timed out: {scenario.replay.orders_timed_out}",
                f"- Final positions: {scenario.replay.final_positions}",
            ]
        )
        if scenario.notes:
            lines.extend(f"- Note: {note}" for note in scenario.notes)
        lines.extend(["", format_operational_report(scenario.report), ""])

    lines.extend(["", "## Promotion Blockers", ""])
    if result.blockers:
        lines.extend(f"- {blocker}" for blocker in result.blockers)
    else:
        lines.append("- None for the local synthetic shakedown. This is not live/paper approval.")
    lines.append("")
    return "\n".join(lines)
