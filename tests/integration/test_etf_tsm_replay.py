"""Tests for ETF TSM runtime replay."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config.loader import load_config
from engine.etf_tsm_replay import run_etf_tsm_engine_replay
from research.universes.etf_tactical_v1 import all_symbols


def test_etf_tsm_engine_replay_smoke(tmp_path: Path) -> None:
    config = load_config("config/research.toml")
    panel = _synthetic_etf_panel()

    result = run_etf_tsm_engine_replay(
        config=config,
        panel=panel,
        out_dir=tmp_path,
        initial_capital=10_000.0,
    )

    assert result.passed
    assert result.replay.bar_count == len(panel)
    assert result.replay.cycle_count == len(panel)
    assert result.replay.orders_submitted > 0
    assert result.replay.orders_filled > 0
    assert result.replay.orders_rejected == 0
    assert result.replay.orders_timed_out == 0
    assert result.operational_report.passed
    assert Path(result.report_path).exists()
    assert Path(result.json_path).exists()
    assert Path(result.operational_report_path).exists()


def _synthetic_etf_panel(n_days: int = 340) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-02", periods=n_days, tz="UTC")
    slopes = {
        "SPY": 0.0009,
        "QQQ": 0.0011,
        "IWM": 0.0007,
        "IEF": 0.0002,
        "GLD": 0.0004,
        "SHY": 0.00005,
        "DBC": -0.0002,
    }
    frames: list[pd.DataFrame] = []
    x = np.arange(n_days, dtype=float)
    seasonal = 0.01 * np.sin(np.linspace(0, 8 * np.pi, n_days))
    for i, symbol in enumerate(all_symbols()):
        base = 40.0 + i * 10.0
        close = base * (1.0 + slopes[symbol] * x + seasonal)
        open_ = close * 0.999
        high = close * 1.01
        low = close * 0.99
        volume = np.full(n_days, 2_000_000.0 + i * 100_000.0)
        frame = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
            index=idx,
        )
        frame.columns = pd.MultiIndex.from_product([[symbol], frame.columns], names=["symbol", "field"])
        frames.append(frame)
    return pd.concat(frames, axis=1).sort_index()
