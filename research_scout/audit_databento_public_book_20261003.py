"""Reconstruct every displayed order and reconcile completed BBO states to MBP-1."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from research.nasdaq_mbo_book import Book
from research_scout.inspect_databento_public_sample_20261003 import OUT
from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write


def rows(path):
    for batch in pq.ParquetFile(path).iter_batches(batch_size=65536):
        fields = batch.schema.names
        columns = [batch.column(name).to_pylist() for name in fields]
        for values in zip(*columns, strict=True):
            yield dict(zip(fields, values, strict=True))


def quote_key(record):
    return ((record["bid_px_00"], record["bid_sz_00"], record["bid_ct_00"]),
            (record["ask_px_00"], record["ask_sz_00"], record["ask_ct_00"]))


def main():
    inventory = json.loads((OUT / "inventory.json").read_text())
    sources = {source["schema"]: source for source in inventory["sources"]}
    for source in sources.values():
        assert sha(Path(source["typed_path"])) == source["typed_sha256"]
        assert source["counts"]["symbol"] == {"NVDA": source["rows"]}
        assert source["counts"]["publisher_id"] == {"2": source["rows"]}
        assert all(value == 0 for value in source["clock_checks"].values())
    assert not (OUT / "book_verification.json").exists()
    book, counts, problems = Book(), Counter(), []
    quotes = (r for r in rows(sources["mbp1"]["typed_path"]) if r["flags"] & 128)
    current = next(quotes, None)
    first_reset = None
    previous_sequence, active_key = None, None
    for record in rows(sources["mbo"]["typed_path"]):
        ordinal = record["source_row"]
        counts["mbo_records"] += 1
        if ordinal == 0:
            assert record["action"] == "R" and record["order_id"] == record["size"] == record["sequence"] == 0
            assert record["price"] is None and record["side"] == "N" and record["flags"] == 8
            first_reset = record
        else:
            assert not record["flags"] & 12, "Bad source quality outside the initial reset"
            key = (record["sequence"], record["ts_recv"], record["ts_event"])
            if active_key is None:
                active_key = key
                assert previous_sequence is None or key[0] > previous_sequence
            else:
                assert active_key == key, "A normalized atomic group has mixed clocks or sequence"
        if record["action"] == "F":
            resting = book.orders.get(record["order_id"])
            assert resting is not None and resting.side == record["side"]
            assert 0 < record["size"] <= resting.size
            assert ((record["price"] <= resting.price) if resting.side == "B" else (record["price"] >= resting.price))
            counts["resting_fills_verified"] += 1
        book.apply(record["action"], record["side"], record["order_id"], record["price"], record["size"], ordinal)
        if record["flags"] & 128:
            counts["completed_mbo_groups"] += 1
            previous_sequence, active_key = record["sequence"], None
            if current is not None:
                assert current["sequence"] >= record["sequence"], "MBP-1 group absent from MBO"
                if current["sequence"] == record["sequence"]:
                    observed = book.bbo()
                    expected = quote_key(current)
                    clocks_match = (record["ts_recv"], record["ts_event"]) == (current["ts_recv"], current["ts_event"])
                    if observed != expected or not clocks_match:
                        counts["mismatches"] += 1
                        if len(problems) < 30:
                            problems.append({"mbo_source_row": ordinal, "quote_source_row": current["source_row"],
                                             "sequence": record["sequence"], "actual": observed, "expected": expected,
                                             "clocks_match": clocks_match})
                    else:
                        counts["completed_quotes_reconciled"] += 1
                    current = next(quotes, None)
                    assert current is None or current["sequence"] > record["sequence"]
        if counts["mbo_records"] % 1000000 == 0:
            print(json.dumps(dict(counts)), flush=True)
    assert current is None and active_key is None
    assert counts["mbo_records"] == sources["mbo"]["rows"]
    assert counts["completed_quotes_reconciled"] + counts["mismatches"] == sources["mbp1"]["counts"]["flags"]["128"]
    result = {"verified": not problems and counts["mismatches"] == 0,
              "completed_at_utc": datetime.now(UTC).isoformat(), "counts": dict(counts), "first_mismatches": problems,
              "initial_clear": first_reset, "terminal_outstanding_orders": len(book.orders),
              "source_inventory_sha256": sha(OUT / "inventory.json"),
              "book_code_sha256": sha(ROOT / "research/nasdaq_mbo_book.py"), "audit_code_sha256": sha(Path(__file__)),
              "scope": "All displayed order lifecycles reconstructed from MBO; every completed MBP-1 BBO checked for exact prices, sizes, order counts and clocks. All reported resting fills reference sufficient visible orders. Both public files derive from the same Databento normalized feed; this is cross-schema reconciliation, not independent raw ITCH decoding or proof of private execution.",
              "initial_reset_policy": "The first record clears to an empty displayed book and has BAD_TS_RECV. It is recorded as initialization with an unusable trading clock, not a tradable event. Every subsequent record is checked for quality flags; no later bad-clock row is discarded or repaired.",
              "sample_reliability_limit": "One vendor-selected NVDA date; no independent temporal validation, market-wide packet continuity, hidden liquidity, routing or private execution established.",
              "returns_calculated": False, "paid_calls": 0, "reliable_edge_established": False}
    write(OUT / "book_verification.json", result)
    print(json.dumps(result), flush=True)
    assert result["verified"], "Source reconciliation failed; no economic test allowed"


if __name__ == "__main__":
    main()
