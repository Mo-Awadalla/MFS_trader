"""Download the free official DTS operating-cash table for v74."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "external_artifacts" / "fiscaldata_tga_v74"
OUTPUT = OUTPUT_DIR / "operating_cash_balance_2020_2023.csv"
FLOW_OUTPUT = OUTPUT_DIR / "deposits_withdrawals_2020_2023.csv"
MANIFEST = OUTPUT_DIR / "manifest.json"
URL = (
    "https://api.fiscaldata.treasury.gov/services/api/"
    "fiscal_service/v1/accounting/dts/operating_cash_balance"
)
FLOW_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/"
    "fiscal_service/v1/accounting/dts/deposits_withdrawals_operating_cash"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def fetch_all(url: str, params: dict[str, str | int]) -> tuple[pd.DataFrame, int]:
    rows = []
    page = 1
    total_pages = None
    while total_pages is None or page <= total_pages:
        query = dict(params)
        query["page[number]"] = page
        response = requests.get(url, params=query, timeout=60)
        response.raise_for_status()
        payload = response.json()
        rows.extend(payload["data"])
        total_pages = int(payload["meta"]["total-pages"])
        total_count = int(payload["meta"]["total-count"])
        page += 1
    if len(rows) != total_count:
        raise RuntimeError(f"API row count mismatch: {len(rows)} != {total_count}")
    return pd.DataFrame(rows), total_count


def main() -> None:
    params = {
        "filter": "record_date:gte:2020-12-01,record_date:lte:2023-12-31",
        "sort": "record_date,src_line_nbr",
        "page[size]": 10000,
    }
    frame, total_count = fetch_all(URL, params)
    flow_frame, flow_total_count = fetch_all(FLOW_URL, params)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT, index=False)
    flow_frame.to_csv(FLOW_OUTPUT, index=False)
    manifest = {
        "candidate": "v74",
        "source": URL,
        "publisher": "U.S. Treasury Bureau of the Fiscal Service",
        "filter": params["filter"],
        "rows": int(len(frame)),
        "record_dates": int(frame["record_date"].nunique()),
        "first_record_date": str(frame["record_date"].min()),
        "last_record_date": str(frame["record_date"].max()),
        "api_total_count": total_count,
        "output_sha256": sha256(OUTPUT),
        "flow_source": FLOW_URL,
        "flow_rows": int(len(flow_frame)),
        "flow_record_dates": int(flow_frame["record_date"].nunique()),
        "flow_api_total_count": flow_total_count,
        "flow_output_sha256": sha256(FLOW_OUTPUT),
        "paid_data": False,
        "databento_call": False
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
