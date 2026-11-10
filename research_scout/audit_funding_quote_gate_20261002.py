"""Independently reconcile both paired funding candidates' displayed budgets."""

import gzip
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pandas as pd

from research_scout.audit_external_quote_20261002 import capture, external_states, valid_at

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"research_scout/bybit_funding_hft_20261002"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = OUT/"quote_gate_independent_verification.json"
    assert not output.exists()
    results = json.loads((OUT/"quote_gate_results.json").read_text())
    manifest = json.loads((OUT/"quote_manifest.json").read_text())
    pairs = pd.read_parquet(OUT/"all_funding_pairs.parquet")
    candidates = pairs.loc[pairs.eligible].to_dict("records")
    assert len(candidates) == len(results["events"]) == 2 and manifest["complete"]
    verified = []
    for candidate in candidates:
        key = candidate["date"], candidate["hour"], candidate["symbol"]
        claimed = next(r for r in results["events"] if (r["date"], r["hour"], r["symbol"]) == key)
        sources = [r for r in manifest["files"] if (r["date"], r["hour"], r["symbol"]) == key]
        bs = next(r for r in sources if r["exchange"] == "binance-futures")
        ys = next(r for r in sources if r["exchange"] == "bybit")
        cutoff = candidate["decision_ns"]
        path = ROOT/bs["path"]
        assert sha(path) == bs["compressed_sha256"]
        raw = gzip.decompress(path.read_bytes())
        assert hashlib.sha256(raw).hexdigest() == bs["decoded_sha256"]
        last, previous, updates = None, -1, {}
        for index, line in enumerate(raw.decode().splitlines(), 1):
            if not line.strip():
                if previous < cutoff:
                    last = None
                updates.clear()
                continue
            stamp, payload = line.split(" ", 1)
            cap = capture(stamp)
            assert cap >= previous
            previous = cap
            body = json.loads(payload)["data"]
            assert body["s"] == candidate["symbol"] and body["e"] == "bookTicker"
            update = int(body["u"])
            if updates:
                assert update >= max(updates)
                if update in updates:
                    assert body == updates[update]
            updates = {update: body}
            if cap < cutoff:
                last = {"id": index, "cap": cap, "pub": int(body["E"])*1_000_000,
                        "cts": int(body["T"])*1_000_000, "bid": D(body["b"]), "ask": D(body["a"]),
                        "bid_size": D(body["B"]), "ask_size": D(body["A"])}
        assert last and all(0 < cutoff-last[k] <= 5_000_000_000 for k in ("cap", "pub", "cts"))
        bybit = external_states([ys], [candidate["symbol"]])[candidate["symbol"]]
        prior = [r for r in bybit if r["cap"] < cutoff]
        y = prior[-1]
        assert valid_at(y, cutoff)
        assert (last["id"], y["source"]) == (claimed["binance_quote_source_index"], claimed["bybit_quote_source_index"])
        for label, price in (("binance_bid", last["bid"]), ("binance_ask", last["ask"]), ("bybit_bid", y["b"][0]), ("bybit_ask", y["a"][0])):
            assert D(str(claimed[label])) == price
        funding = abs(D(str(candidate["bybit_funding_rate"]))*D(str(candidate["bybit_mark_price"]))-D(str(candidate["binance_funding_rate"]))*D(str(candidate["binance_mark_price"])))
        spread = last["ask"]-last["bid"]+y["a"][0]-y["b"][0]
        fee_adverse = D("0.0007")*(last["ask"]+last["bid"]+y["a"][0]+y["b"][0])
        budget = funding-spread-fee_adverse
        quantity = int(min(D(200)/max(last["ask"], y["a"][0]), min(last["bid_size"], last["ask_size"], y["a"][1], y["b"][1])/10)//10)*10
        size_ok = quantity*min(last["bid"], y["b"][0]) >= 100
        for name, value in (("quoted_funding_per_unit", funding), ("spread_cost_per_unit", spread), ("fees_and_adverse_per_unit", fee_adverse), ("payment_budget_after_spread_per_unit", budget)):
            assert abs(D(str(claimed[name]))-value) < D("1e-12")
        assert quantity == claimed["conditional_quantity"] and size_ok == claimed["size_ok"]
        assert claimed["eligible"] == (budget > 0 and size_ok)
        verified.append({"date": key[0], "hour": key[1], "symbol": key[2], "budget_per_unit": str(budget),
                         "budget_positive": budget > 0, "conditional_quantity": quantity, "size_ok": size_ok})
    verification = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(), "events": verified,
                    "auditor_sha256": sha(Path(__file__)), "independent_book_parser_sha256": sha(ROOT/"research_scout/audit_external_quote_20261002.py"),
                    "quote_results_sha256": sha(OUT/"quote_gate_results.json"),
                    "full_pairs_sha256": sha(OUT/"all_funding_pairs.parquet"),
                    "scope": "Both complete-screen candidates matched the original partial screen; native strict-as-of quotes, displayed size and Decimal payment budgets independently reconciled. This is not strategy P&L or actual execution.",
                    "strategy_pnl_tested": False, "reliable_edge_established": False}
    output.write_text(json.dumps(verification, indent=2)+"\n")
    print(json.dumps(verification), flush=True)


if __name__ == "__main__":
    main()
