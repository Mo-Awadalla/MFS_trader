"""Confirm all frozen quote shocks using only their causal raw trade prefixes."""

import gzip
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from research.perp_shock_flow import confirm, parse
from research.precise_ledger import ledger_frame
from research_scout.prepare_perp_shock_flow_20261002 import OUT, PARENT, ROOT, sha


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    sources = json.loads((OUT / "source_manifest.json").read_text())
    assert sources["complete"] and sources["specification_sha256"] == sha(OUT / "specification.json")
    assert spec["parent_selection_sha256"] == sha(PARENT / "selected.parquet")
    frozen = {"frozen_at_utc": datetime.now(UTC).isoformat(), "specification_sha256": sha(OUT / "specification.json"),
              "source_manifest_sha256": sha(OUT / "source_manifest.json"),
              "code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in (
                  Path(__file__), ROOT / "research/perp_shock_flow.py", ROOT / "research/precise_ledger.py",
                  ROOT / "research/spot_perp_supply.py", ROOT / "tests/unit/test_perp_shock_flow.py")},
              "focused_tests_passed": 8, "economic_implementations": 0, "future_returns_evaluated": False}
    with (OUT / "screen_implementation.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(frozen, indent=2) + "\n")
    (OUT / "ledgers").mkdir(exist_ok=True)
    windows, all_rows, counts = [], [], Counter()
    for source in sources["files"]:
        path = ROOT / source["path"]
        assert source["complete"] and sha(path) == source["compressed_sha256"]
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            trades, disconnects, source_counts = parse(stream, source["date"], source["offset"], source["symbols"])
        counts.update(source_counts)
        events = [e for e in spec["events"] if e["date"] == source["date"] and e["offset_minutes"] == source["offset"]]
        event_results = []
        for event in events:
            result, ledger = confirm(trades, disconnects, event)
            all_rows.append(result)
            ledger_path = OUT / "ledgers" / f"{event['date']}_{event['symbol']}_{event['decision_ns']}.parquet"
            ledger_frame(ledger).to_parquet(ledger_path, index=False)
            event_results.append({"result": result, "ledger_path": str(ledger_path.relative_to(ROOT)), "ledger_sha256": sha(ledger_path)})
            print(json.dumps(result), flush=True)
        windows.append({"date": source["date"], "offset": source["offset"], "source_counts": source_counts, "events": event_results})
    selected = [r for r in all_rows if r["selected"]]
    ledger_frame(all_rows).to_parquet(OUT / "flow.parquet", index=False)
    ledger_frame(selected).to_parquet(OUT / "selected.parquet", index=False)
    assert len(all_rows) == len(spec["events"])
    result = {"windows": windows, "source_counts": dict(counts), "candidate_events": len(all_rows),
              "selected_events": len(selected), "selected_symbols": sorted({r["symbol"] for r in selected}),
              "selected_dates": len({r["date"] for r in selected}), "reasons": dict(Counter(r["reason"] for r in all_rows)),
              "implementation_sha256": sha(OUT / "screen_implementation.json"),
              "flow_sha256": sha(OUT / "flow.parquet"), "selected_sha256": sha(OUT / "selected.parquet"),
              "economic_implementations": 0, "future_returns_evaluated": False, "independent_audit_complete": False,
              "actual_execution_verified": False, "selection_2025_opened": False, "reliable_edge_established": False}
    with (OUT / "screen_results.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "windows"}), flush=True)


if __name__ == "__main__":
    main()
