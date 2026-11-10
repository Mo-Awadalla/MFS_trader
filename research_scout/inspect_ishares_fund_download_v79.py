"""Inspect official iShares product-data workbooks without reading returns."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import requests

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
NS = {
    "ss": "urn:schemas-microsoft-com:office:spreadsheet",
}


def rows(worksheet: ET.Element) -> list[list[str]]:
    result: list[list[str]] = []
    for row in worksheet.findall(".//ss:Row", NS):
        values = [
            "".join(data.itertext()).strip()
            for data in row.findall("./ss:Cell/ss:Data", NS)
        ]
        result.append(values)
    return result


def main() -> None:
    for ticker, portfolio_id in FUNDS.items():
        response = requests.get(
            URL, params={**PARAMS, "portfolioId": portfolio_id}, timeout=60
        )
        response.raise_for_status()
        text = response.content.decode("utf-8", errors="replace")
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        text = re.sub(
            r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9A-Fa-f]+;)",
            "&amp;",
            text,
        )
        root = ET.fromstring(text)
        print(ticker, response.headers.get("content-type"), len(response.content))
        for worksheet in root.findall("./ss:Worksheet", NS):
            name = worksheet.attrib.get(
                "{urn:schemas-microsoft-com:office:spreadsheet}Name", ""
            )
            parsed = rows(worksheet)
            matches = [
                row
                for row in parsed
                if any(
                    token in " ".join(row).lower()
                    for token in ("shares outstanding", "historical", "as of date")
                )
            ]
            print("SHEET", name, "ROWS", len(parsed))
            print("HEAD", parsed[:8])
            print("MATCHES", matches[:20])


if __name__ == "__main__":
    main()
