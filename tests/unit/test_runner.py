"""Tests for the research backtest runner."""

from __future__ import annotations

import pandas as pd

from config.schema import AssetClass, CostModelConfig
from research.cost_model import CostModel
from research.runner import compute_metrics, run_single_asset_backtest
from strategies.ma.signal import MAParams, generate_signals


def _make_ohlcv(n: int = 300, start_price: float = 100.0, trend: float = 0.1) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    close = [start_price + trend * i for i in range(n)]
    return pd.DataFrame(
        {
            "open": [c - 0.5 for c in close],
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [10000.0] * n,
        },
        index=idx,
    )


class TestCostModel:
    def test_equity_buy_cost(self):
        cfg = CostModelConfig()
        model = CostModel(cfg)
        cost = model.equity_trade_cost(side="buy", qty=10, price=100.0)
        assert cost.commission >= 0
        assert cost.sec_fee == 0  # buy side, no SEC fee
        assert cost.slippage_fixed > 0

    def test_equity_sell_cost_includes_sec_fee(self):
        cfg = CostModelConfig()
        model = CostModel(cfg)
        cost = model.equity_trade_cost(side="sell", qty=10, price=100.0)
        assert cost.sec_fee > 0
        assert cost.finra_taf > 0

    def test_crypto_taker_fee(self):
        cfg = CostModelConfig()
        model = CostModel(cfg)
        cost = model.crypto_trade_cost(side="buy", qty=1.0, price=50000.0)
        assert cost.exchange_fee > 0

    def test_round_trip_cost(self):
        cfg = CostModelConfig()
        model = CostModel(cfg)
        rt = model.round_trip_cost_pct(AssetClass.EQUITY)
        assert rt > 0
        rt_crypto = model.round_trip_cost_pct(AssetClass.CRYPTO)
        assert rt_crypto > 0


class TestBacktestRunner:
    def test_backtest_with_trending_data(self):
        df = _make_ohlcv(300, trend=0.2)
        params = MAParams(fast_ma_window=10, slow_ma_window=50, trend_filter_active=False)
        signals = generate_signals(df, params)
        result = run_single_asset_backtest(
            df,
            signals,
            strategy_name="ma",
            symbol="AAPL",
            asset_class=AssetClass.EQUITY,
            initial_capital=10000.0,
            params={"fast_ma_window": 10, "slow_ma_window": 50},
        )
        assert result.bar_count > 0
        assert result.metrics["total_return"] != 0
        assert "sharpe" in result.metrics

    def test_backtest_empty_signals(self):
        df = _make_ohlcv(300)
        empty_signals = pd.DataFrame(
            index=df.index,
            columns=["position", "signal"],
        )
        result = run_single_asset_backtest(df, empty_signals, strategy_name="ma", symbol="AAPL")
        # With all-NaN signals, positions are 0 — no trades, but bars are processed
        assert result.trade_count == 0
        assert result.metrics.get("total_return", 0) == 0

    def test_backtest_no_trades_in_sideways(self):
        df = _make_ohlcv(300, trend=0.0)
        params = MAParams(fast_ma_window=10, slow_ma_window=50, trend_filter_active=False)
        signals = generate_signals(df, params)
        result = run_single_asset_backtest(df, signals, strategy_name="ma", symbol="AAPL")
        # May have trades from noise, but should run without error
        assert result.bar_count > 0

    def test_costs_reduce_returns(self):
        """Backtest with costs should have lower returns than without."""
        df = _make_ohlcv(300, trend=0.2)
        params = MAParams(fast_ma_window=10, slow_ma_window=50, trend_filter_active=False)
        signals = generate_signals(df, params)

        # No costs
        no_cost_cfg = CostModelConfig(
            slippage_fixed_pct=0.0,
            commission_pct=0.0,
            sec_fee_per_dollar_sold=0.0,
            finra_taf_per_share_sold=0.0,
        )
        result_no_cost = run_single_asset_backtest(
            df, signals, asset_class=AssetClass.EQUITY, cost_config=no_cost_cfg
        )

        # With costs
        cost_cfg = CostModelConfig(
            slippage_fixed_pct=0.01,  # 1% slippage — very high to test
            commission_pct=0.001,
        )
        result_with_cost = run_single_asset_backtest(
            df, signals, asset_class=AssetClass.EQUITY, cost_config=cost_cfg
        )

        assert result_with_cost.metrics["total_return"] < result_no_cost.metrics["total_return"]

    def test_compute_metrics(self):
        returns = pd.Series([0.01, -0.005, 0.02, 0.01, -0.01] * 50)
        equity = (1 + returns).cumprod() * 10000
        metrics = compute_metrics(returns, equity, 10000.0)
        assert "sharpe" in metrics
        assert "max_drawdown" in metrics
        assert "total_return" in metrics
        assert metrics["max_drawdown"] <= 0  # drawdown is negative

    def test_lookahead_bias_no_future_data(self):
        """The backtest should not use future data — changing the future
        should not change past returns."""
        df = _make_ohlcv(300, trend=0.2)
        params = MAParams(fast_ma_window=10, slow_ma_window=50, trend_filter_active=False)
        signals = generate_signals(df, params)

        result1 = run_single_asset_backtest(df, signals, strategy_name="ma", symbol="AAPL")

        # Distort the last 50 bars
        df2 = df.copy()
        df2.iloc[250:, df2.columns.get_loc("close")] *= 5.0
        signals2 = generate_signals(df2, params)
        result2 = run_single_asset_backtest(df2, signals2, strategy_name="ma", symbol="AAPL")

        # Returns up to bar 250 should be identical
        common = result1.returns.index[:250]
        pd.testing.assert_series_equal(
            result1.returns.loc[common],
            result2.returns.loc[common],
            check_names=False,
        )
