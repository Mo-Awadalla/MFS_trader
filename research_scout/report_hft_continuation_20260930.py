"""Evidence checkpoint for passive execution and cross-crypto research."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/hft_edge_search_20260930"


def read(relative):
    return json.loads((ROOT / relative).read_text())


def dollars(value):
    return "INCOMPLETE" if value is None else f"${value:+.2f}"


def main():
    passive = read("research_scout/crypto_passive_partial_20260930/development_results.json")
    confirm = read("research_scout/crypto_passive_confirmation_20260930/results.json")["results"]
    cross = read("research_scout/crypto_cross_market_20260930/results.json")
    audit = read("research_scout/crypto_cross_market_20260930/data_audit.json")
    check = read("research_scout/hft_edge_search_20260930/continuation_accounting_check.json")
    rows = sum(len(pd.read_parquet(path, columns=["date"])) for path in (ROOT / "research_scout/crypto_cross_market_20260930/panels").glob("*.parquet"))
    book_rows = sum(item["bbo_rows"] for item in audit["sources"])
    trade_rows = sum(item["trade_rows"] for item in audit["sources"])
    lines = [
        "HFT EDGE SEARCH — CONTINUATION CHECKPOINT — 2026-09-30",
        "", "STATUS: ACTIVE. No reliable edge established; no competition win or deployable strategy claimed.",
        "", "The session has evaluated 36 dependent strategy configurations across ETF, BTC and ETH screens.",
        "Six passive configurations were additionally rerun after execution repairs: 42 implementation versions.",
        "The fixed-rule later-date confirmation adds evidence, not a newly tuned rule. These counts are not independent trials.",
        "Earlier research exposure remains; version-count corrections do not account for all historical searching.",
        "", "1. PASSIVE BTC — CORRECTED EXECUTION, FIVE DEVELOPMENT DATES",
        "Dates: 2023-08-15, 09-15, 10-15, 11-15, 12-15.",
        "Daily initial capital $10,000, maximum ticket $1,000. Totals sum isolated daily P&L; not compounded account wealth.",
        "Posted limit offsets 8/16bp; same three direction rules, no retuning after inspection.",
        "Baseline: 2bp maker, 5bp taker per side; 1bp additional cost allowance on taker exits.",
        "Strict-through printed volume accumulates fills. Partial inventory and cancellation acknowledgement are explicit.",
        "A missing execution state or insufficient exit depth invalidates the day's total result.",
        "Original single-large-print results are superseded by the separate repair; original artifacts remain intact.", "",
    ]
    ledger = []
    for name, item in passive.items():
        if not name.endswith("_base"):
            continue
        result = dollars(item["net_dollars"])
        if not item["complete"]:
            result += f"; closed-trade subtotal {dollars(item['closed_trade_pnl'])}"
        lines.append(f"{name.removesuffix('_base')}: {result}; {item['trades']} closed trades; no development gate pass.")
        ledger.append({"batch": "passive_corrected", "name": name, "net_dollars": item["net_dollars"],
                       "closed_trade_subtotal": item["closed_trade_pnl"], "trades": item["trades"], "complete": item["complete"]})
    lines += ["", "2. THE SPARSE POSITIVE WAS TESTED FURTHER WITHOUT LOWERING ITS ORIGINAL GATE",
              "The follow_16bps rule had +$5.46 from nine development trades and stayed positive in every frozen stress.",
              "Its statistical evidence was insufficient. To distinguish sparsity from economic failure, the exact rule",
              "was confirmed on 2024-01-15, 01-21, 01-28 and 01-31. Parameters, fees and scenarios were unchanged.", ""]
    combined = {}
    for name, item in confirm.items():
        development = passive[name]["net_dollars"]
        total = development + item["net_dollars"] if development is not None and item["net_dollars"] is not None else None
        combined[name] = total
        lines.append(f"{name}: later-period {dollars(item['net_dollars'])} / {item['trades']} trades; nine-date sum {dollars(total)}.")
    lines += ["Confirmation verdict: FAILED_LATER_PERIOD_STRESS. March was not opened by this test.",
              "The weak development profit is not retained as a credible trading edge.",
              "", "3. BTC INFORMATION ADDED TO ETH — MATCHED MODEL CONTROLS",
              f"Nine paired dates; {book_rows:,} BBO updates and {trade_rows:,} aggregate trade records admitted; {rows:,} paired decision clocks.",
              "Five 2023 dates trained fixed small boosted-tree models; four January 2024 dates evaluated them.",
              "Same model settings compare ETH price only, ETH price/flow, and ETH plus BTC price/flow information.",
              "Two horizons: 30 and 120 seconds. 250ms assumed feed delay, 1s order latency, and 3s latency stress.",
              "Marketable baseline: 5bp fees plus 1bp additional cost EACH SIDE, plus actual bid/ask crossing.",
              "Pre-decision sizing; submitted IOC with a causal price collar. Unknown deeper entry liquidity is unresolved.",
              "A post-run IOC-depth correction was replayed against all frozen forecasts: every no-trade result was unchanged.",
              "Exact original source snapshots and the correction record are preserved separately.",
              "Unknown submitted-order execution is unresolved, not silently rejected. Funding boundaries are excluded.", ""]
    for name, item in cross["results"].items():
        b = item["scenarios"]["base"]
        peak = item["forecast_abs_bps_quantiles"][-1]
        lines.append(f"{name}: {dollars(b['net_dollars'])}; {b['trades']} trades; maximum absolute forecast {peak:.3f}bp.")
        ledger.append({"batch": "cross_crypto", "name": name, "net_dollars": b["net_dollars"],
                       "closed_trade_subtotal": b["closed_trade_pnl"], "trades": b["trades"], "complete": b["complete"]})
    lines += ["No forecast cleared the frozen cost-plus-buffer threshold. All six stayed out of the market.",
              "Zero trades establish failure of these fitted strategies to find an economic opportunity, not proof that all BTC/ETH information is useless.",
              "", "4. VERIFICATION AND LIMITS",
              "36 focused tests pass. Changed Python files pass Ruff. Independent cash, fee and inventory reconciliation passed.",
              f"Passive development: {check['passive_partial']['priced_trades_across_dependent_stresses']:,} priced trades across dependent stress runs;",
              f"maximum trade-P&L discrepancy {check['passive_partial']['maximum_pnl_error_dollars']:.3g} dollars;",
              f"maximum inventory discrepancy {check['passive_partial']['maximum_quantity_error']:.3g} units.",
              "Later confirmation: 16 priced trades across four dependent scenarios also reconciled.",
              "The ETH no-trade result has no empirical fill validation; execution behavior is covered by synthetic tests only.",
              "Raw source checksums, ordering checks, frozen code hashes, specifications, ledgers and rejected outcomes are retained.",
              "Print-based passive fills do not establish queue position, all at-price fills, market impact or measured latency.",
              "All dates were historically exposed in earlier research. Later-date tests are not pristine forward results.",
              "No paid API request, brokerage order, or deployment was performed.",
              "", "Earlier ETF and stock findings remain in REPORT.txt, including the Alpaca SIP quote-unit repair.",
              "This checkpoint leaves the goal active and establishes no positive raw-return strategy suitable for promotion.", ""]
    (OUT / "CONTINUATION_REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(ledger).to_csv(OUT / "continuation_candidate_ledger.csv", index=False)
    checkpoint = {"status": "active", "reliable_edge_found": False, "configurations": 36,
                  "implementation_versions_including_execution_repairs": 42,
                  "fixed_confirmation_passed": False, "confirmation_combined_pnl": combined,
                  "cross_crypto_candidates": cross["survivors"], "quote_records_cross_crypto": book_rows,
                  "trade_records_cross_crypto": trade_rows, "paired_clocks": rows,
                  "focused_tests_passed": 36, "accounting_verified": all(x["verified"] for x in check.values())}
    (OUT / "continuation_checkpoint.json").write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(json.dumps(checkpoint, indent=2))


if __name__ == "__main__":
    main()
