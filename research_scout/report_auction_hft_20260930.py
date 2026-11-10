"""Publish the original seconds-only auction screen, including its limitations."""

import json

import numpy as np
import pandas as pd

from research_scout.run_auction_hft_20260930 import OUT, ROOT


def main():
    results = json.loads((OUT / "results.json").read_text())
    spec = json.loads((OUT / "specification.json").read_text())
    verification = json.loads((OUT / "verification.json").read_text())
    repair = json.loads((OUT / "precise_ledgers/repair.json").read_text())
    steps = np.asarray([high - low - 500000000
                        for source in results["source_audits"]
                        for symbol in source["symbols"]
                        for low, high in symbol["ambiguity_intervals_ns"]], dtype=np.int64)
    panels = pd.concat([pd.read_parquet(OUT / "panels" / f"{day}.parquet") for day in spec["dates"]])
    execution = panels.loc[panels.clock.eq("event")]
    clock_audit = {
        "source_event_backsteps": len(steps),
        "backstep_ns_quantiles": {str(q): float(np.quantile(steps, q)) for q in (0, .25, .5, .9, .99, 1)},
        "fraction_backsteps_at_most_1ms": float((steps <= 1000000).mean()),
        "fraction_backsteps_at_most_10ms": float((steps <= 10000000).mean()),
        "execution_targets": len(execution),
        "ambiguous_execution_targets": int(execution.ambiguous.sum()),
        "sampled_target_source_delay_ns_quantiles": {str(q): float(panels.source_delay_ns.quantile(q)) for q in (0, .5, .99, 1)},
        "interpretation": "Multi-venue aggregate snapshots cannot be reconstructed as one matching-engine stream by sorting component ts_event values. The original +/-250ms backstep guard creates unknown paths, not evidence of missing quotes or zero returns. Capture-order replay with explicit timing uncertainty is a distinct execution proxy, not verified routable venue fills.",
        "source_documentation": "https://databento.com/docs/standards-and-conventions/common-fields-enums-types",
    }
    (OUT / "clock_audit.json").write_text(json.dumps(clock_audit, indent=2) + "\n")
    lines = [
        "SECONDS-ONLY ETF OPENING-AUCTION SCREEN — ORIGINAL EVENT-CLOCK VERSION",
        "No qualified candidate; all eight configurations have incomplete execution paths.",
        "Closed-trade subtotals below are NOT total strategy returns. Unknown attempts remain unknown.",
        "",
        f"Data: {len(spec['dates'])} sessions; {sum(s['raw_rows'] for s in results['source_audits']):,} raw quote rows; "
        f"{results['auction_audit']['raw_auction_rows']:,} native auction messages scanned.",
        "431 development sessions (2023-24), 235 selection sessions (2025); both historically exposed.",
        "No 2026 quote-price files were opened in this batch. Known degraded source dates excluded upfront.",
        "Decision 09:29:50 ET; 250ms processing, 1s outbound/return acknowledgement (3s stress).",
        "Hold 15 or 30 seconds after entry acknowledgement. Long SPY/SH or UPRO/SPXU; no auction fill assumed.",
        "$10,000 reset per date; integer shares capped at 10% predecision displayed size, with 1% cash reserve.",
        "$0.0075/share, $1 minimum each side; sell levy 0.30bp + $0.0002/share; 1bp adverse allowance each side.",
        "Entry FOK with a 5bp causal price collar; no resizing to future depth and no invented deeper liquidity.",
        "",
        "BASELINE CLOSED SUBTOTALS (NOT COMPLETE STRATEGY NET RETURNS)",
        "Rule | Development closed $ / trades | 2025 closed $ / trades | Total net",
    ]
    for name, candidate in results["results"].items():
        scenario = candidate["scenarios"]["base"]
        dev, sel = scenario["development_2023_2024"], scenario["selection_2025"]
        lines.append(f"{name} | {dev['closed_subtotal']:+.4f} / {dev['trades']} | "
                     f"{sel['closed_subtotal']:+.4f} / {sel['trades']} | UNKNOWN")
    lines += [
        "",
        "Clock audit: 3,700,782 backwards source-event steps, median about 28 microseconds;",
        "99.60% are at most 1ms. The original 250ms guard marks 3,883 of 15,984 execution targets ambiguous.",
        "Sorting anonymized multi-venue snapshots by their component event clocks is not a venue book replay.",
        "The failed completion gate is partly a modeling limitation, not proof that all rules lose money.",
        "",
        "Serialization repair: optional timestamp columns rounded by up to 128ns when pandas introduced floats.",
        "Rebuilt exact nullable integer timestamps from the unchanged simulation records in precise_ledgers/.",
        "Original ledgers preserved; EVERY non-clock column is identical (signals, fills, quantities, fees, P&L).",
        "This repair is not a new strategy or independent evidence.",
        "",
        f"Independent checks: {verification['archived_auction_snapshots_reconciled']:,} auction snapshots reconciled; "
        f"{verification['quote_sources_hash_verified']} quote source hashes verified;",
        f"{verification['native_quote_targets_checked']:,} native as-of targets checked across "
        f"{verification['calendar_selected_native_check_sessions']} calendar-selected sessions (spot checks, not exhaustive).",
        f"All {verification['priced_trades_across_dependent_scenarios']:,} priced dependent-scenario trades reconciled; "
        f"{verification['unresolved_attempts_retained']:,} unresolved attempts retained; "
        f"maximum cash error ${verification['maximum_cash_error_dollars']:.3g}.",
        "",
        "Next: preserve this version and correct aggregate-quote chronology with a separately frozen execution model.",
        "No claim of a reliable edge, live fills, competition outperformance, or a win.",
    ]
    assert verification["verified"] and repair["every_nonclock_column_identical"]
    (OUT / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    checkpoint_path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint.update(current_configurations=108, implementation_versions=140, focused_tests_total=80,
                      report=str(OUT / "REPORT.txt"), auction_original_verified=True,
                      auction_original_candidates=[], auction_original_complete_configurations=0,
                      remaining_evidence_work="Strictly HFT. Correct multi-venue aggregate quote chronology under a newly frozen capture-order/timing-uncertainty proxy; keep original signals, costs and sizing. Unknown entry/depth/exit paths must remain explicit. No reliable edge and no 2026 outcome inspection authorized by an observed success yet.")
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
