"""BB validation pipeline integration tests.

Proves the BB path can produce:
  - research report
  - parameter sweep
  - WFA / MC / DSR / stability via Validation Gauntlet
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.bb_pipeline import (
    STRATEGY_NAME,
    backtest_bb,
    format_bb_gauntlet_report,
    run_bb_research_report,
    run_bb_sweep,
    run_bb_validation_gauntlet,
)
from strategies.bb.signal import BBParams, compact_sweep_grid, default_params


def _make_ohlcv(n: int = 900, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="1D", tz="UTC")
    close = 150.0 + 8.0 * np.sin(np.linspace(0, 40, n)) + np.cumsum(rng.normal(0, 0.2, n))
    return pd.DataFrame(
        {
            "open": close - 0.3,
            "high": close + 0.6,
            "low": close - 0.6,
            "close": close,
            "volume": rng.integers(500_000, 2_000_000, n).astype(float),
        },
        index=idx,
    )


class TestBBValidationPipeline:
    def test_research_report_runs(self):
        df = _make_ohlcv()
        result = run_bb_research_report(df, symbol="AAPL", params=default_params())
        assert result.strategy_name == STRATEGY_NAME
        assert result.bar_count > 0
        assert "sharpe" in result.metrics

    def test_sweep_produces_rows(self):
        df = _make_ohlcv()
        sweep = run_bb_sweep(df, grid=compact_sweep_grid(), symbol="AAPL")
        assert len(sweep) == 3
        assert "sharpe" in sweep.columns
        assert "window" in sweep.columns

    def test_backtest_with_boring_aapl_defaults(self):
        df = _make_ohlcv()
        result = backtest_bb(df, default_params(), symbol="AAPL")
        assert result.params["window"] == 20
        assert result.params["std_mult"] == 2.0
        assert result.params["width_mode"] == "normal"
        assert result.params["long_only"] is True

    def test_validation_gauntlet_runs_all_stages(self):
        df = _make_ohlcv()
        grid = compact_sweep_grid()
        report = run_bb_validation_gauntlet(
            df,
            params=BBParams(window=10, std_mult=1.5, width_mode="none", width_lookback=30),
            symbol="AAPL",
            sweep_grid_override=grid,
            wfa_grid_override=grid,
            seed=42,
        )

        assert report.research.bar_count > 0
        assert len(report.sweep) == len(grid)
        assert report.gauntlet.wfa_result is not None
        assert report.gauntlet.mc_result is not None
        assert report.gauntlet.stability_result is not None
        if report.gauntlet.dsr_result is None:
            assert any("DSR" in reason for reason in report.gauntlet.failure_reasons)
        assert isinstance(report.gauntlet.passed, bool)
        assert report.to_dict()["gauntlet"]["passed"] == report.gauntlet.passed
        assert report.to_dict()["strategy_template_version"] == "bollinger_bands:v2"
        assert report.research.params["strategy_template_version"] == "bollinger_bands:v2"

    def test_gauntlet_report_renders(self):
        df = _make_ohlcv(600)
        report = run_bb_validation_gauntlet(
            df,
            sweep_grid_override=compact_sweep_grid(),
            wfa_grid_override=compact_sweep_grid(),
        )
        text = format_bb_gauntlet_report(report)
        assert "BB Validation Report" in text
        assert "Gauntlet passed" in text
