"""Freeze a local-only millisecond ETF sweep experiment; no network client is used."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from research.exact_json import integer_default

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research_scout/equity_sweep_hft_20261002"
OUT = ROOT / "research_scout/databento_fast_sweep_20261002"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, indent=2, default=integer_default, allow_nan=False) + "\n")


def main():
    old = json.loads((PARENT / "specification.json").read_text())
    result = json.loads((PARENT / "screen_results.json").read_text())
    audit = json.loads((PARENT / "candidate_verification.json").read_text())
    assert audit["verified"] and audit["results_sha256"] == sha(PARENT / "screen_results.json")
    OUT.mkdir(exist_ok=True)
    assert not (OUT / "specification.json").exists()
    code = ("research/equity_sweep_fast.py", "research/equity_resilience.py", "research/exact_json.py",
            "research_scout/run_databento_fast_20261002.py")
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "user_scope": "Use accessible Databento data without paid calls. This experiment reads local DBN files only: no network client, API, new download or account operation.",
        "hypothesis": "An immediate response to a large completed multi-price ETF sweep may capture a short continuation or reversal before the previously tested500ms+signal waiting period.",
        "sources": old["sources"], "symbols": old["symbols"],
        "parent_sessions": result["session_files"], "inherited_unknown_symbol_dates": result["source_errors"],
        "group_scope": "All563previously source-verified prestate-qualified groups from1922023sessions; not just the172old selected events. Same>=100000USD,single known side,monotonic multiple prices spanning>=.01,quantity>=preceding directional touch,matching receive/event timestamps within complete F_LAST group,valid fresh immediate prestate. Parent earlier group-rejection enumeration remains a required independent audit before any reliability promotion.",
        "causal_signal": "Decision=first whole millisecond STRICTLY after burst receive+1ms. Information cutoff decision-1ms.09:30:05..09:39:30ET only. Latest completed F_LAST book strictly before cutoff must complete the burst,be valid,have capture and event ages<=5ms,native event<=cutoff; no fallback to older valid state. Cent prices,spread<=5bp,bid AND ask remain strictly displaced in burst direction. No additional return or displacement tuning.",
        "sizing": "Cent-rounded buy limit102%of current ask. Fixed order quantity=min(floor10000USD/limit,floor10%current bid quantity,floor10%current ask quantity). Causal aggressive ask-to-bid cost<=12bp. No future resizing of requested order.",
        "selection": "Separate long-only follow_buy_sweep and fade_sell_sweep. Per rule sort by decision,descending burst quantity/prestate touch quantity,descending burst notional,symbol,source index.6s global and60s symbol cooldown irrespective of hypothetical fills. No simultaneous positions under the planned<=5s holding periods, conditional on prompt fills and exits.",
        "hold_ms": [1000, 5000],
        "cases": [
            {"name": "base_1ms", "delay_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "delay_5ms", "delay_ms": 5, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "delay_25ms", "delay_ms": 25, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "delay_250ms", "delay_ms": 250, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "fees_2x", "delay_ms": 1, "fee_multiple": 2, "adverse_multiple": 1},
            {"name": "adverse_2x", "delay_ms": 1, "fee_multiple": 1, "adverse_multiple": 2},
            {"name": "clock_minus_1ms", "delay_ms": 1, "clock_shift_ms": -1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "clock_plus_1ms", "delay_ms": 1, "clock_shift_ms": 1, "fee_multiple": 1, "adverse_multiple": 1}],
        "timing": "Entry reference=decision+50us processing+assumed one-way delay+fixed scenario clock shift. Exit reference=entry reference+holding period. Same deterministic timeline per scenario and event; no favorable future timestamp selection. Latency is an explicit research assumption, not measured client access. This aggregated feed does not identify IEX or justify applying an IEX-specific speed bump.",
        "reference": "Use last completed book strictly before each fixed RECEIVE-clock arrival,with a later quote bracketing it. Exact equal-capture boundary unknown. Require valid maintained book,receive and native event age<=250ms and native event<=arrival. EQUS.MINI receive chronology is a proxy timeline,not an invented unified matching-engine book.",
        "conditional_fills": "Aggressive IOC buy at observed ask if<=fixed limit;assumed filled shares=min(fixed requested quantity,future displayed ask size). Unfilled remainder canceled. Force sell assumed filled quantity at observed bid at fixed exit time only if displayed bid size covers it;otherwise remaining inventory and PnL unknown. Commission applies even to partial fill. Hidden liquidity,routeability,NBBO protection,actual acceptance and private fills are unproven.",
        "costs": old["costs"], "bad_data": old["bad_data"], "feed_limits": old["feed_limits"],
        "aggregation": "Report each rule/hold/case separately;192calendar dates. Any inherited bad-clock symbol on a date makes that date's admission unknown,even if another symbol was selected; unknown events/dates are never zero. Separate known event component,observed event cohort and full calendar. Diagnostic sums are not an executed funded portfolio. Show date concentration and drop-best3dates for positive known components.",
        "validation": "Eight focused tests passed. Screen without returns first,then exactly4economic rule/hold configurations with8stress cases. Audit source signal/timing/quantity/cash independently. Positive result needs complete clock/depth/unknown treatment,earlier source-rejection enumeration,NBBO/execution corroboration,multiple-search controls and newly frozen later temporal validation. No2024+outcomes opened in this experiment.",
        "parent_screen_sha256": sha(PARENT / "screen_results.json"),
        "parent_candidate_audit_sha256": sha(PARENT / "candidate_verification.json"),
        "code_sha256": {p: sha(ROOT / p) for p in code},
        "economic_configurations_executed": 0, "actual_execution_verified": False, "reliable_edge_established": False,
    }
    write(OUT / "specification.json", spec)
    checkpoint = ROOT / "research_scout/hft_edge_search_20260930/latest_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert state["focused_tests_total"] == 421
    state.update(focused_tests_total=429, updated_at_utc=datetime.now(UTC).isoformat(),
                 active_research_jobs=["Local Databento immediate ETF sweep screen"],
                 databento_fast_specification=str(OUT / "specification.json"),
                 remaining_evidence_work="Local-only Databento experiment frozen;8 focused tests passed. Screen563previously verified large sweeps on1922023sessions at millisecond decision timing,then fixed1s/5s depth-bounded conditional replay if signals exist. No paid calls.")
    write(checkpoint, state)
    print(json.dumps({"specification_sha256": sha(OUT / "specification.json"), "sessions": len(spec["sources"])}))


if __name__ == "__main__":
    main()
