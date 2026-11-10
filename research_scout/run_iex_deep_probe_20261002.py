"""Run a frozen DEEP quote/print probe, keeping the missing calendar date unknown."""

import gzip
import hashlib
import json
import shutil
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import requests

from research.iex_deep_probe_source import extract_symbol, quote_tape
from research.iex_spread_proxy import Tape, evaluate
from research_scout.prepare_iex_deep_20261002 import OUT, ROOT, digest
from research_scout.run_iex_spread_probe_20261002 import aggregate, write

FOLDER = OUT / "price_probe_v1"


def verify_code(spec):
    for relative, field in (("research/iex_deep_probe_source.py", "source_implementation_sha256"),
                            ("research/iex_deep_supply.py", "deep_book_sha256"),
                            ("research/iex_native_prefix.py", "packet_decoder_sha256"),
                            ("research/iex_spread_proxy.py", "price_proxy_sha256"),
                            ("research_scout/run_iex_spread_probe_20261002.py", "aggregator_sha256")):
        assert digest(ROOT / relative) == spec[field]


def one_event(event):
    spec = json.loads((FOLDER / "specification.json").read_text())
    verify_code(spec)
    parent = json.loads((OUT / "screen_results.json").read_text())
    day, symbol = event["date"], event["symbol"]
    path = OUT / "sessions" / (day + ".json")
    assert digest(path) == parent["session_hashes"][day]
    session = json.loads(path.read_text())
    assert event == {"date": day, **session["selected"][0]}
    event = {**event, "decision_ns": session["decision_ns"]}
    endpoint = event["decision_ns"] + 35_000_000_000
    folder = FOLDER / "sources" / day
    folder.mkdir(parents=True, exist_ok=True)
    prefix = Path(session["prefix_path"])
    assert digest(prefix) == session["prefix_sha256"]
    source, history = session["source"], []
    while True:
        rows, coverage = extract_symbol(prefix, symbol, endpoint)
        history.append({"path": str(prefix), "bytes": prefix.stat().st_size,
                        "sha256": digest(prefix), **coverage})
        write(folder / "prefix_history.json", history)
        if coverage["covered"] or prefix.stat().st_size >= 256 * 1024 * 1024:
            break
        begin = prefix.stat().st_size
        end = min(begin + 32 * 1024 * 1024, 256 * 1024 * 1024, int(source["size"])) - 1
        if end < begin:
            break
        chunk = folder / f"compressed_{begin:012d}_{end:012d}.bin"
        assert not chunk.exists()
        with requests.get(source["link"], headers={"Range": f"bytes={begin}-{end}"},
                          timeout=45, stream=True) as response:
            response.raise_for_status()
            expected = f"bytes {begin}-{end}/{source['size']}"
            if response.status_code != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("DEEP range identity mismatch")
            body = response.content
            if len(body) != end - begin + 1:
                raise ValueError("Incomplete DEEP range")
        chunk.write_bytes(body)
        write(chunk.with_suffix(".bin.json"), {"url": source["link"], "content_range": expected,
              "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
              "downloaded_at_utc": datetime.now(UTC).isoformat()})
        own = folder / "extended_prefix.gz"
        if prefix != own:
            assert not own.exists()
            shutil.copyfile(prefix, own)
            prefix = own
        with prefix.open("ab") as handle:
            handle.write(body)
    native_path, derived_path = folder / "native_symbol.jsonl.gz", folder / "venue_tape.jsonl.gz"
    with gzip.open(native_path, "wt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    venue = quote_tape(rows) if coverage["covered"] else []
    with gzip.open(derived_path, "wt", encoding="utf-8", newline="\n") as handle:
        for row in venue:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    outcomes = []
    for model in spec["fill_models"]:
        for case in spec["cases"]:
            if coverage["covered"]:
                row = evaluate(event, Tape(venue), case, model)
            else:
                row = {"date": day, "symbol": symbol, "case": case["name"], "fill_model": model,
                       "outcome": "unknown_source_coverage", "net_usd": None, "actual_execution_verified": False}
            outcomes.append(row)
    result = {
        "event": event, "source": source, "coverage": coverage,
        "prefix_path": str(prefix), "prefix_sha256": digest(prefix),
        "native_path": str(native_path), "native_sha256": digest(native_path),
        "venue_path": str(derived_path), "venue_sha256": digest(derived_path),
        "source_messages_checked": coverage["messages_checked"], "native_symbol_messages": len(rows),
        "derived_quote_count": sum(r["type"] == "Q" for r in venue), "outcomes": outcomes,
        "specification_sha256": digest(FOLDER / "specification.json"), "runner_sha256": digest(Path(__file__)),
        "actual_execution_verified": False,
    }
    write(FOLDER / "sessions" / (day + ".json"), result)
    return {"date": day, "symbol": symbol, "source_covered": coverage["covered"],
            "source_messages": coverage["messages_checked"],
            "outcomes": dict(Counter(r["outcome"] for r in outcomes))}


def main():
    assert not (FOLDER / "results.json").exists()
    spec = json.loads((FOLDER / "specification.json").read_text())
    verify_code(spec)
    assert digest(OUT / "screen_results.json") == spec["parent_screen_sha256"]
    assert digest(OUT / "independent_verification.json") == spec["parent_audit_sha256"]
    (FOLDER / "sessions").mkdir(exist_ok=True)
    events, errors = spec["selected_events"], []
    pending = [e for e in events if not (FOLDER / "sessions" / (e["date"] + ".json")).exists()]
    with ProcessPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(one_event, e): e for e in pending}
        for job in as_completed(jobs):
            try:
                print(json.dumps(job.result()), flush=True)
            except Exception as exc:
                row = {"date": jobs[job]["date"], "symbol": jobs[job]["symbol"],
                       "error": f"{type(exc).__name__}: {exc}"}
                errors.append(row)
                print(json.dumps(row), flush=True)
    selected_dates = {e["date"] for e in events}
    event_rows, all_rows, hashes, sessions = [], [], {}, []
    for day in spec["dates"]:
        path = FOLDER / "sessions" / (day + ".json")
        if path.exists():
            session = json.loads(path.read_text())
            assert session["specification_sha256"] == digest(FOLDER / "specification.json")
            sessions.append(session)
            hashes[day] = digest(path)
            event_rows.extend(session["outcomes"])
            all_rows.extend(session["outcomes"])
            continue
        if day in spec["unknown_admission_dates"]:
            outcome, value = "unknown_source_before_signal", None
        elif day in selected_dates:
            outcome, value = "unknown_source_or_processing_failure", None
        else:
            outcome, value = "conditional_no_selected_signal", "0"
        for model in spec["fill_models"]:
            for case in spec["cases"]:
                row = {"date": day, "symbol": None, "case": case["name"], "fill_model": model,
                       "outcome": outcome, "net_usd": value, "actual_execution_verified": False}
                all_rows.append(row)
                if day in selected_dates:
                    event_rows.append(row)
    result = {
        "created_at_utc": datetime.now(UTC).isoformat(), "selected_events": len(events),
        "sessions_completed": len(sessions), "calendar_dates": len(spec["dates"]),
        "unknown_admission_dates": spec["unknown_admission_dates"], "errors": errors,
        "calendar_case_rows": all_rows,
        "scenario_results": [aggregate(all_rows, m, c["name"]) for m in spec["fill_models"] for c in spec["cases"]],
        "observed_selected_cohort_results": [aggregate(event_rows, m, c["name"]) for m in spec["fill_models"] for c in spec["cases"]],
        "source_messages_checked": sum(s["source_messages_checked"] for s in sessions),
        "native_symbol_messages": sum(s["native_symbol_messages"] for s in sessions),
        "session_hashes": hashes, "specification_sha256": digest(FOLDER / "specification.json"),
        "runner_sha256": digest(Path(__file__)), "economic_configurations_executed": 1,
        "economic_implementation_versions": 1, "actual_execution_verified": False,
        "reliable_edge_established": False,
        "interpretation": "Exploratory DEEP variant; conditional price/print assumptions only, still unlimited future execution depth. Observed selected cohort is separate from full calendar, which retains unknown admission.",
    }
    write(FOLDER / "results.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("calendar_case_rows", "session_hashes")}), flush=True)


if __name__ == "__main__":
    main()
