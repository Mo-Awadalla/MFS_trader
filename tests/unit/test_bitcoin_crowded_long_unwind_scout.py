from __future__ import annotations

import copy

import pandas as pd
import pytest

from research.bitcoin_crowded_long_unwind_scout import (
    build_daily_panel,
    evaluate_scout,
    load_spec,
)


def _synthetic_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2021-01-01", "2021-01-05", freq="D", tz="UTC")
    perp_rows = []
    metric_rows = []
    premium_rows = []
    for index, date in enumerate(dates):
        perp_rows.extend(
            [
                {"open_time": date + pd.Timedelta(minutes=30), "open": 100.0},
                {"open_time": date + pd.Timedelta(hours=7, minutes=30), "open": 99.0},
            ]
        )
        metric_rows.extend(
            [
                {
                    "create_time": date - pd.Timedelta(hours=7, minutes=55),
                    "sum_open_interest": 100.0 + index,
                },
                {
                    "create_time": date + pd.Timedelta(minutes=5),
                    "sum_open_interest": 101.0 + index,
                },
            ]
        )
        premium_rows.append(
            {
                "open_time": date - pd.Timedelta(minutes=30),
                "close": 0.001 + index * 0.0001,
            }
        )
    funding_times = pd.date_range("2020-12-30", "2021-01-05", freq="8h", tz="UTC")
    funding_rates = [0.0001] * len(funding_times)
    funding_rates[funding_times.get_loc(pd.Timestamp("2021-01-03", tz="UTC"))] = 0.01
    funding = pd.DataFrame(
        {"calc_time": funding_times, "last_funding_rate": funding_rates}
    )
    return (
        pd.DataFrame(perp_rows),
        funding,
        pd.DataFrame(metric_rows).sort_values("create_time").reset_index(drop=True),
        pd.DataFrame(premium_rows),
    )


def test_daily_panel_uses_strict_prior_threshold_and_delayed_execution():
    spec = copy.deepcopy(load_spec())
    spec["primary_signal"]["funding_lookback_settlements"] = 3
    spec["primary_signal"]["minimum_prior_funding_observations"] = 3
    spec["predeclared_controls"]["basis_only"] = "test override"
    perp, funding, metrics, premium = _synthetic_inputs()

    panel = build_daily_panel(
        perp,
        funding,
        metrics,
        premium,
        spec,
        start="2021-01-01",
        end="2021-01-05",
    )

    selected = panel.loc[panel["session_date"] == "2021-01-03"].iloc[0]
    assert selected["funding_threshold"] == pytest.approx(0.0001)
    assert bool(selected["funding_extreme"])
    assert bool(selected["oi_expanding"])
    assert bool(selected["selected"])
    assert selected["funding_timestamp"] <= selected["cutoff_timestamp"]
    assert selected["cutoff_timestamp"] < selected["entry_timestamp"]
    assert selected["entry_timestamp"] < selected["exit_timestamp"]
    assert selected["short_return"] == pytest.approx(0.01)


def test_daily_panel_rejects_stale_point_in_time_oi():
    spec = copy.deepcopy(load_spec())
    spec["primary_signal"]["funding_lookback_settlements"] = 3
    spec["primary_signal"]["minimum_prior_funding_observations"] = 3
    perp, funding, metrics, premium = _synthetic_inputs()
    metrics = metrics.loc[
        metrics["create_time"] != pd.Timestamp("2021-01-03 00:05:00", tz="UTC")
    ]

    panel = build_daily_panel(
        perp,
        funding,
        metrics,
        premium,
        spec,
        start="2021-01-01",
        end="2021-01-05",
    )

    assert "2021-01-03" not in set(panel["session_date"])


def test_daily_panel_rejects_actual_funding_event_at_exit_boundary():
    spec = copy.deepcopy(load_spec())
    spec["primary_signal"]["funding_lookback_settlements"] = 3
    spec["primary_signal"]["minimum_prior_funding_observations"] = 3
    perp, funding, metrics, premium = _synthetic_inputs()
    funding = pd.concat(
        [
            funding,
            pd.DataFrame(
                {
                    "calc_time": [pd.Timestamp("2021-01-03 07:30:00", tz="UTC")],
                    "last_funding_rate": [0.0001],
                }
            ),
        ],
        ignore_index=True,
    )

    panel = build_daily_panel(
        perp,
        funding,
        metrics,
        premium,
        spec,
        start="2021-01-01",
        end="2021-01-05",
    )

    assert "2021-01-03" not in set(panel["session_date"])


def test_evaluator_applies_short_costs_only_on_primary_trigger():
    spec = copy.deepcopy(load_spec())
    spec["progression_gates"]["minimum_selected_days"] = 1
    spec["bootstrap"]["session_resamples"] = 100
    rows = []
    for index, selected in enumerate((True, False, True, False)):
        rows.append(
            {
                "session_date": f"2021-02-{index + 1:02d}",
                "short_return": 0.003,
                "selected": selected,
                "funding_extreme": selected,
                "oi_expanding": True,
                "basis_extreme": False,
                "timestamp_alignment_valid": True,
            }
        )

    report = evaluate_scout(pd.DataFrame(rows), spec)
    panel = report["panel"]

    assert report["mean_selected_short_gross_bps"] == pytest.approx(30.0)
    assert report["mean_selected_fee_only_bps"] == pytest.approx(20.0)
    assert report["mean_selected_conservative_bps"] == pytest.approx(10.0)
    assert panel.loc[~panel["selected"], "strategy_conservative_return"].eq(0.0).all()
