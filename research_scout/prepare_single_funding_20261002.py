"""Freeze a single-venue settlement test before inspecting its price outcomes."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT/"research_scout/bybit_funding_hft_20261002"
OUT = ROOT/"research_scout/single_funding_hft_20261002"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT/"specification.json").exists(), "Preserve frozen settlement hypothesis"
    parent = json.loads((PARENT/"all_states_screen_results.json").read_text())
    assert sha(PARENT/"all_funding_pairs.parquet") == parent["pairs_sha256"]
    all_rows = pd.read_parquet(PARENT/"all_funding_pairs.parquet")
    events = all_rows.loc[all_rows.large_bybit_rate].copy()
    assert len(events) == 90
    events.to_parquet(OUT/"events.parquet", index=False)
    jobs = []
    for (date, hour), group in events.groupby(["date", "hour"], sort=True):
        jobs.append({"date": date, "hour": int(hour), "symbols": sorted(group.symbol.tolist()),
                     "offset": int(hour)*60-1, "slice_minutes": 2})
    specification = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "family": "Single-venue imminent funding payment versus settlement price adjustment",
        "relationship": "Dependent extension using the same Bybit source screen and 2024 development sample. Different exposure: one outright perpetual position rather than a two-venue hedge. No claim of independent discovery.",
        "selection": "All 90 original native/normalized-fresh Bybit events with abs(upcoming rate)>=14bp and next funding time equal to target. Include events with absent Binance counterpart; no selection by future prices or realized funding. All source failures remain unknown.",
        "parent_pairs_sha256": parent["pairs_sha256"], "events_sha256": sha(OUT/"events.parquet"),
        "signal_cutoff": "Funding target T minus 10.25 seconds; last strictly earlier capture only, <=5-second capture/publication/transaction freshness.",
        "entry": "At T-10 seconds, buy if the quoted rate is negative and sell if positive. Base outbound and acknowledgement delay one second each; three-second stress. One entry per symbol/window; no leverage assumed.",
        "exit": "Fixed exit decision T+10 seconds, same outbound delay. Maximum inventory horizon 30 seconds including clock ambiguity. Do not optimize the exit from observed returns.",
        "pretrade_gate": "Projected payment abs(rate)*signal mark minus one displayed full spread minus 7bp*(bid+ask) must be positive. This is only a payment budget; subsequent repricing can eliminate it. Positive, uncrossed native quotes, coherent sequence and source clocks are required.",
        "size": "Common multiple of ten whole contract quantity units, at most 200 USDT entry notional and 10% of both displayed touch quantities, and at least 100 USDT bid notional. Historical contract grid and trading permissions remain conditional until checked; keep every rejected event.",
        "portfolio": "10,000 USDT capital per date, fully collateralized aggregate entries including fees/adverse allowances. Sort simultaneous orders by symbol; no netting of contingent receipts to finance orders.",
        "cashflow": "Use the exchange's realized funding history at the exact target, not a future forecast substituted into the signal. Bound settlement mark over T-5 through T+5 seconds; account for the worst and best cash outcomes over that timing window. A missing historical payment or unresolved book/mark state makes that event unknown, never zero.",
        "execution": "Reconstruct native level-one physical matching-time states. Compare executable entry and exit prices at order arrival, not midprices. Require enough displayed size throughout clock-uncertainty bounds; include price movement, both taker fees and per-execution adverse cost. Quote replay remains conditional on fills and funding eligibility until private execution is independently validated.",
        "scenario_grid": [
            {"name": "base", "latency_seconds": 1, "taker_bps": 6, "adverse_bps": 1, "clock_ms": 1},
            {"name": "double_fees", "latency_seconds": 1, "taker_bps": 12, "adverse_bps": 1, "clock_ms": 1},
            {"name": "latency_3s", "latency_seconds": 3, "taker_bps": 6, "adverse_bps": 1, "clock_ms": 1},
            {"name": "double_adverse", "latency_seconds": 1, "taker_bps": 6, "adverse_bps": 2, "clock_ms": 1},
            {"name": "clock_100ms", "latency_seconds": 1, "taker_bps": 6, "adverse_bps": 1, "clock_ms": 100}],
        "historical_state_limits": "Full normalized states restore missing native fields, but native initialization/disconnect continuity and exact historical contract permissions still require validation before reliability claims.",
        "download": {"jobs": jobs, "exchange": "bybit", "channels": ["tickers", "orderbook.1"], "workers": 3,
                     "per_file_decoded_cap": 96_000_000, "aggregate_decoded_cap": 2_304_000_000,
                     "funding_history_request_cap": 90, "funding_history_response_cap": 65536,
                     "authenticated": False, "paid_fallback": False},
        "format_pilot": "Use the first chronological selected event to verify the public historical-payment API before fetching all 90 payment observations. Public API errors remain explicit.",
        "validation": "One economic rule, five frozen scenarios. Preserve all event outcomes; group inference by date, inspect concentration and remove best events/dates. Advance to untouched 2025 only if development and cost/latency stress survive. Any later revision counts as another dependent hypothesis.",
        "source_documents": ["https://bybit-exchange.github.io/docs/v5/market/history-fund-rate", "https://www.bybit.com/en/help-center/article/Funding-fee-calculation"],
        "implementation_sha256": sha(Path(__file__)), "selection_2025_opened": False,
        "economic_configurations_run": 0, "reliable_edge_established": False}
    (OUT/"specification.json").write_text(json.dumps(specification, indent=2)+"\n")
    print(json.dumps({"events": len(events), "windows": len(jobs), "specification_sha256": sha(OUT/"specification.json")}), flush=True)


if __name__ == "__main__":
    main()
