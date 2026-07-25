from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from research.bitcoin_confirmed_short_squeeze_continuation_scout import (
    _trade_path,
    apply_analogue_model,
    build_decision_panel,
    load_spec,
    simulate_trades,
)


def _inputs(days: int = 130) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    start = pd.Timestamp("2021-01-01", tz="UTC")
    end = start + pd.Timedelta(days=days)
    opens = pd.date_range(
        start - pd.Timedelta(hours=7),
        end + pd.Timedelta(hours=7),
        freq="5min",
        inclusive="left",
        tz="UTC",
    )
    phase = np.arange(len(opens), dtype=float)
    price = 100.0 * np.exp(0.00001 * phase + 0.0003 * np.sin(phase / 17.0))
    spot = pd.DataFrame(
        {
            "symbol": "BTCUSDT",
            "interval": "5m",
            "open_time": opens,
            "open": price,
            "high": price * 1.001,
            "low": price * 0.999,
            "close": price * 1.0001,
            "volume": 10.0,
            "taker_buy_base_volume": 5.5,
        }
    )
    metrics = pd.DataFrame(
        {
            "create_time": opens,
            "sum_open_interest": 1000.0 * np.exp(0.000001 * phase),
            "count_long_short_ratio": 1.0 + 0.05 * np.sin(phase / 31.0),
        }
    )
    funding_times = pd.date_range(start - pd.Timedelta(days=2), end, freq="8h", tz="UTC")
    funding = pd.DataFrame(
        {
            "calc_time": funding_times,
            "last_funding_rate": 0.0001
            + 0.00001 * np.sin(np.arange(len(funding_times), dtype=float)),
        }
    )
    premium_opens = pd.date_range(start - pd.Timedelta(hours=5), end, freq="30min", tz="UTC")
    premium = pd.DataFrame(
        {
            "open_time": premium_opens,
            "close": 0.0001 + 0.00001 * np.cos(np.arange(len(premium_opens), dtype=float)),
        }
    )
    return spot, metrics, funding, premium


def _small_spec() -> dict:
    spec = copy.deepcopy(load_spec())
    spec["rolling"]["lookback_calendar_days"] = 30
    spec["rolling"]["minimum_prior_decisions"] = 20
    spec["analogue_model"]["neighbors"] = 5
    spec["analogue_model"]["bootstrap_resamples"] = 100
    return spec


def test_decision_panel_uses_only_observations_available_at_decision():
    spec = _small_spec()
    spot, metrics, funding, premium = _inputs()

    panel = build_decision_panel(
        spot,
        metrics,
        funding,
        premium,
        spec,
        start="2021-01-02",
        end="2021-04-30",
    )

    assert (panel["latest_metrics_available_at"] <= panel["decision_timestamp"]).all()
    assert (panel["latest_funding_available_at"] <= panel["decision_timestamp"]).all()
    assert (panel["latest_premium_available_at"] <= panel["decision_timestamp"]).all()
    assert (panel["decision_timestamp"] < panel["entry_timestamp"]).all()
    assert (panel["entry_timestamp"] < panel["scheduled_exit_timestamp"]).all()


def test_metrics_publication_lag_prevents_same_timestamp_use():
    spec = _small_spec()
    spot, metrics, funding, premium = _inputs()
    panel = build_decision_panel(
        spot,
        metrics,
        funding,
        premium,
        spec,
        start="2021-01-02",
        end="2021-01-02",
    )
    first = panel.iloc[0]

    assert first["decision_timestamp"] == pd.Timestamp("2021-01-02 00:25:00", tz="UTC")
    assert first["latest_metrics_available_at"] == first["decision_timestamp"]
    assert (
        metrics.loc[metrics["create_time"] == pd.Timestamp("2021-01-02 00:20:00", tz="UTC")].shape[
            0
        ]
        == 1
    )


def test_rolling_threshold_is_strictly_prior():
    spec = _small_spec()
    spot, metrics, funding, premium = _inputs()
    panel = build_decision_panel(
        spot,
        metrics,
        funding,
        premium,
        spec,
        start="2021-01-02",
        end="2021-04-30",
    )
    ready_index = int(
        panel.index[panel["rolling_observations"] >= spec["rolling"]["minimum_prior_decisions"]][0]
    )
    cutoff = panel.loc[ready_index, "decision_timestamp"]
    start = cutoff - pd.Timedelta(days=spec["rolling"]["lookback_calendar_days"])
    prior = panel.loc[
        (panel["decision_timestamp"] >= start) & (panel["decision_timestamp"] < cutoff),
        "funding_crowding",
    ]

    assert panel.loc[ready_index, "funding_crowding_threshold"] == pytest.approx(
        prior.quantile(spec["stage_1"]["crowding_quantile"])
    )


def _analogue_panel() -> pd.DataFrame:
    times = pd.date_range("2021-01-01", periods=75, freq="12h", tz="UTC")
    rows = []
    for index, timestamp in enumerate(times):
        value = 0.1 + index * 0.001
        rows.append(
            {
                "decision_timestamp": timestamp,
                "stage_2": index == len(times) - 1,
                "short_crowding_score": value,
                "oi_buildup_6h": value * 1.1,
                "price_resistance": value * 1.2,
                "oi_contraction_1h": value * 1.3,
                "taker_buy_imbalance": value * 1.4,
                "volatility_expansion": value * 1.5,
                "forward_gross_return_6h": 0.02,
            }
        )
    return pd.DataFrame(rows)


def test_analogue_model_embargoes_preceding_24_hours():
    spec = _small_spec()
    spec["rolling"]["lookback_calendar_days"] = 180
    spec["rolling"]["minimum_prior_decisions"] = 20
    spec["analogue_model"]["minimum_mean_gross_bps"] = -1
    spec["analogue_model"]["minimum_lower_bound_gross_bps"] = -1
    spec["analogue_model"]["minimum_probability_above_cost"] = 0
    spec["analogue_model"]["maximum_largest_positive_outcome_contribution"] = 1
    panel = _analogue_panel()
    result = apply_analogue_model(panel, spec)
    current = result.iloc[-1]

    assert current["analogue_count"] == 5
    assert bool(current["analogue_pass"])
    # The closest states are the most recent, but the 12-hour state is embargoed.
    assert current["analogue_mean_distance"] > 0


def _candidate_row() -> pd.Series:
    return pd.Series(
        {
            "decision_timestamp": pd.Timestamp("2021-01-01 00:25:00", tz="UTC"),
            "decision_clock": "00:25",
            "entry_timestamp": pd.Timestamp("2021-01-01 00:30:00", tz="UTC"),
            "scheduled_exit_timestamp": pd.Timestamp("2021-01-01 06:30:00", tz="UTC"),
            "atr_1h": 1.0,
            "analogue_pass": True,
        }
    )


def _trade_bars(*, stop: bool) -> pd.DataFrame:
    opens = pd.date_range("2021-01-01 00:30:00", "2021-01-01 06:30:00", freq="5min", tz="UTC")
    low = np.full(len(opens), 100.0)
    if stop:
        low[3] = 98.0
    return pd.DataFrame(
        {
            "open_time": opens,
            "open": 100.0,
            "high": 102.0,
            "low": low,
            "close": 100.0,
        }
    )


def test_execution_applies_stop_cost_and_risk_sizing():
    spec = _small_spec()
    trade = _trade_path(
        _trade_bars(stop=True),
        _candidate_row(),
        spec,
        round_trip_cost_bps=30,
    )

    assert trade is not None
    assert trade["exit_reason"] == "stop"
    assert trade["stop_price"] == pytest.approx(98.75)
    assert trade["notional_fraction"] == pytest.approx(0.28)
    assert trade["gross_instrument_return"] == pytest.approx(-0.0125)
    assert trade["net_instrument_return"] < trade["gross_instrument_return"]


def test_execution_caps_notional_and_uses_next_bar_open():
    spec = _small_spec()
    row = _candidate_row()
    row["atr_1h"] = 0.1
    bars = _trade_bars(stop=False)
    bars.loc[bars["open_time"] == row["entry_timestamp"], "open"] = 101.0
    trade = _trade_path(bars, row, spec, round_trip_cost_bps=30)

    assert trade is not None
    assert trade["entry_open"] == pytest.approx(101.0)
    assert trade["notional_fraction"] == pytest.approx(0.5)


def test_rolling_24_hour_entry_throttle():
    spec = _small_spec()
    rows = []
    for hours in (0, 12, 24):
        row = _candidate_row().copy()
        row["decision_timestamp"] += pd.Timedelta(hours=hours)
        row["entry_timestamp"] += pd.Timedelta(hours=hours)
        row["scheduled_exit_timestamp"] += pd.Timedelta(hours=hours)
        rows.append(row)
    panel = pd.DataFrame(rows)
    opens = pd.date_range("2021-01-01 00:30:00", "2021-01-02 06:30:00", freq="5min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open_time": opens,
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.0,
        }
    )

    trades = simulate_trades(panel, bars, spec)

    assert len(trades) == 2
    assert list(trades["entry_timestamp"]) == [
        pd.Timestamp("2021-01-01 00:30:00", tz="UTC"),
        pd.Timestamp("2021-01-02 00:30:00", tz="UTC"),
    ]
