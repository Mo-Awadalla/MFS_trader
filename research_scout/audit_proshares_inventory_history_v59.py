"""Returns-blind audit of free official UPRO/SPXU inventory history.

This script downloads only public ProShares, SEC EDGAR, and Internet Archive
files. It does not call Databento and does not read any strategy return.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "proshares_inventory_v59"
OUTPUT = ROOT / "research_scout" / "proshares_inventory_history_audit_v59.json"
REPORT = ROOT / "research_scout" / "PROSHARES_INVENTORY_HISTORY_AUDIT_V59.md"

PROSHARES = {
    "current_holdings": "https://accounts.profunds.com/etfdata/psdlyhld.csv",
    "historical_nav": "https://accounts.profunds.com/etfdata/historical_nav.csv",
    "split_history": "https://accounts.profunds.com/etfdata/etf_splits.csv",
}
WAYBACK_CDX = (
    "https://web.archive.org/cdx/search/cdx?"
    + urllib.parse.urlencode(
        {
            "url": PROSHARES["current_holdings"],
            "from": "2021",
            "to": "2023",
            "output": "json",
            "filter": "statuscode:200",
            "fl": "timestamp,original,statuscode,mimetype,digest,length",
        }
    )
)
SEC_ATOM = {
    "UPRO": (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcompany&CIK=S000024919&type=NPORT-P&owner=exclude"
        "&count=100&output=atom"
    ),
    "SPXU": (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        "action=getcompany&CIK=S000024911&type=NPORT-P&owner=exclude"
        "&count=100&output=atom"
    ),
}
START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")


def download(url: str, user_agent: str) -> tuple[bytes, dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
        metadata = {
            "url": url,
            "status": int(response.status),
            "content_type": response.headers.get("Content-Type"),
            "last_modified": response.headers.get("Last-Modified"),
            "etag": response.headers.get("ETag"),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return data, metadata


def save_raw(name: str, data: bytes) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    path.write_bytes(data)
    return path


def download_or_cache(
    url: str, raw_name: str, user_agent: str
) -> tuple[bytes, dict[str, Any]]:
    """Download a source, recording any explicit fallback to a hashed local copy."""
    try:
        data, metadata = download(url, user_agent)
        save_raw(raw_name, data)
        metadata["cache_fallback"] = False
        return data, metadata
    except Exception as exc:
        path = RAW / raw_name
        if not path.exists():
            raise
        data = path.read_bytes()
        return data, {
            "url": url,
            "status": None,
            "content_type": None,
            "last_modified": None,
            "etag": None,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "cache_fallback": True,
            "remote_error": f"{type(exc).__name__}: {exc}",
        }


def load_spy_sessions() -> pd.DatetimeIndex:
    path = ROOT / "data" / "parquet" / "equity" / "yahoo_chart" / "SPY_1d.parquet"
    frame = pd.read_parquet(path)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    days = (
        timestamps.dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    return pd.DatetimeIndex(
        sorted({day for day in days if START <= day <= END})
    )


def parse_as_of(data: bytes) -> str | None:
    text = data[:1000].decode("utf-8", errors="replace")
    match = re.search(r"AS OF\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
    return match.group(1) if match else None


def parse_holdings_csv(data: bytes) -> pd.DataFrame:
    """Parse ProShares holdings despite its blank trailing CSV field."""
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    header_index = next(
        index for index, row in enumerate(rows) if row and row[0].strip() == "Fund Ticker"
    )
    columns = [value.strip() for value in rows[header_index]]
    normalized = [
        (row[: len(columns)] + [""] * len(columns))[: len(columns)]
        for row in rows[header_index + 1 :]
        if any(value.strip() for value in row)
    ]
    return pd.DataFrame(normalized, columns=columns)


def parse_atom(data: bytes) -> list[dict[str, str | None]]:
    root = ET.fromstring(data)

    def first_local(element: ET.Element, name: str) -> str | None:
        for child in element.iter():
            if child.tag.rsplit("}", 1)[-1] == name and child.text:
                return child.text.strip()
        return None

    rows: list[dict[str, str | None]] = []
    for entry in root.iter():
        if entry.tag.rsplit("}", 1)[-1] != "entry":
            continue
        rows.append(
            {
                "accession_number": first_local(entry, "accession-number"),
                "filing_date": first_local(entry, "filing-date"),
                "period": first_local(entry, "period"),
                "filing_href": first_local(entry, "filing-href"),
            }
        )
    return rows


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def render(payload: dict[str, Any]) -> str:
    nav = payload["historical_nav"]
    holdings = payload["historical_holdings_archive"]
    failures = [
        name for name, passed in payload["admission_gates"].items() if not passed
    ]
    lines = [
        "# ProShares Inventory History Audit v59",
        "",
        "## Verdict",
        "",
        (
            "**Historical inventory admission passed.**"
            if payload["admission_passed"]
            else (
                "**Rejected returns-blind. No strategy P&L may be opened from "
                "this inventory path.**"
            )
        ),
        "",
        "No Databento endpoint and no strategy return was used.",
        "",
        "## 2021-2023 daily NAV/AUM",
        "",
        f"- Expected SPY sessions: {nav['expected_sessions']}",
    ]
    for symbol in ["UPRO", "SPXU"]:
        item = nav["symbols"][symbol]
        lines.extend(
            [
                (
                    f"- {symbol}: {item['sessions']} sessions, "
                    f"{item['coverage']:.3%} coverage"
                ),
                (
                    f"- {symbol} AUM identity maximum relative error: "
                    f"{item['aum_identity_max_relative_error']:.8f}"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Daily holdings archive",
            "",
            f"- Public 2021-2023 captures found: {holdings['capture_count']}",
            f"- Distinct holdings as-of dates recovered: {holdings['distinct_as_of_dates']}",
            f"- Session coverage: {holdings['session_coverage']:.3%}",
            "",
            "## SEC validation",
            "",
        ]
    )
    for symbol in ["UPRO", "SPXU"]:
        item = payload["sec_nport"][symbol]
        lines.append(
            f"- {symbol}: {item['development_filing_count']} public N-PORT filings "
            "filed during 2021-2023"
        )
    lines.extend(
        [
            "",
            "Failed admission gates: "
            + (", ".join(failures) if failures else "none"),
            "",
            "## Boundary",
            "",
            "Daily NAV, AUM, shares outstanding, and split history are excellent, "
            "but they do not replace dated daily derivative holdings. The frozen "
            "98% holdings and causal-publication gates are not relaxed. AUM-only "
            "rebalance testing would be a post-audit proxy substitution.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    fetched_at = datetime.now(UTC).isoformat()
    source_meta: dict[str, Any] = {}
    raw_data: dict[str, bytes] = {}
    for name, url in PROSHARES.items():
        data, metadata = download_or_cache(
            url, f"{name}.csv", "quant-research-audit/1.0"
        )
        raw_data[name] = data
        source_meta[name] = metadata

    cdx_data, cdx_meta = download_or_cache(
        WAYBACK_CDX,
        "wayback_cdx_2021_2023.json",
        "quant-research-audit/1.0",
    )
    source_meta["wayback_cdx"] = cdx_meta
    cdx_rows = json.loads(cdx_data)
    cdx_header = cdx_rows[0] if cdx_rows else []
    captures = [dict(zip(cdx_header, row, strict=False)) for row in cdx_rows[1:]]

    recovered: list[dict[str, Any]] = []
    for capture in captures:
        timestamp = str(capture["timestamp"])
        archive_url = (
            f"https://web.archive.org/web/{timestamp}id_/"
            f"{PROSHARES['current_holdings']}"
        )
        item: dict[str, Any] = {"timestamp": timestamp, "url": archive_url}
        try:
            data, metadata = download_or_cache(
                archive_url,
                f"holdings_wayback_{timestamp}.csv",
                "quant-research-audit/1.0",
            )
            item.update(metadata)
            item["as_of"] = parse_as_of(data)
        except Exception as exc:  # noqa: BLE001 - audit records remote failure
            item["error"] = f"{type(exc).__name__}: {exc}"
        recovered.append(item)

    sec_rows: dict[str, list[dict[str, str | None]]] = {}
    for symbol, url in SEC_ATOM.items():
        data, metadata = download_or_cache(
            url,
            f"sec_{symbol.lower()}_nport_atom.xml",
            "quant-research-audit/1.0 local@example.invalid",
        )
        source_meta[f"sec_{symbol.lower()}_nport_atom"] = metadata
        sec_rows[symbol] = parse_atom(data)

    expected = load_spy_sessions()
    nav_frame = pd.read_csv(io.BytesIO(raw_data["historical_nav"]))
    nav_frame["Date"] = pd.to_datetime(nav_frame["Date"], errors="coerce")
    nav_frame = nav_frame[
        nav_frame["Ticker"].isin(["UPRO", "SPXU"])
        & nav_frame["Date"].between(START, END)
    ].copy()
    nav_summary: dict[str, Any] = {
        "expected_sessions": len(expected),
        "symbols": {},
    }
    expected_set = set(expected)
    for symbol in ["UPRO", "SPXU"]:
        selected = nav_frame[nav_frame["Ticker"] == symbol].copy()
        selected = selected.sort_values("Date")
        observed = set(pd.DatetimeIndex(selected["Date"]).normalize())
        shares = pd.to_numeric(
            selected["Shares Outstanding (000)"], errors="coerce"
        )
        nav = pd.to_numeric(selected["NAV"], errors="coerce")
        aum = pd.to_numeric(selected["Assets Under Management"], errors="coerce")
        implied_aum = nav * shares * 1000.0
        relative_error = (implied_aum - aum).abs() / aum.abs()
        nav_summary["symbols"][symbol] = {
            "sessions": len(observed),
            "coverage": len(expected_set.intersection(observed)) / len(expected),
            "missing_sessions": sorted(expected_set - observed),
            "duplicate_dates": int(selected["Date"].duplicated().sum()),
            "nonpositive_nav_rows": int((nav <= 0).sum()),
            "nonpositive_aum_rows": int((aum <= 0).sum()),
            "missing_shares_rows": int(shares.isna().sum()),
            "aum_identity_median_relative_error": float(relative_error.median()),
            "aum_identity_max_relative_error": float(relative_error.max()),
        }

    split_frame = pd.read_csv(io.BytesIO(raw_data["split_history"]))
    split_frame["Date of Split"] = pd.to_datetime(
        split_frame["Date of Split"], errors="coerce"
    )
    split_rows = split_frame[
        split_frame["Symbol"].isin(["UPRO", "SPXU"])
        & split_frame["Date of Split"].between(START, END)
    ].to_dict(orient="records")

    current_holdings = parse_holdings_csv(raw_data["current_holdings"])
    current_selected = current_holdings[
        current_holdings["Fund Ticker"].isin(["UPRO", "SPXU"])
    ].copy()
    current_summary: dict[str, Any] = {
        "as_of": parse_as_of(raw_data["current_holdings"]),
        "symbols": {},
    }
    for symbol in ["UPRO", "SPXU"]:
        selected = current_selected[current_selected["Fund Ticker"] == symbol]
        descriptions = selected["Security Description"].fillna("").astype(str)
        current_summary["symbols"][symbol] = {
            "rows": len(selected),
            "swap_rows": int(descriptions.str.contains("SWAP", case=False).sum()),
            "futures_rows": int(
                descriptions.str.contains("FUT", case=False).sum()
            ),
            "has_exposure_value": bool(
                pd.to_numeric(
                    selected["Exposure Value (Notional + G/L)"], errors="coerce"
                ).notna().any()
            ),
            "has_market_value": bool(
                pd.to_numeric(selected["Market Value"], errors="coerce")
                .notna()
                .any()
            ),
        }

    as_of_dates = sorted(
        {
            item["as_of"]
            for item in recovered
            if item.get("as_of") is not None
        }
    )
    archive_coverage = len(as_of_dates) / len(expected)
    sec_summary: dict[str, Any] = {}
    for symbol, rows in sec_rows.items():
        development_rows = [
            row
            for row in rows
            if row.get("filing_date")
            and "2021-01-01" <= str(row["filing_date"]) <= "2023-12-31"
        ]
        sec_summary[symbol] = {
            "all_returned_filing_count": len(rows),
            "development_filing_count": len(development_rows),
            "development_filings": development_rows,
        }

    nav_coverage_pass = all(
        nav_summary["symbols"][symbol]["coverage"] >= 0.98
        for symbol in ["UPRO", "SPXU"]
    )
    aum_identity_pass = all(
        nav_summary["symbols"][symbol]["aum_identity_max_relative_error"] <= 1e-5
        for symbol in ["UPRO", "SPXU"]
    )
    current_fields_pass = all(
        current_summary["symbols"][symbol]["swap_rows"] > 0
        and current_summary["symbols"][symbol]["has_exposure_value"]
        for symbol in ["UPRO", "SPXU"]
    )
    gates = {
        "daily_holdings_coverage_at_least_98_percent": archive_coverage >= 0.98,
        "historical_holdings_publication_timing_known": False,
        "daily_nav_aum_coverage_at_least_98_percent": nav_coverage_pass,
        "aum_reconciles_to_nav_times_shares": aum_identity_pass,
        "current_holdings_separate_derivative_exposure": current_fields_pass,
        "split_history_available": not split_frame.empty,
        "sec_nport_validation_present": all(
            sec_summary[symbol]["development_filing_count"] >= 1
            for symbol in ["UPRO", "SPXU"]
        ),
        "no_target_returns_or_strategy_pnl_read": True,
    }
    payload = {
        "status": "returns_blind_free_public_data_inventory_audit",
        "fetched_at_utc": fetched_at,
        "databento_calls_or_purchases": False,
        "source_metadata": source_meta,
        "historical_nav": nav_summary,
        "split_history_2021_2023": split_rows,
        "current_holdings_schema": current_summary,
        "historical_holdings_archive": {
            "capture_count": len(captures),
            "captures": recovered,
            "distinct_as_of_dates": len(as_of_dates),
            "as_of_dates": as_of_dates,
            "session_coverage": archive_coverage,
        },
        "sec_nport": sec_summary,
        "admission_gates": gates,
        "admission_passed": all(gates.values()),
        "decision": (
            "historical_inventory_path_admitted"
            if all(gates.values())
            else "reject_before_strategy_returns"
        ),
    }
    safe = json_safe(payload)
    OUTPUT.write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render(safe), encoding="utf-8")
    print(json.dumps(safe, indent=2))


if __name__ == "__main__":
    main()
