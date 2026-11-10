"""Audit SOL replication with the same independent source-tape accounting."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.verify_liquidation_passive_20260930 import audit_passive

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/sol_hft_replication_20260930"


def main():
    audit = audit_passive(OUT, OUT, "SOLUSDT")
    spec = json.loads((OUT / "specification.json").read_text())
    result = json.loads((OUT / "results.json").read_text())
    notional = []
    for source in spec["calibration_audits"]:
        path = OUT / "raw/liquidations" / source["date"] / "SOLUSDT.csv.gz"
        assert digest(path) == source["source_sha256"]
        frame = pd.read_csv(path)
        assert len(frame) == source["rows"]
        notional.extend((frame.price * frame.amount).tolist())
    assert abs(pd.Series(notional).quantile(.99) - spec["threshold_reported_notional"]) < 1e-8
    events = {a["date"]: a["events"] for a in result["source_audits"]}
    audit.update(calibration_verified=True, event_count=sum(events.values()))
    (OUT / "verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    lines = ["SOLUSDT PASSIVE LIQUIDATION HFT REPLICATION — 2026-09-30", "", "VERDICT: NO CANDIDATE PROGRESSES. No reliable edge or competition win established.",
             "", "Same eight rules as BTC: follow/reverse, 8/16bp offset, 30/120-second hold after cancellation acknowledgement. No favorable SOL date, offset or cost was selected.",
             f"The Jan-Jun reported-notional distribution set a fixed 99th-percentile trigger of ${spec['threshold_reported_notional']:,.4f} from {len(notional):,} reports.",
             f"Six July-December first-of-month dates produce {sum(events.values())} first-report events. These calendar dates already have BTC research exposure; this is historical development, not forward evidence.",
             "All acquired public files total 269,936,549 compressed bytes; no authentication, paid API or trading order was used.",
             "Native SOL price tick 0.001 USDT and quantity step 0.1 SOL are checked for consistency against observed trades; public tapes do not prove historical private order acceptance.",
             "", "BASELINE: rule | gross dollars | net dollars | completed trades"]
    for name, candidate in result["results"].items():
        base = candidate["scenarios"]["base"]
        net = f"{base['net_dollars']:+.6f}" if base["complete"] else "INCOMPLETE"
        lines.append(f"{name} | {base['gross_closed_subtotal']:+.6f} | {net} | {base['trades']}")
    lines += ["", "Six baseline variants lose; two have zero modeled fills. No variant is complete and positive under every scenario with positive P&L after deleting its best date.",
              "The least-negative traded baseline is reverse/16bp/120s, -$0.6694 from five trades. That is not profitable or reliable evidence.",
              "Costs remain 3bp maker, 6bp taker plus 1bp market allowance. No fee reductions or VIP/rebate assumptions. Doubled fees, three-second outbound delay, full-first-through and touch-price fills are separate stresses.",
              "Max intended order $1000 and 10% of predecision visible size; $10000 starting cash on each isolated date. Every partial position persists until it is closed; unknown submitted execution invalidates the day.",
              "", "VERIFICATION AND LIMITS",
              f"Independent source-tape audit: {audit['maker_fill_records_checked_against_source_tape']} maker-fill records and {audit['no_fill_attempts_verified_against_source_tape']} no-fill attempts checked across dependent scenarios. Maximum P&L discrepancy ${audit['maximum_pnl_error_dollars']:.3g}.",
              "Seven focused engine tests pass, including native instrument units. Capture-time decisions and exchange-time execution remain separated.",
              "Counterfactual trade-through fills are not actual queue fills. Price-band rejection, self-impact, real routing, disconnect behavior and continuous competition wealth remain unobserved.",
              "No later SOL validation dates were opened after this failure. Two zero-fill variants remain absence of evidence in these samples rather than proof of universally negative returns.",
              "The current search totals 76 configurations / 100 implementation versions, including repairs and dependent cross-asset variants. User explicitly requires strictly HFT; slower intraday ETF candidates are excluded.", ""]
    (OUT / "REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    checkpoint_path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint.update(current_configurations=76, implementation_versions=100, focused_tests_total=65,
                      sol_replication_candidates=[], sol_events=sum(events.values()), sol_accounting_verified=True,
                      report=str(OUT / "REPORT.txt"),
                      remaining_evidence_work="Keep strictly HFT. Assess new exchange-native information before more price-feature or asset sweeps.")
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
