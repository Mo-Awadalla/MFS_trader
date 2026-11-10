"""Compare independently priced quote identities without using size to match."""

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/iex_units_hft_20261002"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    spec_path = OUT / "matching_specification.json"
    assert not spec_path.exists()
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_date": "2023-01-11",
        "symbols": ["IWM", "QQQ", "SPY"],
        "identity": "Exact symbol, both bid/ask prices; UNIQUE native quote within plus/minus 2ms of vendor timestamp vs native send timestamp. Size excluded from identity. No nearest-match substitution.",
        "size_hypotheses": ["native shares equal vendor size", "native shares floored by 100 equal vendor size"],
        "clock_report": "Keep native event, native send, exchange PCAP capture and vendor raw timestamp separately. Report associations; do not infer a universal clock guarantee.",
        "prefix_only": True,
        "returns_calculated": False,
        "implementation_sha256": digest(Path(__file__)),
    }
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    stats = json.loads((OUT / "extended_prefix_decoding.json").read_text())
    with gzip.open(OUT / "extended_prefix_records.jsonl.gz", "rt") as handle:
        rows = [json.loads(line) for line in handle]
    lo = int(pd.Timestamp("2023-01-11T14:30:00Z").value)
    hi = stats["last_capture_ns"] - 2_000_000
    matches, summary = [], {}
    for symbol in spec["symbols"]:
        source = ROOT / "data/parquet/alpaca_iex_orderflow_v1/development" / symbol / "2023-01-11/quotes.parquet"
        vendor = pd.read_parquet(source)
        native = [r for r in rows if r["type"] == "Q" and r.get("symbol") == symbol]
        by_price = defaultdict(list)
        for row in native:
            by_price[(row["bid_price"], row["ask_price"])].append(row)
        times = {key: np.asarray([r["send_ns"] for r in value], dtype=np.int64) for key, value in by_price.items()}
        for values in times.values():
            assert np.all(values[1:] >= values[:-1])
        counts, delays_event, delays_send = Counter(), [], []
        for row in vendor.itertuples(index=False):
            timestamp = int(pd.Timestamp(row.raw_timestamp).value)
            assert timestamp == int(row.timestamp.value)
            if not lo <= timestamp <= hi:
                continue
            counts["vendor_quotes_in_overlap"] += 1
            prices = []
            for price in (row.bid_price, row.ask_price):
                fixed = Decimal(str(price)) * 10000
                assert fixed == fixed.to_integral_value()
                prices.append(int(fixed))
            key = tuple(prices)
            if key not in times:
                counts["no_price_match"] += 1
                continue
            ts = times[key]
            start = int(np.searchsorted(ts, timestamp - 2_000_000, side="left"))
            end = int(np.searchsorted(ts, timestamp + 2_000_000, side="right"))
            if end - start != 1:
                counts["ambiguous_price_match" if end > start else "no_nearby_price_match"] += 1
                continue
            reference = by_price[key][start]
            counts["unique_price_matches"] += 1
            same = (reference["bid_size"], reference["ask_size"]) == (row.bid_size, row.ask_size)
            lots = (reference["bid_size"] // 100, reference["ask_size"] // 100) == (row.bid_size, row.ask_size)
            counts["share_identity_matches"] += int(same)
            counts["hundred_share_lot_floor_matches"] += int(lots)
            counts["native_sizes_with_partial_lot"] += int(reference["bid_size"] % 100 != 0 or reference["ask_size"] % 100 != 0)
            counts["zero_two_sided_size_matches"] += int(reference["bid_size"] == reference["ask_size"] == 0)
            event_delta = timestamp - reference["event_ns"]
            send_delta = timestamp - reference["send_ns"]
            delays_event.append(event_delta)
            delays_send.append(send_delta)
            matches.append({"symbol": symbol, "vendor_timestamp_ns": timestamp,
                            "vendor_bid_size": int(row.bid_size), "vendor_ask_size": int(row.ask_size),
                            "native": reference, "vendor_minus_event_ns": event_delta,
                            "vendor_minus_send_ns": send_delta, "share_identity": same,
                            "hundred_share_lot_floor": lots})
        def order_statistics(values):
            ordered = sorted(values)
            return {"min": ordered[0], "middle_order_statistic": ordered[len(ordered) // 2],
                    "max": ordered[-1]} if values else None
        summary[symbol] = {**dict(counts), "vendor_minus_event_ns": order_statistics(delays_event),
                           "vendor_minus_send_ns": order_statistics(delays_send),
                           "vendor_source_sha256": digest(source)}
    ledger = OUT / "quote_matching_ledger.jsonl.gz"
    with gzip.open(ledger, "wt", encoding="utf-8") as handle:
        for row in matches:
            handle.write(json.dumps(row) + "\n")
    result = {"source_date": "2023-01-11", "overlap_start_ns": lo, "overlap_end_ns": hi,
              "by_symbol": summary, "matches": len(matches), "ledger_sha256": digest(ledger),
              "native_rows_sha256": digest(OUT / "extended_prefix_records.jsonl.gz"),
              "native_prefix_sha256": digest(OUT / "20230111_TOPS.extended_prefix.gz"),
              "specification_sha256": digest(spec_path), "size_match_uses_price_only": True,
              "universal_historical_mapping_established": False,
              "native_clock_identity_established": False,
              "queue_priority_or_execution_verified": False, "returns_calculated": False}
    (OUT / "matching_results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
