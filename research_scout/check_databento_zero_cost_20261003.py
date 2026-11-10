"""Free metadata estimates only. This module cannot request market-data delivery."""

import json
import math
import os
from datetime import UTC, datetime

import requests
from dotenv import dotenv_values

from research_scout.inspect_databento_public_sample_20261003 import OUT, ROOT


def main():
    target = OUT / "zero_cost_metadata_check.json"
    assert not target.exists()
    key = os.getenv("DATABENTO_API_KEY") or dotenv_values(ROOT / ".env").get("DATABENTO_API_KEY")
    report = {"checked_at_utc": datetime.now(UTC).isoformat(), "credential_available": bool(key),
              "free_metadata_requests": 0, "market_data_requests": 0, "paid_calls": 0,
              "pricing_reference": "https://databento.com/docs/api-reference-historical/basics/metered-pricing",
              "quotes": []}
    if key:
        for schema in ("mbo", "mbp-1"):
            query = {"dataset": "XNAS.ITCH", "symbols": "NVDA", "schema": schema,
                     "stype_in": "raw_symbol", "start": "2025-09-17T00:00:00Z", "end": "2025-09-18T00:00:00Z"}
            with requests.get("https://hist.databento.com/v0/metadata.get_cost", params=query,
                              auth=(key, ""), allow_redirects=False, timeout=(10, 30)) as response:
                report["free_metadata_requests"] += 1
                result = {"query": query, "http_status": response.status_code}
                if response.status_code == 200:
                    cost = response.json()
                    assert isinstance(cost, (float, int)) and math.isfinite(cost) and cost >= 0
                    result.update(estimated_cost_usd=cost, quoted_zero=(cost == 0))
                else:
                    result["quoted_zero"] = False
                report["quotes"].append(result)
                print(json.dumps(result), flush=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"credential_available": bool(key), "free_metadata_requests": report["free_metadata_requests"],
                      "market_data_requests": 0, "paid_calls": 0}), flush=True)


if __name__ == "__main__":
    main()
