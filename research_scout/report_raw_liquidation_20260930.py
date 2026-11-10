"""Publish the verified native-size HFT screen and preserve the active goal."""

import json

import pandas as pd

from research_scout.audit_force_order_full_20260930 import ASSETS, DATES, OUT, ROOT


def main():
    field = json.loads((OUT / "field_audit.json").read_text())
    result = json.loads((OUT / "results.json").read_text())
    spec = json.loads((OUT / "strategy_specification.json").read_text())
    audit = json.loads((OUT / "verification.json").read_text())
    assert audit["verified"] and not result["candidates_for_additional_evidence"]
    counts = {"negative": 0, "positive": 0, "zero_no_fills": 0, "incomplete": 0}
    for candidate in result["results"].values():
        base = candidate["scenarios"]["base"]
        key = ("incomplete" if not base["complete"] else "positive" if base["net_dollars"] > 0
               else "negative" if base["net_dollars"] < 0 else "zero_no_fills")
        counts[key] += 1
    lines = ["NATIVE EXECUTED LIQUIDATION SIZE: STRICT HFT — 2026-09-30", "",
        "VERDICT: NO CANDIDATE PASSES THE FROZEN SCREEN. The competition goal remains active; no reliable edge or win is established.",
        "", "MATERIAL DATA FINDING",
        "Recovered every ten-minute slice on twelve first-of-month 2024 sample days: 1,728 public unauthenticated requests, 7,492,990 decoded bytes. No paid API or account used.",
        f"All {field['csv_reports']:,} historical CSV reports match native messages one-to-one by instrument and capture timestamp; trade timestamp and side also match.",
        f"These CSV exports use order limit price p and last fill quantity l. In {field['csv_reports'] - field['cumulative_quantity_matches']:,} reports, l differs from cumulative filled quantity z. Actual executed order value is z times average fill price ap.",
        "The current Tardis source mapper uses z; this finding applies to these archived exports and must not be generalized to every version. Original results remain intact as tests of the original proxy.",
        "All observed raw statuses are FILLED. Neither q nor z measures future residual liquidation demand, and the one-second report throttle still omits orders.",
        "", "FROZEN TEST",
        "January–June visible completed orders set the 99th-percentile executed-notional threshold. July–December prices were already exposed in prior studies: this is discovery, not fresh confirmation.",
        "First large report after a five-minute refractory window. Five-minute startup and post-recovery cooldowns. No future disconnect deletes an earlier submitted position.",
        "24 configurations: BTC/SOL, follow/reverse, 30/120-second holds, taker entry or passive entry 8/16bp from the signal midpoint.",
        "Capture-clock decisions, 250ms processing, one-second outbound/return latency, physical exchange-clock fills with <=250ms book age. Entry/exit acknowledgments and partial inventory remain explicit.",
        "Taker fees 6bp plus 1bp adverse allowance EACH side. Passive entry 3bp, taker exit 6bp plus 1bp exit allowance. Observed spread/depth crossing adds to costs. Doubled fees, three-second delays and alternate passive fill assumptions are recorded.",
        "$10,000 daily cash reset and maximum $1,000 order; <=10% predecision visible size. Results are summed isolated-day P&L, not continuous wealth or an allocated multi-asset portfolio.",
        ""]
    event_counts = {}
    for symbol, settings in ASSETS.items():
        native, overlap, prior = 0, 0, 0
        for day in DATES[6:]:
            current = pd.read_parquet(OUT / symbol / "panels" / f"{day}_events.parquet")
            old = pd.read_parquet(ROOT / "research_scout" / settings["source"] / "panels" / f"{day}_events.parquet")
            native += len(current)
            prior += len(old)
            overlap += len(set(current.received_us) & set(old.received_us))
        event_counts[symbol] = native
        lines.append(f"{symbol}: threshold ${spec['threshold_executed_order_notional'][symbol]:,.6f}; {native} events versus {prior} prior proxy events; {overlap} exact trigger clocks overlap.")
    lines += ["", "BASELINE: instrument / rule | gross $ | net $ | completed trades"]
    for key, candidate in result["results"].items():
        base = candidate["scenarios"]["base"]
        net = f"{base['net_dollars']:+.6f}" if base["complete"] else f"UNKNOWN (closed subtotal {base['closed_subtotal']:+.6f})"
        lines.append(f"{key} | {base['gross_closed_subtotal']:+.6f} | {net} | {base['trades']}")
    lines += ["", f"Baseline outcomes: {counts}.",
        "The only positive baseline is BTC passive reverse/16bp/120s: +$1.314932 on ONE trade. Deleting that date leaves $0. Doubled fees give +$0.426280; three-second delay +$0.099953 on two trades, with -$1.854531 after deleting its best date. This is not reliable outperformance.",
        "Two SOL 30-second taker variants have unresolved exits. Their closed losses are subtotals, not complete net returns. Unknown inventory is not erased or assigned a zero outcome.",
        "No candidate qualified to open independent later validation dates. The field repair materially changes event selection but does not rescue the strategy family in this sample.",
        "", "INDEPENDENT VERIFICATION",
        f"Reconstructed {audit['native_events_reconstructed']} events directly from cumulative fills and calibration quantiles; verified raw/panel/code hashes and causal cooldowns.",
        f"Reconciled {audit['priced_trades_across_dependent_scenarios']:,} priced trades across dependent scenarios, {audit['maker_fill_records']:,} maker-fill records and {audit['no_fill_attempts_checked']:,} no-fill attempts against the underlying tapes.",
        f"Maximum cash arithmetic difference: ${audit['maximum_cash_error_dollars']:.3g}. Fourteen focused current-module tests pass, including seven new native-field, clock, inventory and recovery-boundary tests.",
        "Trade-through models cannot prove actual queue priority or live fills. No market-impact or private-order acceptance evidence is claimed. Monthly samples and prior selection do not establish statistical reliability.",
        "Current session: 100 configurations / 124 evaluated implementation versions; these are dependent trials. 72 accumulated focused tests support implementation correctness, not profitability.",
        "", "SOURCE REFERENCES",
        "https://docs.tardis.dev/api/http-api-reference.md",
        "https://github.com/tardis-dev/tardis-node/blob/master/src/mappers/binance.ts",
        "https://docs.tardis.dev/historical-data-details/binance-futures", ""]
    (OUT / "REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    checkpoint_path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint.update(status="active", reliable_edge_found=False, current_configurations=100,
        implementation_versions=124, focused_tests_total=72, native_liquidation_events=event_counts,
        native_liquidation_candidates=[], native_liquidation_accounting_verified=True,
        native_liquidation_field_audit=str(OUT / "FIELD_AUDIT.txt"),
        report=str(OUT / "REPORT.txt"),
        remaining_evidence_work="Keep strictly HFT. Native executed-size liquidation rules failed the frozen reliability screen; do not repeatedly retune this exposed family. Assess distinct exchange-specific equity/ETF trade and quote information already available locally, with conservative fees and explicit feed/queue limits.")
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(json.dumps({"report": str(OUT / "REPORT.txt"), "counts": counts, "goal": "active"}, indent=2))


if __name__ == "__main__":
    main()
