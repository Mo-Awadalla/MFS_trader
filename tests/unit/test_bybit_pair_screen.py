import json

from research.bybit_pair_screen import classify


def inputs():
    cutoff, target = 20_000_000_000, 30_250_000_000
    event = {"date": "fixture", "hour": 8, "symbol": "FIXUSDT", "decision_ns": cutoff,
             "settlement_ns": target, "reason": "unobserved_funding_rate", "sequence_ok": True,
             "capture_ns": cutoff-100_000_000, "event_ns": cutoff-200_000_000, "known_fields": "{}"}
    bybit = {"receive_us": (cutoff-100_000_000)//1000, "event_us": (cutoff-200_000_000)//1000,
             "funding_time_us": target//1000, "funding_rate": -0.004, "mark_price": 10}
    binance = {"receive_ns": cutoff-100_000_000, "event_ns": cutoff-200_000_000,
               "funding_time_ns": target, "funding_rate": 0, "mark_price": 10}
    return event, bybit, binance


def test_missing_native_field_can_be_recovered_but_no_missing_source_is_invented():
    event, bybit, binance = inputs()
    row = classify(event, bybit, binance)
    assert row["eligible"] and row["sell_exchange"] == "binance-futures"
    assert row["quoted_payment_difference_bps"] == 40
    missing = classify(event, None, binance)
    assert not missing["eligible"] and missing["reason"] == "unknown_recovered_bybit_source"


def test_cutoff_tie_and_stale_publication_are_not_available():
    event, bybit, binance = inputs()
    bybit["receive_us"] = event["decision_ns"]//1000
    assert not classify(event, bybit, binance)["bybit_valid"]
    bybit["receive_us"] -= 1000
    bybit["event_us"] -= 5_000_000
    assert not classify(event, bybit, binance)["bybit_valid"]


def test_known_native_rate_and_mark_must_both_match():
    event, bybit, binance = inputs()
    event["known_fields"] = json.dumps({"fundingRate": "-0.003", "markPrice": "10.1"})
    row = classify(event, bybit, binance)
    assert row["reason"] == "native_normalized_field_disagreement"
    assert row["native_conflicting_fields"] == "fundingRate,markPrice"


def test_matching_native_time_uses_milliseconds_and_wrong_target_fails():
    event, bybit, binance = inputs()
    event["known_fields"] = json.dumps({"nextFundingTime": str(event["settlement_ns"]//1_000_000)})
    assert classify(event, bybit, binance)["eligible"]
    bybit["funding_time_us"] += 8*3600*1_000_000
    assert not classify(event, bybit, binance)["bybit_valid"]
    bybit["funding_time_us"] -= 8*3600*1_000_000
    binance["funding_time_ns"] += 8*3600*1_000_000_000
    assert not classify(event, bybit, binance)["usable"]


def test_exact_cost_hurdle_does_not_pass_and_rate_prescreen_still_applies():
    event, bybit, binance = inputs()
    bybit["funding_rate"] = -0.0028
    row = classify(event, bybit, binance)
    assert row["usable"] and not row["eligible"] and row["quoted_payment_difference_bps"] == 28
    bybit["funding_rate"] = -0.00139
    binance["funding_rate"] = 0.01
    row = classify(event, bybit, binance)
    assert not row["large_bybit_rate"] and not row["eligible"]


def test_native_sequence_failure_cannot_be_cured_with_csv():
    event, bybit, binance = inputs()
    event["sequence_ok"] = False
    row = classify(event, bybit, binance)
    assert row["reason"] == "stale_or_invalid_native_state" and not row["eligible"]


def test_missing_counterpart_is_unknown_instead_of_zero_rate():
    event, bybit, _ = inputs()
    row = classify(event, bybit, None)
    assert row["large_bybit_rate"] and not row["usable"]
    assert row["reason"] == "missing_exact_binance_symbol"
