"""Full independent as-of join and exact candidate audit of the acquisition screen."""

import calendar
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import numpy as np
import pandas as pd

from research_scout.prepare_market_lag_coverage_20261002 import OUT, ROOT, sha


def verify(job):
    source, saved = job
    assert sha(ROOT / source["path"]) == source["compressed_sha256"]
    frame = pd.read_csv(ROOT / source["path"], usecols=["exchange", "symbol", "local_timestamp", "bids[0].price", "asks[0].price"],
                        dtype={"exchange": "category", "symbol": "category", "local_timestamp": "int64",
                               "bids[0].price": str, "asks[0].price": str})
    assert len(frame) == saved["normalized_source_rows"]
    assert (frame.exchange == "binance-futures").all() and (frame.symbol == "BTCUSDT").all()
    assert frame.local_timestamp.is_monotonic_increasing
    beginning = calendar.timegm(datetime.strptime(source["date"], "%Y-%m-%d").timetuple()) * 10**6
    clocks = np.array([beginning + m * 60_000_000 + s * 250_000 for m in range(1440) for s in range(8, 236)], dtype=np.int64)
    right = pd.DataFrame({"capture": frame.local_timestamp, "row": np.arange(len(frame), dtype=np.int64),
                          "bid": frame["bids[0].price"].astype(float), "ask": frame["asks[0].price"].astype(float)})
    old = pd.merge_asof(pd.DataFrame({"cutoff": clocks - 1_250_000}), right,
                        left_on="cutoff", right_on="capture", direction="backward", allow_exact_matches=False)
    new = pd.merge_asof(pd.DataFrame({"cutoff": clocks - 250_000}), right,
                        left_on="cutoff", right_on="capture", direction="backward", allow_exact_matches=False)
    valid = np.ones(len(clocks), dtype=bool)
    for endpoint in (old, new):
        valid &= (endpoint["row"].notna() & ((endpoint.cutoff - endpoint.capture) > 0)
                  & ((endpoint.cutoff - endpoint.capture) <= 1_000_000)
                  & np.isfinite(endpoint.bid) & np.isfinite(endpoint.ask)
                  & (endpoint.bid > 0) & (endpoint.ask > endpoint.bid)).to_numpy()
    # Independent cross-product comparisons avoid using the screen's ratio test.
    rb = (new.bid - old.bid) * 10000
    ra = (new.ask - old.ask) * 10000
    positive = (rb >= 15 * old.bid) & (ra >= 15 * old.ask)
    negative = (rb <= -15 * old.bid) & (ra <= -15 * old.ask)
    near = (np.abs(np.abs(rb / old.bid) - 15) <= 1e-8) | (np.abs(np.abs(ra / old.ask) - 15) <= 1e-8)
    potential = np.flatnonzero(valid & (positive | negative | near).to_numpy())
    expected = []
    for position in potential:
        first, last = int(old["row"].iat[position]), int(new["row"].iat[position])
        p0, p1 = [D(frame["bids[0].price"].iat[i]) for i in (first, last)]
        a0, a1 = [D(frame["asks[0].price"].iat[i]) for i in (first, last)]
        up = (p1 - p0) * 10000 >= 15 * p0 and (a1 - a0) * 10000 >= 15 * a0
        down = (p1 - p0) * 10000 <= -15 * p0 and (a1 - a0) * 10000 <= -15 * a0
        if not up and not down:
            continue
        decision = int(clocks[position])
        expected.append({"date": source["date"], "offset_minutes": (decision - beginning) // 60_000_000,
                         "decision_ns": decision * 1000, "direction": 1 if up else -1,
                         "anchor_source_row": first, "current_source_row": last,
                         "anchor_receive_ns": int(frame.local_timestamp.iat[first]) * 1000,
                         "current_receive_ns": int(frame.local_timestamp.iat[last]) * 1000,
                         "anchor_bid": str(p0), "anchor_ask": str(a0), "current_bid": str(p1), "current_ask": str(a1),
                         "bid_return_bps": str((p1 / p0 - 1) * 10000), "ask_return_bps": str((a1 / a0 - 1) * 10000),
                         "requires_native_confirmation": True})
    assert sha(ROOT / saved["candidate_path"]) == saved["candidate_sha256"]
    actual = pd.read_parquet(ROOT / saved["candidate_path"]).to_dict("records")
    assert actual == expected
    assert len(expected) == saved["candidate_grids"]
    assert sorted({r["offset_minutes"] for r in expected}) == saved["candidate_minutes"]
    assert len(clocks) == saved["decision_grids"] and int(valid.sum()) == saved["valid_capture_quote_grids"]
    return {"date": source["date"], "source_rows": len(frame), "decision_grids": len(clocks), "candidate_grids": len(expected),
            "minutes": sorted({r["offset_minutes"] for r in expected})}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    impl = json.loads((OUT / "implementation.json").read_text())
    result = json.loads((OUT / "screen_results.json").read_text())
    assert sha(OUT / "specification.json") == impl["specification_sha256"]
    assert sha(OUT / "implementation.json") == result["implementation_sha256"]
    for path, digest in impl["code_sha256"].items():
        assert sha(ROOT / path) == digest
    jobs = [(s, next(w for w in result["windows"] if w["date"] == s["date"])) for s in spec["sources"]]
    rows = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(verify, job) for job in jobs]):
            row = future.result()
            rows.append(row)
            print(json.dumps(row), flush=True)
    rows.sort(key=lambda r: r["date"])
    native_jobs = [{"date": r["date"], "offset": m} for r in rows for m in r["minutes"]]
    assert native_jobs == result["all_native_jobs"] and native_jobs[:12] == result["initial_native_jobs"]
    assert native_jobs[12:] == result["queued_native_jobs"]
    assert sum(r["source_rows"] for r in rows) == result["normalized_source_rows"]
    assert sum(r["decision_grids"] for r in rows) == result["decision_grids"]
    assert sum(r["candidate_grids"] for r in rows) == result["candidate_grids"]
    audit = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "source_files_verified": len(rows), "normalized_source_rows": result["normalized_source_rows"],
             "decision_grids_verified": result["decision_grids"], "candidate_grids_verified": result["candidate_grids"],
             "candidate_minutes_verified": len(native_jobs), "maximum_numeric_difference": "0",
             "results_sha256": sha(OUT / "screen_results.json"), "auditor_sha256": sha(Path(__file__)),
             "scope": "Independent whole-source reads, backward as-of joins with exact-time exclusion, all-grid quality/cross-product predicates, exact Decimal candidate checks and every selected source-row reference. Normalized acquisition prefilter only; no native signal or execution assertion.",
             "native_signal_eligibility_verified": False, "economic_implementations": 0,
             "future_returns_evaluated": False, "reliable_edge_established": False}
    with (OUT / "independent_verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
