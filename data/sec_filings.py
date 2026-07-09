"""Point-in-time SEC material-filing ingestion and event flags.

The downloader uses only official SEC JSON endpoints, identifies every request,
and deliberately stays below the SEC fair-access request-rate ceiling. Raw SEC
responses and the deterministic normalized event table are cached together.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import requests

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_BASE_URL = "https://data.sec.gov/submissions"
DEFAULT_CACHE_DIR = Path("data/parquet/sec_filings")
DEFAULT_DELAY_SECONDS = 0.11

CIK_OVERRIDES: dict[str, str] = {
    "MMC": "0000062709",
    "FI": "0000798354",
    "BK": "0001390777",
    "XOM": "0000034088",
}

MATERIAL_FORMS = frozenset(
    {"8-K", "8-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A", "6-K", "6-K/A"}
)

_EVENT_COLUMNS = [
    "symbol",
    "cik",
    "accession_number",
    "acceptance_datetime",
    "filing_date",
    "form",
    "items",
    "primary_document",
]


class SecFilingDownloader:
    """Download and normalize SEC submissions for a fixed symbol set."""

    def __init__(
        self,
        user_agent: str | None = None,
        *,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        refresh: bool = False,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        resolved_user_agent = user_agent or os.environ.get("SEC_USER_AGENT", "")
        if not resolved_user_agent.strip():
            raise ValueError(
                "SEC_USER_AGENT is required and must identify the requester and contact address"
            )
        if delay_seconds < DEFAULT_DELAY_SECONDS:
            raise ValueError("SEC fair-access delay must be at least 0.11 seconds")

        self.cache_dir = Path(cache_dir)
        self.raw_dir = self.cache_dir / "raw"
        self.delay_seconds = float(delay_seconds)
        self.refresh = bool(refresh)
        self._session = session or requests.Session()
        self._sleep = sleep
        self._request_count = 0
        self._headers = {
            "User-Agent": resolved_user_agent.strip(),
            "Accept-Encoding": "gzip, deflate",
        }

    def _get_json(self, url: str, cache_name: str) -> Any:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        path = self.raw_dir / Path(cache_name).name
        if path.exists() and not self.refresh:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                path.unlink(missing_ok=True)

        if self._request_count:
            self._sleep(self.delay_seconds)
        response = self._session.get(url, headers=self._headers, timeout=30)
        self._request_count += 1
        response.raise_for_status()
        payload = response.json()

        path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return payload

    def company_ticker_mapping(self) -> dict[str, str]:
        """Return SEC ticker-to-zero-padded-CIK mapping plus frozen overrides."""
        payload = self._get_json(COMPANY_TICKERS_URL, "company_tickers.json")
        records: Iterable[Mapping[str, Any]]
        if isinstance(payload, Mapping):
            records = (record for record in payload.values() if isinstance(record, Mapping))
        else:
            records = ()

        mapping: dict[str, str] = {}
        for record in records:
            ticker = str(record.get("ticker", "")).strip().upper()
            cik = record.get("cik_str")
            if ticker and cik is not None:
                mapping[ticker] = str(cik).zfill(10)
        mapping.update(CIK_OVERRIDES)
        return dict(sorted(mapping.items()))

    def download(
        self,
        symbols: Sequence[str],
        *,
        start: str | pd.Timestamp | None = None,
        end: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Download material filings, filter inclusively by filing date, and cache Parquet."""
        normalized_symbols = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
        if not normalized_symbols:
            raise ValueError("At least one symbol is required")
        start_date = _calendar_date(start)
        end_date = _calendar_date(end)
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("start must not be after end")

        ticker_mapping = self.company_ticker_mapping()
        missing = [symbol for symbol in normalized_symbols if symbol not in ticker_mapping]
        if missing:
            raise KeyError(f"SEC CIK mapping missing symbols: {', '.join(missing)}")

        symbols_by_cik: dict[str, list[str]] = {}
        for symbol in normalized_symbols:
            symbols_by_cik.setdefault(ticker_mapping[symbol], []).append(symbol)

        rows: list[dict[str, Any]] = []
        for cik, cik_symbols in sorted(symbols_by_cik.items()):
            representative_symbol = sorted(cik_symbols)[0]
            submissions_name = f"CIK{cik}.json"
            submissions = self._get_json(
                f"{SUBMISSIONS_BASE_URL}/{submissions_name}", submissions_name
            )
            filings = submissions.get("filings", {}) if isinstance(submissions, Mapping) else {}
            recent = filings.get("recent", {}) if isinstance(filings, Mapping) else {}
            rows.extend(_parse_filing_arrays(recent, symbol=representative_symbol, cik=cik))

            archive_metadata = filings.get("files", []) if isinstance(filings, Mapping) else []
            for metadata in _relevant_archives(archive_metadata, start_date, end_date):
                archive_name = str(metadata["name"])
                archive = self._get_json(
                    f"{SUBMISSIONS_BASE_URL}/{archive_name}", archive_name
                )
                rows.extend(
                    _parse_filing_arrays(archive, symbol=representative_symbol, cik=cik)
                )

        events = _normalize_events(rows, start_date=start_date, end_date=end_date)
        events = _expand_shared_cik_symbols(events, symbols_by_cik)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        events.to_parquet(self.cache_dir / "sec_filing_events.parquet", index=False)
        return events


def _calendar_date(value: str | pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None or str(value).strip() == "":
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize()


def _relevant_archives(
    metadata_rows: Any,
    start_date: pd.Timestamp | None,
    end_date: pd.Timestamp | None,
) -> list[Mapping[str, Any]]:
    if not isinstance(metadata_rows, list):
        return []
    relevant: list[Mapping[str, Any]] = []
    for metadata in metadata_rows:
        if not isinstance(metadata, Mapping) or not metadata.get("name"):
            continue
        archive_start = _calendar_date(metadata.get("filingFrom"))
        archive_end = _calendar_date(metadata.get("filingTo"))
        if start_date is not None and archive_end is not None and archive_end < start_date:
            continue
        if end_date is not None and archive_start is not None and archive_start > end_date:
            continue
        relevant.append(metadata)
    return sorted(relevant, key=lambda row: str(row["name"]))


def _parse_filing_arrays(
    arrays: Any,
    *,
    symbol: str,
    cik: str,
) -> list[dict[str, Any]]:
    if not isinstance(arrays, Mapping):
        return []
    accessions = arrays.get("accessionNumber", [])
    if not isinstance(accessions, list):
        return []

    def value(field: str, index: int) -> Any:
        values = arrays.get(field, [])
        return values[index] if isinstance(values, list) and index < len(values) else ""

    return [
        {
            "symbol": symbol,
            "cik": cik,
            "accession_number": str(accession).strip(),
            "acceptance_datetime": value("acceptanceDateTime", index),
            "filing_date": value("filingDate", index),
            "form": str(value("form", index)).strip().upper(),
            "items": str(value("items", index)).strip(),
            "primary_document": str(value("primaryDocument", index)).strip(),
        }
        for index, accession in enumerate(accessions)
        if str(accession).strip()
    ]


def _parse_acceptance(value: Any, filing_date: pd.Timestamp) -> pd.Timestamp:
    text = str(value).strip()
    if not text:
        return filing_date.tz_localize("UTC")
    if len(text) == 14 and text.isdigit():
        return pd.to_datetime(text, format="%Y%m%d%H%M%S", utc=True)
    return pd.to_datetime(text, utc=True)


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": pd.Series(dtype="object"),
            "cik": pd.Series(dtype="object"),
            "accession_number": pd.Series(dtype="object"),
            "acceptance_datetime": pd.Series(dtype="datetime64[ns, UTC]"),
            "filing_date": pd.Series(dtype="datetime64[ns]"),
            "form": pd.Series(dtype="object"),
            "items": pd.Series(dtype="object"),
            "primary_document": pd.Series(dtype="object"),
        }
    )


def _normalize_events(
    rows: list[dict[str, Any]],
    *,
    start_date: pd.Timestamp | None,
    end_date: pd.Timestamp | None,
) -> pd.DataFrame:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if row["form"] not in MATERIAL_FORMS:
            continue
        filing_date = _calendar_date(row["filing_date"])
        if filing_date is None:
            continue
        if start_date is not None and filing_date < start_date:
            continue
        if end_date is not None and filing_date > end_date:
            continue
        normalized.append(
            {
                **row,
                "filing_date": filing_date,
                "acceptance_datetime": _parse_acceptance(
                    row["acceptance_datetime"], filing_date
                ),
            }
        )
    if not normalized:
        return _empty_events()

    events = pd.DataFrame(normalized, columns=_EVENT_COLUMNS)
    events = events.sort_values(
        ["cik", "accession_number", "acceptance_datetime", "symbol"], kind="stable"
    )
    events = events.drop_duplicates(["cik", "accession_number"], keep="first")
    return events.sort_values(
        ["acceptance_datetime", "cik", "accession_number"], kind="stable"
    ).reset_index(drop=True)


def _expand_shared_cik_symbols(
    events: pd.DataFrame,
    symbols_by_cik: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    """Propagate one deduplicated issuer filing to every requested share class."""
    if events.empty:
        return events
    rows: list[dict[str, Any]] = []
    for row in events.to_dict(orient="records"):
        fallback_symbol = str(row["symbol"])
        for symbol in sorted(symbols_by_cik.get(str(row["cik"]), [fallback_symbol])):
            rows.append({**row, "symbol": symbol})
    return (
        pd.DataFrame(rows, columns=_EVENT_COLUMNS)
        .sort_values(
            ["acceptance_datetime", "cik", "accession_number", "symbol"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def build_event_flag_matrix(
    events: pd.DataFrame,
    panel_sessions: pd.DatetimeIndex | Sequence[Any],
    *,
    symbols: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Flag each event on its first panel session strictly after acceptance date.

    Session timestamps may contain market-close times and any timezone. Only their
    calendar dates determine visibility, matching the frozen conservative policy.
    """
    sessions = pd.DatetimeIndex(panel_sessions)
    if sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise ValueError("panel_sessions must be unique and increasing")
    session_dates = sessions
    if session_dates.tz is not None:
        session_dates = session_dates.tz_convert("UTC").tz_localize(None)
    session_dates = session_dates.normalize()

    event_symbols = set(events.get("symbol", pd.Series(dtype="object")).astype(str).str.upper())
    output_symbols = sorted(
        {symbol.strip().upper() for symbol in symbols if symbol.strip()}
        if symbols is not None
        else event_symbols
    )
    flags = pd.DataFrame(0, index=sessions, columns=output_symbols, dtype="int8")
    if events.empty or sessions.empty:
        return flags
    required = {"symbol", "acceptance_datetime"}
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"events missing required columns: {', '.join(sorted(missing))}")

    for event in events.sort_values(["acceptance_datetime", "symbol"], kind="stable").itertuples():
        symbol = str(event.symbol).upper()
        if symbol not in flags.columns or pd.isna(event.acceptance_datetime):
            continue
        acceptance = pd.Timestamp(event.acceptance_datetime)
        if acceptance.tzinfo is not None:
            acceptance = acceptance.tz_convert("UTC").tz_localize(None)
        event_date = acceptance.normalize()
        position = int(session_dates.searchsorted(event_date, side="right"))
        if position < len(sessions):
            flags.iat[position, flags.columns.get_loc(symbol)] = 1
    return flags
