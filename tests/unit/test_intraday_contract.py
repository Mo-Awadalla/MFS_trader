from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from research.intraday_contract import Costs, Leg, benchmark_returns, evaluate, leg_returns


def leg(day="2023-01-03", exit_price=101.0):
    return Leg(
        day,
        "UPRO",
        day + "T09:30:00-05:00",
        day + "T09:31:00-05:00",
        day + "T15:30:00-05:00",
        1,
        100,
        100,
        exit_price,
        exit_price,
    )


def test_actual_leveraged_price_not_tripled_and_no_cost_double_count():
    r = leg_returns(leg(), Costs(0, 0, 0))
    assert r["net_return"] == pytest.approx(0.01)
    flat = leg_returns(leg(exit_price=100), Costs(5, 0, 0))
    assert flat["net_return"] * 10000 == pytest.approx(-9.99500249875)
    spread = leg_returns(replace(leg(exit_price=100), entry_ask=101, exit_bid=99), Costs(0, 0, 0))
    assert spread["net_return"] == pytest.approx(99 / 101 - 1)


@pytest.mark.parametrize(
    "change",
    [
        {"signal_available": "2023-01-03T09:31:00-05:00"},
        {"exit_time": "2023-01-04T09:31:00-05:00"},
        {"entry_time": "2023-01-03T09:31:00"},
        {"entry_bid": 102},
        {"exit_bid": float("nan")},
    ],
)
def test_temporal_and_price_failures_are_rejected(change):
    with pytest.raises(ValueError):
        leg_returns(replace(leg(), **change), Costs())


def test_missing_is_not_cash_and_exposure_cannot_exceed_capital():
    bm = pd.Series([0.0, 0.0], index=["2023-01-03", "2023-01-04"])
    r = evaluate([leg()], {"2023-01-03": "trade", "2023-01-04": "missing"}, bm)
    assert r["ending_cash"] is None and not r["preliminary_economic_pass"]
    with pytest.raises(ValueError, match="allocations"):
        evaluate([leg(), replace(leg(), symbol="SPXU")], {"2023-01-03": "trade"}, bm.iloc[:1])


def test_benchmark_includes_cash_days_and_adjustment_basis_is_required():
    f = pd.DataFrame(
        {"open": [100, 100, 100], "close": [100, 110, 121]},
        index=["2023-01-03", "2023-01-04", "2023-01-05"],
    )
    bm = benchmark_returns(f, list(f.index), basis="split_dividend_adjusted")
    assert (1 + bm).prod() == pytest.approx(1.21)
    with pytest.raises(ValueError):
        benchmark_returns(f, list(f.index), basis="raw")
    with pytest.raises(ValueError):
        benchmark_returns(f, ["2023-01-06"], basis="split_dividend_adjusted")


def test_sequential_full_capital_trades_compound_instead_of_sum():
    first = replace(leg(exit_price=110), exit_time="2023-01-03T10:00:00-05:00")
    second = replace(
        leg(exit_price=110),
        signal_available="2023-01-03T10:05:00-05:00",
        entry_time="2023-01-03T10:06:00-05:00",
    )
    r = evaluate(
        [first, second],
        {"2023-01-03": "trade"},
        pd.Series([0.0], index=["2023-01-03"]),
        costs=Costs(0, 0, 0),
    )
    assert r["ending_cash"] == pytest.approx(121)


@pytest.mark.parametrize(
    "costs",
    [
        Costs(float("nan"), 0, 0),
        Costs(1, float("nan"), 0),
        Costs(1, 0, float("inf")),
        Costs(1, 1, 0),
    ],
)
def test_invalid_cost_assumptions_are_rejected(costs):
    with pytest.raises(ValueError, match="cost"):
        leg_returns(leg(), costs)


def test_duplicate_benchmark_days_cannot_compound_twice():
    with pytest.raises(ValueError, match="benchmark calendar"):
        evaluate([leg()], {"2023-01-03": "trade"}, pd.Series([0.0, 0.0], index=["2023-01-03"] * 2))


def test_known_edge_and_seeded_random_null_are_distinguished():
    days = pd.bdate_range("2000-01-03", periods=1000).strftime("%Y-%m-%d").tolist()
    bm = pd.Series(0.0, index=days)
    decisions = dict.fromkeys(days, "trade")
    winner = evaluate([leg(d, 100.5) for d in days], decisions, bm, costs=Costs(2, 0, 0))
    assert winner["preliminary_economic_pass"]
    rng = np.random.default_rng(70926)
    moves = rng.choice([-0.004, 0.004], len(days))
    loser = evaluate(
        [leg(d, 100 * (1 + r)) for d, r in zip(days, moves, strict=True)],
        decisions,
        bm,
        costs=Costs(5, 0, 0),
    )
    assert not loser["preliminary_economic_pass"] and loser["ending_cash"] < 100
    scaled = evaluate(
        [leg(d, 100.5) for d in days], decisions, bm, costs=Costs(2, 0, 0), initial_cash=10000
    )
    assert scaled["ending_cash"] / 10000 == pytest.approx(winner["ending_cash"] / 100)
