import json

import pytest

from research.wide_tick_supply import screen

DAY = "2024-01-01"
START_MS = 1704099600000


def line(second, *, kind="bookTicker", symbol="TESTUSDT", identifier=None, **values):
    millis = START_MS+int(second*1000)
    event = {"e": kind, "s": symbol, "T": millis, "E": millis}
    if kind == "bookTicker":
        event.update(u=int(second*1000) if identifier is None else identifier, b="1.000", a="1.002", B="3000", A="3000")
    else:
        event.update(t=int(second*1000) if identifier is None else identifier, p="1", q="1000", m=True, X="MARKET")
    event.update(values)
    whole = int(second)
    fraction = int(round((second-whole)*1_000_000_000))
    return f"{DAY}T09:00:{whole:02d}.{fraction:09d}Z "+json.dumps({"data": event})


def test_exact_grid_receipt_is_excluded_even_at_nanosecond_precision():
    rows, _, _ = screen([line(9.9999999), line(10, a="1.0001")], DAY)
    assert rows[0]["supply"]
    assert rows[0]["receive_ns"] == START_MS*1_000_000+9_999_999_900
    assert not rows[1]["supply"]


def test_fresh_publication_cannot_hide_stale_transaction():
    rows, _, _ = screen([line(9.9, T=START_MS+1000)], DAY)
    assert not rows[0]["valid"] and rows[0]["reason"] == "stale_or_inconsistent_book_clock"


def test_invalid_latest_quote_is_not_replaced_by_earlier_favorable_one():
    rows, _, _ = screen([line(9), line(9.9, A="0")], DAY)
    assert rows[0]["reason"] == "invalid_book_values"


def test_disconnect_clears_book_and_regressing_update_invalidates_state():
    rows, _, _ = screen([line(9), "", line(10.5, identifier=8), line(11.5, identifier=7)], DAY)
    assert rows[0]["reason"] == "no_book_state"
    assert rows[1]["valid"]
    assert rows[2]["reason"] == "non_monotone_or_conflicting_book_id"


def test_only_unique_regular_executions_establish_two_sided_liquidity():
    events = [line(9)]
    events += [line(10, kind="trade", identifier=1), line(10.1, kind="trade", identifier=1, T=START_MS+10000)]
    events += [line(10.2, kind="trade", identifier=2, m=False), line(10.3, kind="trade", identifier=3, X="ADL")]
    _, summary, diag = screen(events, DAY)
    assert summary[0]["buy_count"] == summary[0]["sell_count"] == 1
    assert diag["duplicate_trades"] == 1 and diag["excluded_off_book_or_unknown_type"] == 1


def test_conflicting_trade_identity_and_out_of_window_data_fail_closed():
    with pytest.raises(ValueError, match="Conflicting native trade ID"):
        screen([line(10, kind="trade", identifier=1), line(11, kind="trade", identifier=1, q="2")], DAY)
    with pytest.raises(ValueError, match="outside frozen capture minute"):
        screen([line(60)], DAY)


def test_supply_requires_persistent_depth_and_flow_and_preserves_later_symbols():
    events = [line(i+.1) for i in range(9, 60)]
    events += [line(i+.2, kind="trade", identifier=1000+i, m=bool(i%2)) for i in range(10, 30)]
    events += [line(59.9, symbol="LATEUSDT")]
    events.sort(key=lambda r: r.split(" ", 1)[0])
    rows, summary, _ = screen(events, DAY)
    lookup = {r["symbol"]: r for r in summary}
    assert lookup["TESTUSDT"]["qualified"] and lookup["TESTUSDT"]["selected"]
    assert not lookup["LATEUSDT"]["qualified"]
    assert len(rows) == 100


def test_repeated_old_update_does_not_repair_sequence_until_a_newer_id():
    rows, _, _ = screen([line(9, identifier=8), line(10.1, identifier=7),
                         line(11.1, identifier=8, T=START_MS+9000), line(12.1, identifier=9)], DAY)
    assert not rows[1]["valid"] and not rows[2]["valid"]
    assert rows[3]["valid"]


def test_missing_trade_type_is_excluded_without_inventing_on_book_flow():
    source = line(10, kind="trade")
    stamp, payload = source.split(" ", 1)
    raw = json.loads(payload)
    del raw["data"]["X"]
    _, summary, diag = screen([stamp+" "+json.dumps(raw)], DAY)
    assert summary[0]["buy_count"] == summary[0]["sell_count"] == 0
    assert diag["excluded_off_book_or_unknown_type"] == 1
