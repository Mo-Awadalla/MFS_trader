"""Observed multiple F_LAST records at one native sequence must not break reconciliation."""

import pytest

from research_scout.audit_databento_public_book_v2_20261003 import reconcile


def inputs():
    mbo = []
    for index, (action, side, oid, price, size, seq, flags) in enumerate([
        ("R", "N", 0, None, 0, 0, 8), ("A", "B", 10, 100, 200, 1, 128),
        ("A", "A", 20, 101, 300, 2, 128), ("T", "A", 0, 100, 180, 3, 128),
        ("F", "B", 10, 100, 180, 3, 128), ("C", "B", 10, 100, 180, 3, 128),
    ]):
        mbo.append({"source_row": index, "action": action, "side": side, "order_id": oid,
                    "price": price, "size": size, "sequence": seq, "flags": flags,
                    "ts_recv": 1000 + seq, "ts_event": 900 + seq})
    quotes = []
    for source_index, bid_size, ask, ask_size in ((1, 200, None, 0), (2, 200, 101, 300),
                                                (3, 200, 101, 300), (5, 20, 101, 300)):
        row = {**mbo[source_index], "source_row": len(quotes), "bid_px_00": 100,
               "bid_sz_00": bid_size, "bid_ct_00": 1, "ask_px_00": ask,
               "ask_sz_00": ask_size, "ask_ct_00": int(ask is not None)}
        quotes.append(row)
    return mbo, quotes


def test_reconciles_pre_fill_and_post_cancel_at_same_sequence():
    mbo, quotes = inputs()
    counts, errors, _, outstanding = reconcile(mbo, quotes)
    assert counts["all_quotes_reconciled"] == 4 and not errors and outstanding == 2
    assert counts["resting_fills_verified"] == 1
    assert counts["native_groups_with_multiple_last_flags"] == 1


def test_unmatched_quote_suffix_is_not_silently_dropped():
    mbo, quotes = inputs()
    quotes.append({**quotes[-1], "sequence": 4})
    with pytest.raises(AssertionError, match="Quote suffix"):
        reconcile(mbo, quotes)
