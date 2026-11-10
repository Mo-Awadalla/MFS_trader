"""Independent native-source and feasibility reconciliation, without exit P&L."""

import json
from collections import Counter

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.prepare_halt_hft_20260930 import OUT, ROOT

NS = 1000000000


def pick(frame, cutoff, age):
    times = pd.to_datetime(frame.raw_timestamp, utc=True, format="ISO8601").astype("int64")
    candidates = frame.loc[times < cutoff]
    if candidates.empty:
        return None
    i = candidates.index[-1]
    stamp = int(times.loc[i])
    rows = frame.loc[times == stamp]
    columns = ["bid_price", "ask_price", "bid_size", "ask_size", "conditions", "bid_exchange", "ask_exchange"]
    vals = rows[["bid_price", "ask_price", "bid_size", "ask_size"]].to_numpy(float)
    if (cutoff-stamp > age or rows[columns].nunique(dropna=False).gt(1).any()
            or not np.isfinite(vals).all() or (vals <= 0).any()
            or not rows.bid_price.lt(rows.ask_price).all() or not rows.conditions.eq('["R"]').all()
            or rows.bid_exchange.str.len().eq(0).any() or rows.ask_exchange.str.len().eq(0).any()):
        return None
    row = frame.loc[i].to_dict()
    return {**row, "index": int(i), "source_ns": stamp}


def main():
    spec = json.loads((OUT/"specification.json").read_text())
    original = json.loads((OUT/"screen_implementation.json").read_text())
    assert digest(OUT/"specification.json") == original["protocol_sha256"]
    for name, value in original["implementation"].items():
        assert digest(ROOT/name) == value
    for name, value in spec["source_sha256"].items():
        path = OUT/"source_audit"/name if name == "nyse_halts.csv" else OUT/name
        assert digest(path) == value
    manifest = json.loads((OUT/"manifest.json").read_text())
    assert digest(OUT/"manifest.json") == original["manifest_sha256"]
    counts, totals = Counter(), Counter()
    for record in manifest["files"]:
        if not record["complete"]:
            counts["original_failed_files"] += 1
            continue
        path = ROOT/record["path"]
        assert digest(path) == record["sha256"] and record["metadata"]["pagination_complete"]
        frame = pd.read_parquet(path)
        native = pd.to_datetime(frame.raw_timestamp, utc=True, format="ISO8601").astype("int64")
        assert native.equals(frame.timestamp.dt.as_unit("ns").astype("int64").rename("raw_timestamp"))
        assert native.is_monotonic_increasing and len(frame) == record["rows"]
        assert record["metadata"]["asof"] == record["date"]
        totals[record["kind"]] += len(frame)
        counts["source_files_verified"] += 1
    panel = pd.read_parquet(OUT/"source_normalized/screen.parquet")
    correction = json.loads((OUT/"source_normalized/specification.json").read_text())
    assert digest(ROOT/"research_scout/normalize_halt_source_20260930.py") == correction["implementation_sha256"]
    outcomes, primary_offsets = Counter(), []
    quote_failures = Counter()
    for expected in panel.to_dict("records"):
        folder = OUT/"raw"/expected["date"]
        quote = pd.read_parquet(folder/f"{expected['symbol']}_quotes.parquet")
        p = folder/f"{expected['symbol']}_trades.parquet"
        if not p.exists():
            recovery = OUT/"source_audit/recovery"/f"{expected['date']}_{expected['symbol']}_trades.json"
            metadata = json.loads(recovery.with_suffix(".metadata.json").read_text())
            assert digest(recovery) == metadata["sha256"] and metadata["status"] == 200
            body = json.loads(recovery.read_text())
            assert body["symbol"] == expected["symbol"] and body["trades"] is None and body["next_page_token"] is None
            counts["provider_empty_responses_verified"] += 1
            reason = "no_primary_reopening_print"
        else:
            trades = pd.read_parquet(p)
            times = pd.to_datetime(trades.raw_timestamp, utc=True, format="ISO8601").astype("int64")
            accepted = {"T", "Q"} if expected["exchange"] == "Nasdaq" else {"NYSE": "N", "NYSE American": "A"}[expected["exchange"]]
            flags = trades.conditions.map(json.loads)
            eligible = trades.exchange.isin(accepted) & flags.map(lambda c: "5" in c and not set(c) & {"Z", "L", "W", "P", "H", "U", "T"})
            eligible &= trades.price.gt(0) & trades["size"].gt(0)
            eligible &= times.between(expected["archive_resume_ns"]-5*NS, expected["archive_resume_ns"]+5*NS)
            candidates = trades.loc[eligible]
            if candidates.empty:
                reason = "no_primary_reopening_print"
            else:
                i = candidates.index[0]
                reopen = int(times.loc[i])
                assert int(expected["reopen_index"]) == i and int(expected["reopen_ns"]) == reopen
                price = float(trades.price.loc[i])
                primary_offsets.append((reopen-expected["archive_resume_ns"])/NS)
                assert float(expected["reopen_price"]) == price and int(expected["decision_ns"]) == reopen+6*NS
                assert candidates.loc[times.loc[candidates.index] == reopen, "price"].nunique() == 1
                pre = pick(quote, expected["halt_ns"]-NS, 5*NS)
                old = pick(quote, expected["halt_ns"]-30*NS, 5*NS)
                now = pick(quote, reopen+5*NS, NS)
                for label, state in [("prehalt", pre), ("30s_anchor", old), ("decision", now)]:
                    if state is None:
                        quote_failures[label] += 1
                if pre is None or old is None or now is None or now["source_ns"] < reopen:
                    reason = "missing_stale_invalid_or_ambiguous_signal_quote"
                else:
                    mid = (pre["bid_price"]+pre["ask_price"])/2
                    old_mid = (old["bid_price"]+old["ask_price"])/2
                    move = (mid/old_mid-1)*10000
                    assert abs(move-expected["pre_move_bps"]) < 1e-9
                    assert [old["index"], pre["index"], now["index"]] == [expected["old_index"], expected["pre_index"], expected["quote_index"]]
                    if abs(move) < 100:
                        reason = "prehalt_move_below_gate"
                    elif price < 1.005*mid or now["bid_price"] < price:
                        reason = "no_reopening_concession_and_support"
                    elif not 2 <= now["ask_price"] <= 500 or (now["ask_price"]/now["bid_price"]-1)*10000 > 50:
                        reason = "price_or_spread_gate"
                    else:
                        raise AssertionError("Unexpected candidate requires independent size and P&L work")
        assert reason == expected["reason"] and not expected["eligible"]
        outcomes[reason] += 1
        counts["events_independently_reconciled"] += 1
    assert counts["events_independently_reconciled"] == 78
    result = {"verified": True, **counts, "native_records": dict(totals), "screen_outcomes": dict(outcomes),
              "nonexclusive_quote_failure_counts": dict(quote_failures),
              "reopening_archive_offset_seconds_range": [min(primary_offsets), max(primary_offsets)],
              "round_lot_assumption_affects_any_candidate": False,
              "eligible_orders": 0, "profitability_tested": False,
              "venue_mapping_compatibility_independently_confirmed": False,
              "strategy_execution_verified": False, "reliable_edge_established": False,
              "scope": "All preserved successful source files, both explicit empty recovery responses,72 reopening anchors and78 conditional feasibility dispositions verified. No entry/exit economics evaluated; empty vendor data does not prove no actual trades."}
    (OUT/"verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
