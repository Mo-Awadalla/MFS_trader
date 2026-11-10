"""Audit every native source, grid predecessor, liquidity total and selection."""

import bisect
import calendar
import gzip
import hashlib
import json
import math
from array import array
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/wide_tick_hft_20260930"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (OUT / "verification.json").exists():
        raise RuntimeError("Preserve completed independent audit")
    frozen = json.loads((OUT / "screen_implementation.json").read_text())
    result = json.loads((OUT / "screen_results.json").read_text())
    manifest = json.loads((OUT / "complete_manifest_v1.json").read_text())
    for name, expected in frozen["input_sha256"].items():
        assert sha(OUT / name) == expected
    for name, expected in frozen["implementation_sha256"].items():
        assert sha(ROOT / name) == expected
    for name, expected in result["output_sha256"].items():
        assert sha(OUT / name) == expected
    grids = pd.read_parquet(OUT / "grid_states.parquet")
    summaries = pd.read_parquet(OUT / "symbol_date_supply.parquet")
    audited_grids, audited_messages, audited_summaries = 0, 0, 0
    max_notional_error = 0.0
    for item in manifest["files"]:
        path = ROOT / item["path"]
        assert sha(path) == item["compressed_sha256"]
        day = item["date"]
        mid = calendar.timegm(datetime.strptime(day, "%Y-%m-%d").timetuple())*1_000_000_000
        start, end = mid+32_400_000_000_000, mid+32_460_000_000_000
        day_grid = grids.loc[grids.date == day].to_dict("records")
        source_rows = defaultdict(list)
        for row in day_grid:
            if pd.notna(row["source_line"]):
                source_rows[int(row["source_line"])].append(row)
        seen, streams, high_ids, unique_trades = set(), {}, {}, defaultdict(dict)
        flows = defaultdict(lambda: {"buy_count": 0, "sell_count": 0, "buy_notional": Decimal(0), "sell_notional": Decimal(0)})
        digest, prior = hashlib.sha256(), -1
        with gzip.open(path, "rb") as handle:
            for lineno, raw_line in enumerate(handle):
                digest.update(raw_line)
                if not raw_line.strip():
                    for _symbol, series in streams.items():
                        series[0].append(prior)
                        series[1].append(-1)
                        series[2].append(0)
                    high_ids.clear()
                    continue
                text = raw_line.decode()
                stamp, body = text.split(" ", 1)
                assert stamp[:10] == day
                seconds = int(stamp[11:13])*3600+int(stamp[14:16])*60+int(stamp[17:19])
                remainder = stamp[19:].removesuffix("Z")
                received = mid+seconds*1_000_000_000+(int(remainder[1:].ljust(9, "0")) if remainder else 0)
                assert start <= received < end and received >= prior
                prior = received
                event = json.loads(body)["data"]
                audited_messages += 1
                symbol = event["s"]
                if not symbol.endswith("USDT"):
                    continue
                seen.add(symbol)
                if event["e"] == "bookTicker":
                    values = (event["b"], event["B"], event["a"], event["A"], event["T"])
                    identifier = int(event["u"])
                    previous = high_ids.get(symbol)
                    good_sequence = True
                    if previous is not None and identifier <= previous[0]:
                        good_sequence = identifier == previous[0] and values == previous[1] and previous[2]
                    if previous is None or identifier >= previous[0]:
                        high_ids[symbol] = (identifier, values, good_sequence)
                    else:
                        high_ids[symbol] = (previous[0], previous[1], False)
                    streams.setdefault(symbol, (array("q"), array("q"), array("b")))
                    for series, value in zip(streams[symbol], (received, lineno, int(good_sequence)), strict=True):
                        series.append(value)
                    for row in source_rows.get(lineno, []):
                        assert row["symbol"] == symbol and row["receive_ns"] == received
                        assert row["transaction_ns"] == int(event["T"])*1_000_000 and row["publication_ns"] == int(event["E"])*1_000_000
                        assert int(row["update_id"]) == identifier and bool(row["sequence_ok"]) == good_sequence
                        for column, native in [("bid", "b"), ("ask", "a"), ("bid_quantity", "B"), ("ask_quantity", "A")]:
                            assert row[column] == event[native]
                elif event["e"] == "trade":
                    identifier = int(event["t"])
                    signature = (event["p"], event["q"], event["T"], event["m"], event.get("X"))
                    if identifier in unique_trades[symbol]:
                        assert signature == unique_trades[symbol][identifier]
                        continue
                    unique_trades[symbol][identifier] = signature
                    p, q = Decimal(event["p"]), Decimal(event["q"])
                    matched, published = int(event["T"])*1_000_000, int(event["E"])*1_000_000
                    valid = (event.get("X") == "MARKET" and p.is_finite() and q.is_finite() and min(p, q) > 0
                             and isinstance(event["m"], bool) and -1_000_000 <= received-matched <= 5_000_000_000
                             and -1_000_000 <= received-published <= 5_000_000_000 and matched <= published+1_000_000)
                    if valid and received >= start+10_000_000_000:
                        side = "sell" if event["m"] else "buy"
                        flows[symbol][side+"_count"] += 1
                        flows[symbol][side+"_notional"] += p*q
                else:
                    raise AssertionError("Unknown native event")
        assert digest.hexdigest() == item["decoded_sha256"]
        assert len(day_grid) == len(seen)*50
        derived = defaultdict(lambda: [0, 0])
        for row in day_grid:
            symbol, decision = row["symbol"], row["decision_ns"]
            expected_line, sequence_ok = -1, False
            if symbol in streams:
                received, lines, valid_ids = streams[symbol]
                index = bisect.bisect_left(received, decision)-1
                if index >= 0:
                    expected_line, sequence_ok = lines[index], bool(valid_ids[index])
            assert expected_line == (-1 if pd.isna(row["source_line"]) else int(row["source_line"]))
            valid, supply = False, False
            if expected_line >= 0:
                bid, ask, bq, aq = [Decimal(row[k]) for k in ["bid", "ask", "bid_quantity", "ask_quantity"]]
                finite = all(v.is_finite() and v > 0 for v in [bid, ask, bq, aq])
                clock_ok = (0 < decision-row["receive_ns"] <= 5_000_000_000
                            and 0 < decision-row["transaction_ns"] <= 5_000_000_000
                            and row["transaction_ns"] <= row["receive_ns"]+1_000_000
                            and row["publication_ns"] <= row["receive_ns"]+1_000_000
                            and row["transaction_ns"] <= row["publication_ns"]+1_000_000)
                valid = sequence_ok and finite and bid < ask and clock_ok
                if valid:
                    spread = 20000*(ask-bid)/(ask+bid)
                    supply = 12 <= spread <= 100 and min(bid*bq, ask*aq) >= 2000
                    assert abs(float(spread)-row["spread_bps"]) < 1e-10
            assert row["valid"] == valid and row["supply"] == supply
            derived[symbol][0] += valid
            derived[symbol][1] += supply
            audited_grids += 1
        day_summary = summaries.loc[summaries.date == day].to_dict("records")
        assert {r["symbol"] for r in day_summary} == seen
        qualified = []
        for row in day_summary:
            symbol = row["symbol"]
            flow = flows[symbol]
            assert (row["valid_grid_points"], row["supply_grid_points"]) == tuple(derived[symbol])
            assert row["buy_count"] == flow["buy_count"] and row["sell_count"] == flow["sell_count"]
            for side in ["buy", "sell"]:
                expected = float(flow[side+"_notional"])
                error = abs(row[side+"_notional"]-expected)
                max_notional_error = max(max_notional_error, error)
                assert math.isclose(row[side+"_notional"], expected, rel_tol=1e-11, abs_tol=1e-8)
            accepted = (derived[symbol][0] >= 40 and derived[symbol][1] >= 30
                        and min(flow["buy_count"], flow["sell_count"]) >= 10
                        and min(flow["buy_notional"], flow["sell_notional"]) >= 5000)
            assert row["qualified"] == accepted
            if accepted:
                qualified.append((min(flow["buy_notional"], flow["sell_notional"]), symbol))
            audited_summaries += 1
        qualified.sort(key=lambda row: (-row[0], row[1]))
        selected = {symbol for _, symbol in qualified[:4]}
        assert {r["symbol"] for r in day_summary if r["selected"]} == selected
        print(json.dumps({"date": day, "verified_grids": len(day_grid), "selected": sorted(selected)}), flush=True)
    final = {"verified_at_utc": datetime.now(UTC).isoformat(), "source_files_verified": len(manifest["files"]),
             "native_messages_examined": audited_messages, "grid_predecessors_and_values_verified": audited_grids,
             "symbol_date_liquidity_and_selection_verified": audited_summaries,
             "max_trade_notional_reconstruction_error_usdt": max_notional_error,
             "implementation_sha256": sha(Path(__file__)), "screen_results_sha256": sha(OUT / "screen_results.json"),
             "actual_orders_or_fills_verified": False, "strategy_pnl_tested": False, "reliable_edge_established": False}
    (OUT / "verification.json").write_text(json.dumps(final, indent=2)+"\n")
    print(json.dumps(final), flush=True)


if __name__ == "__main__":
    main()
