"""Reconcile every quote at its normalized action; shared native sequences are allowed."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from research.nasdaq_mbo_book import Book
from research_scout.audit_databento_public_book_20261003 import quote_key, rows
from research_scout.inspect_databento_public_sample_20261003 import OUT
from research_scout.prepare_databento_fast_20261002 import ROOT, sha, write


def reconcile(mbo, quotes, progress=False):
    book, counts, problems = Book(), Counter(), []
    quotes = iter(quotes)
    current = next(quotes, None)
    first_reset = None
    native_key, native_last_flags = None, 0
    for record in mbo:
        ordinal = record["source_row"]
        counts["mbo_records"] += 1
        if ordinal == 0:
            assert record["action"] == "R" and record["order_id"] == record["size"] == record["sequence"] == 0
            assert record["price"] is None and record["side"] == "N" and record["flags"] == 8
            first_reset = record
        else:
            assert not record["flags"] & 12, "Bad source quality outside the initial reset"
            key = (record["sequence"], record["ts_recv"], record["ts_event"])
            if native_key is None or key[0] != native_key[0]:
                assert native_key is None or key[0] > native_key[0]
                if native_key is not None:
                    counts["native_groups_with_multiple_last_flags"] += int(native_last_flags > 1)
                native_key, native_last_flags = key, 0
                counts["native_sequence_groups"] += 1
            else:
                assert key == native_key, "One native sequence has mixed clocks"
            native_last_flags += int(bool(record["flags"] & 128))
        if record["action"] == "F":
            resting = book.orders.get(record["order_id"])
            assert resting is not None and resting.side == record["side"]
            assert 0 < record["size"] <= resting.size
            assert ((record["price"] <= resting.price) if resting.side == "B" else (record["price"] >= resting.price))
            counts["resting_fills_verified"] += 1
        book.apply(record["action"], record["side"], record["order_id"], record["price"], record["size"], ordinal)
        counts["mbo_last_flag_records"] += int(bool(record["flags"] & 128))
        if current is not None:
            assert current["sequence"] >= record["sequence"], "MBP-1 record absent from MBO"
            if (current["sequence"], current["action"]) == (record["sequence"], record["action"]):
                assert (current["price"], current["size"]) == (record["price"], record["size"])
                observed, expected = book.bbo(), quote_key(current)
                clocks_match = (record["ts_recv"], record["ts_event"]) == (current["ts_recv"], current["ts_event"])
                if observed != expected or not clocks_match:
                    counts["mismatches"] += 1
                    if len(problems) < 30:
                        problems.append({"mbo_source_row": ordinal, "quote_source_row": current["source_row"],
                                         "sequence": record["sequence"], "action": record["action"],
                                         "actual": observed, "expected": expected, "clocks_match": clocks_match})
                else:
                    counts["all_quotes_reconciled"] += 1
                    counts["completed_quotes_reconciled"] += int(bool(current["flags"] & 128))
                counts["corresponding_flag_differences"] += int(current["flags"] != record["flags"])
                counts["quote_actions_" + current["action"]] += 1
                current = next(quotes, None)
                assert current is None or current["sequence"] >= record["sequence"]
        if progress and counts["mbo_records"] % 1000000 == 0:
            print(json.dumps(dict(counts)), flush=True)
    assert current is None, "Quote suffix not present in MBO"
    counts["native_groups_with_multiple_last_flags"] += int(native_last_flags > 1)
    return counts, problems, first_reset, len(book.orders)


def main():
    inventory = json.loads((OUT / "inventory.json").read_text())
    sources = {source["schema"]: source for source in inventory["sources"]}
    for source in sources.values():
        assert sha(Path(source["typed_path"])) == source["typed_sha256"]
        assert source["counts"]["symbol"] == {"NVDA": source["rows"]}
        assert source["counts"]["publisher_id"] == {"2": source["rows"]}
        assert all(value == 0 for value in source["clock_checks"].values())
    assert not (OUT / "book_verification_v2.json").exists()
    counts, problems, first_reset, outstanding = reconcile(rows(sources["mbo"]["typed_path"]),
                                                         rows(sources["mbp1"]["typed_path"]), progress=True)
    assert counts["mbo_records"] == sources["mbo"]["rows"]
    assert counts["all_quotes_reconciled"] + counts["mismatches"] == sources["mbp1"]["rows"]
    assert counts["resting_fills_verified"] == sources["mbo"]["counts"]["action"]["F"]
    result = {"verified": not problems and counts["mismatches"] == 0,
              "completed_at_utc": datetime.now(UTC).isoformat(), "counts": dict(counts), "first_mismatches": problems,
              "initial_clear": first_reset, "terminal_outstanding_orders": outstanding,
              "source_inventory_sha256": sha(OUT / "inventory.json"),
              "book_code_sha256": sha(ROOT / "research/nasdaq_mbo_book.py"), "audit_code_sha256": sha(Path(__file__)),
              "preceding_auditor_sha256": sha(ROOT / "research_scout/audit_databento_public_book_20261003.py"),
              "scope": "All displayed order lifecycles reconstructed from MBO; EVERY MBP-1 record checked for exact post-action BBO prices, sizes, order counts and clocks. T and F leave the book unchanged; C removes displayed quantity. All reported resting fills reference sufficient visible orders. Both public files derive from the same Databento normalized feed; this is cross-schema reconciliation, not independent raw ITCH decoding or proof of private execution.",
              "initial_reset_policy": "First R record initializes an empty displayed book with an unusable trading timestamp. All later quality flags are checked without dropping or repairing rows.",
              "v1_failure": "The first auditor assumed unique native sequence among F_LAST records. Native sequence301782 has T,F,C records,each flagged128; two corresponding MBP-1 records show pre-fill and post-cancel BBO. That assumption was invalid. This v2 matches sequence,action,price,size and clocks at each normalized action, including non-F_LAST quotes; economic logic and source files were not changed.",
              "future_signal_rule": "Do not assume every F_LAST record closes a whole native sequence. Before any economic rule, define a causal snapshot after all records at the same capture clock strictly precede the information cutoff. Never expose an intermediate T/F state as a final post-execution book.",
              "sample_reliability_limit": "One vendor-selected NVDA date; no independent temporal validation, market-wide packet continuity, hidden liquidity, routing or private execution established.",
              "returns_calculated": False, "paid_calls": 0, "reliable_edge_established": False}
    write(OUT / "book_verification_v2.json", result)
    print(json.dumps(result), flush=True)
    assert result["verified"], "Source reconciliation failed; no economic test allowed"


if __name__ == "__main__":
    main()
