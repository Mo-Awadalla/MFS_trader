from __future__ import annotations

from data.alpaca_l1 import normalize_quotes, normalize_trades
from data.l1_validate import validate_quotes, validate_trades
from data.validate import QualityResult


def test_trade_validation_rejects_duplicate_vendor_identity():
    trades = normalize_trades(
        [
            {"t": "2026-07-08T13:30:00Z", "i": 7, "x": "V", "p": 100, "s": 10, "c": [], "z": "C"},
            {"t": "2026-07-08T13:30:01Z", "i": 7, "x": "V", "p": 101, "s": 10, "c": [], "z": "C"},
        ],
        "AAPL",
    )

    report = validate_trades(trades, symbol="AAPL")

    assert report.result == QualityResult.FAIL
    assert report.stats["duplicate_trade_id_rows"] == 2


def test_trade_identity_is_scoped_by_exchange():
    trades = normalize_trades(
        [
            {"t": "2026-07-08T13:30:00Z", "i": 7, "x": "V", "p": 100, "s": 10, "c": [], "z": "C"},
            {"t": "2026-07-08T13:30:01Z", "i": 7, "x": "P", "p": 101, "s": 10, "c": [], "z": "C"},
        ],
        "AAPL",
    )

    report = validate_trades(trades, symbol="AAPL")

    assert report.result == QualityResult.PASS
    assert report.stats["duplicate_trade_id_rows"] == 0


def test_trade_validation_rejects_out_of_window_events():
    trades = normalize_trades(
        [{"t": "2026-07-08T13:30:00Z", "i": 7, "x": "V", "p": 100, "s": 10, "c": [], "z": "C"}],
        "AAPL",
    )

    report = validate_trades(
        trades,
        symbol="AAPL",
        requested_start="2026-07-08T13:31:00Z",
        requested_end="2026-07-08T13:32:00Z",
    )

    assert report.result == QualityResult.FAIL
    assert report.stats["outside_requested_interval"] == 1


def test_trade_validation_rejects_missing_exchange_or_tape():
    trades = normalize_trades(
        [{"t": "2026-07-08T13:30:00Z", "i": 7, "p": 100, "s": 10, "c": []}],
        "AAPL",
    )

    report = validate_trades(trades, symbol="AAPL")

    assert report.result == QualityResult.FAIL
    assert report.stats["missing_trade_identity_rows"] == 1


def test_quote_validation_reports_locked_and_crossed_states_without_dropping_rows():
    quotes = normalize_quotes(
        [
            {
                "t": "2026-07-08T13:30:00Z",
                "ax": "V",
                "ap": 100,
                "as": 5,
                "bx": "V",
                "bp": 100,
                "bs": 6,
                "c": [],
                "z": "C",
            },
            {
                "t": "2026-07-08T13:30:01Z",
                "ax": "V",
                "ap": 99,
                "as": 5,
                "bx": "V",
                "bp": 100,
                "bs": 6,
                "c": [],
                "z": "C",
            },
        ],
        "AAPL",
    )

    report = validate_quotes(quotes, symbol="AAPL")

    assert report.result == QualityResult.WARN
    assert report.stats["locked_quotes"] == 1
    assert report.stats["crossed_quotes"] == 1
    assert report.events_checked == 2


def test_incomplete_pagination_is_a_failure():
    trades = normalize_trades(
        [{"t": "2026-07-08T13:30:00Z", "i": 7, "x": "V", "p": 100, "s": 10, "c": [], "z": "C"}],
        "AAPL",
    )

    report = validate_trades(trades, symbol="AAPL", pagination_complete=False)

    assert report.result == QualityResult.FAIL
