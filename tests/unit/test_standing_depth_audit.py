from research.standing_depth_audit import unchanged_topfive


def case():
    quote = {"quote_local_us": 1000, "quote_exchange_us": 900, "target_us": 2000}
    for side, prices in (("bids", [100, 99, 98, 97, 96]), ("asks", [101, 102, 103, 104, 105])):
        for i, price in enumerate(prices):
            quote[f"{side}[{i}].price"] = price
            quote[f"{side}[{i}].amount"] = 10.
    rows = [{"disconnect": False, "local_us": 1000, "E_us": 900, "T_us": 850, "U": 1, "u": 2, "pu": 0, "b": [], "a": []},
            {"disconnect": False, "local_us": 1500, "E_us": 1450, "T_us": 1400, "U": 3, "u": 4, "pu": 2, "b": [["95", "20"]], "a": []},
            {"disconnect": False, "local_us": 2300, "E_us": 2250, "T_us": 2200, "U": 5, "u": 6, "pu": 4, "b": [], "a": []}]
    return rows, quote


def test_deeper_updates_prove_standing_topfive_and_distinguish_E_from_T():
    rows, quote = case()
    result = unchanged_topfive(rows, quote, 1.)
    assert result["verified_unchanged"] and result["updates_between_source_and_target"] == 1
    assert result["csv_clock_matches_E"] and not result["csv_clock_matches_T"]


def test_topfive_change_before_native_target_is_not_admitted():
    rows, quote = case()
    rows[1]["b"] = [["100", "9"]]
    assert unchanged_topfive(rows, quote, 1.)["reason"] == "top_five_changed_before_transaction_time_target"


def test_sequence_gap_and_disconnect_cannot_certify_continuity():
    rows, quote = case()
    rows[1]["pu"] = 1
    assert unchanged_topfive(rows, quote, 1.)["reason"] == "native_sequence_gap"
    rows, quote = case()
    rows.insert(1, {"disconnect": True})
    assert unchanged_topfive(rows, quote, 1.)["reason"] == "disconnect_before_successor"


def test_transaction_clock_tie_at_order_remains_ambiguous():
    rows, quote = case()
    rows[-1]["T_us"] = quote["target_us"]
    assert unchanged_topfive(rows, quote, 1.)["reason"] == "transaction_timestamp_tie_at_order"
