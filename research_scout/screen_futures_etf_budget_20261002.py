"""Match frozen ES impulses to causal SPY states and preserve every rejection."""

import json
from datetime import UTC, datetime

import pandas as pd

from research.futures_etf_budget import budget
from research.same_index_supply import Quotes
from research_scout.screen_futures_etf_20261002 import OUT, ROOT, sha


def main():
    assert not (OUT/"spy_budget_results.json").exists()
    source = json.loads((OUT/"quote_manifest.json").read_text())
    result = json.loads((OUT/"source_screen_results.json").read_text())
    assert sha(OUT/"es_impulses.parquet") == result["impulses_sha256"]
    events = pd.read_parquet(OUT/"es_impulses.parquet").to_dict("records")
    freeze = {"created_at_utc": datetime.now(UTC).isoformat(), "specification_sha256": sha(OUT/"specification.json"),
              "quote_manifest_sha256": sha(OUT/"quote_manifest.json"), "impulses_sha256": result["impulses_sha256"],
              "code_sha256": {p: sha(ROOT/p) for p in ["research_scout/screen_futures_etf_budget_20261002.py", "research/futures_etf_budget.py", "research/same_index_supply.py", "tests/unit/test_futures_etf_budget.py"]},
              "timestamp_policy": "Use strict predecessors of decision-100ms and exactly one second earlier. Every state in a conflicting equal-timestamp group is invalid; do not select a convenient tie. No arbitrary standing-quote expiry. Historical SIP receipt remains conditional.",
              "quantity_units": "Apply the existing historical Alpaca SIP round-lot adapter implicit in Quotes: 100 shares per 2023 SPY quote lot. Historical contract definition evidence remains conditional, as in prior SIP tests.",
              "cost_evaluation": "Compute the declared round-trip cost budget at current bid/ask, including both minimum commissions, sell charges, both adverse allowances and a calendar day of short borrow. This current-quote catch-up budget is not actual P&L.",
              "future_returns_evaluated": False}
    (OUT/"spy_budget_implementation.json").write_text(json.dumps(freeze, indent=2)+"\n")
    tapes, rows = {}, []
    for event in events:
        row = {k: event[k] for k in ("date", "decision_ns", "signal_cutoff_ns", "current_price", "reference_price", "return_bps")}
        row.update(eligible=False, reason="unknown_spy_source")
        matches = [s for s in source["files"] if event["decision_ns"] in s["decision_ns"]]
        assert len(matches) == 1
        item = matches[0]
        if item["complete"]:
            key = item["window_id"]
            if key not in tapes:
                assert sha(ROOT/item["path"]) == item["sha256"]
                tapes[key] = Quotes(pd.read_parquet(ROOT/item["path"]))
            tape = tapes[key]
            cutoff = event["signal_cutoff_ns"]
            current, reference = int(tape.indices(cutoff)), int(tape.indices(cutoff-1_000_000_000))
            a, b = tape.row(current), tape.row(reference)
            row.update(window_id=key, spy_current_index=current, spy_reference_index=reference)
            if a is None or b is None:
                row["reason"] = "missing_invalid_or_tied_spy_state"
                row.update(current_ambiguous=bool(current >= 0 and tape.ambiguous[current]),
                           reference_ambiguous=bool(reference >= 0 and tape.ambiguous[reference]))
            else:
                row.update(spy_current_ns=int(tape.times[current]), spy_reference_ns=int(tape.times[reference]),
                           spy_bid=a["bid_price"], spy_ask=a["ask_price"], spy_bid_size=a["bid_size"], spy_ask_size=a["ask_size"],
                           spy_reference_bid=b["bid_price"], spy_reference_ask=b["ask_price"], **budget(a, b, event))
        rows.append(row)
    frame = pd.DataFrame(rows)
    for key in frame:
        if key.endswith(("_ns", "_index")):
            frame[key] = pd.array([r.get(key) for r in rows], dtype="Int64")
    frame.to_parquet(OUT/"spy_budgets.parquet", index=False)
    priced = frame.loc[frame.get("total_cost", pd.Series(index=frame.index, dtype=float)).notna()]
    output = {"futures_events": len(frame), "source_quote_files": len(source["files"]),
              "complete_quote_files": sum(s["complete"] for s in source["files"]),
              "source_quote_rows": sum(s.get("rows", 0) for s in source["files"]),
              "priced_budgets": len(priced), "eligible_events": int(frame.eligible.sum()),
              "outcomes": frame.reason.value_counts().to_dict(),
              "maximum_remaining_budget_bps": float(priced.remaining_budget_bps.max()) if len(priced) else None,
              "maximum_signed_residual_bps": float(priced.signed_residual_bps.max()) if len(priced) else None,
              "budgets_sha256": sha(OUT/"spy_budgets.parquet"), "implementation_sha256": sha(OUT/"spy_budget_implementation.json"),
              "future_returns_evaluated": False, "economic_implementations": 0, "actual_execution_verified": False,
              "reliable_edge_established": False}
    (OUT/"spy_budget_results.json").write_text(json.dumps(output, indent=2)+"\n")
    print(json.dumps(output), flush=True)
    print(frame.loc[frame.eligible].to_json(orient="records"), flush=True)


if __name__ == "__main__":
    main()
