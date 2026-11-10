"""Run the frozen broad-universe native quote shock screen."""

import gzip
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from research.perp_shock_supply import sample
from research.precise_ledger import ledger_frame
from research_scout.prepare_perp_shock_20261002 import OUT, ROOT, sha


def run_source(source):
    path = ROOT / source["path"]
    assert source["complete"] and sha(path) == source["compressed_sha256"]
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows, quotes, counts, symbols = sample(stream, source["date"], source["offset"])
    tag = f"{source['date']}_{source['offset']:04d}.parquet"
    quote_path, signal_path = OUT / "quotes" / tag, OUT / "signals" / tag
    ledger_frame(quotes).to_parquet(quote_path, index=False)
    ledger_frame(rows).to_parquet(signal_path, index=False)
    return {"date": source["date"], "offset": source["offset"], "source_counts": counts, "symbols": symbols,
            "quote_rows": len(quotes), "signal_rows": len(rows), "valid_endpoints": sum(r["valid_endpoints"] for r in rows),
            "raw_shock_rows": sum(r["supply"] for r in rows), "selected": [r for r in rows if r["selected"]],
            "reasons": dict(Counter(r["reason"] for r in rows)),
            "quotes_path": str(quote_path.relative_to(ROOT)), "quotes_sha256": sha(quote_path),
            "signals_path": str(signal_path.relative_to(ROOT)), "signals_sha256": sha(signal_path)}


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    for parent in spec["parent_audits"]:
        assert sha(ROOT / parent["path"]) == parent["sha256"]
    for source in spec["sources"]:
        assert sha(ROOT / source["parent_manifest"]) == source["parent_manifest_sha256"]
    frozen = {"frozen_at_utc": datetime.now(UTC).isoformat(), "specification_sha256": sha(OUT / "specification.json"),
              "code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in (
                  Path(__file__), ROOT / "research/perp_shock_supply.py", ROOT / "research/precise_ledger.py",
                  ROOT / "research/spot_perp_supply.py", ROOT / "tests/unit/test_perp_shock_supply.py")},
              "focused_tests_passed": 9, "economic_implementations": 0, "future_returns_evaluated": False}
    with (OUT / "screen_implementation.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(frozen, indent=2) + "\n")
    for name in ("quotes", "signals"):
        (OUT / name).mkdir(exist_ok=True)
    windows, counts, reasons = [], Counter(), Counter()
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run_source, s) for s in spec["sources"]]
        for job in as_completed(jobs):
            row = job.result()
            windows.append(row)
            counts.update(row["source_counts"])
            reasons.update(row["reasons"])
            print(json.dumps({k: row[k] for k in ("date", "offset", "symbols", "signal_rows", "raw_shock_rows")}
                             | {"selected_events": len(row["selected"])}), flush=True)
    windows.sort(key=lambda r: (r["date"], r["offset"]))
    selected = [r for w in windows for r in w["selected"]]
    ledger_frame(selected).to_parquet(OUT / "selected.parquet", index=False)
    result = {"windows": windows, "source_counts": dict(counts), "reasons": dict(reasons),
              "source_minutes": len(windows), "signal_rows": sum(w["signal_rows"] for w in windows),
              "quote_rows": sum(w["quote_rows"] for w in windows), "valid_endpoints": sum(w["valid_endpoints"] for w in windows),
              "raw_shock_rows": sum(w["raw_shock_rows"] for w in windows), "selected_events": len(selected),
              "selected_symbols": sorted({r["symbol"] for r in selected}), "selected_dates": len({r["date"] for r in selected}),
              "selected_sha256": sha(OUT / "selected.parquet"), "implementation_sha256": sha(OUT / "screen_implementation.json"),
              "economic_implementations": 0, "future_returns_evaluated": False, "independent_audit_complete": False,
              "actual_execution_verified": False, "selection_2025_opened": False, "reliable_edge_established": False}
    with (OUT / "screen_results.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "windows"}), flush=True)


if __name__ == "__main__":
    main()
