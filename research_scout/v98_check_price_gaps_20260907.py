"""One bounded single-symbol re-request of missing inputs, with raw data retained."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from research_scout import v98_market_data_20260907 as market
from research_scout.v98_earnings_answers_20260907 import NY, OUT, read, save


def main():
    panel = read("event_panel.json")
    plans = {r["day"]: r for r in read("market_request_plan.json")}
    pairs = set()
    for r in panel:
        for missing in r["missing_feature_bars"]:
            symbol, value = missing.split("@", 1)
            pairs.add((pd.Timestamp(value).tz_convert(NY).strftime("%Y-%m-%d"), symbol))
        if r["label_error"]:
            pairs.add((r["day"], r["symbol"]))
    if len(pairs) > 12:
        raise ValueError("Gap probe exceeds bounded scope")
    requests_ = []
    for day, symbol in sorted(pairs):
        params = {**plans[day]["params"], "symbols": symbol}
        requests_.append({"day": f"{day}_{symbol}_5Min", "session_day": day, "symbol": symbol, "params": params})
    save("price_gap_probe_plan.json", {"scope": "One single-symbol repeat of the same historical 5Min SIP request. No strategy changes or alternative price source. No candidate P&L inspected before this plan.", "requests": requests_})
    market.OUT = OUT / "gap_probe"
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(market.fetch_day, r): r for r in requests_}
        for future in as_completed(pending):
            request = pending[future]
            record = future.result()
            record.update(session_day=request["session_day"], symbol=request["symbol"])
            results.append(record)
    results.sort(key=lambda r: (r["session_day"], r["symbol"]))
    save("price_gap_probe_retrieval.json", results)
    print(json.dumps([{"day": r["session_day"], "symbol": r["symbol"], "complete_response": r["complete"], "returned_rows": sum(p["row_count"] for p in r["pages"])} for r in results], indent=2), flush=True)


if __name__ == "__main__":
    main()
