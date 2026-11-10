"""Native same-direction major-coin confirmation of the acquisition candidates."""

import gzip
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime

from research.market_lag_supply import leaders
from research.perp_shock_supply import sample
from research.precise_ledger import ledger_frame
from research_scout.prepare_market_lag_native_20261002 import COVERAGE, HYPOTHESIS, OUT, ROOT, sha


def dump(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def screen(source):
    assert source["complete"] and sha(ROOT / source["path"]) == source["compressed_sha256"]
    with gzip.open(ROOT / source["path"], "rt", encoding="utf-8") as stream:
        rows, quotes, counts, symbols = sample(stream, source["date"], source["offset"])
    assert symbols == 2 and {r["symbol"] for r in rows} == {"BTCUSDT", "ETHUSDT"}
    tag = f"{source['date']}_{source['offset']:04d}.parquet"
    quote_path, signal_path = OUT / "quotes" / tag, OUT / "signals" / tag
    ledger_frame(quotes).to_parquet(quote_path, index=False)
    ledger_frame(rows).to_parquet(signal_path, index=False)
    indexed = {(r["decision_ns"], r["symbol"]): r for r in rows}
    common = [{"date": source["date"], "offset_minutes": source["offset"], "decision_ns": decision,
               **leaders(indexed[(decision, "BTCUSDT")], indexed[(decision, "ETHUSDT")])}
              for decision in sorted({r["decision_ns"] for r in rows})]
    return {"date": source["date"], "offset": source["offset"], "source_counts": counts, "symbols": symbols,
            "quote_rows": len(quotes), "signal_rows": len(rows), "valid_endpoints": sum(r["valid_endpoints"] for r in rows),
            "raw_shock_rows": sum(r["supply"] for r in rows), "selected": [r for r in rows if r["selected"]],
            "reasons": dict(Counter(r["reason"] for r in rows)),
            "quotes_path": str(quote_path.relative_to(ROOT)), "quotes_sha256": sha(quote_path),
            "signals_path": str(signal_path.relative_to(ROOT)), "signals_sha256": sha(signal_path),
            "leader_rows": common, "coherent_leader_grids": sum(r["leader_supply"] for r in common)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    sources = json.loads((OUT / "source_manifest.json").read_text())
    assert sources["complete"] and sha(OUT / "specification.json") == sources["specification_sha256"]
    assert sha(HYPOTHESIS / "specification.json") == spec["hypothesis_specification_sha256"]
    assert sha(COVERAGE / "independent_verification.json") == spec["coverage_audit_sha256"]
    assert sha(COVERAGE / "screen_results.json") == spec["coverage_results_sha256"]
    code = ["research/perp_shock_supply.py", "research/spot_perp_supply.py", "research/market_lag_supply.py",
            "research/precise_ledger.py", "research_scout/screen_market_lag_native_20261002.py"]
    dump(OUT / "implementation.json", {"frozen_at_utc": datetime.now(UTC).isoformat(),
         "specification_sha256": sha(OUT / "specification.json"), "source_manifest_sha256": sha(OUT / "source_manifest.json"),
         "code_sha256": {p: sha(ROOT / p) for p in code}, "economic_implementations": 0,
         "validation": "Reuses unchanged parent signal and leader-gate engines with nine and six previously passed focused tests; independent native audit follows."})
    for name in ("quotes", "signals"):
        (OUT / name).mkdir(exist_ok=True)
    windows, counts = [], Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(screen, s) for s in sources["files"]]):
            row = future.result()
            windows.append(row)
            counts.update(row["source_counts"])
            print(json.dumps({k: row[k] for k in ("date", "offset", "coherent_leader_grids")}), flush=True)
    windows.sort(key=lambda r: (r["date"], r["offset"]))
    all_leaders = [r for w in windows for r in w["leader_rows"]]
    passed = [r for r in all_leaders if r["leader_supply"]]
    ledger_frame(all_leaders).to_parquet(OUT / "leaders.parquet", index=False)
    ledger_frame(passed).to_parquet(OUT / "selected_leader_grids.parquet", index=False)
    jobs = [{"date": w["date"], "offset": w["offset"]} for w in windows if w["coherent_leader_grids"]]
    result = {"source_files": len(windows), "source_counts": dict(counts), "leader_grids": len(all_leaders),
              "coherent_leader_grids": len(passed), "coherent_minutes": len(jobs), "target_acquisition_jobs": jobs,
              "queued_candidate_minutes": len(spec["queued_jobs"]), "windows": windows,
              "implementation_sha256": sha(OUT / "implementation.json"), "leaders_sha256": sha(OUT / "leaders.parquet"),
              "selected_leader_grids_sha256": sha(OUT / "selected_leader_grids.parquet"),
              "target_eligibility_tested": False, "economic_implementations": 0, "future_returns_evaluated": False,
              "selection_2025_opened": False, "reliable_edge_established": False}
    dump(OUT / "screen_results.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "windows"}), flush=True)


if __name__ == "__main__":
    main()
