"""Display price is not a private limit; a differing execution never rewrites the book."""

from research_scout.audit_databento_public_book_v3_20261003 import reconcile


def inputs():
    mbo = []
    for index, (action, price, size, seq) in enumerate([
        ("R", None, 0, 0), ("A", 177030000000, 80, 1),
        ("F", 177020000000, 80, 2), ("C", 177030000000, 80, 2),
    ]):
        mbo.append({"source_row": index, "action": action, "price": price, "size": size,
                    "sequence": seq, "side": "N" if index == 0 else "A", "order_id": 0 if index == 0 else 10,
                    "flags": 8 if index == 0 else 128, "ts_recv": 1000 + seq, "ts_event": 900 + seq})
    quotes = []
    for index, price, size in ((1, 177030000000, 80), (3, None, 0)):
        quotes.append({**mbo[index], "source_row": len(quotes), "bid_px_00": None, "bid_sz_00": 0,
                       "bid_ct_00": 0, "ask_px_00": price, "ask_sz_00": size, "ask_ct_00": int(size > 0)})
    return mbo, quotes


def test_execution_differs_from_display_and_cancel_uses_original_price():
    counts, problems, _, outstanding = reconcile(*inputs())
    assert not problems and outstanding == 0
    assert counts["all_quotes_reconciled"] == 2 and counts["fills_at_other_than_display_price"] == 1


def test_actual_quote_size_mismatch_remains_a_failed_reconciliation():
    mbo, quotes = inputs()
    quotes[0]["ask_sz_00"] = 81
    counts, problems, _, _ = reconcile(mbo, quotes)
    assert counts["mismatches"] == 1 and len(problems) == 1
