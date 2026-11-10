"""Free historical SIP quotes for every frozen CPI content trigger."""

import json
import os
import time

import pandas as pd
import requests
from dotenv import dotenv_values

from data.alpaca_l1 import AlpacaHistoricalL1Client
from research.crypto_symbol_cache import digest
from research_scout.prepare_cpi_hft_20260930 import OUT, ROOT


def main():
    spec = json.loads((OUT/"specification.json").read_text())
    bls = json.loads((OUT/"source_audit/bls_verification.json").read_text())
    assert bls["verified"] and bls["verified_releases"] == 84
    content = json.loads((OUT/"content_results.json").read_text())
    assert digest(OUT/"content_events.parquet") == content["panel_sha256"]
    panel = pd.read_parquet(OUT/"content_events.parquet")
    panel = panel.loc[panel.content_trigger]
    output = OUT/"quotes"
    output.mkdir(exist_ok=True)
    config = dotenv_values(ROOT/".env")
    key = os.getenv("ALPACA_API_KEY") or config.get("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or config.get("APCA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET") or config.get("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or config.get("APCA_API_SECRET_KEY")
    session = requests.Session()
    session.trust_env = False
    client = AlpacaHistoricalL1Client(key, secret, feed="sip", session=session,
                                    max_total_bytes=spec["download"]["per_file_max_bytes"],
                                    max_duration_seconds=spec["download"]["max_seconds_per_file"])
    assert client.is_available()
    records, total = [], 0
    for event in panel.to_dict("records"):
        day, symbol = event["release_date"], event["symbol"]
        path = output/f"{day}_{symbol}.parquet"
        sidecar = path.with_suffix(".json")
        if sidecar.exists():
            record = json.loads(sidecar.read_text())
            if record["complete"]:
                assert digest(path) == record["sha256"]
        else:
            assert total+spec["download"]["per_file_max_bytes"] <= spec["download"]["total_max_bytes"]
            record = {"date": day, "symbol": symbol, "complete": False, "path": str(path.relative_to(ROOT))}
            try:
                start, end = [pd.Timestamp(day+" "+t, tz="America/New_York").tz_convert("UTC") for t in spec["download"]["window_et"]]
                result = client.download_quotes(symbol, start, end, max_pages=spec["download"]["max_pages"])
                assert result.metadata["pagination_complete"]
                frame = result.data
                assert frame.timestamp.is_monotonic_increasing and frame.timestamp.between(start, end, inclusive="both").all()
                frame.to_parquet(path, index=False)
                record.update(complete=True, sha256=digest(path), rows=len(frame), metadata=result.metadata)
            except Exception as error:
                record.update(error_type=type(error).__name__, error="Incomplete historical quote acquisition; retain unknown source.")
            sidecar.write_text(json.dumps(record, indent=2)+"\n")
            time.sleep(.5)
        total += record.get("metadata", {}).get("response_bytes", spec["download"]["per_file_max_bytes"])
        records.append(record)
        manifest = {"complete": len(records) == len(panel) and all(r["complete"] for r in records),
                    "files": records, "expected_files": len(panel), "response_byte_upper_bound": total,
                    "specification_sha256": digest(OUT/"specification.json"),
                    "bls_verification_sha256": digest(OUT/"source_audit/bls_verification.json"),
                    "orders_submitted": False, "billing_changed": False}
        (OUT/"quote_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
        print(json.dumps({"date": day, "symbol": symbol, "rows": record.get("rows"),
                          "complete": record["complete"], "files": len(records), "bytes_upper": total}), flush=True)


if __name__ == "__main__":
    main()
