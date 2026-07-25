"""Tests for the frozen public-data cross-asset carry/trend scout."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.cross_asset_carry_trend_report import run_scout
from research.cross_asset_carry_trend_scout import (
    INSTRUMENTS,
    CrossAssetCarryTrendParams,
    _scale_point_exposures,
    _transition_turnover,
    build_market_features,
    contract_month_gap,
    simulate_component,
)
from scripts.download_public_futures_curve_data import _daily_panel
from scripts.run_cross_asset_carry_trend_scout import format_report


def _panel(index: pd.DatetimeIndex, *, slope: float = 1.0) -> pd.DataFrame:
    increments = 1.0 + 0.2 * np.sin(np.arange(len(index)))
    adjusted = 100.0 + slope * np.cumsum(increments)
    return pd.DataFrame(
        {
            "CARRY": 99.0,
            "CARRY_CONTRACT": 20240600.0,
            "PRICE": 100.0,
            "PRICE_CONTRACT": 20240300.0,
            "FORWARD": 98.0,
            "FORWARD_CONTRACT": 20240900.0,
            "ADJUSTED": adjusted,
        },
        index=index,
    )


def test_public_data_normalization_uses_business_days_and_same_timestamp_carry(
    tmp_path,
) -> None:
    multiple_path = tmp_path / "multiple.csv"
    adjusted_path = tmp_path / "adjusted.csv"
    pd.DataFrame(
        {
            "DATETIME": [
                "2023-01-06 23:00:00",
                "2023-01-08 23:00:00",
                "2023-01-09 16:00:00",
                "2023-01-09 23:00:00",
            ],
            "CARRY": [99.0, 100.0, 101.0, np.nan],
            "CARRY_CONTRACT": [20230600, 20230600, 20230600, 20230600],
            "PRICE": [100.0, 101.0, 102.0, 999.0],
            "PRICE_CONTRACT": [20230300, 20230300, 20230300, 20230300],
            "FORWARD": [98.0, 99.0, 100.0, 101.0],
            "FORWARD_CONTRACT": [20230900] * 4,
        }
    ).to_csv(multiple_path, index=False)
    pd.DataFrame(
        {
            "DATETIME": [
                "2023-01-06 23:00:00",
                "2023-01-08 23:00:00",
                "2023-01-09 23:00:00",
            ],
            "price": [200.0, 201.0, 202.0],
        }
    ).to_csv(adjusted_path, index=False)

    daily = _daily_panel(multiple_path, adjusted_path, "2023-01-01")

    assert daily.index.dayofweek.isin(range(5)).all()
    assert daily.loc["2023-01-06", "PRICE"] == 101.0
    assert daily.loc["2023-01-09", "PRICE"] == 102.0
    assert daily.loc["2023-01-09", "CARRY"] == 101.0


def test_contract_month_gap_is_signed_and_rejects_invalid_identifiers() -> None:
    price = pd.Series([20240300, 20241200, 20240300, 20241300, 20240301, np.nan])
    carry = pd.Series([20240600, 20241100, 20240300, 20250300, 20240600, 20240600])

    result = contract_month_gap(price, carry)

    assert result.iloc[0] == 3.0
    assert result.iloc[1] == -1.0
    assert result.iloc[2:].isna().all()


def test_carry_sign_is_positive_in_backwardation_for_either_contract_direction() -> None:
    index = pd.date_range("2023-01-02", periods=260, freq="B")
    later_carry = _panel(index)
    earlier_carry = _panel(index)
    earlier_carry["PRICE"] = 100.0
    earlier_carry["CARRY"] = 101.0
    earlier_carry["PRICE_CONTRACT"] = 20240600.0
    earlier_carry["CARRY_CONTRACT"] = 20240500.0
    params = CrossAssetCarryTrendParams(trend_lookback_days=5, vol_lookback_days=5, vol_min_periods=3)

    later = build_market_features(later_carry, params)
    earlier = build_market_features(earlier_carry, params)

    assert later["carry_signal"].dropna().eq(1.0).all()
    assert earlier["carry_signal"].dropna().eq(1.0).all()


def test_missing_carry_never_falls_back_to_trend_only() -> None:
    index = pd.date_range("2023-01-02", periods=20, freq="B")
    frame = _panel(index)
    frame.loc[index[-1], ["CARRY", "CARRY_CONTRACT"]] = np.nan
    params = CrossAssetCarryTrendParams(trend_lookback_days=5, vol_lookback_days=5, vol_min_periods=3)

    features = build_market_features(frame, params)

    assert features.loc[index[-1], "trend_signal"] == 1.0
    assert pd.isna(features.loc[index[-1], "combined_signal"])


def test_missing_adjusted_session_does_not_discard_catch_up_pnl() -> None:
    index = pd.date_range("2023-01-02", periods=10, freq="B")
    frame = _panel(index)
    expected_change = frame.loc[index[6], "ADJUSTED"] - frame.loc[index[4], "ADJUSTED"]
    frame.loc[index[5], "ADJUSTED"] = np.nan
    params = CrossAssetCarryTrendParams(
        trend_lookback_days=3,
        vol_lookback_days=3,
        vol_min_periods=2,
    )

    features = build_market_features(frame, params)

    assert index[5] not in features.index
    assert features.loc[index[6], "point_change"] == expected_change


def test_point_exposure_scaling_enforces_market_and_gross_notional_caps() -> None:
    signals = pd.Series({"A": 1.0, "B": -1.0})
    volatility = pd.Series({"A": 0.1, "B": 0.1})
    prices = pd.Series({"A": 100.0, "B": 100.0})

    exposure = _scale_point_exposures(
        signals,
        volatility,
        prices,
        target_volatility=1.0,
        max_market_notional=0.35,
        max_gross_notional=0.50,
    )
    notional = exposure.mul(prices).abs()

    assert float(notional.max()) <= 0.350001
    assert float(notional.sum()) <= 0.500001


def test_roll_turnover_charges_close_and_open() -> None:
    old_exposure = pd.Series({"A": 0.01})
    new_exposure = pd.Series({"A": 0.01})
    old_price = pd.Series({"A": 100.0})
    new_price = pd.Series({"A": 102.0})

    normal = _transition_turnover(
        old_exposure,
        new_exposure,
        old_price,
        new_price,
        pd.Series({"A": False}),
    )
    rolled = _transition_turnover(
        old_exposure,
        new_exposure,
        old_price,
        new_price,
        pd.Series({"A": True}),
    )

    assert normal == 0.0
    assert rolled == 2.02


def test_roll_count_uses_position_entering_a_simultaneous_exit() -> None:
    index = pd.date_range("2023-01-02", "2023-03-31", freq="B")
    panels = {f"M{i}": _panel(index) for i in range(8)}
    for frame in panels.values():
        frame.loc["2023-02-01":"2023-02-28", "CARRY"] = 101.0
        frame.loc[pd.Timestamp("2023-03-02") :, "PRICE_CONTRACT"] = 20240600.0
        frame.loc[pd.Timestamp("2023-03-02") :, "CARRY_CONTRACT"] = 20240900.0
    params = CrossAssetCarryTrendParams(
        trend_lookback_days=3,
        vol_lookback_days=5,
        vol_min_periods=3,
        min_active_markets=8,
        execution_lag_sessions=2,
    )

    path = simulate_component(panels, params, component="combined", cost_bps=0.0)

    assert path.point_exposure.loc["2023-03-02"].abs().sum() == 0.0
    assert path.roll_count == 8


def test_simulation_waits_two_sessions_and_costs_reduce_returns() -> None:
    index = pd.date_range("2023-01-02", "2023-03-31", freq="B")
    panels = {f"M{i}": _panel(index) for i in range(8)}
    params = CrossAssetCarryTrendParams(
        trend_lookback_days=3,
        vol_lookback_days=5,
        vol_min_periods=3,
        min_active_markets=8,
        execution_lag_sessions=2,
    )

    gross = simulate_component(panels, params, component="combined", cost_bps=0.0)
    net = simulate_component(panels, params, component="combined", cost_bps=5.0)
    january_end = pd.Timestamp("2023-01-31")
    expected_first_position_date = index[index.get_loc(january_end) + 2]

    assert gross.point_exposure.loc[: index[index.get_loc(january_end) + 1]].abs().sum().sum() == 0.0
    assert gross.point_exposure.loc[expected_first_position_date].abs().sum() > 0.0
    assert float(net.returns.sum()) < float(gross.returns.sum())
    assert float(net.costs.sum()) > 0.0


def test_zero_combined_signals_still_count_as_eligible_markets() -> None:
    index = pd.date_range("2023-01-02", "2023-03-31", freq="B")
    panels = {
        **{f"UP{i}": _panel(index, slope=1.0) for i in range(4)},
        **{f"FLAT{i}": _panel(index, slope=-1.0) for i in range(4)},
    }
    params = CrossAssetCarryTrendParams(
        trend_lookback_days=3,
        vol_lookback_days=5,
        vol_min_periods=3,
        min_active_markets=8,
        execution_lag_sessions=2,
    )

    path = simulate_component(panels, params, component="combined", cost_bps=0.0)

    assert path.point_exposure.filter(like="UP").abs().sum().sum() > 0.0
    assert path.point_exposure.filter(like="FLAT").abs().sum().sum() == 0.0


def test_missing_known_business_month_end_skips_rebalance() -> None:
    index = pd.date_range("2023-01-02", "2023-03-31", freq="B")
    panels = {f"M{i}": _panel(index).drop(pd.Timestamp("2023-01-31")) for i in range(8)}
    params = CrossAssetCarryTrendParams(
        trend_lookback_days=3,
        vol_lookback_days=5,
        vol_min_periods=3,
        min_active_markets=8,
        execution_lag_sessions=2,
    )

    path = simulate_component(panels, params, component="combined", cost_bps=0.0)

    assert path.point_exposure.loc[:"2023-03-01"].abs().sum().sum() == 0.0
    assert path.point_exposure.loc["2023-03-02":].abs().sum().sum() > 0.0


def test_simulation_keeps_pnl_when_another_market_is_closed() -> None:
    index = pd.date_range("2023-01-02", "2023-03-31", freq="B")
    missing_date = pd.Timestamp("2023-03-15")
    panels = {f"M{i}": _panel(index) for i in range(8)}
    panels["M0"] = panels["M0"].drop(missing_date)
    params = CrossAssetCarryTrendParams(
        trend_lookback_days=3,
        vol_lookback_days=5,
        vol_min_periods=3,
        min_active_markets=8,
        execution_lag_sessions=2,
    )

    path = simulate_component(panels, params, component="combined", cost_bps=0.0)

    assert missing_date in path.returns.index
    assert path.market_gross_returns.loc[missing_date, "M1"] != 0.0


def test_scout_reports_every_frozen_gate_and_diagnostic() -> None:
    index = pd.date_range("2022-01-03", "2022-06-30", freq="B")
    panels = {market: _panel(index) for market in INSTRUMENTS}
    panels["SP500"] = panels["SP500"].drop(index[10])
    params = CrossAssetCarryTrendParams(
        trend_lookback_days=3,
        vol_lookback_days=5,
        vol_min_periods=3,
        min_active_markets=8,
        execution_lag_sessions=2,
    )
    spy = pd.Series(100.0 + np.arange(len(index)), index=index)

    report = run_scout(panels, spy, params)

    assert set(report.component_metrics) == {"carry", "trend", "combined"}
    assert set(report.subperiod_metrics) == {"2010_2016", "2017_2024"}
    assert set(report.leave_one_asset_class_out) == {
        "equity_index",
        "rates",
        "fx",
        "energy",
        "metals",
        "agriculture",
    }
    assert set(report.cost_sensitivity_bps) == {"0.0", "1.0", "2.0", "5.0"}
    assert len(report.gates) == 13
    assert report.scout_passed == all(report.gates.values())
    assert set(report.asset_class_diagnostics["gross_pnl"]) == {
        "equity_index",
        "rates",
        "fx",
        "energy",
        "metals",
        "agriculture",
    }
    rendered = format_report(report)
    assert "Ann. arithmetic" in rendered
    assert "Sortino" in rendered
    assert "## Asset-class contributions" in rendered
    expected_bars = report.component_metrics["combined"]["default_net"]["total_bars"]
    assert all(
        metrics["total_bars"] == expected_bars
        for metrics in report.leave_one_asset_class_out.values()
    )
