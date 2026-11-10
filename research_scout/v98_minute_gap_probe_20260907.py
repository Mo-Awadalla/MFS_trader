"""Inspect the same provider's one-minute records for the nine known data gaps."""

import gzip
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import pandas as pd

from research_scout import v98_market_data_20260907 as market
from research_scout.v98_earnings_answers_20260907 import NY, OUT, ROOT, read, save, sha


def main():
    original = read("price_gap_probe_plan.json")["requests"]
    if len(original) != 9:
        raise ValueError("The bounded gap set changed")
    requests_ = [
        {
            **r,
            "day": r["day"].replace("5Min", "1Min"),
            "params": {**r["params"], "timeframe": "1Min"},
        }
        for r in original
    ]
    save(
        "minute_gap_probe_plan.json",
        {
            "created_utc": datetime.now(UTC).isoformat(),
            "purpose": "At most nine requests for one-minute bars over the exact previously missing instrument-sessions, same SIP feed, adjustments and symbol mapping. No source replacement, price imputation or trading-rule change. Audit before deciding whether aggregation can recover the frozen five-minute inputs.",
            "requests": requests_,
        },
    )
    market.OUT = OUT / "minute_gap_probe"
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(market.fetch_day, r): r for r in requests_}
        for future in as_completed(pending):
            request = pending[future]
            record = future.result()
            record.update(session_day=request["session_day"], symbol=request["symbol"])
            results.append(record)
    results.sort(key=lambda r: (r["session_day"], r["symbol"]))
    save("minute_gap_probe_retrieval.json", results)
    diagnostics = []
    for r in results:
        rows = []
        for page in r["pages"]:
            raw = gzip.decompress((ROOT / page["path"]).read_bytes())
            assert sha(raw) == page["sha256"]
            rows.extend((json.loads(raw).get("bars") or {}).get(r["symbol"], []))
        times = pd.DatetimeIndex(pd.to_datetime([row["t"] for row in rows], utc=True))
        if times.has_duplicates:
            raise ValueError("Duplicate minute bars")
        opening = pd.Timestamp(r["params"]["start"])
        closing = pd.Timestamp(r["params"]["end"])
        rth = times[(times >= opening) & (times < closing)]
        diagnostics.append(
            {
                "day": r["session_day"],
                "symbol": r["symbol"],
                "regular_minute_bars": len(rth),
                "expected_regular_minutes": len(
                    pd.date_range(opening, closing, freq="min", inclusive="left")
                ),
                "five_minute_bins_present": len(set(rth.floor("5min"))),
                "first_regular_time": rth.min().tz_convert(NY).isoformat() if len(rth) else None,
                "last_regular_time": rth.max().tz_convert(NY).isoformat() if len(rth) else None,
            }
        )
    save("minute_gap_probe_audit.json", diagnostics)
    print(json.dumps(diagnostics, indent=2), flush=True)


if __name__ == "__main__":
    main()
