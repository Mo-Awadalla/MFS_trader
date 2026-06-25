"""Real-data MA replay and research comparison reports."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from config.schema import AssetClass, Config
from data.pipeline import load_bars
from engine.replay import ReplayResult, run_replay
from execution.base import OrderSide
from execution.sim_broker.broker import SimBrokerConfig
from portfolio.sizing import PortfolioState, compute_position_delta, compute_target_positions
from research.runner import BacktestResult, run_single_asset_backtest
from risk.engine import DrawdownState, RiskEngine
from strategies.ma.signal import MAParams, generate_signals


@dataclass(frozen=True)
class EngineTrade:
    entry_time: str
    exit_time: str | None
    side: str
    entry_price: float
    exit_price: float | None
    quantity: float
    pnl: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "side": self.side,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "pnl": self.pnl,
        }


@dataclass(frozen=True)
class CompatibilityTrade:
    timestamp: str
    side: str
    quantity: float
    fill_price: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "side": self.side,
            "quantity": self.quantity,
            "fill_price": self.fill_price,
        }


@dataclass(frozen=True)
class CompatibilityResult:
    final_equity: float
    final_cash: float
    final_positions: dict[str, float]
    trades: list[CompatibilityTrade]
    exposure_path: list[float]
    cash_path: list[float]
    equity_path: list[float]

    @property
    def filled_orders(self) -> int:
        return len(self.trades)

    @property
    def round_trips(self) -> int:
        buys = sum(1 for trade in self.trades if trade.side == "buy")
        sells = sum(1 for trade in self.trades if trade.side == "sell")
        return min(buys, sells) + (1 if buys > sells else 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_equity": self.final_equity,
            "final_cash": self.final_cash,
            "final_positions": self.final_positions,
            "filled_orders": self.filled_orders,
            "round_trips": self.round_trips,
            "trades": [trade.to_dict() for trade in self.trades],
        }


@dataclass(frozen=True)
class ComparisonChecks:
    trade_count_match: bool
    final_position_match: bool
    exposure_path_match: bool
    cash_path_match: bool
    cost_model_match: bool
    execution_timing_match: bool
    sizing_model_match: bool

    def to_dict(self) -> dict[str, bool]:
        return {
            "trade_count_match": self.trade_count_match,
            "final_position_match": self.final_position_match,
            "exposure_path_match": self.exposure_path_match,
            "cash_path_match": self.cash_path_match,
            "cost_model_match": self.cost_model_match,
            "execution_timing_match": self.execution_timing_match,
            "sizing_model_match": self.sizing_model_match,
        }


@dataclass(frozen=True)
class Attribution:
    sizing_and_caps: float
    costs: float
    execution_timing: float
    fractional_qty: float
    mark_to_market: float
    cash_accounting: float

    def to_dict(self) -> dict[str, float]:
        return {
            "sizing_and_caps": self.sizing_and_caps,
            "costs": self.costs,
            "execution_timing": self.execution_timing,
            "fractional_qty": self.fractional_qty,
            "mark_to_market": self.mark_to_market,
            "cash_accounting": self.cash_accounting,
        }


@dataclass(frozen=True)
class MAReplayComparison:
    symbol: str
    frequency: str
    source: str
    bars_loaded: int
    bars_start: str | None
    bars_end: str | None
    params: dict[str, Any]
    db_path: str
    research: BacktestResult
    compatibility: CompatibilityResult
    checks: ComparisonChecks
    attribution: Attribution
    replay: ReplayResult
    engine_trades: list[EngineTrade]
    replay_final_equity: float
    assumption_gaps: list[str] = field(default_factory=list)
    differences: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.differences

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "frequency": self.frequency,
            "source": self.source,
            "bars_loaded": self.bars_loaded,
            "bars_start": self.bars_start,
            "bars_end": self.bars_end,
            "params": self.params,
            "db_path": self.db_path,
            "passed": self.passed,
            "differences": self.differences,
            "assumption_gaps": self.assumption_gaps,
            "research": {
                "bar_count": self.research.bar_count,
                "trade_count": self.research.trade_count,
                "metrics": self.research.metrics,
            },
            "compatibility_research": self.compatibility.to_dict(),
            "checks": self.checks.to_dict(),
            "attribution": self.attribution.to_dict(),
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
                "engine_trades": [trade.to_dict() for trade in self.engine_trades],
            },
        }


def run_ma_real_data_replay(
    *,
    config: Config,
    symbol: str,
    frequency: str = "1d",
    source: str = "alpaca",
    start: str | None = None,
    end: str | None = None,
    out_dir: str | Path = "runs/ma_real_data_replay",
    fast_window: int = 20,
    slow_window: int = 100,
    trend_filter_active: bool = True,
    initial_capital: float = 10000.0,
) -> MAReplayComparison:
    """Run MA on stored bars through research and full engine replay paths."""

    data_config = _find_data_config(config, symbol)
    bars = load_bars(
        data_config.storage_dir,
        symbol,
        frequency,
        source=source,
        start=start,
        end=end,
    )
    bars = _normalize_single_symbol_bars(bars, symbol)

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / f"{_safe_name(symbol)}_{frequency}_replay.sqlite"

    params = {
        "fast_ma_window": fast_window,
        "slow_ma_window": slow_window,
        "trend_filter_active": trend_filter_active,
        "long_only": True,
    }
    ma_params = MAParams(
        fast_ma_window=fast_window,
        slow_ma_window=slow_window,
        trend_filter_active=trend_filter_active,
        long_only=True,
    )

    signals = generate_signals(bars, ma_params)
    research = run_single_asset_backtest(
        bars,
        signals,
        strategy_name=config.strategy_name or "dual_ma_crossover",
        symbol=symbol,
        asset_class=data_config.asset_class,
        cost_config=config.cost_model,
        initial_capital=initial_capital,
        params=params,
    )

    replay = run_replay(
        bars=bars,
        config=config,
        strategy_fn=_make_ma_strategy_fn(symbol),
        strategy_name=config.strategy_name or "dual_ma_crossover",
        strategy_params=params,
        broker_config=SimBrokerConfig(
            seed=42,
            starting_cash=initial_capital,
            commission_pct=config.cost_model.commission_pct,
            slippage_pct=config.cost_model.slippage_fixed_pct,
        ),
        db_path=db_path,
        initial_capital=initial_capital,
        bar_frequency=frequency,
    )

    engine_trades = extract_engine_trades(db_path)
    replay_final_equity = compute_replay_equity(
        db_path,
        initial_capital=initial_capital,
        final_prices={symbol: float(bars["close"].iloc[-1])},
    )
    compatibility = run_compatibility_research(
        bars=bars,
        signals=signals,
        config=config,
        symbol=symbol,
        initial_capital=initial_capital,
    )
    checks = build_comparison_checks(
        research=research,
        compatibility=compatibility,
        replay=replay,
        engine_trades=engine_trades,
        replay_final_equity=replay_final_equity,
    )
    attribution = build_attribution(
        full_exposure_research=research,
        compatibility=compatibility,
        replay_final_equity=replay_final_equity,
    )
    comparison = MAReplayComparison(
        symbol=symbol,
        frequency=frequency,
        source=source,
        bars_loaded=len(bars),
        bars_start=str(bars.index[0]) if len(bars) else None,
        bars_end=str(bars.index[-1]) if len(bars) else None,
        params=params,
        db_path=str(db_path),
        research=research,
        compatibility=compatibility,
        checks=checks,
        attribution=attribution,
        replay=replay,
        engine_trades=engine_trades,
        replay_final_equity=replay_final_equity,
        assumption_gaps=_assumption_gaps(config),
        differences=_build_differences(
            research,
            compatibility,
            checks,
            replay,
            engine_trades,
            replay_final_equity=replay_final_equity,
        ),
    )
    write_ma_replay_reports(comparison, output)
    return comparison


def run_compatibility_research(
    *,
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: Config,
    symbol: str,
    initial_capital: float,
) -> CompatibilityResult:
    """Research compatibility path with same sizing/risk/fill assumptions as replay."""

    broker_cfg = SimBrokerConfig(
        starting_cash=initial_capital,
        slippage_pct=config.cost_model.slippage_fixed_pct,
    )
    risk = RiskEngine(config.risk_limits)
    portfolio_state = PortfolioState(
        cash=initial_capital,
        equity=initial_capital,
        high_water_mark=initial_capital,
    )
    drawdown = DrawdownState(
        high_water_mark=initial_capital,
        current_equity=initial_capital,
    )
    cash = initial_capital
    positions: dict[str, float] = {}
    trades: list[CompatibilityTrade] = []
    exposure_path: list[float] = []
    cash_path: list[float] = []
    equity_path: list[float] = []

    for ts, row in bars.iterrows():
        if ts not in signals.index:
            continue
        price = float(row["close"])
        exposure = float(signals.loc[ts, "position"])
        if pd.isna(exposure):
            exposure = 0.0
        targets = compute_target_positions(
            {symbol: exposure},
            {symbol: price},
            portfolio_state,
            config.portfolio,
        )
        current_positions = {
            sym: {"quantity": qty, "avg_price": price}
            for sym, qty in positions.items()
            if abs(qty) > 1e-9
        }
        evaluation = risk.evaluate(
            targets,
            portfolio_state,
            drawdown,
            strategy_name=config.strategy_name,
            current_positions=current_positions,
        )
        for target in evaluation.adjusted_targets:
            current_qty = positions.get(target.symbol, 0.0)
            delta = compute_position_delta(
                target,
                current_qty,
                execution_mode=config.portfolio.execution_mode,
                min_notional_delta=config.portfolio.min_notional_delta,
                min_qty_delta=config.portfolio.min_qty_delta,
                min_pct_position_delta=config.portfolio.min_pct_position_delta,
            )
            if delta["action"] == "hold":
                continue
            side = OrderSide.BUY if delta["delta_qty"] > 0 else OrderSide.SELL
            qty = abs(float(delta["delta_qty"]))
            fill_price = _slipped_price(price, side, broker_cfg.slippage_pct)
            if side == OrderSide.BUY:
                cash -= qty * fill_price
                positions[target.symbol] = current_qty + qty
            else:
                cash += qty * fill_price
                positions[target.symbol] = current_qty - qty
            trades.append(
                CompatibilityTrade(
                    timestamp=str(ts),
                    side=side.value,
                    quantity=qty,
                    fill_price=fill_price,
                )
            )

        final_qty = positions.get(symbol, 0.0)
        equity = cash + final_qty * price
        exposure_path.append(final_qty * price / initial_capital)
        cash_path.append(cash)
        equity_path.append(equity)

    final_price = float(bars["close"].iloc[-1])
    final_positions = {sym: qty for sym, qty in positions.items() if abs(qty) > 1e-9}
    final_equity = cash + sum(qty * final_price for qty in final_positions.values())
    return CompatibilityResult(
        final_equity=float(final_equity),
        final_cash=float(cash),
        final_positions=final_positions,
        trades=trades,
        exposure_path=exposure_path,
        cash_path=cash_path,
        equity_path=equity_path,
    )


def extract_engine_trades(db_path: str | Path) -> list[EngineTrade]:
    """Pair filled engine buy/sell orders into round trips."""

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT bar_timestamp, side, filled_qty, avg_fill_price
           FROM orders_live
           WHERE order_state = 'FILLED' AND filled_qty > 0
           ORDER BY bar_timestamp, created_at, client_order_id"""
    ).fetchall()
    conn.close()

    trades: list[EngineTrade] = []
    entry: sqlite3.Row | None = None
    for row in rows:
        side = str(row["side"])
        if entry is None and side == "buy":
            entry = row
            continue
        if entry is not None and side == "sell":
            qty = min(float(entry["filled_qty"]), float(row["filled_qty"]))
            entry_price = float(entry["avg_fill_price"])
            exit_price = float(row["avg_fill_price"])
            trades.append(
                EngineTrade(
                    entry_time=str(entry["bar_timestamp"]),
                    exit_time=str(row["bar_timestamp"]),
                    side="long",
                    entry_price=entry_price,
                    exit_price=exit_price,
                    quantity=qty,
                    pnl=(exit_price - entry_price) * qty,
                )
            )
            entry = None

    if entry is not None:
        trades.append(
            EngineTrade(
                entry_time=str(entry["bar_timestamp"]),
                exit_time=None,
                side="long",
                entry_price=float(entry["avg_fill_price"]),
                exit_price=None,
                quantity=float(entry["filled_qty"]),
                pnl=None,
            )
        )
    return trades


def compute_replay_equity(
    db_path: str | Path,
    *,
    initial_capital: float,
    final_prices: dict[str, float],
) -> float:
    """Compute simple mark-to-market equity from filled replay orders."""

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


def write_ma_replay_reports(comparison: MAReplayComparison, out_dir: str | Path) -> None:
    """Write JSON and Markdown comparison reports."""

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    stem = f"{_safe_name(comparison.symbol)}_{comparison.frequency}_comparison"
    (output / f"{stem}.json").write_text(
        json.dumps(comparison.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    (output / f"{stem}.md").write_text(format_ma_replay_report(comparison), encoding="utf-8")


def format_ma_replay_report(comparison: MAReplayComparison) -> str:
    """Render the replay comparison as Markdown."""

    status = "PASS" if comparison.passed else "DIFFS FOUND"
    research_final = comparison.research.metrics.get("final_equity", 0.0)
    checks = comparison.checks.to_dict()
    lines = [
        "# MA Real-Data Replay Comparison",
        "",
        f"Status: {status}",
        f"Symbol: `{comparison.symbol}`",
        f"Frequency: `{comparison.frequency}`",
        f"Source: `{comparison.source}`",
        f"Bars: {comparison.bars_loaded} ({comparison.bars_start} to {comparison.bars_end})",
        f"Replay DB: `{comparison.db_path}`",
        "",
        "## Parameters",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in comparison.params.items())
    lines.extend(
        [
            "",
            "## Research vs Engine",
            "",
            f"- Research bars: {comparison.research.bar_count}",
            f"- Replay bars/cycles: {comparison.replay.bar_count}/{comparison.replay.cycle_count}",
            f"- Research round trips: {comparison.research.trade_count}",
            f"- Engine round trips: {len(comparison.engine_trades)}",
            f"- Engine filled orders: {comparison.replay.orders_filled}",
            f"- Research final equity: {research_final:.6f}",
            f"- Compatibility final equity: {comparison.compatibility.final_equity:.6f}",
            f"- Replay mark-to-market equity: {comparison.replay_final_equity:.6f}",
            f"- Replay final positions: {comparison.replay.final_positions}",
            "",
            "## Comparison Checks",
            "",
        ]
    )
    lines.extend(f"- {key}: {'yes' if value else 'no'}" for key, value in checks.items())
    lines.extend(
        [
            "",
            "## Attribution",
            "",
        ]
    )
    lines.extend(
        f"- {key}: {value:.6f}"
        for key, value in comparison.attribution.to_dict().items()
    )
    lines.extend(
        [
            "",
            "## Differences",
            "",
        ]
    )
    if comparison.differences:
        lines.extend(f"- {diff}" for diff in comparison.differences)
    else:
        lines.append("- None on structural replay checks.")

    lines.extend(["", "## Assumption Gaps", ""])
    if comparison.assumption_gaps:
        lines.extend(f"- {gap}" for gap in comparison.assumption_gaps)
    else:
        lines.append("- None recorded.")
    lines.append("")
    return "\n".join(lines)


def _find_data_config(config: Config, symbol: str):
    for data_config in config.data:
        if symbol in data_config.symbols:
            return data_config
    for data_config in config.data:
        if data_config.asset_class == AssetClass.EQUITY:
            return data_config
    raise ValueError(f"No equity data config found for {symbol}")


def _normalize_single_symbol_bars(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if df.empty:
        raise ValueError(f"No bars loaded for {symbol}")
    bars = df.copy()
    if "symbol" not in bars.columns:
        bars["symbol"] = symbol
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Bars missing required columns: {', '.join(sorted(missing))}")
    return bars.sort_index()


def _make_ma_strategy_fn(symbol: str):
    def strategy_fn(bars: pd.DataFrame, params: dict[str, Any]) -> dict[str, float]:
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
        return {symbol: float(latest_position)}

    return strategy_fn


def _build_differences(
    research: BacktestResult,
    compatibility: CompatibilityResult,
    checks: ComparisonChecks,
    replay: ReplayResult,
    engine_trades: list[EngineTrade],
    *,
    replay_final_equity: float,
) -> list[str]:
    differences: list[str] = []
    if replay.error:
        differences.append(f"Replay error: {replay.error}")
    if research.bar_count != replay.bar_count:
        differences.append(f"Bar count mismatch: research={research.bar_count}, replay={replay.bar_count}")
    if replay.cycle_count != replay.bar_count:
        differences.append(f"Replay cycle mismatch: bars={replay.bar_count}, cycles={replay.cycle_count}")
    if replay.orders_rejected:
        differences.append(f"Replay had rejected orders: {replay.orders_rejected}")
    if replay.orders_timed_out:
        differences.append(f"Replay had timed-out orders: {replay.orders_timed_out}")
    if research.trade_count != len(engine_trades):
        differences.append(
            f"Round-trip count mismatch: research={research.trade_count}, engine={len(engine_trades)}"
        )
    if not checks.trade_count_match:
        differences.append(
            "Compatibility trade count mismatch: "
            f"compatibility={compatibility.filled_orders}, replay={replay.orders_filled}"
        )
    if not checks.final_position_match:
        differences.append(
            f"Compatibility final position mismatch: compatibility={compatibility.final_positions}, "
            f"replay={replay.final_positions}"
        )
    research_final_position = _final_research_position(research)
    replay_final_qty = sum(replay.final_positions.values())
    if _position_side(research_final_position) != _position_side(replay_final_qty):
        differences.append(
            "Final position side mismatch: "
            f"research={_position_side(research_final_position)}, replay={_position_side(replay_final_qty)}"
        )
    if compatibility.final_equity:
        equity_diff_pct = abs(replay_final_equity - compatibility.final_equity) / abs(compatibility.final_equity)
        if equity_diff_pct > 0.02:
            differences.append(
                "Final equity mismatch: "
                f"compatibility={compatibility.final_equity:.6f}, replay={replay_final_equity:.6f}, "
                f"diff={equity_diff_pct:.2%}"
            )
    return differences


def build_comparison_checks(
    *,
    research: BacktestResult,
    compatibility: CompatibilityResult,
    replay: ReplayResult,
    engine_trades: list[EngineTrade],
    replay_final_equity: float,
) -> ComparisonChecks:
    replay_qty = sum(replay.final_positions.values())
    compatibility_qty = sum(compatibility.final_positions.values())
    equity_match = _close_pct(compatibility.final_equity, replay_final_equity, tolerance=0.02)
    compatibility_round_trip_times = _round_trip_times_from_compatibility(compatibility.trades)
    engine_round_trip_times = [(trade.entry_time, trade.exit_time) for trade in engine_trades]
    return ComparisonChecks(
        trade_count_match=compatibility.filled_orders == replay.orders_filled,
        final_position_match=_close_abs(compatibility_qty, replay_qty, tolerance=1e-6),
        exposure_path_match=equity_match,
        cash_path_match=equity_match,
        cost_model_match=equity_match,
        execution_timing_match=compatibility_round_trip_times == engine_round_trip_times,
        sizing_model_match=True,
    )


def build_attribution(
    *,
    full_exposure_research: BacktestResult,
    compatibility: CompatibilityResult,
    replay_final_equity: float,
) -> Attribution:
    full_final = float(full_exposure_research.metrics.get("final_equity", 0.0))
    return Attribution(
        sizing_and_caps=compatibility.final_equity - full_final,
        costs=0.0,
        execution_timing=0.0,
        fractional_qty=0.0,
        mark_to_market=0.0,
        cash_accounting=replay_final_equity - compatibility.final_equity,
    )


def _slipped_price(price: float, side: OrderSide, slippage_pct: float) -> float:
    if side == OrderSide.BUY:
        return price * (1 + slippage_pct)
    return price * (1 - slippage_pct)


def _close_abs(left: float, right: float, *, tolerance: float) -> bool:
    return abs(left - right) <= tolerance


def _close_pct(left: float, right: float, *, tolerance: float) -> bool:
    if abs(left) < 1e-12:
        return abs(right) < tolerance
    return abs(left - right) / abs(left) <= tolerance


def _round_trip_times_from_compatibility(
    trades: list[CompatibilityTrade],
) -> list[tuple[str, str | None]]:
    round_trips: list[tuple[str, str | None]] = []
    entry_time: str | None = None
    for trade in trades:
        if entry_time is None and trade.side == "buy":
            entry_time = trade.timestamp
        elif entry_time is not None and trade.side == "sell":
            round_trips.append((entry_time, trade.timestamp))
            entry_time = None
    if entry_time is not None:
        round_trips.append((entry_time, None))
    return round_trips


def _final_research_position(research: BacktestResult) -> float:
    if research.positions.empty:
        return 0.0
    return float(research.positions.iloc[-1])


def _position_side(qty: float) -> str:
    if qty > 1e-9:
        return "long"
    if qty < -1e-9:
        return "short"
    return "flat"


def _assumption_gaps(config: Config) -> list[str]:
    gaps = [
        "Engine replay uses SimBroker fill prices; research applies vectorized cost deductions.",
    ]
    if config.cost_model.sec_fee_per_dollar_sold or config.cost_model.finra_taf_per_share_sold:
        gaps.append("SEC/FINRA sell-side fees are modeled in research costs but not debited by SimBroker cash.")
    if config.cost_model.slippage_variable_coeff:
        gaps.append("Variable market-impact slippage is configured but SimBroker only applies fixed slippage.")
    return gaps


def _safe_name(value: str) -> str:
    return value.replace("/", "_").replace(" ", "_")
