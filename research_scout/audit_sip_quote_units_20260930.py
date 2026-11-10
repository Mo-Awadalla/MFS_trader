"""Versioned unit-only repair of the frozen AAPL rule, preserving old evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.alpaca_quote_units import sip_sizes_in_shares
from research.iex_stock_hft_scout import (
    _day_block_interval,
    _verified_quote_path,
    find_signals,
    simulate_crossing,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/sip_quote_units_repair_20260930"
DATA = ROOT / "data/parquet/sip_stock_hft_v1"
SOURCE = "https://docs.alpaca.markets/us/v1.1/changelog/marketdata-bid-and-ask-size-display-change"


def strict_execution_status(raw: pd.DataFrame, executions: pd.DataFrame, shares: int) -> list[str]:
    """Check latest raw quote, so a locked/crossed quote cannot revive an old BBO."""
    ordered = raw.sort_values("timestamp", kind="stable")
    times = ordered.timestamp.dt.as_unit("ns").astype("int64").to_numpy()
    records = []
    for row in executions.to_dict("records"):
        status = "priced_proxy"
        for leg, side in [("entry", "ask"), ("exit", "bid")]:
            stamp = row[f"{leg}_time"].value
            idx = np.searchsorted(times, stamp, side="right") - 1
            if idx < 0 or stamp - times[idx] > 250_000_000:
                status = f"{leg}_missing_or_stale"
                break
            quote = ordered.iloc[idx]
            if (quote.ask_price <= quote.bid_price or quote.bid_price <= 0
                    or quote.conditions != '["R"]' or quote.ask_size <= 0 or quote.bid_size <= 0):
                status = f"{leg}_invalid_latest_quote"
                break
            if quote[f"{side}_size"] < shares:
                status = f"{leg}_insufficient_displayed_size"
                break
        records.append(status)
    return records


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT / "results.json"
    if report_path.exists():
        raise FileExistsError("Preserve existing repair evidence")
    spec_path = ROOT / "research_scout/sip_stock_hft_v1.json"
    spec = json.loads(spec_path.read_text())
    repair = {
        "created_at_utc": datetime.now(UTC).isoformat(), "source": SOURCE,
        "original_specification_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
        "change": "Convert AAPL SIP bid/ask sizes before 2025-11-03 from 100-share round lots to shares; preserve dates, signal, clocks, threshold, costs and gate definitions",
        "scope": "Unit-only historical repair; not a new independent hypothesis or untouched test",
        "execution_audit": "Separately audit latest raw quote, freshness and displayed quantity; do not silently use an earlier valid quote when latest is crossed or locked",
    }
    (OUTPUT / "specification.json").write_text(json.dumps(repair, indent=2) + "\n")
    audits, frames = [], []
    for day in spec["development_dates"]:
        # Original verifier expects paths relative to the repository, as in its manifests.
        source = _verified_quote_path(Path("data/parquet/sip_stock_hft_v1"), spec, day)
        if source is None:
            raise FileNotFoundError(day)
        raw = pd.read_parquet(source)
        normalized = sip_sizes_in_shares(raw, legacy_round_lot_shares=100, feed="sip")
        old = find_signals(raw, spec)
        signals = find_signals(normalized, spec)
        executions = simulate_crossing(normalized, signals, spec)
        executions["strict_execution_status"] = strict_execution_status(
            normalized, executions, spec["execution_diagnostic"]["shares"]
        )
        executions["session_date"] = day
        frames.append(executions)
        audits.append({"date": day, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                       "source_rows": len(raw), "raw_median_ask_size": float(raw.ask_size.median()),
                       "normalized_median_ask_shares": float(normalized.ask_size.median()),
                       "original_signals": len(old), "corrected_signals": len(signals)})
    panel = pd.concat(frames, ignore_index=True)
    legacy = panel.loc[panel.execution_status.eq("crossing_proxy")]
    strict = panel.loc[panel.strict_execution_status.eq("priced_proxy")]
    statistics = {}
    for name, trades in [("unit_only_original_execution_proxy", legacy), ("strict_execution_audit", strict)]:
        ci = _day_block_interval(trades, spec) if len(trades) else (None, None)
        statistics[name] = {"trades": len(trades), "days": trades.session_date.nunique(),
                            "mean_gross_bps": float(trades.gross_bps.mean()) if len(trades) else None,
                            "mean_net_bps": float(trades.net_bps.mean()) if len(trades) else None,
                            "mean_stress_net_bps": float(trades.stress_net_bps.mean()) if len(trades) else None,
                            "day_block_ci95_net_bps": list(ci),
                            "missing_executions_not_zero_profit": True}
    report = {"repair": repair, "audit": audits,
              "original_signals": sum(a["original_signals"] for a in audits),
              "corrected_signals": len(panel), "statistics": statistics,
              "strict_status_counts": panel.strict_execution_status.value_counts().to_dict(),
              "verdict": "NO_RELIABLE_EDGE_ESTABLISHED_BY_UNIT_REPAIR",
              "limitations": "Only twelve five-minute AAPL windows. Conditional quote proxies, no complete portfolio result. Prior source report retained; missing executions cannot be dropped for a performance claim."}
    panel.to_parquet(OUTPUT / "corrected_signals.parquet", index=False)
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k:v for k,v in report.items() if k not in {"repair", "audit"}}, indent=2))


if __name__ == "__main__":
    main()
