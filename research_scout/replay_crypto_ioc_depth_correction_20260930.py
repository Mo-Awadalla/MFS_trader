"""Verify the IOC-depth correction against saved forecasts, without refitting."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research.crypto_cross_market import replay

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/crypto_cross_market_20260930"


def main():
    target = OUTPUT / "execution_correction.json"
    if target.exists():
        raise FileExistsError("Correction already verified")
    spec = json.loads((OUTPUT / "specification.json").read_text())
    results = json.loads((OUTPUT / "results.json").read_text())
    forecasts = pd.read_parquet(OUTPUT / "selection_predictions.parquet")
    panel = pd.concat([pd.read_parquet(OUTPUT / "panels" / f"{day}.parquet") for day in spec["selection"]], ignore_index=True)
    pd.testing.assert_frame_equal(panel[["date", "decision_ms"]], forecasts[["date", "decision_ms"]])
    verified = []
    for name in results["results"]:
        horizon = int(name.rsplit("_", 1)[1].removesuffix("s"))
        for scenario, arguments in {"base": {}, "double_fees": {"fee_bps": 10}, "latency_3s": {"delay_ms": 3000}}.items():
            trades, daily = replay(panel, forecasts[name].to_numpy(), horizon, **arguments)
            old_trades = pd.read_parquet(OUTPUT / f"{name}_{scenario}_trades.parquet")
            old_daily = pd.read_parquet(OUTPUT / f"{name}_{scenario}_daily.parquet")
            pd.testing.assert_frame_equal(trades, old_trades, check_dtype=False,
                                          check_index_type=False, check_column_type=False)
            pd.testing.assert_frame_equal(daily, old_daily, check_dtype=False)
            verified.append({"name": name, "scenario": scenario, "trades": len(trades), "unchanged": True})
    record = {"created_at_utc": datetime.now(UTC).isoformat(),
              "correction": "An IOC larger than displayed arrival depth can execute at unobserved deeper prices within its collar. Mark this unresolved instead of assuming only a partial top-level fill and canceling the remainder.",
              "original_engine_sha256": spec["code_sha256"]["research\\crypto_cross_market.py"] if "research\\crypto_cross_market.py" in spec["code_sha256"] else spec["code_sha256"]["research/crypto_cross_market.py"],
              "corrected_engine_sha256": hashlib.sha256((ROOT / "research/crypto_cross_market.py").read_bytes()).hexdigest(),
              "original_sources": "code_snapshot/ preserves exact sources matching the frozen specification",
              "refitted": False, "retuned": False, "all_recorded_results_unchanged": True,
              "verified_scenarios": verified}
    target.write_text(json.dumps(record, indent=2) + "\n")
    print(f"All {len(verified)} saved-forecast scenario replays match their original no-trade results exactly.")


if __name__ == "__main__":
    main()
