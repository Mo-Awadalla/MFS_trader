"""Fetch bounded free native prefixes and screen one causal decision per date."""

import argparse
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from research.iex_spread_supply import screen
from research_scout.prepare_iex_spread_20261002 import OUT, ROOT, digest


def one_date(day):
    spec = json.loads((OUT / "specification.json").read_text())
    assert digest(ROOT / "research/iex_spread_supply.py") == spec["implementation_sha256"]
    assert digest(ROOT / "research/iex_native_prefix.py") == spec["decoder_sha256"]
    metadata_path = ROOT / "research_scout/iex_units_hft_20261002/hist_metadata.json"
    assert digest(metadata_path) == spec["source_metadata_sha256"]
    metadata = json.loads(metadata_path.read_text())
    source = next(r for r in metadata[day.replace("-", "")] if r["feed"] == "TOPS")
    folder = OUT / "sources" / day
    folder.mkdir(parents=True, exist_ok=True)
    result_path = OUT / "sessions" / (day + ".json")
    if result_path.exists():
        raise ValueError("Frozen session result already exists")
    (folder / "source.json").write_text(json.dumps(source, indent=2) + "\n")
    decision = int(pd.Timestamp(day + " 09:31:00", tz="America/New_York").value)
    completed, log = 0, []
    prefix = folder / "current_prefix.gz"
    inherited = ROOT / "research_scout/iex_units_hft_20261002/20230111_TOPS.extended_prefix.gz"
    if day == "2023-01-11":
        assert digest(inherited) == "a5b10f7ff16a053f2f7373de035294a3df79257fa359a15856bc66303c185fd2"
        prefix = inherited
        completed = inherited.stat().st_size
    while True:
        if completed:
            result = screen(prefix, decision)
            log.append({"prefix_bytes": completed, "prefix_sha256": digest(prefix),
                        "screen_status": result["status"], "path": str(prefix)})
            (folder / "prefix_history.json").write_text(json.dumps(log, indent=2) + "\n")
            if result["status"] == "screened" or completed >= 256 * 1024 * 1024:
                break
        stop = completed + 32 * 1024 * 1024 - 1
        chunk_path = folder / f"compressed_{completed:012d}_{stop:012d}.bin"
        if chunk_path.exists():
            raise ValueError("Untracked acquisition chunk exists; inspect before retry")
        with requests.get(source["link"], headers={"Range": f"bytes={completed}-{stop}"},
                          timeout=45, stream=True) as response:
            response.raise_for_status()
            expected = f"bytes {completed}-{stop}/{source['size']}"
            if response.status_code != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("Range response identity mismatch")
            body = response.content
            if len(body) != stop - completed + 1:
                raise ValueError("Incomplete range response")
            chunk_path.write_bytes(body)
            (folder / (chunk_path.name + ".json")).write_text(json.dumps({
                "url": source["link"], "content_range": expected,
                "downloaded_at_utc": datetime.now(UTC).isoformat(),
                "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            }, indent=2) + "\n")
        if prefix == inherited:
            prefix = folder / "current_prefix.gz"
            prefix.write_bytes(inherited.read_bytes())
        with prefix.open("ab") as handle:
            handle.write(body)
        completed += len(body)
    result.update(date=day, source=source, prefix_path=str(prefix), prefix_sha256=digest(prefix),
                  compressed_prefix_bytes=completed, specification_sha256=digest(OUT / "specification.json"),
                  runner_sha256=digest(Path(__file__)), full_gzip_checksum_verified=False)
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    return {"date": day, "status": result["status"], "messages": result.get("messages_checked"),
            "candidates": len(result.get("candidates", [])),
            "selected_symbols": [r["symbol"] for r in result.get("selected", [])],
            "compressed_bytes": completed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    spec = json.loads((OUT / "specification.json").read_text())
    dates = [args.date] if args.date else spec["dates"]
    assert all(d in spec["dates"] for d in dates)
    (OUT / "sessions").mkdir(exist_ok=True)
    remaining = [d for d in dates if not (OUT / "sessions" / (d + ".json")).exists()]
    errors = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(one_date, d): d for d in remaining}
        for job in as_completed(jobs):
            try:
                print(json.dumps(job.result()), flush=True)
            except Exception as exc:
                row = {"date": jobs[job], "status": "unknown_source_or_processing_failure",
                       "error": f"{type(exc).__name__}: {exc}"}
                errors.append(row)
                print(json.dumps(row), flush=True)
    if args.date:
        return
    sessions = [json.loads((OUT / "sessions" / (d + ".json")).read_text()) for d in dates
                if (OUT / "sessions" / (d + ".json")).exists()]
    full = [r for r in sessions if r["status"] == "screened"]
    result = {"source_dates_requested": len(dates), "dates_screened": len(full), "errors": errors,
              "insufficient_prefix_dates": [r["date"] for r in sessions if r["status"] != "screened"],
              "source_messages_checked": sum(r["messages_checked"] for r in full),
              "candidates": sum(len(r["candidates"]) for r in full),
              "selected": [{"date": r["date"], **c} for r in full for c in r["selected"]],
              "specification_sha256": digest(OUT / "specification.json"),
              "session_hashes": {r["date"]: digest(OUT / "sessions" / (r["date"] + ".json")) for r in sessions},
              "economic_implementations_executed": 0, "returns_calculated": False,
              "actual_execution_verified": False, "reliable_edge_established": False}
    (OUT / "screen_results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("session_hashes", "selected")}), flush=True)


if __name__ == "__main__":
    main()
