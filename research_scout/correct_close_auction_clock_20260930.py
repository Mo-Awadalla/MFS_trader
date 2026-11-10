"""Repair a documented legacy scheduled-time encoding; keep economic rule fixed."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.screen_close_auction_20260930 import OUT, ROOT, screen

DEST = OUT / "clock_corrected"


def scheduled_time(raw_ns, day, auction_type, close_ns):
    if auction_type != "C":
        return raw_ns, "unsupported_auction_type"
    if raw_ns == close_ns:
        return raw_ns, "already_utc"
    legacy = pd.Timestamp(day + " 16:00:00", tz="UTC").value
    actual = pd.Timestamp(day + " 16:00:00", tz="America/New_York").value
    if raw_ns == legacy and close_ns == actual:
        return actual, "legacy_new_york_wall_time_encoded_as_utc"
    return raw_ns, "unrecognized_no_repair"


def main():
    DEST.mkdir(exist_ok=True)
    spec_path = DEST / "specification.json"
    if spec_path.exists():
        raise FileExistsError("Clock correction already frozen")
    old = json.loads((OUT / "screen_specification.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    assert digest(ROOT / "research_scout/screen_close_auction_20260930.py") == old["code_sha256"]
    for name, sha in results["source_panel_sha256"].items():
        assert digest(OUT / name) == sha
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "stage": "predecision source-clock correction only",
            "original_specification_sha256": digest(OUT / "screen_specification.json"), "code_sha256": digest(Path(__file__)),
            "repair": "For C-type full16:00 sessions only: accept already-UTC scheduled close unchanged. If raw scheduled timestamp equals same-date16:00 encoded as UTC, interpret its wall time as America/New_York with date-specific DST. Any other value is not repaired. Normalize only auction_time, never capture/event/decision timestamps.",
            "evidence": "Native658 predecision snapshots:619 legacy16:00Z encodings,39 correct21:00Z encodings starting2025-11-03 in this file. Databento2025-11-09 release notes document fixing auction_time to UTC for NYSE datasets. Publication date is not used as the historical encoding cutoff; match exact observed encoding to the known exchange session schedule.",
            "invariants": "All original economic, quantity, price cap, cost, freshness, source selection, dates and side rules unchanged. No future auction or post-entry prices inspected. Original screen retained; this is not a new alpha configuration or an independent result.",
            "sources": ["https://databento.com/docs/release-notes", "https://www.nyse.com/trade/auctions"],
            "source_panel_sha256": results["source_panel_sha256"]}
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    a, q, calendar = (pd.read_parquet(OUT / name) for name in ("auction_inputs.parquet", "quote_inputs.parquet", "calendar.parquet"))
    rows, fixed_inputs = [], []
    for au, qu, target in zip(a.to_dict("records"), q.to_dict("records"), calendar.to_dict("records"), strict=True):
        fixed, mode = scheduled_time(au["auction_time_ns"], target["date"], au["auction_type"], target["close_ns"])
        corrected = {**au, "raw_auction_time_ns": au["auction_time_ns"], "auction_time_ns": fixed, "clock_mode": mode}
        fixed_inputs.append(corrected)
        rows.append({**target, "clock_mode": mode, **screen(corrected, qu, target["decision_ns"], target["close_ns"])})
    pd.DataFrame(fixed_inputs).to_parquet(DEST / "auction_inputs.parquet", index=False)
    frame = pd.DataFrame(rows)
    frame.to_parquet(DEST / "screen.parquet", index=False)
    report = {"dates": len(frame), "eligible_dates": int(frame.eligible.sum()), "outcomes": frame.reason.value_counts().to_dict(),
              "clock_modes": frame.clock_mode.value_counts().to_dict(),
              "by_year": {y: {"dates": len(g), "eligible_dates": int(g.eligible.sum())} for y, g in frame.groupby(frame.date.str[:4])},
              "eligible": frame.loc[frame.eligible].to_dict("records"), "profitability_tested": False, "reliable_edge_established": False,
              "panel_sha256": {n: digest(DEST / n) for n in ("auction_inputs.parquet", "screen.parquet")}}
    assert digest(Path(__file__)) == spec["code_sha256"]
    (DEST / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("dates", "eligible_dates", "outcomes", "clock_modes", "by_year")}), flush=True)


if __name__ == "__main__":
    main()
