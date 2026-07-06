"""ETF time-series momentum engine replay.

This is a panel-aware operational replay for the validation-passed ETF TSM
candidate. It is not another vectorized research backtest: precomputed frozen
ETF target weights are fed through the runtime TradingEngine, portfolio sizing,
risk checks, OMS, SQLite state, and simulated broker fills.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pandas as pd

from config.schema import Config
from engine.replay import ReplayResult
from engine.runtime import TradingEngine
from execution.sim_broker.broker import SimBroker, SimBrokerConfig
from monitoring.reports import OperationalReport, build_operational_report, write_operational_report
from portfolio.sizing import PortfolioState
from research.etf_time_series_momentum_experiment import STRATEGY_NAME
from research.etf_time_series_momentum_pipeline import backtest_etf_time_series_momentum
from research.universes.etf_tactical_v1 import all_symbols
from risk.engine import DrawdownState
from storage.parquet_io import read_bars
from storage.repository import get_positions
from storage.schema import init_db
from strategies.etf_time_series_momentum.signal import (
    ETFTimeSeriesMomentumParams,
    default_params,
    generate_signals,
    params_to_dict,
)
from strategies.registry import strategy_template_version

DEFAULT_CACHE_DIR = Path("data/parquet/equity/yahoo_chart")
DEFAULT_REPORT_STEM = "etf_tsm_engine_replay"


@dataclass
class ETFEngineReplayComparison:
    """Research-vs-runtime replay summary for ETF TSM."""

    symbols: tuple[str, ...]
    bars_loaded: int
    bars_start: str | None
    bars_end: str | None
    params: dict[str, Any]
    db_path: str
    report_path: str
    json_path: str
    operational_report_path: str
    operational_json_path: str
    research_metrics: dict[str, float]
    research_rebalances: int
    research_trade_rows: int
    replay: ReplayResult
    replay_final_equity: float
    final_target_weights: dict[str, float]
    final_replay_weights: dict[str, float]
    operational_report: OperationalReport
    differences: list[str] = field(default_factory=list)
    assumption_gaps: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.differences and self.operational_report.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "symbols": list(self.symbols),
            "bars_loaded": self.bars_loaded,
            "bars_start": self.bars_start,
            "bars_end": self.bars_end,
            "params": self.params,
            "db_path": self.db_path,
            "report_path": self.report_path,
            "json_path": self.json_path,
            "operational_report_path": self.operational_report_path,
            "operational_json_path": self.operational_json_path,
            "research": {
                "metrics": self.research_metrics,
                "rebalances": self.research_rebalances,
                "trade_rows": self.research_trade_rows,
            },
            "replay": {
                "bar_count": self.replay.bar_count,
                "cycle_count": self.replay.cycle_count,
                "orders_submitted": self.replay.orders_submitted,
                "orders_filled": self.replay.orders_filled,
                "orders_rejected": self.replay.orders_rejected,
                "orders_timed_out": self.replay.orders_timed_out,
                "final_positions": self.replay.final_positions,
                "final_equity": self.replay_final_equity,
                "error": self.replay.error,
            },
            "final_target_weights": self.final_target_weights,
            "final_replay_weights": self.final_replay_weights,
            "operational_report": self.operational_report.to_dict(),
            "differences": self.differences,
            "assumption_gaps": self.assumption_gaps,
        }


def run_etf_tsm_engine_replay(
    *,
    config: Config,
    out_dir: str | Path = "runs/etf_tsm_engine_replay",
    panel: pd.DataFrame | None = None,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    symbols: tuple[str, ...] | None = None,
    params: ETFTimeSeriesMomentumParams | None = None,
    initial_capital: float = 10_000.0,
    max_bars: int | None = None,
) -> ETFEngineReplayComparison:
    """Replay ETF TSM target weights through the runtime engine and sim broker."""

    symbols = symbols or all_symbols()
    params = params or default_params()
    panel = panel.copy() if panel is not None else load_cached_yahoo_panel(cache_dir, symbols=symbols)
    panel = panel.sort_index()
    if max_bars is not None:
        panel = panel.tail(max_bars)
    if panel.empty:
        raise ValueError("ETF TSM replay panel is empty")

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / f"{DEFAULT_REPORT_STEM}.sqlite"
    report_path = output / f"{DEFAULT_REPORT_STEM}.md"
    json_path = output / f"{DEFAULT_REPORT_STEM}.json"
    operational_report_path = output / f"{DEFAULT_REPORT_STEM}_operational.md"
    operational_json_path = output / f"{DEFAULT_REPORT_STEM}_operational.json"
    if db_path.exists():
        db_path.unlink()

    replay_config = _runtime_replay_config(config, params=params)
    research = backtest_etf_time_series_momentum(
        panel,
        params,
        cost_config=replay_config.cost_model,
        initial_capital=initial_capital,
    )
    raw_signals = generate_signals(panel, params)
    target_weights = raw_signals.xs("weight", axis=1, level="field").astype(float)
    held_weights = target_weights.shift(1).fillna(0.0)

    conn = init_db(db_path)
    broker = SimBroker(
        SimBrokerConfig(
            seed=42,
            starting_cash=initial_capital,
            commission_pct=replay_config.cost_model.commission_pct,
            slippage_pct=replay_config.cost_model.slippage_fixed_pct,
        )
    )
    broker.connect()
    engine = TradingEngine(
        config=replay_config,
        conn=conn,
        broker=broker,
        strategy_fn=_make_target_weight_strategy_fn(held_weights, symbols),
        strategy_name=STRATEGY_NAME,
        strategy_params={"params": params_to_dict(params), "weight_source": "precomputed_frozen_targets"},
    )
    replay = ReplayResult()

    if not engine.startup():
        replay.error = f"engine_startup_failed: {engine.state.halt_reason or 'unknown'}"
    else:
        close = panel.xs("close", axis=1, level="field").astype(float)
        for i, ts in enumerate(panel.index):
            prices = {
                str(symbol): float(price)
                for symbol, price in close.loc[ts].dropna().items()
                if float(price) > 0
            }
            for symbol, price in prices.items():
                broker.set_price(symbol, price)
            engine.process_bar(
                bars=panel.iloc[: i + 1],
                prices=prices,
                bar_timestamp=str(ts),
                portfolio_state=PortfolioState(
                    cash=initial_capital,
                    equity=initial_capital,
                    high_water_mark=initial_capital,
                ),
                drawdown=DrawdownState(
                    high_water_mark=initial_capital,
                    current_equity=initial_capital,
                ),
            )
            replay.bar_count += 1
            replay.cycle_count = engine.state.cycle_count
            if engine.state.halted:
                replay.error = f"engine_halted: {engine.state.halt_reason}"
                break

    positions = get_positions(conn, strategy=STRATEGY_NAME)
    replay.final_positions = {str(p["symbol"]): float(p["quantity"]) for p in positions}
    replay.orders_submitted = _scalar(conn, "SELECT COUNT(*) FROM events WHERE event_type = 'ORDER_INTENT'")
    replay.orders_filled = _scalar(conn, "SELECT COUNT(*) FROM events WHERE event_type = 'ORDER_FILLED'")
    replay.orders_rejected = _scalar(conn, "SELECT COUNT(*) FROM events WHERE event_type = 'BROKER_REJECT'")
    replay.orders_timed_out = _scalar(conn, "SELECT COUNT(*) FROM events WHERE event_type = 'BROKER_TIMEOUT'")
    replay.events = _events(conn)
    engine.shutdown()
    conn.close()

    final_prices = {str(symbol): float(price) for symbol, price in close.iloc[-1].dropna().items()}
    replay_final_equity = compute_replay_equity(
        db_path,
        initial_capital=initial_capital,
        final_prices=final_prices,
    )
    final_target_weights = {
        str(symbol): float(weight)
        for symbol, weight in held_weights.iloc[-1].reindex(symbols).fillna(0.0).items()
    }
    final_replay_weights = _position_weights(
        replay.final_positions,
        final_prices=final_prices,
        initial_capital=initial_capital,
    )
    operational_report = build_operational_report(db_path)
    write_operational_report(operational_report, operational_report_path, fmt="markdown")
    write_operational_report(operational_report, operational_json_path, fmt="json")

    comparison = ETFEngineReplayComparison(
        symbols=symbols,
        bars_loaded=len(panel),
        bars_start=str(panel.index[0]) if len(panel) else None,
        bars_end=str(panel.index[-1]) if len(panel) else None,
        params={
            **params_to_dict(params),
            "strategy_template_version": strategy_template_version(STRATEGY_NAME),
            "runtime_config_overrides": _runtime_override_summary(params),
        },
        db_path=str(db_path),
        report_path=str(report_path),
        json_path=str(json_path),
        operational_report_path=str(operational_report_path),
        operational_json_path=str(operational_json_path),
        research_metrics=research.metrics,
        research_rebalances=research.rebalance_count,
        research_trade_rows=research.trade_count,
        replay=replay,
        replay_final_equity=replay_final_equity,
        final_target_weights=final_target_weights,
        final_replay_weights=final_replay_weights,
        operational_report=operational_report,
        differences=_build_differences(replay, operational_report),
        assumption_gaps=_assumption_gaps(),
    )
    write_etf_tsm_replay_reports(comparison)
    return comparison


def load_cached_yahoo_panel(
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    *,
    symbols: tuple[str, ...] | None = None,
    frequency: str = "1d",
) -> pd.DataFrame:
    """Load cached Yahoo ETF bars into a (symbol, field) panel."""

    cache = Path(cache_dir)
    symbols = symbols or all_symbols()
    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        path = cache / f"{symbol}_{frequency}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"missing cached Yahoo bars for {symbol}: {path}")
        df = read_bars(path)[["open", "high", "low", "close", "volume"]].copy()
        df.columns = pd.MultiIndex.from_product([[symbol], df.columns], names=["symbol", "field"])
        frames.append(df)
    panel = pd.concat(frames, axis=1, sort=True).sort_index()
    return panel.loc[~panel.index.duplicated(keep="last")]


def compute_replay_equity(
    db_path: str | Path,
    *,
    initial_capital: float,
    final_prices: dict[str, float],
) -> float:
    """Compute mark-to-market replay equity from filled runtime orders."""

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT symbol, side, filled_qty, avg_fill_price
           FROM orders_live
           WHERE order_state = 'FILLED' AND filled_qty > 0
           ORDER BY created_at, client_order_id"""
    ).fetchall()
    conn.close()

    cash = initial_capital
    positions: dict[str, float] = {}
    for row in rows:
        symbol = str(row["symbol"])
        qty = float(row["filled_qty"])
        price = float(row["avg_fill_price"])
        if row["side"] == "buy":
            cash -= qty * price
            positions[symbol] = positions.get(symbol, 0.0) + qty
        else:
            cash += qty * price
            positions[symbol] = positions.get(symbol, 0.0) - qty

    equity = cash
    for symbol, qty in positions.items():
        equity += qty * final_prices.get(symbol, 0.0)
    return float(equity)


def write_etf_tsm_replay_reports(comparison: ETFEngineReplayComparison) -> None:
    Path(comparison.json_path).write_text(
        json.dumps(comparison.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    Path(comparison.report_path).write_text(format_etf_tsm_replay_report(comparison), encoding="utf-8")


def format_etf_tsm_replay_report(comparison: ETFEngineReplayComparison) -> str:
    status = "PASS" if comparison.passed else "BLOCKED"
    lines = [
        "# ETF TSM Engine Replay",
        "",
        f"Status: {status}",
        f"Symbols: `{', '.join(comparison.symbols)}`",
        f"Bars: {comparison.bars_loaded} ({comparison.bars_start} to {comparison.bars_end})",
        f"Replay DB: `{comparison.db_path}`",
        f"Operational report: `{comparison.operational_report_path}`",
        "",
        "## What this proves",
        "",
        "This replay feeds the validation-passed ETF TSM target weights through the runtime engine, portfolio sizing, risk engine, OMS, SQLite state, and simulated broker fills. It is operational evidence, not a new validation pass and not live-trading approval.",
        "",
        "## Research vs Runtime",
        "",
        f"- Research final equity: {comparison.research_metrics.get('final_equity', 0.0):.6f}",
        f"- Research Sharpe: {comparison.research_metrics.get('sharpe', 0.0):.6f}",
        f"- Research max drawdown: {comparison.research_metrics.get('max_drawdown', 0.0):.6f}",
        f"- Research rebalances/trade rows: {comparison.research_rebalances}/{comparison.research_trade_rows}",
        f"- Replay bars/cycles: {comparison.replay.bar_count}/{comparison.replay.cycle_count}",
        f"- Replay orders submitted/filled/rejected/timed out: {comparison.replay.orders_submitted}/{comparison.replay.orders_filled}/{comparison.replay.orders_rejected}/{comparison.replay.orders_timed_out}",
        f"- Replay mark-to-market equity: {comparison.replay_final_equity:.6f}",
        f"- Replay final positions: {comparison.replay.final_positions}",
        "",
        "## Final target vs replay weights",
        "",
        "| Symbol | Target weight | Replay weight |",
        "| --- | ---: | ---: |",
    ]
    for symbol in comparison.symbols:
        target = comparison.final_target_weights.get(symbol, 0.0)
        replay = comparison.final_replay_weights.get(symbol, 0.0)
        lines.append(f"| {symbol} | {target:.6f} | {replay:.6f} |")

    lines.extend(["", "## Runtime config overrides", ""])
    overrides = comparison.params.get("runtime_config_overrides", {})
    lines.extend(f"- {key}: {value}" for key, value in overrides.items())

    lines.extend(["", "## Differences / blockers", ""])
    if comparison.differences:
        lines.extend(f"- {difference}" for difference in comparison.differences)
    elif comparison.operational_report.blockers:
        lines.extend(f"- {blocker}" for blocker in comparison.operational_report.blockers)
    else:
        lines.append("- None on structural runtime replay checks.")

    lines.extend(["", "## Assumption gaps", ""])
    lines.extend(f"- {gap}" for gap in comparison.assumption_gaps)
    lines.append("")
    return "\n".join(lines)


def _runtime_replay_config(config: Config, *, params: ETFTimeSeriesMomentumParams) -> Config:
    return replace(
        config,
        strategy_name=STRATEGY_NAME,
        strategy_version=strategy_template_version(STRATEGY_NAME),
        strategies_enabled=[STRATEGY_NAME],
        portfolio=replace(
            config.portfolio,
            execution_mode="continuous_rebalance",
            per_position_risk_pct=0.05,
            dollar_neutral=False,
            equal_weight=False,
            rebalance_frequency="monthly",
            min_notional_delta=25.0,
            min_qty_delta=1e-9,
            min_pct_position_delta=0.05,
        ),
        risk_limits=replace(
            config.risk_limits,
            per_position_pct=0.05,
            max_gross_exposure_pct=params.max_gross,
            max_net_exposure_pct=params.max_gross,
            max_open_positions=max(config.risk_limits.max_open_positions, params.top_n + 1),
        ),
        engine=replace(config.engine, startup_reconciliation_required=False),
    )


def _runtime_override_summary(params: ETFTimeSeriesMomentumParams) -> dict[str, Any]:
    return {
        "portfolio.execution_mode": "continuous_rebalance",
        "portfolio.per_position_risk_pct": 0.05,
        "risk_limits.per_position_pct": 0.05,
        "risk_limits.max_gross_exposure_pct": params.max_gross,
        "risk_limits.max_net_exposure_pct": params.max_gross,
        "engine.startup_reconciliation_required": False,
        "portfolio.min_notional_delta": 25.0,
        "portfolio.min_pct_position_delta": 0.05,
        "target_weight_timing": "weights shifted one bar to match vectorized research execution",
    }


def _make_target_weight_strategy_fn(held_weights: pd.DataFrame, symbols: tuple[str, ...]):
    def strategy_fn(bars: pd.DataFrame, _params: dict[str, Any]) -> dict[str, float]:
        if bars.empty:
            return {}
        ts = bars.index[-1]
        if ts not in held_weights.index:
            eligible = held_weights.index[held_weights.index <= ts]
            if len(eligible) == 0:
                return dict.fromkeys(symbols, 0.0)
            ts = eligible[-1]
        row = held_weights.loc[ts].reindex(symbols).fillna(0.0)
        return {str(symbol): float(row.loc[symbol]) for symbol in symbols}

    return strategy_fn


def _build_differences(replay: ReplayResult, operational_report: OperationalReport) -> list[str]:
    differences: list[str] = []
    if replay.error:
        differences.append(f"Replay error: {replay.error}")
    if replay.bar_count != replay.cycle_count:
        differences.append(f"Replay cycle mismatch: bars={replay.bar_count}, cycles={replay.cycle_count}")
    if replay.orders_submitted <= 0:
        differences.append("Replay submitted no orders; target weights did not exercise the OMS path.")
    if replay.orders_filled <= 0:
        differences.append("Replay filled no orders; simulated broker path was not exercised.")
    if replay.orders_rejected:
        differences.append(f"Replay had rejected orders: {replay.orders_rejected}")
    if replay.orders_timed_out:
        differences.append(f"Replay had timed-out orders: {replay.orders_timed_out}")
    differences.extend(operational_report.blockers)
    return differences


def _assumption_gaps() -> list[str]:
    return [
        "Replay uses a simulated broker, not Alpaca paper/live broker authority.",
        "ETF target weights are precomputed from the frozen signal function and replayed through runtime as a target-weight adapter.",
        "Runtime sizing is configured so fixed-fraction sizing maps target weights to notional exposure; this proves operational plumbing, not new alpha.",
        "Portfolio equity is held constant for target sizing during replay; mark-to-market equity is computed from filled orders at the end.",
    ]


def _position_weights(
    positions: dict[str, float],
    *,
    final_prices: dict[str, float],
    initial_capital: float,
) -> dict[str, float]:
    return {
        symbol: float(quantity) * final_prices.get(symbol, 0.0) / initial_capital
        for symbol, quantity in positions.items()
    }


def _scalar(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0] or 0) if row else 0


def _events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT event_type, severity, symbol, message, timestamp FROM events ORDER BY id"
    ).fetchall()
    return [dict(row) for row in rows]
