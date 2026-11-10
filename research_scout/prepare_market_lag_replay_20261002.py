"""Freeze both declared market-lag response controls before future-price calculations."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research_scout.prepare_market_lag_flow_20261002 import OUT as FLOW
from research_scout.prepare_market_lag_flow_20261002 import ROOT, sha

TARGET = ROOT / "research_scout/market_lag_targets_hft_20261002/batch02"
OUT = ROOT / "research_scout/market_lag_response_hft_20261002"


def main():
    flow_audit = json.loads((FLOW / "independent_verification.json").read_text())
    assert flow_audit["verified"] and flow_audit["results_sha256"] == sha(FLOW / "screen_results.json")
    events = pd.read_parquet(FLOW / "selected.parquet").to_dict("records")
    assert len(events) == 1 and events[0]["symbol"] == "TRXUSDT"
    OUT.mkdir(exist_ok=True)
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Fifteen-second response in a lagging perpetual after a coherent major-coin shock",
        "relationship": "Both follow_common_move and fade_common_move were declared before the source/target/flow screens. One TRX event survives exactly 49 preselected native BTC/ETH minutes from six full cached BTC days; retain the separate earlier 60 sparse windows. This is dependent development research, not independent validation or a chosen post-return winner. One event is inadequate for reliability.",
        "events_path": str((FLOW / "selected.parquet").relative_to(ROOT)), "events_sha256": sha(FLOW / "selected.parquet"),
        "flow_results_sha256": sha(FLOW / "screen_results.json"), "flow_audit_sha256": sha(FLOW / "independent_verification.json"),
        "target_results_sha256": sha(TARGET / "screen_results.json"), "target_audit_sha256": sha(TARGET / "independent_verification.json"),
        "rules": {"follow_common_move": "Sell the lagging target after the common down move, or buy after an up move.",
                  "fade_common_move": "Opposite direction control, with identical causal inputs, timing, quantity constraints and costs."},
        "engine_rule_mapping": {"follow_common_move": "follow_shock", "fade_common_move": "fade_shock"},
        "entry_signal": "Latest native TRX full BBO strictly before decision minus 250ms, with capture/T/E age in (0,250ms] of that cutoff and consistent native clocks. Match full price, quantity, ID and capture/T/E fields to the independently audited original all-symbol signal. Do not change the quote or quantity across scenarios.",
        "quantity": "Reuse the unchanged tested causal planner: floor(min(200/(1.01*directional quote),10% of directional displayed quantity)/10)*10 base units. Minimum 100 USDT entry notional. Fixed before transmission, no future-depth resizing. Reserve full notional plus 2% from an independent 10000-USDT daily account; no leverage. Ten-unit increment and minimum are conditional sizing assumptions, not verified historical exchange filters.",
        "grids": {"TRXUSDT": "0.00001"}, "historical_price_grid_verified": False,
        "historical_lot_size_verified": False,
        "grid_evidence": "The assumed 0.00001 increment is consistent with the already observed causal native TRX quotes. All replay prices must lie on it. No current exchangeInfo is substituted for historical order permissions or filters; these remain unverified and forbid deployment/reliability promotion.",
        "timing": "Processing 50ms plus outbound delay. Entry ACK after another outbound delay. Exit decision 15 seconds after that ACK, then 50ms processing plus outbound. Planned inventory below 30 seconds including clock stress. An unresolved exit has unknown actual duration.",
        "entry_order": "Fixed-quantity FOK with 10bp collar from the causal directional quote, rounded inward to the assumed price increment. Every compatible native transaction-clock state must offer sufficient entire touch size inside the limit to establish a conditional fill. All prices outside means no fill; mixed prices or inadequate touch depth means unknown.",
        "exit_order": "Full-quantity marketable exit; all compatible native states need sufficient entire touch depth. No deeper or passive fills invented. Unknown submitted inventory invalidates full P&L and halts later same-date events. There is one selected event in this cohort.",
        "execution_clock": "Use native T for matching, E for publication and capture for information availability. Include the entire predecessor T tie group and all states in arrival +/-1ms, or +/-100ms stress; require a later successor. Source clock/ID regression makes execution evidence unknown, not a retroactive no-order. Overlapping disconnect makes an envelope unknown. Public-book execution remains conditional, not a private-fill assertion.",
        "funding": "Native markPrice captured before the cutoff and at most five seconds old in capture/publication must show next funding later than decision+24.2 seconds+1 second. No funding income credited. Missing clearance prevents entry.",
        "costs": {"taker_bps_each_side": 6, "adverse_bps_each_side": 1},
        "scenarios": [
            {"name": "base", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "fees_2x", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 2, "adverse_multiple": 1},
            {"name": "adverse_2x", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 2},
            {"name": "latency_250ms", "delay_ms": 250, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "latency_3s", "delay_ms": 3000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "clock_100ms", "delay_ms": 1000, "clock_ms": 100, "fee_multiple": 1, "adverse_multiple": 1}],
        "jobs": [{"date": e["date"], "offset": int(e["offset_minutes"]), "symbol": e["symbol"]} for e in events],
        "download": {"exchange": "binance-futures", "slice_minutes": 2, "channels": ["bookTicker", "markPrice"],
                     "workers": 1, "per_slice_decoded_cap": 32_000_000, "request_deadline_seconds": 120,
                     "authenticated": False, "paid_fallback": False},
        "progression": "Retain both controls and all stresses. No tuning signal thresholds, exit duration or side on this event. Even a positive conditional result needs historical filter verification, a prospective broader coverage plan and truly later validation; a single event cannot establish reliability. No 2025 selection data in this replay.",
        "economic_implementations_run": 0, "actual_execution_verified": False, "selection_2025_opened": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"events": len(events), "rules": 2, "scenario_cases": 12, "specification_sha256": sha(OUT / "specification.json")}))


if __name__ == "__main__":
    main()
