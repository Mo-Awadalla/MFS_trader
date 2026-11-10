"""Apply the immutable halt source-cohort signal without examining exits."""

import json
from datetime import UTC, datetime

import pandas as pd

from research.alpaca_quote_units import sip_sizes_in_shares
from research.crypto_symbol_cache import digest
from research.halt_hft import signal
from research_scout.prepare_halt_hft_20260930 import OUT, ROOT


def main():
    output = OUT / "screen.parquet"
    if output.exists():
        raise RuntimeError("Preserve frozen screen")
    manifest = json.loads((OUT/"manifest.json").read_text())
    assert manifest["specification_sha256"] == digest(OUT/"specification.json")
    assert len(manifest["files"]) == manifest["expected_files"]
    cohort = pd.read_parquet(OUT/"cohort.parquet")
    cohort = cohort.loc[cohort.date.str.startswith("2023")]
    freeze = {"created_at_utc": datetime.now(UTC).isoformat(), "implementation": {
        p: digest(ROOT/p) for p in ["research/halt_hft.py", "research_scout/screen_halt_hft_20260930.py",
                                    "research/alpaca_quote_units.py"]},
              "protocol_sha256": digest(OUT/"specification.json"), "manifest_sha256": digest(OUT/"manifest.json")}
    (OUT/"screen_implementation.json").write_text(json.dumps(freeze, indent=2)+"\n")
    records = []
    for event in cohort.to_dict("records"):
        folder = OUT/"raw"/event["date"]
        frames = {}
        for kind in ["quotes", "trades"]:
            path = folder/f"{event['symbol']}_{kind}.parquet"
            record = json.loads(path.with_suffix(".json").read_text())
            if record["complete"]:
                assert digest(path) == record["sha256"]
                frames[kind] = pd.read_parquet(path)
        if len(frames) < 2:
            records.append({**event, "eligible": False, "reason": "unresolved_source_acquisition"})
            continue
        quotes = sip_sizes_in_shares(frames["quotes"], legacy_round_lot_shares=100, feed="sip")
        records.append(signal(event, quotes, frames["trades"]))
    panel = pd.DataFrame(records)
    for column in ["reopen_ns", "decision_ns", "quote_ns", "reopen_index", "pre_index", "old_index", "quote_index", "quantity"]:
        if column in panel:
            panel[column] = pd.array([r.get(column) for r in records], dtype="Int64")
    panel.to_parquet(output, index=False)
    result = {"events": len(panel), "eligible": int(panel.eligible.sum()),
              "outcomes": panel.reason.value_counts().to_dict(),
              "eligible_by_family": panel.loc[panel.eligible, "family"].value_counts().to_dict() if "family" in panel else {},
              "eligible_dates": sorted(panel.loc[panel.eligible, "date"].unique().tolist()),
              "source_complete": manifest["complete"], "profitability_tested": False,
              "signal_capture_clock_verified": False, "round_lot_definitions_individually_verified": False,
              "reliable_edge_established": False, "panel_sha256": digest(output)}
    (OUT/"screen_results.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
