"""Download and freeze official iShares Historical sheets for V79."""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "external_artifacts" / "ishares_cross_asset_flow_v79"
RAW_DIR = OUT_DIR / "raw"
OUTPUT = OUT_DIR / "historical_nav_shares_2020_2023.csv"
MANIFEST = OUT_DIR / "manifest.json"
URL = (
    "https://www.blackrock.com/varnish-api/blk-one01-product-data/"
    "product-data/api/v1/get-fund-document"
)
PARAMS = {
    "appSubType": "ISHARES",
    "appType": "PRODUCT_PAGE",
    "component": "fundDownload",
    "locale": "en_US",
    "targetSite": "us-ishares",
    "userType": "individual",
}
FUNDS = {"HYG": "239565", "IEF": "239456"}
NS = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}


def clean_xml(content: bytes) -> str:
    text = content.decode("utf-8", errors="replace")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9A-Fa-f]+;)",
        "&amp;",
        text,
    )


def historical_rows(content: bytes, ticker: str) -> pd.DataFrame:
    root = ET.fromstring(clean_xml(content))
    target = None
    name_key = "{urn:schemas-microsoft-com:office:spreadsheet}Name"
    for worksheet in root.findall("./ss:Worksheet", NS):
        if worksheet.attrib.get(name_key) == "Historical":
            target = worksheet
            break
    if target is None:
        raise RuntimeError(f"{ticker}: Historical sheet absent")
    rows: list[list[str]] = []
    for row in target.findall(".//ss:Row", NS):
        rows.append(
            [
                "".join(data.itertext()).strip()
                for data in row.findall("./ss:Cell/ss:Data", NS)
            ]
        )
    if not rows or rows[0][:4] != [
        "As Of",
        "NAV per Share",
        "Ex-Dividends",
        "Shares Outstanding",
    ]:
        raise RuntimeError(f"{ticker}: unexpected Historical header {rows[:1]}")
    frame = pd.DataFrame(
        [row[:4] for row in rows[1:] if len(row) >= 4],
        columns=["as_of", "nav_per_share", "ex_dividends", "shares_outstanding"],
    )
    frame["as_of"] = pd.to_datetime(frame["as_of"], errors="coerce")
    frame["nav_per_share"] = pd.to_numeric(frame["nav_per_share"], errors="coerce")
    frame["shares_outstanding"] = pd.to_numeric(
        frame["shares_outstanding"], errors="coerce"
    )
    frame["ticker"] = ticker
    frame = frame[
        frame["as_of"].between("2020-01-01", "2023-12-31")
        & frame["nav_per_share"].gt(0)
        & frame["shares_outstanding"].gt(0)
    ].copy()
    return frame[
        ["as_of", "ticker", "nav_per_share", "shares_outstanding", "ex_dividends"]
    ]


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    raw_manifest = {}
    for ticker, portfolio_id in FUNDS.items():
        response = requests.get(
            URL, params={**PARAMS, "portfolioId": portfolio_id}, timeout=90
        )
        response.raise_for_status()
        content = response.content
        raw_path = RAW_DIR / f"{ticker}_fundDownload.xml"
        raw_path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest().upper()
        raw_manifest[ticker] = {
            "portfolio_id": portfolio_id,
            "url": response.url,
            "bytes": len(content),
            "sha256": digest,
            "content_type": response.headers.get("content-type"),
        }
        frames.append(historical_rows(content, ticker))
    frame = pd.concat(frames, ignore_index=True).sort_values(["as_of", "ticker"])
    if frame.duplicated(["as_of", "ticker"]).any():
        raise RuntimeError("duplicate fund/date observations")
    frame.to_csv(OUTPUT, index=False)
    manifest = {
        "candidate": "v79",
        "source": "official BlackRock iShares product-data fundDownload",
        "downloaded": raw_manifest,
        "output": OUTPUT.name,
        "output_rows": len(frame),
        "output_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest().upper(),
        "date_min": frame["as_of"].min().strftime("%Y-%m-%d"),
        "date_max": frame["as_of"].max().strftime("%Y-%m-%d"),
        "rows_by_ticker": frame.groupby("ticker").size().to_dict(),
        "post_2023_rows_in_output": 0,
        "paid_data": False,
        "databento_call": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
