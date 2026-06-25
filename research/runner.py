"""Research backtest runner — vectorbt-based single-asset backtest.

This is the research prototyping path. For deployment-qualifying backtests,
the engine replay mode (engine/replay.py) exercises the full pipeline.

Signal convention (from strategies/ma/signal.py):
    - Signals at bar close, executed at next bar open (no lookahead)
    - position column = target position to hold going into next bar
    - signal column = action to take (1 enter, -1 exit/short, 0 hold)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import structlog

from config.schema import AssetClass, CostModelConfig
from research.cost_model import CostModel

log = structlog.get_logger(__name__)


@dataclass
class BacktestResult:
    """Container for a single backtest run's results."""

    strategy_name: str
    symbol: str
    params: dict[str, Any]
    equity_curve: pd.Series
    returns: pd.Series
    positions: pd.Series
    trades: pd.DataFrame
    metrics: dict[str, float] = field(default_factory=dict)
    bar_count: int = 0
    trade_count: int = 0


def run_single_asset_backtest(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    strategy_name: str = "ma_crossover",
    symbol: str = "UNKNOWN",
    asset_class: AssetClass = AssetClass.EQUITY,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
    params: dict[str, Any] | None = None,
) -> BacktestResult:
    """Run a vectorized single-asset backtest.

    Args:
        df: OHLCV DataFrame.
        signals: Output from a strategy's generate_signals() function.
        strategy_name: Name for labeling.
        symbol: Symbol being tested.
        asset_class: Equity or crypto (affects cost model).
        cost_config: Transaction cost configuration.
        initial_capital: Starting capital.
        params: Strategy parameters (for metadata).

    Returns:
        BacktestResult with equity curve, returns, trades, and metrics.
    """
    if cost_config is None:
        cost_config = CostModelConfig()
    cost_model = CostModel(cost_config)

    if signals.empty or "position" not in signals.columns:
        return _empty_result(strategy_name, symbol, params or {})

    # Align signals to price data
    aligned = df.join(signals[["position", "signal"]], how="inner")
    if aligned.empty:
        return _empty_result(strategy_name, symbol, params or {})

    # Execute at next bar open to avoid lookahead bias
    # position at bar T means we hold that position from T+1 onward
    position = aligned["position"].shift(1).fillna(0)
    signal_action = aligned["signal"].shift(1).fillna(0)

    # Returns: position * next-bar return
    close = aligned["close"]
    asset_returns = close.pct_change().fillna(0.0)

    # Apply transaction costs on signal changes
    round_trip_cost = cost_model.round_trip_cost_pct(asset_class)
    # Cost is incurred when position changes (entry or exit)
    position_change = position.diff().abs().fillna(0)
    trade_cost = position_change * round_trip_cost / 2  # half round-trip per side

    strategy_returns = position * asset_returns - trade_cost
    equity = (1 + strategy_returns).cumprod() * initial_capital

    # Build trades DataFrame
    trades = _extract_trades(position, close, signal_action, asset_class, cost_model)

    metrics = compute_metrics(strategy_returns, equity, initial_capital)

    return BacktestResult(
        strategy_name=strategy_name,
        symbol=symbol,
        params=params or {},
        equity_curve=equity,
        returns=strategy_returns,
        positions=position,
        trades=trades,
        metrics=metrics,
        bar_count=len(aligned),
        trade_count=len(trades),
    )


def compute_metrics(returns: pd.Series, equity: pd.Series, initial_capital: float) -> dict[str, float]:
    """Compute standard performance metrics."""
    if returns.empty:
        return {}

    total_return = (equity.iloc[-1] / initial_capital) - 1
    years = len(returns) / 252 if len(returns) > 252 else len(returns) / 252
    cagr = (equity.iloc[-1] / initial_capital) ** (1 / years) - 1 if years > 0 else 0

    ann_factor = 252  # daily bars
    ann_return = returns.mean() * ann_factor
    ann_vol = returns.std() * np.sqrt(ann_factor)
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0

    downside = returns[returns < 0]
    sortino = (ann_return / (downside.std() * np.sqrt(ann_factor))) if len(downside) > 0 and downside.std() > 0 else 0

    # Max drawdown
    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax
    max_dd = float(drawdown.min())

    # Win rate
    nonzero = returns[returns != 0]
    win_rate = float((nonzero > 0).mean()) if len(nonzero) > 0 else 0

    return {
        "total_return": float(total_return),
        "cagr": float(cagr),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": max_dd,
        "ann_volatility": float(ann_vol),
        "win_rate": win_rate,
        "total_bars": len(returns),
        "final_equity": float(equity.iloc[-1]),
    }


def _extract_trades(
    position: pd.Series,
    close: pd.Series,
    signal: pd.Series,
    asset_class: AssetClass,
    cost_model: CostModel,
) -> pd.DataFrame:
    """Extract individual trades from position changes."""
    entries = signal[signal != 0]
    if entries.empty:
        return pd.DataFrame(columns=["entry_time", "exit_time", "side", "entry_price", "exit_price", "pnl", "cost"])

    trades: list[dict[str, Any]] = []
    current_entry: dict[str, Any] | None = None

    for ts, sig in entries.items():
        pos = position.loc[ts]
        price = close.loc[ts]

        if sig > 0 and pos > 0:  # Enter long
            if current_entry is not None:
                # Close previous trade
                current_entry["exit_time"] = ts
                current_entry["exit_price"] = price
                current_entry["pnl"] = (price - current_entry["entry_price"]) * current_entry["direction"]
                trades.append(current_entry)
            current_entry = {
                "entry_time": ts,
                "side": "long",
                "direction": 1,
                "entry_price": price,
            }
        elif sig < 0:  # Exit or enter short
            if current_entry is not None:
                current_entry["exit_time"] = ts
                current_entry["exit_price"] = price
                current_entry["pnl"] = (price - current_entry["entry_price"]) * current_entry["direction"]
                trades.append(current_entry)
                current_entry = None
            if pos < 0:  # Enter short
                current_entry = {
                    "entry_time": ts,
                    "side": "short",
                    "direction": -1,
                    "entry_price": price,
                }

    # Close any open trade at the end
    if current_entry is not None:
        current_entry["exit_time"] = position.index[-1]
        current_entry["exit_price"] = close.iloc[-1]
        current_entry["pnl"] = (close.iloc[-1] - current_entry["entry_price"]) * current_entry["direction"]
        trades.append(current_entry)

    if not trades:
        return pd.DataFrame(columns=["entry_time", "exit_time", "side", "entry_price", "exit_price", "pnl"])

    trades_df = pd.DataFrame(trades)
    trades_df["cost"] = trades_df.apply(
        lambda r: cost_model.round_trip_cost_pct(asset_class) * r["entry_price"], axis=1
    )
    trades_df["net_pnl"] = trades_df["pnl"] - trades_df["cost"]
    return trades_df


def _empty_result(strategy_name: str, symbol: str, params: dict[str, Any]) -> BacktestResult:
    return BacktestResult(
        strategy_name=strategy_name,
        symbol=symbol,
        params=params,
        equity_curve=pd.Series(dtype=float),
        returns=pd.Series(dtype=float),
        positions=pd.Series(dtype=int),
        trades=pd.DataFrame(),
        metrics={},
        bar_count=0,
        trade_count=0,
    )


def print_report(result: BacktestResult) -> None:
    """Print a human-readable backtest report."""
    print(f"\n{'=' * 60}")
    print(f"  Backtest Report: {result.strategy_name} on {result.symbol}")
    print(f"{'=' * 60}")
    print(f"  Bars:     {result.bar_count}")
    print(f"  Trades:   {result.trade_count}")
    print(f"  Params:   {result.params}")
    print(f"  {'─' * 56}")
    for key, val in result.metrics.items():
        if isinstance(val, float):
            print(f"  {key:20s} {val:>12.4f}")
        else:
            print(f"  {key:20s} {val:>12}")
    print(f"{'=' * 60}\n")
