"""Bounded read-only historical SIP recovery for every price-eligible auction."""

import json
import os
from datetime import UTC, datetime

import pandas as pd
import requests
from dotenv import dotenv_values

from data.alpaca_l1 import AlpacaHistoricalL1Client
from research.crypto_symbol_cache import digest
from research_scout.benchmark_close_auction_20260930 import DEST as BENCH
from research_scout.benchmark_close_auction_20260930 import INPUT, OUT, ROOT

DEST = OUT / "sip_quote_revision"


def main():
    (DEST / "raw").mkdir(parents=True, exist_ok=True)
    spec_path = DEST / "acquisition_specification.json"
    if not spec_path.exists():
        auctions = pd.read_parquet(BENCH / "auction_references.parquet").set_index("date")
        screen = pd.read_parquet(INPUT / "screen.parquet")
        dates = [r["date"] for r in screen.loc[screen.eligible].to_dict("records")
                 if auctions.loc[r["date"], "valid"] and auctions.loc[r["date"], "price"] <= r["limit"] + 1e-9]
        specification = {"created_at_utc": datetime.now(UTC).isoformat(), "symbol": "SPY", "dates": dates,
                         "feed": "sip", "window_et": ["16:00:00", "16:01:00"],
                         "per_date_byte_cap": 5000000, "per_date_page_cap": 10, "total_success_byte_cap": 50000000,
                         "selection": "Every original price-eligible auction date, irrespective of profit, missing exit or previous quote coverage.32 original triggers unchanged;22 prices above their LOC caps need no exit quote. No new dates or instruments selected to improve P&L.",
                         "purpose": "Replace sparse trade-triggered exit observations with a consistent historical consolidated-quote reference for all10 possible entries. This still cannot establish auction allocation, venue routing or real fills.",
                         "sources": ["https://docs.alpaca.markets/us/docs/market-data-faq"],
                         "cost_and_authorization": "Historical endpoints ending years before the current15-minute restriction; no subscription upgrade, paid fallback or orders. Use only already-configured Alpaca credentials against data.alpaca.markets.",
                         "source_sha256": {"screen": digest(INPUT / "screen.parquet"), "auction_references": digest(BENCH / "auction_references.parquet")}}
        spec_path.write_text(json.dumps(specification, indent=2) + "\n")
    spec = json.loads(spec_path.read_text())
    assert digest(INPUT / "screen.parquet") == spec["source_sha256"]["screen"]
    assert digest(BENCH / "auction_references.parquet") == spec["source_sha256"]["auction_references"]
    config = dotenv_values(ROOT / ".env")
    key = os.getenv("ALPACA_API_KEY") or config.get("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or config.get("APCA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET") or config.get("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or config.get("APCA_API_SECRET_KEY")
    session = requests.Session()
    session.trust_env = False
    client = AlpacaHistoricalL1Client(key, secret, feed="sip", session=session,
                                      max_total_bytes=spec["per_date_byte_cap"], max_duration_seconds=120)
    if not client.is_available():
        raise RuntimeError("Existing Alpaca historical-data credentials are unavailable")
    reports, total = [], 0
    for day in spec["dates"]:
        path, meta = DEST / "raw" / f"{day}.parquet", DEST / "raw" / f"{day}.json"
        if path.exists() and meta.exists():
            record = json.loads(meta.read_text())
            assert digest(path) == record["sha256"]
        else:
            start = pd.Timestamp(day + " 16:00", tz="America/New_York").tz_convert("UTC")
            end = start + pd.Timedelta(minutes=1)
            result = client.download_quotes("SPY", start, end, max_pages=spec["per_date_page_cap"])
            assert result.metadata["pagination_complete"]
            frame = result.data
            assert frame.timestamp.is_monotonic_increasing
            assert frame.timestamp.between(start, end, inclusive="both").all()
            frame.to_parquet(path, index=False)
            record = {"date": day, "path": str(path.relative_to(ROOT)), "sha256": digest(path),
                      "rows": len(frame), "metadata": result.metadata, "credentials_recorded": False}
            meta.write_text(json.dumps(record, indent=2) + "\n")
        total += record["metadata"]["response_bytes"]
        assert total <= spec["total_success_byte_cap"]
        reports.append(record)
        print(json.dumps({"date": day, "rows": record["rows"], "bytes": record["metadata"]["response_bytes"],
                          "pagination_complete": record["metadata"]["pagination_complete"]}), flush=True)
    (DEST / "manifest.json").write_text(json.dumps({"complete": len(reports) == len(spec["dates"]),
        "files": reports, "response_bytes": total, "billing_changed": False, "orders_submitted": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
