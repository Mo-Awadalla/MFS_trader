from __future__ import annotations

import copy

import pandas as pd
import pytest

from research.sec_item_202_premarket_continuation_scout import (
    build_event_panel,
    evaluate_scout,
    load_spec,
    select_eligible_events,
)


def _event(
    *,
    symbol: str = "AAPL",
    accession: str = "0001",
    accepted: str = "2024-06-03T12:00:00Z",
    form: str = "8-K",
    items: str = "2.02,9.01",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "cik": "0000320193",
        "accession_number": accession,
        "acceptance_datetime": pd.Timestamp(accepted),
        "filing_date": pd.Timestamp(accepted).tz_convert("UTC").tz_localize(None).normalize(),
        "form": form,
        "items": items,
        "primary_document": "example.htm",
    }


def test_event_selector_enforces_exact_item_clock_partition_universe_and_deduplication() -> None:
    spec = load_spec()
    events = pd.DataFrame(
        [
            _event(accession="first", accepted="2024-06-03T13:25:00Z"),
            _event(accession="later", accepted="2024-06-03T13:25:00Z"),
            _event(symbol="MSFT", accession="too-late", accepted="2024-06-03T13:25:01Z"),
            _event(symbol="NVDA", accession="wrong-item", items="12.02,9.01"),
            _event(symbol="AMZN", accession="wrong-form", form="10-Q"),
            _event(symbol="NOTIN", accession="outside-universe"),
            _event(symbol="META", accession="wrong-partition", accepted="2022-06-03T12:00:00Z"),
        ]
    )

    selected = select_eligible_events(
        events,
        spec,
        partition="internal_validation",
        universe={"AAPL", "MSFT", "NVDA", "AMZN", "META"},
    )

    assert selected["symbol"].tolist() == ["AAPL"]
    assert selected["accession_number"].tolist() == ["first"]
    assert selected["session_date"].tolist() == ["2024-06-03"]
    assert selected.iloc[0]["acceptance_local"] == pd.Timestamp("2024-06-03T09:25:00-04:00")


def _bars_for_event(*, include_stock_exit: bool = True) -> pd.DataFrame:
    zone = "America/New_York"
    clocks = {
        "09:30:00": {"AAPL": (100.0, 100.0), "SPY": (100.0, 100.0)},
        "09:55:00": {"AAPL": (101.0, 102.0), "SPY": (100.5, 101.0)},
        "10:05:00": {"AAPL": (102.0, 102.5), "SPY": (101.0, 101.2)},
        "15:55:00": {"AAPL": (104.0, 104.0), "SPY": (101.5, 101.5)},
    }
    rows: list[dict[str, object]] = []
    for clock, values in clocks.items():
        timestamp = pd.Timestamp(f"2024-06-03 {clock}", tz=zone).tz_convert("UTC")
        for symbol, (open_price, close_price) in values.items():
            if clock == "15:55:00" and symbol == "AAPL" and not include_stock_exit:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": max(open_price, close_price),
                    "low": min(open_price, close_price),
                    "close": close_price,
                    "volume": 1000.0,
                }
            )
    return pd.DataFrame(rows)


def test_event_panel_uses_delayed_entry_market_residual_and_final_bar_open_exit() -> None:
    spec = load_spec()
    events = select_eligible_events(
        pd.DataFrame([_event()]),
        spec,
        partition="internal_validation",
        universe={"AAPL"},
    )

    panel = build_event_panel(events, _bars_for_event(), spec)
    row = panel.iloc[0]

    assert row["stock_signal_return"] == pytest.approx(0.02)
    assert row["benchmark_signal_return"] == pytest.approx(0.01)
    assert row["residual_signal_return"] == pytest.approx(0.01)
    assert row["stock_gross_return"] == pytest.approx(104.0 / 102.0 - 1.0)
    assert row["benchmark_holding_return"] == pytest.approx(101.5 / 101.0 - 1.0)
    assert row["selected"]
    assert row["complete_window"]
    assert row["timestamp_alignment_valid"]
    assert row["signal_known_timestamp"] < row["entry_timestamp"] < row["exit_timestamp"]
    assert row["entry_timestamp"] == pd.Timestamp("2024-06-03T14:05:00Z")


def test_event_panel_preserves_incomplete_event_with_diagnostic() -> None:
    spec = load_spec()
    events = select_eligible_events(
        pd.DataFrame([_event()]),
        spec,
        partition="internal_validation",
        universe={"AAPL"},
    )

    panel = build_event_panel(
        events,
        _bars_for_event(include_stock_exit=False),
        spec,
    )

    assert len(panel) == 1
    assert not panel.iloc[0]["complete_window"]
    assert panel.iloc[0]["missing_inputs"] == "stock_exit"
    assert not panel.iloc[0]["selected"]


def _evaluation_panel(residual_gross: float = 0.005) -> pd.DataFrame:
    rows = []
    sessions = ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    for index, session_date in enumerate(sessions):
        base = pd.Timestamp(f"{session_date} 10:00:00", tz="America/New_York").tz_convert("UTC")
        rows.append(
            {
                "session_date": session_date,
                "symbol": f"S{index}",
                "acceptance_datetime": base - pd.Timedelta(hours=2),
                "signal_known_timestamp": base,
                "entry_timestamp": base + pd.Timedelta(minutes=5),
                "exit_timestamp": base + pd.Timedelta(hours=5, minutes=55),
                "residual_signal_return": 0.01,
                "stock_gross_return": residual_gross + 0.002,
                "residual_gross_return": residual_gross,
                "selected": True,
                "complete_window": True,
                "missing_inputs": "",
                "timestamp_alignment_valid": True,
            }
        )
    return pd.DataFrame(rows)


def _easy_spec() -> dict[str, object]:
    spec = copy.deepcopy(load_spec())
    spec["partitions"]["internal_validation"]["minimum_selected_events"] = 4
    spec["partitions"]["internal_validation"]["minimum_selected_sessions"] = 4
    spec["progression_gates"]["minimum_mean_net_residual_bps"] = 1.0
    spec["progression_gates"]["minimum_profit_factor"] = 1.0
    spec["progression_gates"]["maximum_top_5pct_profitable_session_contribution"] = 1.0
    spec["progression_gates"]["maximum_single_issuer_absolute_pnl_share"] = 1.0
    spec["bootstrap"]["session_resamples"] = 100
    return spec


def test_evaluator_applies_cost_per_event_and_equal_weights_same_session() -> None:
    report = evaluate_scout(
        _evaluation_panel(),
        _easy_spec(),
        partition="internal_validation",
    )

    assert report["selected_events"] == 5
    assert report["selected_sessions"] == 4
    assert report["mean_residual_gross_bps"] == pytest.approx(50.0)
    assert report["mean_residual_fixed_net_bps"] == pytest.approx(40.0)
    assert report["mean_residual_stress_net_bps"] == pytest.approx(30.0)
    first_session = report["session_returns"].iloc[0]
    assert first_session["trade_count"] == 2
    assert first_session["residual_fixed_net_return"] == pytest.approx(0.004)
    assert report["passed"]


def test_evaluator_fails_when_costs_consume_the_residual_edge() -> None:
    spec = _easy_spec()
    spec["progression_gates"]["minimum_mean_net_residual_bps"] = 0.0
    report = evaluate_scout(
        _evaluation_panel(residual_gross=0.0005),
        spec,
        partition="internal_validation",
    )

    assert report["mean_residual_gross_bps"] == pytest.approx(5.0)
    assert report["mean_residual_fixed_net_bps"] == pytest.approx(-5.0)
    assert not report["gates"]["minimum_mean_net_residual"]
    assert not report["gates"]["positive_under_stress_costs"]
    assert not report["passed"]
