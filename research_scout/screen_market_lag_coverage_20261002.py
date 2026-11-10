"""Locate possible market-shock minutes without evaluating any future return."""

import calendar
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D

import numpy as np
import pandas as pd

from research.market_lag_coverage import sample
from research.precise_ledger import ledger_frame
from research_scout.prepare_market_lag_coverage_20261002 import OUT, ROOT, sha


def dump(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def screen(source):
    path = ROOT / source["path"]
    assert sha(path) == source["compressed_sha256"]
    frame = pd.read_csv(path, usecols=["exchange", "symbol", "local_timestamp", "bids[0].price", "asks[0].price"],
                        dtype={"exchange": "category", "symbol": "category", "local_timestamp": "int64",
                               "bids[0].price": str, "asks[0].price": str})
    assert (frame.exchange == "binance-futures").all() and (frame.symbol == "BTCUSDT").all()
    times = frame.local_timestamp.to_numpy()
    bid, ask = frame["bids[0].price"].to_numpy(dtype=float), frame["asks[0].price"].to_numpy(dtype=float)
    start = calendar.timegm(datetime.strptime(source["date"], "%Y-%m-%d").timetuple()) * 10**6
    result = sample(times, bid, ask, start)
    positions = np.flatnonzero(result["candidate"] | result["near_boundary"])
    candidates, rejected_rounding, additions = [], 0, 0
    for position in positions:
        old, new, decision = [int(result[k][position]) for k in ("anchor_row", "current_row", "decision_us")]
        rb, ra = [(D(frame[k].iat[new]) / D(frame[k].iat[old]) - 1) * 10000 for k in ("bids[0].price", "asks[0].price")]
        direction = 1 if min(rb, ra) >= 15 else -1 if max(rb, ra) <= -15 else 0
        if not direction:
            rejected_rounding += 1
            continue
        additions += int(not result["candidate"][position])
        assert 0 < decision - 1_250_000 - int(times[old]) <= 1_000_000
        assert 0 < decision - 250_000 - int(times[new]) <= 1_000_000
        candidates.append({"date": source["date"], "offset_minutes": (decision - start) // 60_000_000,
                           "decision_ns": decision * 1000, "direction": direction,
                           "anchor_source_row": old, "current_source_row": new,
                           "anchor_receive_ns": int(times[old]) * 1000, "current_receive_ns": int(times[new]) * 1000,
                           "anchor_bid": frame["bids[0].price"].iat[old], "anchor_ask": frame["asks[0].price"].iat[old],
                           "current_bid": frame["bids[0].price"].iat[new], "current_ask": frame["asks[0].price"].iat[new],
                           "bid_return_bps": str(rb), "ask_return_bps": str(ra), "requires_native_confirmation": True})
    minutes = sorted({int(r["offset_minutes"]) for r in candidates})
    target = OUT / "candidates" / f"{source['date']}.parquet"
    ledger_frame(candidates).to_parquet(target, index=False)
    return {"date": source["date"], "normalized_source_rows": len(frame), "decision_grids": len(result["decision_us"]),
            "valid_capture_quote_grids": int(result["valid"].sum()), "float_prefilter_rows": int(result["candidate"].sum()),
            "near_boundary_rows": int(result["near_boundary"].sum()), "decimal_checked_rows": len(positions),
            "rounding_rejected_rows": rejected_rounding, "rounding_added_rows": additions,
            "candidate_grids": len(candidates), "candidate_minutes": minutes,
            "candidate_path": str(target.relative_to(ROOT)), "candidate_sha256": sha(target)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    (OUT / "candidates").mkdir(exist_ok=True)
    code = ["research/market_lag_coverage.py", "research/precise_ledger.py",
            "research_scout/screen_market_lag_coverage_20261002.py", "tests/unit/test_market_lag_coverage.py"]
    dump(OUT / "implementation.json", {"frozen_at_utc": datetime.now(UTC).isoformat(),
         "specification_sha256": sha(OUT / "specification.json"), "code_sha256": {p: sha(ROOT / p) for p in code},
         "focused_tests_passed": 5, "economic_implementations": 0})
    windows = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(screen, row) for row in spec["sources"]]):
            row = future.result()
            windows.append(row)
            print(json.dumps({k: row[k] for k in ("date", "normalized_source_rows", "candidate_grids", "candidate_minutes")}), flush=True)
    windows.sort(key=lambda r: r["date"])
    jobs = [{"date": row["date"], "offset": minute} for row in windows for minute in row["candidate_minutes"]]
    result = {"source_files": len(windows), "normalized_source_rows": sum(r["normalized_source_rows"] for r in windows),
              "decision_grids": sum(r["decision_grids"] for r in windows),
              "candidate_grids": sum(r["candidate_grids"] for r in windows), "candidate_minutes": len(jobs),
              "all_native_jobs": jobs, "initial_native_jobs": jobs[:12], "queued_native_jobs": jobs[12:],
              "windows": windows, "implementation_sha256": sha(OUT / "implementation.json"),
              "native_signal_eligibility_verified": False, "economic_implementations": 0,
              "future_returns_evaluated": False, "selection_2025_opened": False, "reliable_edge_established": False}
    dump(OUT / "screen_results.json", result)
    print(json.dumps({k: result[k] for k in ("source_files", "normalized_source_rows", "decision_grids", "candidate_grids", "candidate_minutes")}), flush=True)


if __name__ == "__main__":
    main()
