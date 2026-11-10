"""Apply the frozen activity screen to every spread/depth candidate."""

import gzip
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research.fdusd_activity import screen
from research.precise_ledger import ledger_frame
from research_scout.prepare_fdusd_activity_20261002 import OUT, PARENT, ROOT, sha


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    sources = json.loads((OUT / "source_manifest.json").read_text())
    assert sources["complete"] and sources["specification_sha256"] == sha(OUT / "specification.json")
    assert spec["parent_selection_sha256"] == sha(PARENT / "selected.parquet")
    assert spec["parent_audit_sha256"] == sha(PARENT / "independent_verification.json")
    frozen = {"frozen_at_utc": datetime.now(UTC).isoformat(), "specification_sha256": sha(OUT / "specification.json"),
              "source_manifest_sha256": sha(OUT / "source_manifest.json"),
              "code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in (
                  Path(__file__), ROOT / "research/fdusd_activity.py", ROOT / "research/precise_ledger.py",
                  ROOT / "research/spot_perp_supply.py", ROOT / "tests/unit/test_fdusd_activity.py")},
              "focused_tests_passed": 11, "economic_implementations": 0, "future_returns_evaluated": False}
    with (OUT / "screen_implementation.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(frozen, indent=2) + "\n")
    (OUT / "ledgers").mkdir(exist_ok=True)
    summaries, windows, totals = [], [], Counter()
    for source in sources["files"]:
        path = ROOT / source["path"]
        assert source["complete"] and sha(path) == source["compressed_sha256"]
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            rows, ledger, counts = screen(stream, source["date"], source["offset"], source["symbols"])
        summaries.extend(rows)
        totals.update(counts)
        ledger_path = OUT / "ledgers" / f"{source['date']}_{source['offset']:04d}.parquet"
        ledger_frame(ledger).to_parquet(ledger_path, index=False)
        window = {"date": source["date"], "offset": source["offset"], "source_counts": counts,
                  "ledger_path": str(ledger_path.relative_to(ROOT)), "ledger_sha256": sha(ledger_path),
                  "summaries": rows, "selected": sum(r["selected"] for r in rows)}
        windows.append(window)
        print(json.dumps({k: window[k] for k in ("date", "offset", "source_counts", "selected")}), flush=True)
    summary_path, selected_path = OUT / "activity.parquet", OUT / "selected.parquet"
    frame = pd.DataFrame(summaries)
    frame.to_parquet(summary_path, index=False)
    selected = frame.loc[frame.selected]
    selected.to_parquet(selected_path, index=False)
    assert len(frame) == len(spec["candidate_windows"])
    result = {"windows": windows, "source_counts": dict(totals), "candidate_windows": len(frame),
              "source_minutes": len(windows), "selected_windows": len(selected),
              "selected_symbols": sorted(selected.symbol.unique()), "selected_dates": selected.date.nunique(),
              "source_integrity_failures": int((~frame.source_integrity_ok).sum()),
              "reasons": dict(Counter(frame.reason)), "implementation_sha256": sha(OUT / "screen_implementation.json"),
              "summary_sha256": sha(summary_path), "selected_sha256": sha(selected_path),
              "economic_implementations": 0, "future_returns_evaluated": False,
              "independent_audit_complete": False, "actual_execution_verified": False,
              "selection_2025_opened": False, "reliable_edge_established": False}
    with (OUT / "screen_results.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "windows"}), flush=True)


if __name__ == "__main__":
    main()
