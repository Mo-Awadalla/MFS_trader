"""Acquire bounded public DEEP prefixes and run the fixed causal admission."""

import argparse
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from research.iex_deep_supply import screen
from research_scout.prepare_iex_deep_20261002 import OUT, PARENT, ROOT, digest


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def one_date(day):
    spec = json.loads((OUT / "specification.json").read_text())
    for relative, key in (("research/iex_deep_supply.py", "implementation_sha256"),
                          ("research/iex_native_prefix.py", "packet_decoder_sha256"),
                          ("research/iex_spread_supply.py", "eligibility_sha256")):
        assert digest(ROOT / relative) == spec[key]
    metadata = ROOT / "research_scout/iex_units_hft_20261002/hist_metadata.json"
    assert digest(metadata) == spec["source_metadata_sha256"]
    source = next(s for s in json.loads(metadata.read_text())[day.replace("-", "")] if s["feed"] == "DEEP")
    parent = json.loads((PARENT / "screen_results.json").read_text())
    assert digest(PARENT / "screen_results.json") == spec["parent_results_sha256"]
    parent_session_path = PARENT / "sessions" / (day + ".json")
    assert digest(parent_session_path) == parent["session_hashes"][day]
    parent_session = json.loads(parent_session_path.read_text())
    compare = [r["symbol"] for r in parent_session["candidates"]]
    folder = OUT / "sources" / day
    folder.mkdir(parents=True, exist_ok=True)
    write(folder / "source.json", source)
    prefix = folder / "prefix.gz"
    assert not prefix.exists(), "Existing acquisition needs explicit recovery"
    decision = int(pd.Timestamp(day + " 09:31:00", tz="America/New_York").value)
    size, history = 0, []
    while size < 256 * 1024 * 1024:
        end = min(size + 32 * 1024 * 1024, int(source["size"])) - 1
        if end < size:
            raise ValueError("Full source does not cover the fixed cutoff")
        chunk = folder / f"compressed_{size:012d}_{end:012d}.bin"
        assert not chunk.exists()
        with requests.get(source["link"], headers={"Range": f"bytes={size}-{end}"},
                          timeout=45, stream=True) as response:
            response.raise_for_status()
            expected = f"bytes {size}-{end}/{source['size']}"
            if response.status_code != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("DEEP range identity mismatch")
            body = response.content
            if len(body) != end - size + 1:
                raise ValueError("Incomplete DEEP range")
        chunk.write_bytes(body)
        write(chunk.with_suffix(".bin.json"), {
            "url": source["link"], "content_range": expected, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(), "downloaded_at_utc": datetime.now(UTC).isoformat(),
        })
        with prefix.open("ab") as handle:
            handle.write(body)
        size += len(body)
        result = screen(prefix, decision, compare)
        history.append({"bytes": size, "sha256": digest(prefix), "status": result["status"]})
        write(folder / "prefix_history.json", history)
        if result["status"] == "screened":
            break
    original = {r["symbol"]: r for r in parent_session["candidates"]}
    for row in result.get("tops_candidate_comparisons", []):
        old = original[row["symbol"]]["quote"]
        row["tops_quote_at_same_capture_cutoff"] = old
        row["tops_original_budget_usd"] = original[row["symbol"]]["quoted_net_budget_usd"]
        row["better_displayed_bid_exists"] = row["deep_quote"]["bid_price"] > old["bid_price"]
        row["better_displayed_ask_exists"] = 0 < row["deep_quote"]["ask_price"] < old["ask_price"]
        protected = row["protected_aggregation_assuming_100_shares"]
        row["protected_matches_tops_at_cutoff"] = (
            protected["bid"] == {"price": old["bid_price"], "size": old["bid_size"]}
            and protected["ask"] == {"price": old["ask_price"], "size": old["ask_size"]})
    result.update(date=day, source=source, prefix_path=str(prefix), prefix_sha256=digest(prefix),
                  compressed_prefix_bytes=size, specification_sha256=digest(OUT / "specification.json"),
                  runner_sha256=digest(Path(__file__)), parent_session_sha256=digest(parent_session_path),
                  full_session_checksum_verified=False)
    write(OUT / "sessions" / (day + ".json"), result)
    return {"date": day, "status": result["status"], "messages": result["messages_checked"],
            "candidates": len(result.get("candidates", [])),
            "selected": [r["symbol"] for r in result.get("selected", [])],
            "original_candidates_compared": len(result.get("tops_candidate_comparisons", []))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    spec = json.loads((OUT / "specification.json").read_text())
    dates = [args.date] if args.date else spec["dates"]
    assert all(d in spec["dates"] for d in dates)
    (OUT / "sessions").mkdir(exist_ok=True)
    pending = [d for d in dates if not (OUT / "sessions" / (d + ".json")).exists()]
    errors = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(one_date, d): d for d in pending}
        for job in as_completed(jobs):
            try:
                print(json.dumps(job.result()), flush=True)
            except Exception as exc:
                row = {"date": jobs[job], "outcome": "unknown_source_or_decode", "error": f"{type(exc).__name__}: {exc}"}
                errors.append(row)
                print(json.dumps(row), flush=True)
    if args.date:
        if errors:
            write(OUT / (args.date + "_errors.json"), errors)
        return
    sessions = [json.loads((OUT / "sessions" / (d + ".json")).read_text()) for d in dates
                if (OUT / "sessions" / (d + ".json")).exists()]
    complete = [r for r in sessions if r["status"] == "screened"]
    comparisons = [c for r in complete for c in r["tops_candidate_comparisons"]]
    result = {
        "dates_requested": len(dates), "dates_screened": len(complete), "errors": errors,
        "incomplete_prefix_dates": [r["date"] for r in sessions if r["status"] != "screened"],
        "source_messages": sum(r["messages_checked"] for r in complete),
        "candidates": sum(len(r["candidates"]) for r in complete),
        "selected": [{"date": r["date"], **c} for r in complete for c in r["selected"]],
        "original_candidates_compared": len(comparisons),
        "original_candidates_with_better_displayed_price": sum(c["better_displayed_bid_exists"] or c["better_displayed_ask_exists"] for c in comparisons),
        "original_candidates_still_eligible": sum(c["causal_outcome"] == "candidate" for c in comparisons),
        "protected_aggregation_matches_tops": sum(c["protected_matches_tops_at_cutoff"] for c in comparisons),
        "specification_sha256": digest(OUT / "specification.json"),
        "runner_sha256": digest(Path(__file__)),
        "session_hashes": {r["date"]: digest(OUT / "sessions" / (r["date"] + ".json")) for r in sessions},
        "economic_configurations_executed": 0, "returns_calculated": False,
        "actual_execution_verified": False, "reliable_edge_established": False,
    }
    assert not (OUT / "screen_results.json").exists()
    write(OUT / "screen_results.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("selected", "session_hashes")}), flush=True)


if __name__ == "__main__":
    main()
