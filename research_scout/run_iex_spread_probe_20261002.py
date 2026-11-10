"""Run the frozen native IEX conditional price probe with bounded source extension."""

import gzip
import hashlib
import json
import shutil
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import requests

from research.iex_spread_proxy import Tape, evaluate, extract_symbol
from research_scout.prepare_iex_spread_20261002 import OUT, ROOT, digest

FOLDER = OUT / "price_probe_v1"


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def one_event(event):
    spec = json.loads((FOLDER / "specification.json").read_text())
    assert digest(ROOT / "research/iex_spread_proxy.py") == spec["implementation_sha256"]
    assert digest(ROOT / "research/iex_native_prefix.py") == spec["decoder_sha256"]
    parent = json.loads((OUT / "screen_results.json").read_text())
    day, symbol = event["date"], event["symbol"]
    parent_path = OUT / "sessions" / (day + ".json")
    assert digest(parent_path) == parent["session_hashes"][day]
    session = json.loads(parent_path.read_text())
    assert event == {"date": day, **session["selected"][0]}
    event = {**event, "decision_ns": session["decision_ns"]}
    endpoint = event["decision_ns"] + 35_000_000_000
    source_folder = FOLDER / "sources" / day
    source_folder.mkdir(parents=True, exist_ok=True)
    prefix = Path(session["prefix_path"])
    assert digest(prefix) == session["prefix_sha256"]
    source = session["source"]
    log = []
    while True:
        rows, coverage = extract_symbol(prefix, symbol, endpoint)
        log.append({"path": str(prefix), "bytes": prefix.stat().st_size,
                    "sha256": digest(prefix), **coverage})
        write(source_folder / "prefix_history.json", log)
        if coverage["covered"] or prefix.stat().st_size >= 256 * 1024 * 1024:
            break
        begin = prefix.stat().st_size
        end = min(begin + 32 * 1024 * 1024, 256 * 1024 * 1024, int(source["size"])) - 1
        if end < begin:
            break
        chunk = source_folder / f"compressed_{begin:012d}_{end:012d}.bin"
        assert not chunk.exists(), "Untracked extension requires inspection"
        with requests.get(source["link"], headers={"Range": f"bytes={begin}-{end}"},
                          timeout=45, stream=True) as response:
            response.raise_for_status()
            expected = f"bytes {begin}-{end}/{source['size']}"
            if response.status_code != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("Native source range identity mismatch")
            body = response.content
            if len(body) != end - begin + 1:
                raise ValueError("Incomplete native source range")
        chunk.write_bytes(body)
        write(chunk.with_suffix(".bin.json"), {
            "url": source["link"], "content_range": expected, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "downloaded_at_utc": datetime.now(UTC).isoformat(),
        })
        own_prefix = source_folder / "extended_prefix.gz"
        if prefix != own_prefix:
            assert not own_prefix.exists()
            shutil.copyfile(prefix, own_prefix)
            prefix = own_prefix
        with prefix.open("ab") as handle:
            handle.write(body)
    records_path = source_folder / "selected_symbol.jsonl.gz"
    with gzip.open(records_path, "wt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    outcomes = []
    if coverage["covered"]:
        tape = Tape(rows)
        for model in spec["fill_models"]:
            for case in spec["cases"]:
                outcomes.append(evaluate(event, tape, case, model))
    else:
        for model in spec["fill_models"]:
            for case in spec["cases"]:
                outcomes.append({"date": day, "symbol": symbol, "case": case["name"],
                                 "fill_model": model, "outcome": "unknown_source_coverage",
                                 "net_usd": None, "actual_execution_verified": False})
    result = {
        "event": event, "source": source, "coverage": coverage,
        "prefix_path": str(prefix), "prefix_sha256": digest(prefix),
        "records_path": str(records_path), "records_sha256": digest(records_path),
        "selected_symbol_messages": len(rows), "message_types": dict(Counter(r["type"] for r in rows)),
        "source_messages_checked": coverage["messages_checked"], "outcomes": outcomes,
        "specification_sha256": digest(FOLDER / "specification.json"),
        "runner_sha256": digest(Path(__file__)), "actual_execution_verified": False,
    }
    write(FOLDER / "sessions" / (day + ".json"), result)
    return {"date": day, "symbol": symbol, "source_covered": coverage["covered"],
            "source_messages": coverage["messages_checked"], "symbol_messages": len(rows),
            "outcomes": dict(Counter(r["outcome"] for r in outcomes))}


def aggregate(rows, model, case):
    selected = [r for r in rows if r["case"] == case and r["fill_model"] == model]
    known = [r for r in selected if r["net_usd"] is not None]
    values = sorted((Decimal(r["net_usd"]) for r in known), reverse=True)
    total = sum(values, Decimal(0))
    complete = len(known) == len(selected)
    return {"fill_model": model, "case": case, "events": len(selected), "known_events": len(known),
            "unknown_events": len(selected) - len(known),
            "outcomes": dict(Counter(r["outcome"] for r in selected)),
            "conditionally_priced_entries": sum(r["outcome"] == "conditional_priced" for r in known),
            "positive_events": sum(v > 0 for v in values), "negative_events": sum(v < 0 for v in values),
            "known_component_usd": str(total), "full_conditional_net_usd": str(total) if complete else None,
            "drop_best_three_known_component_usd": str(sum(values[3:], Decimal(0))),
            "drop_best_three_full_conditional_net_usd": str(sum(values[3:], Decimal(0))) if complete else None,
            "maximum_known_event_usd": str(values[0]) if values else None,
            "maximum_exposure_ns": max((r.get("exposure_ns", 0) for r in known), default=0),
            "actual_execution_verified": False, "reliable_edge_established": False}


def main():
    assert not (FOLDER / "results.json").exists()
    spec = json.loads((FOLDER / "specification.json").read_text())
    assert digest(OUT / "screen_results.json") == spec["parent_screen_sha256"]
    assert digest(OUT / "independent_verification.json") == spec["parent_audit_sha256"]
    (FOLDER / "sessions").mkdir(exist_ok=True)
    events = spec["selected_events"]
    errors = []
    pending = [e for e in events if not (FOLDER / "sessions" / (e["date"] + ".json")).exists()]
    with ProcessPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(one_event, e): e for e in pending}
        for job in as_completed(jobs):
            try:
                print(json.dumps(job.result()), flush=True)
            except Exception as exc:
                errors.append({"date": jobs[job]["date"], "symbol": jobs[job]["symbol"],
                               "error": f"{type(exc).__name__}: {exc}"})
                print(json.dumps(errors[-1]), flush=True)
    sessions, rows, hashes = [], [], {}
    for event in events:
        path = FOLDER / "sessions" / (event["date"] + ".json")
        if path.exists():
            session = json.loads(path.read_text())
            assert session["specification_sha256"] == digest(FOLDER / "specification.json")
            sessions.append(session)
            rows.extend(session["outcomes"])
            hashes[event["date"]] = digest(path)
        else:
            for model in spec["fill_models"]:
                for case in spec["cases"]:
                    rows.append({"date": event["date"], "symbol": event["symbol"], "case": case["name"],
                                 "fill_model": model, "outcome": "unknown_source_or_processing_failure",
                                 "net_usd": None, "actual_execution_verified": False})
    result = {
        "created_at_utc": datetime.now(UTC).isoformat(), "events": len(events),
        "sessions_completed": len(sessions), "errors": errors, "event_case_rows": len(rows),
        "source_messages_checked": sum(s["source_messages_checked"] for s in sessions),
        "scenario_results": [aggregate(rows, m, c["name"]) for m in spec["fill_models"] for c in spec["cases"]],
        "session_hashes": hashes, "specification_sha256": digest(FOLDER / "specification.json"),
        "runner_sha256": digest(Path(__file__)), "economic_policy_count": 1,
        "economic_implementation_versions": 1, "actual_execution_verified": False,
        "reliable_edge_established": False, "full_source_checksum_verified": False,
        "interpretation": "Conditional print/price feasibility only; independently budgeted events, unverified queue, hidden liquidity, acceptance, repricing, depth and clock assumptions. Unknown outcomes remain unknown.",
    }
    write(FOLDER / "results.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "session_hashes"}), flush=True)


if __name__ == "__main__":
    main()
