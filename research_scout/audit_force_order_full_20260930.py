"""Reconcile native reports to the exact historical CSV exports in this study."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research.raw_liquidation_replay import parse_slice
from research_scout.fetch_force_order_full_20260930 import DATES, OUT, ROOT

ASSETS = {"BTCUSDT": {"source": "liquidation_event_20260930", "trades": "liquidation_passive_20260930",
                       "tick_size": .1, "quantity_step": .001},
          "SOLUSDT": {"source": "sol_hft_replication_20260930", "trades": "sol_hft_replication_20260930",
                       "tick_size": .001, "quantity_step": .1}}


def main():
    manifest = json.loads((OUT / "download_manifest.json").read_text())
    assert manifest["complete"] and not manifest["errors"] and len(manifest["files"]) == 1728
    targets = {(entry["date"], entry["minute_offset"]) for entry in manifest["files"]}
    assert targets == {(day, minute) for day in DATES for minute in range(0, 1440, 10)}
    rows, disconnects, recoveries = [], [], []
    pending, previous_day = False, None
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        assert digest(path) == entry["sha256"] and path.stat().st_size == entry["bytes"]
        payload = path.read_bytes()
        records, markers = parse_slice(payload, entry["date"], entry["minute_offset"])
        if entry["date"] != previous_day:
            pending = False
        previous_day = entry["date"]
        by_line = {row["source_line"]: row for row in records}
        for line_number, line in enumerate(payload.decode("utf-8").splitlines()):
            if not line.strip():
                pending = True
            elif line_number in by_line and pending:
                capture = by_line[line_number]["local_timestamp"]
                recoveries.append({"date": entry["date"], "recovery_local_timestamp": capture,
                                   "warmup_end_local_timestamp": capture + 300_000_000})
                pending = False
        rows.extend(records)
        if markers:
            disconnects.append({"date": entry["date"], "minute_offset": entry["minute_offset"], "count": markers})
    raw = pd.DataFrame(rows).sort_values(["date", "local_timestamp", "minute_offset", "source_line"], kind="stable").reset_index(drop=True)
    raw.to_parquet(OUT / "orders.parquet", index=False)
    csvs, sources = [], []
    for symbol, settings in ASSETS.items():
        for day in DATES:
            path = ROOT / "research_scout" / settings["source"] / "raw/liquidations" / day / f"{symbol}.csv.gz"
            source = json.loads(path.with_suffix(path.suffix + ".json").read_text())
            assert digest(path) == source["sha256"]
            frame = pd.read_csv(path)
            csvs.append(frame)
            sources.append({"path": str(path.relative_to(ROOT)), "sha256": source["sha256"], "rows": len(frame)})
    csv = pd.concat(csvs, ignore_index=True)
    joined = csv.merge(raw.loc[raw.status.eq("FILLED")], on=["symbol", "local_timestamp"], how="outer",
                       validate="one_to_one", indicator=True, suffixes=("_csv", "_raw"))
    assert joined._merge.eq("both").all(), joined._merge.value_counts().to_dict()
    assert joined.timestamp_csv.eq(joined.timestamp_raw).all()
    assert joined.side_csv.eq(joined.side_raw).all()
    joined.to_parquet(OUT / "csv_comparison.parquet", index=False)
    last_matches = np.isclose(joined.amount, joined.last_fill_quantity, rtol=0, atol=1e-9)
    cumulative_matches = np.isclose(joined.amount, joined.filled_quantity, rtol=0, atol=1e-9)
    limit_matches = np.isclose(joined.price, joined.limit_price, rtol=0, atol=1e-9)
    average_matches = np.isclose(joined.price, joined.average_price, rtol=0, atol=1e-9)
    ratio = joined.executed_notional / (joined.price * joined.amount)
    report = {"verified": True, "raw_messages": len(raw), "csv_reports": len(csv),
              "matched_csv_reports": len(joined), "last_fill_quantity_matches": int(last_matches.sum()),
              "cumulative_quantity_matches": int(cumulative_matches.sum()),
              "limit_price_matches": int(limit_matches.sum()), "average_price_matches": int(average_matches.sum()),
              "order_T_timestamp_matches": len(joined), "side_matches": len(joined),
              "actual_to_csv_proxy_quantiles": {str(k): float(v) for k, v in ratio.quantile([0, .25, .5, .75, .9, .99, 1]).items()},
              "status_counts": raw.status.value_counts().to_dict(), "disconnect_slices": disconnects,
              "recovery_warmups": recoveries,
              "csv_sources": sources, "orders_sha256": digest(OUT / "orders.parquet"),
              "download_manifest_sha256": digest(OUT / "download_manifest.json"),
              "returns_examined": False,
              "interpretation": "These historical CSV exports store limit p and last filled l. Cumulative executed notional is z times ap for the reported order. The stream is throttled and is not a complete liquidation tape. Current Tardis open-source mapper uses z, so this observation must not be generalized to every version/export.",
              "normalizer_source": "https://github.com/tardis-dev/tardis-node/blob/master/src/mappers/binance.ts"}
    (OUT / "field_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "csv_sources"}, indent=2))
    lines = ["RAW LIQUIDATION FIELD AUDIT — 2026-09-30", "",
             f"All {len(csv):,} historical BTC/SOL CSV reports match native messages by instrument and capture timestamp; order trade timestamps and sides match.",
             f"CSV amount matches last fill l in {last_matches.sum():,} reports; cumulative filled quantity z in {cumulative_matches.sum():,}.",
             f"CSV price matches order limit p in {limit_matches.sum():,} reports; actual average execution price ap in {average_matches.sum():,}.",
             f"True executed order notional / old CSV proxy ranges from {ratio.min():.6f} to {ratio.max():.6f} in these exports.",
             "Prior strategy results remain preserved and reproducible as tests of last-fill-times-limit proxies. They are not tests of total executed order notional.",
             "Current open-source normalization uses z. Findings above refer to these exact archived CSV files, not all Tardis versions or datasets.",
             "Recovering z and ap creates a new input, not evidence of an edge. The raw stream still omits orders under its one-second throttling rule.",
             f"Disconnect-marked ten-minute slices: {len(disconnects)}. Native payload hashes and every calendar slice are checked.", ""]
    (OUT / "FIELD_AUDIT.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
