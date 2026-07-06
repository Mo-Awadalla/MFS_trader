"""Build the ETF TSM vs SPY comparison report and charts.

This is a deterministic, no-credential report builder. It uses the cached Yahoo
adjusted ETF daily bars from the validation-passed ETFTimeSeriesMomentumVolTarget-v1
experiment and writes recruiter-facing performance artifacts under docs/.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.etf_time_series_momentum_pipeline import (  # noqa: E402
    backtest_etf_time_series_momentum,
)
from research.runner import compute_metrics  # noqa: E402
from research.universes.etf_tactical_v1 import all_symbols  # noqa: E402
from storage.parquet_io import read_bars  # noqa: E402

CACHE_DIR = ROOT / "data" / "parquet" / "equity" / "yahoo_chart"
REPORT_PATH = ROOT / "docs" / "reports" / "etf_tsm_spy_comparison.md"
ASSET_DIR = ROOT / "docs" / "assets"
EQUITY_CHART = ASSET_DIR / "etf_tsm_equity_vs_spy.png"
DRAWDOWN_CHART = ASSET_DIR / "etf_tsm_drawdown_vs_spy.png"
INITIAL_CAPITAL = 10_000.0


def cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}_1d.parquet"


def load_symbol(symbol: str) -> pd.DataFrame:
    path = cache_path(symbol)
    if not path.exists():
        raise FileNotFoundError(f"missing cached Yahoo daily bars for {symbol}: {path}")
    return read_bars(path)


def build_panel(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    columns = []
    for symbol in sorted(frames):
        df = frames[symbol][["open", "high", "low", "close", "volume"]].copy()
        df.columns = pd.MultiIndex.from_product([[symbol], df.columns], names=["symbol", "field"])
        columns.append(df)
    panel = pd.concat(columns, axis=1, sort=True).sort_index()
    return panel.loc[~panel.index.duplicated(keep="last")]


def drawdown(equity: pd.Series) -> pd.Series:
    return (equity / equity.cummax()) - 1.0


def spy_buy_and_hold(spy: pd.DataFrame, index: pd.Index) -> tuple[pd.Series, pd.Series, dict[str, float]]:
    close = spy["close"].reindex(index).ffill()
    returns = close.pct_change(fill_method=None).fillna(0.0)
    equity = (1.0 + returns).cumprod() * INITIAL_CAPITAL
    return returns, equity, compute_metrics(returns, equity, INITIAL_CAPITAL)


def metric_row(name: str, strategy_value: Any, spy_value: Any, fmt: str = ".4f") -> str:
    strategy_text = format(strategy_value, fmt) if isinstance(strategy_value, float) else str(strategy_value)
    spy_text = format(spy_value, fmt) if isinstance(spy_value, float) else str(spy_value)
    return f"| {name} | {strategy_text} | {spy_text} |"


def pct(value: float) -> str:
    return f"{value:.2%}"


def multiple(value: float) -> str:
    return f"{value:.2f}x"


def make_charts(strategy_equity: pd.Series, spy_equity: pd.Series) -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    (strategy_equity / INITIAL_CAPITAL).plot(ax=ax, label="ETF TSM vol-target", linewidth=2.0)
    (spy_equity / INITIAL_CAPITAL).plot(ax=ax, label="SPY buy-and-hold", linewidth=1.8)
    ax.set_title("Growth of $1: ETF TSM vs SPY")
    ax.set_ylabel("Growth multiple")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(EQUITY_CHART, dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    drawdown(strategy_equity).plot(ax=ax, label="ETF TSM vol-target", linewidth=2.0)
    drawdown(spy_equity).plot(ax=ax, label="SPY buy-and-hold", linewidth=1.8)
    ax.set_title("Drawdown: ETF TSM vs SPY")
    ax.set_ylabel("Drawdown")
    ax.yaxis.set_major_formatter(lambda x, _pos: f"{x:.0%}")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(DRAWDOWN_CHART, dpi=160)
    plt.close(fig)


def build_report() -> str:
    frames = {symbol: load_symbol(symbol) for symbol in all_symbols()}
    panel = build_panel(frames)
    strategy = backtest_etf_time_series_momentum(panel, initial_capital=INITIAL_CAPITAL)
    spy_returns, spy_equity, spy_metrics = spy_buy_and_hold(frames["SPY"], strategy.returns.index)
    make_charts(strategy.equity_curve, spy_equity)

    aligned = pd.concat(
        [strategy.returns.rename("strategy"), spy_returns.rename("spy")],
        axis=1,
    ).dropna()
    correlation = float(aligned["strategy"].corr(aligned["spy"]))
    annualized_active_return = float((aligned["strategy"] - aligned["spy"]).mean() * 252)

    report = [
        "# ETF TSM vs SPY Comparison",
        "",
        "This report compares the validation-passed `ETFTimeSeriesMomentumVolTarget-v1` Experiment against a SPY buy-and-hold benchmark using the same cached Yahoo adjusted daily data panel.",
        "",
        "Important scope: this is SPY-relative vectorized research evidence. It supports the resume/project story, but paper/live approval remains separate; simulated runtime replay evidence lives in `docs/reports/etf_tsm_engine_replay/etf_tsm_engine_replay.md`.",
        "",
        "## Inputs",
        "",
        f"- Symbols: {', '.join(all_symbols())}",
        f"- Date range: {panel.index.min()} to {panel.index.max()}",
        f"- Bars: {len(panel)}",
        "- Data source: cached Yahoo Chart adjusted daily OHLCV (`data/parquet/equity/yahoo_chart`)",
        "- Starting equity: $10,000",
        "- Strategy: 12-month absolute momentum, top 3 positive-trend ETFs, inverse-volatility weighting, 10% annual volatility target, SHY defensive fallback",
        "",
        "## Headline Metrics",
        "",
        "| Metric | ETF TSM vol-target | SPY buy-and-hold |",
        "| --- | ---: | ---: |",
        metric_row("Total return", multiple(strategy.metrics["total_return"]), multiple(spy_metrics["total_return"]), ""),
        metric_row("CAGR", pct(strategy.metrics["cagr"]), pct(spy_metrics["cagr"]), ""),
        metric_row("Sharpe", strategy.metrics["sharpe"], spy_metrics["sharpe"]),
        metric_row("Sortino", strategy.metrics["sortino"], spy_metrics["sortino"]),
        metric_row("Annual volatility", pct(strategy.metrics["ann_volatility"]), pct(spy_metrics["ann_volatility"]), ""),
        metric_row("Max drawdown", pct(strategy.metrics["max_drawdown"]), pct(spy_metrics["max_drawdown"]), ""),
        metric_row("Final equity", f"${strategy.metrics['final_equity']:,.2f}", f"${spy_metrics['final_equity']:,.2f}", ""),
        "",
        "## SPY-relative diagnostics",
        "",
        f"- Strategy/SPY daily return correlation: `{correlation:.4f}`",
        f"- Annualized active return vs SPY: `{annualized_active_return:.2%}`",
        f"- Rebalances: `{strategy.rebalance_count}`",
        f"- Skipped rebalances: `{strategy.skipped_rebalance_count}`",
        f"- Trade rows: `{strategy.trade_count}`",
        "",
        "## Charts",
        "",
        f"![ETF TSM equity vs SPY](../assets/{EQUITY_CHART.name})",
        "",
        f"![ETF TSM drawdown vs SPY](../assets/{DRAWDOWN_CHART.name})",
        "",
        "## Interpretation",
        "",
        "The strategy's resume value is not only the return profile; it is the disciplined process: the hypothesis was source-backed, frozen before validation, passed WFA/MC/DSR/stability, and remains explicitly marked as not paper/live approved until operational gates are completed.",
        "",
    ]
    return "\n".join(report)


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = build_report()
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"wrote {REPORT_PATH}")
    print(f"wrote {EQUITY_CHART}")
    print(f"wrote {DRAWDOWN_CHART}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
