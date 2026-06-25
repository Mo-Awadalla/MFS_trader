"""Convenience: run the MA crossover strategy through the research pipeline.

This wires together: load data → generate signals → backtest → report.
"""

from __future__ import annotations

from pathlib import Path

from config.schema import AssetClass, CostModelConfig
from data.pipeline import load_bars
from research.runner import BacktestResult, print_report, run_single_asset_backtest
from strategies.ma.signal import MAParams, generate_signals


def run_ma_backtest(
    storage_dir: str | Path,
    symbol: str,
    source: str,
    frequency: str = "1d",
    params: MAParams | None = None,
    asset_class: AssetClass = AssetClass.EQUITY,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
    start: str | None = None,
    end: str | None = None,
) -> BacktestResult:
    """Load bars, generate MA signals, run backtest, return result."""
    params = params or MAParams()
    df = load_bars(storage_dir, symbol, frequency, source=source, start=start, end=end)
    signals = generate_signals(df, params)
    result = run_single_asset_backtest(
        df,
        signals,
        strategy_name="dual_ma_crossover",
        symbol=symbol,
        asset_class=asset_class,
        cost_config=cost_config,
        initial_capital=initial_capital,
        params={
            "fast_ma_type": params.fast_ma_type,
            "fast_ma_window": params.fast_ma_window,
            "slow_ma_type": params.slow_ma_type,
            "slow_ma_window": params.slow_ma_window,
            "trend_filter_active": params.trend_filter_active,
            "trend_filter_window": params.trend_filter_window,
            "long_only": params.long_only,
        },
    )
    return result


if __name__ == "__main__":  # pragma: no cover
    import sys

    if len(sys.argv) < 4:
        print("Usage: python -m research.ma_backtest <storage_dir> <symbol> <source> [frequency]")
        sys.exit(1)

    result = run_ma_backtest(
        storage_dir=sys.argv[1],
        symbol=sys.argv[2],
        source=sys.argv[3],
        frequency=sys.argv[4] if len(sys.argv) > 4 else "1d",
    )
    print_report(result)
