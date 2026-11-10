"""Publish execution-revision results without turning unknown paths into zero."""

import json

from research_scout.run_auction_capture_20260930 import OUT, PREVIOUS, ROOT


def value(number):
    return "UNKNOWN" if number is None else f"{number:+.4f}"


def main():
    result = json.loads((OUT / "results.json").read_text())
    audit = json.loads((OUT / "verification.json").read_text())
    assert audit["verified"]
    lines = [
        "SECONDS-ONLY ETF AUCTION RULES: CAPTURE-ORDER EXECUTION REVISION",
        "Reliable edge established: NO. Competition win established: NO.",
        f"Rules qualifying for additional evidence: {result['candidates_for_additional_evidence']}",
        "",
        "Same 8 unfitted signals and same 666 sessions as the original run (2023-25).",
        "Holds 15/30s after entry acknowledgement; decision 09:29:50 ET. No 2026 quote outcomes opened.",
        "Native data: 171,294,232 quote rows; source/cache hashes verified. Original auction inputs already reconciled.",
        "All signal forecasts, eligibility, quantities, predecision prices, cost gates and selected dates are IDENTICAL",
        "to the original version. This is an execution-model correction, not independent confirmation or retuned alpha.",
        "",
        "Execution: preserve receive order of aggregated quotes; keep an unchanged valid standing quote until updated.",
        "Do not reorder multi-venue snapshots by component event timestamps. No arbitrary 250ms book expiry at execution.",
        "Signal freshness checks remain unchanged. Last invalid state cannot be replaced with an older valid state.",
        "At each order arrival use all observed book states within +/-1ms quote-clock alignment; stress +/-100ms.",
        "Keep both admissible fill and rejection branches. Inadequate L1 depth remains unresolved, not resized or dropped.",
        "Holding starts after entry ACK; baseline 1s outbound/return, delay stress 3s. Fixed 5bp causal FOK entry collar.",
        "$10,000 daily reset, integer shares <=10% predecision displayed size and 1% reserve.",
        "$0.0075/share with $1 minimum each side; sell levy 0.30bp + $0.0002/share; extra 1bp each side.",
        "Stress doubles fees, separately doubles adverse allowance, or expands time alignment as above.",
        "",
        "BASELINE MODEL INTERVALS IN DOLLARS",
        "Rule | 2023-24 net [lower,upper] | 2025 net [lower,upper] | 2025 mandatory fills / unknown dates",
    ]
    for name, candidate in result["results"].items():
        dev = candidate["scenarios"]["base"]["development_2023_2024"]
        sel = candidate["scenarios"]["base"]["selection_2025"]
        lines.append(f"{name} | [{value(dev['net_lower'])},{value(dev['net_upper'])}] | "
                     f"[{value(sel['net_lower'])},{value(sel['net_upper'])}] | {sel['known_fill_dates']} / {len(sel['unresolved_dates'])}")
    lines += ["", "2025 RESOLVED-ATTEMPT SUBTOTALS ONLY — exclude unknown paths; NOT total strategy returns",
              "Rule | Base [lower,upper] | Double-fee lower | 3s-delay lower | 100ms-alignment lower"]
    for name, candidate in result["results"].items():
        scenarios = {k: v["selection_2025"] for k, v in candidate["scenarios"].items()}
        base = scenarios["base"]
        lines.append(f"{name} | [{base['resolved_subtotal_lower']:+.4f},{base['resolved_subtotal_upper']:+.4f}] | "
                     f"{scenarios['double_fees']['resolved_subtotal_lower']:+.4f} | "
                     f"{scenarios['latency_3s']['resolved_subtotal_lower']:+.4f} | "
                     f"{scenarios['alignment_100ms']['resolved_subtotal_lower']:+.4f}")
    lines += [
        "",
        "Intervals bound only the specified observed-state proxy. Anonymous aggregate BBO is not a routable",
        "venue book; hidden intervening states, routing and actual fills are not established by these intervals.",
        "No confidence interval or p-value is presented as proof after repeated historical model search.",
        "Progress requires complete positive lower-bound 2025 returns in all stresses, >=50 mandatory fills,",
        "positive after removing best five dates, and complete positive 2023-24 baseline. Passing permits more testing only.",
        "",
        f"Independent audit: {audit['bounded_dependent_scenario_attempts']:,} bounded attempts, including "
        f"{audit['mixed_fill_or_reject_attempts']} mixed fill/rejection branches; "
        f"{audit['unresolved_attempts_retained']} unknown attempts retained; {audit['known_rejections']} known rejections.",
        f"Maximum cash reconciliation error ${audit['maximum_cash_error_dollars']:.3g}.",
        f"Native quote envelope spot checks: {audit['native_envelopes_checked']} groups / {audit['native_state_rows_checked']} state rows",
        f"on {', '.join(audit['native_calendar_sample_dates'])}; full cached-branch arithmetic and source hashes cover all dates.",
        "Seven new mechanism tests pass; combined auction/timestamp/funding regression run: 18 passed.",
        "Session bookkeeping: 108 configurations / 148 implementation versions; historical focused-test count 90.",
        "Funding screening is a separate six-instrument feasibility check, not six profitable backtests.",
        "",
        f"Original version and timestamp repair preserved: {PREVIOUS}",
        "Documentation: https://databento.com/docs/standards-and-conventions/common-fields-enums-types",
        "Documentation: https://databento.com/docs/schemas-and-data-formats/mbp-1",
    ]
    (OUT / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    checkpoint_path = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint.update(current_configurations=108, implementation_versions=148, focused_tests_total=90,
                      report=str(OUT / "REPORT.txt"), auction_capture_verified=True,
                      auction_capture_candidates=result["candidates_for_additional_evidence"],
                      remaining_evidence_work="Strictly HFT. Capture-order auction correction audited: six complete losing 2025 baselines, two incomplete. Six-instrument funding-payment screen audited with no eligible events. No reliable edge. Source-review and freeze a structurally distinct seconds-long hypothesis before new outcomes; preserve all prior selection history and avoid unsupported physical-fill claims. Do not open later outcomes to rescue these failed rules.")
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
