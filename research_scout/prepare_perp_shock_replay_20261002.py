"""Freeze the two parent-declared response controls before additional outcomes."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "research_scout/perp_shock_hft_20261002"
FLOW = ROOT / "research_scout/perp_shock_flow_hft_20261002"
OUT = ROOT / "research_scout/perp_shock_response_hft_20261002"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    events = pd.read_parquet(FLOW / "selected.parquet").to_dict("records")
    assert len(events) == 5 and all(e["source_integrity_ok"] for e in events)
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Fifteen-second response to large one-second perpetual price shocks with aggressive trade confirmation",
        "relationship": "Dependent follow-through of both controls declared before the quote and flow screens. All five selected events, no ranking, symbol filtering or direction selection by future returns. Previously exposed 2024 source minutes are development data, not pristine validation. Related prior response families failed; retain their search history.",
        "events_path": str((FLOW / "selected.parquet").relative_to(ROOT)),
        "events_sha256": sha(FLOW / "selected.parquet"),
        "parent_results_sha256": sha(PARENT / "screen_results.json"),
        "flow_results_sha256": sha(FLOW / "screen_results.json"),
        "independent_parent_and_flow_audits_required_before_pnl": True,
        "rules": {"follow_shock": "Buy an upward shock; sell a downward shock.",
                  "fade_shock": "Sell an upward shock; buy a downward shock."},
        "entry_signal": "Latest full native BBO captured strictly before the frozen decision minus 250ms. Require capture, transaction T and publication E age in (0,250ms] relative to that cutoff, with native clocks consistent. Match the complete signal to the original independently audited quote ledger. No scenario changes that quote or quantity.",
        "quantity": "floor(min(200/(1.01*directional quote),10% of directional displayed quantity)/10)*10 base units. Minimum entry notional 100 USDT. Fixed before order transmission, never resize from future depth. Reserve full notional plus 2% costs from 10000 USDT, without leverage. The ten-unit increment and minimum are conditional conservative sizing assumptions, not verified historical LOT_SIZE/MIN_NOTIONAL rules.",
        "grids": {"ADAUSDT": "0.0001", "XRPUSDT": "0.0001", "BAKEUSDT": "0.0001", "CELOUSDT": "0.001", "ZROUSDT": "0.001"},
        "historical_price_grid_verified": False,
        "historical_lot_size_verified": False,
        "grid_evidence": "These price increments are explicit assumptions consistent with the already observed signal spreads; every replay price must lie on the assumed grid. ZRO's official launch announcement gives 0.001 on 2024-06-20, but continuity of all historical exchange filters is not established. No deployment or reliability claim without historical order-rule evidence.",
        "zro_launch_reference": "https://www.binance.com/en/support/announcement/detail/09bdfa5901c94bf6a4e60ab66078a75c",
        "timing": "Process 50ms then outbound delay. Entry ACK takes another outbound delay. Decide exit 15s after that ACK; process 50ms and send with the same outbound delay. Planned inventory remains below 30s including stress uncertainty. An unresolved exit has unknown actual holding time.",
        "entry_order": "FOK with 10bp collar from the fixed causal directional quote, rounded inward to the assumed tick. All compatible native transaction-clock quotes must offer full touch size within the limit; all outside means no fill; mixed eligibility or inadequate touch depth means unknown. No passive or deeper fills inferred.",
        "exit_order": "Full quantity marketable exit, requiring sufficient displayed touch in every compatible native state. Unknown inventory is never zeroed. Evaluate independent daily episodes; halt all later same-date events after an unresolved submitted position, or while a known earlier position remains scheduled open. Any unknown makes the full sample net result unknown.",
        "execution_clock": "T is matching time; E is publication; capture is information time. Preserve all equal-T predecessor states and all groups in arrival +/-1ms, or +/-100ms stress, and require a later successor. Regressing transaction times or conflicting IDs make execution evidence unknown for the whole source, never a retroactive predecision no-order. Disconnect overlap makes an order envelope unknown. Native quote execution is conditional, not an actual private fill.",
        "funding": "A native markPrice captured strictly before the signal cutoff, with capture and publication at most five seconds old and consistent, must indicate next funding after decision+24.2s+1s. No funding payment is credited. This covers the latest stressed planned exit plus a margin.",
        "costs": {"taker_bps_each_side": 6, "adverse_bps_each_side": 1},
        "scenarios": [
            {"name": "base", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "fees_2x", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 2, "adverse_multiple": 1},
            {"name": "adverse_2x", "delay_ms": 1000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 2},
            {"name": "latency_250ms", "delay_ms": 250, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "latency_3s", "delay_ms": 3000, "clock_ms": 1, "fee_multiple": 1, "adverse_multiple": 1},
            {"name": "clock_100ms", "delay_ms": 1000, "clock_ms": 100, "fee_multiple": 1, "adverse_multiple": 1}],
        "jobs": [{"date": e["date"], "offset": int(e["offset_minutes"]), "symbol": e["symbol"]} for e in events],
        "download": {"exchange": "binance-futures", "slice_minutes": 2,
                     "channels": ["bookTicker", "markPrice"], "workers": 2,
                     "per_slice_decoded_cap": 32_000_000, "request_deadline_seconds": 180,
                     "authenticated": False, "paid_fallback": False},
        "progression": "Five events across four dates cannot establish reliability. Preserve both controls and all outcomes. Conditional positive results require independent execution/cash reconciliation, historical filter verification, a newly frozen wider development coverage plan, and later independent validation. No tuning exits or triggers on these returns; no opening 2025 selection data in this test.",
        "actual_execution_verified": False, "selection_2025_opened": False,
        "reliable_edge_established": False, "preparation_sha256": sha(Path(__file__)),
    }
    with (OUT / "specification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(spec, indent=2) + "\n")
    print(json.dumps({"events": len(events), "rules": 2, "scenario_cases": 12, "specification_sha256": sha(OUT / "specification.json")}))


if __name__ == "__main__":
    main()
