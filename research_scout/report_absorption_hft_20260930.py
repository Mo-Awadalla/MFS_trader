"""Record completed discovery and its execution-clock correction, without promotion."""

import json
from datetime import UTC, datetime

import pandas as pd

from research_scout.fetch_absorption_native_20260930 import OUT as NATIVE
from research_scout.run_absorption_hft_20260930 import OUT, ROOT


def main():
    original = json.loads((OUT / "results.json").read_text())
    audit = json.loads((OUT / "verification.json").read_text())
    corrected = json.loads((NATIVE / "results.json").read_text())
    verified = json.loads((NATIVE / "verification.json").read_text())
    assert audit["verified"] and verified["verified"]
    assert not original["candidates_for_additional_evidence"] and not corrected["candidates_for_additional_evidence"]
    old = ["BTC/SOL SAMPLED PRICE RESILIENCE AND LEVEL BREAK: ORIGINAL PUBLICATION-CLOCK VERSION",
           "Reliable edge established: NO. Competition win established: NO.",
           "This version is superseded for execution by native_transaction_clock/REPORT.txt.", "",
           "Eight fixed rules: BTC/SOL x fade defended level / follow first observed break x 15/30s ACK-based holds.",
           "Six first-of-month Jul-Dec 2024 dates. Jul-Sep development, Oct-Dec selection; all globally exposed discovery.",
           "1,397 causal defended-level events and 914 subsequent breaks. This is sampled price resilience, not proof of hidden orders.",
           "250ms processing + 250ms outbound/return; delays stressed to 1s/3s. $1,000 maximum ticket,",
           "10% of predecision opposite touch size, $100 minimum, $10,000 reset per date, fixed native quantity steps.",
           "Five-bp causal FOK entry collar, market exit against observed depth. 6bp taker + 1bp adverse allowance EACH side.",
           "Double-fee and extra-adverse stresses; no rebates, funding credit or favorable resizing.", "",
           "IMPORTANT CLOCK ERRATUM: Binance normalized book timestamp matches raw E (publication), not raw T (transaction).",
           "The original execution model used E as a transaction-time proxy and imposed a 250ms quote expiry.",
           "All eight six-day totals were incomplete. Closed subtotals below are NOT complete strategy returns.", "",
           "Rule | full net | priced closed subtotal | completed trades"]
    for symbol, rules in original["results"].items():
        for name, rule in rules.items():
            b = rule["scenarios"]["base"]["all"]
            old.append(f"{symbol}/{name} | UNKNOWN | {b['closed_subtotal']:.4f} | {b['trades']}")
    old.extend(["", "Independent original arithmetic/event audit passed: 12,423 dependent priced trades, 165 unresolved attempts,",
                "34 known FOK rejections. Exact CSV-asof spot checks: 3,990 targets on first July date, both assets.",
                "These checks validated the specified publication-clock model, not physical fills.",
                "Original specification, source hashes, events, quotes, results and ledgers remain unchanged.",
                "All requested execution targets were subsequently reconstructed from sequenced native depth; see correction report."])
    (OUT / "REPORT.txt").write_text("\n".join(old) + "\n", encoding="utf-8")

    lines = ["BTC/SOL PRICE RESILIENCE AND BREAK: NATIVE TRANSACTION-CLOCK CORRECTION",
             "Reliable edge established: NO. Competition win established: NO. Candidates advancing: [].", "",
             "Same eight rules, signals, dates, quantities, costs, processing delays and ACK-based holds as the original study.",
             "No parameter rescue and no fresh test dates. This adds 8 implementation versions, not 8 new hypotheses.",
             "All six first-of-month Jul-Dec 2024 dates were already exposed historical discovery.", "",
             "EXECUTION CORRECTION",
             "Match each normalized initial top-five snapshot to its exact raw capture/E pair, check its delta quantities,",
             "then follow pu/u-sequenced native depth updates in transaction time T until the first successor after the order.",
             "Include T-before-order updates even if E publication occurs after the order. Do not expire an unchanged book",
             "merely because no top-five update was published in 250ms. Native gaps/backtracks would remain unknown.",
             "At equal transaction timestamps retain pre/post-update states. Initial five levels delimit known price coverage;",
             "deleted top levels cannot be replaced with invented deeper liquidity. Insufficient coverage stays unknown.",
             "A fill/unknown branch retains possible inventory and halts later orders that date. FOK prices and quantities",
             "remain fixed from predecision data. Long/short cash intervals include every observed admissible fill branch.", "",
             "BASELINE: six independent daily reset accounts, dollar sums, no annualization or portfolio aggregation",
             "Rule | full net [lower,upper] | closed subtotal [lower,upper] | mandatory trades | unknown attempts"]
    diagnostics = []
    for symbol, rules in corrected["results"].items():
        for name, rule in rules.items():
            b = rule["scenarios"]["base"]["all"]
            total = f"[{b['net_lower']:.4f},{b['net_upper']:.4f}]" if b["complete"] else "UNKNOWN"
            f = pd.read_parquet(NATIVE / symbol / f"{name}_base_attempts.parquet")
            priced = f.loc[f.status.eq("bounded")]
            unresolved = f.loc[f.status.str.startswith("unresolved")]
            lines.append(f"{symbol}/{name} | {total} | [{b['closed_lower']:.4f},{b['closed_upper']:.4f}] | "
                         f"{b['mandatory_trades']} | {len(unresolved)}")
            diagnostics.append({"symbol": symbol, "rule": name, "complete": b["complete"],
                                "gross_lower": float(priced.gross_lower.sum()), "gross_upper": float(priced.gross_upper.sum()),
                                "cost_lower": float(priced.cost_lower.sum()), "cost_upper": float(priced.cost_upper.sum()),
                                "unknowns": unresolved.reindex(columns=["date", "event_id", "status", "reason"]).to_dict("records")})
    lines.extend(["", "For incomplete rules, closed subtotals exclude unresolved inventory and all later halted paths;",
                  "they are not net strategy returns. Configurations overlap; never add their dollar sums into a portfolio.",
                  "All four SOL baseline rules are complete and lose on every sampled date. All four BTC baselines remain",
                  "incomplete because some submitted orders need more depth than the known range. No missing fill is dropped.", "",
                  "COMPLETE SCENARIO RESULTS / ALL 40 CANDIDATE-SCENARIO COMBINATIONS"])
    complete = []
    for symbol, rules in corrected["results"].items():
        for name, rule in rules.items():
            for scenario, result in rule["scenarios"].items():
                s = result["all"]
                if s["complete"]:
                    complete.append(s)
                    lines.append(f"{symbol}/{name}/{scenario}: [{s['net_lower']:.4f},{s['net_upper']:.4f}]")
    lines.extend([f"Complete: {len(complete)}/40. Every complete result has a negative upper endpoint.",
                  "Incomplete scenarios remain unknown; stress losses are dependent replays, not independent samples.", "",
                  "GROSS ECONOMICS OF RESOLVED PATHS ONLY",
                  "Rule | gross [lower,upper] | commission + adverse allowance [lower,upper]"])
    for d in diagnostics:
        lines.append(f"{d['symbol']}/{d['rule']} | [{d['gross_lower']:.4f},{d['gross_upper']:.4f}] | "
                     f"[{d['cost_lower']:.4f},{d['cost_upper']:.4f}]")
    lines.extend(["", "These signals do not demonstrate an economic margin over conservative execution costs on this sample.",
                  "Do not spend fresh outcome data tuning these failed thresholds, holding periods or fee assumptions.", "",
                  "AUDIT",
                  f"{verified['native_targets_checked']:,} unique execution targets checked, including unreached targets and all stresses.",
                  f"{verified['native_raw_files_hashed']:,} public raw slices; 3,398,242,245 decoded bytes / 774,995,770 compressed bytes; no paid API.",
                  f"{sum(a['raw_messages'] for a in corrected['source_audits']):,} raw depth messages scanned.",
                  f"{verified['unique_raw_proof_lines_reconciled']:,} unique proof lines independently matched to raw files.",
                  f"{verified['target_tie_branches']} targets had transaction-timestamp ties; before/after alternatives retained.",
                  f"{verified['formerly_stale_targets_with_continuous_native_state']} old-age targets had continuous native state through the order.",
                  f"{verified['targets_with_any_native_state_different_from_E_asof_snapshot']:,} targets had at least one native state different from their publication-clock snapshot.",
                  "Source E-T delay: median2ms, p90=10ms, p99=29.74ms, maximum133ms across selected source states.",
                  f"{verified['bounded_attempts']:,} dependent closed attempts; {verified['unresolved_attempts']} unresolved attempts retained; {verified['rejected_fok']} known FOK rejections.",
                  f"Maximum independently reconciled cash error: ${verified['maximum_cash_error_dollars']:.3g}.",
                  "Historical next-funding timestamps in all12 corresponding ticker sources fell on hourly boundaries.",
                  "The frozen completed paths avoid every hourly boundary. Unknown inventory includes any unknown later funding.",
                  "22 new focused cases passed across event detection, standing-book admission and native execution; cumulative112.", "",
                  "SCOPE AND NEXT EVIDENCE",
                  "This is conditional historical feed-state execution. Batched depth data cannot prove every intervening",
                  "matching-engine state, actual order priority or impact. The intervals bound specified timestamp alternatives,",
                  "not every possible physical fill. There is no significant, reliable or live-tradable edge claim.",
                  "Progression required each development/selection period to be complete and positive in every stress,",
                  "baseline>=50 mandatory trades, >=2 positive dates and positive after removing its best date. None passed.",
                  "Session bookkeeping:116 configurations /164 implementation versions. Preserve the full multiple-search history.",
                  "Next research must remain seconds-scale stocks/ETFs/crypto, with an economic mechanism and causal cost gate",
                  "frozen before new outcomes. Do not relabel the failed family or reuse selection results as a holdout.", "",
                  "Primary source documentation:",
                  "https://docs.tardis.dev/historical-data-details/binance-futures.md",
                  "https://docs.tardis.dev/downloadable-csv-files/data-types",
                  "Native E/T and delta mappings above were directly reconciled to the downloaded historical messages."])
    (NATIVE / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (NATIVE / "baseline_diagnostics.json").write_text(json.dumps(diagnostics, indent=2) + "\n")
    erratum = ["BINANCE HISTORICAL QUOTE CLOCK ERRATUM", "",
               "Verified scope: every20,527 requested execution target in the BTC/SOL Jul-Dec2024 absorption study.",
               "The normalized book_snapshot_5 timestamp matched the exact native E publication/event field.",
               "Native T transaction time was separately recovered. E-T was nonnegative, median2ms and maximum133ms",
               "in the selected source snapshots.20,527 states matched native E; this does not mean T always differed.",
               "1,470 requested targets had at least one changed admissible book state after the native-T correction.", "",
               "Earlier Binance execution studies that used the same normalized timestamp are publication-clock proxies,",
               "not audited transaction-time fills. Their original outcomes remain preserved for reproducibility.",
               "No earlier result had established a reliable edge; this erratum does not promote or validate those results.",
               "The new correction applies to absorption execution only. It does not automatically establish semantics",
               "for every historic export, Bybit timestamps, equity component clocks, trade fields or live matching-engine priority.",
               "The normalized capture clocks still define the frozen causal signals; signal thresholds were not changed.",
               f"Corrected experiment and full audit: {NATIVE / 'REPORT.txt'}"]
    (OUT / "CLOCK_ERRATUM.txt").write_text("\n".join(erratum) + "\n", encoding="utf-8")
    checkpoint_path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint.update(updated_at_utc=datetime.now(UTC).isoformat(), status="active", reliable_edge_found=False,
        current_configurations=116, implementation_versions=164, focused_tests_total=112,
        report=str(NATIVE / "REPORT.txt"), absorption_original_verified=True, absorption_native_verified=True,
        absorption_candidates=[], absorption_event_counts={"defended_level": 1397, "subsequent_break": 914},
        absorption_native_targets=20527, absorption_native_bounded_attempts=19406,
        absorption_native_complete_baselines=4, absorption_native_complete_baselines_profitable=0,
        binance_quote_clock_erratum=str(OUT / "CLOCK_ERRATUM.txt"),
        remaining_evidence_work="Strictly HFT. Eight new BTC/SOL price-resilience/break rules fail progression. All four SOL baseline rules complete and losing; BTC baselines incomplete with unknown depth. Native-T correction verified on all20,527 targets, including187 formerly stale targets. Earlier Binance CSV-timestamp fills are publication-clock proxies. No active download or replay jobs remain. Do not reopen later outcomes or retune this family to rescue it. Source-review and freeze a structurally distinct seconds-long cost-aware mechanism; preserve all prior multiple-search history. No reliable edge and no live order authorization.")
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(json.dumps({"complete_scenarios": len(complete), "positive_complete_scenarios": sum(x['net_upper'] > 0 for x in complete),
                      "native_report": str(NATIVE / 'REPORT.txt'), "status": "active", "reliable_edge": False}), flush=True)


if __name__ == "__main__":
    main()
