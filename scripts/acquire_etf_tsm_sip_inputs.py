"""Acquire and integrity-gate a bounded ETF TSM SIP input snapshot (no trading)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.catalog import BarRequest, DataCatalog, StrictPanelRequest  # noqa: E402
from storage.parquet_io import parquet_path, write_bars  # noqa: E402

SYMBOLS = ("DBC", "GLD", "IEF", "IWM", "QQQ", "SHY", "SPY")
DATA_URL = "https://data.alpaca.markets/v2/stocks/bars"
CA_URL = "https://data.alpaca.markets/v1/corporate-actions"
CALENDAR_URL = "https://paper-api.alpaca.markets/v2/calendar"
CUTOFF = "2026-09-04"
_NEW_YORK = ZoneInfo("America/New_York")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _pages(url: str, params: dict[str, str], headers: dict[str, str]) -> list[Any]:
    pages: list[Any] = []
    token: str | None = None
    seen: set[str] = set()
    while True:
        query = {**params, **({"page_token": token} if token else {})}
        response = requests.get(url, headers=headers, params=query, timeout=60)
        response.raise_for_status()
        payload = response.json()
        pages.append(payload)
        if not isinstance(payload, dict):
            raise ValueError("Alpaca pagination payload is not an object")
        token = payload.get("next_page_token")
        if token and (not isinstance(token, str) or token in seen):
            raise ValueError("Alpaca pagination token is invalid or repeated")
        if token:
            seen.add(token)
        if not token:
            return pages


def _bars(pages: list[Any], symbol: str) -> pd.DataFrame:
    rows = [bar for page in pages for bar in page.get("bars", {}).get(symbol, [])]
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError(f"no bars returned for {symbol}")
    frame["timestamp"] = pd.to_datetime(frame["t"], utc=True)
    result = frame.set_index("timestamp")[["o", "h", "l", "c", "v"]]
    result.columns = ["open", "high", "low", "close", "volume"]
    result = result.astype(float).sort_index()
    result.index = result.index.normalize()
    if result.index.has_duplicates or not (result > 0).all().all():
        raise ValueError(f"invalid raw bars for {symbol}")
    return result


def calendar_session_close_utc(item: dict[str, str]) -> str:
    """Turn Alpaca's date-plus-local-close calendar record into a UTC instant."""
    try:
        session_date = date.fromisoformat(item["date"])
        local_close = time.fromisoformat(item["close"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("calendar entry requires ISO date and local close time") from exc
    return datetime.combine(session_date, local_close, _NEW_YORK).astimezone(UTC).isoformat()


def completed_calendar_entries(
    calendar: list[dict[str, str]],
    common_start: str,
    common_end: str,
    cutoff: str,
) -> list[dict[str, str]]:
    """Keep only complete exchange sessions within the frozen common panel."""
    if common_start > common_end:
        raise ValueError("common panel start is after its end")
    upper_bound = min(common_end, cutoff)
    completed = [
        item
        for item in calendar
        if isinstance(item, dict) and common_start <= item.get("date", "") <= upper_bound
    ]
    if not completed:
        raise ValueError("calendar has no completed sessions in the common panel")
    return completed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire immutable raw and adjusted SIP ETF daily inputs")
    parser.add_argument("--acquire", action="store_true", help="required opt-in for data requests")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--snapshot-id", required=True)
    args = parser.parse_args(argv)
    if not args.acquire:
        parser.error("--acquire is required")
    values = dotenv_values(args.env_file.resolve())
    key, secret = values.get("ALPACA_API_KEY"), values.get("ALPACA_API_SECRET")
    if not key or not secret:
        print("missing Alpaca credentials", file=sys.stderr)
        return 2
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    snapshot = args.snapshot_id
    if Path(snapshot).name != snapshot or snapshot in {"", ".", ".."}:
        parser.error("--snapshot-id must be one safe path component")
    data_root = ROOT / "data/parquet/etf_tsm_sip_campaign" / snapshot
    report_root = ROOT / "docs/reports/etf_campaign_inputs" / snapshot
    data_root.mkdir(parents=True, exist_ok=False)
    if report_root.exists():
        raise FileExistsError("snapshot id already exists")
    acquired_at = datetime.now(UTC).isoformat()
    end = "2026-09-05T00:00:00Z"
    artifacts: dict[str, Any] = {"raw": {}, "adjusted": {}}
    corporate_action_coverage: dict[str, Any] = {
        "cash_dividend_missing_payable_date": [],
        "cash_dividend_missing_record_date": [],
    }
    failures: list[str] = []
    for adjustment, label in (("raw", "raw"), ("all", "adjusted")):
        try:
            pages = _pages(DATA_URL, {"symbols": ",".join(SYMBOLS), "timeframe": "1Day", "start": "2000-01-01T00:00:00Z", "end": end, "feed": "sip", "adjustment": adjustment, "limit": "10000"}, headers)
            raw_path = data_root / "http" / f"bars_{label}.json"
            _atomic_json(raw_path, pages)
            for symbol in SYMBOLS:
                frame = _bars(pages, symbol)
                path = parquet_path(data_root, symbol, "1d", source=f"alpaca_sip_{label}")
                write_bars(frame, path)
                artifacts[label][symbol] = {"path": str(path), "sha256": _hash(path), "rows": len(frame), "start": str(frame.index.min()), "end": str(frame.index.max())}
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
    try:
        calendar = requests.get(CALENDAR_URL, headers=headers, params={"start": "2000-01-01", "end": CUTOFF}, timeout=60)
        calendar.raise_for_status()
        _atomic_json(data_root / "http/calendar.json", calendar.json())
        raw_ends = [pd.Timestamp(item["end"]) for item in artifacts["raw"].values()]
        raw_starts = [pd.Timestamp(item["start"]) for item in artifacts["raw"].values()]
        common_start = max(raw_starts).date().isoformat()
        common_end = min(raw_ends).date().isoformat()
        calendar_payload = calendar.json()
        if not isinstance(calendar_payload, list):
            raise ValueError("Alpaca calendar payload is not a list")
        completed_calendar = completed_calendar_entries(
            calendar_payload, common_start, common_end, CUTOFF
        )
        sessions = tuple(f"{item['date']}T00:00:00Z" for item in completed_calendar)
        closes = tuple(calendar_session_close_utc(item) for item in completed_calendar)
        strict = StrictPanelRequest(BarRequest(data_root, SYMBOLS, "1d", "alpaca_sip_raw"), sessions, closes, acquired_at)
        DataCatalog().load_strict_panel(strict)
        DataCatalog().load_strict_panel(StrictPanelRequest(BarRequest(data_root, SYMBOLS, "1d", "alpaca_sip_adjusted"), sessions, closes, acquired_at))
    except Exception as exc:  # noqa: BLE001
        failures.append(f"calendar/panel: {type(exc).__name__}: {exc}")
    try:
        actions = _pages(CA_URL, {"symbols": ",".join(SYMBOLS), "start": "2000-01-01", "end": CUTOFF, "limit": "1000"}, headers)
        _atomic_json(data_root / "http/corporate_actions.json", actions)
        cash_dividends = [
            event
            for page in actions
            for event in page.get("corporate_actions", {}).get("cash_dividends", [])
        ]
        missing_payable = [event for event in cash_dividends if not event.get("payable_date")]
        missing_record = [event for event in cash_dividends if not event.get("record_date")]
        serialize = lambda events: [  # noqa: E731
            {key: event.get(key) for key in ("id", "symbol", "ex_date", "process_date", "payable_date", "record_date")}
            for event in events
        ]
        corporate_action_coverage["cash_dividend_missing_payable_date"] = serialize(missing_payable)
        corporate_action_coverage["cash_dividend_missing_record_date"] = serialize(missing_record)
        if missing_payable:
            failures.append(f"corporate_actions: {len(missing_payable)} cash dividends lack payable_date")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"corporate_actions: {type(exc).__name__}: {exc}")
    try:
        assets: dict[str, Any] = {}
        for symbol in SYMBOLS:
            response = requests.get(f"https://paper-api.alpaca.markets/v2/assets/{symbol}", headers=headers, timeout=60)
            response.raise_for_status()
            payload = response.json()
            assets[symbol] = {key: payload.get(key) for key in ("symbol", "tradable", "fractionable", "min_trade_increment", "price_increment")}
            if not payload.get("tradable") or not payload.get("fractionable"):
                failures.append(f"assets: {symbol} is not tradable and fractionable")
        _atomic_json(data_root / "http/assets.json", assets)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"assets: {type(exc).__name__}: {exc}")
    files = [path for path in data_root.rglob("*") if path.is_file()]
    report = {"schema_version": 1, "snapshot_id": snapshot, "acquired_at": acquired_at, "completed_session_cutoff": CUTOFF, "symbols": list(SYMBOLS), "feed": "sip", "adjustments": {"execution": "raw", "signals": "all"}, "effective_fractional_minimum_dollars": 1, "artifacts": artifacts, "corporate_action_coverage": corporate_action_coverage, "files": {str(path.relative_to(data_root)): _hash(path) for path in files}, "status": "passed" if not failures else "failed", "failures": failures, "limitations": ["Dividend ex-date is not treated as a payable date; missing payable/record dates are not inferred."]}
    _atomic_json(report_root / "manifest.json", report)
    print(f"status={report['status']} manifest={report_root / 'manifest.json'}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
