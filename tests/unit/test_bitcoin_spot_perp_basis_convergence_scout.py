from __future__ import annotations

import copy

import pandas as pd
import pytest

from research.bitcoin_spot_perp_basis_convergence_scout import (
    build_daily_panel,
    evaluate_scout,
    load_spec,
)


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows_spot = []
    rows_perp = []
    for date in pd.date_range("2021-01-01", "2021-01-06", freq="D", tz="UTC"):
        rows_spot.extend(
            [
                {"open_time": date - pd.Timedelta(minutes=30), "open": 100.0, "close": 100.0},
                {"open_time": date + pd.Timedelta(minutes=30), "open": 100.0, "close": 100.0},
                {"open_time": date + pd.Timedelta(hours=7, minutes=30), "open": 101.0, "close": 101.0},
            ]
        )
        rows_perp.extend(
            [
                {"open_time": date - pd.Timedelta(minutes=30), "open": 101.0, "close": 101.0},
                {"open_time": date + pd.Timedelta(minutes=30), "open": 101.0, "close": 101.0},
                {"open_time": date + pd.Timedelta(hours=7, minutes=30), "open": 101.0, "close": 101.0},
            ]
        )
    funding = pd.DataFrame(
        {
            "calc_time": pd.date_range("2020-12-31", "2021-01-06", freq="8h", tz="UTC"),
            "last_funding_rate": 0.0,
        }
    )
    return pd.DataFrame(rows_spot), pd.DataFrame(rows_perp), funding


def test_panel_uses_two_delayed_legs_and_capital_weighting():
    spec = copy.deepcopy(load_spec())
    spec["signal"]["lookback_days"] = 2
    spec["signal"]["minimum_prior_days"] = 2
    spot, perp, funding = _inputs()

    panel = build_daily_panel(spot, perp, funding, spec, start="2021-01-01", end="2021-01-06")

    row = panel.iloc[-1]
    assert row["signal_timestamp"] < row["entry_timestamp"] < row["exit_timestamp"]
    assert row["spot_return"] == pytest.approx(0.01)
    assert row["perp_short_return"] == pytest.approx(0.0)
    assert row["capital_gross_return"] == pytest.approx(0.005)


def test_evaluator_charges_weighted_four_execution_cost_once():
    spec = copy.deepcopy(load_spec())
    spec["progression_gates"]["minimum_selected_days"] = 1
    spec["bootstrap"]["session_resamples"] = 100
    panel = pd.DataFrame(
        {
            "session_date": ["2021-01-01", "2021-01-02"],
            "signal_basis": [0.002, 0.001],
            "capital_gross_return": [0.004, 0.004],
            "basis_change": [-0.001, -0.001],
            "selected": [True, False],
            "timestamp_alignment_valid": [True, True],
        }
    )

    report = evaluate_scout(panel, spec)

    assert report["mean_gross_capital_bps"] == pytest.approx(40.0)
    assert report["mean_fee_only_capital_bps"] == pytest.approx(25.0)
    assert report["mean_conservative_capital_bps"] == pytest.approx(15.0)
    assert report["panel"].loc[1, "strategy_conservative_return"] == 0.0


def test_panel_skips_missing_two_leg_boundary_and_actual_funding_crossing():
    spec = copy.deepcopy(load_spec())
    spec["signal"]["lookback_days"] = 2
    spec["signal"]["minimum_prior_days"] = 2
    spot, perp, funding = _inputs()
    missing_entry = pd.Timestamp("2021-01-04 00:30:00", tz="UTC")
    spot = spot.loc[spot["open_time"] != missing_entry].copy()
    funding = pd.concat(
        [
            funding,
            pd.DataFrame(
                {
                    "calc_time": [pd.Timestamp("2021-01-05 07:30:00", tz="UTC")],
                    "last_funding_rate": [0.0001],
                }
            ),
        ],
        ignore_index=True,
    )

    panel = build_daily_panel(spot, perp, funding, spec, start="2021-01-01", end="2021-01-06")

    dates = set(panel["session_date"])
    assert "2021-01-04" not in dates
    assert "2021-01-05" not in dates
