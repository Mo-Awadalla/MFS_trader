"""Freeze the two declared response controls before their quote outcomes."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research_scout.prepare_spot_perp_clock_20261002 import OUT as PARENT
from research_scout.prepare_spot_perp_clock_20261002 import ROOT, sha

OUT = ROOT / "research_scout/spot_perp_response_hft_20261002"


def main():
    OUT.mkdir(exist_ok=True)
    results = json.loads((PARENT / "screen_results.json").read_text())
    events = pd.read_parquet(PARENT / "selected.parquet")
    assert results["selected_events"] == len(events) == 1
    assert set(events.symbol) == {"ENAUSDT"}
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Fifteen-second perpetual response to the frozen spot/perpetual discrepancy screen",
        "relationship": "Dependent execution follow-through of the two controls declared in the original supply specification. One ENAUSDT event on September 1, 2024 at 00:00:16 UTC; no rule, date, direction or exit time is selected by its future return. One event is inadequate for reliability regardless of its outcome.",
        "events_path": str((PARENT / "selected.parquet").relative_to(ROOT)),
        "events_sha256": sha(PARENT / "selected.parquet"),
        "source_screen_results_sha256": sha(PARENT / "screen_results.json"),
        "rules": {"fade_basis": "Use the selected screen direction: sell the rich perpetual or buy the cheap one.",
                  "follow_basis": "Opposite control using the same selected event and all other gates."},
        "entry_signal": "Use the same full native perpetual BBO strictly before decision minus 250ms; do not replace it with a future quote for any scenario. Require the source-screen signal audit to have passed before P&L. Verify all quote/source-line references and native T/E/capture semantics.",
        "quantity": "floor(min(200/(1.01*directional_entry_quote), 10% of same-side displayed quantity)/100)*100 ENA, fixed at signal. Minimum order 100 USDT. The coarse 100-ENA increment is a conservative conditional sizing assumption, not a verified historical exchange LOT_SIZE rule. No future resizing. Reserve full limit notional and 2% costs from an independent 10000-USDT account; no leverage.",
        "grid": {"price_tick": "0.0001", "quantity_step_assumption": "100",
                 "historical_lot_size_verified": False,
                 "tick_source": "https://www.binance.com/en/support/announcement/detail/aa2bfe791cca4fbc9db2764249b19592",
                 "tick_source_effective_utc": "2024-05-08T06:30:00Z",
                 "launch_source": "https://www.binance.com/en/support/announcement/detail/db4b4fc4fd0349a892eca0c47293d136",
                 "launch_utc": "2024-04-02T12:30:00Z"},
        "timing": "Decision at the frozen grid. Processing 50ms then outbound delay. Entry ACK after an additional outbound delay. Exit decision 15 seconds after ACK, then 50ms processing plus outbound. Planned inventory <=30 seconds even with 3-second outbound/ACK and clock stress. No actual holding-time claim for unresolved exits.",
        "entry_order": "FOK collar 10bp from the causal directional quote, rounded inward to the verified 0.0001 tick. Fixed quantity. Every compatible native transaction-clock BBO must fit the entire quantity at the touch and inside the collar. All prices outside implies no fill; mixed or insufficient depth implies unknown. No passive or deeper fills invented.",
        "exit_order": "Marketable full-quantity exit; every compatible native BBO must have sufficient full touch depth. Preserve unknowns rather than assigning zero. Any later same-date event would halt after an unresolved submitted position; this cohort contains one event.",
        "execution_clock": "Use native bookTicker T as transaction time, E as publication time, and the capture prefix as information time. Source ids and transaction times must not regress; conflicting equal-id updates poison the stream. Physical envelope includes the complete predecessor T group and all groups in arrival +/-1ms (100ms stress); require a successor and valid book/clock/depth in every compatible state. A source disconnect spanning an order interval is unknown. Quotes remain conditional execution evidence, not private fills or proof of queue priority.",
        "funding": "Require a native markPrice message captured before decision minus 250ms, at most five seconds old, with native next-funding time later than the latest possible stressed exit plus one second. Require its event/publication timestamp consistent with capture. No funding payment or forecast rate is credited. Missing/ambiguous advancement prevents an order.",
        "costs": {"taker_bps_each_side": 6, "adverse_bps_each_side": 1},
        "scenarios": [
            {"name": "base", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "fees_2x", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 2, "adverse_multiple": 1},
            {"name": "adverse_2x", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 2},
            {"name": "latency_250ms", "delay_ms": 250, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "latency_3s", "delay_ms": 3000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "clock_100ms", "delay_ms": 1000, "clock_ms": 100, "fee_multiple": 1, "adverse_multiple": 1}],
        "acquisition": {"exchange": "binance-futures", "date": "2024-09-01", "offset": 0, "slice_minutes": 1,
                        "symbol": "enausdt", "channels": ["bookTicker", "markPrice"],
                        "decoded_cap": 16_000_000, "authenticated": False, "paid_fallback": False},
        "progression": "No reliable edge or candidate promotion from a single event, even if positive. A conditional loss/no-fill/unknown is preserved. Any wider sample must retain the same family selection history, controls and costs, with a new prospective coverage plan before its outcomes.",
        "economic_implementations_run": 0, "actual_execution_verified": False,
        "historical_permissions_verified": False, "selection_2025_opened": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"events": 1, "planned_economic_rules": 2, "planned_scenarios": 12}))


if __name__ == "__main__":
    main()
