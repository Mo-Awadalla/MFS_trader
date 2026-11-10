"""Assemble an auditable research checkpoint without promoting failed results."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/hft_edge_search_20260930"


def main():
    records = []
    sources = [
        ("own_price_and_book", "hft_edge_search_20260930"),
        ("cross_etf", "hft_cross_etf_20260930"),
        ("crypto_cost_aware", "crypto_edge_search_20260930"),
    ]
    for family, folder in sources:
        report = json.loads((ROOT / "research_scout" / folder / "results.json").read_text())
        for name, result in report["candidates"].items():
            base = result["base"]
            complete = base.get("complete", True)
            records.append({
                "family": family, "candidate": name, "source": folder + "/results.json",
                "complete_quote_proxy_path": complete, "trades": base["trades"],
                "net_dollars_if_complete": base["net_dollars"] if complete else None,
                "priced_subtotal_if_incomplete": base["net_dollars"] if not complete else None,
                "status": "no_trades" if base["trades"] == 0 and complete
                          else "failed_gates" if complete else "incomplete_exit_evidence",
                "passed": result.get("selection_gate", result.get("screen_pass", False)),
            })
    repair = json.loads((ROOT / "research_scout/sip_quote_units_repair_20260930/results.json").read_text())
    summary = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "goal_status": "active_not_achieved",
        "user_constraints": {"instruments": ["stocks", "ETFs", "crypto"],
                             "objective": "raw outperformance and reliable edge",
                             "fees": "conservative assumptions explicitly requested"},
        "new_configurations": len(records), "survivors": sum(r["passed"] for r in records),
        "original_rule_repairs": 1, "records": records,
        "stock_repair": repair["statistics"],
        "later_history": "No 2026 equity evaluation or March crypto evaluation by these new batches; those periods have prior research exposure and are not pristine",
        "next_research_direction": "Audit broader stock quote coverage and prioritize mechanisms with measured gross edge comfortably above execution costs; do not tune rejected candidates on their selection dates",
        "needed_for_reliability": "More independent days, untouched confirmation, venue-specific execution evidence, cost and latency robustness, full-calendar accounting and appropriate benchmark",
    }
    (OUTPUT / "checkpoint.json").write_text(json.dumps(summary, indent=2) + "\n")
    pd.DataFrame(records).to_csv(OUTPUT / "candidate_ledger.csv", index=False)
    lines = [
        "HFT EDGE SEARCH — 2026-09-30", "",
        "STATUS: ACTIVE. No reliable trading edge found or competition win established.",
        "",
        "24 new configurations: 9 own-price/book ETF, 6 cross-ETF, 9 BTC cost-aware.",
        "These are dependent configurations, not 24 independent discoveries. All failed progression.",
        "One earlier AAPL rule was also replayed after a verified quote-unit repair.",
        "",
        "DATA AND CHRONOLOGY",
        "Databento EQUS.MINI: 806 local opening sessions inventoried. 444 sessions from 2023-2024 trained models; 235 admitted 2025 sessions selected candidates (15 known degraded dates excluded).",
        "346,290 symbol-clock rows, six ETFs, 5/30/120-second holds. Later 2026 panel was not opened for this batch.",
        "BTCUSDT: existing audited 5 training and 4 selection dates; eight later historical dates remained unused by this batch. The archive has prior research exposure.",
        "AAPL SIP: twelve five-minute 2025 windows, source hashes verified. Insufficient to generalize to stocks broadly.",
        "",
        "RESULTS (each scenario begins with $10,000; INCOMPLETE is not a portfolio result)",
    ]
    for r in records:
        pnl = (f"${r['net_dollars_if_complete']:+.2f}" if r['complete_quote_proxy_path']
               else f"INCOMPLETE; priced subtotal ${r['priced_subtotal_if_incomplete']:+.2f}")
        lines.append(f"{r['candidate']}: {pnl}; {r['trades']} priced trades; {r['status']}.")
    lines += [
        "",
        "WHY THE SMALL POSITIVE IS REJECTED",
        "price_ridge_120s: +$112.23 (+1.12%) from 12 trades / 11 trade days across 235 admitted sessions.",
        "Only three positive days; the best day supplied 86.16% of positive P&L. Removing the best five days gives -$24.56.",
        "Mean daily P&L 95% five-session-block interval: -$0.144 to +$1.683. Nine-trial-adjusted lower bound: -$0.187.",
        "One-second latency reduces profit to +$36.11. This is not reliable evidence of an edge.",
        "For context, cached adjusted-price SPY returned +17.06% from the first 2025 open to the last close. The strategy lacks a complete 250-session path because 15 dates were excluded, so this is not a formal matched-calendar comparison.",
        "",
        "A REAL MEASUREMENT ERROR FOUND",
        "Alpaca SIP quote sizes changed from round lots to shares on 2025-11-03. The old AAPL rule compared pre-change lot counts directly with a 100-share threshold.",
        "A separate adapter converts pre-change AAPL sizes by 100, retains raw values, and prevents double conversion. Original raw files, specifications and reports remain unchanged.",
        "Corrected signals: 102 rather than 17. Usable quote proxies: 52 across all twelve dates. Mean gross crossing return -1.216 bps; original-cost net -3.102 bps; stress -7.102 bps.",
        "Day-block 95% interval for net mean: [-4.149, -1.977] bps. 37 entries and 13 exits lacked fresh quotes; they are not booked as zero P&L or silently included in a portfolio return.",
        "Official source: https://docs.alpaca.markets/us/v1.1/changelog/marketdata-bid-and-ask-size-display-change",
        "",
        "EXECUTION AND RELIABILITY",
        "ETF base: observed ask/bid crossing, 250ms assumed combined delay, 1bp adverse slippage each side, $0.005/share commission each side, sell-notional and per-share levies. Whole shares, available cash, 10% of decision/arrival offer size. No broker commission minimum modeled; real minima would worsen these results.",
        "Stress: double slippage, 1s and 3s delay, wider spread. An unpriceable exit or insufficient displayed exit quantity invalidates the path. No passive fill assumptions.",
        "Crypto: bid/ask crossing, 1s delay, 60s holds, 5bps fee and 1bp slippage each side. Funding boundaries excluded. No model forecast clears the fixed cost threshold on selection dates.",
        "Crypto cache lacks execution depth and is already conditioned on future quote availability: usable for rejection screening, not deployment validation.",
        "EQUS.MINI aggregates anonymized component-venue BBOs; it does not establish consolidated NBBO routing, queue priority or actual fills.",
        "Source: https://databento.com/docs/venues-and-datasets/equs-mini",
        "Historical tuning exposure remains; new-batch multiplicity adjustments do not erase prior research. No reliable edge has been established.",
        "",
        "VERIFICATION",
        "Focused tests cover timestamp units, strict causality, same-clock cross-fund joins, fees, sizing, overlap, funding boundaries, invalid latest quotes and missing exits.",
        "Independent recomputation reconciled first-batch trade P&L to below $1e-13 and cash to below $1e-10.",
        "Original source data and historical reports were retained. No paid market-data request or broker order was made.",
    ]
    (OUTPUT / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"configurations": len(records), "survivors": summary["survivors"], "report": str(OUTPUT / "REPORT.txt")}))


if __name__ == "__main__":
    main()
