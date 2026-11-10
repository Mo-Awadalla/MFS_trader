"""Guard the experiment's information boundary and missing-data accounting."""

import math

import numpy as np
import pandas as pd
import pytest

from research.intraday_contract import Leg
from research_scout.v98_backtest_20260907 import (
    build_legs,
    event_features,
    fit_predict_pair,
    independent_cash,
    time_at,
)
from research_scout.v98_earnings_answers_20260907 import NY, calendar, first_session, read
from research_scout.v98_transcript_roles_20260907 import explicit_management_role, extract_page


def synthetic_bars():
    schedule = calendar().schedule
    day = "2021-01-05"
    previous = schedule.loc["2021-01-04", "close"] - pd.Timedelta(minutes=5)
    rows = [{"symbol": "AAPL", "timestamp": previous, "open": 99, "close": 100}]
    for symbol in ["AAPL", "SPY"]:
        for i, timestamp in enumerate(pd.date_range(time_at(day, "09:30"), periods=6, freq="5min")):
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": timestamp.tz_convert("UTC"),
                    "open": 101 + i,
                    "close": 101.5 + i,
                }
            )
    return day, pd.DataFrame(rows).set_index(["symbol", "timestamp"]).sort_index(), schedule


def test_features_stop_at_completed_half_hour_and_include_prior_close():
    day, bars, schedule = synthetic_bars()
    before = event_features(day, "AAPL", bars, schedule)
    future = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "timestamp": time_at(day, "10:05").tz_convert("UTC"),
                "open": 10000,
                "close": 1,
            }
        ]
    ).set_index(["symbol", "timestamp"])
    after = event_features(day, "AAPL", pd.concat([bars, future]).sort_index(), schedule)
    assert before == after
    assert before["stock_gap"] == pytest.approx(math.log(101 / 100))
    assert before["stock_first30"] == pytest.approx(math.log(106.5 / 101))
    assert pd.Timestamp(before["signal_available"]) == time_at(day, "10:01")


def test_missing_required_market_bar_is_explicit():
    day, bars, schedule = synthetic_bars()
    bars = bars.drop(index=("SPY", time_at(day, "09:45")))
    result = event_features(day, "AAPL", bars, schedule)
    assert result["feature_error"] == "missing_required_bars"
    assert len(result["missing_feature_bars"]) == 1


def synthetic_training():
    return pd.DataFrame(
        [
            {
                "day": "2020-12-15",
                "key": f"past{i}",
                "symbol": f"S{i % 30}",
                "prepared_text": "sales and demand revenue growth "
                + ("rising" if i % 2 else "falling"),
                "qa_text": "question answer management " + ("uncertain" if i % 3 else "confident"),
                "stock_gap": (i % 7) * 0.001,
                "stock_first30": (i % 5) * 0.001,
                "spy_first30": (i % 3) * 0.001,
                "target": (i % 3 - 1) * 0.005,
            }
            for i in range(300)
        ]
    )


def test_heldout_labels_and_vocabulary_never_enter_fit():
    train = synthetic_training()
    test = train.iloc[:2].copy()
    test["day"] = "2021-01-05"
    test["prepared_text"] += " futureonlytoken"
    test["qa_text"] += " futureonlyanswer"
    spec = read("specification.json")
    base1, aug1, audit = fit_predict_pair(train, test, spec)
    test["target"] = 9999
    base2, aug2, _ = fit_predict_pair(train, test, spec)
    assert np.array_equal(base1, base2)
    assert np.array_equal(aug1, aug2)
    assert "futureonlytoken" not in audit["prepared_vocabulary"]
    assert "futureonlyanswer" not in audit["qa_vocabulary"]
    assert audit["training_last_day"] < audit["test_first_day"]
    train.loc[0, "day"] = "2021-01-01"
    with pytest.raises(ValueError, match="Training reaches"):
        fit_predict_pair(train, test, spec)


def test_unknown_signal_blocks_day_instead_of_silently_becoming_cash():
    benchmark = pd.Series([0.01, 0.02], index=["2021-01-05", "2021-01-06"])
    events = [
        {
            "key": "bad",
            "day": "2021-01-05",
            "symbol": "AAPL",
            "feature_error": "missing_required_bars",
        }
    ]
    legs, decisions, missing = build_legs(events, [], benchmark)
    assert not legs
    assert decisions == {"2021-01-05": "missing", "2021-01-06": "cash"}
    assert missing["2021-01-05"][0]["key"] == "bad"


def test_first_full_session_respects_strict_buffer_and_early_close():
    schedule = calendar().schedule
    opens = pd.DatetimeIndex(
        schedule.loc[schedule.close.dt.tz_convert(NY).dt.strftime("%H:%M") == "16:00", "open"]
    )
    assert first_session("2021-01-05T08:59:00-05:00", opens) == "2021-01-05"
    assert first_session("2021-01-05T09:00:00-05:00", opens) == "2021-01-06"
    assert first_session("2021-11-25T16:00:00-05:00", opens) == "2021-11-29"


def test_independent_cash_uses_funded_basket_and_missing_blocks_equity():
    day = "2021-01-05"
    common = {
        "day": day,
        "signal_available": time_at(day, "10:01").isoformat(),
        "entry_time": time_at(day, "10:05").isoformat(),
        "exit_time": time_at(day, "15:55").isoformat(),
        "weight": 0.5,
        "entry_bid": 100,
        "entry_ask": 100,
        "price_basis": "bar_reference",
    }
    legs = [
        Leg(symbol="AAPL", exit_bid=110, exit_ask=110, **common),
        Leg(symbol="MSFT", exit_bid=90, exit_ask=90, **common),
    ]
    assert independent_cash(legs, {day: "trade"}, 0) == pytest.approx(100)
    assert independent_cash(legs, {day: "trade"}, 5) == pytest.approx(100 * 0.9995 / 1.0005)
    assert independent_cash(legs, {day: "missing"}, 5) is None


def test_non_analyst_is_not_automatically_management():
    for role in [
        "Vining Sparks",
        "Bloomberg -- Aerospace Reporter",
        "Equity Research",
        "Chief Equity Research Analyst",
        "Autonomous Research -- Partner",
        "Wells Fargo -- Analsyt",
        "UBS -- Managing Director",
        "M.D.",
    ]:
        assert not explicit_management_role(role)
    for role in [
        "Chief Executive Officer",
        "Executive Vice President and Chief Financial Officer",
        "SVP of IR",
        "General Counsel",
        "Head of Sales",
    ]:
        assert explicit_management_role(role)
    import json

    metadata = json.dumps(
        {
            "@type": "NewsArticle",
            "datePublished": "2020-01-01T20:00:00Z",
            "dateModified": "2020-01-01T20:00:00Z",
        }
    )
    speech = "Business demand improved. " * 180
    html = f"""<script type="application/ld+json">{metadata}</script>
    <div id="article-body-transcript"><h2>Prepared Remarks:</h2>
    <p><strong>Alex Exec</strong> -- Chief Executive Officer</p><p>{speech}</p>
    <h2>Questions and Answers:</h2>
    <p><strong>Robin Analyst</strong> -- Analyst</p><p>A question.</p>
    <p><strong>Alex Exec</strong> -- Chief Executive Officer</p><p>{speech}</p>
    <p><strong>Outside Person</strong> -- Equity Research</p><p>OUTSIDE_QUESTION</p>
    <h2>Call participants:</h2>
    <p><strong>Alex Exec</strong> -- Chief Executive Officer</p>
    <p><strong>Robin Analyst</strong> -- Analyst</p>
    <p><strong>Outside Person</strong> -- Equity Research</p></div>"""
    parsed = extract_page(html)
    assert "management_attribution_not_explicit" in parsed["problems"]
    assert parsed["management_attribution_unresolved"] == [
        {"speaker": "Outside Person", "role": "Equity Research"}
    ]
