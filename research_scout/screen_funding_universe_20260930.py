"""Enumerate all historical native Binance contracts before funding settlement."""

import gzip
import hashlib
import json
from datetime import UTC, datetime

import pandas as pd

from research.crypto_symbol_cache import digest
from research.funding_native_screen import snapshot
from research_scout.prepare_funding_universe_20260930 import OUT, ROOT


def main():
    if (OUT/"stage_a_results.json").exists():
        raise RuntimeError("Preserve original broad-universe screen")
    spec = json.loads((OUT/"specification.json").read_text())
    manifest = json.loads((OUT/"native_manifest.json").read_text())
    assert len(manifest["files"]) == manifest["expected_files"] == 24
    assert digest(OUT/"specification.json") == manifest["specification_sha256"]
    freeze = {"created_at_utc": datetime.now(UTC).isoformat(),
              "implementation_sha256": {p: digest(ROOT/p) for p in ["research/funding_native_screen.py", "research_scout/screen_funding_universe_20260930.py"]},
              "manifest_sha256": digest(OUT/"native_manifest.json"), "protocol_sha256": digest(OUT/"specification.json"),
              "future_prices_or_realized_funding_used": False}
    (OUT/"stage_a_implementation.json").write_text(json.dumps(freeze, indent=2)+"\n")
    rows, diagnostics, failed = [], [], []
    for item in sorted(manifest["files"], key=lambda r: (r["date"], r["hour"])):
        if not item["complete"]:
            failed.append(item)
            continue
        path = ROOT/item["path"]
        assert digest(path) == item["compressed_sha256"]
        payload = gzip.decompress(path.read_bytes())
        assert hashlib.sha256(payload).hexdigest() == item["decoded_sha256"]
        target = pd.Timestamp(f"{item['date']} {item['hour']:02d}:00", tz="UTC").value
        output, diag = snapshot(payload.decode().splitlines(), target)
        rows.extend({"date": item["date"], "hour": item["hour"], **r} for r in output)
        diagnostics.append({"date": item["date"], "hour": item["hour"], **diag})
    frame = pd.DataFrame(rows)
    for name in frame:
        if name.endswith("_ns") or name in {"line_index", "record_index"}:
            frame[name] = pd.array([r.get(name) for r in rows], dtype="Int64")
    frame.to_parquet(OUT/"binance_snapshots.parquet", index=False)
    selected = frame.loc[frame.large_binance_rate]
    selected.to_parquet(OUT/"large_binance_rates.parquet", index=False)
    result = {"source_slices": len(manifest["files"])-len(failed), "native_symbol_event_states": len(frame),
              "unique_symbols": int(frame.symbol.nunique()), "usable_states": int(frame.usable.sum()),
              "large_binance_rate_events": len(selected), "counterpart_symbol_dates": len(selected[["date", "symbol"]].drop_duplicates()),
              "outcomes": frame.reason.value_counts().to_dict(), "diagnostics": diagnostics, "failed_sources": failed,
              "maximum_absolute_quoted_binance_rate_bps": float(frame.loc[frame.usable, "funding_rate"].abs().max()*10000),
              "snapshots_sha256": digest(OUT/"binance_snapshots.parquet"), "large_rates_sha256": digest(OUT/"large_binance_rates.parquet"),
              "strategy_pnl_tested": False, "edge_established": False, "sources": spec["sources"]}
    (OUT/"stage_a_results.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"diagnostics", "sources"}}))
    print(selected[["date", "hour", "symbol", "funding_rate", "mark_price"]].to_string(index=False))


if __name__ == "__main__":
    main()
