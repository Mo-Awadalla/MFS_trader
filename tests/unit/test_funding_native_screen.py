import json

import pandas as pd

from research.funding_native_screen import snapshot

TARGET = pd.Timestamp("2024-01-01 08:00", tz="UTC").value


def line(seconds_before, rate=".0014", symbol="TESTUSDT", event_lag_ms=0, next_offset=0):
    local = TARGET-int(seconds_before*1_000_000_000)
    message = {"stream": symbol.lower()+"@markPrice@1s", "data": {
        "e": "markPriceUpdate", "E": local//1_000_000-event_lag_ms,
        "T": TARGET//1_000_000+next_offset, "s": symbol, "p": "123.4", "r": rate}}
    return pd.Timestamp(local, unit="ns", tz="UTC").isoformat()+" "+json.dumps(message)


def test_receipt_cutoff_excludes_later_rate_changes_and_funding_time_is_not_event_clock():
    rows, _ = snapshot([line(31), line(30, ".02"), line(20, ".03")], TARGET)
    assert rows[0]["usable"] and rows[0]["large_binance_rate"]
    assert rows[0]["funding_rate"] == .0014
    assert rows[0]["funding_time_ns"] == TARGET > rows[0]["decision_ns"]


def test_negative_rate_and_exact_threshold_are_preserved():
    rows, _ = snapshot([line(31, "-.0014")], TARGET)
    assert rows[0]["large_binance_rate"] and rows[0]["funding_rate"] < 0


def test_disconnect_invalidates_old_state_until_full_snapshot():
    rows, _ = snapshot([line(32), "", line(31, symbol="OTHERUSDT")], TARGET)
    by_symbol = {r["symbol"]: r for r in rows}
    assert not by_symbol["TESTUSDT"]["usable"]
    assert by_symbol["OTHERUSDT"]["usable"]


def test_new_invalid_state_is_not_replaced_with_earlier_qualifying_rate():
    rows, _ = snapshot([line(32), line(31, next_offset=4*3600*1000)], TARGET)
    assert not rows[0]["usable"] and not rows[0]["large_binance_rate"]


def test_capture_cannot_hide_stale_publication_or_wrong_settlement_currency():
    rows, _ = snapshot([line(31, event_lag_ms=6000), line(31, symbol="TESTUSDC")], TARGET)
    assert len(rows) == 1 and not rows[0]["usable"]
