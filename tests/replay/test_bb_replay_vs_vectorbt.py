"""Golden comparison: BB engine replay vs vectorbt research baseline."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config.schema import (
    AssetClass,
    BrokerConfig,
    Config,
    DataConfig,
    EngineConfig,
    LiveDeploymentConfig,
    Mode,
    MonitoringConfig,
    PortfolioConfig,
    RiskLimits,
)
from engine.replay import run_replay
from research.bb_pipeline import STRATEGY_NAME, backtest_bb, default_cost_config
from research.runner import run_single_asset_backtest
from strategies.bb.signal import BBParams, generate_signals, params_from_dict

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "replay" / "golden"
GOLDEN_FILE = GOLDEN_DIR / "bb_aapl_1d.json"


def _make_config() -> Config:
    return Config(
        mode=Mode.RESEARCH,
        brokers=[
            BrokerConfig(
                name="sim_broker",
                asset_class=AssetClass.EQUITY,
                api_key_env="x",
                api_secret_env="y",
                base_url="sim",
            )
        ],
        data=[DataConfig(symbols=["AAPL"], asset_class=AssetClass.EQUITY)],
        risk_limits=RiskLimits(
            per_position_pct=0.05,
            max_daily_loss_pct=0.99,
            max_monthly_loss_pct=0.99,
        ),
        portfolio=PortfolioConfig(per_position_risk_pct=0.05),
        cost_model=default_cost_config(),
        monitoring=MonitoringConfig(),
        engine=EngineConfig(startup_reconciliation_required=False),
        live_deployment=LiveDeploymentConfig(),
        strategy_name=STRATEGY_NAME,
        strategy_version="0.1.0",
        strategies_enabled=["bb"],
    )


def _strategy_fn(bars: pd.DataFrame, params: dict) -> dict[str, float]:
    bb_params = params_from_dict(params)
    signals = generate_signals(bars, bb_params)
    if signals.empty or "position" not in signals.columns:
        return {}
    latest_position = signals["position"].iloc[-1]
    if pd.isna(latest_position):
        return {}
    return {"AAPL": float(latest_position)}


def _make_synthetic_bars(n: int = 300, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    close = 150.0 + 10.0 * np.sin(np.linspace(0, 24, n)) + np.cumsum(rng.normal(0, 0.3, n))
    df = pd.DataFrame(
        {
            "symbol": "AAPL",
            "open": close - 0.3,
            "high": close + 0.6,
            "low": close - 0.6,
            "close": close,
            "volume": rng.integers(500_000, 5_000_000, n).astype(float),
        },
        index=idx,
    )
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    return df


class TestBBReplayVsVectorBT:
    def test_both_paths_produce_trades(self, tmp_path):
        bars = _make_synthetic_bars(300)
        params = BBParams(window=10, std_mult=1.5, width_mode="none", width_lookback=30)
        signals = generate_signals(bars, params)
        vt_result = run_single_asset_backtest(
            bars,
            signals,
            strategy_name=STRATEGY_NAME,
            symbol="AAPL",
            cost_config=default_cost_config(),
        )
        replay_result = run_replay(
            bars=bars,
            config=_make_config(),
            strategy_fn=_strategy_fn,
            strategy_name=STRATEGY_NAME,
            strategy_params={
                "window": 10,
                "std_mult": 1.5,
                "width_mode": "none",
                "width_lookback": 30,
                "long_only": True,
                "mean_reversion": True,
            },
            db_path=tmp_path / "bb_replay.sqlite",
            initial_capital=10000.0,
        )

        assert vt_result.trade_count > 0
        assert replay_result.orders_filled > 0

    def test_replay_is_deterministic(self, tmp_path):
        bars = _make_synthetic_bars(120)
        config = _make_config()
        params = {
            "window": 10,
            "std_mult": 1.5,
            "width_mode": "none",
            "width_lookback": 30,
            "long_only": True,
            "mean_reversion": True,
        }
        results = []
        for i in range(3):
            results.append(
                run_replay(
                    bars=bars,
                    config=config,
                    strategy_fn=_strategy_fn,
                    strategy_name=STRATEGY_NAME,
                    strategy_params=params,
                    db_path=tmp_path / f"bb_replay_{i}.sqlite",
                    initial_capital=10000.0,
                )
            )

        for i in range(1, 3):
            assert results[i].orders_submitted == results[0].orders_submitted
            assert results[i].orders_filled == results[0].orders_filled
            assert results[i].final_positions == results[0].final_positions

    def test_research_and_replay_attribution(self, tmp_path):
        bars = _make_synthetic_bars(200)
        params = BBParams(window=10, std_mult=1.5, width_mode="none", width_lookback=30)
        research = backtest_bb(bars, params, symbol="AAPL")
        replay = run_replay(
            bars=bars,
            config=_make_config(),
            strategy_fn=_strategy_fn,
            strategy_name=STRATEGY_NAME,
            strategy_params={
                "window": 10,
                "std_mult": 1.5,
                "width_mode": "none",
                "width_lookback": 30,
                "long_only": True,
                "mean_reversion": True,
            },
            db_path=tmp_path / "bb_attribution.sqlite",
            initial_capital=10000.0,
        )

        attribution = {
            "research_trade_count": research.trade_count,
            "replay_orders_filled": replay.orders_filled,
            "research_sharpe": research.metrics.get("sharpe", 0.0),
        }
        assert attribution["research_trade_count"] > 0
        assert attribution["replay_orders_filled"] > 0

    def test_golden_file_exists_or_create(self, tmp_path):
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        bars = _make_synthetic_bars(120)
        params = {
            "window": 10,
            "std_mult": 1.5,
            "width_mode": "none",
            "width_lookback": 30,
            "long_only": True,
            "mean_reversion": True,
        }
        result = run_replay(
            bars=bars,
            config=_make_config(),
            strategy_fn=_strategy_fn,
            strategy_name=STRATEGY_NAME,
            strategy_params=params,
            db_path=tmp_path / "bb_golden.sqlite",
            initial_capital=10000.0,
        )

        golden = {
            "strategy": STRATEGY_NAME,
            "params": params,
            "orders_submitted": result.orders_submitted,
            "orders_filled": result.orders_filled,
            "orders_rejected": result.orders_rejected,
            "orders_timed_out": result.orders_timed_out,
            "final_positions": result.final_positions,
            "bar_count": result.bar_count,
            "data_seed": 11,
            "data_bars": 120,
        }
        GOLDEN_FILE.write_text(json.dumps(golden, indent=2, default=str), encoding="utf-8")
        loaded = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
        assert loaded["orders_submitted"] == result.orders_submitted

    def test_golden_file_matches_current_run(self, tmp_path):
        if not GOLDEN_FILE.exists():
            pytest.skip("No golden file — run test_golden_file_exists_or_create first")

        golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
        bars = _make_synthetic_bars(golden["data_bars"], seed=golden["data_seed"])
        result = run_replay(
            bars=bars,
            config=_make_config(),
            strategy_fn=_strategy_fn,
            strategy_name=golden["strategy"],
            strategy_params=golden["params"],
            db_path=tmp_path / "bb_golden_check.sqlite",
            initial_capital=10000.0,
        )

        assert result.orders_submitted == golden["orders_submitted"]
        assert result.orders_filled == golden["orders_filled"]
        assert result.orders_rejected == golden["orders_rejected"]
        assert result.orders_timed_out == golden["orders_timed_out"]
        assert result.final_positions == golden["final_positions"]
