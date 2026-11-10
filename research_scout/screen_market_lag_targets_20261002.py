"""Test fresh lagging targets only at the three verified causal leader clocks."""

import gzip
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D

import pandas as pd

from research.market_lag_supply import lag, leaders
from research.perp_shock_supply import sample
from research.precise_ledger import ledger_frame
from research_scout.prepare_market_lag_targets_20261002 import HYPOTHESIS, OUT, PARENT, ROOT, sha


def dump(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def screen(job):
    source, events, hypothesis, parent_window = job
    assert source["complete"] and sha(ROOT / source["path"]) == source["compressed_sha256"]
    with gzip.open(ROOT / source["path"], "rt", encoding="utf-8") as stream:
        rows, quotes, counts, symbols = sample(stream, source["date"], source["offset"])
    tag = f"{source['date']}_{source['offset']:04d}.parquet"
    quote_path, signal_path = OUT / "quotes" / tag, OUT / "signals" / tag
    ledger_frame(quotes).to_parquet(quote_path, index=False)
    ledger_frame(rows).to_parquet(signal_path, index=False)
    assert sha(ROOT / parent_window["quotes_path"]) == parent_window["quotes_sha256"]
    parent_quotes = {(r["decision_ns"], r["symbol"]): r for r in pd.read_parquet(ROOT / parent_window["quotes_path"]).to_dict("records")}
    indexed_quotes = {(r["decision_ns"], r["symbol"]): r for r in quotes}
    indexed_rows = {(r["decision_ns"], r["symbol"]): r for r in rows}
    target_rows, chosen_rows, previous = [], [], -1
    for event in sorted(events, key=lambda r: r["decision_ns"]):
        decision = int(event["decision_ns"])
        for clock in (decision - 10**9, decision):
            for symbol in ("BTCUSDT", "ETHUSDT"):
                old, new = parent_quotes[(clock, symbol)], indexed_quotes[(clock, symbol)]
                for field in ("receive_ns", "transaction_ns", "publication_ns", "update_id", "bid", "ask", "bid_quantity", "ask_quantity", "sequence_ok", "transaction_order_ok"):
                    assert new[field] == old[field], (source["date"], source["offset"], clock, symbol, field)
        leader = leaders(indexed_rows[(decision, "BTCUSDT")], indexed_rows[(decision, "ETHUSDT")])
        assert leader["leader_supply"] and leader["direction"] == event["direction"]
        assert D(leader["common_move_bps"]) == D(event["common_move_bps"])
        candidates = []
        for row in rows:
            if row["decision_ns"] != decision or row["symbol"] in hypothesis["excluded_symbols"]:
                continue
            tested = {"date": source["date"], "offset_minutes": source["offset"], "decision_ns": decision,
                      "symbol": row["symbol"], "direction": leader["direction"], "common_move_bps": leader["common_move_bps"],
                      **lag(leader, row), "selected": False}
            target_rows.append(tested)
            if tested["target_supply"]:
                candidates.append(tested)
        if candidates and decision - previous >= 30 * 10**9:
            chosen = sorted(candidates, key=lambda r: (-D(r["budget_bps"]), r["symbol"]))[0]
            chosen["selected"] = True
            chosen_rows.append(dict(chosen))
            previous = decision
    target_path = OUT / "targets" / tag
    ledger_frame(target_rows).to_parquet(target_path, index=False)
    return {"date": source["date"], "offset": source["offset"], "source_counts": counts, "symbols": symbols,
            "quote_rows": len(quotes), "signal_rows": len(rows), "valid_endpoints": sum(r["valid_endpoints"] for r in rows),
            "raw_shock_rows": sum(r["supply"] for r in rows), "selected": [r for r in rows if r["selected"]],
            "reasons": dict(Counter(r["reason"] for r in rows)),
            "quotes_path": str(quote_path.relative_to(ROOT)), "quotes_sha256": sha(quote_path),
            "signals_path": str(signal_path.relative_to(ROOT)), "signals_sha256": sha(signal_path),
            "target_rows": len(target_rows), "raw_target_candidates": sum(r["target_supply"] for r in target_rows),
            "selected_targets": chosen_rows, "target_reasons": dict(Counter(r["reason"] for r in target_rows)),
            "targets_path": str(target_path.relative_to(ROOT)), "targets_sha256": sha(target_path)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    sources = json.loads((OUT / "source_manifest.json").read_text())
    hypothesis = json.loads((HYPOTHESIS / "specification.json").read_text())
    assert sources["complete"] and sha(OUT / "specification.json") == sources["specification_sha256"]
    assert sha(HYPOTHESIS / "specification.json") == spec["hypothesis_specification_sha256"]
    assert sha(PARENT / "independent_verification.json") == spec["native_parent_audit_sha256"]
    assert sha(ROOT / spec["admitted_leader_grids_path"]) == spec["admitted_leader_grids_sha256"]
    events = pd.read_parquet(ROOT / spec["admitted_leader_grids_path"]).to_dict("records")
    parent = json.loads((PARENT / "screen_results.json").read_text())
    code = ["research/perp_shock_supply.py", "research/spot_perp_supply.py", "research/market_lag_supply.py",
            "research/precise_ledger.py", "research_scout/screen_market_lag_targets_20261002.py"]
    dump(OUT / "implementation.json", {"frozen_at_utc": datetime.now(UTC).isoformat(),
         "specification_sha256": sha(OUT / "specification.json"), "source_manifest_sha256": sha(OUT / "source_manifest.json"),
         "code_sha256": {p: sha(ROOT / p) for p in code}, "economic_implementations": 0,
         "validation": "Unchanged previously tested native signal and lag gate engines; full independent source and target audit follows."})
    for name in ("quotes", "signals", "targets"):
        (OUT / name).mkdir(exist_ok=True)
    jobs = [(s, [e for e in events if e["date"] == s["date"] and e["offset_minutes"] == s["offset"]], hypothesis,
             next(w for w in parent["windows"] if w["date"] == s["date"] and w["offset"] == s["offset"])) for s in sources["files"]]
    windows, counts, reasons = [], Counter(), Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(screen, job) for job in jobs]):
            row = future.result()
            windows.append(row)
            counts.update(row["source_counts"])
            reasons.update(row["target_reasons"])
            print(json.dumps({k: row[k] for k in ("date", "offset", "target_rows", "raw_target_candidates", "selected_targets")}), flush=True)
    windows.sort(key=lambda r: (r["date"], r["offset"]))
    selected = [r for w in windows for r in w["selected_targets"]]
    ledger_frame(selected).to_parquet(OUT / "selected.parquet", index=False)
    result = {"source_files": len(windows), "source_counts": dict(counts), "admitted_leader_grids": len(events),
              "target_rows": sum(r["target_rows"] for r in windows), "raw_target_candidates": sum(r["raw_target_candidates"] for r in windows),
              "selected_target_events": len(selected), "selected_sha256": sha(OUT / "selected.parquet"),
              "target_reasons": dict(reasons), "windows": windows,
              "implementation_sha256": sha(OUT / "implementation.json"), "economic_implementations": 0,
              "future_returns_evaluated": False, "selection_2025_opened": False, "reliable_edge_established": False}
    dump(OUT / "screen_results.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "windows"}), flush=True)


if __name__ == "__main__":
    main()
