"""Engine replay mode — historical bars through the full pipeline.

This is the deployment-qualifying backtest path. Same code as live, but:
    - Reads bars from Parquet (not live feed)
    - Uses sim_broker (not real broker)
    - No real money at risk

Replay mode is deterministic: same data + same params = same result.
This is how we prove the engine behaves correctly before paper trading.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from config.schema import Config
from engine.runtime import TradingEngine
from execution.sim_broker.broker import SimBroker, SimBrokerConfig
from portfolio.sizing import PortfolioState
from risk.engine import DrawdownState
from storage.schema import init_db

log = structlog.get_logger(__name__)


@dataclass
class ReplayResult:
    """Results of a replay run."""

    bar_count: int = 0
    cycle_count: int = 0
    orders_submitted: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    orders_timed_out: int = 0
    final_equity: float = 0.0
    final_positions: dict[str, float] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def run_replay(
    bars: pd.DataFrame,
    config: Config,
    strategy_fn: Callable[[pd.DataFrame, dict[str, Any]], dict[str, float]],
    strategy_name: str,
    strategy_params: dict[str, Any] | None = None,
    *,
    broker_config: SimBrokerConfig | None = None,
    db_path: str | Path = "replay.sqlite",
    initial_capital: float = 10000.0,
    bar_frequency: str = "1D",
) -> ReplayResult:
    """Run a replay backtest — historical bars through the full engine.

    Args:
        bars: OHLCV DataFrame with DatetimeIndex.
        config: System configuration (risk limits, portfolio config, etc.).
        strategy_fn: Callable(bars_df, params) → {symbol: exposure}.
        strategy_name: Strategy name.
        strategy_params: Strategy parameters.
        broker_config: SimBroker failure config (default = no failures).
        db_path: Path for replay SQLite DB.
        initial_capital: Starting capital.
        bar_frequency: Bar frequency label for logging.

    Returns:
        ReplayResult with order/position/event counts.
    """
    result = ReplayResult()

    # Initialize DB
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()  # fresh replay
    conn = init_db(db_path)

    # Create sim broker
    broker = SimBroker(broker_config or SimBrokerConfig(seed=42))
    broker.connect()

    # Create engine
    engine = TradingEngine(
        config=config,
        conn=conn,
        broker=broker,
        strategy_fn=strategy_fn,
        strategy_name=strategy_name,
        strategy_params=strategy_params or {},
    )

    # Startup
    if not engine.startup():
        result.error = "engine_startup_failed"
        conn.close()
        return result

    # Get symbols from data
    symbols = bars["symbol"].unique().tolist() if "symbol" in bars.columns else ["UNKNOWN"]

    # Set prices on sim broker
    for sym in symbols:
        if sym in bars.columns:
            broker.set_price(sym, float(bars[sym].iloc[-1]))

    # Run through each bar
    portfolio_state = PortfolioState(
        cash=initial_capital,
        equity=initial_capital,
        high_water_mark=initial_capital,
    )
    drawdown = DrawdownState(
        high_water_mark=initial_capital,
        current_equity=initial_capital,
    )

    # Group bars by timestamp if multi-symbol
    if "symbol" in bars.columns:
        grouped = bars.groupby(level=0) if bars.index.name else bars.groupby(bars.index)
    else:
        grouped = [(ts, df) for ts, df in [(bars.index[i], bars.iloc[: i + 1]) for i in range(len(bars))]]

    for ts, bar_data in grouped:
        if engine.state.halted:
            result.error = f"engine_halted: {engine.state.halt_reason}"
            break

        # Build prices dict from latest bar
        if isinstance(bar_data, pd.DataFrame):
            if "close" in bar_data.columns and "symbol" in bar_data.columns:
                prices = {row["symbol"]: row["close"] for _, row in bar_data.iterrows()}
                # Update broker prices
                for sym, price in prices.items():
                    broker.set_price(sym, float(price))
            elif "close" in bar_data.columns:
                prices = {symbols[0]: float(bar_data["close"].iloc[-1])}
            else:
                prices = {}
        else:
            prices = {}

        # Process bar
        engine.process_bar(
            bars=bars.loc[:ts] if bars.index.name else bars.iloc[: bars.index.get_loc(ts) + 1],
            prices=prices,
            bar_timestamp=str(ts),
            portfolio_state=portfolio_state,
            drawdown=drawdown,
        )

        result.bar_count += 1
        result.cycle_count = engine.state.cycle_count

    # Collect final state
    from storage.repository import get_positions

    positions = get_positions(conn, strategy=strategy_name)
    result.final_positions = {p["symbol"]: p["quantity"] for p in positions}

    # Count orders from events
    order_count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type = 'ORDER_INTENT'"
    ).fetchone()[0]
    fill_count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type = 'ORDER_FILLED'"
    ).fetchone()[0]
    reject_count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type = 'BROKER_REJECT'"
    ).fetchone()[0]
    timeout_count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type = 'BROKER_TIMEOUT'"
    ).fetchone()[0]

    result.orders_submitted = order_count
    result.orders_filled = fill_count
    result.orders_rejected = reject_count
    result.orders_timed_out = timeout_count

    # Collect events for inspection
    events = conn.execute(
        "SELECT event_type, severity, symbol, message, timestamp FROM events ORDER BY id"
    ).fetchall()
    result.events = [dict(e) for e in events]

    # Shutdown
    engine.shutdown()
    conn.close()

    return result
