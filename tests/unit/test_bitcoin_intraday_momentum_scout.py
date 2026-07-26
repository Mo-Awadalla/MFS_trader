from __future__ import annotations

import copy
import io

import numpy as np
import pandas as pd
import pytest

from data.binance_public_archive import month_keys, normalize_kline_csv
from research.bitcoin_intraday_momentum_scout import (
    build_session_panel,
    evaluate_scout,
    load_spec,
)


def _csv_rows(*, unit: str = "ms") -> bytes:
    opens = pd.date_range("2025-01-01", periods=3, freq="30min", tz="UTC")
    multiplier = 1_000 if unit == "ms" else 1_000_000
    rows = []
    for index, timestamp in enumerate(opens):
        open_epoch = int(timestamp.timestamp() * multiplier)
        close_epoch = int((timestamp + pd.Timedelta(minutes=30)).timestamp() * multiplier) - 1
        price = 100.0 + index
        rows.append(
            [open_epoch, price, price + 1, price - 1, price + 0.5, 10, close_epoch, 1000, 5, 4, 400, 0]
        )
    buffer = io.StringIO()
    pd.DataFrame(rows).to_csv(buffer, header=False, index=False)
    return buffer.getvalue().encode()


def _bars(start: str, end: str) -> pd.DataFrame:
    opens = pd.date_range(start, end, freq="30min", tz="UTC", inclusive="left")
    phase = np.arange(len(opens), dtype=float)
    prices = 100.0 * np.exp(0.0001 * phase)
    return pd.DataFrame(
        {
            "symbol": "BTCUSDT",
            "interval": "30m",
            "open_time": opens,
            "open": prices,
            "close": prices,
        }
    )


def test_month_keys_are_inclusive():
    assert month_keys("2020-12-15", "2021-02-01") == ["2020-12", "2021-01", "2021-02"]


@pytest.mark.parametrize("unit", ["ms", "us"])
def test_normalize_kline_csv_detects_timestamp_unit(unit: str):
    result = normalize_kline_csv(_csv_rows(unit=unit), symbol="BTCUSDT", interval="30m")

    assert len(result) == 3
    assert result.iloc[0]["open_time"] == pd.Timestamp("2025-01-01T00:00:00Z")
    assert result.iloc[-1]["close_time"] < pd.Timestamp("2025-01-01T01:30:00Z")


def test_normalize_kline_csv_accepts_documented_header_and_mixed_timestamp_units():
    content = _csv_rows(unit="ms").decode().splitlines()
    second = content[1].split(",")
    second[0] = str(int(second[0]) * 1_000)
    second[6] = str(int(second[6]) * 1_000)
    header = (
        "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
        "taker_buy_volume,taker_buy_quote_volume,ignore"
    )
    payload = ("\n".join([header, content[0], ",".join(second), content[2]]) + "\n").encode()

    result = normalize_kline_csv(payload, symbol="BTCUSDT", interval="30m")

    assert result["open_time"].tolist() == list(
        pd.date_range("2025-01-01", periods=3, freq="30min", tz="UTC")
    )


def test_session_panel_uses_new_york_dst_and_nonoverlapping_clocks():
    spec = load_spec()
    bars = _bars("2024-03-08", "2024-03-13")

    panel = build_session_panel(bars, spec)
    before = panel.loc[panel["session_date"] == "2024-03-09"].iloc[0]
    after = panel.loc[panel["session_date"] == "2024-03-11"].iloc[0]

    assert before["signal_timestamp"] == pd.Timestamp("2024-03-09T14:30:00Z")
    assert after["signal_timestamp"] == pd.Timestamp("2024-03-11T13:30:00Z")
    assert (panel["signal_timestamp"] < panel["entry_timestamp"]).all()
    assert (panel["entry_timestamp"] < panel["exit_timestamp"]).all()


def test_evaluator_applies_cost_once_only_when_selected():
    spec = copy.deepcopy(load_spec())
    spec["progression_gates"]["minimum_selected_sessions"] = 2
    spec["bootstrap"]["session_resamples"] = 100
    rows = []
    for index in range(4):
        selected = index < 2
        rows.append(
            {
                "session_date": f"2020-01-{index + 1:02d}",
                "signal_timestamp": pd.Timestamp("2020-01-01T14:30:00Z") + pd.Timedelta(days=index),
                "entry_timestamp": pd.Timestamp("2020-01-01T21:30:00Z") + pd.Timedelta(days=index),
                "exit_timestamp": pd.Timestamp("2020-01-01T22:00:00Z") + pd.Timedelta(days=index),
                "signal_return": 0.01 if selected else -0.01,
                "last_half_hour_return": 0.01,
                "selected": selected,
                "timestamp_alignment_valid": True,
            }
        )

    report = evaluate_scout(pd.DataFrame(rows), spec)
    panel = report["panel"]

    assert report["mean_selected_gross_bps"] == pytest.approx(100.0)
    assert report["mean_selected_fee_only_bps"] == pytest.approx(80.0)
    assert report["mean_selected_conservative_bps"] == pytest.approx(70.0)
    assert panel.loc[~panel["selected"], "strategy_conservative_return"].eq(0.0).all()


def test_evaluator_fails_when_costs_consume_positive_gross_edge():
    spec = copy.deepcopy(load_spec())
    spec["progression_gates"]["minimum_selected_sessions"] = 4
    spec["bootstrap"]["session_resamples"] = 100
    rows = []
    for index in range(4):
        rows.append(
            {
                "session_date": f"2020-02-{index + 1:02d}",
                "signal_timestamp": pd.Timestamp("2020-02-01T14:30:00Z") + pd.Timedelta(days=index),
                "entry_timestamp": pd.Timestamp("2020-02-01T21:30:00Z") + pd.Timedelta(days=index),
                "exit_timestamp": pd.Timestamp("2020-02-01T22:00:00Z") + pd.Timedelta(days=index),
                "signal_return": 0.01 + index * 0.001,
                "last_half_hour_return": 0.002,
                "selected": True,
                "timestamp_alignment_valid": True,
            }
        )

    report = evaluate_scout(pd.DataFrame(rows), spec)

    assert report["mean_selected_gross_bps"] == pytest.approx(20.0)
    assert report["mean_selected_conservative_bps"] == pytest.approx(-10.0)
    assert report["gates"]["positive_after_conservative_costs"] is False
    assert report["passed"] is False
