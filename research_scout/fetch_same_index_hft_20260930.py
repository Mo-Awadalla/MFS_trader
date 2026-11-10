"""Bounded free historical SIP acquisition for the frozen ETF pair screen."""

import json
import os
import time

import pandas as pd
import requests
from dotenv import dotenv_values

from data.alpaca_l1 import AlpacaHistoricalL1Client
from research.crypto_symbol_cache import digest
from research_scout.prepare_same_index_hft_20260930 import OUT, ROOT


def main():
    spec = json.loads((OUT/"specification.json").read_text())
    budget = spec["download"]
    symbols = [s for pair in spec["pairs"] for s in pair]
    output = OUT/"quotes"
    output.mkdir(exist_ok=True)
    config = dotenv_values(ROOT/".env")
    key = os.getenv("ALPACA_API_KEY") or config.get("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or config.get("APCA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET") or config.get("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or config.get("APCA_API_SECRET_KEY")
    session = requests.Session()
    session.trust_env = False
    client = AlpacaHistoricalL1Client(key, secret, feed="sip", session=session,
                                    max_total_bytes=budget["per_file_max_bytes"],
                                    max_duration_seconds=budget["max_seconds_per_file"])
    assert client.is_available()
    records, total = [], 0
    for day in spec["dates"]:
        for symbol in symbols:
            path = output/f"{day}_{symbol}.parquet"
            sidecar = path.with_suffix(".json")
            if sidecar.exists():
                record = json.loads(sidecar.read_text())
                if record["complete"]:
                    assert digest(path) == record["sha256"]
            else:
                assert total+budget["per_file_max_bytes"] <= budget["total_max_bytes"]
                record = {"date": day, "symbol": symbol, "complete": False, "path": str(path.relative_to(ROOT))}
                try:
                    start, end = [pd.Timestamp(day+" "+clock, tz="America/New_York").tz_convert("UTC") for clock in budget["window_et"]]
                    result = client.download_quotes(symbol, start, end, max_pages=budget["max_pages"])
                    frame = result.data
                    assert result.metadata["pagination_complete"] and len(frame) > 0
                    assert frame.timestamp.is_monotonic_increasing and frame.timestamp.between(start, end, inclusive="both").all()
                    assert frame.symbol.eq(symbol).all()
                    frame.to_parquet(path, index=False)
                    record.update(complete=True, sha256=digest(path), rows=len(frame), metadata=result.metadata)
                except Exception as error:
                    record.update(error_type=type(error).__name__, error="Incomplete bounded historical quote acquisition; preserve unknown source.")
                sidecar.write_text(json.dumps(record, indent=2)+"\n")
                time.sleep(.5)
            total += record.get("metadata", {}).get("response_bytes", budget["per_file_max_bytes"])
            records.append(record)
            manifest = {"complete": len(records) == len(spec["dates"])*len(symbols) and all(r["complete"] for r in records),
                        "files": records, "expected_files": len(spec["dates"])*len(symbols), "response_byte_upper_bound": total,
                        "specification_sha256": digest(OUT/"specification.json"), "orders_submitted": False, "billing_changed": False}
            (OUT/"quote_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
            print(json.dumps({"date": day, "symbol": symbol, "rows": record.get("rows"),
                              "complete": record["complete"], "files": len(records), "bytes_upper": total}), flush=True)


if __name__ == "__main__":
    main()
