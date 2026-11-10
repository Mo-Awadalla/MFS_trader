"""Versioned consolidated quote reference for unchanged conditional auction rules."""

import json
from datetime import UTC, datetime

import databento as db
import pandas as pd

from research.alpaca_quote_units import sip_sizes_in_shares
from research.auction_hft_event import costs
from research.crypto_symbol_cache import digest
from research.sip_quote_envelope import envelope
from research_scout.benchmark_close_auction_20260930 import DEST as BENCH
from research_scout.benchmark_close_auction_20260930 import INPUT, ROOT, targets
from research_scout.fetch_close_auction_sip_20260930 import DEST

DEFINITION = ROOT / "external_artifacts/databento_cash_etf_budget_v1/ARCX.PILLAR/definition/cash_etf_arcx_definition_2021-01-01_2026-07-27.dbn.zst"
SCENARIOS = {"base": {"delay_s": 1, "fee_multiplier": 1., "adverse_bps": 1., "radius_ns": 1000000},
             "double_fees": {"delay_s": 1, "fee_multiplier": 2., "adverse_bps": 1., "radius_ns": 1000000},
             "latency_3s": {"delay_s": 3, "fee_multiplier": 1., "adverse_bps": 1., "radius_ns": 1000000},
             "extra_slippage": {"delay_s": 1, "fee_multiplier": 1., "adverse_bps": 2., "radius_ns": 1000000},
             "alignment_100ms": {"delay_s": 1, "fee_multiplier": 1., "adverse_bps": 1., "radius_ns": 100000000}}


def summarize(frame):
    complete = bool(frame.conditional_complete.all())
    lo, hi = frame.conditional_pnl_lower.fillna(0), frame.conditional_pnl_upper.fillna(0)
    return {"conditional_complete": complete, "net_lower": float(lo.sum()) if complete else None,
            "net_upper": float(hi.sum()) if complete else None, "closed_lower": float(lo.sum()), "closed_upper": float(hi.sum()),
            "conditional_allocations": int(frame.status.eq("conditional_full_allocation").sum()),
            "positive_dates": int((lo > 0).sum()), "without_best_three": float(lo.sum() - lo.nlargest(3).sum()) if complete else None,
            "outcomes": frame.status.value_counts().to_dict(), "actual_strategy_execution_verified": False}


def main():
    spec_path = DEST / "replay_specification.json"
    if spec_path.exists():
        raise FileExistsError("SIP reference revision already frozen")
    manifest = json.loads((DEST / "manifest.json").read_text())
    assert manifest["complete"]
    old = json.loads((BENCH / "specification.json").read_text())
    for path, sha in old["code_sha256"].items():
        assert digest(ROOT / path) == sha
    validation = json.loads((ROOT / "external_artifacts/databento_cash_etf_budget_v1/validation_report.json").read_text())
    expected = next(r["sha256"] for r in validation["files"] if r["path"].replace("\\", "/") == DEFINITION.relative_to(ROOT).as_posix())
    assert digest(DEFINITION) == expected
    code = ["research/sip_quote_envelope.py", "research_scout/run_close_auction_sip_20260930.py", "research/alpaca_quote_units.py"]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "new_hypotheses": 0, "execution_reference_revisions": 2,
            "prior_benchmark_specification_sha256": digest(BENCH / "specification.json"), "manifest_sha256": digest(DEST / "manifest.json"),
            "source_definition_sha256": expected, "scenarios": SCENARIOS,
            "invariants": "All32 predecision signals, quantities, LOC caps, official auction prices, conditional full-allocation assumption, fees, delayed ACK/holds and exit-target clocks unchanged. Original trade-conditioned result retained. Historical SIP quotes acquired for all10 price-eligible dates, not only gaps or losers.",
            "quote_reference": "Complete historical SIP quote stream, fixed original exit target. Base includes standing state strictly before target-1ms and every update through target+1ms inclusive; stress alignment to+/-100ms. Require a predecessor and successor bracketing the whole window. Last invalid state cannot be replaced with an older quote. No arbitrary standing-quote age expiry. Positive noncrossed R-condition quotes with enough known bid shares required in EVERY observed state, otherwise conditional P&L remains unknown with possible inventory.",
            "units": "Point-in-time native ARCX.PILLAR SPY definitions must establish100-share round lots for each pre2025-11-03 date. Apply the documented Alpaca SIP lot-to-share change; preserve source quantities and timestamps. No double normalization or future definition.",
            "bounds": "Evaluate net cash at min/max bid in the observed envelope, including actual notional-dependent fees and adverse allowances. Bounds are conditional on full auction allocation and the specified observed-price set, not bounds on real physical fills. SIP timestamps are not strategy receipts or guaranteed matching-engine times. Quote routing, auction rationing and market impact remain unverified.",
            "advance": old["advance"], "historical_scope": "All2023-25 dates exposed discovery. No independent confirmation or live trading. Two execution-reference versions, not two new alpha hypotheses.",
            "sources": ["https://docs.alpaca.markets/us/docs/market-data-faq", "https://docs.alpaca.markets/us/v1.1/changelog/marketdata-bid-and-ask-size-display-change"],
            "code_sha256": {p: digest(ROOT / p) for p in code}}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    screen = pd.read_parquet(INPUT / "screen.parquet")
    signals = screen.loc[screen.eligible]
    auctions = pd.read_parquet(BENCH / "auction_references.parquet")
    request = targets(signals, auctions)
    req = {(r["date"], r["delay_s"], r["hold_s"]): r for r in request.to_dict("records")}
    definitions = db.DBNStore.from_file(str(DEFINITION)).to_df().reset_index()
    definitions = definitions.loc[definitions.raw_symbol.eq("SPY")]
    quote_data, unit_audit = {}, []
    for file in manifest["files"]:
        assert digest(ROOT / file["path"]) == file["sha256"] and file["metadata"]["pagination_complete"]
        raw = pd.read_parquet(ROOT / file["path"])
        assert raw.timestamp.is_monotonic_increasing
        pd.testing.assert_series_equal(raw.timestamp, pd.to_datetime(raw.raw_timestamp, utc=True, format="ISO8601"), check_names=False)
        decision = int(screen.loc[screen.date.eq(file["date"]), "decision_ns"].iloc[0])
        prior = definitions.loc[definitions.ts_event.dt.as_unit("ns").astype("int64").lt(decision)].sort_values("ts_event").iloc[-1]
        assert int(prior.min_lot_size_round_lot) == 100
        normalized = sip_sizes_in_shares(raw, legacy_round_lot_shares=100, feed="sip")
        quote_data[file["date"]] = normalized
        unit_audit.append({"date": file["date"], "definition_event_ns": int(prior.ts_event.value),
                           "round_lot": int(prior.min_lot_size_round_lot), "rows": len(raw), "source_sha256": file["sha256"]})
    states, results, advance = [], {}, []
    au = auctions.set_index("date").to_dict("index")
    for hold in (15, 30):
        scenarios = {}
        for scenario_name, scenario in SCENARIOS.items():
            rows = []
            for s in signals.to_dict("records"):
                a, qty = au[s["date"]], int(s["quantity"])
                rec = {"date": s["date"], "hold_s": hold, "quantity": qty, "limit": s["limit"], "auction_price": a["price"],
                       "actual_strategy_execution_verified": False}
                assert a["valid"]
                if a["price"] > s["limit"] + 1e-9:
                    rows.append({**rec, "status": "outside_limit_no_reference_fill", "conditional_complete": True,
                                 "conditional_pnl_lower": 0., "conditional_pnl_upper": 0.})
                    continue
                assert qty <= a["quantity"]
                r = req[s["date"], scenario["delay_s"], hold]
                state = envelope(quote_data[s["date"]], r["target_ns"], qty, scenario["radius_ns"])
                states.append({"date": s["date"], "hold_s": hold, "scenario": scenario_name, **state})
                rec.update(target_ns=int(r["target_ns"]), ack_ns=int(r["ack_ns"]))
                if not state["complete"]:
                    rows.append({**rec, "status": state["reason"], "conditional_complete": False, "possible_open_quantity": qty})
                    continue
                ends, gross = [], []
                for bid in (state["bid_lower"], state["bid_upper"]):
                    fee, levy, adverse = costs(qty, a["price"], bid, scenario["fee_multiplier"], scenario["adverse_bps"])
                    gross.append(qty * (bid - a["price"]))
                    ends.append(gross[-1] - fee - levy - adverse)
                assert qty * a["price"] + max(1., qty * .0075) * scenario["fee_multiplier"] + qty * a["price"] * scenario["adverse_bps"] / 10000 < 10000
                rows.append({**rec, "status": "conditional_full_allocation", "conditional_complete": True,
                             "bid_lower": state["bid_lower"], "bid_upper": state["bid_upper"], "gross_lower": min(gross),
                             "gross_upper": max(gross), "conditional_pnl_lower": min(ends), "conditional_pnl_upper": max(ends)})
            ledger = pd.DataFrame(rows)
            for field in ("target_ns", "ack_ns"):
                if field in ledger:
                    ledger[field] = pd.array([r.get(field) for r in rows], dtype="Int64")
            ledger.to_parquet(DEST / f"{hold}s_{scenario_name}_ledger.parquet", index=False)
            scenarios[scenario_name] = {"all": summarize(ledger),
                "development_2023_2024": summarize(ledger.loc[ledger.date.lt("2025-01-01")]),
                "selection_2025": summarize(ledger.loc[ledger.date.ge("2025-01-01")])}
        passed = True
        for period in ("development_2023_2024", "selection_2025"):
            base = scenarios["base"][period]
            passed &= (all(s[period]["conditional_complete"] and s[period]["net_lower"] > 0 for s in scenarios.values())
                       and base["positive_dates"] >= 3 and base["without_best_three"] > 0)
        if passed:
            advance.append(f"{hold}s")
        results[f"{hold}s"] = {"scenarios": scenarios, "advance_to_allocation_evidence": bool(passed)}
        print(f"{hold}s: {json.dumps(scenarios['base'])}; advance={passed}", flush=True)
    pd.DataFrame(states).to_parquet(DEST / "quote_envelopes.parquet", index=False)
    assert all(digest(ROOT / p) == sha for p, sha in spec["code_sha256"].items())
    (DEST / "results.json").write_text(json.dumps({"results": results, "unit_audit": unit_audit,
        "advance_to_allocation_evidence": advance, "conditional_benchmark_only": True, "reliable_edge_established": False,
        "output_sha256": {p.name: digest(p) for p in DEST.glob("*.parquet")}}, indent=2) + "\n")


if __name__ == "__main__":
    main()
