"""Convenience: run the BB mean-reversion strategy through the research pipeline."""

from __future__ import annotations

from pathlib import Path

from config.schema import AssetClass, CostModelConfig
from data.pipeline import load_bars
from research.bb_pipeline import backtest_bb, default_cost_config
from research.runner import BacktestResult, print_report
from strategies.bb.signal import BBParams, default_params


def run_bb_backtest(
    storage_dir: str | Path,
    symbol: str,
    source: str,
    frequency: str = "1d",
    params: BBParams | None = None,
    asset_class: AssetClass = AssetClass.EQUITY,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = 10000.0,
    start: str | None = None,
    end: str | None = None,
) -> BacktestResult:
    """Load bars, generate BB signals, run backtest, return result."""
    params = params or default_params()
    cost_config = cost_config or default_cost_config()
    df = load_bars(storage_dir, symbol, frequency, source=source, start=start, end=end)
    return backtest_bb(
        df,
        params,
        symbol=symbol,
        asset_class=asset_class,
        cost_config=cost_config,
        initial_capital=initial_capital,
    )


if __name__ == "__main__":  # pragma: no cover
    import sys

    if len(sys.argv) < 4:
        print("Usage: python -m research.bb_backtest <storage_dir> <symbol> <source> [frequency]")
        sys.exit(1)

    result = run_bb_backtest(
        storage_dir=sys.argv[1],
        symbol=sys.argv[2],
        source=sys.argv[3],
        frequency=sys.argv[4] if len(sys.argv) > 4 else "1d",
    )
    print_report(result)
